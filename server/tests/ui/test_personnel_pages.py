# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: people, job functions, hourly rates, absences, availability, own data (chapter 5.5)."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.personnel import services
from rentalars.personnel.models import Absence, JobFunction, Person
from tests.helpers import (
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
)
from tests.ui.base import UiTestCase, form_data


class PersonPageTests(UiTestCase):
    """PER-001, PER-002, PER-003, PER-013, AUT-012."""

    def test_create_a_freelancer_with_account(self) -> None:
        """AUT-026: the person gets the login with it – a freelancer the role "Freie Kraft"."""
        url = reverse("personnel:person_create")
        response = self.client.post(
            url,
            form_data(
                self.client.get(url),
                first_name="Tom",
                last_name="Richter",
                kind="freelancer",
                email="tom@example.de",
                company="Richter Lichtdesign",
                vat_id="DE123456789",
            ),
        )
        tom = Person.objects.get(first_name="Tom")
        self.assertRedirects(response, reverse("personnel:person_detail", args=[tom.pk]))
        self.assertEqual(
            (tom.name, tom.user.username, tom.user.email, tom.company, tom.is_freelancer),
            ("Tom Richter", "tom.richter", "tom@example.de", "Richter Lichtdesign", True),
        )
        self.assertEqual([role.name for role in tom.user.roles.all()], ["Freie Kraft"])
        page = self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[tom.pk])))
        for shown in ("Tom Richter", "Freie Kraft", "Richter Lichtdesign", "DE123456789", "Noch keine Funktion"):
            self.assertIn(shown, page)

    def test_an_address_of_another_account_is_refused(self) -> None:
        """AUT-026: person and account share the e-mail address, so it must be free."""
        make_user("anna")
        url = reverse("personnel:person_create")
        page = self.client.post(
            url, form_data(self.client.get(url), first_name="Anna", last_name="Zwei", email="anna@example.de")
        )
        self.assertIn("anna@example.de", self.assert_ok(page))
        self.assertFalse(Person.objects.filter(last_name="Zwei").exists())

    def test_no_account_to_choose(self) -> None:
        """AUT-026: every person is an account; the form offers no account to link."""
        form = self.assert_ok(self.client.get(reverse("personnel:person_create")))
        self.assertNotIn('name="user"', form)
        self.assertIn('name="invite"', form)

    def test_list_with_search_kind_and_job_function(self) -> None:
        make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        make_person("Tom Richter", rates={"Lichttechnik": "38.00"}, kind="freelancer", company="Richter Lichtdesign")
        gone = make_person("Gerd Gegangen")
        services.set_person_active(gone, active=False)
        url = reverse("personnel:person_list")

        page = self.assert_ok(self.client.get(url))
        self.assertIn("Becker, Anna", page)
        self.assertIn("Tontechnik", page)
        self.assertNotIn("Gegangen, Gerd", page)
        self.assertIn("Gegangen, Gerd", self.assert_ok(self.client.get(url, {"inactive": "1"})))

        for query, shown, hidden in (
            ({"q": "lichtdesign"}, "Richter, Tom", "Becker, Anna"),
            ({"kind": "freelancer"}, "Richter, Tom", "Becker, Anna"),
            ({"job_function": job_function("Tontechnik").pk}, "Becker, Anna", "Richter, Tom"),
        ):
            page = self.assert_ok(self.client.get(url, query))
            self.assertIn(shown, page, query)
            self.assertNotIn(f">{hidden}<", page, query)

    def test_overview_of_a_person_shows_deployments_absences_and_times(self) -> None:
        """PER-013."""
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        project = make_project("Stadtfest")
        plan(project, "Tontechnik", anna, start=at(10, 8), end=at(10, 20))
        record_time(anna, project, "Tontechnik", at(10, 8), at(10, 16), approve=True)
        services.save_absence(Absence(person=anna, kind="vacation", start=at(20), end=at(27)))
        page = self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[anna.pk])))
        deployments = page[page.index("Geplante Einsätze") : page.index("Erfasste Zeiten")]
        self.assertIn("Stadtfest", deployments)
        self.assertIn("10.03.2027 08:00", deployments)
        self.assertIn("Urlaub", page)
        times = page[page.index("Erfasste Zeiten") : page.index("Verlauf")]
        self.assertIn("freigegeben", times)
        self.assertIn(">8<", times)

    def test_deactivate_and_reactivate(self) -> None:
        anna = make_person("Anna Becker")
        url = reverse("personnel:person_set_active", args=[anna.pk])
        self.client.post(url, {"active": "0"})
        self.assertFalse(Person.objects.get(pk=anna.pk).is_active)
        self.assertIn(
            "deaktiviert", self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[anna.pk])))
        )
        self.client.post(url, {"active": "1"})
        self.assertTrue(Person.objects.get(pk=anna.pk).is_active)

    def test_delete_only_people_who_never_worked(self) -> None:
        unused = make_person("Uwe Unbenutzt")
        self.assertRedirects(
            self.client.post(reverse("personnel:person_delete", args=[unused.pk])), reverse("personnel:person_list")
        )
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project(), "Tontechnik", anna)
        refused = self.client.post(reverse("personnel:person_delete", args=[anna.pk]), follow=True)
        self.assertIn("kann nicht gelöscht werden", " ".join(self.messages_of(refused)))
        self.assertTrue(Person.objects.filter(pk=anna.pk).exists())

    def test_export_and_anonymise(self) -> None:
        """NFA-009."""
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, email="anna@example.de")
        project = make_project("Stadtfest")
        plan(project, "Tontechnik", anna)
        exported = self.client.get(reverse("personnel:person_export", args=[anna.pk]))
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported["Content-Disposition"])
        document = json.loads(exported.content)
        self.assertEqual(document["person"]["email"], "anna@example.de")
        self.assertEqual(document["deployments"][0]["project_name"], "Stadtfest")

        done = self.client.post(reverse("personnel:person_anonymise", args=[anna.pk]), follow=True)
        page = self.assert_ok(done)
        self.assertIn(f"Anonymisiert ({anna.pk})", page)
        self.assertNotIn("anna@example.de", page)
        self.assertNotIn("Anna Becker", page)
        # An anonymised person can no longer be edited.
        edit = self.client.get(reverse("personnel:person_edit", args=[anna.pk]), follow=True)
        self.assertIn("anonymisiert", " ".join(self.messages_of(edit)))
        # The deployment stays in the project, without the name.
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertIn(f"Anonymisiert ({anna.pk})", planning)
        self.assertNotIn("Anna Becker", planning)

    def test_personnel_pages_need_the_module(self) -> None:
        """NFA-010."""
        anna = make_person("Anna Becker")
        warehouse = self.browser_for("luka", "Lager")
        for name, arguments in (
            ("personnel:person_list", []),
            ("personnel:person_detail", [anna.pk]),
            ("personnel:person_edit", [anna.pk]),
            ("personnel:availability", []),
            ("personnel:job_function_list", []),
            ("personnel:person_export", [anna.pk]),
        ):
            self.assertEqual(warehouse.get(reverse(name, args=arguments)).status_code, 403, name)
        self.assertNotIn('href="/personnel/"', self.assert_ok(warehouse.get(reverse("core:home"))))

    def test_a_reader_changes_nothing(self) -> None:
        anna = make_person("Anna Becker")
        reader = self.browser_for("paula", "Projektleitung")  # reads personnel
        page = self.assert_ok(reader.get(reverse("personnel:person_detail", args=[anna.pk])))
        self.assertNotIn("Person bearbeiten", page)
        self.assertNotIn("Anonymisieren", page)
        for name in (
            "personnel:person_edit",
            "personnel:person_set_active",
            "personnel:absence_add",
            "personnel:rate_set",
        ):
            self.assertEqual(reader.post(reverse(name, args=[anna.pk]), {}).status_code, 403, name)
        self.assertEqual(reader.post(reverse("personnel:person_anonymise", args=[anna.pk])).status_code, 403)


