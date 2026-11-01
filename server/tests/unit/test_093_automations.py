# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "automations": the default automations like any other, their buttons in one row (ADM-019; ADM-013).

The requirements: the four default automations can be edited and deleted, not only switched off; and the buttons
"Ausschalten" and "Löschen" of an automation stand at the same height.

* The four rules that come with Rentalars (PRJ-112, MAT-057) are changed, switched and deleted like the company's
  own – in the browser and through the API, with the same rights and checks, audited alike. Each carries a stable
  key; the list marks them "Standard", and "geändert" when one differs from how it came.
* "Standard-Automationen wiederherstellen" (list, API) creates the missing ones by key and leaves every rule that is
  there alone – changed or not.
* No update creates or changes one: the migration only gives the existing ones their key; ``migrate``, the
  start data and the localisation of the start data leave a deleted default deleted and a changed one changed.
* The buttons of a rule stand in one row (``cell-buttons``); the browser test measures them
  (tests/browser/test_093_automations_in_browser.py).
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module
from rentalars.automations import defaults
from rentalars.automations.models import Action, Automation, Trigger
from rentalars.core.defaults import install_defaults
from rentalars.core.models import AuditAction, AuditLogEntry, SystemSettings
from rentalars.core.start_data import localise
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_user
from tests.ui.base import UiTestCase, form_data

AUTOMATIONS = "/administration/automations/"
KEYS = ["case_closing_due", "case_closing_communication", "case_backlog_due", "defect_case"]
UPDATE = importlib.import_module("rentalars.automations.migrations.0004_default_keys_093")


def default(key: str) -> Automation:
    """The default with this key."""
    return Automation.objects.get(default_key=key)


def entries_of(rule: Automation, action: str) -> Any:
    """The change log entries of a rule."""
    return AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(Automation), object_id=str(rule.pk), action=action
    )


def snapshot() -> list[tuple[Any, ...]]:
    """Every rule with everything a user sees of it."""
    return list(
        Automation.objects.order_by("pk").values_list(
            "pk",
            "name",
            "is_active",
            "trigger",
            "status",
            "action",
            "new_case_status",
            "subject",
            "text",
            "default_key",
        )
    )


# --- The defaults and their marks -------------------------------------------------------------------------------


class DefaultsTests(RentalarsTestCase):
    """The four defaults of a new database carry their key; "geändert" tells a changed one from one as it came."""

    def test_a_new_database_has_the_four_with_their_keys(self) -> None:
        rules = Automation.objects.exclude(default_key=None).order_by("pk")
        self.assertEqual(
            [(rule.default_key, rule.name, rule.is_active) for rule in rules],
            [
                ("case_closing_due", "Wartet auf Schließen: zum Termin schließen", True),
                ("case_closing_communication", "Wartet auf Schließen: bei neuer Kommunikation wieder öffnen", True),
                ("case_backlog_due", "Rückstand: zur Wiedervorlage wieder öffnen", True),
                ("defect_case", "Defektmeldung → Servicefall", True),
            ],
        )
        self.assertEqual([item.key for item in defaults.DEFAULTS], KEYS)
        self.assertEqual(defaults.missing(), [])
        for rule in rules:
            self.assertTrue(rule.is_default)
            self.assertFalse(rule.default_changed, rule.name)

    def test_changed_or_not(self) -> None:
        rule = default("case_backlog_due")
        rule.is_active = False  # switched off is no change
        self.assertFalse(rule.default_changed)
        rule.name = "Backlog: open again when the follow-up is due"  # the English name of the start data
        self.assertFalse(rule.default_changed)
        rule.name = "Rückstand: wieder öffnen"
        self.assertTrue(rule.default_changed)
        rule.refresh_from_db()
        rule.new_case_status = "in_progress"
        self.assertTrue(rule.default_changed)
        rule.refresh_from_db()
        rule.text = "x"
        self.assertTrue(rule.default_changed)
        own = Automation(name="Defektmeldung → Servicefall", trigger=Trigger.DEFECT, action=Action.CREATE_CASE)
        self.assertFalse(own.is_default)
        self.assertFalse(own.default_changed)  # an own rule is never "changed" – it did not come with Rentalars


