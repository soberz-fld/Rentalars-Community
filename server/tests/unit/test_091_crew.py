# SPDX-License-Identifier: GPL-3.0-or-later
"""Several crew lines at once (PRJ-117), planned firmly without request (PER-041), and the person is told
(PRJ-118).

The requirement: in Project → Planning, multiple selection for personnel as well, to set e.g. the meeting point or
other values for several lines at once; personnel can also be planned firmly, without a request; the person concerned
is notified of these changes.

* Crew lines are ticked like material lines; the bar sets values (dialog), plans firmly, asks or deletes – page and
  API (``POST /projects/{id}/crew-lines/bulk``) through ``projects.crew_bulk`` (PRJ-117).
* "Planned firmly" counts like an accepted request and is never asked again: new times are told instead (PER-041).
* The person is told – planned firmly, times, meeting point, note, phase …, taken off – once per action, never
  about their own change, never without an active account (PRJ-118).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.core.audit import acting_as
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import course, crew
from rentalars.projects.crew_bulk import CrewBulkAction, change_crew_lines
from rentalars.projects.models import CrewLine, ProjectStatus, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, make_person, make_project, make_user, plan, set_clock
from tests.ui.base import UiTestCase


def notices(person: object, kind: str = Kind.DEPLOYMENT_CHANGE) -> list[Notification]:
    """The notifications of one kind a person got, oldest first."""
    return list(Notification.objects.filter(user=person.user, kind=kind).order_by("id"))


class CrewTestCase(RentalarsTestCase):
    """A confirmed project from 10 to 12 March with Anna, Tom and an open place."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Tontechnik": "30.00", "Stagehand": "18.00"})
        self.line = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))


class FirmPlanningTests(CrewTestCase):
    """A person planned firmly, without request (PER-041; PER-016)."""

    def test_planned_firmly_when_added_and_told_once(self) -> None:
        line = plan(self.project, "Tontechnik", self.tom, start=at(11, 8), end=at(11, 18), firm=True)
        self.assertEqual(line.request_status, RequestStatus.FIRM)
        self.assertEqual((line.requested_start, line.requested_end), (at(11, 8), at(11, 18)))
        self.assertTrue(line.is_confirmed)
        self.assertFalse(line.times_changed_since_request)
        (told,) = notices(self.tom)
        self.assertTrue(told.title.startswith("Fest eingeplant: "), told.title)
        self.assertIn("Tontechnik", told.title)
        self.assertEqual(told.url, reverse("projects:deployment", args=[self.project.pk]))
        self.assertEqual(notices(self.tom, Kind.DEPLOYMENT_REQUEST), [])
        self.assertEqual(line.get_request_status_display(), "fest eingeplant")

    def test_an_open_place_is_not_planned_firmly(self) -> None:
        with self.assertRaises(ValidationError):
            plan(self.project, "Tontechnik", None, firm=True)
        place = plan(self.project, "Tontechnik", None)
        with self.assertRaises(ValidationError):
            crew.update_crew_line(place, rights=ALL_RIGHTS, firm=True)

    def test_new_times_of_a_firm_line_are_told_not_asked(self) -> None:
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, firm=True)
        Notification.objects.all().delete()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, start=at(10, 10))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.FIRM)  # PER-034 does not ask a firm line again
        self.assertEqual(self.line.requested_start, at(10, 10))
        self.assertFalse(self.line.times_changed_since_request)
        self.assertEqual(notices(self.anna, Kind.DEPLOYMENT_REQUEST), [])
        (told,) = notices(self.anna)
        self.assertTrue(told.title.startswith("Einsatz geändert: "), told.title)
        self.assertIn("Neue Zeiten: Mi 10.03. 10:00 – Mi 10.03. 18:00 (vorher: Mi 10.03. 08:00", told.body)

    def test_a_firm_line_moved_with_its_phase_is_told(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(10, 8), end=at(10, 18))
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, phase=phase, firm=True)
        other = plan(self.project, "Tontechnik", self.tom, phase=phase)
        crew.request_deployment(other, user=None)
        Notification.objects.all().delete()
        course.update_phase(phase, move_crew=True, start=at(10, 9), end=at(10, 19))
        self.line.refresh_from_db()
        self.assertEqual((self.line.start, self.line.request_status), (at(10, 9), RequestStatus.FIRM))
        self.assertEqual(len(notices(self.anna)), 1)
        self.assertEqual(notices(self.anna, Kind.DEPLOYMENT_REQUEST), [])
        # Tom was asked: asked again (PER-034) – that request is his one message.
        self.assertEqual(len(notices(self.tom, Kind.DEPLOYMENT_REQUEST)), 1)
        self.assertEqual(notices(self.tom), [])

    def test_an_accepted_line_stays_accepted(self) -> None:
        crew.request_deployment(self.line, user=None)
        crew.answer_deployment(self.line, accept=True, user=None)
        Notification.objects.all().delete()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, firm=True)
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)
        self.assertEqual(notices(self.anna), [])

    def test_taken_back_the_line_can_be_asked(self) -> None:
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, firm=True)
        with self.assertRaises(ValidationError):
            crew.request_deployment(self.line, user=None)  # firm: nothing to ask
        with self.assertRaises(ValidationError):
            crew.answer_deployment(self.line, accept=False, user=None)  # nor to answer
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, firm=False)
        self.assertEqual((self.line.request_status, self.line.requested_start), (RequestStatus.NONE, None))
        self.assertTrue(crew.request_deployment(self.line, user=None))
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)

    def test_firm_counts_in_my_deployments(self) -> None:
        from rentalars.projects.my_deployments import _request_badge

        crew.update_crew_line(self.line, rights=ALL_RIGHTS, firm=True)
        self.assertIn("green", str(_request_badge(self.line)))
        client = self.client
        client.force_login(self.anna.user)
        page = client.get(reverse("projects:my_deployments"), {"request": "firm"}).content.decode()
        self.assertIn("fest eingeplant", page)
        self.assertIn("Stadtfest", page)


