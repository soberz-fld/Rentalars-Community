# SPDX-License-Identifier: GPL-3.0-or-later
"""Two settings of Einstellungen → Benachrichtigungen on by default (VFG-036, DOK-015).

The requirement: the notices about known shortages being repeated at each check and about service cases are on by default –
for existing installations too, switched on by the update.

* ``shortage_repeat`` ("bekannte Fehlbestände bei jeder Prüfung erneut melden") and ``invoice_service_cases``
  ("auch Servicefälle", the reminders of invoices) are on by default.
* The update switches both on in an existing installation as well. Each value switched is written to the change
  log of the settings as "Aktualisierung", with the value before – a fresh database (start data not
  installed yet) gets them without an entry, as ``accounts/0008_roles_091`` does.
* Against a flood of old service cases: ``invoice_cases_since`` – service cases done before it are not reminded
  of. Switching "service cases too" on in an existing installation sets it to the moment of the update, so that
  every case done earlier with work and without invoice is not reminded of at the next check (and every week
  after); they stay in the lists ("Rechnung offen"). The page and the API set it as well when somebody switches
  the setting on (``NotificationSettings.save``). A fresh database has no old cases and gets no cut-off.

Going back: the values switched on by this step – as its entry in the change log names them – are switched off
again, unless somebody has switched them off since. Without an entry (a fresh database) both stay on.
``invoice_cases_since`` goes with its column.
"""

from django.db import migrations, models
from django.utils import timezone

ACTOR = "Aktualisierung 0.9.3"
#: The fields this step switches on.
FIELDS = ("shortage_repeat", "invoice_service_cases")
#: How the change log names the settings (``str()`` of the model in German, the language of the installation).
REPR = "Benachrichtigungen der Firma"


def _content_type(apps):
    return apps.get_model("contenttypes", "ContentType").objects.get_or_create(
        app_label="core", model="notificationsettings"
    )[0]


def switch_on(apps, schema_editor):
    """The data step: both settings on; what was off is noted in the change log.

    Service cases switched on in an existing installation: only those done from now on are reminded of
    (``invoice_cases_since``) – a bookkeeping value, not in the change log.
    """
    settings_model = apps.get_model("core", "NotificationSettings")
    row = settings_model.objects.filter(pk=1).first()
    if row is None:
        return  # created on first use, with the new defaults; the first check sets the cut-off of all reminders
    changes = {name: [False, True] for name in FIELDS if not getattr(row, name)}
    if not changes:
        return
    system_settings = apps.get_model("core", "SystemSettings").objects.filter(pk=1).first()
    existing = system_settings is not None and system_settings.defaults_installed
    values = dict.fromkeys(changes, True)
    if existing and "invoice_service_cases" in changes:
        values["invoice_cases_since"] = timezone.now()
    settings_model.objects.filter(pk=1).update(**values)
    if not existing:
        return  # a fresh database: nothing to report, no old service cases
    apps.get_model("core", "AuditLogEntry").objects.create(
        timestamp=timezone.now(),
        actor_label=ACTOR,
        action="updated",
        content_type=_content_type(apps),
        object_id="1",
        object_repr=REPR,
        changes=changes,
    )


def back_to_092(apps, schema_editor):
    """Going back: off again what this step switched on – and nobody switched off since."""
    entry = (
        apps.get_model("core", "AuditLogEntry")
        .objects.filter(actor_label=ACTOR, content_type=_content_type(apps), object_id="1", action="updated")
        .order_by("-timestamp", "-pk")
        .first()
    )
    if entry is None:
        return
    settings_model = apps.get_model("core", "NotificationSettings")
    before = {
        name: values[0]
        for name, values in (entry.changes or {}).items()
        if name in FIELDS and isinstance(values, list) and len(values) == 2
    }
    for name, value in before.items():
        settings_model.objects.filter(pk=1, **{name: True}).update(**{name: value})


class Migration(migrations.Migration):
    """The new defaults, and the data step for an existing installation."""

    dependencies = [
        ("core", "0023_page_size_092"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationsettings",
            name="invoice_service_cases",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Done service cases with something to charge are reminded of as well – those done since the "
                    "setting was switched on."
                ),
                verbose_name="service cases too",
            ),
        ),
        # The cut-off of the reminders of service cases.
        migrations.AddField(
            model_name="notificationsettings",
            name="invoice_cases_since",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="notificationsettings",
            name="shortage_repeat",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Off: each shortage is reported once – again only if it grows, or if it was resolved and comes "
                    "back. On: every check reminds of all open shortages again – one message per project."
                ),
                verbose_name="report known shortages again at every check",
            ),
        ),
        migrations.RunPython(switch_on, back_to_092),
    ]