class RatePageTests(UiTestCase):
    """PER-005, PER-007, PER-010."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.detail = reverse("personnel:person_detail", args=[self.anna.pk])
        self.sound = job_function("Tontechnik")

    def test_assign_a_job_function_with_its_rate(self) -> None:
        hand = job_function("Stagehand")
        page = self.client.get(self.detail)
        done = self.client.post(
            reverse("personnel:rate_set", args=[self.anna.pk]),
            form_data(page, containing="hourly_rate", job_function=hand.pk, hourly_rate="20,00"),
            follow=True,
        )
        self.assertIn("Stagehand: Satz gespeichert", " ".join(self.messages_of(done)))
        self.assertEqual(services.rate_on(self.anna, hand), Decimal("20.00"))
        self.assertIn("20,00", self.assert_ok(done))

    def test_a_later_rate_keeps_the_old_one_as_history(self) -> None:
        page = self.client.get(self.detail)
        self.client.post(
            reverse("personnel:rate_set", args=[self.anna.pk]),
            form_data(
                page, containing="hourly_rate", job_function=self.sound.pk, hourly_rate="38", valid_from="2027-07-01"
            ),
        )
        self.assertEqual(services.rate_on(self.anna, self.sound, datetime.date(2027, 6, 30)), Decimal("35.00"))
        self.assertEqual(services.rate_on(self.anna, self.sound, datetime.date(2027, 7, 1)), Decimal("38.00"))
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("35,00", page)
        self.assertIn("38,00", page)
        self.assertIn("01.07.2027", page)

    def test_take_a_job_function_away(self) -> None:
        self.client.post(reverse("personnel:rate_remove", args=[self.anna.pk, self.sound.pk]))
        self.assertFalse(services.has_job_function(self.anna, self.sound))

    def test_rates_are_invisible_and_unchangeable_without_the_cost_right(self) -> None:
        """AUT-019."""
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        browser = self.browser_for("pit", "Personal ohne Kosten")
        page = self.assert_ok(browser.get(self.detail))
        self.assertIn("Tontechnik", page)
        self.assertNotIn("35,00", page)
        self.assertNotIn("Satz speichern", page)
        refused = browser.post(
            reverse("personnel:rate_set", args=[self.anna.pk]), {"job_function": self.sound.pk, "hourly_rate": "1"}
        )
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(
            browser.post(reverse("personnel:rate_remove", args=[self.anna.pk, self.sound.pk])).status_code, 403
        )
        self.assertEqual(services.rate_on(self.anna, self.sound), Decimal("35.00"))
        # Not in the history of the person either.
        self.assertNotIn("35.00", page)


class JobFunctionPageTests(UiTestCase):
    """PER-004, PER-008, PRJ-052."""

    def test_create_with_service_product_and_guide_value(self) -> None:
        """The service product comes with the function (PRD-044): no product to choose."""
        url = reverse("personnel:job_function_create")
        form = self.client.get(url)
        self.assertNotIn('name="service_product"', self.assert_ok(form))
        self.client.post(url, form_data(form, name="Pyrotechnik", price="45.00", guide_cost_rate="40"))
        function = JobFunction.objects.get(name="Pyrotechnik")
        product = function.service_product
        self.assertEqual(
            (product.name, product.price, function.guide_cost_rate), ("Pyrotechnik", Decimal("45.00"), Decimal("40"))
        )

        listed = self.assert_ok(self.client.get(reverse("personnel:job_function_list")))
        row = listed[listed.index("Pyrotechnik</a>") :]
        self.assertIn(product.article_number, row)
        self.assertIn("45,00", row)
        self.assertIn("40,00", row)

    def test_suggested_job_functions_exist_and_can_be_deactivated(self) -> None:
        listed = self.assert_ok(self.client.get(reverse("personnel:job_function_list")))
        # PER-037: the job functions of the start data.
        for name in ("Techniker", "Tontechniker", "Lichttechniker", "Medientechniker", "Stagehand", "Sonstiges"):
            self.assertIn(name, listed)
        driver = job_function("Sonstiges")
        url = reverse("personnel:job_function_edit", args=[driver.pk])
        self.client.post(url, form_data(self.client.get(url), is_active=None))
        self.assertFalse(JobFunction.objects.get(pk=driver.pk).is_active)

    def test_delete_is_refused_while_in_use(self) -> None:
        make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        sound = job_function("Tontechnik")
        refused = self.client.post(reverse("personnel:job_function_delete", args=[sound.pk]), follow=True)
        self.assertIn("wird verwendet", " ".join(self.messages_of(refused)))
        unused = job_function("Fahrer")
        self.client.post(reverse("personnel:job_function_delete", args=[unused.pk]))
        self.assertFalse(JobFunction.objects.filter(pk=unused.pk).exists())

    def test_guide_value_is_hidden_without_the_cost_right(self) -> None:
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        browser = self.browser_for("pit", "Personal ohne Kosten")
        sound = job_function("Tontechnik", price="45.00", guide="32.00")
        self.assertNotIn("32,00", self.assert_ok(browser.get(reverse("personnel:job_function_list"))))
        form = self.assert_ok(browser.get(reverse("personnel:job_function_edit", args=[sound.pk])))
        self.assertNotIn("guide_cost_rate", form)
        # Saving the form without the field leaves the value alone.
        url = reverse("personnel:job_function_edit", args=[sound.pk])
        browser.post(url, form_data(browser.get(url), name="Tontechnik FOH"))
        sound.refresh_from_db()
        self.assertEqual((sound.name, sound.guide_cost_rate), ("Tontechnik FOH", Decimal("32.00")))


class AbsenceAndAvailabilityPageTests(UiTestCase):
    """PER-011, VFG-009, VFG-010."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Lichttechnik": "38.00"})
        self.project = make_project("Stadtfest")
        plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 22))

    def test_enter_and_delete_an_absence(self) -> None:
        detail = reverse("personnel:person_detail", args=[self.tom.pk])
        self.client.post(
            reverse("personnel:absence_add", args=[self.tom.pk]),
            form_data(
                self.client.get(detail),
                containing="kind",
                kind="vacation",
                start="2027-03-09T00:00",
                end="2027-03-16T00:00",
            ),
        )
        absence = self.tom.absences.get()
        self.assertEqual((absence.kind, absence.start, absence.end), ("vacation", at(9), at(16)))
        self.assertIn("Urlaub", self.assert_ok(self.client.get(detail)))
        self.client.post(reverse("personnel:absence_delete", args=[self.tom.pk, absence.pk]))
        self.assertEqual(self.tom.absences.count(), 0)

    def test_absence_during_a_deployment_warns(self) -> None:
        """PRJ-022."""
        detail = reverse("personnel:person_detail", args=[self.anna.pk])
        done = self.client.post(
            reverse("personnel:absence_add", args=[self.anna.pk]),
            form_data(
                self.client.get(detail),
                containing="kind",
                kind="sick",
                start="2027-03-10T00:00",
                end="2027-03-11T00:00",
            ),
            follow=True,
        )
        messages = " ".join(self.messages_of(done))
        self.assertIn("Abwesenheit gespeichert", messages)
        self.assertIn("Stadtfest", messages)
        self.assertEqual(self.anna.absences.count(), 1)

    def test_who_is_free(self) -> None:
        services.save_absence(Absence(person=self.tom, kind="vacation", start=at(9), end=at(16)))
        lea = make_person("Lea Vogel", rates={"Tontechnik": "25.00"})
        url = reverse("personnel:availability")
        page = self.assert_ok(self.client.get(url, {"start": "2027-03-10T09:00", "end": "2027-03-10T18:00"}))
        self.assertLess(page.index("Vogel, Lea"), page.index("Becker, Anna"))
        self.assertLess(page.index("Becker, Anna"), page.index("Richter, Tom"))
        anna_row = page[page.index("Becker, Anna") : page.index("Richter, Tom")]
        self.assertIn("eingeplant", anna_row)
        self.assertIn("Stadtfest", anna_row)
        self.assertIn("abwesend", page[page.index("Richter, Tom") :])
        self.assertIn("frei", page[page.index("Vogel, Lea") : page.index("Becker, Anna")])

        # VFG-010: who is free and can do sound?
        sound = job_function("Tontechnik")
        page = self.assert_ok(
            self.client.get(url, {"start": "2027-03-10T09:00", "end": "2027-03-10T18:00", "job_function": sound.pk})
        )
        self.assertIn("Vogel, Lea", page)
        self.assertNotIn("Richter, Tom", page)
        self.assertEqual(lea.rates.count(), 1)

    def test_without_a_question_tomorrow_is_shown(self) -> None:
        page = self.assert_ok(self.client.get(reverse("personnel:availability")))
        # PRJ-068: noon to noon of the next day.
        self.assertIn('value="2027-03-02T12:00"', page)
        self.assertIn('value="2027-03-03T12:00"', page)
        self.assertIn("Becker, Anna", page)

    def test_a_reversed_period_is_pointed_out(self) -> None:
        page = self.assert_ok(
            self.client.get(reverse("personnel:availability"), {"start": "2027-03-10T18:00", "end": "2027-03-10T09:00"})
        )
        self.assertIn("Das Ende muss nach dem Beginn liegen", page)