class ChangeNoticeTests(CrewTestCase):
    """What the person is told about a change of their line – and what not (PRJ-118)."""

    def test_one_notification_for_several_fields(self) -> None:
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Tor 1")
        Notification.objects.all().delete()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Halle 3", note="Schwarze Kleidung")
        (told,) = notices(self.anna)
        self.assertIn("Treffpunkt: Halle 3 (vorher: Tor 1)", told.body)
        self.assertIn("Neue Notiz: Schwarze Kleidung", told.body)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="")
        self.assertIn("Treffpunkt entfernt (vorher: Halle 3)", notices(self.anna)[-1].body)

    def test_hours_prices_and_rates_are_not_told(self) -> None:
        crew.update_crew_line(
            self.line, rights=ALL_RIGHTS, planned_hours=Decimal("6"), unit_price=Decimal("50"), hourly_rate=Decimal("1")
        )
        self.assertEqual(notices(self.anna), [])

    def test_a_person_changing_their_own_line_is_not_told(self) -> None:
        with acting_as(self.anna.user):
            crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Halle 3")
        self.assertEqual(notices(self.anna), [])

    def test_taken_off_by_deleting_or_by_another_person(self) -> None:
        other = plan(self.project, "Tontechnik", self.tom, start=at(11, 8), end=at(11, 18))
        crew.update_crew_line(other, rights=ALL_RIGHTS, person=self.anna)
        (told,) = notices(self.tom)
        self.assertTrue(told.title.startswith("Nicht mehr eingeplant: "), told.title)
        self.assertEqual(told.url, reverse("projects:my_deployments"))
        self.assertEqual(notices(self.anna), [])  # put on a line, not asked yet: nothing to tell
        crew.delete_crew_line(self.line)
        self.assertTrue(notices(self.anna)[-1].title.startswith("Nicht mehr eingeplant: "))

    def test_declined_over_and_cancelled_are_not_told(self) -> None:
        crew.request_deployment(self.line, user=None)
        crew.answer_deployment(self.line, accept=False, user=None)
        Notification.objects.all().delete()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Halle 3")
        crew.delete_crew_line(self.line)
        self.assertEqual(notices(self.anna), [])
        # A deployment that is over: corrections after the event concern nobody any more.
        past = plan(self.project, "Tontechnik", self.tom, start=at(10, 8), end=at(10, 18))
        set_clock(at(13, 8))
        crew.update_crew_line(past, rights=ALL_RIGHTS, meeting_point="Halle 3")
        self.assertEqual(notices(self.tom), [])
        set_clock(at(1, 8))
        self.project.status = ProjectStatus.CANCELLED
        self.project.save()
        crew.update_crew_line(past, rights=ALL_RIGHTS, meeting_point="Halle 4")
        self.assertEqual(notices(self.tom), [])

    def test_without_an_active_account_nobody_is_told(self) -> None:
        user = self.anna.user
        user.is_active = False
        user.save()
        self.line.refresh_from_db()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Halle 3")
        self.assertEqual(Notification.objects.filter(kind=Kind.DEPLOYMENT_CHANGE).count(), 0)

    def test_asked_again_the_request_names_the_other_changes(self) -> None:
        crew.request_deployment(self.line, user=None)
        crew.answer_deployment(self.line, accept=True, user=None)
        Notification.objects.all().delete()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, start=at(10, 9), meeting_point="Halle 3")
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)  # PER-034
        self.assertEqual(notices(self.anna), [])
        (request,) = notices(self.anna, Kind.DEPLOYMENT_REQUEST)
        self.assertIn("Neue Zeiten", request.body)
        self.assertIn("Treffpunkt: Halle 3", request.body)

    def test_the_kind_has_its_category_and_goes_to_the_phone(self) -> None:
        from rentalars.notifications.categories import Category, category_of
        from rentalars.notifications.services import choice

        self.assertEqual(category_of(Kind.DEPLOYMENT_CHANGE), Category.PROJECT)
        self.assertEqual(choice(self.anna.user, Kind.DEPLOYMENT_CHANGE), (True, True, True))


