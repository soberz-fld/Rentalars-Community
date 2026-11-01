# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "notifications": the tasks of the AI in the settings, every kind switchable (UIX-052), two company
defaults (VFG-036, DOK-015).

1. The requirement: the notification settings offer the choice whether to be notified when the AI has finished a
   task; the notification arrives, but could not be switched in the settings.

   The AI sends ``job_finished`` – like every task in the background. It was in the settings, last of all under
   "System" as the entry for a finished background task, where nobody looks for the AI. Now it comes first in
   "System" and names the tasks of the AI; switched off, nothing arrives on any channel. Every kind that can be
   sent is in the settings (page and API) – or deliberately always sent, with a reason (none so far).
2. The requirement: in "Benachrichtigungen der Firma" the options "Bekannte Fehlbestände bei jeder Prüfung erneut
   melden" and "Auch Servicefälle" are on by default – for existing installations they are switched on by the update
   (decided). Known shortages come as one reminder per project, so that the default does not flood.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import mail as django_mail
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase
from django.urls import reverse

from rentalars.ai import summary
from rentalars.ai.models import Source
from rentalars.core.models import AuditLogEntry, NotificationSettings, SystemSettings
from rentalars.documents import invoice_reminders
from rentalars.notifications import services
from rentalars.notifications.categories import Category, category_of
from rentalars.notifications.models import ALWAYS_SENT, Kind, Notification, Preference
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    RentalarsTestCase,
    add_line,
    at,
    make_customer,
    make_person,
    make_project,
    make_stock,
    make_user,
    record_time,
)
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_083_ai import AITestCase

PREFERENCES = "/account/notifications/"
API_PREFERENCES = f"{API}/notifications/preferences"
API_SETTINGS = f"{API}/settings/notifications"
#: The name of ``job_finished`` in the settings, as the user reads it.
AI_LABEL = "Eine Aufgabe im Hintergrund ist fertig (z. B. KI-Zusammenfassung, Antwortentwurf, Rechnung lesen, Export)"
MIGRATION = importlib.import_module("rentalars.core.migrations.0024_notification_defaults_093")
ROOT = Path(settings.BASE_DIR) / "rentalars"


def switch(user: Any, kind: str, *, app: bool = False, email: bool = False, companion: bool = False) -> None:
    """Set the three channels of one kind for a user."""
    services.set_preference(user, kind, in_app=app, by_email=email, companion=companion)


# --- 1. The tasks of the AI in the settings ------------------------------------------------------------------


