# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests (API-014), area "companion": the companion app's offline changes and names.

* PRJ-113: ``field_changed_at`` on ``/projects``;
  ``changed_at`` on ``PATCH /projects/{id}``, ``POST …/status`` and
  ``PUT``/``DELETE …/follow-up`` – the younger change wins.
* PRJ-114: ``case_status_changed_at`` on ``/service-cases``.
* API-016: ``manager_name`` and ``venue_label``.
* The app's token – limited to packing, projects, time tracking and e-mail –
  reaches chat, correspondence, price overview and ``/mail/unknown``.

The server's clock stands at 10:00 on 1 March 2027 in these tests; the
project was created at 08:00 (``NOW``).
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any

from rentalars.api.models import WriteLock
from rentalars.customers.models import Venue
from rentalars.projects import service_cases, services
from rentalars.projects.models import CaseStatus, Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    NOW,
    at,
    clock,
    make_customer,
    make_person,
    make_project,
    make_user,
    plan,
    set_clock,
)

#: The modules the token of the companion app is limited to.
APP_MODULES = ["packing", "projects", "time_tracking", "email"]

MINUTE = datetime.timedelta(minutes=1)
SERVER_NOW = NOW + datetime.timedelta(hours=2)

#: The keys PRJ-113 names at least.
REQUIRED_KEYS = {"name", "venue", "start", "end", "event_start", "event_end", "notes", "status", "follow_up"}


def moment(text: str) -> datetime.datetime:
    """A moment as the API writes it."""
    return datetime.datetime.fromisoformat(text)


