# SPDX-License-Identifier: GPL-3.0-or-later
"""Wishes for documents, the project list and the deployment view (DOK-013, PRJ-085, PRJ-081).

The festival used throughout, net 1.848,00 · 19 % 351,12 · gross 2.199,12::

    Licht        6 × PAR 64 at 20,00, 10 % off                   108,00
                 Nebelmaschine 50,00, optional (not added up)
    Ton          Mischpult 300,00
      Mikrofone  4 × Funkmikrofon at 25,00                       100,00   Ton with subgroup 400,00
    no group     Transport 80,00 · LED-Wand (subrental) 900,00, costs 650,00
    personnel    Tontechnik 8 h at 45,00                         360,00   costs 8 h × 35,00 = 280,00
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.accounts.models import Role
from rentalars.accounts.rights import ProjectScope, rights_of
from rentalars.documents import content as builder
from rentalars.documents import services
from rentalars.documents.deployment import deployment_pdf, file_name, render_deployment_html
from rentalars.documents.models import Document, DocumentDetail, DocumentKind, DocumentTemplate
from rentalars.documents.pdf import render_html
from rentalars.mail.sending import chosen_attachments, document_choices
from rentalars.products.models import BillingMode, Product
from rentalars.projects import services as project_services
from rentalars.projects.deployment import deployment_picture, neutral
from rentalars.projects.family_prices import family_prices
from rentalars.projects.list_sums import ListSums, attach_sums
from rentalars.projects.models import LineVariant, Project, ProjectAccessLevel, ProjectMembership, ProjectStatus
from rentalars.projects.pricing import compute_project_prices
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    ready_for_invoices,
)

D = Decimal


def flat(article_number: str, name: str, price: str, **fields: Any) -> Any:
    """A product billed as a flat price: quantity × price."""
    return make_product(article_number, name, price=price, billing_mode=BillingMode.FLAT, **fields)


def stadtfest(project: Project | None = None) -> SimpleNamespace:
    """The festival of the module description, ready for offers and invoices."""
    project = project or make_project("Stadtfest", customer=ready_for_invoices())
    light = add_group(project, "Licht", description="Frontlicht für die Bühne", discount_percent=D("10"))
    add_line(project, flat("L-100", "PAR 64", "20.00"), 6, group=light)
    fog = add_line(project, flat("L-200", "Nebelmaschine", "50.00"), 1, group=light, variant=LineVariant.OPTIONAL)
    sound = add_group(project, "Ton")
    add_line(project, flat("T-100", "Mischpult", "300.00"), 1, group=sound)
    microphones = add_group(project, "Mikrofone", parent=sound)
    add_line(project, flat("T-200", "Funkmikrofon", "25.00"), 4, group=microphones)
    add_line(project, flat("K-100", "Transport", "80.00"), 1)
    wall = make_product("E-002", "Zumietung LED-Wand", kind="subrental", billing_mode="flat", price="0.00")
    add_line(project, wall, 1, title="LED-Wand 3 × 2 m", unit_price=D("900.00"), purchase_price=D("650.00"))
    function = job_function("Tontechnik", price="45.00")
    anna = make_person(
        "Anna Becker", rates={"Tontechnik": "35.00"}, phone="0170 111", email="anna@example.de", share_phone=True
    )
    crew_line = plan(project, function, anna, start=at(10, 8), end=at(10, 20), planned_hours=D("8"))
    return SimpleNamespace(
        project=project, light=light, sound=sound, microphones=microphones, fog=fog, anna=anna, crew_line=crew_line
    )


class OfferValidityTests(RentalarsTestCase):
    """DOK-013: the validity of an offer as a date or in days; the default in the template of the offer."""

    issued = datetime.date(2027, 3, 1)

    def test_days_and_date_name_the_same_day(self) -> None:
        self.assertEqual(services.offer_valid_until(self.issued, validity_days=30), datetime.date(2027, 3, 31))
        self.assertEqual(
            services.offer_valid_until(self.issued, datetime.date(2027, 3, 31)), datetime.date(2027, 3, 31)
        )
        self.assertEqual(
            services.offer_valid_until(self.issued, datetime.date(2027, 3, 31), 30), datetime.date(2027, 3, 31)
        )
        self.assertEqual(services.offer_valid_until(self.issued, validity_days=0), self.issued)

    def test_date_and_days_that_differ_are_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            services.offer_valid_until(self.issued, datetime.date(2027, 4, 1), 30)
        self.assertIn("validity_days", caught.exception.error_dict)
        self.assertIn("31.03.2027", " ".join(caught.exception.messages))
        for days in (-1, 3651):
            with self.subTest(days=days), self.assertRaises(ValidationError):
                services.offer_valid_until(self.issued, validity_days=days)
        with self.assertRaises(ValidationError):
            services.offer_valid_until(self.issued, datetime.date(2027, 2, 28))

    def test_the_default_comes_from_the_template_of_the_offer(self) -> None:
        template = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        self.assertEqual(template.validity_days, 14)  # documents 0004: as before
        self.assertEqual(services.offer_valid_until(self.issued), datetime.date(2027, 3, 15))
        template.validity_days = 30
        template.full_clean()
        template.save()
        self.assertEqual(services.default_validity_days(), 30)
        self.assertEqual(services.offer_valid_until(self.issued), datetime.date(2027, 3, 31))

    def test_only_the_offer_has_a_validity(self) -> None:
        offer = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        offer.validity_days = None
        with self.assertRaises(ValidationError) as caught:
            offer.full_clean()
        self.assertIn("validity_days", caught.exception.error_dict)
        invoice = services.template_for(DocumentKind.INVOICE)
        self.assertIsNone(invoice.validity_days)
        invoice.validity_days = 10
        with self.assertRaises(ValidationError):
            invoice.full_clean()

    def test_a_fresh_offer_template_starts_with_14_days(self) -> None:
        DocumentTemplate.objects.filter(kind=DocumentKind.OFFER).delete()
        self.assertEqual(services.template_for(DocumentKind.OFFER).validity_days, 14)

    def test_the_offer_stores_date_days_and_fills_the_placeholder(self) -> None:
        project = make_project(customer=ready_for_invoices())
        add_line(project, flat("L-100", "PAR 64", "20.00"), 2)
        template = services.template_for(DocumentKind.OFFER)
        template.closing = "Dieses Angebot gilt {validity_days} Tage."
        template.save()
        offer = services.create_document(project, DocumentKind.OFFER, validity_days=21)
        self.assertEqual((offer.valid_until, offer.validity_days), (datetime.date(2027, 3, 22), 21))
        self.assertEqual(offer.content["closing"], "Dieses Angebot gilt 21 Tage.")
        invoice = services.create_document(project, DocumentKind.INVOICE)
        self.assertIsNone(invoice.validity_days)


class OfferWithGroupsOnlyTests(RentalarsTestCase):
    """DOK-013: an offer with the groups and their sums, without the positions in them."""

    def setUp(self) -> None:
        super().setUp()
        self.festival = stadtfest()
        self.project = self.festival.project

    def content(self, detail: str, kind: str = DocumentKind.OFFER) -> builder.DocumentContent:
        return services.build_content(self.project, kind, number="X", issued_on=at(1).date(), detail=detail)

    @staticmethod
    def outline(content: builder.DocumentContent) -> list[tuple[str, str, bool, list[str]]]:
        return [
            (section.title, section.part, section.positions_hidden, [p.title for p in section.positions])
            for section in content.sections
        ]

    def test_groups_show_their_sums_and_the_rest_is_listed(self) -> None:
        offer = self.content(DocumentDetail.GROUPS)
        self.assertEqual(offer.detail, "groups")
        self.assertEqual(
            self.outline(offer),
            [
                # The optional line stays: it is not part of the sum of "Licht".
                ("Licht", "", True, ["Nebelmaschine"]),
                ("Ton", "opens", True, []),
                ("Mikrofone", "", True, []),
                ("Ton", "closes", True, []),
                ("Ohne Teilgruppe", "", False, ["Transport", "LED-Wand 3 × 2 m"]),
                ("Personal", "", False, ["Tontechnik, Stunde"]),
            ],
        )
        subtotals = {(section.title, section.part): section.subtotal for section in offer.sections}
        self.assertEqual(subtotals[("Licht", "")], D("108.00"))
        self.assertEqual(subtotals[("Mikrofone", "")], D("100.00"))
        self.assertEqual(subtotals[("Ton", "closes")], D("400.00"))
        self.assertEqual(offer.sections[0].description, "Frontlicht für die Bühne")
        self.assertEqual(offer.sections[0].adjustment_label, "Rabatt 10 %")
        # The positions that remain are numbered from 1.
        self.assertEqual(
            [(position.number, position.title) for section in offer.sections for position in section.positions],
            [("1", "Nebelmaschine"), ("2", "Transport"), ("3", "LED-Wand 3 × 2 m"), ("4", "Tontechnik, Stunde")],
        )

    def test_the_totals_are_those_of_the_offer_with_positions(self) -> None:
        full, groups = self.content(DocumentDetail.LINES), self.content(DocumentDetail.GROUPS)
        self.assertEqual(full.detail, "lines")
        self.assertFalse(any(section.positions_hidden for section in full.sections))
        for name in ("net_total", "tax_total", "gross_total", "optional_lines_total"):
            with self.subTest(total=name):
                self.assertEqual(getattr(groups, name), getattr(full, name))
        self.assertEqual((groups.net_total, groups.gross_total), (D("1848.00"), D("2199.12")))
        self.assertEqual(
            [(share.net, share.tax, share.positions_total) for share in groups.taxes],
            [(share.net, share.tax, share.positions_total) for share in full.taxes],
        )

    def test_the_offer_is_stored_with_its_level_of_detail(self) -> None:
        offer = services.create_document(self.project, DocumentKind.OFFER, detail=DocumentDetail.GROUPS)
        self.assertEqual((offer.detail, offer.content["detail"]), ("groups", "groups"))
        self.assertTrue(offer.content["sections"][0]["positions_hidden"])
        # A stored document is read back as it was, also the new fields.
        self.assertTrue(builder.from_json(offer.content).sections[0].positions_hidden)
        self.assertEqual(services.create_document(self.project, DocumentKind.OFFER).detail, "lines")

    def test_the_pdf_shows_the_groups_without_their_positions(self) -> None:
        html = render_html(self.content(DocumentDetail.GROUPS), services.template_for(DocumentKind.OFFER))
        for text in ("Licht", "108,00", "Frontlicht für die Bühne", "Mikrofone", "Zwischensumme Ton mit Untergruppen"):
            self.assertIn(text, html)
        for text in ("PAR 64", "Mischpult", "Funkmikrofon"):
            self.assertNotIn(text, html)
        for text in ("Nebelmaschine", "Transport", "Tontechnik", "2.199,12"):
            self.assertIn(text, html)
        full = render_html(self.content(DocumentDetail.LINES), services.template_for(DocumentKind.OFFER))
        self.assertIn("PAR 64", full)
        self.assertIn("Zwischensumme Licht", full)
        self.assertTrue(services.preview(self.project, DocumentKind.OFFER, detail="groups").startswith(b"%PDF"))

    def test_only_an_offer_shows_groups_only(self) -> None:
        for kind in (DocumentKind.ORDER_CONFIRMATION, DocumentKind.DELIVERY_NOTE):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                services.create_document(self.project, kind, detail=DocumentDetail.GROUPS)
        with self.assertRaises(ValidationError):
            services.create_document(self.project, DocumentKind.OFFER, detail="pages")
        self.assertEqual(
            services.create_document(self.project, DocumentKind.ORDER_CONFIRMATION, detail="lines").detail, "lines"
        )

    def test_a_whole_project_keeps_the_blocks_of_its_parts(self) -> None:
        """PRJ-046: each part's groups carry their sums inside the part's block."""
        part = project_services.create_subproject(self.project, name="Bühne Schlosspark", start=at(11, 8))
        stage = add_group(part, "Bühne")
        add_line(part, flat("K-200", "Podest", "40.00"), 5, group=stage)
        full = services.build_content(self.project, DocumentKind.OFFER, number="X", issued_on=at(1).date())
        offer = services.build_content(
            self.project, DocumentKind.OFFER, number="X", issued_on=at(1).date(), detail="groups"
        )
        block = [section for section in offer.sections if section.subproject == part.number]
        self.assertEqual(
            [(s.title, s.part, s.subproject_block, s.positions_hidden, s.subtotal) for s in block],
            [
                (f"Teilprojekt {part.number} Bühne Schlosspark, 11.03.–12.03.2027", "opens", True, False, D("0")),
                ("Bühne", "", False, True, D("200.00")),
                (f"Teilprojekt {part.number} Bühne Schlosspark", "closes", True, False, D("200.00")),
            ],
        )
        self.assertEqual(block[1].positions, [])
        self.assertEqual((offer.net_total, offer.gross_total), (full.net_total, full.gross_total))
        self.assertEqual(offer.net_total, D("2048.00"))


class ListSumsTests(RentalarsTestCase):
    """PRJ-085: the sums of the project list come from the price calculation, for whole projects with their parts."""

    def setUp(self) -> None:
        super().setUp()
        self.festival = stadtfest()
        self.project = self.festival.project
        self.admin = make_user("admin", superuser=True)

    def sums(self, *projects: Project, user: Any = None) -> list[ListSums | None]:
        loaded = list(Project.objects.filter(pk__in=[project.pk for project in projects]).order_by("pk"))
        user = user or self.admin
        attach_sums(loaded, rights=rights_of(user), user=user)
        return [project.list_sums for project in loaded]

    def test_the_sums_of_one_project(self) -> None:
        (sums,) = self.sums(self.project)
        self.assertEqual(
            sums,
            ListSums(
                planned_hours=D("8.00"),
                material_revenue=D("1488.00"),
                personnel_revenue=D("360.00"),
                net_total=D("1848.00"),
                gross_total=D("2199.12"),
                material_cost=D("650.00"),
                personnel_cost=D("280.00"),
                profit=D("918.00"),
            ),
        )
        prices = compute_project_prices(self.project)
        self.assertEqual(
            (sums.net_total, sums.gross_total, sums.profit),
            (prices.net_total, prices.gross_total, prices.contribution_margin),
        )

    def test_a_whole_project_sums_up_its_parts_but_not_the_cancelled_ones(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne Schlosspark", start=at(11, 8))
        add_line(part, flat("K-200", "Podest", "40.00"), 5)
        plan(part, "Tontechnik", None, start=at(11, 8), end=at(11, 12), planned_hours=D("4"))
        cancelled = project_services.create_subproject(self.project, name="Bühne Hafen")
        add_line(cancelled, flat("K-300", "Zelt", "1000.00"), 1)
        cancelled.status = ProjectStatus.CANCELLED
        cancelled.save()
        whole, own = self.sums(self.project, part)
        self.assertEqual(own.net_total, D("380.00"))  # 200,00 + 4 h × 45,00
        self.assertEqual(own.planned_hours, D("4.00"))
        self.assertEqual(whole.net_total, D("2228.00"))
        self.assertEqual(whole.planned_hours, D("12.00"))
        self.assertEqual(whole.personnel_revenue, D("540.00"))
        self.assertEqual(whole.gross_total, family_prices(self.project).totals.gross_total)
        self.assertEqual(whole.material_revenue + whole.personnel_revenue, whole.net_total)

    def test_no_sums_where_the_planning_may_not_be_read(self) -> None:
        """AUT-023: a project known only through a crew line shows nothing; a membership "read" shows the sums."""
        Role.objects.create(
            name="Leitung zugewiesen",
            module_levels={"projects": 2},
            special_rights=["prices"],
            project_scope=ProjectScope.ASSIGNED,
        )
        user = make_user("lea", roles=("Leitung zugewiesen",))
        lea = make_person("Lea Krause", user=user)
        other = make_project("Messe")
        add_line(other, flat("K-400", "Messestand", "500.00"), 1)
        plan(self.project, "Tontechnik", lea, start=at(10, 8), end=at(10, 12), planned_hours=D("4"))
        ProjectMembership.objects.create(project=other, user=user, level=ProjectAccessLevel.READ)
        deployed, member = self.sums(self.project, other, user=user)
        self.assertIsNone(deployed)
        self.assertEqual(member.net_total, D("500.00"))

    def test_the_number_of_queries_does_not_grow_with_the_projects(self) -> None:
        """NFA-014: a page of projects needs as many queries as a few – each like the festival, with a part."""
        lamp, transport, wall = (Product.objects.get(article_number=number) for number in ("L-100", "K-100", "E-002"))

        def like_the_festival(name: str) -> Project:
            project = make_project(name)
            group = add_group(project, "Licht", discount_percent=D("5"))
            add_line(project, lamp, 2, group=group)
            add_line(project, transport, 1)
            add_line(project, wall, 1, title="LED-Wand", unit_price=D("900.00"), purchase_price=D("650.00"))
            plan(project, "Tontechnik", None, start=at(10, 8), end=at(10, 12), planned_hours=D("4"))
            part = project_services.create_subproject(project, name="Teil")
            add_line(part, transport, 1)
            return project

        def measured(projects: list[Project]) -> int:
            loaded = list(Project.objects.filter(pk__in=[project.pk for project in projects]))
            with CaptureQueriesContext(connection) as queries:
                attach_sums(loaded, rights=ALL_RIGHTS, user=self.admin)
            self.assertTrue(all(project.list_sums is not None for project in loaded))
            return len(queries)

        few = [self.project, like_the_festival("Messe")]
        many = few + [like_the_festival(f"Projekt {index}") for index in range(8)]
        self.assertEqual(measured(many), measured(few))
        self.assertLess(measured(many), 15)


class DeploymentOverviewTests(RentalarsTestCase):
    """PRJ-081: the deployment view as PDF – for the viewer, and for a mail as any colleague sees it."""

    def setUp(self) -> None:
        super().setUp()
        self.festival = stadtfest()
        self.project = self.festival.project
        self.project.venue = "Marktplatz"
        self.project.save()
        self.ben_user = make_user("ben", roles=("Freie Kraft",))
        self.ben = make_person("Ben Braun", user=self.ben_user, phone="0170 222", email="ben@example.de")
        self.carl = make_person("Carl Conrad", phone="0170 333", email="carl@example.de")
        plan(self.project, "Bühne", self.ben, start=at(10, 7), end=at(10, 15), meeting_point="Tor 3")
        plan(self.project, "Bühne", self.carl, start=at(10, 7), end=at(10, 15))
        self.admin = make_user("admin", superuser=True)

    def contacts(self, picture: Any) -> dict[str, tuple[str, str]]:
        return {row.person.name: (row.phone, row.email) for row in picture.rows if row.person}

    def test_crew_sees_released_contacts_and_its_own(self) -> None:
        picture = deployment_picture(self.project, rights=rights_of(self.ben_user), user=self.ben_user)
        self.assertEqual([row.person.name for row in picture.own_rows], ["Ben Braun"])
        self.assertEqual(
            self.contacts(picture),
            {
                "Anna Becker": ("0170 111", ""),
                "Ben Braun": ("0170 222", "ben@example.de"),
                "Carl Conrad": ("", ""),
            },
        )
        html = render_deployment_html(picture)
        for text in ("Einsatzübersicht", self.project.number, "Mein Einsatz", "Tor 3", "Marktplatz", "Carl Conrad"):
            self.assertIn(text, html)
        for text in ("0170 333", "carl@example.de", self.project.customer.name, "45,00", "35,00"):
            self.assertNotIn(text, html)

    def test_planners_see_every_contact(self) -> None:
        picture = deployment_picture(self.project, rights=rights_of(self.admin), user=self.admin)
        self.assertEqual(self.contacts(picture)["Carl Conrad"], ("0170 333", "carl@example.de"))
        self.assertEqual(picture.own_rows, [])
        self.assertTrue(deployment_pdf(self.project, rights=rights_of(self.admin), user=self.admin).startswith(b"%PDF"))

    def test_the_mail_gets_the_view_of_any_colleague(self) -> None:
        picture = neutral(self.project)
        self.assertIsNone(picture.viewer)
        self.assertEqual(self.contacts(picture)["Carl Conrad"], ("", ""))
        self.assertEqual(self.contacts(picture)["Ben Braun"], ("", ""))
        self.assertNotIn("Mein Einsatz", render_deployment_html(picture))

    def test_offered_as_attachment_of_a_mail_but_not_ticked(self) -> None:
        choices = dict(document_choices(ALL_RIGHTS, self.project))
        self.assertEqual(choices["deployment"], "Einsatzübersicht (PDF)")
        self.assertNotIn("deployment", dict(document_choices(ALL_RIGHTS)))
        (attachment,) = chosen_attachments(self.project, rights=ALL_RIGHTS, documents=["deployment"], user=self.admin)
        self.assertEqual(attachment.filename, f"Einsatzuebersicht-{self.project.number}.pdf")
        self.assertEqual(attachment.filename, file_name(self.project))
        self.assertEqual(attachment.content_type, "application/pdf")
        self.assertTrue(attachment.data.startswith(b"%PDF"))
        self.assertFalse(Document.objects.exists())  # made at the moment, never stored
