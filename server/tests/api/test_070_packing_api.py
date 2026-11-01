# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, helper "packing": what the Android app needs from the server.

What the app relies on – pinned here
so that it cannot break: login, tokens, logout, ``/me``, the packlist with
``ETag`` and quantities as text, time entries with ``Idempotency-Key``, the
error format, German messages, no redirects, the ``Date`` header.
The rest is new: change times per row (PCK-027), the packlists to
take along and the sync (PCK-026, PCK-027), limits for tokens (AUT-021).
PCK-028: the return is ticked, then booked with ``take-back``.
"""

from __future__ import annotations

import datetime
import http.client
import json
import re
import urllib.parse
from decimal import Decimal
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import LiveServerTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from rentalars.accounts import twofactor
from rentalars.accounts.models import ApiToken, Role
from rentalars.accounts.rights import Level
from rentalars.api.models import IdempotentCall
from rentalars.api.safeguards import IDEMPOTENCY_TTL
from rentalars.core.defaults import install_defaults
from rentalars.core.models import AuditAction, AuditLogEntry, SystemSettings
from rentalars.material import numbering
from rentalars.packing import services
from rentalars.packing.models import PackEntry, Packlist
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectStatus
from rentalars.timetracking.models import TimeEntry
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    LATER,
    PASSWORD,
    add_line,
    at,
    job_function,
    make_item,
    make_model,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
    set_clock,
)

D = Decimal
TWO_DECIMALS = re.compile(r"^\d+\.\d\d$")
#: The quantities of a packlist row; each is text with two decimals.
ROW_QUANTITIES = (
    "required",
    "packed",
    "issued",
    "returned",
    "taken_back",
    "ready_to_issue",
    "ready_to_take_back",
    "still_out",
    "missing",
    "awaiting_handover",
    "handed_over",
)


class PacklistApiTestCase(ApiTestCase):
    """Ten cables and a single rack on the packlist of a confirmed project, 10 to 12 March 2027."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 12, "XLR-Kabel 5 m")
        self.rack_product = make_product("T-500", "Funkrack")
        make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.project = make_project()
        self.cable_line = add_line(self.project, self.cable, 10).line
        self.rack_line = add_line(self.project, self.rack_product, 1).line
        self.packlist = services.get_packlist(self.project)
        self.base = f"{API}/projects/{self.project.pk}/packlists/{self.packlist.pk}"

    def rows(self, document: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {row["article_number"]: row for section in document["sections"] for row in section["rows"]}

    def tick(self, quantity: str, field: str = "packed", client: APIClient | None = None) -> Any:
        body = {"line": self.cable_line.pk, "product": self.cable.pk, field: quantity}
        return (client or self.admin).patch(f"{self.base}/rows", body, format="json")

    def change(self, field: str, quantity: Any, moment: str, line: Any = None) -> dict[str, Any]:
        line = line or self.cable_line
        return {"line": line.pk, "product": line.product_id, "field": field, "quantity": quantity, "changed_at": moment}

    def sync(self, *changes: dict[str, Any], client: APIClient | None = None, **headers: Any) -> Any:
        return (client or self.admin).post(f"{self.base}/sync", {"changes": list(changes)}, format="json", **headers)


# --- A: unchanged --------------------------------------------------------------------------------


class AppSignInApiTests(ApiTestCase):
    """A1 to A5 (APP-001): password (and code), a token of its own for the app, ``/me``, revoking it, logout."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_user("anna", roles=("Crew",))
        self.person = make_person("Anna Becker", user=self.anna)
        self.browser = APIClient(enforce_csrf_checks=True)

    def login(self, **body: str) -> Any:
        return self.browser.post(f"{API}/auth/login", {"username": "anna", "password": PASSWORD, **body}, format="json")

    def test_the_way_of_the_app(self) -> None:
        answer = self.login()
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertTrue({"sessionid", "csrftoken"} <= set(answer.cookies))
        csrf = answer.cookies["csrftoken"].value
        body = {
            "name": "Rentalars-App",
            "allowed_modules": ["packing", "projects", "time_tracking"],
            "expires_at": "2027-05-30T08:00:00+02:00",
        }
        # The session alone is not enough: the CSRF token and the origin belong to it.
        self.assert_error(self.browser.post(f"{API}/tokens", body, format="json"), 403, "permission_denied")
        created = self.browser.post(
            f"{API}/tokens",
            body,
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_ORIGIN="http://testserver",
            HTTP_REFERER="http://testserver/",
        )
        self.assertEqual(created.status_code, 201, created.content)
        token = created.json()
        self.assertTrue(token["key"].startswith("rl_"))
        self.assertEqual(token["expires_at"], "2027-05-30T08:00:00+02:00")
        self.assertIsInstance(token["id"], int)
        logout = self.browser.post(f"{API}/auth/logout", HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="http://testserver")
        self.assertEqual(logout.status_code, 204)

        app = APIClient()
        app.credentials(HTTP_AUTHORIZATION=f"Bearer {token['key']}")
        me = app.get(f"{API}/me").json()
        self.assertEqual(
            (me["id"], me["username"], me["full_name"], me["person"]["id"]),
            (self.anna.pk, "anna", "Anna Becker", self.person.pk),
        )
        # Logging out in the app revokes its token with the token itself.
        self.assertEqual(app.delete(f"{API}/tokens/{token['id']}").status_code, 204)
        self.assert_error(app.get(f"{API}/me"), 401, "not_authenticated")

    def test_error_codes_of_the_login(self) -> None:
        self.assert_error(self.login(password="falsch"), 400, "invalid_credentials")
        secret = twofactor.new_secret()
        twofactor.enable(self.anna, secret, twofactor.code_at(secret, twofactor.current_step() - 1))
        self.assert_error(self.login(), 400, "code_required")
        self.assert_error(self.login(code="000000"), 400, "invalid_code")
        answer = self.login(code=twofactor.code_at(secret, twofactor.current_step()))
        self.assertEqual(answer.status_code, 200, answer.content)

    def test_too_many_failures_lock_out(self) -> None:
        for _attempt in range(5):
            self.assert_error(self.login(password="falsch"), 400, "invalid_credentials")
        self.assert_error(self.login(), 429, "locked_out")

    def test_two_factor_must_be_set_up_in_the_browser_first(self) -> None:
        Role.objects.filter(name="Crew").update(requires_two_factor=True)
        self.assert_error(self.login(), 403, "two_factor_setup_required")


class PacklistDocumentApiTests(PacklistApiTestCase):
    """A6 and B: ETag and 304, quantities as text with two decimals, the change times of every row."""

    def test_etag_and_not_modified(self) -> None:
        first = self.admin.get(self.base)
        self.assertEqual(first.status_code, 200)
        tag = first["ETag"]
        again = self.admin.get(self.base, HTTP_IF_NONE_MATCH=tag)
        self.assertEqual((again.status_code, again["ETag"], again.content), (304, tag, b""))
        self.tick("4")
        changed = self.admin.get(self.base, HTTP_IF_NONE_MATCH=tag)
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed["ETag"], tag)

    def test_quantities_are_text_with_two_decimals(self) -> None:
        for document in (self.admin.get(self.base).json(), self.tick("4").json()):
            for row in self.rows(document).values():
                for name in ROW_QUANTITIES:
                    self.assertRegex(row[name], TWO_DECIMALS, f"{row['article_number']} {name}")
            for name in ("ready_to_issue", "not_issued", "ready_to_take_back", "taken_back", "still_out"):
                self.assertRegex(document[name], TWO_DECIMALS, name)
        self.assertEqual(self.rows(self.admin.get(self.base).json())["K-005"]["packed"], "4.00")

    def test_every_row_says_when_its_ticks_changed(self) -> None:
        rows = self.rows(self.admin.get(self.base).json())
        self.assertEqual((rows["K-005"]["packed_changed_at"], rows["K-005"]["returned_changed_at"]), (None, None))
        set_clock(at(9, 8, 15))
        rows = self.rows(self.tick("4").json())
        self.assertEqual(rows["K-005"]["packed_changed_at"], "2027-03-09T07:15:00Z")
        self.assertIsNone(rows["T-500"]["packed_changed_at"])
        set_clock(at(9, 9))
        self.tick("4")  # the same quantity: the moment stays
        self.assertEqual(
            self.rows(self.admin.get(self.base).json())["K-005"]["packed_changed_at"], "2027-03-09T07:15:00Z"
        )
        # Every action answers with them as well.
        steps = (("pack-all", {}), ("issue", {"only_packed": True}), ("return-all", {}))
        for minute, (path, body) in enumerate(steps, start=1):
            set_clock(at(9, 10, minute))
            document = self.admin.post(f"{self.base}/{path}", body, format="json").json()
            self.assertIn("packed_changed_at", self.rows(document)["T-500"])
            self.assertIn("returned_changed_at", self.rows(document)["T-500"])
        rows = self.rows(self.admin.get(self.base).json())
        self.assertEqual(rows["T-500"]["packed_changed_at"], "2027-03-09T09:01:00Z")  # pack-all
        self.assertEqual(rows["K-005"]["packed_changed_at"], "2027-03-09T09:01:00Z")  # 4 → 10
        self.assertEqual(rows["K-005"]["returned_changed_at"], "2027-03-09T09:03:00Z")  # return-all

    def test_the_etag_changes_with_the_moment_alone(self) -> None:
        set_clock(at(9, 8))
        self.tick("4")
        tag = self.admin.get(self.base)["ETag"]
        set_clock(at(9, 10))
        self.sync(self.change("packed", "4.00", "2027-03-09T09:30:00+01:00"))  # same quantity, later moment
        self.assertEqual(self.admin.get(self.base, HTTP_IF_NONE_MATCH=tag).status_code, 200)


class TimeEntriesApiTests(ApiTestCase):
    """A7 (APP-004, ZEI-020): choices, a period of up to 500 rows, an entry with Idempotency-Key; ZEI-009, ZEI-022."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, user=self.anna_user)
        plan(self.project, self.sound, self.anna, start=at(10, 8), end=at(10, 20))
        self.app = self.client_of(self.anna_user, allowed_modules=["packing", "projects", "time_tracking"])
        set_clock(LATER)

    def entry(self, start: str, end: str) -> dict[str, Any]:
        return {"project": self.project.pk, "job_function": self.sound.pk, "start": start, "end": end}

    def test_choices_list_and_once_only(self) -> None:
        choices = self.app.get(f"{API}/time-entries/choices").json()
        self.assertEqual(choices[0]["name"], "Stadtfest")
        body = self.entry("2027-03-10T08:00:00+01:00", "2027-03-10T12:00:00+01:00")
        first = self.app.post(f"{API}/time-entries", body, format="json", HTTP_IDEMPOTENCY_KEY="app-1")
        self.assertEqual(first.status_code, 201, first.content)
        # The answer is kept at least a day: a repetition 23 hours later gets it once more.
        self.assertGreaterEqual(IDEMPOTENCY_TTL, datetime.timedelta(days=1))
        set_clock(LATER + datetime.timedelta(hours=23))
        again = self.app.post(f"{API}/time-entries", body, format="json", HTTP_IDEMPOTENCY_KEY="app-1")
        self.assertEqual((again.status_code, again["Idempotent-Replayed"]), (201, "true"))
        self.assertEqual(again.json(), first.json())
        self.assertEqual(TimeEntry.objects.count(), 1)
        self.assertEqual(IdempotentCall.objects.count(), 1)
        listed = self.app.get(
            f"{API}/time-entries",
            {"person": self.anna.pk, "from": "2027-03-01", "to": "2027-03-31", "page_size": 500},
        ).json()
        self.assertEqual([row["id"] for row in listed["results"]], [first.json()["id"]])
        # ZEI-009: no overlap; ZEI-022: nothing in the future.
        overlap = self.app.post(
            f"{API}/time-entries", self.entry("2027-03-10T11:00:00+01:00", "2027-03-10T13:00:00+01:00"), format="json"
        )
        self.assert_error(overlap, 400, "validation_error")
        future = self.app.post(
            f"{API}/time-entries", self.entry("2027-04-10T08:00:00+02:00", "2027-04-10T09:00:00+02:00"), format="json"
        )
        self.assert_error(future, 400, "validation_error")


class ProtocolApiTests(PacklistApiTestCase):
    """A8: the error format, German messages, no redirects under /api/v1."""

    def test_errors_in_german(self) -> None:
        error = self.assert_error(
            self.admin.post(f"{self.base}/issue", {}, format="json", HTTP_ACCEPT_LANGUAGE="de"), 400, "validation_error"
        )
        self.assertIn("Hake ab, was rausgeht", error["message"])
        self.assertEqual(set(error), {"code", "message", "fields"})
        missing = self.assert_error(APIClient().get(f"{API}/me", HTTP_ACCEPT_LANGUAGE="de"), 401, "not_authenticated")
        self.assertIn("Anmeldedaten", missing["message"])

    def test_no_redirects(self) -> None:
        anonymous = APIClient()
        paths = [
            f"{API}/me",
            f"{API}/me/",
            f"{API}/offline/packlists",
            f"{API}/offline/packlists/",
            self.base,
            f"{self.base}/",
            f"{API}/projects/{self.project.number}/packlists",
            f"{API}/projects/{self.project.number.removeprefix('P-')}/packlists",
            f"{API}/projects/P-{self.project.number}/packlists",
            f"{API}/time-entries",
            f"{API}/docs",
        ]
        for path in paths:
            for client in (self.admin, anonymous):
                answer = client.get(path)
                self.assertFalse(300 <= answer.status_code < 400, f"{path}: {answer.status_code}")
        self.assertFalse(300 <= self.admin.post(f"{self.base}/sync/", {}, format="json").status_code < 400)


class DateHeaderApiTests(LiveServerTestCase):
    """A8 (APP-005): every answer has a ``Date`` header – from the server in front of the app, here the test server."""

    def setUp(self) -> None:
        super().setUp()
        install_defaults()
        numbering.reset_cache()
        settings = SystemSettings.load()
        settings.setup_completed = True
        settings.save()
        _token, self.key = ApiToken.create_for_user(make_user("anna", superuser=True), "test")

    def ask(self, method: str, path: str, *, key: str | None = None, body: Any = None) -> http.client.HTTPResponse:
        address = urllib.parse.urlparse(self.live_server_url)
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=30)
        headers = {"Accept-Language": "de", "Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        answer = connection.getresponse()
        answer.read()
        connection.close()
        return answer

    def test_every_answer(self) -> None:
        for method, path, key, status in (
            ("GET", f"{API}/me", self.key, 200),
            ("GET", f"{API}/me", None, 401),
            ("GET", f"{API}/offline/packlists", self.key, 200),
            ("GET", f"{API}/projects/999999/packlists/1", self.key, 404),
            ("POST", f"{API}/projects/999999/packlists/1/sync", self.key, 404),
            ("GET", f"{API}/docs", self.key, 200),
        ):
            answer = self.ask(method, path, key=key, body={} if method == "POST" else None)
            self.assertEqual(answer.status, status, path)
            self.assertTrue(answer.getheader("Date"), path)


# --- B, C: the packlists on the phone and the sync (PCK-026, PCK-027) ------------------------------------------


class OfflinePacklistsApiTests(PacklistApiTestCase):
    """C1: the confirmed projects that are not finished, by the rule of opening a packlist."""

    def setUp(self) -> None:
        super().setUp()
        self.option = make_project("Option", status=ProjectStatus.OPTION)
        self.inquiry = make_project("Anfrage", status=ProjectStatus.INQUIRY)
        self.open_items = make_project("Klärung offen", status=ProjectStatus.CONFIRMED_OPEN)
        self.out = make_project("Unterwegs", start=at(1), end=at(5))
        self.out.status = ProjectStatus.OUT
        self.out.save()
        self.closed = make_project("Abgeschlossen")
        self.closed.status = ProjectStatus.CLOSED
        self.closed.save()

    def listed(self, client: APIClient) -> dict[int, dict[str, Any]]:
        answer = client.get(f"{API}/offline/packlists")
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertIn("server_time", answer.json())
        return {project["id"]: project for project in answer.json()["projects"]}

    def test_the_warehouse_takes_every_confirmed_project(self) -> None:
        listed = self.listed(self.client_for("luka", "Lager", allowed_modules=["packing", "projects", "time_tracking"]))
        self.assertEqual(set(listed), {self.project.pk, self.open_items.pk, self.out.pk})
        project = listed[self.project.pk]
        self.assertEqual(
            {key: project[key] for key in ("number", "name", "status", "customer", "can_write")},
            {
                "number": self.project.number,
                "name": "Stadtfest",
                "status": "confirmed",
                "customer": self.project.customer.name,
                "can_write": True,
            },
        )
        self.assertEqual((project["start"], project["end"]), ("2027-03-09T23:00:00Z", "2027-03-11T23:00:00Z"))
        self.assertIn("venue", project)
        self.assertEqual(project["packlists"], self.admin.get(f"{API}/projects/{self.project.pk}/packlists").json())

    def test_crew_takes_its_own_projects_with_the_customers_name(self) -> None:
        """PRJ-122: the name of the customer in every role."""
        anna = make_user("anna", roles=("Freie Kraft",))
        plan(self.project, job_function("Tontechnik"), make_person("Anna Becker", user=anna))
        listed = self.listed(self.client_of(anna, allowed_modules=["packing", "projects", "time_tracking"]))
        self.assertEqual(set(listed), {self.project.pk})
        self.assertEqual(
            (listed[self.project.pk]["customer"], listed[self.project.pk]["can_write"]),
            (self.project.customer.name, False),
        )

    def test_packing_in_assigned_projects_only(self) -> None:
        Role.objects.create(
            name="Packen vor Ort",
            module_levels={"projects": int(Level.READ), "packing": int(Level.WRITE)},
            project_scope="assigned",
        )
        pia = make_user("pia", roles=("Packen vor Ort",))
        ProjectMembership.objects.create(project=self.out, user=pia, level=ProjectAccessLevel.READ)
        listed = self.listed(self.client_of(pia))
        self.assertEqual(set(listed), {self.out.pk})
        self.assertTrue(listed[self.out.pk]["can_write"])
        self.assertEqual(listed[self.out.pk]["customer"], self.out.customer.name)
        # A read-only token writes nowhere.
        self.assertFalse(self.listed(self.client_of(pia, read_only=True))[self.out.pk]["can_write"])

    def test_without_packing_nothing(self) -> None:
        times_only = self.client_for("tim", "Crew", allowed_modules=["time_tracking"])
        self.assert_error(times_only.get(f"{API}/offline/packlists"), 403, "permission_denied")

    def test_packlists_nobody_opened_are_created_in_a_few_queries(self) -> None:
        """PCK-001, NFA-014: the main packlists are there, logged; the list costs the same for 5 and 15 more.

        PCK-026: they come into being when the project is created confirmed, no longer while the
        list is read (tests.unit.test_082_sync.ReadOnlyListTests).
        """
        app = self.client_for("luka", "Lager", allowed_modules=["packing", "projects", "time_tracking"])
        self.listed(app)  # what is looked up once, such as the content types, is looked up now
        counts = []
        for many in (5, 15):
            for index in range(many):
                make_project(f"Neu {many}-{index}")
            with CaptureQueriesContext(connection) as queries:
                listed = self.listed(app)
            counts.append(len(queries))
            self.assertTrue(all(len(project["packlists"]) == 1 for project in listed.values()))
        self.assertEqual(counts[0], counts[1])
        self.assertEqual(Packlist.objects.filter(project__name__startswith="Neu ").count(), 20)
        created = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Packlist), action=AuditAction.CREATED
        )
        self.assertEqual(created.filter(object_repr__startswith="Packliste").count(), Packlist.objects.count())
        # A second call creates nothing more.
        self.listed(app)
        self.assertEqual(Packlist.objects.filter(project__name__startswith="Neu ").count(), 20)


