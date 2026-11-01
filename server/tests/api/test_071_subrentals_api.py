# SPDX-License-Identifier: GPL-3.0-or-later
"""API of subrentals: the status "open" (PRJ-101); the subrentals of a project per supplier, the documents
and the mails of a supplier (PRJ-106)."""

from __future__ import annotations

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.accounts.models import Role
from rentalars.mail.fetching import import_mail
from rentalars.mail.models import AssignedBy, ProjectMail
from rentalars.masterdata.models import Supplier
from rentalars.projects import services
from rentalars.projects.models import MaterialLine, ProjectFile
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, add_line, make_project, make_stock
from tests.mailbox import capture_smtp, configure_mailbox, make_mail

PDF = b"%PDF-1.4\n%%EOF\n"


class SubrentalApiCase(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.spots = make_stock("L-010", 4, "Spot", price="20.00")
        self.line = add_line(self.project, self.spots, 6).line
        self.nord = Supplier.objects.create(name="Verleih Nord", email="dispo@verleih-nord.example")
        self.base = f"{API}/projects/{self.project.pk}"

    def subrent(self, **fields: object) -> MaterialLine:
        return services.accept_subrental_suggestion(self.line, self.spots, 2, rights=ALL_RIGHTS, **fields)


class StatusApiTests(SubrentalApiCase):
    """PRJ-101 in the API of lines and of the subrental suggestion."""

    def test_open_by_default_and_never_asked_without_supplier(self) -> None:
        """PRJ-101."""
        accept = f"{self.base}/shortages/accept"
        body = {"line": self.line.pk, "product": self.spots.pk, "quantity": 2}
        self.assert_error(
            self.admin.post(accept, {**body, "status": "requested"}, format="json"), 400, "validation_error"
        )
        created = self.admin.post(accept, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["subrental_status"], "open")
        url = f"{self.base}/material-lines/{created.json()['id']}"
        self.assert_error(
            self.admin.patch(url, {"subrental_status": "ordered"}, format="json"),
            400,
            "validation_error",
            "subrental_status",
        )
        changed = self.admin.patch(url, {"subrental_status": "ordered", "supplier": self.nord.pk}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["subrental_status"], "ordered")

    def test_supplier_with_address_and_phone(self) -> None:
        """PRJ-106: the master data of a supplier."""
        created = self.admin.post(
            f"{API}/suppliers",
            {"name": "Rent-All", "contact": "Frau Berg", "email": "info@rent-all.example", "phone": "0221 1"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(
            {key: created.json()[key] for key in ("contact", "email", "phone")},
            {"contact": "Frau Berg", "email": "info@rent-all.example", "phone": "0221 1"},
        )
        self.assert_error(
            self.admin.post(f"{API}/suppliers", {"name": "X", "email": "kein-mail"}, format="json"),
            400,
            "validation_error",
            "email",
        )


class SubrentalPageApiTests(SubrentalApiCase):
    """``/projects/{id}/subrentals`` and ``/projects/{id}/subrentals/{supplier}`` (PRJ-106)."""

    def test_list_and_page(self) -> None:
        """PRJ-106."""
        covering = self.subrent(supplier=self.nord, purchase_price=Decimal("12.50"))
        listed = self.admin.get(f"{self.base}/subrentals")
        self.assertEqual(listed.status_code, 200, listed.content)
        (row,) = listed.json()
        self.assertEqual(
            (row["supplier"]["name"], row["lines"], row["statuses"], row["documents"], row["mails"]),
            ("Verleih Nord", 1, {"open": 1}, 0, 0),
        )
        page = self.admin.get(f"{self.base}/subrentals/{self.nord.pk}").json()
        self.assertEqual(page["supplier"]["email"], "dispo@verleih-nord.example")
        (line,) = page["lines"]
        self.assertEqual(
            (line["id"], line["status"], line["purchase_cost"], line["covers_line"]),
            (covering.pk, "open", "25.00", self.line.pk),
        )
        self.assertEqual(page["purchase_total"], "25.00")
        self.assertEqual(page["mails"], [])

    def test_purchase_prices_and_mails_need_their_rights(self) -> None:
        """AUT-019: no purchase prices without their right, no mails without the correspondence right."""
        self.subrent(supplier=self.nord, purchase_price=Decimal("12.50"))
        Role.objects.create(name="Planung", module_levels={"projects": 2}, special_rights=["prices"])
        planner = self.client_for("pia", "Planung")
        page = planner.get(f"{self.base}/subrentals/{self.nord.pk}").json()
        self.assertNotIn("purchase_price", page["lines"][0])
        self.assertNotIn("purchase_total", page)
        self.assertIsNone(page["mails"])
        self.assertEqual(self.client_for("ben", "Crew").get(f"{self.base}/subrentals").status_code, 404)

    def test_change_status_and_prices_at_once(self) -> None:
        """PRJ-106: ``PATCH`` – all or none."""
        covering = self.subrent(supplier=self.nord)
        url = f"{self.base}/subrentals/{self.nord.pk}"
        changed = self.admin.patch(
            url, {"lines": [{"id": covering.pk, "status": "ordered", "purchase_price": "11.00"}]}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["lines"][0]["status"], "ordered")
        covering.refresh_from_db()
        self.assertEqual((covering.subrental_status, covering.purchase_price), ("ordered", Decimal("11.00")))
        stranger = add_line(self.project, services.default_subrental_product(), 1, title="Hazer").line
        self.assert_error(
            self.admin.patch(
                url,
                {"lines": [{"id": covering.pk, "status": "received"}, {"id": stranger.pk, "status": "open"}]},
                format="json",
            ),
            400,
            "validation_error",
        )
        covering.refresh_from_db()
        self.assertEqual(covering.subrental_status, "ordered")
        self.assert_error(self.admin.patch(url, {"lines": "x"}, format="json"), 400, "validation_error", "lines")
        self.assert_error(
            self.admin.patch(url, {"lines": [{"id": covering.pk, "status": "x"}]}, format="json"),
            400,
            "validation_error",
        )
        Role.objects.create(name="Planung", module_levels={"projects": 2}, special_rights=["prices"])
        self.assert_error(
            self.client_for("pia", "Planung").patch(
                url, {"lines": [{"id": covering.pk, "purchase_price": "1"}]}, format="json"
            ),
            400,
            "validation_error",
        )


class SupplierDocumentApiTests(SubrentalApiCase):
    """PRJ-106: documents of a supplier are files of the project with ``supplier`` and its kind."""

    def test_upload_filter_and_change(self) -> None:
        files = f"{self.base}/files"
        created = self.admin.post(
            files,
            {
                "file": SimpleUploadedFile("angebot.pdf", PDF),
                "title": "Angebot 4711",
                "supplier": self.nord.pk,
                "supplier_document_kind": "offer",
            },
            format="multipart",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(
            (created.json()["supplier"], created.json()["supplier_document_kind"]), (self.nord.pk, "offer")
        )
        self.admin.post(files, {"file": SimpleUploadedFile("plan.pdf", PDF)}, format="multipart")
        self.assertEqual(len(self.admin.get(files).json()), 2)
        (only,) = self.admin.get(files, {"supplier": self.nord.pk}).json()
        self.assertEqual(only["title"], "Angebot 4711")
        changed = self.admin.patch(f"{files}/{only['id']}", {"supplier_document_kind": "invoice"}, format="json")
        self.assertEqual(changed.json()["supplier_document_kind"], "invoice")
        # Without a supplier there is no kind.
        unlinked = self.admin.patch(f"{files}/{only['id']}", {"supplier": None}, format="json")
        self.assertEqual((unlinked.json()["supplier"], unlinked.json()["supplier_document_kind"]), (None, ""))
        # A supplier's file without a kind is "other".
        other = self.admin.post(
            files, {"file": SimpleUploadedFile("x.pdf", PDF), "supplier": self.nord.pk}, format="multipart"
        )
        self.assertEqual(other.json()["supplier_document_kind"], "other")
        page = self.admin.get(f"{self.base}/subrentals/{self.nord.pk}").json()
        self.assertEqual([item["kind"] for item in page["documents"]], ["other"])
        self.assertEqual(ProjectFile.objects.count(), 3)


class SupplierMailApiTests(SubrentalApiCase):
    """PRJ-106: the supplier of a mail – read, filtered, set by hand, given when sending."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.incoming = import_mail(
            make_mail(f"Angebot [RL#{self.project.number}]", sender="dispo@verleih-nord.example"),
            self.project,
            assigned_by=AssignedBy.TAG,
        )
        self.other = import_mail(
            make_mail(f"Frage [RL#{self.project.number}]", sender="fahrer@spedition.example"),
            self.project,
            assigned_by=AssignedBy.TAG,
        )

    def test_read_filter_and_link_by_hand(self) -> None:
        mails = f"{self.base}/mails"
        self.assertEqual(self.admin.get(f"{mails}/{self.incoming.pk}").json()["supplier"], self.nord.pk)
        self.assertEqual(
            [row["id"] for row in self.admin.get(mails, {"supplier": self.nord.pk}).json()], [self.incoming.pk]
        )
        linked = self.admin.post(f"{mails}/{self.other.pk}/supplier", {"supplier": self.nord.pk}, format="json")
        self.assertEqual(linked.status_code, 200, linked.content)
        self.assertEqual(linked.json()["supplier"], self.nord.pk)
        self.assertEqual(len(self.admin.get(mails, {"supplier": self.nord.pk}).json()), 2)
        unlinked = self.admin.post(f"{mails}/{self.other.pk}/supplier", {"supplier": None}, format="json")
        self.assertIsNone(unlinked.json()["supplier"])
        self.assert_error(
            self.admin.post(f"{mails}/{self.other.pk}/supplier", {"supplier": "x"}, format="json"),
            400,
            "validation_error",
            "supplier",
        )
        self.assertEqual(
            self.admin.post(f"{mails}/{self.other.pk}/supplier", {"supplier": 999}, format="json").status_code, 404
        )
        reader = self.client_for("lea", "Nur-Lesen")
        self.assertEqual(
            reader.post(f"{mails}/{self.other.pk}/supplier", {"supplier": self.nord.pk}, format="json").status_code,
            403,
        )

    def test_send_about_a_subrental(self) -> None:
        with capture_smtp():
            sent = self.admin.post(
                f"{self.base}/mails",
                {
                    "to": "kollege@verleih-nord.example",
                    "subject": "Lieferung",
                    "body": "Hallo",
                    "supplier": self.nord.pk,
                },
                format="json",
            )
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertEqual(sent.json()["supplier"], self.nord.pk)
        self.assertEqual(ProjectMail.objects.get(pk=sent.json()["id"]).supplier, self.nord)
