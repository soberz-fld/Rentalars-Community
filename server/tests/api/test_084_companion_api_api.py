# SPDX-License-Identifier: GPL-3.0-or-later
"""Through the API, area "companion-api": what the companion app needs (API-015, API-016).

Every new or changed operation is called here with success and with its refusals (API-014), always with the
token of the companion app – limited to ``packing``, ``projects``, ``time_tracking`` and ``email`` – by a person
without any right on the personnel module:

* API-015: ``GET``/``PATCH /people/me/profile`` (the younger change wins), ``GET``/``POST /people/me/absences``
  (``Idempotency-Key``), ``DELETE /people/me/absences/{id}``, ``GET /people/me/deployments`` (``ETag``, 304);
* API-016: ``server_version`` in ``GET /me``; ``unread`` of ``GET /notifications?companion=1`` and paging to older
  unread ones; ``pay_kind`` and ``in_day_rate`` on time entries.
"""

from __future__ import annotations

import datetime
from decimal import Decimal as D  # noqa: N817
from typing import Any

from django.core import mail
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

import rentalars
from rentalars.accounts.rights import Module
from rentalars.core.models import SystemSettings
from rentalars.customers.models import Venue
from rentalars.notifications import services as notifications
from rentalars.notifications.models import Kind, Notification
from rentalars.personnel.models import Absence, AbsenceKind, Person, Qualification, QualificationType
from rentalars.projects.models import CrewBilling, PhaseKind, ProjectPhase, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import LATER, at, job_function, make_person, make_project, make_user, plan, record_time, set_clock

PROFILE = f"{API}/people/me/profile"
ABSENCES = f"{API}/people/me/absences"
DEPLOYMENTS = f"{API}/people/me/deployments"

#: The token of the companion app (APP-001): these four modules, nothing else.
APP_MODULES = [Module.PACKING, Module.PROJECTS, Module.TIME_TRACKING, Module.EMAIL]


def moment(value: str | None) -> datetime.datetime | None:
    return parse_datetime(value) if value else None


class CrewCase(ApiTestCase):
    """Bob: role "Crew", no right on personnel; the app's token."""

    def setUp(self) -> None:
        super().setUp()
        self.bob_user = make_user("bob", roles=("Crew",))
        self.bob = make_person("Bob Baumann", user=self.bob_user, phone="0170 1", email="bob@example.org")
        self.app = self.client_of(self.bob_user, allowed_modules=APP_MODULES)

    def reload(self) -> Person:
        return Person.objects.get(pk=self.bob.pk)


