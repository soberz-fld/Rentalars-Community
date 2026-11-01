# SPDX-License-Identifier: GPL-3.0-or-later
"""The full export of all data in open formats (IMP-006).

One ZIP file holds everything Rentalars knows:

``json/<app>.<model>.json``
    Every table in the JSON format of Django. The files can be read by any
    program and loaded into an empty Rentalars with ``manage.py loaddata``.
``csv/<app>.<model>.csv``
    The same tables as CSV (semicolon, UTF-8), one column per field, for
    spreadsheet programs.
``dateien/…``
    All stored files – project files, mail attachments, documents, photos –
    under the names the tables refer to.
``LIESMICH.txt``
    What is in the archive and what is left out.

Left out are secrets that are of no use outside this installation and
dangerous in the wrong hands: password hashes, the secrets of two-factor
logins, API token hashes, mail passwords, the setup token; and technical
tables (sessions, login attempts, Django's own bookkeeping). The export is
made in the background (NFA-041) and only by administrators: it contains the
personal data of everybody.

IMP-006: the button is a section of the page "Sicherung"
(``core.settings_views.full_export``), which says how the export differs from
a backup: a backup (``core.backup``) restores Rentalars – the whole database
with its secrets, the configuration, the files, encrypted if switched on –;
the export is for reading by people and other programs, without secrets.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from rentalars.core.i18n import is_english, local_pattern

#: Tables that are not exported: technical bookkeeping, short-lived data.
EXCLUDED_MODELS = frozenset(
    {
        "admin.logentry",
        "auth.permission",
        "contenttypes.contenttype",
        "sessions.session",
        "accounts.loginattempt",
        "accounts.usersession",
        "core.backgroundjob",
        # API-012: a webhook's address may itself be a secret link, and its signing secret is one;
        # the deliveries are a short-lived log of what was sent.
        "api.webhook",
        "api.webhookdelivery",
        # The request ids the link service has seen – bookkeeping that lives for minutes.
        "gateway_link.gatewayreplay",
    }
)

#: Fields that are left empty in the export: secrets.
SECRET_FIELDS: dict[str, frozenset[str]] = {
    "accounts.user": frozenset({"password", "totp_secret_encrypted", "totp_last_step", "recovery_code_hashes"}),
    "accounts.apitoken": frozenset({"key_hash"}),
    # AUT-029: the password of the search account of the directory login.
    "accounts.ldapsettings": frozenset({"bind_password_encrypted"}),
    # EML-041: the access data of every mailbox.
    "mail.mailbox": frozenset({"imap_password_encrypted", "smtp_password_encrypted"}),
    "core.systemsettings": frozenset({"setup_token"}),
    # PER-022, PER-023: the subscription link works like a password, a private ICS link reveals a
    # calendar, and the CalDAV password is one. The key of an encrypted backup sits in its task.
    "personnel.person": frozenset({"calendar_token", "caldav_password_encrypted"}),
    "personnel.calendarfeed": frozenset({"url"}),  # PER-031: the linked calendars
    "core.backgroundjob": frozenset({"params"}),
    "documents.accountingsettings": frozenset({"lexware_api_key_encrypted"}),  # DOK-011
    "api.webhook": frozenset({"secret_encrypted"}),  # API-012: the key the receiver checks the signature with
    # PER-032: whoever has the token of a deployment request answers it by mail.
    "mail.crewrequestmail": frozenset({"token"}),
    "ai.aiprovider": frozenset({"api_key_encrypted"}),  # ADM-017: the key of an AI interface
    # ADM-016: the token names a prepared address change that root applies with it.
    "core.addresschange": frozenset({"token"}),
    # VFG-040: the calendar link of a product, model or item works without login, like a password.
    "schedule.calendarlink": frozenset({"token"}),
    # The two private keys of the link to the Rentalars Gateway and the secret of an open pairing offer.
    # After loading the data the link is set up again (rentalars gateway connect) and the devices are paired anew.
    "gateway_link.gatewaylink": frozenset({"link_key", "e2e_key"}),
    "gateway_link.gatewaypairing": frozenset({"secret"}),
}

#: Folders of stored files that are not exported: the results of tasks (earlier exports among them).
EXCLUDED_FOLDERS = ("jobs/",)

README = """Rentalars – vollständiger Datenexport
=====================================

Erstellt: {created}
Version:  Rentalars {version}