class CompanionApiTestCase(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.app = self.client_of(self.paula, allowed_modules=APP_MODULES)
        self.project = make_project(
            "Stadtfest", venue="Marktplatz", manager=self.paula, status=ProjectStatus.INQUIRY, notes="Bühne"
        )
        self.url = f"{API}/projects/{self.project.pk}"
        set_clock(SERVER_NOW)

    def server_change(self, at_moment: datetime.datetime, **changes: Any) -> None:
        """A change on the server – in the browser, say – at this moment."""
        set_clock(at_moment)
        services.update_project(Project.objects.get(pk=self.project.pk), **changes)
        set_clock(SERVER_NOW)

    def stored(self) -> Project:
        return Project.objects.get(pk=self.project.pk)


class FieldChangedAtApiTests(CompanionApiTestCase):
    """PRJ-113: the moments on ``GET /projects`` and ``/projects/{id}``."""

    def test_list_and_detail_show_the_moment_of_every_field(self) -> None:
        self.server_change(NOW + 30 * MINUTE, venue="Rathaus")
        detail = self.app.get(self.url).json()
        listed = self.app.get(f"{API}/projects").json()["results"][0]
        for document in (detail, listed):
            times = document["field_changed_at"]
            self.assertLessEqual(REQUIRED_KEYS, set(times))
            self.assertEqual(moment(times["venue"]), NOW + 30 * MINUTE)
            self.assertEqual(moment(times["name"]), NOW)
            self.assertNotIn("case_status", times)  # a project, not a case
        # The fingerprint of the answer still works (API-010).
        response = self.app.get(self.url)
        self.assertEqual(self.app.get(self.url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 304)

    def test_the_deployment_view_shows_names_and_the_moments_of_its_fields_only(self) -> None:
        """API-016, AUT-023: manager and venue by name; no moment of a field it does not show."""
        venue = Venue.objects.create(name="Stadthalle", city="Musterstadt")
        services.update_project(self.stored(), venue_site=venue)
        frieda = make_user("frieda", roles=("Freie Kraft",))
        person = make_person("Frieda Frei", rates={"Stagehand": "20.00"}, user=frieda)
        plan(self.project, "Stagehand", person, start=at(10, 8), end=at(10, 14))
        crew = self.client_of(frieda, allowed_modules=APP_MODULES)
        for document in (crew.get(self.url).json(), crew.get(f"{API}/projects").json()["results"][0]):
            self.assertEqual(document["access"], "deployment")
            self.assertEqual(document["manager_name"], "paula")
            self.assertEqual(document["venue_label"], "Stadthalle, Musterstadt – Marktplatz")
            self.assertNotIn("notes", document)
            self.assertEqual(
                set(document["field_changed_at"]),
                {"name", "venue_site", "venue", "manager", "status", "start", "end", "event_start", "event_end"}
                | {"is_internal"},
            )
        full = self.app.get(self.url).json()
        self.assertEqual((full["manager_name"], full["access"]), ("paula", "edit"))
        self.assertIn("notes", full["field_changed_at"])


class PatchWithChangedAtApiTests(CompanionApiTestCase):
    """PRJ-113: ``PATCH /projects/{id}`` with ``changed_at`` – each field on its own."""

    def patch(self, when: datetime.datetime | str, **fields: Any) -> Any:
        changed_at = when if isinstance(when, str) else when.isoformat()
        return self.app.patch(self.url, {**fields, "changed_at": changed_at}, format="json")

    def test_a_later_change_counts_and_keeps_its_moment(self) -> None:
        phone = NOW + 90 * MINUTE
        response = self.patch(phone, name="Stadtfest 2027")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["name"], body["applied"]), ("Stadtfest 2027", ["name"]))
        self.assertEqual(moment(body["field_changed_at"]["name"]), phone)
        self.assertEqual(moment(body["field_changed_at"]["venue"]), NOW)
        self.assertEqual(self.stored().name, "Stadtfest 2027")

    def test_an_older_change_does_not_count(self) -> None:
        self.server_change(NOW + 60 * MINUTE, name="Im Browser")
        body = self.patch(NOW + 30 * MINUTE, name="Vom Telefon").json()
        self.assertEqual((body["name"], body["applied"]), ("Im Browser", []))
        self.assertEqual(self.stored().name, "Im Browser")

    def test_at_the_same_moment_the_server_wins(self) -> None:
        self.server_change(NOW + 60 * MINUTE, name="Im Browser")
        body = self.patch(NOW + 60 * MINUTE, name="Vom Telefon").json()
        self.assertEqual((body["name"], body["applied"]), ("Im Browser", []))

    def test_fields_are_judged_one_by_one(self) -> None:
        self.server_change(NOW + 60 * MINUTE, venue="Rathaus")
        body = self.patch(
            NOW + 30 * MINUTE, name="Vom Telefon", venue="Kirche", start="2027-03-10T07:00:00+01:00"
        ).json()
        self.assertEqual(body["applied"], ["name", "start"])
        self.assertEqual((body["name"], body["venue"]), ("Vom Telefon", "Rathaus"))
        self.assertEqual(moment(body["start"]), at(10, 7))

    def test_a_moment_in_the_future_counts_as_now(self) -> None:
        body = self.patch(SERVER_NOW + 3 * datetime.timedelta(hours=1), name="Uhr geht vor").json()
        self.assertEqual(body["applied"], ["name"])
        self.assertEqual(moment(body["field_changed_at"]["name"]), SERVER_NOW)
        # Another phone ahead as well: "now" again – equal, the server wins.
        self.assertEqual(self.patch(SERVER_NOW + 5 * MINUTE, name="Auch vor").json()["applied"], [])
        set_clock(SERVER_NOW + MINUTE)
        self.assertEqual(self.patch(SERVER_NOW + 5 * MINUTE, name="Später").json()["applied"], ["name"])

    def test_the_same_value_counts_from_its_moment(self) -> None:
        """A device that set the name the server has already – a third, older change does not win against it."""
        self.assertEqual(self.patch(NOW + 60 * MINUTE, name="Stadtfest").json()["applied"], ["name"])
        self.assertEqual(moment(self.app.get(self.url).json()["field_changed_at"]["name"]), NOW + 60 * MINUTE)
        self.assertEqual(self.patch(NOW + 30 * MINUTE, name="Älter").json()["applied"], [])
        self.assertEqual(self.stored().name, "Stadtfest")

    def test_a_refused_value_changes_nothing(self) -> None:
        self.assert_error(self.patch(NOW + 60 * MINUTE, name=""), 400, "validation_error", "name")
        self.assertEqual(self.stored().name, "Stadtfest")
        self.assertEqual(self.stored().field_changed_at["name"], NOW.astimezone(datetime.UTC).isoformat())

    def test_compared_and_written_under_the_write_lock(self) -> None:
        self.patch(NOW + 60 * MINUTE, notes="Neu")
        key = hashlib.sha256(f"record:projects.project:{self.project.pk}".encode()).hexdigest()
        self.assertTrue(WriteLock.objects.filter(key=key).exists())

    def test_without_changed_at_everything_is_as_before(self) -> None:
        etag = self.app.get(self.url)["ETag"]
        self.server_change(NOW + 60 * MINUTE, notes="Im Browser")
        stale = self.app.patch(self.url, {"name": "Neu"}, format="json", HTTP_IF_MATCH=etag)
        self.assert_error(stale, 412, "precondition_failed")
        body = self.app.patch(self.url, {"name": "Neu"}, format="json").json()
        self.assertEqual(body["name"], "Neu")
        self.assertNotIn("applied", body)
        self.assertEqual(moment(body["field_changed_at"]["name"]), SERVER_NOW)

    def test_a_moment_without_time_zone_or_no_moment_is_refused(self) -> None:
        for wrong in ("2027-03-01T09:30:00", "gestern"):
            with self.subTest(value=wrong):
                self.assert_error(self.patch(wrong, name="Neu"), 400, "validation_error", "changed_at")
        self.assertEqual(self.stored().name, "Stadtfest")

    def test_read_only_fields_are_not_judged(self) -> None:
        body = self.patch(NOW + 60 * MINUTE, status="cancelled", notes="Neu").json()
        self.assertEqual((body["applied"], body["status"]), (["notes"], "inquiry"))