class ProfileApiTests(CrewCase):
    """API-015: the own personnel data, as the tab "Personnel data" shows them."""

    def test_read_without_personnel_rights(self) -> None:
        """API-015, API-014: contact data with their moments, functions, qualifications – with the app's token."""
        self.assertEqual(self.client_of(self.bob_user).get(f"{API}/people/{self.bob.pk}").status_code, 403)
        sound = job_function("Tontechnik")
        from rentalars.personnel import services

        services.set_rate(self.bob, sound, D("35.00"), None, daily_rate=D("280.00"))
        kind = QualificationType.objects.create(name="Ersthelfer", validity_months=24)
        Qualification.objects.create(
            person=self.bob, qualification_type=kind, acquired_on=datetime.date(2025, 4, 1), valid_until=at(15).date()
        )
        response = self.app.get(PROFILE)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(
            (data["id"], data["name"], data["phone"], data["email"], data["share_phone"], data["share_email"]),
            (self.bob.pk, "Bob Baumann", "0170 1", "bob@example.org", False, False),
        )
        self.assertEqual(set(data["updated_at"]), {"phone", "email", "share_phone", "share_email"})
        self.assertTrue(all(moment(value) is not None for value in data["updated_at"].values()))
        self.assertTrue(data["rates_visible"])
        self.assertEqual(
            data["job_functions"],
            [{"job_function": sound.pk, "name": "Tontechnik", "hourly_rate": "35.00", "daily_rate": "280.00"}],
        )
        qualification = data["qualifications"][0]
        self.assertEqual(
            (qualification["name"], qualification["valid_until"], qualification["state"]),
            ("Ersthelfer", "2027-03-15", "soon"),
        )
        self.assertIn("ETag", response)

    def test_rates_only_if_the_person_may_see_them(self) -> None:
        """PER-010, PER-029: as in the browser – without the setting, the functions without rates."""
        from rentalars.personnel import services

        services.set_rate(self.bob, job_function("Tontechnik"), D("35.00"), None)
        settings = SystemSettings.load()
        settings.people_see_own_rates = False
        settings.save()
        data = self.app.get(PROFILE).json()
        self.assertFalse(data["rates_visible"])
        self.assertEqual(set(data["job_functions"][0]), {"job_function", "name"})

    def test_change_without_moment_as_in_the_browser(self) -> None:
        """API-015: without ``changed_at`` every field sent is taken, noted with now."""
        set_clock(at(1, 9))
        response = self.app.patch(PROFILE, {"phone": "0170 2", "share_phone": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(
            (data["phone"], data["share_phone"], data["applied"]), ("0170 2", True, ["phone", "share_phone"])
        )
        self.assertEqual(moment(data["updated_at"]["phone"]), at(1, 9))
        self.assertEqual(moment(data["updated_at"]["email"]), at(1, 8))  # not sent: its moment stays

    def test_the_younger_change_wins(self) -> None:
        """API-015: older and equal moments lose, a later one wins and is stored; per field; the future counts as now."""
        set_clock(at(1, 9))
        older = self.app.patch(PROFILE, {"phone": "0170 7", "changed_at": at(1, 7).isoformat()}, format="json")
        self.assertEqual(older.status_code, 200, older.content)
        self.assertEqual((older.json()["phone"], older.json()["applied"]), ("0170 1", []))
        equal = self.app.patch(PROFILE, {"phone": "0170 8", "changed_at": at(1, 8).isoformat()}, format="json")
        self.assertEqual((equal.json()["phone"], equal.json()["applied"]), ("0170 1", []))  # the server wins
        later = self.app.patch(PROFILE, {"phone": "0170 9", "changed_at": at(1, 8, 30).isoformat()}, format="json")
        self.assertEqual((later.json()["phone"], later.json()["applied"]), ("0170 9", ["phone"]))
        self.assertEqual(moment(later.json()["updated_at"]["phone"]), at(1, 8, 30))
        # Taken with the same value: the moment moves on all the same – a later change counts from it.
        same = self.app.patch(PROFILE, {"phone": "0170 9", "changed_at": at(1, 8, 40).isoformat()}, format="json")
        self.assertEqual(same.json()["applied"], ["phone"])
        self.assertEqual(moment(same.json()["updated_at"]["phone"]), at(1, 8, 40))
        # One moment per field; a field without one is taken as before.
        mixed = self.app.patch(
            PROFILE,
            {"phone": "0170 5", "share_email": True, "changed_at": {"phone": at(1, 8, 20).isoformat()}},
            format="json",
        ).json()
        self.assertEqual((mixed["phone"], mixed["share_email"], mixed["applied"]), ("0170 9", True, ["share_email"]))
        self.assertEqual(moment(mixed["updated_at"]["share_email"]), at(1, 9))
        # A phone whose clock runs ahead: the moment counts as now.
        ahead = self.app.patch(
            PROFILE, {"email": "bob.b@example.org", "changed_at": at(2, 8).isoformat()}, format="json"
        ).json()
        self.assertEqual((ahead["email"], ahead["applied"]), ("bob.b@example.org", ["email"]))
        self.assertEqual(moment(ahead["updated_at"]["email"]), at(1, 9))
        self.assertEqual(self.reload().email, "bob.b@example.org")
        self.bob_user.refresh_from_db()
        self.assertEqual(self.bob_user.email, "bob.b@example.org")  # the account follows (AUT-026)

    def test_a_change_in_the_browser_counts_against_the_app(self) -> None:
        """API-015: the browser notes its change; an older offline change of the app does not override it."""
        set_clock(at(1, 10))
        self.client.force_login(self.bob_user)
        response = self.client.post(
            reverse("personnel:own_profile"), {"phone": "0170 3", "email": "bob@example.org", "share_phone": "on"}
        )
        self.assertEqual(response.status_code, 302, response.content)
        data = self.app.get(PROFILE).json()
        self.assertEqual(moment(data["updated_at"]["phone"]), at(1, 10))
        self.assertEqual(moment(data["updated_at"]["share_phone"]), at(1, 10))
        self.assertEqual(moment(data["updated_at"]["email"]), at(1, 8))
        stale = self.app.patch(
            PROFILE, {"phone": "0170 4", "share_phone": False, "changed_at": at(1, 9).isoformat()}, format="json"
        ).json()
        self.assertEqual((stale["phone"], stale["share_phone"], stale["applied"]), ("0170 3", True, []))

    def test_refusals(self) -> None:
        """API-015, API-008: unknown fields, a moment without zone, an address in use, a read-only token."""
        self.assert_error(self.app.patch(PROFILE, {"name": "Robert"}, format="json"), 400, "validation_error", "name")
        self.assert_error(
            self.app.patch(PROFILE, {"phone": "1", "changed_at": "2027-03-01T09:00"}, format="json"),
            400,
            "validation_error",
            "changed_at",
        )
        self.assert_error(
            self.app.patch(PROFILE, {"phone": "1", "changed_at": {"name": at(1, 9).isoformat()}}, format="json"),
            400,
            "validation_error",
            "changed_at.name",
        )
        self.assert_error(self.app.patch(PROFILE, {"share_phone": "maybe"}, format="json"), 400, "validation_error")
        make_user("carla")
        Person.objects.filter(user__username="carla").update(email="carla@example.org")
        from rentalars.accounts.models import User

        User.objects.filter(username="carla").update(email="carla@example.org")
        self.assert_error(
            self.app.patch(PROFILE, {"email": "Carla@example.org"}, format="json"), 400, "validation_error", "email"
        )
        reader = self.client_of(self.bob_user, allowed_modules=APP_MODULES, read_only=True)
        self.assertEqual(reader.get(PROFILE).status_code, 200)
        self.assert_error(reader.patch(PROFILE, {"phone": "1"}, format="json"), 403, "permission_denied")
        self.assertEqual(self.reload().phone, "0170 1")

    def test_the_login_address_only_with_the_module_email(self) -> None:
        """Review: a token limited to time tracking cannot change the login address – nor take the account."""
        timer = self.client_of(self.bob_user, allowed_modules=[Module.TIME_TRACKING])
        self.assertEqual(timer.get(f"{API}/projects").status_code, 403)
        self.assertFalse(timer.get(PROFILE).json()["email_editable"])
        mail.outbox.clear()
        error = self.assert_error(
            timer.patch(PROFILE, {"email": "evil@example.org", "phone": "0170 6"}, format="json"),
            403,
            "token_scope",
            "email",
        )
        self.assertIn("E-Mail-Adresse", error["message"])
        self.assertEqual((self.reload().email, self.reload().phone), ("bob@example.org", "0170 1"))  # nothing
        self.bob_user.refresh_from_db()
        self.assertEqual(self.bob_user.email, "bob@example.org")
        APIClient().post(f"{API}/auth/password-reset", {"email": "evil@example.org"}, format="json")
        self.assertEqual(mail.outbox, [])
        # Phone and releases with any token that may write; the address sent back unchanged is no change.
        same = timer.patch(PROFILE, {"email": "Bob@example.org", "phone": "0170 6", "share_phone": True}, format="json")
        self.assertEqual(same.status_code, 200, same.content)
        self.assertEqual((same.json()["phone"], same.json()["applied"]), ("0170 6", ["phone", "email", "share_phone"]))

    def test_the_login_address_with_the_app_token_or_without_limits(self) -> None:
        """Review: the companion app's token (with "email") and an unlimited token change it; the browser too."""
        self.assertTrue(self.app.get(PROFILE).json()["email_editable"])
        response = self.app.patch(PROFILE, {"email": "bob.app@example.org"}, format="json")
        self.assertEqual((response.status_code, response.json()["email"]), (200, "bob.app@example.org"))
        unlimited = self.client_of(self.bob_user)
        self.assertTrue(unlimited.get(PROFILE).json()["email_editable"])
        response = unlimited.patch(PROFILE, {"email": "bob.all@example.org"}, format="json")
        self.assertEqual((response.status_code, response.json()["email"]), (200, "bob.all@example.org"))
        self.bob_user.refresh_from_db()
        self.assertEqual(self.bob_user.email, "bob.all@example.org")
        browser = APIClient()
        browser.force_login(self.bob_user)
        response = browser.patch(PROFILE, {"email": "bob@example.org"}, format="json")
        self.assertEqual((response.status_code, response.json()["email_editable"]), (200, True))
        reader = self.client_of(self.bob_user, read_only=True)
        self.assertFalse(reader.get(PROFILE).json()["email_editable"])

    def test_if_match(self) -> None:
        """API-010: the profile has an ETag; a change against an outdated one is refused with 412."""
        tag = self.app.get(PROFILE)["ETag"]
        self.assertEqual(
            self.app.patch(PROFILE, {"phone": "0170 2"}, format="json", HTTP_IF_MATCH=tag).status_code, 200
        )
        response = self.app.patch(PROFILE, {"phone": "0170 3"}, format="json", HTTP_IF_MATCH=tag)
        self.assert_error(response, 412, "precondition_failed")


class AbsenceApiTests(CrewCase):
    """API-015: the own absences from 30 days back; enter and delete (PER-012)."""

    def test_list_from_thirty_days_back(self) -> None:
        """API-014: an absence that ended more than 30 days ago is not listed."""
        old = Absence.objects.create(person=self.bob, start=at(1, month=1), end=at(15, month=1))
        recent = Absence.objects.create(person=self.bob, start=at(1, month=2), end=at(5, month=2))
        coming = Absence.objects.create(person=self.bob, kind=AbsenceKind.VACATION, start=at(20), end=at(25))
        Absence.objects.create(person=make_person("Carla Clausen"), start=at(20), end=at(25))
        response = self.app.get(ABSENCES)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["id"] for row in response.json()], [recent.pk, coming.pk])
        self.assertNotIn(old.pk, [row["id"] for row in response.json()])
        self.assertEqual(response.json()[1]["kind"], "vacation")

    def test_enter_once_and_delete(self) -> None:
        """API-015, API-010: POST with an Idempotency-Key enters once; clashes are warnings; DELETE own ones only."""
        plan(make_project("Stadtfest"), "Tontechnik", self.bob, start=at(10, 8), end=at(10, 20))
        body = {"kind": "vacation", "start": at(10).isoformat(), "end": at(12).isoformat(), "note": "Urlaub"}
        first = self.app.post(ABSENCES, body, format="json", HTTP_IDEMPOTENCY_KEY="abs-1")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(len(first.json()["warnings"]), 1)
        again = self.app.post(ABSENCES, body, format="json", HTTP_IDEMPOTENCY_KEY="abs-1")
        self.assertEqual((again.status_code, again["Idempotent-Replayed"]), (201, "true"))
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(self.bob.absences.count(), 1)
        self.assert_error(
            self.app.post(ABSENCES, {**body, "end": at(9).isoformat()}, format="json"), 400, "validation_error", "end"
        )
        other = Absence.objects.create(person=make_person("Carla Clausen"), start=at(20), end=at(25))
        self.assert_error(self.app.delete(f"{ABSENCES}/{other.pk}"), 404, "not_found")
        self.assertEqual(self.app.delete(f"{ABSENCES}/{first.json()['id']}").status_code, 204)
        self.assertFalse(self.bob.absences.exists())
        self.assertTrue(Absence.objects.filter(pk=other.pk).exists())

    def test_a_read_only_token_changes_nothing(self) -> None:
        absence = Absence.objects.create(person=self.bob, start=at(20), end=at(25))
        reader = self.client_of(self.bob_user, allowed_modules=APP_MODULES, read_only=True)
        body = {"kind": "sick", "start": at(2).isoformat(), "end": at(3).isoformat()}
        self.assert_error(reader.post(ABSENCES, body, format="json"), 403, "permission_denied")
        self.assert_error(reader.delete(f"{ABSENCES}/{absence.pk}"), 403, "permission_denied")
        self.assertEqual(self.bob.absences.count(), 1)


