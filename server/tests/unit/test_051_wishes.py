# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the wishes that are not mail, planning, imports, calendars, settings or lines.

* AUT-026 – every person is an account, every account a person.
* AUT-027 – one-time password with a forced change; "forgot password" for invited accounts.
* PER-025 – only people with a job function are offered for planning.
* UIX-020 – pages follow changes: the stamps behind ``/changes/``.
* UIX-022 – no "Back" on the sections of the planning.
* UIX-024 – readable addresses with project and article numbers.
* PRJ-068 – noon to noon as the usual period.
* PRJ-073 – planned hours from the clock times of a longer period.
* PRJ-076 – project templates.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.hashers import is_password_usable
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory
from django.urls import resolve, reverse

from rentalars.accounts.forms import ResetPasswordForm
from rentalars.accounts.models import SecurityEvent, User
from rentalars.accounts.rights import Rights
from rentalars.accounts.services import set_one_time_password
from rentalars.core import changes
from rentalars.core.models import SystemSettings
from rentalars.core.trail import is_start_page
from rentalars.personnel import services as personnel_services
from rentalars.personnel.models import EmploymentKind, Person, unique_username
from rentalars.projects.forms import CrewAddForm, people_choices
from rentalars.projects.models import OpenItem, PhaseKind, ProjectPhase, ProjectTemplate, suggested_hours
from rentalars.projects.project_templates import apply_template, save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    PASSWORD,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
)

# --- AUT-026: people are accounts ----------------------------------------------------


class PeopleAreAccountsTests(RentalarsTestCase):
    def test_a_new_user_is_a_person(self) -> None:
        """An account created in the user administration appears in the personnel."""
        user = User.objects.create_user("bert", "Bert@Example.de", PASSWORD, first_name="Bert", last_name="Kern")
        person = Person.objects.get(user=user)
        self.assertEqual((person.first_name, person.last_name, person.email), ("Bert", "Kern", "bert@example.de"))

    def test_a_new_person_gets_an_account_without_password(self) -> None:
        """A person created in the personnel can log in once invited; the role follows the kind."""
        crew = personnel_services.save_person(Person(first_name="Jörg", last_name="Groß"))
        freelancer = personnel_services.save_person(
            Person(first_name="Jörg", last_name="Groß", kind=EmploymentKind.FREELANCER)
        )
        self.assertEqual(crew.user.username, "joerg.gross")
        self.assertEqual(freelancer.user.username, "joerg.gross2")
        self.assertFalse(is_password_usable(crew.user.password))
        self.assertEqual([role.name for role in crew.user.roles.all()], ["Crew"])
        self.assertEqual([role.name for role in freelancer.user.roles.all()], ["Freie Kraft"])

    def test_names_address_and_state_stay_in_step(self) -> None:
        """Changing the person changes the account, and the other way round."""
        person = make_person("Anna Becker", email="anna@example.de")
        person.last_name, person.email = "Berger", "anna.berger@example.de"
        personnel_services.save_person(person)
        user = User.objects.get(pk=person.user_id)
        self.assertEqual((user.last_name, user.email), ("Berger", "anna.berger@example.de"))
        user.first_name = "Annika"
        user.save()
        person.refresh_from_db()
        self.assertEqual(person.first_name, "Annika")
        personnel_services.set_person_active(person, active=False)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_two_people_without_address_are_allowed(self) -> None:
        """The e-mail address is optional, and empty addresses do not collide."""
        first = make_person("Carl Ohne")
        second = make_person("Dora Ohne")
        self.assertIsNone(User.objects.get(pk=first.user_id).email)
        self.assertIsNone(User.objects.get(pk=second.user_id).email)

    def test_deleting_a_person_takes_the_unused_account(self) -> None:
        """A person who never logged in goes with the account; one who did must be deactivated."""
        person = make_person("Emil Neu")
        user_pk = person.user_id
        personnel_services.delete_person(person)
        self.assertFalse(User.objects.filter(pk=user_pk).exists())

        used = make_person("Frida Alt")
        User.objects.filter(pk=used.user_id).update(last_login=at(1))
        used.refresh_from_db()
        with self.assertRaises(ValidationError):
            personnel_services.delete_person(used)

    def test_usernames_are_unique(self) -> None:
        """``unique_username`` counts up, ignoring case."""
        make_user("anna.becker")
        self.assertEqual(unique_username("Anna", "Becker"), "anna.becker2")
        self.assertEqual(unique_username("", ""), "person")


