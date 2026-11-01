# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "fixes": a job function can always be chosen when recording a time (ZEI-007),
surcharges only on crew lines (PER-009, PER-040), the English labels left over (UIX-029).
"""

from __future__ import annotations

import datetime
import pathlib
import re
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.utils import translation

from rentalars.accounts.rights import rights_of
from rentalars.core.models import TimeSurchargeRule
from rentalars.core.surcharge_presets import NIGHT_AFTER_MIDNIGHT, preset_names
from rentalars.core.surcharges import forget_cached_rules
from rentalars.documents.models import AccountingSettings
from rentalars.packing.models import LineAssignment, PackEntry, Packlist
from rentalars.personnel import services as personnel
from rentalars.personnel.models import JobFunction
from rentalars.projects import services as project_services
from rentalars.projects.models import CrewBilling
from rentalars.projects.pricing import compute_project_prices
from rentalars.timetracking import services
from rentalars.timetracking.forms import TimeEntryForm
from tests.helpers import (
    LATER,
    RentalarsTestCase,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    set_clock,
)
from tests.unit.test_080_surcharges import march, switch_on

D = Decimal


def names(functions: list[JobFunction]) -> list[str]:
    return [function.name for function in functions]


def every_active() -> list[str]:
    return sorted(JobFunction.objects.filter(is_active=True).values_list("name", flat=True), key=str.lower)


class JobFunctionChoiceTests(RentalarsTestCase):
    """ZEI-007: the choice of the job function is never empty – own ones, the project's crew, else all."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)  # the hours of 10 March are recorded afterwards (ZEI-022)
        # A project without phases and without crew lines, which Kai may see as project manager.
        self.project = make_project("Messe", start=at(10), end=at(12))
        self.kai_user = make_user("kai", roles=("Projektleitung",))
        self.kai = make_person("Kai Kurz", user=self.kai_user)  # no job function of his own
        self.sound = job_function("Tontechnik", price="45.00", guide="30.00")

    def record(self, function: JobFunction, project: object = "default") -> object:
        return services.create_entry(
            person=self.kai,
            project=self.project if project == "default" else project,
            job_function=function,
            start=at(10, 8),
            end=at(10, 12),
            rights=rights_of(self.kai_user),
            user=self.kai_user,
        )

    def test_without_phases_crew_and_own_functions_every_active_function(self) -> None:
        """The case of the user's report: the choice is not empty, so a time can be recorded."""
        self.assertFalse(self.project.phases.exists())
        self.assertFalse(self.project.crew_lines.exists())
        functions = services.job_functions_for(self.kai, self.project)
        self.assertEqual(names(functions), every_active())
        self.assertIn("Tontechnik", names(functions))
        entry = self.record(self.sound)
        # Without an own rate and without a crew line: the guide value of the job function (ZEI-008).
        self.assertEqual((entry.job_function, entry.hourly_rate), (self.sound, D("30.00")))

    def test_the_job_functions_of_the_project_crew(self) -> None:
        """Crew lines of other people and open places name the job functions of the project – then no others."""
        light = job_function("Lichttechnik")
        plan(self.project, light, make_person("Tom Richter", rates={"Lichttechnik": "30.00"}))
        plan(self.project, self.sound)  # an open place
        self.assertEqual(names(services.job_functions_for(self.kai, self.project)), ["Lichttechnik", "Tontechnik"])
        self.record(light)
        with self.assertRaises(ValidationError) as raised:
            self.record(job_function("Rigging"), project=self.project)
        self.assertIn("job_function", raised.exception.message_dict)

    def test_own_functions_first_then_those_of_the_crew(self) -> None:
        tent = job_function("Zeltbau")
        personnel.set_rate(self.kai, tent, D("25.00"), datetime.date(2027, 1, 1))
        plan(self.project, job_function("Aufbau"))
        self.assertEqual(names(services.job_functions_for(self.kai, self.project)), ["Zeltbau", "Aufbau"])
        # Only own functions and no crew: just those – the fallback is for an empty choice only.
        other = make_project("Lagerinventur", start=at(10), end=at(12))
        self.assertEqual(names(services.job_functions_for(self.kai, other)), ["Zeltbau"])
        self.assertEqual(self.record(tent).hourly_rate, D("25.00"))

    def test_planned_functions_of_the_person_count_as_own(self) -> None:
        light = job_function("Lichttechnik")
        plan(self.project, job_function("Aufbau"))
        plan(self.project, light, self.kai)
        self.assertEqual(names(services.job_functions_for(self.kai, self.project)), ["Lichttechnik", "Aufbau"])

    def test_without_project(self) -> None:
        """ZEI-023: own job functions – for somebody without any every active one, as on a project."""
        self.assertEqual(names(services.job_functions_for(self.kai, None)), every_active())
        self.record(self.sound, project=None)
        anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.assertEqual(names(services.job_functions_for(anna, None)), ["Stagehand"])

    def test_a_whole_project_offers_the_crew_functions_of_its_parts(self) -> None:
        part = project_services.create_subproject(self.project, name="Halle 2", start=at(10, 8), end=at(11, 8))
        plan(part, job_function("Rigging"))
        self.assertEqual(names(services.job_functions_for(self.kai, self.project)), ["Rigging"])
        self.assertEqual(names(services.job_functions_for(self.kai, part)), ["Rigging"])

    def test_inactive_functions_are_not_offered(self) -> None:
        JobFunction.objects.filter(name="Tontechnik").update(is_active=False)
        self.assertNotIn("Tontechnik", names(services.job_functions_for(self.kai, self.project)))

    def test_the_form_always_has_a_job_function_preselected(self) -> None:
        set_clock(at(11, 18))  # the project runs: it is among the suggestions
        form = TimeEntryForm(
            person=self.kai, rights=rights_of(self.kai_user), user=self.kai_user, project_id=self.project.pk
        )
        self.assertEqual(form.initial["project"], str(self.project.pk))
        values = [value for value, _label in form.fields["job_function"].choices]
        self.assertEqual(len(values), len(every_active()))
        self.assertIn(form.initial["job_function"], values)