class RestoreTests(RentalarsTestCase):
    """Restoring creates the missing defaults by key and leaves every rule that is there alone."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_user("anna", superuser=True)

    def test_only_what_is_missing(self) -> None:
        default("defect_case").delete()
        default("case_closing_communication").delete()
        changed = default("case_backlog_due")
        changed.name, changed.new_case_status, changed.is_active = "Rückstand anders", "in_progress", False
        changed.save()
        # An own rule with the name of a deleted default is no default: restoring goes by key.
        Automation.objects.create(name="Defektmeldung → Servicefall", trigger=Trigger.DEFECT, action=Action.NOTIFY)
        before = snapshot()
        self.assertEqual([item.key for item in defaults.missing()], ["case_closing_communication", "defect_case"])
        created = defaults.restore(user=self.anna)
        self.assertEqual([rule.default_key for rule in created], ["case_closing_communication", "defect_case"])
        self.assertEqual(snapshot()[: len(before)], before)  # nothing that was there changed
        for rule in created:
            rule.refresh_from_db()
            self.assertTrue(rule.is_active)
            self.assertFalse(rule.default_changed)
            self.assertEqual(rule.created_by, self.anna)
            self.assertTrue(entries_of(rule, AuditAction.CREATED).exists())
        self.assertEqual(default("defect_case").name, "Defektmeldung → Servicefall")
        self.assertEqual(Automation.objects.filter(name="Defektmeldung → Servicefall").count(), 2)
        self.assertEqual(defaults.restore(user=self.anna), [])  # nothing more to do
        self.assertEqual(Automation.objects.exclude(default_key=None).count(), 4)

    def test_a_renamed_default_is_not_made_twice(self) -> None:
        rule = default("defect_case")
        rule.name = "Defekte → Fall"
        rule.save()
        self.assertEqual(defaults.restore(), [])
        self.assertEqual(Automation.objects.filter(trigger=Trigger.DEFECT).count(), 1)

    def test_in_english(self) -> None:
        default("case_closing_due").delete()
        with self.settings(LANGUAGE_CODE="en"):
            (created,) = defaults.restore()
        self.assertEqual(created.name, "Waiting to close: close at the time set")
        self.assertIsNone(created.created_by)

    def test_two_at_the_same_moment(self) -> None:
        """The key is unique: what somebody else restored in the meantime is not made a second time."""
        default("defect_case").delete()
        with mock.patch.object(defaults, "missing", return_value=list(defaults.DEFAULTS)):
            created = defaults.restore()
        self.assertEqual([rule.default_key for rule in created], ["defect_case"])
        self.assertEqual(Automation.objects.exclude(default_key=None).count(), 4)


class UpdateTests(RentalarsTestCase):
    """What an update runs never brings back a deleted default nor changes a changed one."""

    def test_migrate_start_data_and_localisation_leave_them_alone(self) -> None:
        default("defect_case").delete()
        changed = default("case_closing_due")
        changed.new_case_status, changed.text = "open", ""
        changed.name = "Wartet: wieder öffnen"
        changed.save()
        unchanged_name = default("case_backlog_due")  # the name of the start data, the rule changed
        unchanged_name.status = "waiting"
        unchanged_name.save()
        before = snapshot()
        call_command("migrate", verbosity=0)  # nothing to apply; its signals run (core.defaults)
        self.assertEqual(snapshot(), before)
        # The start data, even if it were installed again (the marker of core.defaults reset).
        settings_row = SystemSettings.load()
        settings_row.defaults_installed = False
        settings_row.save()
        self.assertTrue(install_defaults())
        self.assertEqual(snapshot(), before)
        localise("de")
        self.assertEqual(snapshot(), before)
        # The data step of the update again (as a second run of it would): it creates nothing.
        UPDATE.give_keys(django_apps, None)
        self.assertEqual(snapshot(), before)
        self.assertEqual([item.key for item in defaults.missing()], ["defect_case"])
        self.assertTrue(default("case_closing_due").default_changed)
        self.assertTrue(default("case_backlog_due").default_changed)


class UpdateMigrationTests(TransactionTestCase):
    """The update: the defaults that are there get their key – found as the old migration made them."""

    before = [("automations", "0001_squashed_0003_defects_085")]
    after = [("automations", "0004_default_keys_093")]

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate(self, targets: list[tuple[str, str]]) -> Any:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_keys_for_what_is_there_nothing_created_nothing_changed(self) -> None:
        anna = make_user("anna")
        old = self.migrate(self.before)
        rules = old.get_model("automations", "Automation").objects
        rules.all().delete()
        first = importlib.import_module("rentalars.automations.migrations.0001_squashed_0003_defects_085")
        first.add_default_rules(old, None)
        first.add_default_rule(old, None)
        # Before the update: the defect rule deleted, one rule renamed, one changed in its rule but not in its name, an own
        # rule (with a creator) like the deleted default, an own rule without creator that is like none.
        rules.filter(trigger="defect").delete()
        rules.filter(status="backlog").update(name="Rückstand: wieder öffnen")
        rules.filter(trigger="case_follow_up", status="closing").update(new_case_status="open", text="anders")
        own = rules.create(name="Defekt melden", trigger="defect", action="create_case", created_by_id=anna.pk)
        loose = rules.create(name="Alt", trigger="case_communication", status="waiting", action="case_status")
        before = list(rules.order_by("pk").values_list("pk", "name", "status", "new_case_status", "text", "is_active"))
        logged = AuditLogEntry.objects.count()

        new = self.migrate(self.after)
        found = new.get_model("automations", "Automation").objects
        self.assertEqual(
            list(found.order_by("pk").values_list("pk", "name", "status", "new_case_status", "text", "is_active")),
            before,
        )
        self.assertEqual(
            dict(found.exclude(default_key=None).values_list("default_key", "name")),
            {
                "case_closing_due": "Wartet auf Schließen: zum Termin schließen",  # by name, rule changed
                "case_closing_communication": "Wartet auf Schließen: bei neuer Kommunikation wieder öffnen",
                "case_backlog_due": "Rückstand: wieder öffnen",  # renamed: by its rule
            },
        )
        self.assertIsNone(found.get(pk=own.pk).default_key)
        self.assertIsNone(found.get(pk=loose.pk).default_key)
        self.assertEqual(AuditLogEntry.objects.count(), logged)  # the update writes nothing into the change log
        self.assertEqual([item.key for item in defaults.missing()], ["defect_case"])
        self.assertTrue(default("case_closing_due").default_changed)
        self.assertTrue(default("case_backlog_due").default_changed)
        self.assertFalse(default("case_closing_communication").default_changed)
        # Back to the earlier state and forward again: the same keys, still nothing created.
        self.migrate(self.before)
        again = self.migrate(self.after).get_model("automations", "Automation").objects
        self.assertEqual(again.count(), len(before))
        self.assertEqual(set(again.exclude(default_key=None).values_list("default_key", flat=True)), set(KEYS[:3]))


# --- The pages -----------------------------------------------------------------------------------------------------


class PageTests(UiTestCase):
    """Einstellungen → Automationen: the defaults edited, deleted and restored like any rule."""

    def test_the_list_marks_them_and_offers_the_same_buttons(self) -> None:
        text = self.assert_ok(self.client.get(AUTOMATIONS))
        self.assertEqual(text.count('<span class="badge outline">Standard</span>'), 4)
        self.assertNotIn("geändert</span>", text)
        rule = default("defect_case")
        self.assertIn(
            f'<div class="cell-buttons"><a class="btn secondary small" href="{AUTOMATIONS}{rule.pk}/">Bearbeiten</a>'
            f'<button class="btn secondary small" type="submit" form="toggle-{rule.pk}">Ausschalten</button>'
            f'<button class="btn secondary small danger" type="submit" form="delete-{rule.pk}"',
            text,
        )
        self.assertIn("„Standard-Automationen wiederherstellen“ holt sie zurück, wie sie kam.", text)
        self.assertNotIn("restore-defaults", text)  # nothing missing, no button
        # The column "Herkunft", for the CSV as well.
        csv = self.client.get(AUTOMATIONS, {"cols": "name,origin", "format": "csv"}).content.decode("utf-8-sig")
        self.assertIn("Herkunft", csv)
        self.assertIn("Defektmeldung → Servicefall;Standard", csv)

    def test_edit_a_default(self) -> None:
        rule = default("case_backlog_due")
        page = self.client.get(f"{AUTOMATIONS}{rule.pk}/")
        text = self.assert_ok(page)
        self.assertIn("Diese Automation kam mit Rentalars.", text)
        self.assertIn(f'form="delete-{rule.pk}"', text)
        self.assertIn(
            f'<form id="delete-{rule.pk}" method="post" action="{AUTOMATIONS}{rule.pk}/delete/" hidden>', text
        )
        data = form_data(page, "case_status", name="Rückstand: in Arbeit nehmen", new_case_status="in_progress")
        response = self.client.post(f"{AUTOMATIONS}{rule.pk}/", data, follow=True)
        self.assertIn("Die Automation „Rückstand: in Arbeit nehmen“ ist gespeichert.", self.messages_of(response))
        rule.refresh_from_db()
        self.assertEqual((rule.new_case_status, rule.default_key), ("in_progress", "case_backlog_due"))
        self.assertIn('<span class="badge outline">geändert</span>', self.assert_ok(response))
        entry = entries_of(rule, AuditAction.UPDATED).get()  # audited like any change
        self.assertEqual(entry.actor, self.admin_user)
        self.assertEqual(entry.changes["new_case_status"], ["open", "in_progress"])
        self.assertNotIn("default_key", entry.changes)
        text = self.assert_ok(self.client.get(f"{AUTOMATIONS}{rule.pk}/"))
        self.assertIn("Diese Automation kam mit Rentalars und wurde seitdem geändert.", text)

    def test_an_unchanged_save_stays_unchanged(self) -> None:
        for key in KEYS:
            rule = default(key)
            data = form_data(self.client.get(f"{AUTOMATIONS}{rule.pk}/"), "trigger")
            self.assertEqual(self.client.post(f"{AUTOMATIONS}{rule.pk}/", data).status_code, 302)
            self.assertFalse(default(key).default_changed, key)

    def test_delete_and_restore(self) -> None:
        rule = default("defect_case")
        changed = default("case_closing_due")
        changed.name = "Zum Termin schließen"
        changed.save()
        response = self.client.post(reverse("automations:delete", args=[rule.pk]), follow=True)
        self.assertIn(
            "Die Automation „Defektmeldung → Servicefall“ ist gelöscht. Ihre Ausführungen bleiben in der Liste. "
            "„Standard-Automationen wiederherstellen“ holt sie zurück, wie sie kam.",
            self.messages_of(response),
        )
        self.assertTrue(entries_of(rule, AuditAction.DELETED).exists())
        text = self.assert_ok(response)
        self.assertIn('form="restore-defaults"', text)
        self.assertIn(
            'data-confirm="Standard-Automationen wiederherstellen? Rentalars legt an: „Defektmeldung → Servicefall“. '
            'Die vorhandenen Automationen – geändert oder nicht – bleiben, wie sie sind."',
            text,
        )
        before = snapshot()
        response = self.client.post(reverse("automations:restore_defaults"), follow=True)
        self.assertEqual(
            self.messages_of(response),
            [
                "1 Standard-Automation wiederhergestellt: „Defektmeldung → Servicefall“. "
                "Die anderen bleiben, wie sie sind."
            ],
        )
        self.assertEqual(snapshot()[: len(before)], before)
        self.assertEqual(default("defect_case").created_by, self.admin_user)
        self.assertEqual(default("case_closing_due").name, "Zum Termin schließen")
        self.assertNotIn('form="restore-defaults"', self.assert_ok(response))
        response = self.client.post(reverse("automations:restore_defaults"), follow=True)
        self.assertEqual(self.messages_of(response), ["Alle Standard-Automationen sind da; nichts wurde angelegt."])
        # Two at once: the plural.
        default("defect_case").delete()
        default("case_backlog_due").delete()
        response = self.client.post(reverse("automations:restore_defaults"), follow=True)
        self.assertEqual(
            self.messages_of(response),
            [
                "2 Standard-Automationen wiederhergestellt: „Rückstand: zur Wiedervorlage wieder öffnen“, "
                "„Defektmeldung → Servicefall“. Die anderen bleiben, wie sie sind."
            ],
        )

    def test_rights(self) -> None:
        Role.objects.create(name="Einstellungen lesen", module_levels={Module.ADMINISTRATION: int(Level.READ)})
        reader = self.browser_for("lea", "Einstellungen lesen")
        default("defect_case").delete()
        text = self.assert_ok(reader.get(AUTOMATIONS))
        self.assertNotIn("restore-defaults", text)
        self.assertNotIn("Bearbeiten", text)
        self.assertNotIn("cell-buttons", text)
        self.assertIn('<span class="badge outline">Standard</span>', text)  # the mark is for every reader
        rule = default("case_backlog_due")
        self.assertEqual(reader.post(reverse("automations:restore_defaults")).status_code, 403)
        self.assertEqual(reader.post(reverse("automations:delete", args=[rule.pk])).status_code, 403)
        self.assertEqual(reader.get(f"{AUTOMATIONS}{rule.pk}/").status_code, 403)
        self.assertEqual(
            self.browser_for("nur", "Nur-Lesen").post(reverse("automations:restore_defaults")).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("automations:restore_defaults")).status_code, 405)
        self.assertEqual(defaults.missing()[0].key, "defect_case")


# --- The API (API-002, API-014) ------------------------------------------------------------------------------------


class ApiTests(ApiTestCase):
    """``/automations``: the defaults changed and deleted like any rule; ``/automations/restore-defaults``."""

    def test_change_and_delete_a_default(self) -> None:
        listed = {rule["default_key"]: rule for rule in self.admin.get(f"{API}/automations").json()}
        self.assertEqual(set(listed), {*KEYS})
        self.assertFalse(any(rule["default_changed"] for rule in listed.values()))
        own = self.admin.post(
            f"{API}/automations",
            {"name": "Eigene", "trigger": "defect", "action": "create_inquiry", "default_key": "defect_case"},
            format="json",
        )
        self.assertEqual(own.status_code, 201, own.content)
        self.assertEqual((own.json()["default_key"], own.json()["default_changed"]), (None, False))
        rule = listed["case_closing_communication"]
        detail = f"{API}/automations/{rule['id']}"
        response = self.admin.patch(detail, {"communication": "mail_in", "default_key": "x"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["communication"], "mail_in")
        self.assertEqual(response.json()["default_key"], "case_closing_communication")  # read-only
        self.assertTrue(response.json()["default_changed"])
        entry = entries_of(Automation(pk=rule["id"]), AuditAction.UPDATED).get()
        self.assertEqual((entry.actor, entry.changes["communication"]), (self.admin_user, ["", "mail_in"]))
        # The same checks as for any rule.
        self.assert_error(
            self.admin.patch(detail, {"action": "reply"}, format="json"), 400, "validation_error", "action"
        )
        response = self.admin.put(
            detail,
            {
                "name": "Neu",
                "trigger": "case_communication",
                "status": "",
                "action": "case_status",
                "new_case_status": "open",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["name"], response.json()["status"]), ("Neu", ""))
        self.assertEqual(self.admin.delete(detail).status_code, 204)
        self.assertFalse(Automation.objects.filter(default_key="case_closing_communication").exists())

    def test_restore_defaults(self) -> None:
        url = f"{API}/automations/restore-defaults"
        default("defect_case").delete()
        changed = default("case_backlog_due")
        changed.is_active = False
        changed.text = ""
        changed.status = "waiting"
        changed.save()
        response = self.admin.post(url, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        (created,) = response.json()
        self.assertEqual(
            (created["default_key"], created["name"], created["is_active"], created["default_changed"]),
            ("defect_case", "Defektmeldung → Servicefall", True, False),
        )
        self.assertEqual(Automation.objects.get(pk=created["id"]).created_by, self.admin_user)
        changed.refresh_from_db()
        self.assertEqual((changed.is_active, changed.status), (False, "waiting"))  # left alone
        again = self.admin.post(url, format="json")
        self.assertEqual((again.status_code, again.json()), (200, []))
        self.assert_error(self.client_for("lena", "Projektleitung").post(url, format="json"), 403, "permission_denied")
        Role.objects.create(name="Einstellungen lesen", module_levels={Module.ADMINISTRATION: int(Level.READ)})
        reader = self.client_for("lea", "Einstellungen lesen")
        self.assertEqual(reader.get(f"{API}/automations").status_code, 200)
        self.assert_error(reader.post(url, format="json"), 403, "permission_denied")
        self.assert_error(reader.delete(f"{API}/automations/{created['id']}"), 403, "permission_denied")