class StatusWithChangedAtApiTests(CompanionApiTestCase):
    """PRJ-113: ``POST /projects/{id}/status`` with ``changed_at``; 409 when no longer allowed."""

    def status(self, new_status: str, when: datetime.datetime) -> Any:
        return self.app.post(
            f"{self.url}/status", {"status": new_status, "changed_at": when.isoformat()}, format="json"
        )

    def server_status(self, new_status: str, when: datetime.datetime) -> None:
        set_clock(when)
        services.change_status(self.stored(), new_status, rights=ALL_RIGHTS)
        set_clock(SERVER_NOW)

    def test_a_later_status_counts(self) -> None:
        body = self.status("option", NOW + 60 * MINUTE).json()
        self.assertEqual((body["status"], body["applied"]), ("option", ["status"]))
        self.assertEqual(moment(body["field_changed_at"]["status"]), NOW + 60 * MINUTE)

    def test_an_older_status_does_not_count(self) -> None:
        self.server_status("option", NOW + 60 * MINUTE)
        response = self.status("cancelled", NOW + 30 * MINUTE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["status"], response.json()["applied"]), ("option", []))

    def test_a_step_no_longer_allowed_is_a_conflict_with_the_project_as_it_is(self) -> None:
        self.server_status("cancelled", NOW + 60 * MINUTE)
        response = self.status("confirmed", NOW + 90 * MINUTE)
        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual((body["status"], body["applied"], body["id"]), ("cancelled", [], self.project.pk))
        self.assertEqual(body["error"]["code"], "status_not_allowed")
        self.assertTrue(body["error"]["message"])
        self.assertEqual(moment(body["field_changed_at"]["status"]), NOW + 60 * MINUTE)
        self.assertEqual(self.stored().status, "cancelled")

    def test_the_status_it_has_already_counts_from_its_moment(self) -> None:
        self.assertEqual(self.status("inquiry", NOW + 60 * MINUTE).json()["applied"], ["status"])
        self.assertEqual(self.status("option", NOW + 30 * MINUTE).json()["applied"], [])
        self.assertEqual(self.stored().status, "inquiry")

    def test_an_unknown_status_is_still_a_wrong_request(self) -> None:
        self.assert_error(self.status("vielleicht", NOW + 60 * MINUTE), 400, "validation_error", "status")

    def test_without_changed_at_as_before(self) -> None:
        body = self.app.post(f"{self.url}/status", {"status": "option"}, format="json").json()
        self.assertEqual(body["status"], "option")
        self.assertNotIn("applied", body)
        self.assert_error(
            self.app.post(f"{self.url}/status", {"status": "out"}, format="json"), 400, "validation_error"
        )


