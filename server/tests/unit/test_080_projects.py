# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "projects": dividing a project into subprojects afterwards (PRJ-050), service cases (PRJ-090) and
show files as project files (PRJ-089)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.core.models import AuditLogEntry
from rentalars.core.showfiles import guess_system, is_showfile_name, showfile_extension, systems_for
from rentalars.core.uploads import document_type_allowed, validate_document_upload
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.imap import MailboxError
from rentalars.mail.models import ProjectMail, UnknownTagMail
from rentalars.masterdata.models import DocumentType
from rentalars.notifications.models import Notification
from rentalars.packing.models import LineAssignment, PackEntry, Packlist
from rentalars.projects import service_cases
from rentalars.projects import services as project_services
from rentalars.projects.files import add_file, files_for_crew, update_file
from rentalars.projects.models import (
    CaseStatus,
    CrewLine,
    Group,
    LineVariant,
    MaterialLine,
    Project,
    ProjectKind,
    ProjectPhase,
    ProjectStatus,
)
from rentalars.projects.showfiles import showfile_type
from rentalars.projects.split import split_into_subprojects, split_plan
from rentalars.schedule.services import project_timeline
from rentalars.timetracking.models import TimeEntry
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_customer,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
    record_time,
)
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail

D = Decimal


class SplitCase(RentalarsTestCase):
    """ "Stadtfest" planned in one piece: two stages as groups, a group for the power, and crew."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10, 8), end=at(13, 20), event_start=at(11), event_end=at(13))
        self.spots = make_stock("L-010", 10, "Spot")
        self.desks = make_stock("T-020", 4, "Pult")
        self.cables = make_stock("K-030", 20, "Kabel")
        self.market = add_group(self.project, "Bühne Marktplatz")
        self.market_light = add_group(self.project, "Licht", parent=self.market)
        self.park = add_group(self.project, "Bühne Schlosspark")
        self.power = add_group(self.project, "Strom")
        self.market_spots = add_line(self.project, self.spots, 4, group=self.market_light).line
        self.market_desk = add_line(self.project, self.desks, 1, group=self.market).line
        self.park_spots = add_line(self.project, self.spots, 4, group=self.park).line
        self.cable_line = add_line(self.project, self.cables, 10, group=self.power).line

    def split(self, *groups: Group, crew: dict[int, int] | None = None) -> list[Project]:
        return split_into_subprojects(self.project, [group.pk for group in groups], crew).parts


class SplitTests(SplitCase):
    """PRJ-050: chosen top-level groups become subprojects with their lines; the rest stays."""

    def test_two_groups_become_two_subprojects(self) -> None:
        """PRJ-050: numbered like parts, named like the groups, with the periods and status of the project."""
        market, park = self.split(self.market, self.park)
        self.assertEqual((market.number, park.number), (f"{self.project.number}-1", f"{self.project.number}-2"))
        self.assertEqual((market.name, park.name), ("Bühne Marktplatz", "Bühne Schlosspark"))
        for part in (market, park):
            self.assertEqual(part.parent, self.project)
            self.assertEqual((part.start, part.end), (self.project.start, self.project.end))
            self.assertEqual((part.event_start, part.event_end), (self.project.event_start, self.project.event_end))
            self.assertEqual(part.status, ProjectStatus.CONFIRMED)
            self.assertEqual(part.customer, self.project.customer)
        self.assertEqual(MaterialLine.objects.get(pk=self.market_spots.pk).project, market)
        self.assertEqual(MaterialLine.objects.get(pk=self.park_spots.pk).project, park)
        # What was not chosen stays at the whole project.
        self.assertEqual(MaterialLine.objects.get(pk=self.cable_line.pk).project, self.project)
        self.assertEqual(list(self.project.groups.values_list("name", flat=True)), ["Strom"])
        self.assertTrue(self.project.subprojects.exists())

    def test_the_group_dissolves_into_the_part(self) -> None:
        """PRJ-050: its lines stand without group in the part, its subgroups are the part's groups."""
        (market,) = self.split(self.market)
        self.assertFalse(Group.objects.filter(pk=self.market.pk).exists())
        desk = MaterialLine.objects.get(pk=self.market_desk.pk)
        self.assertEqual((desk.project, desk.group), (market, None))
        light = Group.objects.get(pk=self.market_light.pk)
        self.assertEqual((light.project, light.parent), (market, None))
        self.assertEqual(MaterialLine.objects.get(pk=self.market_spots.pk).group, light)

    def test_a_group_with_a_discount_stays_a_group_and_the_prices_stay(self) -> None:
        """PRJ-050: a group with a price rule is kept as the one group of the part."""
        from rentalars.projects.pricing import compute_project_prices

        project_services.update_group(self.market, rights=ALL_RIGHTS, discount_percent=D("10"))
        before = compute_project_prices(self.project).net_total
        option = next(option for option in split_plan(self.project).groups if option.group == self.market)
        self.assertTrue(option.keeps_group)
        self.assertEqual(option.kept_because, ["Rabatt oder Pauschalpreis"])
        (market,) = self.split(self.market)
        group = Group.objects.get(pk=self.market.pk)
        self.assertEqual((group.project, group.parent), (market, None))
        after = compute_project_prices(self.project).net_total + compute_project_prices(market).net_total
        self.assertEqual(after, before)

    def test_the_change_log_names_what_went_where(self) -> None:
        market, park = self.split(self.market, self.park)
        whole = AuditLogEntry.objects.get(event="project.split", object_id=str(self.project.pk))
        self.assertEqual(
            whole.changes["parts"], [f"{market.number} Bühne Marktplatz", f"{park.number} Bühne Schlosspark"]
        )
        entry = AuditLogEntry.objects.get(event="project.split_part", object_id=str(market.pk))
        self.assertEqual(
            entry.changes, {"project": self.project.number, "group": "Bühne Marktplatz", "lines": 2, "crew": 0}
        )
        from rentalars.core.history import describe

        (item,) = describe([entry], ALL_RIGHTS)
        self.assertEqual(
            item.summary,
            f"Aus der Gruppe „Bühne Marktplatz“ von {self.project.number} entstanden: Materialpositionen: 2, "
            "Personalpositionen: 0",
        )

    def test_crew_goes_with_its_time_entries_and_a_copy_of_its_phase(self) -> None:
        """PRJ-050, PRJ-048: a crew line that goes takes its times; its phase is copied into the part."""
        setup = ProjectPhase.objects.create(project=self.project, kind="setup", start=at(10, 8), end=at(10, 18))
        anna = make_person("Anna Becker", rates={"Lichttechnik": "30.00"})
        goes = plan(self.project, "Lichttechnik", anna, start=at(10, 8), end=at(10, 18), phase=setup)
        stays = plan(self.project, "Lichttechnik", start=at(11, 8), end=at(11, 18))
        entry = record_time(anna, self.project, "Lichttechnik", at(10, 8), at(10, 18))
        self.assertEqual(entry.crew_line, goes)
        (market,) = self.split(self.market, crew={goes.pk: self.market.pk})
        goes = CrewLine.objects.get(pk=goes.pk)
        self.assertEqual(goes.project, market)
        self.assertEqual((goes.phase.project, goes.phase.kind, goes.phase.start), (market, "setup", at(10, 8)))
        self.assertNotEqual(goes.phase.pk, setup.pk)
        self.assertTrue(ProjectPhase.objects.filter(pk=setup.pk, project=self.project).exists())
        self.assertEqual(TimeEntry.objects.get(pk=entry.pk).project, market)
        self.assertEqual(CrewLine.objects.get(pk=stays.pk).project, self.project)

    def test_a_crew_line_only_goes_with_a_chosen_group(self) -> None:
        line = plan(self.project, "Lichttechnik", start=at(10, 8), end=at(10, 18))
        with self.assertRaises(ValidationError):
            self.split(self.market, crew={line.pk: self.park.pk})
        self.assertFalse(self.project.subprojects.exists())

    def test_a_covering_subrental_goes_with_its_line(self) -> None:
        """PRJ-054: the subrental that covers a shortage follows the line it covers."""
        short = add_line(self.project, self.spots, 4, group=self.market).line  # 12 of 10 spots
        subrental = project_services.accept_subrental_suggestion(short, self.spots, 2, rights=ALL_RIGHTS)
        (market,) = self.split(self.market)
        subrental.refresh_from_db()
        self.assertEqual((subrental.project, subrental.group, subrental.covers_line), (market, None, short))

    def test_open_pack_records_go_and_the_packlist_assignment_too(self) -> None:
        packlist = Packlist.objects.create(project=self.project)
        PackEntry.objects.create(packlist=packlist, line=self.market_desk, product=self.desks)
        truck = Packlist.objects.create(project=self.project, title="LKW 1")
        LineAssignment.objects.create(line=self.market_spots, packlist=truck)
        self.split(self.market)
        self.assertFalse(PackEntry.objects.filter(line=self.market_desk).exists())
        self.assertFalse(LineAssignment.objects.filter(line=self.market_spots).exists())

    def test_a_group_whose_material_is_packed_cannot_go(self) -> None:
        """PRJ-050: not once material is packed or issued."""
        packlist = Packlist.objects.create(project=self.project)
        PackEntry.objects.create(packlist=packlist, line=self.market_desk, product=self.desks, packed_quantity=D("1"))
        option = next(option for option in split_plan(self.project).groups if option.group == self.market)
        self.assertFalse(option.possible)
        self.assertIn("gepackt", option.reasons[0])
        with self.assertRaises(ValidationError):
            self.split(self.market)
        # The other stage can go.
        (park,) = self.split(self.park)
        self.assertEqual(park.name, "Bühne Schlosspark")

    def test_alternatives_and_surcharges_across_the_border_stop_a_group(self) -> None:
        """PRJ-083, PRJ-058: an alternative or a surcharge works within one project."""
        alternative = add_line(self.project, self.desks, 1, group=self.park).line
        project_services.update_line(
            alternative, rights=ALL_RIGHTS, variant=LineVariant.ALTERNATIVE, alternative_to=self.market_desk
        )
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        surcharge = add_line(self.project, night, 1).line
        project_services.set_surcharge_targets(surcharge, [{"type": "line", "id": self.cable_line.pk}])
        project_services.update_line(surcharge, rights=ALL_RIGHTS, group=self.park)
        reasons = {option.group.name: option.reasons for option in split_plan(self.project).groups}
        self.assertIn(
            "Eine ihrer Positionen ist Alternative zu einer Position außerhalb – oder umgekehrt.",
            reasons["Bühne Marktplatz"],
        )
        self.assertIn("Ein Aufpreis bezieht sich über ihre Grenze hinweg.", reasons["Bühne Schlosspark"])
        self.assertIn("Ein Aufpreis bezieht sich über ihre Grenze hinweg.", reasons["Strom"])

    def test_a_surcharge_on_the_whole_project_is_pointed_out(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        surcharge = add_line(self.project, night, 1).line
        project_services.set_surcharge_targets(surcharge, [{"type": "project"}])
        warnings = split_plan(self.project).warnings
        self.assertEqual(len(warnings), 1)
        self.assertIn("„Nachtzuschlag“ bezieht sich auf das ganze Projekt", warnings[0])

    def test_what_cannot_be_divided(self) -> None:
        """PRJ-050: no subproject, nothing out or over, no project without groups."""
        (market,) = self.split(self.market)
        self.assertIn("eine Ebene", split_plan(market).refusal)
        out = make_project("Unterwegs", status=ProjectStatus.OUT)
        add_group(out, "Bühne")
        self.assertIn("nur ein Projekt in Planung", split_plan(out).refusal)
        empty = make_project("Ohne Gruppen")
        self.assertIn("keine Teilgruppen", split_plan(empty).refusal)
        with self.assertRaises(ValidationError):
            split_into_subprojects(empty, [])

    def test_a_whole_project_turns_further_groups_into_parts(self) -> None:
        """PRJ-050: "Teilgruppe in Teilprojekt umwandeln" on an existing whole project."""
        (market,) = self.split(self.market)
        self.project.refresh_from_db()
        self.assertEqual(
            [option.group.name for option in split_plan(self.project).groups], ["Bühne Schlosspark", "Strom"]
        )
        (park,) = self.split(self.park)
        self.assertEqual(park.number, f"{self.project.number}-2")
        self.assertEqual(MaterialLine.objects.get(pk=self.market_spots.pk).project, market)

    def test_an_inquiry_stays_an_inquiry(self) -> None:
        project = make_project("Gala", status=ProjectStatus.INQUIRY)
        group = add_group(project, "Saal")
        add_line(project, self.spots, 2, group=group)
        (part,) = split_into_subprojects(project, [group.pk]).parts
        self.assertEqual(part.status, ProjectStatus.INQUIRY)


class ServiceCaseTests(RentalarsTestCase):
    """PRJ-090: a quick kind of project for a service case."""

    def test_a_case_takes_its_number_from_the_projects(self) -> None:
        project = make_project("Stadtfest")
        case = service_cases.create_case(name="Spot flackert", case_contact="Herr Meier, 0170 123")
        self.assertEqual(case.kind, ProjectKind.SERVICE_CASE)
        self.assertEqual(case.case_status, CaseStatus.OPEN)
        self.assertEqual(case.status, ProjectStatus.INQUIRY)
        self.assertGreater(case.number, project.number)
        self.assertEqual(case.mail_tag, f"[RL#{case.number}]")
        self.assertIsNone(case.customer)
        self.assertEqual(case.customer_name, "Herr Meier, 0170 123")

    def test_a_contact_must_belong_to_the_customer(self) -> None:
        from rentalars.customers.models import Contact

        other = make_customer("Andere GmbH")
        contact = Contact.objects.create(customer=other, name="Frau Lang")
        with self.assertRaises(ValidationError):
            service_cases.create_case(name="Frage", customer=make_customer("Stadtwerke"), contact=contact)

    def test_no_planning_in_a_case(self) -> None:
        """PRJ-090: no material, no crew, no parts, no project status."""
        case = service_cases.create_case(name="Reparatur")
        with self.assertRaises(ValidationError):
            add_line(case, make_stock("L-010", 2), 1)
        with self.assertRaises(ValidationError):
            plan(case, "Lichttechnik")
        with self.assertRaises(ValidationError):
            project_services.create_subproject(case, name="Teil")
        with self.assertRaises(ValidationError):
            project_services.change_status(case, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.assertIn("Servicefall", split_plan(case).refusal)

    def test_the_statuses_of_a_case(self) -> None:
        case = service_cases.create_case(name="Frage")
        service_cases.set_case_status(case, CaseStatus.IN_PROGRESS)
        service_cases.set_case_status(case, CaseStatus.DONE)
        service_cases.set_case_status(case, CaseStatus.OPEN)  # any order
        self.assertEqual(Project.objects.get(pk=case.pk).case_status, CaseStatus.OPEN)
        with self.assertRaises(ValidationError):
            service_cases.set_case_status(case, "closed")
        changes = [entry.changes for entry in AuditLogEntry.objects.filter(object_id=str(case.pk), action="updated")]
        self.assertIn({"case_status": ["in_progress", "done"]}, changes)

    def test_not_in_the_timeline_nor_the_list(self) -> None:
        """PRJ-090: not in calendar, timeline or the list of projects – the views leave it out."""
        project = make_project("Stadtfest", start=at(1, 6), end=at(2, 20))
        case = service_cases.create_case(name="Störung")
        everything = Project.objects.all()
        self.assertIn(case, everything)
        rows = project_timeline(service_cases.without_cases(everything), [at(1).date(), at(2).date()])
        self.assertEqual([row[0] for row in rows], [project])
        self.assertEqual(list(service_cases.cases(everything)), [case])

    def test_the_person_responsible_is_told(self) -> None:
        anna, ben = make_user("anna"), make_user("ben")
        # PRJ-090: an edited case needs a customer.
        case = service_cases.create_case(name="Störung", manager=anna, user=ben, customer=make_customer())
        notification = Notification.objects.get(user=anna)
        self.assertEqual(notification.title, f"Servicefall {case.number} Störung ist jetzt deiner")
        service_cases.update_case(case, manager=ben, user=ben)  # took it over oneself: nobody to tell
        self.assertEqual(Notification.objects.count(), 1)

    def test_a_case_becomes_a_project(self) -> None:
        """PRJ-090: number, mails and history stay; it starts as an inquiry with the periods given."""
        case = service_cases.create_case(name="Reparatur wird Vermietung")
        service_cases.set_case_status(case, CaseStatus.IN_PROGRESS)
        with self.assertRaises(ValidationError):
            service_cases.convert_to_project(Project.objects.get(pk=case.pk), start=at(10), end=at(12))
        customer = make_customer("Stadtwerke")
        project = service_cases.convert_to_project(
            Project.objects.get(pk=case.pk), customer=customer, start=at(10), end=at(12)
        )
        self.assertEqual((project.pk, project.number), (case.pk, case.number))
        self.assertEqual((project.kind, project.case_status, project.status), ("project", "", ProjectStatus.INQUIRY))
        self.assertTrue(AuditLogEntry.objects.filter(event="service_case.converted", object_id=str(case.pk)).exists())
        add_line(project, make_stock("L-010", 2), 1)  # now it plans
        with self.assertRaises(ValidationError):
            service_cases.set_case_status(project, CaseStatus.DONE)

    def test_suggestions_from_an_inquiry(self) -> None:
        """PRJ-090: the subject without "AW:", the customer and contact of the sender's address."""
        from rentalars.customers.models import Contact

        customer = make_customer("Stadtwerke")
        contact = Contact.objects.create(customer=customer, name="Frau Lang", email="lang@stadtwerke.example")
        known = UnknownTagMail(subject="AW: Re: Beamer defekt", sender="Frau Lang <LANG@stadtwerke.example>")
        self.assertEqual(
            service_cases.suggestions_from_inquiry(known),
            {"name": "Beamer defekt", "customer": customer, "contact": contact},
        )
        unknown = UnknownTagMail(subject="", sender="Max Muster <max@example.org>")
        self.assertEqual(
            service_cases.suggestions_from_inquiry(unknown),
            {"name": "Anfrage per Mail", "case_contact": "Max Muster <max@example.org>"},
        )


class ServiceCaseFromInquiryTests(RentalarsTestCase):
    """PRJ-090: a case from an inquiry without project tag takes the mail along – or nothing happens."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        self.raw = make_mail("Nebelmaschine defekt", message_id="<n@x.example>", sender="Max <max@example.org>")
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(self.raw)}):
            fetch_mail(force=True)
        self.inquiry = UnknownTagMail.objects.get(tag="")

    def test_the_mail_goes_into_the_new_case(self) -> None:
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(self.raw)}):
            # PRJ-090: the customer is required – the sender is no known customer here.
            case = service_cases.create_from_inquiry(
                self.inquiry, name="Nebelmaschine defekt", customer=make_customer()
            )
        mail = ProjectMail.objects.get()
        self.assertEqual(mail.project, case)
        self.inquiry.refresh_from_db()
        self.assertIsNotNone(self.inquiry.resolved_at)

    def test_without_the_mail_there_is_no_case(self) -> None:
        empty = {"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox()}
        with mailboxes(empty), self.assertRaises(MailboxError):
            service_cases.create_from_inquiry(self.inquiry, name="Nebelmaschine defekt", customer=make_customer())
        self.assertFalse(Project.objects.filter(kind=ProjectKind.SERVICE_CASE).exists())
        self.inquiry.refresh_from_db()
        self.assertIsNone(self.inquiry.resolved_at)


class ShowfileUploadTests(RentalarsTestCase):
    """PRJ-089: show files pass the upload check by their ending; nothing executable does."""

    def test_the_endings_of_the_usual_consoles(self) -> None:
        for name in (
            "Gala.esf3d",
            "gala.ESF",
            "Stadtfest.show",
            "Stadtfest.show.gz",
            "Tour.shw",
            "backup.sbk",
            "Set.avc",
            "Mix.dm7f",
            "Kirche.scn",
            "FOH.ses",
            "System.dbpr",
            "Workspace.qlab5",
            "Show-Ordner.zip",
        ):
            with self.subTest(name=name):
                self.assertTrue(document_type_allowed(name))
        for name in ("setup.exe", "run.sh", "page.html", "logo.svg", "macro.js", ".show.gz", "show.gz"):
            with self.subTest(name=name):
                self.assertFalse(document_type_allowed(name))

    def test_the_console_from_the_ending(self) -> None:
        self.assertEqual(showfile_extension("Gala.show.gz"), ".show.gz")
        self.assertEqual(guess_system("Gala.show.gz"), "grandMA2")
        self.assertEqual(guess_system("gala.ESF3D"), "ETC Eos")
        self.assertEqual(guess_system("Mix.dm7f"), "Yamaha DM7")
        self.assertEqual(guess_system("Set.avc"), "Resolume Arena")
        self.assertEqual(guess_system("Tour.shw"), "")  # Hog 4, MagicQ or X32/M32: chosen by hand
        self.assertEqual(systems_for("Tour.shw"), ["Hog 4", "ChamSys MagicQ", "Midas M32", "Behringer X32"])
        self.assertFalse(is_showfile_name("Plan.pdf"))

    def test_the_refusal_names_the_show_files(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_document_upload(SimpleUploadedFile("tool.exe", b"MZ"))
        self.assertIn("Showfiles: asc, avc,", caught.exception.messages[0])

    def test_the_size_limit_holds_for_show_files_too(self) -> None:
        from rentalars.core.models import SystemSettings

        settings = SystemSettings.load()
        settings.max_upload_mb = 1
        settings.save()
        with self.assertRaises(ValidationError):
            validate_document_upload(SimpleUploadedFile("big.show", b"x" * (1024 * 1024 + 1)))


class ShowfileTests(RentalarsTestCase):
    """PRJ-089: the document type "Showfile", the console, the version and the current show."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.user = make_user("anna")

    def upload(self, name: str, **fields: object) -> object:
        return add_file(self.project, SimpleUploadedFile(name, b"show"), user=self.user, **fields)

    def test_the_start_data_have_the_type_showfile(self) -> None:
        kind = showfile_type()
        self.assertEqual((kind.name, kind.is_showfile, kind.visible_to_crew), ("Showfile", True, True))

    def test_a_show_file_gets_the_type_and_its_console(self) -> None:
        first = self.upload("Stadtfest.show", show_version="2.1.1.5")
        self.assertEqual(first.document_type, showfile_type())
        self.assertEqual((first.show_system, first.show_version, first.is_current_show), ("grandMA3", "2.1.1.5", True))
        self.assertTrue(first.visible_to_crew)  # PRJ-089: the planned crew sees it
        self.assertIn(first, files_for_crew(self.project))
        # A plan without show file ending stays a plain file.
        plan_file = self.upload("Plan.pdf")
        self.assertEqual((plan_file.document_type, plan_file.show_system, plan_file.is_current_show), (None, "", False))

    def test_the_newest_show_of_a_console_is_the_current_one(self) -> None:
        first = self.upload("Stadtfest-v1.show")
        second = self.upload("Stadtfest-v2.show")
        sound = self.upload("FOH.dm7f")
        first.refresh_from_db()
        self.assertEqual((first.is_current_show, second.is_current_show, sound.is_current_show), (False, True, True))
        update_file(first, is_current_show=True)  # back to the first one
        second.refresh_from_db()
        sound.refresh_from_db()
        self.assertEqual((second.is_current_show, sound.is_current_show), (False, True))

    def test_an_ambiguous_ending_leaves_the_console_open(self) -> None:
        show = self.upload("Tour.shw")
        self.assertEqual(show.show_system, "")
        update_file(show, show_system="Hog 4", show_version="3.20")
        show.refresh_from_db()
        self.assertEqual((show.show_system, show.show_version), ("Hog 4", "3.20"))

    def test_another_type_drops_the_show_fields(self) -> None:
        show = self.upload("Stadtfest.show")
        update_file(show, document_type=DocumentType.objects.get(name="Sonstiges"))
        show.refresh_from_db()
        self.assertEqual((show.show_system, show.show_version, show.is_current_show), ("", "", False))
