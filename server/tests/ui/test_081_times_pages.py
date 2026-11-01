# SPDX-License-Identifier: GPL-3.0-or-later
"""On the pages, area "times": ZEI-025, ZEI-024, ZEI-026.

* ZEI-025: the quick entry and the edit dialog divide a period into job functions – the person's deployments first,
  with phase and times; "My times", the approval and the report show the parts; the approval decides a period as a
  whole.
* ZEI-024: open service cases in the quick entry; the hint at the companion app in "My times", put away for good.
* ZEI-026: the column "Stundenlohn" (a day rate where paid per day) and "In Zwischenablage kopieren" at approved
  times.
"""

from __future__ import annotations

from decimal import Decimal as D  # noqa: N817

from django.urls import reverse

from rentalars.projects import service_cases
from rentalars.projects.models import CrewBilling, PhaseKind, ProjectPhase
from rentalars.timetracking import services
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus
from rentalars.timetracking.services import Part
from tests.helpers import (
    ALL_RIGHTS,
    LATER,
    at,
    clock_at_least,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)
from tests.ui.base import UiTestCase, form_data


class PeriodPageCase(UiTestCase):
    """Anna (crew) works light at the setup (08–12) and sound (12–20) of the Stadtfest on Wednesday, 10 March 2027."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.light = job_function("Licht", price="40.00")
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Licht": "30.00", "Tontechnik": "35.00"}, user=self.anna_user)
        self.setup = ProjectPhase.objects.create(
            project=self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 12)
        )
        self.light_line = plan(self.project, self.light, self.anna, start=at(10, 8), end=at(10, 12), phase=self.setup)
        self.sound_line = plan(self.project, self.sound, self.anna, start=at(10, 12), end=at(10, 20))
        self.crew = self.browser_of(self.anna_user)
        self.manager = self.browser_of(make_user("paula", roles=("Projektleitung",)))
        self.quick = reverse("timetracking:quick")

    def divide(self, *, approve: bool = False) -> TimeEntry:
        with clock_at_least(at(10, 16, 30)):
            first = services.create_entry(
                person=self.anna,
                project=self.project,
                job_function=self.light,
                start=at(10, 8),
                end=at(10, 16, 30),
                break_minutes=30,
                rights=ALL_RIGHTS,
                user=None,
                submit=True,
                parts=[Part(self.light, D("3"), self.light_line), Part(self.sound)],
            )
        if approve:
            services.approve_entries([first], rights=ALL_RIGHTS, user=None)
        return first


class DividingInTheDialogTests(PeriodPageCase):
    """ZEI-025 in the quick entry and the edit dialog."""

    def test_the_deployments_are_suggested_with_phase_and_times(self) -> None:
        dialog = self.assert_ok(self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew))
        self.assertIn('<optgroup label="Für dich eingeplant">', dialog)
        self.assertIn(f'value="line:{self.light_line.pk}">Licht – Aufbau, Mi 10.03. 08:00–12:00</option>', dialog)
        self.assertIn(f'value="line:{self.sound_line.pk}">Tontechnik, Mi 10.03. 12:00–20:00</option>', dialog)
        self.assertIn("Mehrere Funktionen in diesem Zeitraum", dialog)
        self.assertIn('name="part_0_function"', dialog)
        self.assertIn('<label for="id_part_0_hours">Stunden der Funktion 1</label>', dialog)

    def test_saving_a_divided_period(self) -> None:
        """ZEI-025: the job function above gets the rest; the confirmation names every part."""
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        data = form_data(
            dialog,
            job_function=f"line:{self.sound_line.pk}",
            day="2027-03-10",
            begin="08:00",
            end="16:30",
            break_minutes="30",
            part_0_function=f"line:{self.light_line.pk}",
            part_0_hours="3",
        )
        saved = self.assert_ok(self.htmx("post", self.quick, data, client=self.crew))
        self.assertIn("Zeit erfasst", saved)
        self.assertIn("als Tontechnik", saved)
        self.assertIn("als Licht", saved)
        parts = list(TimeEntry.objects.order_by("id"))
        self.assertEqual(
            [(part.job_function, part.crew_line, part.hours) for part in parts],
            [(self.sound, self.sound_line, D("5.00")), (self.light, self.light_line, D("3.00"))],
        )

    def test_hours_that_do_not_add_up_are_refused_in_the_dialog(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        data = form_data(
            dialog,
            job_function=str(self.sound.pk),
            day="2027-03-10",
            begin="08:00",
            end="10:00",
            part_0_function=str(self.light.pk),
            part_0_hours="3",
        )
        refused = self.assert_ok(self.htmx("post", self.quick, data, client=self.crew))
        self.assertIn("lassen nichts für", refused)
        self.assertIn('<details class="time-parts" open>', refused)
        self.assertFalse(TimeEntry.objects.exists())
        missing = form_data(dialog, day="2027-03-10", begin="08:00", end="10:00", part_0_function=str(self.light.pk))
        refused = self.assert_ok(self.htmx("post", self.quick, missing, client=self.crew))
        self.assertIn("Gib die Stunden dieser Funktion an.", refused)

    def test_the_edit_dialog_shows_and_changes_the_parts(self) -> None:
        first = self.divide()
        second = TimeEntry.objects.exclude(pk=first.pk).get()
        url = reverse("timetracking:entry_edit", args=[second.pk])  # any part opens the whole period
        dialog = self.htmx("get", url, client=self.crew)
        text = self.assert_ok(dialog)
        self.assertIn('<details class="time-parts" open>', text)
        data = form_data(dialog)
        self.assertEqual(data["job_function"], f"line:{self.light_line.pk}")
        self.assertEqual(data["part_0_function"], f"line:{self.sound_line.pk}")
        self.assertEqual(data["part_0_hours"], "5,00")
        data.update(part_0_hours="6")
        response = self.htmx("post", url, data, client=self.crew)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(list(TimeEntry.objects.order_by("id").values_list("hours", flat=True)), [D("2"), D("6")])


class PeriodListsTests(PeriodPageCase):
    """ZEI-025: the parts in "My times", the approval and the report."""

    def test_my_times_show_the_parts(self) -> None:
        self.divide()
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertEqual(page.count("Teil 1 von 2 eines Zeitraums von 8 Std."), 1)
        self.assertEqual(page.count("Teil 2 von 2 eines Zeitraums von 8 Std."), 1)

    def test_the_deployment_view_shows_the_parts(self) -> None:
        self.divide()
        page = self.assert_ok(self.crew.get(reverse("projects:deployment", args=[self.project])))
        self.assertIn("Teil 1 von 2 eines Zeitraums von 8 Std.", page)
        self.assertIn("Teil 2 von 2 eines Zeitraums von 8 Std.", page)

    def test_the_approval_decides_the_period_as_a_whole(self) -> None:
        first = self.divide()
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval")))
        self.assertEqual(page.count('name="entry"'), 1)
        self.assertIn("Wird mit dem ersten Teil des Zeitraums entschieden", page)
        self.manager.post(reverse("timetracking:decide"), {"entry": [first.pk], "decision": "approve"})
        self.assertEqual(set(TimeEntry.objects.values_list("status", flat=True)), {TimeEntryStatus.APPROVED})

    def test_the_report_and_its_csv_have_a_row_per_part(self) -> None:
        self.divide(approve=True)
        url = reverse("timetracking:report")
        page = self.assert_ok(self.manager.get(url, {"since": "2027-03-01"}))
        self.assertIn("Teil 2 von 2", page)
        csv = self.manager.get(url, {"since": "2027-03-01", "format": "csv"}).content.decode()
        self.assertIn(";Licht;10.03.2027;08:00;16:30;30;3;", csv)
        self.assertIn(";Tontechnik;10.03.2027;08:00;16:30;30;5;", csv)


class ServiceCaseInTheDialogTests(PeriodPageCase):
    """ZEI-024: open service cases in the quick entry, with every job function."""

    def test_cases_are_offered_and_take_a_spontaneous_time(self) -> None:
        case = service_cases.create_case(name="Scheinwerfer flackert")
        rigging = job_function("Rigging")
        dialog = self.assert_ok(self.htmx("get", self.quick, client=self.crew))
        self.assertIn('<optgroup label="Servicefälle">', dialog)
        self.assertIn(f"{case.number} Scheinwerfer flackert", dialog)
        # The guess stays the deployment, not a case the person has nothing to do with.
        self.assertIn(f'<option value="{self.project.pk}" selected>', dialog)
        with_case = self.htmx("get", self.quick, {"project": case.pk}, client=self.crew)
        self.assertIn(">Rigging</option>", self.assert_ok(with_case))
        data = form_data(with_case, job_function=str(rigging.pk), day="2027-03-20", begin="09:00", end="10:30")
        self.assert_ok(self.htmx("post", self.quick, data, client=self.crew))
        entry = TimeEntry.objects.get()
        self.assertEqual((entry.project, entry.job_function, entry.hours), (case, rigging, D("1.50")))


class CompanionHintTests(PeriodPageCase):
    """ZEI-024: a small hint at the companion app in "My times", put away for good."""

    def test_the_hint_links_to_the_tokens_and_can_be_put_away(self) -> None:
        url = reverse("timetracking:my_times")
        page = self.assert_ok(self.crew.get(url))
        self.assertIn("Rentalars Companion für Android", page)
        self.assertIn(f'href="{reverse("accounts:account")}#tokens"', page)
        self.assertIn('id="tokens"', self.assert_ok(self.crew.get(reverse("accounts:account"))))
        answer = self.htmx("post", reverse("timetracking:companion_hint_dismiss"), client=self.crew)
        self.assertEqual((answer.status_code, answer.content), (200, b""))
        self.assertNotIn("Rentalars Companion", self.assert_ok(self.crew.get(url)))
        # Only for this user.
        ben = self.browser_of(make_user("ben", roles=("Crew",)))
        self.assertIn("Rentalars Companion", self.assert_ok(ben.get(url)))

    def test_not_on_the_dashboard(self) -> None:
        self.assertNotIn("Rentalars Companion", self.assert_ok(self.crew.get(reverse("core:home"))))


class PayColumnAndCopyTests(PeriodPageCase):
    """ZEI-026."""

    def test_the_hourly_pay_between_hours_and_amount(self) -> None:
        record_time(self.anna, self.project, self.light, at(10, 8), at(10, 12))
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertRegex(page, r"(?s)<th[^>]*>Stunden</th><th[^>]*>Stundenlohn</th><th[^>]*>Betrag</th>")
        self.assertIn("30,00 €", page)
        self.assertIn("120,00 €", page)

    def test_a_day_rate(self) -> None:
        plan(
            self.project,
            self.sound,
            self.anna,
            start=at(11, 8),
            end=at(11, 22),
            billing=CrewBilling.DAY,
            daily_rate=D("280.00"),
        )
        record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 12))
        record_time(self.anna, self.project, self.sound, at(11, 18), at(11, 22))
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertIn("Tagessatz</span> 280,00 €", page)
        self.assertIn("im Tagessatz", page)

    def test_approved_times_can_be_copied(self) -> None:
        self.divide(approve=True)
        submitted = record_time(self.anna, self.project, self.sound, at(11, 12), at(11, 14), submit=True)
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertEqual(page.count("data-copy-block="), 1)
        self.assertIn('aria-label="In Zwischenablage kopieren"', page)
        self.assertIn(
            f'data-copy-block="Licht, Stunde\n\tDatum: 2027.03.10\n\tProjekt: {self.project.number} - Stadtfest\n'
            "\tAktivität: Aufbau\nTontechnik, Stunde\n",
            page,
        )
        self.assertIn('data-copied-text="Kopiert"', page)
        self.assertIn('role="status" aria-live="polite" data-copy-status', page)
        self.assertEqual(submitted.status, TimeEntryStatus.SUBMITTED)