class SurchargesOnlyOnCrewLinesTests(RentalarsTestCase):
    """PER-009, PER-040: the surcharges for night, Sunday and holidays reach crew lines and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.function = job_function("Tontechnik", price="45.00", guide="30.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "30.00"})
        self.project = make_project(start=march(10), end=march(28, 12))

    def test_the_rules_change_the_crew_lines_and_no_other_line(self) -> None:
        # Saturday 18:00 to Sunday 02:00: night, night after midnight and Sunday.
        plan(self.project, self.function, self.anna, start=march(13, 18), end=march(14, 2), billing=CrewBilling.PLAN)
        add_line(self.project, make_product("L-100", "Scheinwerfer", price="20.00"), 4)
        add_line(self.project, make_product("N-100", "Transport", price="80.00", kind="incidental"), 1)
        with_rules = compute_project_prices(self.project)
        self.assertEqual(with_rules.personnel_time_surcharges, D("126.00"))
        TimeSurchargeRule.objects.all().delete()
        forget_cached_rules()
        without_rules = compute_project_prices(self.project)
        self.assertEqual(without_rules.personnel_time_surcharges, D("0"))
        # The material and the incidental costs cost the same with and without the rules.
        self.assertEqual(with_rules.ungrouped_total, without_rules.ungrouped_total)
        self.assertEqual(with_rules.groups_total, without_rules.groups_total)
        self.assertEqual(with_rules.personnel_total - without_rules.personnel_total, D("126.00"))

    def test_the_preset_rule_names(self) -> None:
        """UIX-029: "Night 0–4" – without the "o'clock"; German stays "Nacht 0–4 Uhr"."""
        self.assertEqual(preset_names("en")[NIGHT_AFTER_MIDNIGHT], "Night 0–4")
        self.assertEqual(preset_names("de")[NIGHT_AFTER_MIDNIGHT], "Nacht 0–4 Uhr")


class EnglishLabelTests(RentalarsTestCase):
    """UIX-029: "packing list", "debtor", no "o'clock" – German stays as it was."""

    def test_the_names_of_the_packing_models(self) -> None:
        expected = {
            Packlist: ("packing list", "packing lists", "Packliste"),
            PackEntry: ("packing list entry", "packing list entries", "Packlisteneintrag"),
            LineAssignment: ("packing list assignment", "packing list assignments", "Zuordnung zur Packliste"),
        }
        for model, (singular, plural, german) in expected.items():
            with translation.override("en"):
                self.assertEqual(
                    (str(model._meta.verbose_name), str(model._meta.verbose_name_plural)), (singular, plural)
                )
            with translation.override("de"):
                self.assertEqual(str(model._meta.verbose_name), german)

    def test_the_accounting_settings(self) -> None:
        field = AccountingSettings._meta.get_field
        with translation.override("en"):
            self.assertEqual(str(field("datev_debitor_mode").verbose_name), "debtor accounts")
            self.assertEqual(
                [str(label) for _value, label in field("datev_debitor_mode").choices],
                ["one debtor account per customer", "one collective debtor account"],
            )
            self.assertEqual(str(field("datev_collective_account").verbose_name), "collective debtor account")
            self.assertTrue(str(field("datev_account_length").help_text).startswith("Number of digits of the general"))
            self.assertIn("(Beraternummer)", str(field("datev_consultant_number").help_text))
        with translation.override("de"):
            self.assertEqual(str(field("datev_debitor_mode").verbose_name), "Debitorenkonten")
            self.assertEqual(
                str(field("datev_account_length").help_text), "Meist 4. Debitorenkonten haben eine Stelle mehr."
            )

    def test_no_english_text_says_packlist_debitor_or_oclock(self) -> None:
        """Every msgid of the catalogue – the English interface – is free of the three words."""
        catalogue = pathlib.Path(django_settings.BASE_DIR) / "locale/de/LC_MESSAGES/django.po"
        text = catalogue.read_text(encoding="utf-8")
        msgids = []
        for block in re.findall(r'^msgid(?:_plural)? ((?:".*"\n)+)', text, flags=re.MULTILINE):
            msgids.append("".join(re.findall(r'"(.*)"', block)))
        self.assertGreater(len(msgids), 1000)
        # Placeholders such as %(packlist)s are no text anybody reads.
        found = [
            msgid
            for msgid in msgids
            if re.search(r"packlist|debitor|o'clock|o’clock", re.sub(r"%\(\w+\)[sd]|\{\w+\}", "", msgid), re.I)
        ]
        self.assertEqual(found, [])