class SyncApiTests(PacklistApiTestCase):
    """C2: the later change counts, per row and quantity; limits as in the browser; invalid input is refused whole."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(at(9, 12))

    def test_applied_older_refused_in_the_order_of_the_request(self) -> None:
        set_clock(at(9, 10))
        self.tick("5")
        set_clock(at(9, 12))
        answer = self.sync(
            self.change("packed", "7", "2027-03-09T11:00:00+01:00"),
            self.change("packed", 2, "2027-03-09T09:00:00+01:00"),
            self.change("packed", "1.00", "2027-03-09T10:00:00+01:00"),  # the same moment as the server: server wins
            self.change("returned", "1", "2027-03-09T11:30:00+01:00"),
            self.change("packed", "1", "2027-03-09T11:30:00+01:00", line=self.rack_line),
        )
        self.assertEqual(answer.status_code, 200, answer.content)
        document = answer.json()
        self.assertEqual(set(document), {"results", "packlist", "server_time"})
        self.assertEqual(
            [(result["line"], result["field"], result["outcome"]) for result in document["results"]],
            [
                (self.cable_line.pk, "packed", "applied"),
                (self.cable_line.pk, "packed", "older"),
                (self.cable_line.pk, "packed", "older"),
                (self.cable_line.pk, "returned", "refused"),
                (self.rack_line.pk, "packed", "applied"),
            ],
        )
        self.assertEqual(document["results"][0]["message"], "")
        self.assertEqual(document["results"][1]["message"], "Auf dem Server gilt eine spätere Änderung.")
        self.assertIn("unterwegs", document["results"][3]["message"])
        rows = self.rows(document["packlist"])
        self.assertEqual(
            (rows["K-005"]["packed"], rows["K-005"]["packed_changed_at"]), ("7.00", "2027-03-09T10:00:00Z")
        )
        # The packlist as GET delivers it.
        current = self.admin.get(self.base).json()
        self.assertEqual(document["packlist"], current)
        self.assertEqual(document["server_time"], "2027-03-09T11:00:00Z")

    def test_the_future_counts_as_now(self) -> None:
        self.sync(self.change("packed", "3", "2027-12-24T18:00:00+01:00"))
        entry = PackEntry.objects.get(line=self.cable_line)
        self.assertEqual(entry.packed_changed_at, at(9, 12))

    def test_return_ticks_from_the_phone_with_the_limits_of_the_partial_return(self) -> None:
        self.tick("6")
        self.admin.post(f"{self.base}/issue", {"only_packed": True}, format="json")
        self.tick("2", field="returned")
        self.admin.post(f"{self.base}/take-back")
        set_clock(at(11, 12))
        answer = self.sync(
            self.change("returned", "1", "2027-03-11T10:00:00+01:00"),  # below what is taken back
            self.change("returned", "7", "2027-03-11T10:01:00+01:00"),  # more than is out
            self.change("returned", "5", "2027-03-11T10:02:00+01:00"),
            self.change("packed", "8", "2027-03-11T10:03:00+01:00"),  # partly issued: the rest is still packed
        ).json()
        self.assertEqual(
            [result["outcome"] for result in answer["results"]], ["refused", "refused", "applied", "applied"]
        )
        rows = self.rows(answer["packlist"])
        self.assertEqual(
            (rows["K-005"]["returned"], rows["K-005"]["taken_back"], rows["K-005"]["packed"]), ("5.00", "2.00", "8.00")
        )

    def test_rights(self) -> None:
        self.assert_error(self.sync(client=self.client_of(self.admin_user, read_only=True)), 403, "permission_denied")
        # Crew packs in its own projects (accounts/0007); a freelancer still only reads the packing list.
        freelancer = make_user("fred", roles=("Freie Kraft",))
        plan(self.project, job_function("Tontechnik"), make_person("Fred Frei", user=freelancer))
        self.assert_error(self.sync(client=self.client_of(freelancer)), 403, "permission_denied")
        crew = make_user("anna", roles=("Crew",))
        plan(self.project, job_function("Tontechnik"), make_person("Anna Becker", user=crew))
        self.assertEqual(self.sync(client=self.client_of(crew)).status_code, 200)
        luka = self.client_for("luka", "Lager", allowed_modules=["packing", "projects", "time_tracking"])
        self.assertEqual(
            self.sync(self.change("packed", "1", "2027-03-09T11:00:00+01:00"), client=luka).status_code, 200
        )
        other = make_project("Weinfest")
        wrong = f"{API}/projects/{other.pk}/packlists/{self.packlist.pk}/sync"
        self.assert_error(self.admin.post(wrong, {"changes": []}, format="json"), 404, "not_found")

    def test_invalid_input_is_refused_as_a_whole(self) -> None:
        good = self.change("packed", "4", "2027-03-09T11:00:00+01:00")
        invalid = [
            self.change("packed", "4", "2027-13-09T11:00:00+01:00"),  # month 13
            self.change("packed", "4", "2027-03-09T25:00:00+01:00"),
            self.change("packed", "4", "2027-03-09T11:00:00"),  # no zone
            self.change("packed", "4", "2027-03-09T11:00:00+25:00"),
            self.change("packed", "4", "0001-01-01T00:00:00+05:00"),
            self.change("packed", "4", "gestern"),
            self.change("packed", "4", 1234567890),
            self.change("packed", "-1", "2027-03-09T11:00:00+01:00"),
            self.change("packed", "1.234", "2027-03-09T11:00:00+01:00"),
            self.change("packed", "NaN", "2027-03-09T11:00:00+01:00"),
            self.change("packed", "Infinity", "2027-03-09T11:00:00+01:00"),
            self.change("packed", "123456789012", "2027-03-09T11:00:00+01:00"),
            self.change("issued", "4", "2027-03-09T11:00:00+01:00"),
            {**good, "line": "zwölf"},
            {**good, "line": True},
            {**good, "line": 10**30},
            {**good, "product": None},
            {key: value for key, value in good.items() if key != "changed_at"},
            "packed",
            None,
        ]
        for change in invalid:
            answer = self.sync(good, change)
            self.assert_error(answer, 400, "validation_error")
        for body in ([good], {"changes": good}, {"changes": None}, {}, "x", {"changes": [good] * 1001}):
            answer = self.admin.post(f"{self.base}/sync", body, format="json")
            self.assertEqual(answer.status_code, 400, body if len(str(body)) < 200 else "1001 changes")
        self.assertEqual(self.admin.post(f"{self.base}/sync", "{", content_type="application/json").status_code, 400)
        self.assertFalse(PackEntry.objects.filter(packed_quantity__gt=0).exists())  # nothing was taken over
        self.assertEqual(self.sync(*[good] * 1000).status_code, 200)

    def test_sync_is_not_taken_for_a_packing_step(self) -> None:
        answer = self.sync()
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json()["results"], [])

    def test_sent_twice_with_the_same_key(self) -> None:
        change = self.change("packed", "4", "2027-03-09T11:00:00+01:00")
        first = self.sync(change, HTTP_IDEMPOTENCY_KEY="sync-1")
        second = self.sync(change, HTTP_IDEMPOTENCY_KEY="sync-1")
        self.assertEqual((second.status_code, second["Idempotent-Replayed"]), (200, "true"))
        self.assertEqual(first.json(), second.json())

    def test_described_in_the_api_description(self) -> None:
        description = self.admin.get(f"{API}/schema?format=json").json()
        self.assertIn("/api/v1/projects/{project_pk}/packlists/{packlist_pk}/sync", description["paths"])
        self.assertIn("/api/v1/offline/packlists", description["paths"])


# --- D: tokens do not open more than they have (AUT-021) -------------------------------------------------------


class TokenLimitApiTests(ApiTestCase):
    """D1 to D3: a token limited to modules creates no tokens and sees only itself; one with an expiry lives no longer."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_user("anna", roles=("Projektleitung",))
        self.other, _key = ApiToken.create_for_user(self.anna, "Laptop")

    def token(self, **options: Any) -> tuple[ApiToken, APIClient]:
        token, key = ApiToken.create_for_user(self.anna, "App", **options)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
        return token, client

    def test_a_token_limited_to_modules(self) -> None:
        token, app = self.token(allowed_modules=["packing", "projects", "time_tracking"])
        error = self.assert_error(app.post(f"{API}/tokens", {"name": "Neu"}, format="json"), 403, "permission_denied")
        self.assertIn("beschränktes Token", error["message"])
        self.assertEqual(ApiToken.objects.filter(user=self.anna).count(), 2)
        self.assertEqual([row["id"] for row in app.get(f"{API}/tokens").json()["results"]], [token.pk])
        self.assertEqual(app.delete(f"{API}/tokens/{self.other.pk}").status_code, 404)
        self.other.refresh_from_db()
        self.assertIsNone(self.other.revoked_at)
        self.assertEqual(app.delete(f"{API}/tokens/{token.pk}").status_code, 204)

    def test_a_token_with_an_expiry(self) -> None:
        _token, app = self.token(expires_at=at(30))
        later = app.post(f"{API}/tokens", {"name": "Neu", "expires_at": "2027-04-30T00:00:00+02:00"}, format="json")
        self.assert_error(later, 400, "validation_error", field="expires_at")
        self.assert_error(
            app.post(f"{API}/tokens", {"name": "Neu"}, format="json"), 400, "validation_error", "expires_at"
        )
        earlier = app.post(f"{API}/tokens", {"name": "Neu", "expires_at": "2027-03-20T00:00:00+01:00"}, format="json")
        self.assertEqual(earlier.status_code, 201, earlier.content)
        # It still sees all tokens of its user.
        self.assertEqual(len(app.get(f"{API}/tokens").json()["results"]), 3)

    def test_an_unlimited_token_and_the_session_stay_as_they_were(self) -> None:
        _token, app = self.token()
        self.assertEqual(app.post(f"{API}/tokens", {"name": "Neu"}, format="json").status_code, 201)
        _token, reader = self.token(read_only=True)
        self.assert_error(reader.post(f"{API}/tokens", {"name": "Neu"}, format="json"), 403, "permission_denied")