# --- AUT-027: one-time password ---------------------------------------------------


class OneTimePasswordTests(RentalarsTestCase):
    def test_the_password_works_once_and_asks_for_a_new_one(self) -> None:
        """The administrator hands over a password; every page then leads to choosing an own one."""
        admin = make_user("admin", superuser=True)
        user = make_person("Gerd Gast").user
        password = set_one_time_password(user, acting_user=admin)
        user.refresh_from_db()
        self.assertTrue(user.must_change_password)
        self.assertTrue(SecurityEvent.objects.filter(user=user, kind="one_time_password").exists())

        browser = Client()
        self.assertTrue(browser.login(username=user.username, password=password))
        self.assertRedirects(browser.get(reverse("core:home")), reverse("accounts:new_password"))
        api = browser.get("/api/v1/projects/")
        self.assertEqual(api.status_code, 403)
        self.assertEqual(api.json()["error"]["code"], "password_change_required")

        own = "ein ganz eigenes Kennwort 2027"
        response = browser.post(reverse("accounts:new_password"), {"new_password1": own, "new_password2": own})
        self.assertRedirects(response, reverse("core:home"))
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password(own))
        self.assertEqual(browser.get(reverse("core:home")).status_code, 200)

    def test_not_for_a_deactivated_account(self) -> None:
        """A deactivated account gets no password."""
        person = make_person("Hanna Weg")
        personnel_services.set_person_active(person, active=False)
        with self.assertRaises(ValidationError):
            set_one_time_password(User.objects.get(pk=person.user_id))

    def test_forgot_password_reaches_an_invited_account(self) -> None:
        """An invited account without a password gets the link too (the mail of the invitation was lost)."""
        make_person("Ida Neu", email="ida@example.de")
        self.assertEqual([user.username for user in ResetPasswordForm().get_users("IDA@example.de")], ["ida.neu"])
        Client().post(reverse("accounts:password_reset"), {"email": "ida@example.de"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ida@example.de"])


# --- PER-025: people with a job function ----------------------------------------


class PeopleChoicesTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sound = job_function("Tontechnik")
        self.light = job_function("Lichttechnik")
        self.anna = make_person("Anna Ton", rates={"Tontechnik": "30.00"})
        self.bert = make_person("Bert Licht", rates={"Lichttechnik": "30.00"})
        self.office = make_person("Carla Büro")

    def ids(self, choices: list) -> set:
        return {pk for pk, _label in choices}

    def test_only_people_with_the_function(self) -> None:
        """A person appears once the job function is assigned; office accounts stay out."""
        choices, functions_of = people_choices(self.sound)
        self.assertEqual(self.ids(choices), {self.anna.pk})
        choices, _functions = people_choices()
        self.assertEqual(self.ids(choices), {self.anna.pk, self.bert.pk})
        self.assertEqual(functions_of[self.bert.pk], {self.light.pk})

    def test_planners_who_may_deviate_see_the_others(self) -> None:
        """With the right to plan outside the job functions, everybody is offered – the others last."""
        choices, _functions = people_choices(self.sound, include_others=True)
        self.assertEqual(choices[0][0], self.anna.pk)
        self.assertIn(self.office.pk, self.ids(choices))

    def test_a_planned_person_stays_in_the_list(self) -> None:
        """Somebody planned before the function was taken away is still shown on the line."""
        choices, _functions = people_choices(self.sound, keep=self.office)
        self.assertIn(self.office.pk, self.ids(choices))

    def test_the_options_carry_the_functions(self) -> None:
        """The page script narrows the list by ``data-functions``."""
        form = CrewAddForm(project=make_project())
        html = str(form["person"])
        self.assertIn(f'data-functions="{self.sound.pk}"', html)
        self.assertNotIn("Carla", html)
        self.assertIn('data-people-for="job_function"', html)


# --- UIX-024: readable addresses ----------------------------------------------------


class ReadableAddressTests(RentalarsTestCase):
    def test_the_project_number_is_in_the_address(self) -> None:
        """Whether reverse gets the object, the key or the number."""
        project = make_project()
        expected = f"/projects/{project.number}/"
        self.assertEqual(reverse("projects:detail", args=[project]), expected)
        self.assertEqual(reverse("projects:detail", args=[project.pk]), expected)
        self.assertEqual(reverse("projects:detail", kwargs={"pk": project.number}), expected)
        self.assertEqual(resolve(expected).kwargs["pk"], project.pk)

    def test_old_links_with_the_key_still_lead_there(self) -> None:
        """Old bookmarks keep working."""
        project = make_project()
        self.assertEqual(resolve(f"/projects/{project.pk}/").kwargs["pk"], project.pk)

    def test_the_article_number_is_in_the_address(self) -> None:
        """Products are addressed by their article number."""
        product = make_product("L-010")
        self.assertEqual(reverse("products:detail", args=[product.pk]), "/products/L-010/")
        self.assertEqual(resolve("/products/L-010/").kwargs["pk"], product.pk)

    def test_unknown_numbers_find_nothing(self) -> None:
        """An address with a number that does not exist is not found."""
        from django.urls import Resolver404

        with self.assertRaises(Resolver404):
            resolve("/projects/1999-9999/")


# --- UIX-020: pages follow changes ------------------------------------------------


class ChangeStampTests(RentalarsTestCase):
    def test_a_change_in_the_project_changes_its_stamp(self) -> None:
        """Adding a line is a change of the project page."""
        admin = make_user("admin", superuser=True)
        project = make_project()
        key = f"project:{project.pk}"
        before = changes.stamps([key], admin)[key]
        add_line(project, make_stock("L-001", 2), 1)
        after = changes.stamps([key], admin)[key]
        self.assertNotEqual(before, after)
        self.assertEqual(changes.stamps([key], admin)[key], after)

    def test_nothing_is_told_without_access(self) -> None:
        """A user who may not read the project, or asks for an unknown key, gets an empty text."""
        project = make_project()
        nobody = make_user("nobody")
        key = f"project:{project.pk}"
        self.assertEqual(changes.stamps([key, "something:else"], nobody), {key: "", "something:else": ""})

    def test_the_keys_of_a_page(self) -> None:
        """A project page watches its project; every page watches the notifications.

        UIX-010: and the chat of the project, for the unread count of the tab "Chat".
        """
        project = make_project()
        request = RequestFactory().get(f"/projects/{project.number}/")
        request.resolver_match = resolve(request.path)
        # Stock refresh: the planning page also watches the stock figures of its availability column.
        self.assertEqual(
            changes.watch_keys(request),
            ["notifications", f"project:{project.pk}", f"chat:{project.pk}", f"stock:{project.pk}"],
        )
        request = RequestFactory().get("/projects/")
        request.resolver_match = resolve(request.path)
        self.assertEqual(changes.watch_keys(request), ["notifications"])


# --- UIX-022: no "Back" on the sections of the planning ------------------------------


class StartPageTests(RentalarsTestCase):
    def test_the_tabs_of_planning_are_start_pages(self) -> None:
        """The calendar, the timeline and the plans are reached from the navigation."""
        for name in ("schedule:calendar", "schedule:timeline", "schedule:products", "schedule:personnel"):
            request = RequestFactory().get(reverse(name))
            request.resolver_match = resolve(request.path)
            self.assertTrue(is_start_page(request), name)


# --- PRJ-068, PRJ-073: periods and hours ----------------------------------------------


class NoonToNoonTests(RentalarsTestCase):
    def test_the_usual_period_is_noon_to_noon(self) -> None:
        """A fresh installation suggests 12:00 to 12:00 of the next day."""
        settings = SystemSettings.load()
        self.assertEqual(
            (settings.default_start_time, settings.default_end_time), (datetime.time(12), datetime.time(12))
        )


class SuggestedHoursTests(RentalarsTestCase):
    def test_hours_are_the_length_of_the_period(self) -> None:
        """Always end minus start (PRJ-073): 08:00 to 20:00 over three days are 60 hours."""
        cases = [
            (at(10, 8), at(10, 14), "6.00"),
            (at(10, 8), at(10, 23, 30), "15.50"),
            (at(10, 8), at(12, 20), "60.00"),
            (at(10, 10), at(12, 18), "56.00"),
            (at(10, 12), at(11, 12), "24.00"),
            (at(10, 20), at(11, 2), "6.00"),
        ]
        for start, end, hours in cases:
            with self.subTest(start=start, end=end):
                self.assertEqual(suggested_hours(start, end), Decimal(hours))

    def test_a_crew_line_takes_the_suggestion(self) -> None:
        """A place over the whole project gets the length of the project as its hours (PRJ-073)."""
        project = make_project(start=at(10, 8), end=at(12, 20))
        line = plan(project, "Bühnentechnik")
        self.assertEqual(line.planned_hours, Decimal("60.00"))


# --- PRJ-076: project templates -------------------------------------------------------


class ProjectTemplateTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-001", 10, "Lautsprecher", price="20.00")
        self.cable = make_stock("K-001", 50, "Kabel", price="2.00")
        self.source = make_project("Stadtfest 2027", start=at(10, 12), end=at(12, 12))
        stage = add_group(self.source, "Bühne", discount_percent=Decimal("10"))
        add_line(self.source, self.speaker, 4, group=stage, note="hinten links")
        add_line(self.source, self.cable, 20, group=stage, start=at(11, 12), end=at(12, 12))
        add_line(self.source, None, 1, title="Anfahrt", unit_price=Decimal("80.00"))
        plan(self.source, job_function("Tontechnik", price="40.00"), meeting_point="Lager")
        ProjectPhase.objects.create(project=self.source, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 18))
        ProjectPhase.objects.create(project=self.source, kind=PhaseKind.CLEANING, start=at(12, 8), end=at(12, 10))
        OpenItem.objects.create(project=self.source, text="Strom klären")
        self.template = save_as_template(self.source, name="Stadtfest", rights=ALL_RIGHTS)

    def test_the_template_keeps_the_structure(self) -> None:
        """Groups, lines, crew places, phases and open items are in the content."""
        self.assertEqual(self.template.counts, {"groups": 1, "lines": 3, "crew": 1, "phases": 2, "open_items": 1})
        self.assertEqual(self.template.source_number, self.source.number)

    def test_a_new_project_gets_the_content_relative_to_its_start(self) -> None:
        """Times move with the start; a line's own period keeps its place."""
        target = make_project("Weinfest", start=at(20, 12, month=4), end=at(22, 12, month=4))
        result = apply_template(self.template, target, rights=ALL_RIGHTS)
        self.assertEqual((result.lines, result.crew, result.phases, result.left_out), (3, 1, 2, []))
        group = target.groups.get()
        self.assertEqual((group.name, group.discount_percent), ("Bühne", Decimal("10.00")))
        lines = {
            line.product.article_number if line.product else line.title: line
            for line in target.material_lines.select_related("product")
        }
        self.assertEqual(lines["T-001"].quantity, Decimal("4"))
        self.assertEqual(lines["T-001"].note, "hinten links")
        self.assertEqual((lines["T-001"].start, lines["T-001"].end), (target.start, target.end))
        self.assertEqual((lines["K-001"].start, lines["K-001"].end), (at(21, 12, month=4), at(22, 12, month=4)))
        self.assertEqual(lines["Anfahrt"].unit_price, Decimal("80.00"))
        crew = target.crew_lines.get()
        self.assertIsNone(crew.person)
        self.assertEqual(crew.meeting_point, "Lager")
        phases = list(target.phases.order_by("start"))
        self.assertEqual([phase.kind for phase in phases], [PhaseKind.SETUP, PhaseKind.CLEANING])
        self.assertEqual((phases[0].start, phases[0].end), (at(20, 14, month=4), at(20, 18, month=4)))
        self.assertEqual(list(target.open_items.values_list("text", flat=True)), ["Strom klären"])

    def test_prices_are_those_of_today(self) -> None:
        """A price changed since the template was saved applies to the new project."""
        self.speaker.price = Decimal("25.00")
        self.speaker.save()
        target = make_project("Weinfest", start=at(20, 12, month=4), end=at(22, 12, month=4))
        apply_template(self.template, target, rights=ALL_RIGHTS)
        self.assertEqual(target.material_lines.get(product=self.speaker).unit_price, Decimal("25.00"))

    def test_a_deactivated_product_is_left_out_and_named(self) -> None:
        """What is gone is reported, the rest is created."""
        self.cable.is_active = False
        self.cable.save()
        target = make_project("Weinfest", start=at(20, 12, month=4), end=at(22, 12, month=4))
        result = apply_template(self.template, target, rights=ALL_RIGHTS)
        self.assertEqual(result.lines, 2)
        self.assertEqual(len(result.left_out), 1)

    def test_without_the_right_to_prices_no_prices_are_kept(self) -> None:
        """Whoever may not see prices saves a template without them."""
        template = save_as_template(
            self.source,
            name="Ohne Preise",
            rights=Rights(module_levels=dict(ALL_RIGHTS.module_levels), special_rights=frozenset()),
        )
        self.assertIsNone(template.content["groups"][0]["discount_percent"])
        self.assertIsNone(next(line for line in template.content["lines"] if line["title"])["unit_price"])

    def test_names_are_unique_unless_replaced(self) -> None:
        """A second template of the same name needs "replace"."""
        with self.assertRaises(ValidationError):
            save_as_template(self.source, name="stadtfest", rights=ALL_RIGHTS)
        replaced = save_as_template(self.source, name="stadtfest", rights=ALL_RIGHTS, replace=True, crew=False)
        self.assertEqual(ProjectTemplate.objects.count(), 1)
        self.assertEqual(replaced.counts["crew"], 0)
        with self.assertRaises(ValidationError):
            save_as_template(self.source, name="  ", rights=ALL_RIGHTS)


class ExportWithoutCalendarSecretsTests(RentalarsTestCase):
    def test_calendar_links_and_passwords_stay_out(self) -> None:
        """IMP-006 after PER-022, PER-023: a subscription token works like a password."""
        from rentalars.core.export import _fields
        from rentalars.core.models import BackgroundJob

        fields = _fields(Person)
        for secret in ("calendar_token", "availability_feed_url", "caldav_password_encrypted"):
            self.assertNotIn(secret, fields)
        self.assertIn("caldav_url", fields)
        self.assertNotIn("params", _fields(BackgroundJob))  # the key of an encrypted backup


class DashboardShortagesTests(RentalarsTestCase):
    def test_kept_until_something_changes(self) -> None:
        """UIX-021: the start page shares one result until the next change."""
        from rentalars.core.views import dashboard_shortages
        from rentalars.projects.models import Project

        product = make_stock("L-001", 1)
        project = make_project("Herbstfest", start=at(10, 12, month=9), end=at(11, 12, month=9))
        add_line(project, product, 3)
        first, count = dashboard_shortages(Project.objects.all())
        self.assertEqual((count, first[0].quantity), (1, 2))
        with self.assertNumQueries(1):  # only the newest entry of the change log
            self.assertEqual(dashboard_shortages(Project.objects.all())[1], 1)
        line = project.material_lines.get()
        from rentalars.projects import services

        services.update_line(line, rights=ALL_RIGHTS, quantity=Decimal("1"))
        self.assertEqual(dashboard_shortages(Project.objects.all())[1], 0)