class FollowUpWithChangedAtApiTests(CompanionApiTestCase):
    """PRJ-113: ``PUT``/``DELETE /projects/{id}/follow-up`` with ``changed_at``."""

    def test_set_later_counts_older_does_not(self) -> None:
        put = f"{self.url}/follow-up"
        data = {"follow_up_on": "2027-03-05", "follow_up_note": "Angebot nachfassen"}
        body = self.app.put(put, {**data, "changed_at": (NOW + 60 * MINUTE).isoformat()}, format="json").json()
        self.assertEqual((body["follow_up_on"], body["applied"]), ("2027-03-05", ["follow_up"]))
        self.assertEqual(moment(body["field_changed_at"]["follow_up"]), NOW + 60 * MINUTE)
        older = {"follow_up_on": "2027-03-08", "changed_at": (NOW + 30 * MINUTE).isoformat()}
        body = self.app.put(put, older, format="json").json()
        self.assertEqual((body["follow_up_on"], body["applied"]), ("2027-03-05", []))

    def test_remove_with_the_moment_in_the_address(self) -> None:
        self.app.put(f"{self.url}/follow-up", {"follow_up_on": "2027-03-05"}, format="json")  # at 10:00
        # "+01:00" not encoded: arrives as " 01:00" and is read as meant.
        body = self.app.delete(f"{self.url}/follow-up?changed_at=2027-03-01T09:30:00+01:00").json()
        self.assertEqual((body["follow_up_on"], body["applied"]), ("2027-03-05", []))
        set_clock(SERVER_NOW + 30 * MINUTE)
        body = self.app.delete(f"{self.url}/follow-up?changed_at=2027-03-01T10:15:00%2B01:00").json()
        self.assertEqual((body["follow_up_on"], body["applied"]), (None, ["follow_up"]))
        self.assertEqual(moment(body["field_changed_at"]["follow_up"]), at(1, 10, 15))

    def test_removing_what_is_not_there_counts_from_its_moment(self) -> None:
        body = self.app.delete(f"{self.url}/follow-up", {"changed_at": (NOW + 60 * MINUTE).isoformat()}, format="json")
        self.assertEqual(body.json()["applied"], ["follow_up"])
        self.assertEqual(moment(body.json()["field_changed_at"]["follow_up"]), NOW + 60 * MINUTE)

    def test_an_invalid_follow_up_is_refused_whatever_its_moment(self) -> None:
        response = self.app.put(f"{self.url}/follow-up", {"changed_at": (NOW + 30 * MINUTE).isoformat()}, format="json")
        self.assert_error(response, 400, "validation_error", "follow_up_on")


