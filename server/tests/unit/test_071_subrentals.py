# SPDX-License-Identifier: GPL-3.0-or-later
"""Subrentals: the status "open" and the supplier field (PRJ-101); one page per project and supplier with
lines, documents and correspondence (PRJ-106) – and the data steps of the migrations for existing installations.

Requirements: the status of a subrental can be "open" when no supplier is chosen yet (the combination "requested" and "no supplier"
is illogical); subrentals also hold correspondence and documents (incoming offers, order confirmations, invoices, ...).
"""

from __future__ import annotations

from decimal import Decimal as D  # noqa: N817

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.accounts.rights import Rights
from rentalars.core.models import AuditLogEntry
from rentalars.mail.fetching import import_mail
from rentalars.mail.models import AssignedBy, ProjectMail
from rentalars.mail.sending import send_project_mail
from rentalars.mail.suppliers import addresses_of, mails_with, set_supplier, supplier_for
from rentalars.masterdata.models import Supplier
from rentalars.projects import lines as line_services
from rentalars.projects import services, subrentals
from rentalars.projects.models import MaterialLine, ProjectFile, SubrentalStatus, SupplierDocumentKind
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, make_project, make_stock, make_user
from tests.mailbox import capture_smtp, configure_mailbox, make_mail

PDF = b"%PDF-1.4\n%%EOF\n"
NO_PURCHASE_PRICES = Rights(module_levels=dict(ALL_RIGHTS.module_levels), special_rights=frozenset({"prices"}))