# --- PCK-028: the return per piece through the API -------------------------------------------------------------


class PartialReturnApiTests(PacklistApiTestCase):
    """Tick back, book with ``take-back``; issue the rest meanwhile; what came back stays done."""

    def test_the_example(self) -> None:
        self.tick("6")
        self.assertEqual(self.admin.post(f"{self.base}/issue", format="json").json()["status"], "partly_issued")
        ticked = self.tick("4", field="returned").json()
        self.assertEqual(
            (self.rows(ticked)["K-005"]["returned"], ticked["ready_to_take_back"], ticked["taken_back"]),
            ("4.00", "4.00", "0.00"),
        )
        booked = self.admin.post(f"{self.base}/take-back").json()
        row = self.rows(booked)["K-005"]
        self.assertEqual((row["taken_back"], row["still_out"], booked["not_issued"]), ("4.00", "2.00", "5.00"))
        self.assertEqual(
            booked["bar"], {"back": "4.00", "ticked_back": "0.00", "out": "2.00", "packed": "0.00", "in_stock": "5.00"}
        )
        self.assertEqual(self.tick("1", field="returned").json()["sections"][0]["rows"][0]["returned"], "4.00")
        again = self.admin.post(f"{self.base}/take-back")
        self.assert_error(again, 400, "validation_error")
        self.tick("10")
        self.admin.patch(
            f"{self.base}/rows",
            {"line": self.rack_line.pk, "product": self.rack_product.pk, "packed": "1"},
            format="json",
        )
        issued = self.admin.post(f"{self.base}/issue", format="json").json()
        self.assertEqual((issued["status"], self.rows(issued)["K-005"]["still_out"]), ("issued", "6.00"))
        self.admin.post(f"{self.base}/return-all")
        done = self.admin.post(f"{self.base}/take-back").json()
        self.assertEqual(done["status"], "returned")
        self.assertEqual(Packlist.objects.get(pk=self.packlist.pk).project.status, ProjectStatus.RETURNED)