class ServiceCaseApiTestCase(CompanionApiTestCase):
    """A service case of the customer "Theater", created at 08:00, open."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(NOW)
        self.case = service_cases.create_case(
            name="Spot flackert", customer=make_customer("Theater"), manager=self.paula
        )
        set_clock(SERVER_NOW)
        self.case_url = f"{API}/service-cases/{self.case.pk}"

    def patch(self, **fields: Any) -> Any:
        return self.app.patch(self.case_url, fields, format="json")


class ServiceCaseChangeTimesApiTests(ServiceCaseApiTestCase):
    """PRJ-114: the status of a service case with its moment; API-016: ``manager_name``."""

    def test_list_and_detail_show_the_moment_of_the_status_and_the_manager(self) -> None:
        set_clock(NOW + 30 * MINUTE)
        service_cases.set_case_status(Project.objects.get(pk=self.case.pk), CaseStatus.IN_PROGRESS)
        set_clock(SERVER_NOW)
        detail = self.app.get(self.case_url).json()
        listed = self.app.get(f"{API}/service-cases").json()["results"][0]
        for document in (detail, listed):
            self.assertEqual(moment(document["case_status_changed_at"]), NOW + 30 * MINUTE)
            self.assertEqual(document["case_status_changed_at"], document["field_changed_at"]["case_status"])
            self.assertEqual(moment(document["field_changed_at"]["name"]), NOW)
            self.assertEqual(document["manager_name"], "paula")
        # /projects/{id} reads a case too, with its status.
        self.assertIn("case_status", self.app.get(f"{API}/projects/{self.case.pk}").json()["field_changed_at"])

    def test_a_later_status_counts(self) -> None:
        body = self.patch(case_status="done", case_status_changed_at=(NOW + 60 * MINUTE).isoformat()).json()
        self.assertEqual((body["case_status"], body["applied"]), ("done", ["case_status"]))
        self.assertEqual(moment(body["case_status_changed_at"]), NOW + 60 * MINUTE)

    def test_an_older_status_does_not_count(self) -> None:
        set_clock(NOW + 60 * MINUTE)
        service_cases.set_case_status(Project.objects.get(pk=self.case.pk), CaseStatus.IN_PROGRESS)
        set_clock(SERVER_NOW)
        body = self.patch(case_status="done", case_status_changed_at=(NOW + 30 * MINUTE).isoformat()).json()
        self.assertEqual((body["case_status"], body["applied"]), ("in_progress", []))
        # With ``changed_at`` the same moment as the stored one means: the server wins.
        body = self.patch(case_status="done", changed_at=(NOW + 60 * MINUTE).isoformat()).json()
        self.assertEqual((body["case_status"], body["applied"]), ("in_progress", []))
        # ``case_status_changed_at`` equal to the stored moment is the echo of a GET – see RoundTripApiTests.

    def test_waiting_with_its_follow_up_counts_or_not_as_a_whole(self) -> None:
        waiting = {"case_status": "waiting", "case_waiting_for": "reply", "follow_up_on": "2027-03-05"}
        set_clock(NOW + 60 * MINUTE)
        self.app.put(f"{API}/projects/{self.case.pk}/follow-up", {"follow_up_on": "2027-03-04"}, format="json")
        set_clock(SERVER_NOW)
        # The status is later than its last change, the follow-up earlier than its own: both go together.
        body = self.patch(**waiting, case_status_changed_at=(NOW + 30 * MINUTE).isoformat()).json()
        self.assertEqual(body["applied"], ["follow_up", "case_status"])
        self.assertEqual(
            (body["case_status"], body["case_waiting_for"], body["follow_up_on"]), ("waiting", "reply", "2027-03-05")
        )
        older = {**waiting, "follow_up_on": "2027-03-09", "case_status": "backlog"}
        body = self.patch(**older, case_status_changed_at=(NOW + 20 * MINUTE).isoformat()).json()
        self.assertEqual((body["case_status"], body["follow_up_on"], body["applied"]), ("waiting", "2027-03-05", []))

    def test_changed_at_judges_every_field(self) -> None:
        set_clock(NOW + 60 * MINUTE)
        service_cases.update_case(Project.objects.get(pk=self.case.pk), notes="Im Browser")
        set_clock(SERVER_NOW)
        body = self.patch(name="Spot defekt", notes="Vom Telefon", changed_at=(NOW + 30 * MINUTE).isoformat()).json()
        self.assertEqual((body["name"], body["notes"], body["applied"]), ("Spot defekt", "Im Browser", ["name"]))

    def test_other_fields_without_their_moment_are_taken_as_before(self) -> None:
        body = self.patch(
            name="Spot defekt", case_status="in_progress", case_status_changed_at=(NOW + 30 * MINUTE).isoformat()
        ).json()
        self.assertEqual(body["applied"], ["name", "case_status"])
        self.assertEqual(moment(body["field_changed_at"]["name"]), SERVER_NOW)
        self.assertEqual(moment(body["case_status_changed_at"]), NOW + 30 * MINUTE)

    def test_without_a_moment_as_before(self) -> None:
        body = self.patch(case_status="in_progress").json()
        self.assertEqual(body["case_status"], "in_progress")
        self.assertNotIn("applied", body)
        self.assertEqual(moment(body["case_status_changed_at"]), SERVER_NOW)
        self.assert_error(
            self.patch(case_status="done", case_status_changed_at="morgen"),
            400,
            "validation_error",
            "case_status_changed_at",
        )

    def test_creating_ignores_the_moments(self) -> None:
        customer = self.case.customer
        response = self.app.post(
            f"{API}/service-cases",
            {"name": "Neu", "customer": customer.pk, "changed_at": (NOW + 30 * MINUTE).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(moment(response.json()["case_status_changed_at"]), SERVER_NOW)


class RoundTripApiTests(ServiceCaseApiTestCase):
    """Review, finding 2: a client sends back what GET delivered, with another status.

    ``case_status_changed_at`` is read and written under one name; the moment
    it echoes is no moment of a change and must not stop the status.
    ``field_changed_at`` is read-only.
    """

    def round_trip(self, method: str, **changes: Any) -> Any:
        """GET the case, change it, send the whole document back."""
        document = self.app.get(self.case_url).json()
        document.update(changes)
        return getattr(self.app, method)(self.case_url, document, format="json")

    def test_put_and_patch_of_the_whole_case_change_the_status(self) -> None:
        for method, new_status in (("put", "in_progress"), ("patch", "done")):
            with self.subTest(method=method):
                set_clock(SERVER_NOW + (5 if method == "put" else 10) * MINUTE)
                response = self.round_trip(method, case_status=new_status, name=f"Spot ({method})")
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                self.assertEqual((body["case_status"], body["name"]), (new_status, f"Spot ({method})"))
                self.assertIn("case_status", body["applied"])
                self.assertEqual(Project.objects.get(pk=self.case.pk).case_status, new_status)
                # Noted with the server's clock, as any change without a moment of its own.
                self.assertEqual(moment(body["case_status_changed_at"]), clock())

    def test_the_echo_in_another_time_zone_is_still_the_echo(self) -> None:
        stored = moment(self.app.get(self.case_url).json()["case_status_changed_at"])
        utc = stored.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
        body = self.patch(case_status="in_progress", case_status_changed_at=utc).json()
        self.assertEqual((body["case_status"], body["applied"]), ("in_progress", ["case_status"]))

    def test_a_real_older_moment_is_still_refused_a_later_one_applied(self) -> None:
        set_clock(NOW + 60 * MINUTE)
        service_cases.set_case_status(Project.objects.get(pk=self.case.pk), CaseStatus.IN_PROGRESS)
        set_clock(SERVER_NOW)
        older = self.round_trip("put", case_status="done", case_status_changed_at=(NOW + 30 * MINUTE).isoformat())
        self.assertEqual(
            (older.json()["case_status"], older.json()["applied"].count("case_status")), ("in_progress", 0)
        )
        later = self.round_trip("put", case_status="done", case_status_changed_at=(NOW + 90 * MINUTE).isoformat())
        self.assertEqual((later.json()["case_status"], later.json()["applied"].count("case_status")), ("done", 1))
        self.assertEqual(moment(later.json()["case_status_changed_at"]), NOW + 90 * MINUTE)

    def test_field_changed_at_sent_back_is_ignored(self) -> None:
        document = self.app.get(self.case_url).json()
        forged = dict.fromkeys(document["field_changed_at"], "2099-01-01T00:00:00+00:00")
        body = self.round_trip("put", field_changed_at=forged, notes="Neu").json()
        self.assertEqual(moment(body["field_changed_at"]["notes"]), SERVER_NOW)
        self.assertEqual(moment(body["field_changed_at"]["name"]), NOW)
        project = self.app.get(f"{API}/projects/{self.case.pk}").json()
        self.assertEqual(moment(project["field_changed_at"]["customer"]), NOW)

    def test_a_project_sent_back_whole(self) -> None:
        """``changed_at`` is write-only – a GET sent back carries none; ``field_changed_at`` is ignored."""
        document = self.app.get(self.url).json()
        self.assertNotIn("changed_at", document)
        document.update(name="Stadtfest 2027", field_changed_at={"name": "2099-01-01T00:00:00+00:00"})
        response = self.app.put(self.url, document, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["name"], "Stadtfest 2027")
        self.assertNotIn("applied", body)
        self.assertEqual(moment(body["field_changed_at"]["name"]), SERVER_NOW)


class AppTokenApiTests(CompanionApiTestCase):
    """The app token: chat, mails, price overview and inquiries with the app's token."""

    def test_everything_the_app_uses_answers(self) -> None:
        for address in (
            f"{self.url}",
            f"{self.url}/chat",
            f"{self.url}/chat/read",
            f"{self.url}/mails",
            f"{self.url}/price-overview",
            f"{API}/mail/unknown",
            f"{API}/service-cases",
        ):
            with self.subTest(address=address):
                self.assertEqual(self.app.get(address).status_code, 200, address)
        self.assertEqual(self.app.post(f"{self.url}/chat", {"text": "Bin da"}, format="json").status_code, 201)
        self.assertEqual(self.app.post(f"{self.url}/chat/read", {}, format="json").status_code, 200)
        changed = self.app.patch(
            self.url, {"notes": "Neu", "changed_at": (NOW + 60 * MINUTE).isoformat()}, format="json"
        )
        self.assertEqual(changed.json()["applied"], ["notes"])

    def test_without_the_module_email_the_inquiries_stay_closed(self) -> None:
        without = self.client_of(self.paula, allowed_modules=["packing", "projects", "time_tracking"])
        self.assert_error(without.get(f"{API}/mail/unknown"), 403, "permission_denied")
