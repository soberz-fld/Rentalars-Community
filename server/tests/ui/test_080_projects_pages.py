# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "projects": "In Teilprojekte gliedern" (PRJ-050), Projekte → Servicefälle and the page of a
case (PRJ-090), show files among the files of a project (PRJ-089)."""

from __future__ import annotations

import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import ProjectMail, UnknownTagMail
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, Group, MaterialLine, Project, ProjectFile, ProjectStatus
from rentalars.projects.showfiles import showfile_type
from tests.helpers import add_group, add_line, at, make_customer, make_person, make_project, make_stock, make_user, plan
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data


def tabs_of(text: str) -> list[str]:
    """The labels of the first row of tabs of a page."""
    start = text.index('<nav class="tabs"')
    return [label.strip() for label in re.findall(r">([^<>]+)</a>", text[start : text.index("</nav>", start)])]


class SplitPageTests(UiTestCase):
    """PRJ-050: the page "In Teilprojekte gliedern"."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10, 8), end=at(13, 20))
        spots = make_stock("L-010", 10, "Spot")
        self.market = add_group(self.project, "Bühne Marktplatz")
        self.park = add_group(self.project, "Bühne Schlosspark")
        self.power = add_group(self.project, "Strom")
        add_line(self.project, spots, 2, group=self.market)
        add_line(self.project, spots, 3, group=self.park)
        self.crew = plan(self.project, "Lichttechnik", start=at(10, 8), end=at(10, 18))
        self.url = reverse("projects:split", args=[self.project])

    def test_the_head_offers_it_behind_the_arrow_of_add_subproject(self) -> None:
        text = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project])))
        self.assertIn(f'<a href="{self.url}">In Teilprojekte gliedern</a>', text)
        self.assertIn('aria-label="Mehr zu Teilprojekten"', text)

    def test_the_page_shows_the_groups_and_the_crew(self) -> None:
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn("<h1>In Teilprojekte gliedern</h1>", text)
        self.assertIn("Dieses Projekt wird zum Gesamtprojekt.", text)
        self.assertIn(f'name="groups" value="{self.market.pk}"', text)
        self.assertIn("1 Position", text)
        self.assertIn("ihre Positionen und Untergruppen stehen direkt im Teilprojekt", text)
        self.assertIn(f'name="crew_{self.crew.pk}"', text)
        self.assertIn(f'<option value="{self.market.pk}">geht mit „Bühne Marktplatz“</option>', text)
        # ?group= ticks one group.
        ticked = self.assert_ok(self.client.get(f"{self.url}?group={self.park.pk}"))
        self.assertIn(f'name="groups" value="{self.park.pk}" checked', ticked)

    def test_dividing_leads_to_the_overview_of_the_parts(self) -> None:
        data = {"groups": [str(self.market.pk), str(self.park.pk)], f"crew_{self.crew.pk}": str(self.park.pk)}
        response = self.client.post(self.url, data, follow=True)
        text = self.assert_ok(response)
        self.assertEqual(response.redirect_chain[-1][0], reverse("projects:family", args=[self.project]))
        self.assertIn(
            f"2 Teilprojekte angelegt: {self.project.number}-1 Bühne Marktplatz, {self.project.number}-2 Bühne "
            "Schlosspark.",
            self.messages_of(response),
        )
        self.assertIn("Bühne Schlosspark", text)
        park = Project.objects.get(number=f"{self.project.number}-2")
        self.assertEqual(self.crew.__class__.objects.get(pk=self.crew.pk).project, park)
        # Now it is a whole project: the arrow turns further groups into parts.
        head = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project])))
        self.assertIn(f'<a href="{self.url}">Teilgruppen in Teilprojekte umwandeln</a>', head)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("<h1>Teilgruppen in Teilprojekte umwandeln</h1>", page)
        self.assertIn("Strom", page)

    def test_without_a_choice_nothing_happens(self) -> None:
        text = self.assert_ok(self.client.post(self.url, {}))
        self.assertIn("Wähle mindestens eine Teilgruppe.", text)
        self.assertFalse(self.project.subprojects.exists())

    def test_a_crew_line_only_goes_with_a_chosen_group(self) -> None:
        data = {"groups": [str(self.market.pk)], f"crew_{self.crew.pk}": str(self.park.pk)}
        text = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Diese Teilgruppe wird kein Teilprojekt.", text)
        self.assertFalse(self.project.subprojects.exists())

    def test_a_subproject_says_why_not(self) -> None:
        self.client.post(self.url, {"groups": [str(self.market.pk)]})
        part = Project.objects.get(parent=self.project)
        text = self.assert_ok(self.client.get(reverse("projects:split", args=[part])))
        self.assertIn("Ein Teilprojekt lässt sich nicht weiter gliedern", text)
        self.assertNotIn('name="groups"', text)

    def test_only_who_may_change_the_project(self) -> None:
        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(self.url).status_code, 403)
        self.assertEqual(reader.post(self.url, {"groups": [str(self.market.pk)]}).status_code, 403)
        self.assertTrue(Group.objects.filter(pk=self.market.pk, project=self.project).exists())