class SubrentalCase(RentalarsTestCase):
    """A project whose spots are short; a supplier with an e-mail address."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.spots = make_stock("L-010", 4, "Spot", price="20.00")
        self.line = add_line(self.project, self.spots, 6).line
        self.nord = Supplier.objects.create(name="Verleih Nord", email="dispo@verleih-nord.example")
        self.product = services.default_subrental_product()

    def subrent(self, quantity: int = 2, **fields: object) -> MaterialLine:
        return services.accept_subrental_suggestion(self.line, self.spots, quantity, rights=ALL_RIGHTS, **fields)


class StatusTests(SubrentalCase):
    """PRJ-101: "open" first and by default; every other status needs a supplier."""

    def test_open_is_the_first_status_and_the_default(self) -> None:
        """PRJ-101."""
        self.assertEqual(SubrentalStatus.values[0], SubrentalStatus.OPEN)
        self.assertEqual(self.subrent().subrental_status, SubrentalStatus.OPEN)
        planned = add_line(self.project, self.product, 1, title="Nebelmaschine").line
        self.assertEqual(planned.subrental_status, SubrentalStatus.OPEN)

    def test_no_status_but_open_without_a_supplier(self) -> None:
        """PRJ-101: "angefragt" and "kein Lieferant" do not go together – in the service, so in form and API."""
        with self.assertRaises(ValidationError) as caught:
            self.subrent(status=SubrentalStatus.REQUESTED)
        self.assertIn("subrental_status", caught.exception.message_dict)
        subrental = self.subrent()
        for status in (SubrentalStatus.REQUESTED, SubrentalStatus.ORDERED, SubrentalStatus.RECEIVED):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                services.update_line(subrental, rights=ALL_RIGHTS, subrental_status=status)
        services.update_line(subrental, rights=ALL_RIGHTS, supplier=self.nord, subrental_status="ordered")
        subrental.refresh_from_db()
        self.assertEqual((subrental.supplier, subrental.subrental_status), (self.nord, SubrentalStatus.ORDERED))
        # Taking the supplier away again needs the status "open" with it.
        with self.assertRaises(ValidationError):
            services.update_line(subrental, rights=ALL_RIGHTS, supplier=None)
        services.update_line(subrental, rights=ALL_RIGHTS, supplier=None, subrental_status="open")

    def test_a_copy_starts_open_again(self) -> None:
        """PRJ-101: the copy of a subrental is asked for anew – it keeps the supplier, the status is "open"."""
        planned = add_line(
            self.project, self.product, 1, title="Hazer", supplier=self.nord, subrental_status="ordered"
        ).line
        copy = line_services.duplicate_line(planned, rights=ALL_RIGHTS).line
        self.assertEqual((copy.supplier, copy.subrental_status), (self.nord, SubrentalStatus.OPEN))


class SupplierFieldTests(SubrentalCase):
    """PRJ-101: suggestions while typing, and a new supplier from there."""

    def test_suggestions_and_the_offer_to_create(self) -> None:
        """PRJ-101."""
        Supplier.objects.create(name="Licht-Verleih Süd", contact="Frau Berg")
        Supplier.objects.create(name="Verleih Alt", is_active=False)
        found = subrentals.supplier_suggestions("verleih", rights=ALL_RIGHTS)
        self.assertEqual([row["label"] for row in found[:-1]], ["Licht-Verleih Süd", "Verleih Nord"])
        self.assertEqual(found[0]["hint"], "Frau Berg")
        self.assertEqual(found[1]["hint"], "dispo@verleih-nord.example")
        self.assertTrue(found[-1]["create"])
        self.assertIn("name=verleih", found[-1]["create_url"])
        # Who may not create one is not offered it; an exact name needs no new supplier.
        reader = Rights(module_levels={"projects": 1})
        self.assertFalse(any(row.get("create") for row in subrentals.supplier_suggestions("Neu", rights=reader)))
        exact = subrentals.supplier_suggestions("verleih nord", rights=ALL_RIGHTS)
        self.assertFalse(any(row.get("create") for row in exact))
        # By address too.
        self.assertEqual(subrentals.supplier_suggestions("dispo@", rights=reader)[0]["label"], "Verleih Nord")

    def test_a_name_exists_only_once(self) -> None:
        """PRJ-101: "verleih nord" is "Verleih Nord"."""
        with self.assertRaises(ValidationError):
            subrentals.create_supplier(Supplier(name="verleih nord"))
        created = subrentals.create_supplier(Supplier(name="  Rent-All  ", email="info@rent-all.example"))
        self.assertEqual(created.name, "Rent-All")


class PageTests(SubrentalCase):
    """PRJ-106: lines, documents and mails of one supplier in one project."""

    def test_lines_and_purchase_total(self) -> None:
        """PRJ-106: the supplier's subrentals of the project with their purchase prices."""
        covering = self.subrent(supplier=self.nord, purchase_price=D("12.50"))
        planned = add_line(self.project, self.product, 1, title="Hazer", supplier=self.nord, purchase_price=D("40"))
        other = Supplier.objects.create(name="Rent-All")
        add_line(self.project, self.product, 1, title="Bühne", supplier=other)
        add_line(make_project("Anderes"), self.product, 1, title="Hazer", supplier=self.nord)
        page = subrentals.build_page(self.project, self.nord, rights=ALL_RIGHTS)
        self.assertEqual([row.line for row in page.rows], [covering, planned.line])
        self.assertEqual([row.purchase_cost for row in page.rows], [D("25.00"), D("40.00")])
        self.assertEqual(page.purchase_total, D("65.00"))
        self.assertEqual(page.status_counts, [("offen", 2)])
        self.assertEqual(subrentals.suppliers_of(self.project), [other, self.nord])

    def test_change_status_and_prices_at_once(self) -> None:
        """PRJ-106: all or nothing; purchase prices need their right."""
        first = self.subrent(supplier=self.nord)
        second = add_line(self.project, self.product, 1, title="Hazer", supplier=self.nord).line
        changed = subrentals.update_lines(
            self.project,
            self.nord,
            {
                first.pk: {"subrental_status": "ordered", "purchase_price": D("9")},
                second.pk: {"subrental_status": "open"},
            },
            rights=ALL_RIGHTS,
        )
        self.assertEqual(changed, [first])
        first.refresh_from_db()
        self.assertEqual((first.subrental_status, first.purchase_price), ("ordered", D("9.00")))
        stranger = add_line(self.project, self.product, 1, title="Bühne").line
        with self.assertRaises(ValidationError):
            subrentals.update_lines(
                self.project,
                self.nord,
                {second.pk: {"subrental_status": "ordered"}, stranger.pk: {"subrental_status": "ordered"}},
                rights=ALL_RIGHTS,
            )
        second.refresh_from_db()
        self.assertEqual(second.subrental_status, "open")  # nothing was saved
        with self.assertRaises(ValidationError):
            subrentals.update_lines(
                self.project, self.nord, {first.pk: {"purchase_price": D("1")}}, rights=NO_PURCHASE_PRICES
            )

    def test_documents_of_the_supplier_are_files_of_the_project(self) -> None:
        """PRJ-106: upload with a kind; among the project's files, never for the crew."""
        user = make_user()
        document = subrentals.add_document(
            self.project,
            self.nord,
            SimpleUploadedFile("angebot.pdf", PDF),
            kind=SupplierDocumentKind.OFFER,
            title="Angebot 4711",
            user=user,
        )
        self.assertEqual(
            (document.supplier, document.supplier_document_kind, document.visible_to_crew),
            (self.nord, "offer", False),
        )
        self.assertIn(document, self.project.files.all())
        self.assertEqual(subrentals.build_page(self.project, self.nord, rights=ALL_RIGHTS).files, [document])
        with self.assertRaises(ValidationError):
            subrentals.add_document(self.project, self.nord, SimpleUploadedFile("x.pdf", PDF), kind="x", user=user)
        # A kind only with a supplier; a supplier's file without a kind is "other".
        plain = ProjectFile(project=self.project, original_name="a.pdf", supplier_document_kind="invoice")
        with self.assertRaises(ValidationError):
            plain.clean()
        plain = ProjectFile(project=self.project, original_name="a.pdf", supplier=self.nord)
        plain.clean()
        self.assertEqual(plain.supplier_document_kind, SupplierDocumentKind.OTHER)