class OwnProfilePageTests(UiTestCase):
    """PER-012, PER-019, PER-010: what people decide and see about themselves."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("frieda", roles=("Freie Kraft",))
        self.person = make_person(
            "Frieda Frei", rates={"Stagehand": "20.00"}, user=self.user, phone="0151 1", note="intern: zuverlässig"
        )
        self.browser = self.browser_of(self.user)
        self.url = reverse("personnel:own_profile")

    def test_release_the_phone_number_for_colleagues(self) -> None:
        page = self.browser.get(self.url)
        text = self.assert_ok(page)
        self.assertNotIn("zuverlässig", text)  # internal notes are not shown to the person … on this page
        self.browser.post(self.url, form_data(page, containing="phone", share_phone="on", phone="0151 2"))
        self.person.refresh_from_db()
        self.assertEqual((self.person.share_phone, self.person.share_email, self.person.phone), (True, False, "0151 2"))

    def test_own_rates_show_unless_switched_off(self) -> None:
        """PER-010."""
        self.assertIn("20,00", self.assert_ok(self.browser.get(self.url)))
        from rentalars.core.models import SystemSettings

        settings = SystemSettings.load()
        settings.people_see_own_rates = False
        settings.save()
        page = self.assert_ok(self.browser.get(self.url))
        self.assertNotIn("20,00", page)
        self.assertIn("Stundensätze werden hier nicht angezeigt", page)

    def test_enter_own_absence(self) -> None:
        """PER-012."""
        self.browser.post(
            reverse("personnel:own_absence_add"),
            form_data(self.browser.get(self.url), containing="kind", start="2027-03-20T00:00", end="2027-03-22T00:00"),
        )
        absence = self.person.absences.get()
        self.assertEqual(absence.kind, "unavailable")
        self.assertIn("nicht verfügbar", self.assert_ok(self.browser.get(self.url)))
        self.browser.post(reverse("personnel:own_absence_delete", args=[absence.pk]))
        self.assertEqual(self.person.absences.count(), 0)

    def test_nobody_deletes_the_absence_of_somebody_else(self) -> None:
        anna = make_person("Anna Becker")
        services.save_absence(Absence(person=anna, start=at(20), end=at(22)))
        response = self.browser.post(reverse("personnel:own_absence_delete", args=[anna.absences.get().pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(anna.absences.count(), 1)

    def test_own_deployments_are_listed_on_the_start_page_and_the_profile(self) -> None:
        """PRJ-023, AUT-012."""
        project = make_project("Stadtfest")
        plan(project, "Stagehand", self.person, start=at(10, 8), end=at(10, 14), meeting_point="Rampe")
        home = self.assert_ok(self.browser.get(reverse("core:home")))
        block = home[home.index("Meine Einsätze") :]
        for shown in ("Stadtfest", "Stagehand", "Rampe", reverse("projects:deployment", args=[project.pk])):
            self.assertIn(shown, block)
        self.assertIn("Stadtfest", self.assert_ok(self.browser.get(self.url)))
        self.assertIn(self.url, self.assert_ok(self.browser.get(reverse("accounts:account"))))

    def test_every_account_has_a_profile(self) -> None:
        """AUT-026: an account made in the user administration is a person too."""
        loose = make_user("lose", roles=("Crew",))
        browser = self.browser_of(loose)
        self.assertIn("lose", self.assert_ok(browser.get(self.url)))
        self.assertIn(self.url, self.assert_ok(browser.get(reverse("accounts:account"))))