class ServiceCasePageTests(UiTestCase):
    """PRJ-090: Projekte → Servicefälle, a new case, its page, status, editing and turning it into a project."""

    def test_the_tab_and_a_new_case(self) -> None:
        text = self.assert_ok(self.client.get(reverse("projects:cases")))
        self.assertEqual(tabs_of(text)[:3], ["Projekte", "Offene Punkte", "Servicefälle"])
        self.assertIn('<a href="/projects/service-cases/" aria-current="page">Servicefälle</a>', text)
        self.assertIn("Keine passenden Servicefälle.", text)
        form = self.assert_ok(self.client.get(reverse("projects:case_create")))
        self.assertIn("<h1>Neuer Servicefall</h1>", form)
        self.assertIn('<label for="id_name">Worum geht es?', form)
        # PRJ-090: required, as for a project – unless the case is internal (MAT-057).
        self.assertIn(
            '<label for="id_customer_text">Kunde <span class="required" aria-hidden="true" '
            'data-show-if="is_internal=">*</span></label>',
            form,
        )
        customer = make_customer("Stadtwerke")
        data = form_data(
            self.client.get(reverse("projects:case_create")),
            "name",
            name="Spot flackert",
            customer=str(customer.pk),
            case_contact="",
            notes="Seit gestern, Bühne 2.",
        )
        response = self.client.post(reverse("projects:case_create"), data, follow=True)
        case = Project.objects.get(name="Spot flackert")
        self.assertEqual(response.redirect_chain[-1][0], reverse("projects:case_detail", args=[case]))
        self.assertIn(f"Servicefall {case.number} angelegt.", self.messages_of(response))
        self.assertEqual((case.kind, case.case_status, case.manager), ("service_case", "open", self.admin_user))
        page = self.assert_ok(response)
        self.assertIn('<span class="badge accent">Servicefall</span>', page)
        self.assertIn("Seit gestern, Bühne 2.", page)
        tabs = tabs_of(page)
        self.assertEqual(tabs[0], "Überblick")  # PRJ-090
        self.assertEqual(tabs.count("Überblick"), 1)  # the case's own page, not the deployment view of a project
        for absent in ("Planung", "Preisübersicht", "Zeitplanung", "Packliste"):
            self.assertNotIn(absent, tabs)
        for present in ("Dokumente", "Korrespondenz", "Zugriff", "Verlauf"):
            self.assertIn(present, tabs)
        self.assertIn("Servicefall bearbeiten", page)
        self.assertIn("In Projekt umwandeln", page)
        self.assertNotIn("Status ändern", page)
        self.assertNotIn("Duplizieren", page)
        self.assertIn(f"Noch keine Mails. Mails mit [RL#{case.number}] im Betreff landen hier.", page)
        # The list shows it until it is done.
        listed = self.assert_ok(self.client.get(reverse("projects:cases")))
        self.assertIn("Spot flackert", listed)
        self.assertIn('<span class="badge outline">offen</span>', listed)

    def test_status_and_editing(self) -> None:
        anna = make_user("anna", roles=("Projektleitung",))
        # PRJ-090: an edited case needs a customer.
        case = service_cases.create_case(name="Frage zur Anleitung", customer=make_customer())
        url = reverse("projects:case_status", args=[case])
        response = self.client.post(url, {"case_status": "in_progress"}, follow=True)
        self.assertIn("Der Servicefall ist jetzt „in Arbeit“.", self.messages_of(response))
        self.assertIn('<option value="in_progress" selected>in Arbeit</option>', self.assert_ok(response))
        edit = reverse("projects:case_edit", args=[case])
        data = form_data(self.client.get(edit), "name", manager=str(anna.pk), case_contact="Max, 0170 1")
        self.client.post(edit, data)
        case.refresh_from_db()
        self.assertEqual((case.manager, case.case_contact), (anna, "Max, 0170 1"))
        self.client.post(url, {"case_status": "done"})
        listed = self.assert_ok(self.client.get(reverse("projects:cases")))
        self.assertNotIn("Frage zur Anleitung", listed)
        done = self.assert_ok(self.client.get(reverse("projects:cases") + "?status=done"))
        self.assertIn("Frage zur Anleitung", done)
        self.assertIn('<span class="badge green">erledigt</span>', done)
        mine = self.assert_ok(self.browser_of(anna).get(reverse("projects:cases") + "?status=done&mine=1"))
        self.assertIn("Frage zur Anleitung", mine)

    def test_the_planning_and_the_schedule_lead_to_the_case(self) -> None:
        case = service_cases.create_case(name="Reparatur")
        detail = reverse("projects:case_detail", args=[case])
        self.assertRedirects(self.client.get(reverse("projects:detail", args=[case])), detail)
        self.assertRedirects(
            self.client.get(reverse("projects:edit", args=[case])), reverse("projects:case_edit", args=[case])
        )
        self.assertRedirects(
            self.client.get(reverse("projects:course", args=[case])),
            f"{detail}#open-items",
            fetch_redirect_response=False,
        )
        # A project is no case.
        project = make_project()
        self.assertEqual(self.client.get(reverse("projects:case_detail", args=[project])).status_code, 404)

    def test_open_items_of_a_case(self) -> None:
        """PRJ-090: the open items of a case are on its page and among the open items of all projects."""
        case = service_cases.create_case(name="Ersatzteil bestellen")
        self.client.post(reverse("projects:open_items_add", args=[case.pk]), {"texts": "Lampe bestellen"})
        page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[case])))
        self.assertIn("Lampe bestellen", page)
        overview = self.assert_ok(self.client.get(reverse("projects:open_items")))
        self.assertIn("Lampe bestellen", overview)
        self.assertIn('<span class="badge accent">Servicefall</span> offen', overview)

    def test_the_tabs_it_shares_with_a_project(self) -> None:
        """PRJ-090: documents and files, correspondence, access and history are those of a project."""
        case = service_cases.create_case(name="Reparatur", case_contact="Herr Meier")
        for name in ("documents:list", "mail:project_mails", "projects:members", "projects:history"):
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name, args=[case])))
                self.assertIn('<span class="badge accent">Servicefall</span>', text)
                self.assertIn("<span>Herr Meier</span>", text)
                self.assertEqual(tabs_of(text)[0], "Überblick")  # PRJ-090

    def test_not_among_the_projects_but_found_by_the_search(self) -> None:
        case = service_cases.create_case(name="Nebelmaschine Störung")
        make_project("Stadtfest", start=at(1, 6), end=at(2, 20))
        projects = self.assert_ok(self.client.get("/projects/?all=1"))
        self.assertNotIn("Nebelmaschine Störung", projects)
        self.assertIn("Stadtfest", projects)
        for url in (
            "/schedule/?month=2027-03",
            "/schedule/timeline/?from=2027-03-01&weeks=1",
            "/schedule/?view=week&week=2027-03-01",
        ):
            with self.subTest(url=url):
                self.assertNotIn("Nebelmaschine", self.assert_ok(self.client.get(url)))
        found = self.assert_ok(self.client.get("/search/?q=Nebelmaschine"))
        self.assertIn(f"{case.number} Nebelmaschine Störung", found)
        self.assertIn("Servicefall", found)

    def test_the_start_page_names_my_cases(self) -> None:
        service_cases.create_case(name="Kabel defekt", manager=self.admin_user)
        text = self.assert_ok(self.client.get("/"))
        self.assertIn("Meine Servicefälle", text)
        self.assertIn("Kabel defekt", text)
        self.assertNotIn("Kabel defekt</a></td>", text)  # not among the coming projects

    def test_turn_a_case_into_a_project(self) -> None:
        case = service_cases.create_case(name="Reparatur wird Vermietung")
        url = reverse("projects:case_convert", args=[case])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("<h1>Servicefall in ein Projekt umwandeln</h1>", page)
        self.assertIn("beginnt als Anfrage", page)
        data = form_data(self.client.get(url), "name")
        refused = self.assert_ok(self.client.post(url, data))
        self.assertIn("Wähle den Kunden", refused)
        self.assertEqual(Project.objects.get(pk=case.pk).kind, "service_case")
        customer = make_customer("Stadtwerke")
        response = self.client.post(url, {**data, "customer": str(customer.pk), "addresses_for": ""}, follow=True)
        project = Project.objects.get(pk=case.pk)
        self.assertEqual((project.kind, project.status, project.customer), ("project", ProjectStatus.INQUIRY, customer))
        self.assertEqual(response.redirect_chain[-1][0], reverse("projects:detail", args=[project]))
        self.assertIn(
            f"Servicefall {project.number} ist jetzt ein Projekt. Plane Material und Crew.",
            self.messages_of(response),
        )

    def test_only_who_may_write_projects(self) -> None:
        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(reverse("projects:case_create")).status_code, 403)
        case = service_cases.create_case(name="Frage")
        self.assert_ok(reader.get(reverse("projects:case_detail", args=[case])))
        self.assertEqual(
            reader.post(reverse("projects:case_status", args=[case]), {"case_status": "done"}).status_code, 403
        )
        self.assertEqual(Project.objects.get(pk=case.pk).case_status, CaseStatus.OPEN)