class MailTests(SubrentalCase):
    """PRJ-106: the mails of the project with the supplier – linked when stored, or by hand."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()

    def receive(self, sender: str, *, to: str = "projekte@verleih.example", cc: str = "") -> ProjectMail:
        headers = {"Cc": cc} if cc else None
        raw = make_mail(f"Angebot [RL#{self.project.number}]", sender=sender, to=to, headers=headers)
        return import_mail(raw, self.project, assigned_by=AssignedBy.TAG)

    def test_a_mail_from_the_supplier_is_linked(self) -> None:
        """PRJ-106: by the sender's address, exactly – "max@…" is not "x@…"."""
        self.assertEqual(self.receive("Dispo <DISPO@verleih-nord.example>").supplier, self.nord)
        self.assertIsNone(self.receive("Max <maxdispo@verleih-nord.example>").supplier)
        self.assertEqual(self.receive("Kunde <k@stadt.example>", cc="dispo@verleih-nord.example").supplier, self.nord)

    def test_an_address_of_two_suppliers_links_to_none(self) -> None:
        Supplier.objects.create(name="Verleih Nord GmbH", email="dispo@verleih-nord.example")
        self.assertIsNone(self.receive("dispo@verleih-nord.example").supplier)
        self.assertIsNone(supplier_for(set()))

    def test_a_sent_mail_is_linked(self) -> None:
        """PRJ-106: to the supplier's address, or named by the page of the subrental."""
        with capture_smtp():
            to_supplier = send_project_mail(
                self.project, to="Verleih Nord <dispo@verleih-nord.example>", subject="Anfrage", body="Hallo", user=None
            )
            named = send_project_mail(
                self.project,
                to="kollege@verleih-nord.example",
                subject="Anfrage",
                body="Hallo",
                user=None,
                supplier=self.nord,
            )
            other = send_project_mail(self.project, to="k@stadt.example", subject="Frage", body="Hallo", user=None)
        self.assertEqual((to_supplier.supplier, named.supplier, other.supplier), (self.nord, self.nord, None))

    def test_the_page_lists_linked_mails_and_mails_from_the_address(self) -> None:
        """PRJ-106: an address entered after the mail arrived still finds it; a mail linked elsewhere stays there."""
        rent_all = Supplier.objects.create(name="Rent-All")
        early = self.receive("info@rent-all.example")
        self.assertIsNone(early.supplier)
        moved = self.receive("dispo@verleih-nord.example")
        set_supplier(moved, rent_all)
        by_hand = self.receive("chef@stadt.example")
        set_supplier(by_hand, self.nord)
        rent_all.email = "info@rent-all.example"
        rent_all.save()
        self.assertEqual(set(mails_with(self.project, rent_all)), {early, moved})
        self.assertEqual(set(mails_with(self.project, self.nord)), {by_hand})
        entry = AuditLogEntry.objects.filter(object_id=str(by_hand.pk), changes__has_key="supplier").first()
        self.assertIsNotNone(entry)
        page = subrentals.build_page(self.project, self.nord, rights=ALL_RIGHTS)
        self.assertEqual(page.mails, [by_hand])
        # Without the right to read correspondence there are no mails on the page.
        no_mail = Rights(module_levels=dict(ALL_RIGHTS.module_levels), special_rights=frozenset())
        self.assertIsNone(subrentals.build_page(self.project, self.nord, rights=no_mail).mails)

    def test_addresses_of_header_texts(self) -> None:
        self.assertEqual(addresses_of('"Müller, Hans" <H@x.example>, b@y.example', ""), {"h@x.example", "b@y.example"})