class DeploymentApiTests(CrewCase):
    """API-015: the own crew lines as in "My deployments" (UIX-043)."""

    def setUp(self) -> None:
        super().setUp()
        hall = Venue.objects.create(name="Stadthalle", city="Musterstadt")
        self.festival = make_project("Festival", start=at(10), end=at(14), venue_site=hall)
        self.stage = make_project(
            "Bühne 2", parent=self.festival, start=at(11), end=at(13), status=ProjectStatus.OPTION
        )
        setup = ProjectPhase.objects.create(
            project=self.stage, kind=PhaseKind.SETUP, start=at(11, 8), end=at(11, 12), location="Hof"
        )
        self.past = plan(
            make_project("Firmenfeier", start=at(10, month=2), end=at(11, month=2)),
            "Tontechnik",
            self.bob,
            start=at(10, 18, month=2),
            end=at(10, 23, month=2),
        )
        self.main = plan(self.festival, "Tontechnik", self.bob, start=at(10, 8), end=at(10, 20), meeting_point="Tor 3")
        self.part = plan(self.stage, "Licht", self.bob, start=at(11, 8), end=at(11, 12), phase=setup, note="Leiter")
        cancelled = make_project("Abgesagt", start=at(20), end=at(21), status=ProjectStatus.CANCELLED)
        plan(cancelled, "Tontechnik", self.bob, start=at(20, 8), end=at(20, 18))
        plan(self.festival, "Tontechnik", make_person("Carla Clausen"), start=at(10, 8), end=at(10, 20))

    def test_list_with_past_ones_and_names(self) -> None:
        """API-015, API-014: past deployments too, none of cancelled projects; names instead of IDs."""
        response = self.app.get(DEPLOYMENTS)
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()
        self.assertEqual([row["id"] for row in rows], [self.past.pk, self.main.pk, self.part.pk])
        main, part = rows[1], rows[2]
        self.assertEqual(
            (main["project"]["name"], main["job_function_name"], main["venue_label"], main["meeting_point"]),
            ("Festival", "Tontechnik", "Stadthalle", "Tor 3"),
        )
        self.assertEqual((main["state"], main["phase"], main["request_status"]), ("firm", None, ""))
        self.assertEqual(
            (part["project"]["parent"], part["project"]["parent_number"], part["project"]["parent_name"]),
            (self.festival.pk, self.festival.number, "Festival"),
        )
        self.assertEqual((part["phase_label"], part["note"], part["state"]), ("Aufbau", "Leiter", "option"))
        self.assertEqual(part["venue_label"], "Hof")  # the place of the phase, as "My deployments" shows it
        self.assertEqual(moment(part["start"]), at(11, 8))
        self.assertEqual(part["planned_hours"], "4.00")

    def test_period_and_etag(self) -> None:
        """API-015: ``from``/``to`` narrow (a day alone up to its end); ETag and 304; 400 for nonsense."""
        rows = self.app.get(DEPLOYMENTS, {"from": "2027-03-01", "to": "2027-03-10"}).json()
        self.assertEqual([row["id"] for row in rows], [self.main.pk])
        rows = self.app.get(DEPLOYMENTS, {"from": at(10, 20).isoformat()}).json()
        self.assertEqual([row["id"] for row in rows], [self.part.pk])
        response = self.app.get(DEPLOYMENTS)
        unchanged = self.app.get(DEPLOYMENTS, HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(unchanged.status_code, 304)
        self.part.note = "Leiter und Gaffa"
        self.part.save()
        self.assertEqual(self.app.get(DEPLOYMENTS, HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 200)
        self.assert_error(self.app.get(DEPLOYMENTS, {"from": "gestern"}), 400, "validation_error", "from")

    def test_queries_do_not_grow_with_the_deployments(self) -> None:
        """Bounded queries: the same number for 3 and for 8 deployments."""
        self.app.get(DEPLOYMENTS)  # the first call of a token notes its use and starts its minute
        with CaptureQueriesContext(connection) as few:
            self.app.get(DEPLOYMENTS)
        for day in range(15, 20):
            other = make_project(f"Tag {day}", start=at(day), end=at(day + 1))
            plan(other, "Licht", self.bob, start=at(day, 8), end=at(day, 18))
        with CaptureQueriesContext(connection) as more:
            rows = self.app.get(DEPLOYMENTS).json()
        self.assertEqual(len(rows), 8)
        self.assertEqual(len(more.captured_queries), len(few.captured_queries))


class MeApiTests(CrewCase):
    """API-016: the version of the server in ``GET /me``."""

    def test_server_version(self) -> None:
        response = self.app.get(f"{API}/me")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["server_version"], rentalars.__version__)


class CompanionNotificationApiTests(CrewCase):
    """API-016: ``unread`` of the chosen ones; older unread ones page by page."""

    def test_unread_counts_the_filtered_and_paging_reaches_old_ones(self) -> None:
        for number in range(55):
            set_clock(at(1, 8) + datetime.timedelta(minutes=number))
            notifications.notify([self.bob_user], Kind.FOLLOW_UP, f"Wiedervorlage {number}", email=False)
        for number in range(70):
            set_clock(at(2, 8) + datetime.timedelta(minutes=number))
            notifications.notify([self.bob_user], Kind.PROJECT_CHANGE, f"Geändert {number}", email=False)
        Notification.objects.filter(title="Wiedervorlage 54").update(read_at=at(2, 9))
        self.assertTrue(Notification.objects.filter(kind=Kind.FOLLOW_UP, companion=True).exists())
        everything = self.app.get(f"{API}/notifications").json()
        self.assertEqual((everything["unread"], everything["unread_total"]), (124, 124))
        first = self.app.get(f"{API}/notifications", {"companion": 1, "unread": 1}).json()
        self.assertEqual((first["count"], first["unread"], first["unread_total"]), (54, 54, 124))
        self.assertEqual(len(first["results"]), 50)
        rest = self.app.get(first["next"]).json()
        self.assertEqual([row["title"] for row in rest["results"]][-1], "Wiedervorlage 0")
        self.assertEqual(len(rest["results"]), 4)
        project = self.app.get(f"{API}/notifications", {"category": "project", "companion": 1}).json()
        self.assertEqual((project["count"], project["unread"]), (55, 54))


class PayKindApiTests(CrewCase):
    """API-016: ``pay_kind`` and ``in_day_rate`` on time entries, as "My times" shows them."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.light = job_function("Licht", price="40.00")
        self.sound = job_function("Tontechnik", price="45.00")
        self.rig = job_function("Rigging", price="50.00")
        from rentalars.personnel import services

        for function in (self.light, self.sound, self.rig):
            services.set_rate(self.bob, function, D("30.00"), datetime.date(2027, 1, 1))
        plan(
            self.project,
            self.sound,
            self.bob,
            start=at(11, 8),
            end=at(11, 22),
            billing=CrewBilling.DAY,
            daily_rate=D("280.00"),
        )
        plan(self.project, self.rig, self.bob, start=at(12, 8), end=at(12, 18), cost_flat_rate=D("500.00"))
        self.hourly = record_time(self.bob, self.project, self.light, at(10, 8), at(10, 12))
        self.morning = record_time(self.bob, self.project, self.sound, at(11, 8), at(11, 12))
        self.evening = record_time(self.bob, self.project, self.sound, at(11, 18), at(11, 22))
        self.flat = record_time(self.bob, self.project, self.rig, at(12, 8), at(12, 18))

    def kinds(self, rows: list[dict[str, Any]]) -> dict[int, tuple[Any, Any]]:
        return {row["id"]: (row.get("pay_kind"), row.get("in_day_rate")) for row in rows}

    def test_kinds_in_lists_pages_and_single_entries(self) -> None:
        """API-016, API-014: the day rate once per day – also when the page holds only the later entry."""
        rows = self.app.get(f"{API}/time-entries").json()["results"]
        expected = {
            self.hourly.pk: ("hourly", False),
            self.morning.pk: ("daily", False),
            self.evening.pk: ("daily", True),
            self.flat.pk: ("flat", False),
        }
        self.assertEqual(self.kinds(rows), expected)
        # Newest first, two per page: the evening is on the first page without its morning.
        page = self.app.get(f"{API}/time-entries", {"page_size": 2}).json()["results"]
        self.assertEqual(self.kinds(page), {self.flat.pk: ("flat", False), self.evening.pk: ("daily", True)})
        single = self.app.get(f"{API}/time-entries/{self.evening.pk}").json()
        self.assertEqual((single["pay_kind"], single["in_day_rate"]), ("daily", True))
        report = self.app.get(f"{API}/reports/hours", {"group_by": "day"}).json()["entries"]
        self.assertEqual(self.kinds(report), expected)

    def test_only_with_the_rate(self) -> None:
        """AUT-019, PER-010: without seeing the own rates, no pay at all – as "My times"."""
        settings = SystemSettings.load()
        settings.people_see_own_rates = False
        settings.save()
        row = self.app.get(f"{API}/time-entries/{self.morning.pk}").json()
        self.assertNotIn("pay_kind", row)
        self.assertNotIn("hourly_rate", row)

    def test_queries_do_not_grow_with_the_entries(self) -> None:
        """Bounded queries: a page of 4 entries and a page of 10 need the same number."""
        self.app.get(f"{API}/time-entries")  # the first call of a token notes its use and starts its minute
        with CaptureQueriesContext(connection) as few:
            self.app.get(f"{API}/time-entries")
        for day in range(15, 21):
            record_time(self.bob, self.project, self.sound, at(day, 8), at(day, 10))
        with CaptureQueriesContext(connection) as more:
            rows = self.app.get(f"{API}/time-entries").json()["results"]
        self.assertEqual(len(rows), 10)
        self.assertEqual(len(more.captured_queries), len(few.captured_queries))


class SchemaTests(ApiTestCase):
    """API-004: the new operations and fields are described."""

    def test_described(self) -> None:
        schema = self.admin.get(f"{API}/schema", {"format": "json"}).json()
        for path in ("/people/me/profile", "/people/me/absences", "/people/me/absences/{absence_pk}"):
            self.assertIn(f"{API}{path}", schema["paths"])
        self.assertIn("get", schema["paths"][f"{API}/people/me/deployments"])
        self.assertIn("changed_at", schema["components"]["schemas"]["PatchedOwnProfileChangeRequest"]["properties"])
        self.assertIn("updated_at", schema["components"]["schemas"]["OwnProfile"]["properties"])
        self.assertIn("venue_label", schema["components"]["schemas"]["OwnDeployment"]["properties"])