class ServiceCaseFromInquiryPageTests(UiTestCase):
    """PRJ-090: Projekte → Anfragen offers "Als Servicefall anlegen"; the mail goes into the new case."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        self.raw = make_mail("AW: Beamer defekt", message_id="<b@x.example>", sender="Max Muster <max@example.org>")
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(self.raw)}):
            fetch_mail(force=True)
        self.inquiry = UnknownTagMail.objects.get(tag="")

    def test_from_the_inquiry_to_the_case(self) -> None:
        listed = self.assert_ok(self.client.get("/projects/inquiries/"))
        url = f"{reverse('projects:case_create')}?inquiry={self.inquiry.pk}"
        self.assertIn(f'href="{url.replace("&", "&amp;")}"', listed)
        self.assertIn("Als Servicefall anlegen", listed)
        form = self.assert_ok(self.client.get(url))
        self.assertIn("Aus der Mail „AW: Beamer defekt“ von Max Muster &lt;max@example.org&gt;.", form)
        data = form_data(self.client.get(url), "name")
        self.assertEqual((data["name"], data["case_contact"]), ("Beamer defekt", "Max Muster <max@example.org>"))
        data["customer"] = str(make_customer("Max Muster").pk)  # PRJ-090: the sender is no customer yet
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(self.raw)}):
            response = self.client.post(url, data, follow=True)
        case = Project.objects.get(name="Beamer defekt")
        self.assertIn("Die Mail liegt jetzt im Servicefall.", self.messages_of(response))
        mail = ProjectMail.objects.get()
        self.assertEqual(mail.project, case)
        page = self.assert_ok(response)
        self.assertIn("Letzte Mails", page)
        self.assertIn(reverse("mail:detail", args=[case, mail.pk]), page)

    def test_a_mail_gone_from_the_inbox_creates_no_case(self) -> None:
        url = f"{reverse('projects:case_create')}?inquiry={self.inquiry.pk}"
        data = form_data(self.client.get(url), "name", customer=str(make_customer().pk))  # PRJ-090
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox()}):
            text = self.assert_ok(self.client.post(url, data))
        self.assertIn("nicht mehr im Posteingang", text)
        self.assertFalse(Project.objects.filter(kind="service_case").exists())

    def test_without_the_right_to_write_mail(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        url = f"{reverse('projects:case_create')}?inquiry={self.inquiry.pk}"
        self.assertIn(warehouse.get(url).status_code, (403, 404))


class ShowfilePageTests(UiTestCase):
    """PRJ-089: show files on the tab "Dokumente" and in the overview of the crew."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.documents = reverse("documents:list", args=[self.project])
        self.upload_url = reverse("projects:files", args=[self.project])

    def upload(self, name: str, **fields: str) -> object:
        data = {"title": "", "document_type": "", "visible_to_crew": "", "show_system": "", "show_version": ""}
        data.update(fields)
        return self.client.post(self.upload_url, {**data, "file": SimpleUploadedFile(name, b"show")}, follow=True)

    def test_the_upload_form_knows_show_files(self) -> None:
        text = self.assert_ok(self.client.get(self.documents))
        kind = showfile_type()
        self.assertIn(f'<option value="{kind.pk}" data-showfile="1">Showfile</option>', text)
        self.assertIn('data-show-endings="{', text)
        self.assertIn('<datalist id="show-systems">', text)
        self.assertIn('<option value="grandMA3"></option>', text)
        self.assertIn("Showfiles von Pulten, Medienservern und Tonsystemen sind willkommen", text)
        self.assertIn("Höchstens 50 MB je Datei.", text)

    def test_upload_a_show_file(self) -> None:
        response = self.upload("Stadtfest.show.gz", show_version="3.9.60")
        text = self.assert_ok(response)
        show = ProjectFile.objects.get()
        self.assertEqual(
            (show.document_type, show.show_system, show.show_version), (showfile_type(), "grandMA2", "3.9.60")
        )
        self.assertIn("grandMA2 · Version 3.9.60", text)
        self.assertIn('<span class="badge green">aktuelle Show</span>', text)
        # Handed out as a download, never shown in the browser.
        download = self.client.get(reverse("projects:file_download", args=[self.project, show.pk]))
        self.assertIn("attachment", download["Content-Disposition"])

    def test_a_program_is_still_refused(self) -> None:
        text = self.assert_ok(self.upload("setup.exe"))
        self.assertIn("Dateien dieser Art können nicht abgelegt werden.", text)
        self.assertIn("Showfiles: asc, avc,", text)
        self.assertFalse(ProjectFile.objects.exists())

    def test_edit_console_version_and_current_show(self) -> None:
        self.upload("Tour.shw")
        older = ProjectFile.objects.get()
        self.upload("Tour-2.shw", show_system="Hog 4")
        url = reverse("projects:file_edit", args=[self.project, older.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn('<label for="id_show_system">Pult oder Software</label>', page)
        self.assertIn("Aktuelle Show", page)
        data = form_data(self.client.get(url), "title", show_system="Hog 4", show_version="3.20", is_current_show="on")
        self.client.post(url, data)
        older.refresh_from_db()
        newer = ProjectFile.objects.exclude(pk=older.pk).get()
        self.assertEqual((older.show_system, older.show_version, older.is_current_show), ("Hog 4", "3.20", True))
        self.assertFalse(newer.is_current_show)

    def test_the_crew_sees_the_show_file(self) -> None:
        self.upload("FOH.dm7f", show_version="1.60")
        person = make_person(
            "Anna Becker", rates={"Tontechnik": "30.00"}, user=make_user("anna", roles=("Freie Kraft",))
        )
        plan(self.project, "Tontechnik", person)
        crew = self.browser_of(person.user)
        text = self.assert_ok(crew.get(reverse("projects:deployment", args=[self.project])))
        self.assertIn("FOH.dm7f", text)
        self.assertIn("Yamaha DM7 · Version 1.60", text)
        show = ProjectFile.objects.get()
        self.assertEqual(crew.get(reverse("projects:file_download", args=[self.project, show.pk])).status_code, 200)


class LinesOfAPartStayTests(UiTestCase):
    """PRJ-050 seen from the planning: the lines are in the part afterwards, the rest at the whole project."""

    def test_the_planning_of_the_part(self) -> None:
        project = make_project("Gala")
        hall = add_group(project, "Saal")
        line = add_line(project, make_stock("L-010", 4, "Spot"), 2, group=hall).line
        self.client.post(reverse("projects:split", args=[project]), {"groups": [str(hall.pk)]})
        part = MaterialLine.objects.get(pk=line.pk).project
        text = self.assert_ok(self.client.get(reverse("projects:detail", args=[part])))
        self.assertIn("Spot", text)
        self.assertIn('<span class="badge accent subproject-badge">Teilprojekt</span>', text)