class AITaskSettingPageTests(UiTestCase):
    """UIX-052: Mein Konto → Benachrichtigungen – the finished task names the AI, first under "System", and is switched."""

    def test_named_and_first_under_system(self) -> None:
        text = self.assert_ok(self.browser_for("paula", "Projektleitung").get(PREFERENCES))
        self.assertIn(f"<td>{AI_LABEL}</td>", text)
        system = text.index('id="category-system"')
        self.assertLess(system, text.index('name="job_finished-app"'))
        self.assertLess(text.index('name="job_finished-app"'), text.index('name="mail_problem-app"'))
        # The defaults: in Rentalars, neither by e-mail nor in the app.
        self.assertIn('name="job_finished-app" value="1" checked', text)
        self.assertNotIn('name="job_finished-email" value="1" checked', text)
        self.assertNotIn('name="job_finished-companion" value="1" checked', text)
        self.assertIn(f'aria-label="{AI_LABEL}: In der App"', text)

    def test_switched_on_and_off(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        browser = self.browser_of(paula)
        data = form_data(browser.get(PREFERENCES), "deployment_request-app")
        data.pop("job_finished-app")
        data.update({"job_finished-email": "1", "job_finished-companion": "1"})
        response = browser.post(PREFERENCES, data, follow=True)
        self.assertIn("Benachrichtigungseinstellungen gespeichert.", self.messages_of(response))
        stored = Preference.objects.get(user=paula, kind=Kind.JOB_FINISHED)
        self.assertEqual((stored.in_app, stored.by_email, stored.companion), (False, True, True))
        data = form_data(browser.get(PREFERENCES), "deployment_request-app")
        for channel in ("app", "email", "companion"):
            data.pop(f"job_finished-{channel}", None)
        browser.post(PREFERENCES, data)
        stored.refresh_from_db()
        self.assertEqual((stored.in_app, stored.by_email, stored.companion), (False, False, False))
        # The other kinds kept what they had.
        self.assertTrue(Preference.objects.get(user=paula, kind=Kind.DEPLOYMENT_REQUEST).companion)


class AITaskNotificationTests(AITestCase, ApiTestCase):
    """UIX-052: when a summary of the AI is finished, the notification follows the user's choice – on every channel."""

    def setUp(self) -> None:
        super().setUp()
        self.install_local()
        self.use("summary", Source.LOCAL)

    def summarise(self) -> None:
        """Start a summary of Paula's project; the task runs at once in the tests, mails go after the commit."""
        from rentalars.accounts.rights import rights_of

        with self.captureOnCommitCallbacks(execute=True):
            job = summary.start(self.project, user=self.user, rights=rights_of(self.user))
        job.refresh_from_db()
        self.assertEqual(job.status, "done", job.message)

    def test_by_default_in_rentalars(self) -> None:
        self.summarise()
        notice = Notification.objects.get(user=self.user)
        self.assertEqual(notice.kind, Kind.JOB_FINISHED)
        self.assertEqual(notice.title, f"Fertig: Zusammenfassung der Korrespondenz von {self.project.number}")
        self.assertEqual((notice.read_at, notice.companion), (None, False))
        self.assertEqual(django_mail.outbox, [])

    def test_switched_off_nothing_arrives(self) -> None:
        response = self.client_of(self.user).put(
            API_PREFERENCES,
            [{"kind": "job_finished", "in_app": False, "by_email": False, "companion": False}],
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.summarise()
        self.assertFalse(Notification.objects.filter(user=self.user).exists())
        self.assertEqual(django_mail.outbox, [])
        found = self.client_of(self.user).get(f"{API}/notifications?companion=1").json()
        self.assertEqual((found["count"], found["unread_total"]), (0, 0))

    def test_each_channel_on_its_own(self) -> None:
        switch(self.user, Kind.JOB_FINISHED, email=True)
        self.summarise()
        notice = Notification.objects.get(user=self.user)
        self.assertIsNotNone(notice.read_at)  # not at the bell
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertIn("Zusammenfassung der Korrespondenz", django_mail.outbox[0].subject)
        notice.delete()
        switch(self.user, Kind.JOB_FINISHED, companion=True)
        self.summarise()
        notice = Notification.objects.get(user=self.user)
        self.assertTrue(notice.companion)
        self.assertIsNotNone(notice.read_at)
        self.assertEqual(len(django_mail.outbox), 1)  # no second mail


# --- 1. Every kind switchable --------------------------------------------------------------------------------


def kinds_sent_in_the_code() -> dict[str, list[str]]:
    """Every ``notify(…, Kind.X, …)`` of the application: the name of ``X`` → where."""
    found: dict[str, list[str]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name != "notify":
                continue
            kind = (
                node.args[1]
                if len(node.args) > 1
                else next((keyword.value for keyword in node.keywords if keyword.arg == "kind"), None)
            )
            where = f"{path.relative_to(ROOT.parent)}:{node.lineno}"
            label = kind.attr if isinstance(kind, ast.Attribute) and isinstance(kind.value, ast.Name) else "?"
            found.setdefault(label, []).append(where)
    return found


class EveryKindSwitchableTests(ApiTestCase):
    """UIX-052: every kind a user can be sent is in the settings – page and API – or deliberately always sent."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))

    def test_every_kind_in_the_settings_or_always_sent_with_a_reason(self) -> None:
        listed = [item["kind"] for item in services.preferences_of(self.paula)]
        api = [row["kind"] for row in self.client_of(self.paula).get(API_PREFERENCES).json()]
        self.assertEqual(api, listed)
        browser = Client()
        browser.force_login(self.paula)
        page = browser.get(PREFERENCES).content.decode()
        for kind in Kind.values:
            with self.subTest(kind=kind):
                if kind in ALWAYS_SENT:
                    self.assertTrue(str(ALWAYS_SENT[kind]).strip(), "an exception needs its reason")
                    self.assertNotIn(kind, listed)
                    self.assertNotIn(f'name="{kind}-app"', page)
                    continue
                self.assertIn(kind, listed, "neither in the settings nor in ALWAYS_SENT")
                for channel in ("app", "email", "companion"):
                    self.assertIn(f'name="{kind}-{channel}"', page)
        self.assertEqual(sorted(listed), sorted(set(Kind.values) - set(ALWAYS_SENT)))
        self.assertFalse(set(ALWAYS_SENT) - set(Kind.values), "an exception that is no kind")

    def test_every_kind_sent_in_the_code_is_a_kind(self) -> None:
        """``notify`` refuses an unknown kind; here every call of the application names one of ``Kind``."""
        found = kinds_sent_in_the_code()
        self.assertNotIn("?", found, f"notify() without Kind.X: {found.get('?')}")
        self.assertTrue(set(found) <= set(Kind.names), set(found) - set(Kind.names))
        self.assertIn("JOB_FINISHED", found)
        with self.assertRaises(ValueError):
            services.notify([self.paula], "weather", "Regen")

    def test_switched_off_no_kind_arrives_on_any_channel(self) -> None:
        for kind in services.switchable_kinds():
            with self.subTest(kind=kind), self.captureOnCommitCallbacks(execute=True):
                switch(self.paula, kind)
                self.assertEqual(services.notify([self.paula], kind, "Etwas"), [])
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(django_mail.outbox, [])

    def test_each_channel_of_every_kind(self) -> None:
        expected = {"app": (True, False, False), "email": (False, True, False), "companion": (False, False, True)}
        for channel, (in_app, by_email, companion) in expected.items():
            for kind in services.switchable_kinds():
                with self.subTest(kind=kind, channel=channel):
                    switch(self.paula, kind, **{channel: True})
                    django_mail.outbox.clear()
                    with self.captureOnCommitCallbacks(execute=True):
                        services.notify([self.paula], kind, "Etwas")
                    notice = Notification.objects.get(user=self.paula, kind=kind)
                    self.assertEqual(notice.read_at is None, in_app)
                    self.assertEqual(notice.companion, companion)
                    self.assertEqual(len(django_mail.outbox), int(by_email))
                    notice.delete()

    def test_a_kind_always_sent(self) -> None:
        """The exception, should one ever be needed: not listed, not stored, the defaults whatever was stored."""
        Preference.objects.create(user=self.paula, kind=Kind.SYSTEM_ERROR, in_app=False, by_email=False)
        with mock.patch.dict(ALWAYS_SENT, {Kind.SYSTEM_ERROR: "Die Betreiber müssen es erfahren."}):
            self.assertNotIn(Kind.SYSTEM_ERROR, [item["kind"] for item in services.preferences_of(self.paula)])
            self.assertEqual(services.choice(self.paula, Kind.SYSTEM_ERROR), (True, True, False))
            with self.assertRaises(ValueError):
                switch(self.paula, Kind.SYSTEM_ERROR)
            response = self.client_of(self.paula).put(
                API_PREFERENCES, [{"kind": "system_error", "in_app": False, "by_email": False}], format="json"
            )
            self.assert_error(response, 400, "validation_error")
            self.assertIn("lässt sich nicht abschalten", response.content.decode())


class PreferencesApiTests(ApiTestCase):
    """UIX-052, API-002: ``/notifications/preferences`` names the tasks of the AI as the page does, and switches them."""

    def test_read_and_switch(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        client = self.client_of(paula)
        rows = client.get(API_PREFERENCES).json()
        system = [row for row in rows if row["category"] == "system"]
        self.assertEqual(system[0]["kind"], "job_finished")
        self.assertEqual(
            system[0],
            {
                "kind": "job_finished",
                "label": AI_LABEL,
                "category": "system",
                "category_label": "System",
                "in_app": True,
                "by_email": False,
                "companion": False,
            },
        )
        response = client.put(
            API_PREFERENCES,
            [{"kind": "job_finished", "in_app": False, "by_email": True, "companion": True}],
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = next(row for row in response.json() if row["kind"] == "job_finished")
        self.assertEqual((row["in_app"], row["by_email"], row["companion"]), (False, True, True))
        self.assertEqual(services.choice(paula, Kind.JOB_FINISHED), (False, True, True))
        self.assertEqual(category_of(Kind.JOB_FINISHED), Category.SYSTEM)


# --- 2. The defaults of the company --------------------------------------------------------------------------


class CompanyDefaultsTests(UiTestCase):
    """VFG-036, DOK-015: both settings on – for a new installation and, by the update, in this one."""

    def test_on_by_default(self) -> None:
        self.assertTrue(NotificationSettings().shortage_repeat)
        self.assertTrue(NotificationSettings().invoice_service_cases)
        stored = NotificationSettings.load()  # the row the migrations made, switched on by the update
        self.assertEqual((stored.shortage_repeat, stored.invoice_service_cases), (True, True))
        NotificationSettings.objects.all().delete()  # a queryset delete: created anew on first use
        stored = NotificationSettings.load()
        self.assertEqual((stored.shortage_repeat, stored.invoice_service_cases), (True, True))

    def test_the_page(self) -> None:
        text = self.assert_ok(self.client.get(reverse("notifications:company_settings")))
        for name in ("shortage_repeat", "invoice_service_cases"):
            self.assertRegex(text, rf'<input type="checkbox" name="{name}"[^>]* checked')
        self.assertIn("ekannte Fehlbestände bei jeder Prüfung erneut melden", text)
        self.assertIn("uch Servicefälle", text)
        self.assertIn("An: Jede Prüfung erinnert an alle offenen Fehlbestände – eine Nachricht je Projekt.", text)
        data = form_data(self.client.get(reverse("notifications:company_settings")), "shortage_interval")
        data.pop("shortage_repeat")
        data.pop("invoice_service_cases")
        self.client.post(reverse("notifications:company_settings"), data)
        stored = NotificationSettings.objects.get(pk=1)
        self.assertEqual((stored.shortage_repeat, stored.invoice_service_cases), (False, False))

    def test_a_done_service_case_with_work_is_reminded_of_by_default(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        NotificationSettings.objects.filter(pk=1).update(invoice_reminders_since=at(1, 0, month=2))
        case = service_cases.create_case(name="Spot repariert", customer=make_customer("Kino"), manager=paula)
        record_time(make_person("Tom"), case, "Techniker", at(1, 9), at(1, 11))
        service_cases.set_case_status(case, CaseStatus.DONE, by=paula)
        self.assertIn(case, invoice_reminders.due_projects(at(5, 9, 1)))
        self.assertEqual(invoice_reminders.state_of(case), invoice_reminders.InvoiceState.OPEN)


class CompanyDefaultsApiTests(ApiTestCase):
    """VFG-036, DOK-015, API-002: ``/settings/notifications`` delivers both on and switches them."""

    def test_read_and_switch_off(self) -> None:
        found = self.admin.get(API_SETTINGS).json()
        self.assertEqual((found["shortage_repeat"], found["invoice_service_cases"]), (True, True))
        changed = self.admin.patch(
            API_SETTINGS, {"shortage_repeat": False, "invoice_service_cases": False}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["shortage_repeat"], changed.json()["invoice_service_cases"]), (False, False))
        stored = NotificationSettings.objects.get(pk=1)
        self.assertEqual((stored.shortage_repeat, stored.invoice_service_cases), (False, False))


class KnownShortagesTests(RentalarsTestCase):
    """VFG-036: reported again at every check – the known ones of a project in one reminder, so that it does not flood."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project(manager=self.paula)
        add_line(self.project, make_stock("L-001", 2, "Topteil"), 5)
        add_line(self.project, make_stock("L-002", 1, "Traverse"), 3)
        NotificationSettings.objects.filter(pk=1).update(shortage_last_run=at(1, 4, 15))

    def reported(self) -> list[str]:
        return list(
            Notification.objects.filter(user=self.paula, kind=Kind.SHORTAGE)
            .order_by("pk")
            .values_list("title", flat=True)
        )

    def test_one_reminder_per_project_and_check(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.run_due_shortage_check(at(2, 4, 15)), 2)
        self.assertEqual(len(django_mail.outbox), 2)  # new: one by one
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.run_due_shortage_check(at(3, 4, 15)), 2)
        self.assertEqual(len(django_mail.outbox), 3)  # known: one mail for both
        # Review (changed on purpose): several known shortages get a short title with their number and the
        # list in the text – in the title a long list was cut after 250 characters (test_093_review_feeds).
        self.assertEqual(
            self.reported(),
            [
                f"Fehlbestand in {self.project}: 3 × Topteil fehlen",
                f"Fehlbestand in {self.project}: 2 × Traverse fehlen",
                f"Weiterhin Fehlbestände in {self.project}: 2 Produkte",
            ],
        )
        notice = Notification.objects.filter(user=self.paula).latest("pk")
        self.assertEqual(
            notice.body, "3 × Topteil fehlen\n2 × Traverse fehlen\nAb 10.03.2027 00:00. Liste: Planung → Fehlbestände."
        )
        self.assertEqual(NotificationSettings.objects.get(pk=1).shortage_reported, 2)

    def test_a_new_shortage_next_to_known_ones(self) -> None:
        services.run_due_shortage_check(at(2, 4, 15))
        add_line(self.project, make_stock("L-003", 1, "Kabel"), 5)
        self.assertEqual(services.run_due_shortage_check(at(3, 4, 15)), 3)
        # Review (changed on purpose): the known ones by their number in the title, listed in the text.
        self.assertEqual(
            self.reported()[2:],
            [
                f"Fehlbestand in {self.project}: 4 × Kabel fehlen",
                f"Weiterhin Fehlbestände in {self.project}: 2 Produkte",
            ],
        )
        notice = Notification.objects.filter(user=self.paula).latest("pk")
        self.assertTrue(notice.body.startswith("3 × Topteil fehlen\n2 × Traverse fehlen\n"))
        self.assertNotIn("Kabel", notice.body)

    def test_switched_off_each_shortage_once(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_repeat=False)
        self.assertEqual(services.run_due_shortage_check(at(2, 4, 15)), 2)
        self.assertEqual(services.run_due_shortage_check(at(3, 4, 15)), 0)
        self.assertEqual(len(self.reported()), 2)


# --- 2. The update -------------------------------------------------------------------------------------------


def update_entries() -> Any:
    """The entries of the update in the change log of the settings."""
    return AuditLogEntry.objects.filter(
        actor_label="Aktualisierung 0.9.3", content_type=ContentType.objects.get_for_model(NotificationSettings)
    )


class DataStepTests(RentalarsTestCase):
    """VFG-036, DOK-015: ``core/0024_notification_defaults_093``, the data step on its own: what it switches,
    notes and gives back."""

    def setUp(self) -> None:
        super().setUp()
        SystemSettings.objects.filter(pk=1).update(defaults_installed=True)

    def values(self) -> tuple[bool, bool]:
        stored = NotificationSettings.objects.get(pk=1)
        return stored.shortage_repeat, stored.invoice_service_cases

    def test_only_what_was_off_and_back(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_repeat=True, invoice_service_cases=False)
        MIGRATION.switch_on(apps, None)
        self.assertEqual(self.values(), (True, True))
        entry = update_entries().get()
        self.assertEqual(entry.changes, {"invoice_service_cases": [False, True]})
        self.assertEqual(
            (entry.object_id, entry.object_repr, entry.action), ("1", "Benachrichtigungen der Firma", "updated")
        )
        MIGRATION.switch_on(apps, None)  # again: nothing to do
        self.assertEqual(update_entries().count(), 1)
        MIGRATION.back_to_092(apps, None)
        self.assertEqual(self.values(), (True, False))

    def test_switched_off_since_stays_off(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_repeat=False, invoice_service_cases=False)
        MIGRATION.switch_on(apps, None)
        NotificationSettings.objects.filter(pk=1).update(shortage_repeat=False)
        MIGRATION.back_to_092(apps, None)
        self.assertEqual(self.values(), (False, False))

    def test_a_fresh_database_without_entry(self) -> None:
        SystemSettings.objects.filter(pk=1).update(defaults_installed=False)
        NotificationSettings.objects.filter(pk=1).update(shortage_repeat=False, invoice_service_cases=False)
        MIGRATION.switch_on(apps, None)
        self.assertEqual(self.values(), (True, True))
        self.assertFalse(update_entries().exists())
        MIGRATION.back_to_092(apps, None)  # nothing noted, nothing given back: the earlier state accepts both on
        self.assertEqual(self.values(), (True, True))


class MigrationTests(TransactionTestCase):
    """VFG-036, DOK-015: the update and back, with the migrations themselves."""

    before = [("core", "0023_page_size_092")]
    after = [("core", "0024_notification_defaults_093")]

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

    def test_switched_on_noted_and_given_back(self) -> None:
        old = self.migrate(self.before)
        old.get_model("core", "SystemSettings").objects.update_or_create(pk=1, defaults={"defaults_installed": True})
        old.get_model("core", "NotificationSettings").objects.update_or_create(
            pk=1, defaults={"shortage_repeat": False, "invoice_service_cases": False}
        )
        new = self.migrate(self.after)
        stored = new.get_model("core", "NotificationSettings").objects.get(pk=1)
        self.assertEqual((stored.shortage_repeat, stored.invoice_service_cases), (True, True))
        entry = new.get_model("core", "AuditLogEntry").objects.get(actor_label="Aktualisierung 0.9.3")
        self.assertEqual(entry.changes, {"shortage_repeat": [False, True], "invoice_service_cases": [False, True]})
        # Review: service cases only once done after the update (test_093_review_feeds).
        self.assertIsNotNone(stored.invoice_cases_since)
        old = self.migrate(self.before)
        stored = old.get_model("core", "NotificationSettings").objects.get(pk=1)
        self.assertEqual((stored.shortage_repeat, stored.invoice_service_cases), (False, False))