class BulkServiceTests(CrewTestCase):
    """``crew_bulk.change_crew_lines``: one action, each line through the service for a single line (PRJ-117)."""

    def setUp(self) -> None:
        super().setUp()
        self.second = plan(self.project, "Tontechnik", self.anna, start=at(11, 8), end=at(11, 18))
        self.toms = plan(self.project, "Stagehand", self.tom, start=at(10, 8), end=at(10, 18))
        self.place = plan(self.project, "Stagehand", None)
        self.all_ids = [self.line.pk, self.second.pk, self.toms.pk, self.place.pk]

    def change(self, action: str, ids: list[int] | None = None, **values: object) -> object:
        return change_crew_lines(self.project, ids or self.all_ids, action, rights=ALL_RIGHTS, user=None, values=values)

    def test_meeting_point_for_all_one_notification_per_person(self) -> None:
        result = self.change(CrewBulkAction.EDIT, meeting_point="Halle 3")
        self.assertEqual(sorted(result.changed_ids), sorted(self.all_ids))
        self.assertEqual(set(CrewLine.objects.values_list("meeting_point", flat=True)), {"Halle 3"})
        (told,) = notices(self.anna)
        self.assertTrue(told.title.startswith("2 Einsätze geändert: "), told.title)
        self.assertEqual(told.body.count("Treffpunkt: Halle 3"), 2)
        self.assertEqual(len(notices(self.tom)), 1)
        # The same again: nothing changes, nobody is told.
        result = self.change(CrewBulkAction.EDIT, meeting_point="Halle 3")
        self.assertEqual((result.changed, len(result.unchanged)), ([], 4))
        self.assertEqual(Notification.objects.filter(kind=Kind.DEPLOYMENT_CHANGE).count(), 2)

    def test_a_refused_line_is_named_and_its_person_not_told(self) -> None:
        # Until 11 March 12:00 – the line of the 11th would end before it starts.
        result = self.change(CrewBulkAction.EDIT, end=at(11, 7))
        self.assertEqual([skipped.line.pk for skipped in result.skipped], [self.second.pk])
        self.assertIn("Ende", result.skipped[0].reason)
        self.assertEqual(result.skipped[0].label, f"{self.second.title} – Anna Becker")
        self.second.refresh_from_db()
        self.assertEqual(self.second.end, at(11, 18))
        (told,) = notices(self.anna)  # only about the line that changed
        self.assertTrue(told.title.startswith("Einsatz geändert: "), told.title)

    def test_a_phase_brings_its_period(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(10, 6), end=at(10, 12))
        self.change(CrewBulkAction.EDIT, [self.line.pk, self.toms.pk], phase=phase)
        self.line.refresh_from_db()
        self.assertEqual((self.line.phase, self.line.start, self.line.end), (phase, at(10, 6), at(10, 12)))
        self.assertIn("Phase: Aufbau", notices(self.anna)[0].body)
        self.change(CrewBulkAction.EDIT, [self.line.pk], phase=None)
        self.line.refresh_from_db()
        self.assertEqual((self.line.phase, self.line.start), (None, at(10, 6)))

    def test_plan_firmly(self) -> None:
        crew.request_deployment(self.toms, user=None)
        crew.answer_deployment(self.toms, accept=True, user=None)
        Notification.objects.all().delete()
        result = self.change(CrewBulkAction.FIRM)
        self.assertEqual(sorted(result.changed_ids), sorted([self.line.pk, self.second.pk]))
        self.assertEqual([line.pk for line in result.unchanged], [self.toms.pk])
        self.assertEqual(
            [(skipped.line.pk, skipped.reason) for skipped in result.skipped],
            [(self.place.pk, "ist ein offener Platz")],
        )
        (told,) = notices(self.anna)
        self.assertTrue(told.title.startswith("Fest eingeplant für 2 Einsätze: "), told.title)
        self.assertEqual(notices(self.tom), [])

    def test_ask(self) -> None:
        crew.update_crew_line(self.toms, rights=ALL_RIGHTS, firm=True)
        crew.request_deployment(self.second, user=None)
        Notification.objects.all().delete()
        result = self.change(CrewBulkAction.ASK)
        self.assertEqual(result.changed_ids, [self.line.pk])
        self.assertEqual([line.pk for line in result.unchanged], [self.second.pk])  # asked for these times already
        self.assertEqual(
            sorted((skipped.line.pk, skipped.reason) for skipped in result.skipped),
            sorted([(self.toms.pk, "ist fest eingeplant"), (self.place.pk, "ist ein offener Platz")]),
        )
        self.assertEqual(len(notices(self.anna, Kind.DEPLOYMENT_REQUEST)), 1)

    def test_delete(self) -> None:
        result = self.change(CrewBulkAction.DELETE, [self.line.pk, self.second.pk, self.place.pk])
        self.assertEqual(len(result.changed), 3)
        self.assertEqual(list(self.project.crew_lines.all()), [self.toms])
        (told,) = notices(self.anna)
        self.assertTrue(told.title.startswith("Nicht mehr eingeplant für 2 Einsätze: "), told.title)

    def test_refused_requests(self) -> None:
        with self.assertRaises(ValidationError):
            self.change("optional")
        with self.assertRaises(ValidationError):
            self.change(CrewBulkAction.EDIT)  # nothing to set
        with self.assertRaises(ValidationError):
            change_crew_lines(
                make_project("Anderes"), self.all_ids, CrewBulkAction.DELETE, rights=ALL_RIGHTS, user=None
            )
        from rentalars.accounts.rights import Rights

        with self.assertRaises(ValidationError):  # AUT-019: the discount needs the price right
            change_crew_lines(
                self.project,
                self.all_ids,
                CrewBulkAction.EDIT,
                rights=Rights(module_levels={"projects": 3}),
                user=None,
                values={"discount_percent": Decimal("5")},
            )
        self.assertEqual(CrewLine.objects.filter(discount_percent=5).count(), 0)


