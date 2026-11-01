# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of stage 4 outside a single project.

Calendar and utilization (PRJ-028, VFG-012), personnel plan (VFG-014),
notifications (UIX-005), sessions and two-factor login (AUT-006, AUT-008),
security log (AUT-022) and self-check (NFA-037).
"""

from __future__ import annotations

from django.test import Client

from rentalars.accounts import twofactor
from rentalars.accounts.models import Role, SecurityEvent, UserSession
from rentalars.notifications.models import Kind
from rentalars.notifications.services import notify
from rentalars.personnel.models import Absence
from rentalars.projects.models import ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import PASSWORD, add_line, at, make_person, make_project, make_stock, make_user, plan


class CalendarApiTests(ApiTestCase):
    """PRJ-028: the projects of a span, with their phases."""

    def test_projects_of_the_span(self) -> None:
        march = make_project("Stadtfest")
        make_project("Sommerfest", start=at(10, month=7), end=at(12, month=7))
        make_project("Abgesagt", status=ProjectStatus.CANCELLED)
        self.admin.post(
            f"{API}/projects/{march.pk}/phases",
            {"kind": "setup", "start": "2027-03-10T08:00:00+01:00", "end": "2027-03-10T18:00:00+01:00"},
            format="json",
        )
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-08", "weeks": 1}).json()
        self.assertEqual([row["name"] for row in rows], ["Stadtfest"])
        self.assertEqual([phase["kind"] for phase in rows[0]["phases"]], ["setup"])
        with_cancelled = self.admin.get(f"{API}/calendar", {"from": "2027-03-08", "weeks": 1, "all": "1"}).json()
        self.assertEqual(len(with_cancelled), 2)

    def test_only_visible_projects_are_shown(self) -> None:
        """AUT-016: crew sees only their own projects in the calendar too."""
        make_project("Stadtfest")
        own = make_project("Weinfest")
        ben = make_user("ben", roles=("Crew",))
        plan(own, "Stagehand", make_person("Ben Schmidt", user=ben))
        rows = self.client_of(ben).get(f"{API}/calendar", {"from": "2027-03-08"}).json()
        self.assertEqual([row["name"] for row in rows], ["Weinfest"])

    def test_a_wrong_date_is_an_error(self) -> None:
        self.assert_error(self.admin.get(f"{API}/calendar", {"from": "8.3.2027"}), 400, "validation_error", "from")


class UtilizationApiTests(ApiTestCase):
    """VFG-012: how much of a product is reserved, day by day."""

    def test_reserved_quantity_per_day(self) -> None:
        speaker = make_stock("L-001", 10, "Topteil")
        add_line(make_project("Stadtfest"), speaker, 6)
        add_line(make_project("Option", status=ProjectStatus.OPTION), speaker, 5)
        rows = self.admin.get(f"{API}/utilization", {"product": speaker.pk, "from": "2027-03-09", "weeks": 1}).json()
        (row,) = rows
        days = {day["day"]: day for day in row["days"]}
        self.assertEqual((days["2027-03-09"]["firm"], days["2027-03-09"]["level"]), (0, "free"))
        self.assertEqual(
            (days["2027-03-10"]["firm"], days["2027-03-10"]["optional"], days["2027-03-10"]["stock"]), (6, 5, 10)
        )
        self.assertEqual(days["2027-03-10"]["level"], "tight")

    def test_products_or_a_category_must_be_chosen(self) -> None:
        self.assert_error(self.admin.get(f"{API}/utilization"), 400, "validation_error", "product")

    def test_not_for_accounts_limited_to_their_projects(self) -> None:
        """The figures sum up every project; crew must not learn about the others."""
        self.assert_error(
            self.client_for("ben", "Crew").get(f"{API}/utilization", {"product": 1}), 403, "permission_denied"
        )


class PersonnelPlanApiTests(ApiTestCase):
    """VFG-014: deployments and absences of every person; double bookings are marked."""

    def test_deployments_absences_and_conflicts(self) -> None:
        anna = make_person("Anna Becker")
        # VFG-023: only people who can be planned are listed – Ben has a job function, Carla none.
        ben = make_person("Ben Schmidt", rates={"Stagehand": "20.00"})
        make_person("Carla Wolf")
        plan(make_project("Stadtfest"), "Stagehand", anna, start=at(10, 8), end=at(10, 18))
        plan(make_project("Weinfest"), "Stagehand", anna, start=at(10, 14), end=at(10, 22))
        Absence.objects.create(person=ben, kind="vacation", start=at(9), end=at(12))
        rows = self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-08", "weeks": 1, "busy": "1"}).json()
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(sorted(by_name), ["Anna Becker", "Ben Schmidt"])
        self.assertTrue(by_name["Anna Becker"]["conflict"])
        self.assertEqual([entry["type"] for entry in by_name["Ben Schmidt"]["entries"]], ["absence"])
        self.assertFalse(by_name["Ben Schmidt"]["conflict"])

    def test_needs_the_personnel_module(self) -> None:
        self.assert_error(self.client_for("ben", "Crew").get(f"{API}/personnel-plan"), 403, "permission_denied")


class NotificationApiTests(ApiTestCase):
    """UIX-005: notifications in the application, and which ones by e-mail."""

    def test_list_read_and_preferences(self) -> None:
        ben = make_user("ben")
        client = self.client_of(ben)
        notify([ben], Kind.SHORTAGE, "Engpass: Topteil", url="/projects/1/")
        notify([ben], Kind.DEFECT, "Defekt: Kabel")
        listed = client.get(f"{API}/notifications").json()
        self.assertEqual((listed["count"], listed["unread"]), (2, 2))
        first = listed["results"][0]
        marked = client.post(f"{API}/notifications/read", {"ids": [first["id"]]}, format="json").json()
        self.assertEqual((marked["marked"], marked["unread"]), (1, 1))
        self.assertEqual(client.get(f"{API}/notifications", {"unread": "1"}).json()["count"], 1)
        self.assertEqual(client.post(f"{API}/notifications/read", {}, format="json").json()["unread"], 0)

        preferences = {row["kind"]: row for row in client.get(f"{API}/notifications/preferences").json()}
        self.assertTrue(preferences["shortage"]["by_email"])
        self.assertFalse(preferences["project_change"]["by_email"])
        changed = client.put(
            f"{API}/notifications/preferences",
            [{"kind": "shortage", "in_app": True, "by_email": False}],
            format="json",
        ).json()
        self.assertFalse({row["kind"]: row for row in changed}["shortage"]["by_email"])
        notify([ben], Kind.SHORTAGE, "Engpass: Kabel")
        from django.core import mail

        self.assertEqual([message.subject for message in mail.outbox if "Kabel" in message.subject], [])

    def test_everybody_sees_only_their_own(self) -> None:
        notify([self.admin_user], Kind.DEFECT, "Defekt")
        other = self.client_for("ben")
        self.assertEqual(other.get(f"{API}/notifications").json()["count"], 0)
        self.assertEqual(other.post(f"{API}/notifications/read", {}, format="json").json()["marked"], 0)


class SessionApiTests(ApiTestCase):
    """AUT-008: users see where they are logged in and end sessions elsewhere."""

    def test_list_and_end_a_session(self) -> None:
        ben = make_user("ben")
        laptop, phone = Client(HTTP_USER_AGENT="Laptop"), Client(HTTP_USER_AGENT="Phone")
        laptop.force_login(ben)
        phone.force_login(ben)
        api = self.client_of(ben)
        sessions = api.get(f"{API}/me/sessions").json()
        self.assertEqual(len(sessions), 2)
        phone_session = UserSession.objects.get(session_key=phone.session.session_key)
        self.assertEqual(api.delete(f"{API}/me/sessions/{phone_session.pk}").status_code, 204)
        self.assertEqual(len(api.get(f"{API}/me/sessions").json()), 1)
        self.assertEqual(phone.get("/").status_code, 302)  # logged out
        self.assertTrue(SecurityEvent.objects.filter(kind="session_ended", user=ben).exists())

    def test_sessions_of_others_are_not_found(self) -> None:
        ben = make_user("ben")
        Client().force_login(ben)
        session = UserSession.objects.get(user=ben)
        self.assert_error(self.admin.delete(f"{API}/me/sessions/{session.pk}"), 404, "not_found")


class TwoFactorApiTests(ApiTestCase):
    """AUT-006: login with a code; administrators can switch it off for a lost phone."""

    def setUp(self) -> None:
        super().setUp()
        self.ben = make_user("ben")
        self.secret = twofactor.new_secret()
        self.step = twofactor.current_step()
        twofactor.enable(self.ben, self.secret, twofactor.code_at(self.secret, self.step))

    def login(self, **extra: str) -> object:
        return Client().post(
            f"{API}/auth/login", {"username": "ben", "password": PASSWORD, **extra}, content_type="application/json"
        )

    def test_wrong_codes_lock_the_name_like_wrong_passwords(self) -> None:
        """AUT-005: whoever knows the password cannot guess the code without end."""
        for _attempt in range(5):
            self.assertEqual(self.login(code="000000").json()["error"]["code"], "invalid_code")
        locked = self.login(code="000000")
        self.assertEqual((locked.status_code, locked.json()["error"]["code"]), (429, "locked_out"))
        # Not even the right code opens the door now, and another spelling of the name does not help.
        right = self.login(code=twofactor.code_at(self.secret, self.step + 1))
        self.assertEqual(right.status_code, 429)

    def test_a_right_password_does_not_clear_the_wrong_codes(self) -> None:
        """Each try with the password and a wrong code counts; the right password in between is no success."""
        for _attempt in range(4):
            self.login(code="000000")
            self.login()  # password right, no code yet
        self.login(code="000000")
        self.assertEqual(self.login(code="000000").status_code, 429)

    def test_login_needs_the_code(self) -> None:
        self.assertEqual(self.login().json()["error"]["code"], "code_required")
        self.assertEqual(self.login(code="000000").json()["error"]["code"], "invalid_code")
        response = self.login(code=twofactor.code_at(self.secret, self.step + 1))
        self.assertEqual(response.status_code, 200)
        # The same code does not work a second time.
        self.assertEqual(
            self.login(code=twofactor.code_at(self.secret, self.step + 1)).json()["error"]["code"], "invalid_code"
        )

    def test_an_administrator_resets_the_second_factor(self) -> None:
        response = self.admin.post(f"{API}/users/{self.ben.pk}/reset-two-factor")
        self.assertEqual(response.status_code, 200, response.data)
        self.ben.refresh_from_db()
        self.assertFalse(self.ben.has_two_factor)
        self.assertEqual(self.login().status_code, 200)

    def test_a_required_second_factor_must_be_set_up_first(self) -> None:
        role = Role.objects.create(name="Streng", requires_two_factor=True)
        anna = make_user("anna", roles=(role.name,))
        response = Client().post(
            f"{API}/auth/login", {"username": anna.username, "password": PASSWORD}, content_type="application/json"
        )
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (403, "two_factor_setup_required"))


class SecurityLogApiTests(ApiTestCase):
    """AUT-022: logins and failed logins are logged; administrators read the log."""

    def test_read_the_log(self) -> None:
        make_user("ben")
        Client().post(f"{API}/auth/login", {"username": "ben", "password": "wrong"}, content_type="application/json")
        Client().post(f"{API}/auth/login", {"username": "ben", "password": PASSWORD}, content_type="application/json")
        log = self.admin.get(f"{API}/security-log").json()
        self.assertEqual([row["kind"] for row in log["results"]], ["login", "login_failed"])
        failed = self.admin.get(f"{API}/security-log", {"kind": "login_failed"}).json()["results"]
        self.assertEqual(failed[0]["identifier"], "ben")

    def test_only_for_the_administration(self) -> None:
        self.assert_error(self.client_for("ben", "Projektleitung").get(f"{API}/security-log"), 403, "permission_denied")


class SelfCheckApiTests(ApiTestCase):
    """NFA-037: the state of the installation, also for monitoring."""

    def test_run_the_checks(self) -> None:
        report = self.admin.get(f"{API}/self-check").json()
        self.assertIn(report["state"], {"ok", "note", "warning", "error"})
        groups = {finding["group"] for finding in report["findings"]}
        self.assertIn("Datenbank", groups)

    def test_only_for_the_administration(self) -> None:
        self.assert_error(self.client_for("ben", "Lager").get(f"{API}/self-check"), 403, "permission_denied")
