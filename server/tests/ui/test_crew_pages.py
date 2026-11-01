# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: the block "personnel" of the planning, the deployment view, project members.

PRJ-019 to PRJ-023, PRJ-038, PRJ-051, PRJ-052, PRJ-061, ZEI-021, AUT-016 to AUT-025.
"""

from __future__ import annotations

from decimal import Decimal

from django.urls import get_resolver, reverse

from rentalars.accounts.models import Role
from rentalars.mail.models import MailAttachment, ProjectMail
from rentalars.masterdata.models import Supplier
from rentalars.packing.models import Packlist
from rentalars.personnel import services as personnel
from rentalars.personnel.models import Absence
from rentalars.projects.logistics import add_vehicle_line
from rentalars.projects.models import (
    CrewLine,
    OpenItem,
    Project,
    ProjectFile,
    ProjectMembership,
    ProjectPhase,
    ServiceCaseParticipant,
    TripVehicle,
)
from rentalars.projects.relations import link
from tests.helpers import (
    ALL_RIGHTS,
    ASSIGNED_READER,
    add_group,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    record_time,
)
from tests.ui.base import UiTestCase, form_data

D = Decimal


class CrewBlockTests(UiTestCase):
    """The block "personnel" on the planning page."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 10), end=at(14, 18))
        self.sound = job_function("Tontechnik", price="45.00", guide="32.00")
        self.hand = job_function("Stagehand", price="28.00", guide="18.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.planning = reverse("projects:detail", args=[self.project.pk])
        self.add = reverse("projects:crew_add", args=[self.project.pk])

    def crew_block(self, text: str) -> str:
        start = text.index('id="planning-crew"')
        return text[start : text.index("</section>", start)]

    def test_plan_a_person_from_the_planning_page(self) -> None:
        """PRJ-019, PRJ-021: answered with the refreshed block – the page is not left."""
        page = self.client.get(self.planning)
        answer = self.htmx(
            "post",
            self.add,
            form_data(
                page,
                containing="job_function",
                job_function=self.sound.pk,
                person=self.anna.pk,
                start="2027-03-13T08:00",
                end="2027-03-13T22:00",
            ),
        )
        block = self.crew_block(self.assert_ok(answer))
        line = CrewLine.objects.get()
        self.assertEqual(
            (line.person, line.start, line.end, line.planned_hours, line.hourly_rate),
            (self.anna, at(13, 8), at(13, 22), D("14.00"), D("35.00")),
        )
        for shown in (
            "Anna Becker",
            "Tontechnik, Stunde",
            "Sa 13.03. 08:00",
            "630,00",
            "490,00",
            "Zwischensumme Personal",
        ):
            self.assertIn(shown, block)

    def test_the_period_starts_as_the_project_period(self) -> None:
        page = self.assert_ok(self.client.get(self.planning))
        self.assertIn('value="2027-03-12T10:00"', page)
        self.assertIn('value="2027-03-14T18:00"', page)

    def test_plan_open_places_and_fill_one_later(self) -> None:
        """PRJ-020, PRJ-052: "2 × stagehand, Saturday 08–14"."""
        page = self.client.get(self.planning)
        answer = self.htmx(
            "post",
            self.add,
            form_data(
                page,
                containing="job_function",
                job_function=self.hand.pk,
                count="2",
                start="2027-03-13T08:00",
                end="2027-03-13T14:00",
            ),
        )
        block = self.crew_block(self.assert_ok(answer))
        self.assertEqual(CrewLine.objects.filter(person__isnull=True, planned_hours=6).count(), 2)
        self.assertIn("2 Plätze offen", block)
        self.assertIn("Richtwert", block)
        self.assertIn("108,00", block)  # 6 h × guide value 18.00

        lea = make_person("Lea Vogel", rates={"Stagehand": "16.00"})
        place = CrewLine.objects.first()
        url = reverse("projects:crew_edit", args=[self.project.pk, place.pk])
        dialog = self.htmx("get", url)
        self.assertIn("Stagehand, Stunde", self.assert_ok(dialog))
        saved = self.htmx("post", url, form_data(dialog, person=lea.pk))
        self.assertIn("closeDialog", saved["HX-Trigger"])
        place.refresh_from_db()
        self.assertEqual((place.person, place.hourly_rate), (lea, D("16.00")))
        self.assertIn("1 Platz offen", self.crew_block(self.assert_ok(saved)))

    def test_edit_period_hours_flat_rate_and_billing_in_the_dialog(self) -> None:
        """PRJ-023, PER-018, PRJ-061."""
        line = plan(self.project, self.sound, self.anna, start=at(13, 8), end=at(13, 14))
        url = reverse("projects:crew_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)
        text = self.assert_ok(dialog)
        # From and until stand next to each other (UIX-014); no browser history in the fields.
        self.assertRegex(text, r'(?s)<div class="form-row pair">.*?name="start".*?name="end".*?</div>')
        self.assertIn('autocomplete="off"', text)

        self.htmx("post", url, form_data(dialog, end="2027-03-13T18:00", meeting_point="FOH", note="bringt Funke mit"))
        line.refresh_from_db()
        self.assertEqual((line.planned_hours, line.meeting_point, line.note), (D("10.00"), "FOH", "bringt Funke mit"))

        dialog = self.htmx("get", url)
        self.htmx("post", url, form_data(dialog, billing="effort", cost_flat_rate="300,00", planned_hours="8"))
        line.refresh_from_db()
        self.assertEqual((line.billing, line.cost_flat_rate, line.planned_hours), ("effort", D("300.00"), D("8.00")))
        block = self.crew_block(self.assert_ok(self.client.get(self.planning)))
        for shown in ("nach Aufwand", "Schätzung", "Pauschale", "300,00", "360,00", "Treffpunkt: FOH"):
            self.assertIn(shown, block)

    def test_an_invalid_period_stays_in_the_dialog(self) -> None:
        line = plan(self.project, self.sound, self.anna, start=at(13, 8), end=at(13, 14))
        url = reverse("projects:crew_edit", args=[self.project.pk, line.pk])
        answer = self.htmx("post", url, form_data(self.htmx("get", url), end="2027-03-13T07:00"))
        self.assertIn("Das Ende muss nach dem Beginn liegen", self.assert_ok(answer))
        self.assertNotIn("HX-Trigger", answer)

    def test_a_person_outside_their_job_functions_is_refused_or_pointed_out(self) -> None:
        """PER-006."""
        Role.objects.create(name="Planung", module_levels={"projects": 2, "personnel": 1})
        planner = self.browser_for("pia", "Planung")
        data = form_data(
            planner.get(self.planning), containing="job_function", job_function=self.hand.pk, person=self.anna.pk
        )
        refused = self.htmx("post", self.add, data, client=planner)
        self.assertIn("hat die Funktion Stagehand nicht", self.assert_ok(refused))
        self.assertEqual(CrewLine.objects.count(), 0)

        allowed = self.htmx("post", self.add, data)  # the administrator may deviate
        self.assertEqual(CrewLine.objects.count(), 1)
        self.assertIn("Stagehand gehört nicht zu den Funktionen dieser Person", self.assert_ok(allowed))

    def test_double_booking_and_absence_show_at_the_line(self) -> None:
        """PRJ-022."""
        other = make_project("Jazznacht", start=at(13), end=at(14))
        plan(other, self.sound, self.anna, start=at(13, 16), end=at(13, 23))
        personnel.save_absence(Absence(person=self.anna, kind="vacation", start=at(13), end=at(15)))
        plan(self.project, self.sound, self.anna, start=at(13, 8), end=at(13, 18))
        block = self.crew_block(self.assert_ok(self.client.get(self.planning)))
        self.assertIn("Auch in", block)
        self.assertIn(
            f"Projekt {other.number}", block
        )  # By number only – the reader may not open the other project (AUT-016)
        self.assertIn("Abwesend (Urlaub)", block)

    def test_delete_a_crew_line(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        answer = self.htmx("post", reverse("projects:crew_delete", args=[self.project.pk, line.pk]))
        self.assertIn("Noch niemand eingeplant", self.assert_ok(answer))
        self.assertEqual(CrewLine.objects.count(), 0)

    def test_crew_is_a_block_of_its_own_and_counts_in_the_totals(self) -> None:
        """PRJ-038."""
        group = add_group(self.project, "Ton FOH")
        add_line(self.project, make_product("T-030", "Digitalmischpult", price="100.00"), 1, group=group, rental_days=1)
        plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        page = self.assert_ok(self.client.get(self.planning))
        group_block = page[page.index("Ton FOH") : page.index('id="planning-crew"')]
        self.assertNotIn("Tontechniker", group_block)
        totals = page[page.index('id="planning-totals"') :]
        for shown in ("Personal", "360,00", "460,00", "Personalkosten (geplant)", "280,00"):
            self.assertIn(shown, totals)

        overview = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn("Tontechnik, Stunde", overview[overview.index("Personal") :])

    def test_prices_and_costs_follow_the_rights(self) -> None:
        """AUT-019."""
        plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        Role.objects.create(name="Planung", module_levels={"projects": 2, "personnel": 2})
        planner = self.browser_for("pia", "Planung")
        page = self.assert_ok(planner.get(self.planning))
        block = self.crew_block(page)
        self.assertIn("Anna Becker", block)
        for hidden in ("45,00", "360,00", "35,00", "280,00", "Zwischensumme Personal"):
            self.assertNotIn(hidden, page)
        dialog = self.assert_ok(
            self.htmx(
                "get", reverse("projects:crew_edit", args=[self.project.pk, CrewLine.objects.get().pk]), client=planner
            )
        )
        for hidden in ("unit_price", "hourly_rate", "cost_flat_rate", "billing"):
            self.assertNotIn(f'name="{hidden}"', dialog)

    def test_personnel_planning_plans_without_editing_the_project(self) -> None:
        """Catalogue chapter 4."""
        planner = self.browser_for("dora", "Personaldisposition")
        page = self.assert_ok(planner.get(self.planning))
        self.assertIn(self.add, page)
        self.assertNotIn(reverse("projects:line_add", args=[self.project.pk]), page)
        self.htmx(
            "post",
            self.add,
            form_data(
                planner.get(self.planning), containing="job_function", job_function=self.sound.pk, person=self.anna.pk
            ),
            client=planner,
        )
        self.assertEqual(CrewLine.objects.count(), 1)

    def test_the_warehouse_sees_the_crew_but_cannot_plan(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        warehouse = self.browser_for("luka", "Lager")
        page = self.assert_ok(warehouse.get(self.planning))
        self.assertIn("Anna Becker", self.crew_block(page))
        self.assertNotIn(self.add, page)
        self.assertEqual(warehouse.post(self.add, {"job_function": self.hand.pk}).status_code, 403)
        self.assertEqual(
            warehouse.post(reverse("projects:crew_delete", args=[self.project.pk, line.pk])).status_code, 403
        )

    def test_approved_times_without_crew_line_show_and_can_be_taken_over(self) -> None:
        """ZEI-021."""
        plan(self.project, self.sound, self.anna, start=at(13, 8), end=at(13, 18), planned_hours=D("8"))
        record_time(self.anna, self.project, self.sound, at(13, 8), at(13, 17), approve=True)
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        record_time(kai, self.project, self.hand, at(13, 8), at(13, 14), approve=True)

        block = self.crew_block(self.assert_ok(self.client.get(self.planning)))
        self.assertIn("geleistet 9", block)  # planned and worked hours side by side
        self.assertIn("Freigegebene Zeiten ohne Personalposition", block)
        self.assertIn("Kai Kurz, Stagehand", block)

        answer = self.htmx(
            "post",
            reverse("projects:crew_times", args=[self.project.pk]),
            {"person": kai.pk, "job_function": self.hand.pk, "line": "new"},
        )
        block = self.crew_block(self.assert_ok(answer))
        self.assertNotIn("Freigegebene Zeiten ohne Personalposition", block)
        adopted = CrewLine.objects.get(person=kai)
        self.assertEqual((adopted.planned_hours, adopted.billing), (D("6.00"), "effort"))


class DeploymentViewTests(UiTestCase):
    """AUT-018, AUT-023, AUT-025, PER-019: what crew sees of a project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", venue="Marktplatz")
        add_line(self.project, make_product("L-010", "LED-Scheinwerfer", price="23.45"), 4, rental_days=1)
        self.user = make_user("carla", roles=("Crew",))
        self.person = make_person("Carla Crew", rates={"Stagehand": "20.00"}, user=self.user)
        plan(
            self.project,
            job_function("Stagehand", price="28.00"),
            self.person,
            start=at(10, 8),
            end=at(10, 14),
            meeting_point="Rampe",
            note="Sicherheitsschuhe",
        )
        self.browser = self.browser_of(self.user)
        self.url = reverse("projects:deployment", args=[self.project.pk])

    def test_the_project_page_leads_crew_to_the_deployment_view(self) -> None:
        response = self.browser.get(reverse("projects:detail", args=[self.project.pk]))
        self.assertRedirects(response, self.url)

    def test_time_place_job_function_and_own_note(self) -> None:
        page = self.assert_ok(self.browser.get(self.url))
        for shown in ("Marktplatz", "Stagehand", "Rampe", "Sicherheitsschuhe", "Mi 10.03.2027 08:00", "6 Std."):
            self.assertIn(shown, page)
        # Only the tabs of the deployment view.
        tabs = page[page.index('<nav class="tabs"') : page.index("</nav>", page.index('<nav class="tabs"'))]
        # PRJ-104: "Überblick"; the packlist comes first.
        self.assertIn("Überblick", tabs)
        self.assertNotIn(">Einsatz<", tabs)
        # (tab order; PRJ-125) adapted: "Überblick" is the first tab, before the packlist.
        self.assertLess(tabs.index("Überblick"), tabs.index("Packliste"))
        for hidden in ("Planung", "Preisübersicht", "Zugriff", "Verlauf"):
            self.assertNotIn(hidden, tabs)
        for hidden in ("23,45", "28,00", "Projekt bearbeiten"):
            self.assertNotIn(hidden, page)
        # PRJ-122: the customer's name shows in every role – as text, no link.
        self.assertIn("Stadtwerke", page)
        self.assertNotIn("/customers/", page)

    def test_own_times_in_the_project_and_the_way_to_record_one(self) -> None:
        record_time(self.person, self.project, "Stagehand", at(10, 8), at(10, 14), submit=True)
        page = self.assert_ok(self.browser.get(self.url))
        times = page[page.index("Meine Zeiten in diesem Projekt") :]
        self.assertIn("eingereicht", times)
        self.assertIn(f"{reverse('timetracking:quick')}?project={self.project.pk}", times)

    def test_a_project_without_assignment_is_not_found(self) -> None:
        other = make_project("Jazznacht")
        for name in ("projects:deployment", "projects:detail", "packing:packlist"):
            self.assertEqual(self.browser.get(reverse(name, args=[other.pk])).status_code, 404, name)

    def test_project_list_and_start_page_show_own_deployments_with_the_customers_name(self) -> None:
        """PRJ-122: the name of the customer shows in every role – only of the projects the role sees."""
        make_project("Jazznacht")
        for name in ("projects:list", "core:home"):
            page = self.assert_ok(self.browser.get(reverse(name)))
            self.assertIn("Stadtfest", page, name)
            self.assertNotIn("Jazznacht", page, name)
            self.assertIn("Stadtwerke", page, name)
            self.assertNotIn("/customers/", page, name)  # a name, no link
        # What is shown can be searched for – among the projects the role sees.
        page = self.assert_ok(self.browser.get(reverse("projects:list"), {"q": "Stadtwerke"}))
        self.assertIn("Stadtfest", page)
        self.assertNotIn("Jazznacht", page)
        page = self.assert_ok(self.browser.get(reverse("core:search"), {"q": "Stadtwerke"}))
        self.assertIn("Stadtfest", page)
        self.assertNotIn("Jazznacht", page)

    def test_readers_of_the_project_use_the_page_as_a_crew_sheet(self) -> None:
        make_person("Tom Richter", rates={"Lichttechnik": "38.00"}, phone="0171 5550102")
        plan(self.project, "Lichttechnik", make_person("Tim Tief", phone="0171 1"))
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Carla Crew", page)
        self.assertIn("0171 1", page)  # all contact data for project management (PER-019)
        self.assertIn("Du bist in diesem Projekt selbst nicht eingeplant", page)


class MembersPageTests(UiTestCase):
    """AUT-016, AUT-018: explicit assignment of users to a project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.user = make_user("frieda", roles=(ASSIGNED_READER,))  # AUT-036
        self.url = reverse("projects:members", args=[self.project.pk])

    def test_add_a_member_change_the_level_and_remove_them(self) -> None:
        browser = self.browser_of(self.user)
        self.assertEqual(browser.get(reverse("projects:detail", args=[self.project.pk])).status_code, 404)

        page = self.client.get(self.url)
        done = self.client.post(
            self.url, form_data(page, containing="user", user=self.user.pk, level="read"), follow=True
        )
        self.assertIn("hat jetzt Zugriff", " ".join(self.messages_of(done)))
        self.assertIn("Stadtfest", self.assert_ok(browser.get(reverse("projects:detail", args=[self.project.pk]))))

        self.client.post(self.url, form_data(page, containing="user", user=self.user.pk, level="deployment"))
        membership = ProjectMembership.objects.get()
        self.assertEqual(membership.level, "deployment")
        self.assertRedirects(
            browser.get(reverse("projects:detail", args=[self.project.pk])),
            reverse("projects:deployment", args=[self.project.pk]),
        )

        self.client.post(reverse("projects:member_remove", args=[self.project.pk, membership.pk]))
        self.assertEqual(browser.get(reverse("projects:detail", args=[self.project.pk])).status_code, 404)

    def test_people_planned_through_a_crew_line_are_listed_for_information(self) -> None:
        person = make_person("Frieda Frei", rates={"Stagehand": "20.00"}, user=self.user)
        plan(self.project, "Stagehand", person)
        page = self.assert_ok(self.client.get(self.url))
        # AUT-035: in the one list of everybody with access, with the job function as the reason.
        self.assertIn("eingeplant als Stagehand", page)
        self.assertIn("Frieda Frei", page)

    def test_a_reader_sees_the_members_but_does_not_change_them(self) -> None:
        ProjectMembership.objects.create(project=self.project, user=self.user, level="read")
        browser = self.browser_of(self.user)
        page = self.assert_ok(browser.get(self.url))
        self.assertIn("frieda", page)
        self.assertNotIn("Mitglied hinzufügen", page)
        self.assertEqual(browser.post(self.url, {"user": self.user.pk, "level": "edit"}).status_code, 403)
        membership = ProjectMembership.objects.get()
        self.assertEqual(
            browser.post(reverse("projects:member_remove", args=[self.project.pk, membership.pk])).status_code, 403
        )
        self.assertEqual(ProjectMembership.objects.get().level, "read")

    def test_membership_changes_are_in_the_history_of_the_project(self) -> None:
        self.client.post(self.url, {"user": self.user.pk, "level": "read"})
        history = self.assert_ok(self.client.get(reverse("projects:history", args=[self.project.pk])))
        self.assertIn("frieda", history)


class NoPageForgetsToAskTests(UiTestCase):
    """AUT-020: every page below a project asks whether the user may see that project.

    The addresses are read from the address table, so a page added later is
    walked too – without anybody having to remember this test.
    """

    #: Addresses with ``<int:pk>`` of a project, by the modules that define them.
    MODULES = ("rentalars.projects.urls", "rentalars.packing.urls", "rentalars.mail.urls")

    def project_addresses(self, project: Project, other_ids: dict[str, int]) -> list[tuple[str, str]]:
        addresses = []
        for pattern in get_resolver().url_patterns:
            module = getattr(getattr(pattern, "urlconf_module", None), "__name__", "")
            if module not in self.MODULES:
                continue
            for entry in pattern.url_patterns:
                names = entry.pattern.converters
                if "pk" not in names:
                    continue
                arguments = {"pk": project.pk}
                for name in names:
                    if name == "action":
                        arguments[name] = "issue"
                    elif name != "pk":
                        arguments[name] = other_ids[name]
                addresses.append((entry.name, reverse(f"{pattern.namespace}:{entry.name}", kwargs=arguments)))
        return addresses

    def test_a_foreign_project_is_not_found_on_any_page_by_any_method(self) -> None:
        foreign = make_project("Jazznacht")
        group = add_group(foreign, "Licht")
        line = add_line(foreign, make_product("L-010", price="20.00"), 1, group=group).line
        crew_line = plan(foreign, "Stagehand")
        membership = ProjectMembership.objects.create(project=foreign, user=self.admin_user, level="read")
        # Stage 4: phases, open items, files and mails of the foreign project (PRJ-006/007/059, EML-019).
        phase = ProjectPhase.objects.create(project=foreign, start=foreign.start, end=foreign.end)
        item = OpenItem.objects.create(project=foreign, text="Aufbauzeiten")
        project_file = ProjectFile.objects.create(project=foreign, file="projects/x/plan.pdf", original_name="plan.pdf")
        mail = ProjectMail.objects.create(project=foreign, message_key="k" * 64, message_id="<a@b>", subject="Jazz")
        attachment = MailAttachment.objects.create(mail=mail, file="mail/x/a.pdf", filename="a.pdf")
        # Stage 5: a further packlist (PCK-008).
        Packlist.objects.create(project=foreign)
        second = Packlist.objects.create(project=foreign, title="LKW 2")
        ids = {
            "packlist_pk": second.pk,
            "line_pk": line.pk,
            "group_pk": group.pk,
            "membership_pk": membership.pk,
            "phase_pk": phase.pk,
            "item_pk": item.pk,
            "file_pk": project_file.pk,
            "mail_pk": mail.pk,
            "attachment_pk": attachment.pk,
            # PRJ-106: the page of the subrentals at a supplier.
            "supplier_pk": Supplier.objects.create(name="Verleih Nord").pk,
            # PRJ-108: a person taking part in a service case.
            "participant_pk": ServiceCaseParticipant.objects.create(project=foreign, person=make_person("Pia")).pk,
            # PRJ-111: a trip of the project, named by its key.
            "key": f"to_venue-{phase.pk}",
            # PRJ-119: a relation of the foreign project.
            "relation_pk": link(foreign, make_project("Nachbarfest")).pk,
        }
        # LOG-001: a vehicle booking and a vehicle on a trip of the foreign project.
        vehicle_product = make_product(
            "S-900", price=None, kind="vehicle", vehicle_type="car", price_per_km=Decimal("0.80")
        )
        vehicle_line = add_vehicle_line(foreign, rights=ALL_RIGHTS, product=vehicle_product)
        ids["use_pk"] = TripVehicle.objects.create(project=foreign, trip_key=ids["key"], vehicle_line=vehicle_line).pk

        # The strongest restricted role: may write and delete everything – in assigned projects.
        Role.objects.create(
            name="Projektleitung extern",
            module_levels={"projects": 3, "packing": 3, "personnel": 3, "time_tracking": 3},
            special_rights=[
                "prices",
                "purchase_prices",
                "personnel_costs",
                "approve_times",
                "correspondence_read",
                "correspondence_write",
            ],
            project_scope="assigned",
        )
        browser = self.browser_for("erik", "Projektleitung extern")
        addresses = self.project_addresses(foreign, ids)
        self.assertGreater(len(addresses), 25)
        for name, address in addresses:
            if name in {"crew_edit", "crew_delete", "crew_request", "crew_answer"}:
                address = address.replace(f"/{line.pk}/", f"/{crew_line.pk}/")
            if name in {"vehicle_edit", "vehicle_delete"}:  # LOG-001
                address = address.replace(f"/{line.pk}/", f"/{vehicle_line.pk}/")
            if name.startswith("unknown_"):
                continue  # not a project page: <pk> is a mail of the list of unknown tags
            if name.startswith("legacy_"):
                continue  # Not a project page: <pk> is a batch of the old-project import (PRJ-130)
            for method in ("get", "post"):
                response = getattr(browser, method)(address)
                # 405: the page exists only for the other method; it must not reveal anything either.
                self.assertIn(response.status_code, (404, 405), f"{method.upper()} {name}")
                if response.status_code == 405:
                    self.assertNotIn("Jazznacht", response.content.decode())

        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "confirmed")
        self.assertEqual(
            (foreign.groups.count(), foreign.material_lines.count(), foreign.crew_lines.count()), (1, 1, 1)
        )
        self.assertEqual(ProjectMembership.objects.count(), 1)