Inhalt
------
json/     Jede Tabelle als JSON-Datei im Format von Django. Ein frisch
          installiertes Rentalars derselben Version lädt sie, im
          ausgepackten Ordner, mit „sudo rentalars loaddata json/*.json“.
csv/      Dieselben Tabellen als CSV (Semikolon, UTF-8) für
          Tabellenprogramme. Eine Spalte je Feld; Verweise auf andere
          Tabellen stehen als ID.
dateien/  Alle gespeicherten Dateien (Projektdateien, Mailanhänge,
          Dokumente, Fotos) unter dem Namen, den die Tabellen nennen.
          Nach dem Laden gehören sie nach /var/lib/rentalars/media/.

Nicht enthalten
---------------
Passwörter (nur ihre Prüfsummen wären gespeichert), Geheimnisse der
Zwei-Faktor-Anmeldung, API-Schlüssel, Passwörter des Postfachs, das
Einrichtungs-Token, Webhooks, Sitzungen, Anmeldeversuche und Aufgaben
im Hintergrund. Nach einem Laden der Daten setzen alle Nutzer ein neues
Passwort, und das Postfach wird neu eingetragen.

Der Export enthält personenbezogene Daten von Kunden, Personal und
Nutzern. Bitte so aufbewahren und weitergeben, wie es der Datenschutz
verlangt.
"""

#: UIX-029: the same for a user whose language is English. The folder names stay as they are.
README_ENGLISH = """Rentalars – complete data export
================================

Created: {created}
Version: Rentalars {version}

Contents
--------
json/     Every table as a JSON file in Django's format. A freshly
          installed Rentalars of the same version loads them, in the
          unpacked folder, with "sudo rentalars loaddata json/*.json".
csv/      The same tables as CSV (semicolon, UTF-8) for spreadsheet
          programs. One column per field; references to other tables
          are given as IDs.
dateien/  All stored files (project files, mail attachments, documents,
          photos) under the names the tables give. After loading they
          belong in /var/lib/rentalars/media/.

Not included
------------
Passwords (only their checksums would be stored), the secrets of the
two-factor login, API keys, mailbox passwords, the setup token,
webhooks, sessions, login attempts and tasks in the background. After
loading the data, every user sets a new password, and the mailbox is
entered again.

The export contains personal data of customers, staff and users. Please
keep and pass it on as data protection requires.
"""


def exported_models() -> list[type[models.Model]]:
    """The models whose tables are exported, in an order that loads (referenced tables first)."""
    app_list = {app_config: None for app_config in apps.get_app_configs() if app_config.models_module is not None}
    ordered = serializers.sort_dependencies(app_list.items(), allow_cycles=True)
    return [model for model in ordered if model._meta.label_lower not in EXCLUDED_MODELS and model._meta.managed]


def _fields(model: type[models.Model]) -> list[str]:
    secrets = SECRET_FIELDS.get(model._meta.label_lower, frozenset())
    return [field.name for field in model._meta.local_fields if field.name not in secrets and not field.primary_key]


def _rows(model: type[models.Model]) -> Iterator[models.Model]:
    return model._base_manager.order_by("pk").iterator(chunk_size=2000)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)
    if isinstance(value, models.fields.files.FieldFile):
        return value.name or ""
    return str(value)


def _write_table(archive: zipfile.ZipFile, model: type[models.Model]) -> int:
    """Write one table as JSON and as CSV; returns the number of rows."""
    label = model._meta.label_lower
    fields = _fields(model)
    with archive.open(f"json/{label}.json", "w") as raw:
        stream = io.TextIOWrapper(raw, encoding="utf-8")
        many_to_many = [field.name for field in model._meta.local_many_to_many]
        serializers.serialize(
            "json", _rows(model), stream=stream, fields=[*fields, *many_to_many], indent=1, ensure_ascii=False
        )
        stream.flush()
        stream.detach()
    count = 0
    attnames = ["id", *[model._meta.get_field(name).attname for name in fields]]
    with archive.open(f"csv/{label}.csv", "w") as raw:
        stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(attnames)
        for record in _rows(model):
            writer.writerow([_csv_value(getattr(record, name)) for name in attnames])
            count += 1
        stream.flush()
        stream.detach()
    return count


def _stored_files() -> Iterator[tuple[Path, str]]:
    root = Path(settings.MEDIA_ROOT)
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(EXCLUDED_FOLDERS):
            continue
        yield path, relative


def write_export(target: Path, progress: Any = None) -> dict[str, int]:
    """Write the whole archive to ``target``; returns the number of rows per table and of files."""
    from rentalars import __version__

    tables = exported_models()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        archive.writestr(
            "LIESMICH.txt",
            (README_ENGLISH if is_english() else README).format(
                created=timezone.localtime().strftime(local_pattern("%d.%m.%Y %H:%M")), version=__version__
            ),
        )
        for position, model in enumerate(tables):
            counts[model._meta.label_lower] = _write_table(archive, model)
            if progress is not None:
                progress(5 + 60 * (position + 1) // len(tables))
        files = list(_stored_files())
        for position, (path, relative) in enumerate(files):
            archive.write(path, f"dateien/{relative}")
            if progress is not None and position % 20 == 0:
                progress(65 + 30 * position // max(len(files), 1))
        counts["files"] = len(files)
    return counts


def start(user: Any) -> Any:
    """Start the full export as a task in the background; returns the task."""
    from django.utils.translation import gettext as _

    from rentalars.core.audit import record_event
    from rentalars.core.jobs import start_job
    from rentalars.core.models import SystemSettings

    record_event(SystemSettings.load(), "export.full", {"by": str(user)})
    return start_job("export", {}, user=user, title=_("Full data export"))


def run_job(job: Any) -> tuple[Path, str]:
    """The background task: write the archive into a temporary file."""
    from rentalars.core.jobs import report_progress

    handle = tempfile.NamedTemporaryFile(prefix="rentalars-export-", suffix=".zip", delete=False)  # noqa: SIM115
    handle.close()
    target = Path(handle.name)
    counts = write_export(target, progress=lambda percent: report_progress(job, percent))
    job.result = {
        "tables": len(counts) - 1,
        "rows": sum(v for k, v in counts.items() if k != "files"),
        "files": counts["files"],
    }
    return target, f"rentalars-export-{timezone.localdate():%Y-%m-%d}.zip"