class CrewPageTests(UiTestCase):
    """The block "Personal" of the planning: boxes, bar, dialog – with and without page script (PRJ-117, PER-041)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        self.line = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))
        self.toms = plan(self.project, "Tontechnik", self.tom, start=at(11, 8), end=at(11, 18))
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.bulk = reverse("projects:crew_bulk", args=[self.project.pk])
        self.edit = reverse("projects:crew_bulk_edit", args=[self.project.pk])

    def test_boxes_and_bar(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn(f'name="crew_lines" value="{self.line.pk}" form="crew-selection"', page)
        self.assertIn('data-check-all="crew_lines"', page)
        self.assertIn('id="crew-selection"', page)
        self.assertIn('data-bulk-bar="crew_lines"', page)
        for label in ("Werte setzen …", "Fest einplanen", "Anfragen", "Alle Personalpositionen auswählen"):
            self.assertIn(label, page)
        self.assertIn("Fest eingeplant (ohne Anfrage)", page)  # the add form
        self.assertIn("fest einplanen", page)  # each line
        self.assertNotIn("Für das ganze Projekt, in keiner Teilgruppe", page)
        # Who only reads the project chooses nothing.
        page = self.assert_ok(self.browser_for("nora", "Nur-Lesen").get(self.detail))
        self.assertNotIn('name="crew_lines"', page)
        self.assertNotIn('id="crew-selection"', page)

    def test_plan_firmly_with_the_page_script(self) -> None:
        response = self.htmx("post", self.bulk, {"crew_lines": [self.line.pk, self.toms.pk], "action": "firm"})
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("2 Personalpositionen fest eingeplant", text)
        self.assertIn("fest eingeplant", text)
        self.assertEqual(set(CrewLine.objects.values_list("request_status", flat=True)), {RequestStatus.FIRM})
        self.assertEqual(Notification.objects.filter(kind=Kind.DEPLOYMENT_CHANGE).count(), 2)

    def test_without_the_page_script(self) -> None:
        response = self.client.post(self.bulk, {"crew_lines": [self.line.pk], "action": "delete"})
        self.assertRedirects(response, f"{self.detail}#planning-crew", fetch_redirect_response=False)
        page = self.client.get(self.detail)
        self.assertIn("1 Personalposition gelöscht.", self.messages_of(page))
        self.assertFalse(CrewLine.objects.filter(pk=self.line.pk).exists())
        # "Werte setzen …" sends the chosen lines with the token of the bar: the dialog as a page of its own.
        page = self.assert_ok(self.client.post(self.edit, {"crew_lines": [self.toms.pk], "step": "choose"}))
        self.assertIn("Werte der gewählten Personalpositionen setzen", page)
        self.assertIn('name="meeting_point"', page)
        response = self.client.post(self.edit, {"crew_lines": [self.toms.pk], "meeting_point": "Halle 3"})
        self.assertRedirects(response, f"{self.detail}#planning-crew", fetch_redirect_response=False)
        self.toms.refresh_from_db()
        self.assertEqual(self.toms.meeting_point, "Halle 3")

    def test_the_dialog(self) -> None:
        dialog = self.htmx("get", self.edit, {"crew_lines": [self.line.pk, self.toms.pk]})
        text = self.assert_ok(dialog)
        self.assertIn("Für diese 2 Personalpositionen:", text)
        self.assertIn("Rabatt in Prozent", text)  # the administrator may see prices
        response = self.htmx("post", self.edit, {"crew_lines": [self.line.pk, self.toms.pk]})
        self.assertIn("Wähle, was für die gewählten Personalpositionen gesetzt werden soll.", response.content.decode())
        response = self.htmx(
            "post",
            self.edit,
            {"crew_lines": [self.line.pk, self.toms.pk], "note": "Schwarze Kleidung", "planned_hours": "6,5"},
        )
        self.assertIn("closeDialog", response["HX-Trigger"])
        self.assertEqual(
            set(CrewLine.objects.values_list("note", "planned_hours")), {("Schwarze Kleidung", Decimal("6.50"))}
        )

    def test_rights(self) -> None:
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertEqual(reader.post(self.bulk, {"crew_lines": [self.line.pk], "action": "delete"}).status_code, 403)
        self.assertEqual(reader.get(self.edit, {"crew_lines": [self.line.pk]}).status_code, 403)
        # Personnel planning plans the crew – without the price right, without the discount.
        planner = self.browser_for("petra", "Personaldisposition")
        text = self.assert_ok(planner.get(self.edit, {"crew_lines": [self.line.pk]}, HTTP_HX_REQUEST="true"))
        self.assertNotIn("discount_percent", text)
        response = planner.post(self.bulk, {"crew_lines": [self.line.pk], "action": "firm"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.FIRM)

    def test_plan_firmly_when_adding_and_in_the_dialog(self) -> None:
        from rentalars.personnel.models import JobFunction

        function = JobFunction.objects.get(name="Tontechnik")
        add = reverse("projects:crew_add", args=[self.project.pk])
        newcomer = make_person("Lea Vogel", rates={"Tontechnik": "25.00"})
        self.htmx(
            "post",
            add,
            {
                "job_function": function.pk,
                "person": newcomer.pk,
                "count": 1,
                "start": "2027-03-12T08:00",
                "end": "2027-03-12T18:00",
                "firm": "on",
            },
        )
        line = CrewLine.objects.get(person=newcomer)
        self.assertEqual(line.request_status, RequestStatus.FIRM)
        edit = reverse("projects:crew_edit", args=[self.project.pk, self.toms.pk])
        dialog = self.htmx("get", edit)
        self.assertIn("Fest eingeplant (ohne Anfrage)", dialog.content.decode())
        from tests.ui.base import form_data

        data = form_data(dialog, "start", firm="on")
        response = self.htmx("post", edit, data)
        self.assertEqual(response.status_code, 200)
        self.toms.refresh_from_db()
        self.assertEqual(self.toms.request_status, RequestStatus.FIRM)
        self.assertIn("Tom Richter ist fest eingeplant und wird benachrichtigt.", response.content.decode())


class CrewBulkApiTests(ApiTestCase):
    """``POST /projects/{id}/crew-lines/bulk`` and ``firm`` of a crew line (PRJ-117, PER-041; API-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.line = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))
        self.place = plan(self.project, "Tontechnik", None)
        self.url = f"{API}/projects/{self.project.pk}/crew-lines/bulk"

    def test_edit_firm_ask_delete(self) -> None:
        response = self.admin.post(
            self.url,
            {"lines": [self.line.pk, self.place.pk], "action": "edit", "values": {"meeting_point": "Halle 3"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(sorted(response.json()["changed"]), sorted([self.line.pk, self.place.pk]))
        self.assertEqual(len(Notification.objects.filter(user=self.anna.user, kind=Kind.DEPLOYMENT_CHANGE)), 1)
        response = self.admin.post(self.url, {"lines": [self.line.pk, self.place.pk], "action": "firm"}, format="json")
        data = response.json()
        self.assertEqual(data["changed"], [self.line.pk])
        self.assertEqual(
            data["skipped"],
            [{"line": self.place.pk, "title": f"{self.place.title} – offen", "reason": "ist ein offener Platz"}],
        )
        response = self.admin.post(self.url, {"lines": [self.line.pk], "action": "ask"}, format="json")
        self.assertEqual(response.json()["skipped"][0]["reason"], "ist fest eingeplant")
        response = self.admin.post(self.url, {"lines": [self.place.pk], "action": "delete"}, format="json")
        self.assertEqual(response.json()["changed"], [self.place.pk])
        self.assertFalse(CrewLine.objects.filter(pk=self.place.pk).exists())

    def test_refused(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assert_error(
            reader.post(self.url, {"lines": [self.line.pk], "action": "firm"}, format="json"), 403, "permission_denied"
        )
        planner = self.client_for("petra", "Personaldisposition")
        response = planner.post(
            self.url, {"lines": [self.line.pk], "action": "edit", "values": {"discount_percent": "5"}}, format="json"
        )
        self.assert_error(response, 400, "validation_error")
        self.assert_error(
            self.admin.post(self.url, {"lines": [], "action": "firm"}, format="json"), 400, "validation_error", "lines"
        )
        other = make_project("Anderes")
        self.assert_error(
            self.admin.post(
                f"{API}/projects/{other.pk}/crew-lines/bulk", {"lines": [self.line.pk], "action": "firm"}, format="json"
            ),
            400,
            "validation_error",
        )

    def test_firm_of_a_single_line(self) -> None:
        detail = f"{API}/projects/{self.project.pk}/crew-lines/{self.line.pk}"
        response = self.admin.patch(detail, {"firm": True}, format="json")
        self.assertEqual(response.json()["request_status"], "firm")
        response = self.admin.post(f"{detail}/request", format="json")
        self.assert_error(response, 400, "validation_error")
        response = self.admin.patch(detail, {"firm": False}, format="json")
        self.assertEqual(response.json()["request_status"], "")
        tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        created = self.admin.post(
            f"{API}/projects/{self.project.pk}/crew-lines",
            {"job_function": self.line.job_function_id, "person": tom.pk, "firm": True},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()[0]["request_status"], "firm")
        self.assertEqual(Notification.objects.filter(user=tom.user, kind=Kind.DEPLOYMENT_CHANGE).count(), 1)


class SettingsTests(RentalarsTestCase):
    """The kind of notification each person may switch off: in the list of their settings (PRJ-118)."""

    def test_in_the_settings_of_a_person(self) -> None:
        from rentalars.notifications.services import preferences_of

        kinds = [item["kind"] for item in preferences_of(make_user("anna"))]
        self.assertIn(Kind.DEPLOYMENT_CHANGE, kinds)
        self.assertLess(kinds.index(Kind.DEPLOYMENT_ANSWER), kinds.index(Kind.DEPLOYMENT_CHANGE))
