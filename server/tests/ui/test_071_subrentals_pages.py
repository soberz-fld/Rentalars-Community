# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of subrentals: the supplier field with suggestions and "create" and the status "offen" (PRJ-101);
the page "Zumietung bei …" with lines, documents and correspondence, reached from the planning, from Planung →
Fehlbestände and from the supplier (PRJ-106)."""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.mail.fetching import import_mail
from rentalars.mail.models import AssignedBy, ProjectMail
from rentalars.masterdata.models import Supplier
from rentalars.projects import services
from rentalars.projects.models import MaterialLine, ProjectFile, ProjectStatus, SubrentalStatus
from tests.helpers import ALL_RIGHTS, add_line, make_project, make_stock
from tests.mailbox import capture_smtp, configure_mailbox, make_mail
from tests.ui.base import UiTestCase, form_data, forms_of

PDF = b"%PDF-1.4\n%%EOF\n"


class SubrentalPagesCase(UiTestCase):
    """A project whose spots are short, a supplier with address, phone and contact person."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(status=ProjectStatus.CONFIRMED)
        self.spots = make_stock("L-010", 4, "Spot", price="20.00")
        self.line = add_line(self.project, self.spots, 6).line
        self.nord = Supplier.objects.create(
            name="Verleih Nord", contact="Herr Maier", email="dispo@verleih-nord.example", phone="040 123456"
        )
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.page_url = reverse("projects:subrental", args=[self.project.pk, self.nord.pk])

    def subrent(self, **fields: object) -> MaterialLine:
        return services.accept_subrental_suggestion(self.line, self.spots, 2, rights=ALL_RIGHTS, **fields)


class SupplierFieldPageTests(SubrentalPagesCase):
    """PRJ-101: the dialogs of a subrental."""

    def test_the_line_dialog_types_the_supplier_and_says_status(self) -> None:
        """PRJ-101: a type-ahead instead of a list; "Status" with "offen" first and chosen."""
        subrental = self.subrent()
        url = reverse("projects:line_edit", args=[self.project.pk, subrental.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn(f'data-url="{reverse("projects:supplier_suggest")}"', dialog)
        self.assertIn('<label for="id_supplier_text">Lieferant</label>', dialog)
        self.assertIn('<input type="hidden" name="supplier" id="id_supplier" value=""', dialog)
        self.assertIn('<label for="id_subrental_status">Status <span', dialog)
        self.assertNotIn("Status beim Lieferanten", dialog)
        self.assertEqual(form_data(self.htmx("get", url), "subrental_status")["subrental_status"], "open")
        # "angefragt" without a supplier is refused at the status.
        data = form_data(self.htmx("get", url), "subrental_status", subrental_status="requested")
        refused = self.assert_ok(self.htmx("post", url, data))
        self.assertIn("Ohne Lieferanten kann der Status nur „offen“ sein.", refused)
        data.update(supplier=str(self.nord.pk))
        self.htmx("post", url, data)
        subrental.refresh_from_db()
        self.assertEqual((subrental.supplier, subrental.subrental_status), (self.nord, "requested"))
        # The chosen supplier shows by name in the field.
        self.assertIn('value="Verleih Nord"', self.assert_ok(self.htmx("get", url)))

    def test_the_subrent_dialog(self) -> None:
        """PRJ-101, PRJ-084: supplier with suggestions, status "offen" unless a supplier is chosen."""
        url = reverse("projects:subrental_accept", args=[self.project.pk, self.line.pk])
        query = {"product": self.spots.pk, "quantity": 2}
        dialog = self.assert_ok(self.htmx("get", url, query))
        self.assertIn("data-typeahead", dialog)
        data = form_data(self.htmx("get", url, query), "quantity", status="ordered")
        self.assertIn(
            "Ohne Lieferanten kann der Status nur „offen“ sein.", self.assert_ok(self.htmx("post", url, data))
        )
        self.assertFalse(MaterialLine.objects.filter(covers_line=self.line).exists())
        data.update(supplier=str(self.nord.pk))
        self.assertIn("closeDialog", self.htmx("post", url, data)["HX-Trigger"])
        subrental = MaterialLine.objects.get(covers_line=self.line)
        self.assertEqual((subrental.supplier, subrental.subrental_status), (self.nord, SubrentalStatus.ORDERED))

    def test_suggestions_and_a_new_supplier_in_a_dialog(self) -> None:
        """PRJ-101: the last suggestion creates the supplier; the dialog answers with "objectCreated"."""
        found = self.client.get(reverse("projects:supplier_suggest"), {"q": "Rent"}).json()
        self.assertEqual(found[-1]["label"], "„Rent“ als neuen Lieferanten anlegen")
        create_url = found[-1]["create_url"] + "&field=supplier"
        dialog = self.assert_ok(self.htmx("get", create_url))
        self.assertIn('hx-target="this"', dialog)  # stays in its own dialog, over the dialog of the line
        self.assertIn('value="Rent"', dialog)
        data = form_data(self.htmx("get", create_url), "name", name="Rent-All", email="info@rent-all.example")
        answer = self.htmx("post", create_url, data)
        self.assertEqual(answer.status_code, 204)
        trigger = json.loads(answer["HX-Trigger"])
        created = Supplier.objects.get(name="Rent-All")
        self.assertEqual(trigger["objectCreated"], {"field": "supplier", "id": created.pk, "label": "Rent-All"})
        self.assertTrue(trigger["closeDialog"])
        self.assertEqual(created.email, "info@rent-all.example")
        # The same name once more is refused – in other case too.
        again = self.assert_ok(self.htmx("post", create_url, {**data, "name": "rent-all"}))
        self.assertIn("Einen Lieferanten mit diesem Namen gibt es schon.", again)

    def test_who_may_ask_and_who_may_create(self) -> None:
        """PRJ-101: reading projects is enough for suggestions; creating needs write access."""
        reader = self.browser_for("lea", "Nur-Lesen")
        found = reader.get(reverse("projects:supplier_suggest"), {"q": "Neu"}).json()
        self.assertFalse(any(row.get("create") for row in found))
        self.assertEqual(reader.get(reverse("projects:supplier_quick_create")).status_code, 403)
        Role.objects.create(name="Kasse", module_levels={"customers": 1})
        self.assertEqual(
            self.browser_for("kai", "Kasse").get(reverse("projects:supplier_suggest"), {"q": "x"}).status_code, 403
        )


class SubrentalPageTests(SubrentalPagesCase):
    """PRJ-106: "Zumietung bei …"."""

    def test_reached_from_planning_shortages_and_supplier(self) -> None:
        """PRJ-106: the supplier's name leads there – in the planning, under Fehlbestände, in the master data."""
        self.subrent(supplier=self.nord)
        self.assertIn(f'href="{self.page_url}"', self.assert_ok(self.client.get(self.detail)))
        shortages = self.assert_ok(self.client.get(reverse("availability:shortages")))
        self.assertIn(f'href="{self.page_url}"', shortages)
        self.assertIn(f'<option value="{self.nord.pk}">Verleih Nord</option>', shortages)
        rent_all = Supplier.objects.create(name="Rent-All")
        add_line(self.project, services.default_subrental_product(), 1, title="Hazer", supplier=rent_all)
        filtered = self.assert_ok(self.client.get(reverse("availability:shortages"), {"supplier": self.nord.pk}))
        self.assertIn("Zumietungen bei Verleih Nord", filtered)
        self.assertNotIn("Hazer", filtered)
        admin = self.assert_ok(self.client.get(reverse("admin:masterdata_supplier_change", args=[self.nord.pk])))
        self.assertIn(f"/shortages/?supplier={self.nord.pk}#subrentals", admin)
        self.assertIn("dispo@verleih-nord.example", admin)

    def test_lines_with_status_and_purchase_prices(self) -> None:
        """PRJ-106: status and purchase price of every line at once."""
        covering = self.subrent(supplier=self.nord, purchase_price=Decimal("12.50"))
        page = self.assert_ok(self.client.get(self.page_url))
        self.assertIn("Zumietung bei Verleih Nord", page)
        for text in ("Herr Maier", "mailto:dispo@verleih-nord.example", "040 123456", "2 Stk. × Spot", "25,00"):
            self.assertIn(text, page)
        data = form_data(self.client.get(self.page_url), f"status_{covering.pk}")
        data.update({f"status_{covering.pk}": "ordered", f"price_{covering.pk}": "11,00"})
        response = self.client.post(
            reverse("projects:subrental_lines", args=[self.project.pk, self.nord.pk]), data, follow=True
        )
        self.assertIn("Die Zumietungen sind gespeichert.", self.messages_of(response))
        covering.refresh_from_db()
        self.assertEqual((covering.subrental_status, covering.purchase_price), ("ordered", Decimal("11.00")))

    def test_without_purchase_price_right_and_read_only(self) -> None:
        """AUT-019: no purchase prices without their right; reading only: no forms."""
        self.subrent(supplier=self.nord, purchase_price=Decimal("12.50"))
        Role.objects.create(
            name="Planung ohne EK", module_levels={"projects": 3}, special_rights=["prices", "correspondence_read"]
        )
        planner = self.browser_for("pia", "Planung ohne EK")
        page = self.assert_ok(planner.get(self.page_url))
        self.assertNotIn("12,50", page)
        self.assertNotIn('name="price_', page)
        self.assertIn('name="status_', page)
        reader = self.assert_ok(self.browser_for("lea", "Nur-Lesen").get(self.page_url))
        self.assertNotIn('name="status_', reader)
        self.assertNotIn('name="file"', reader)
        self.assertIn("25,00", reader)
        crew = self.browser_for("ben", "Crew")
        self.assertEqual(crew.get(self.page_url).status_code, 404)

    def test_documents_of_the_supplier(self) -> None:
        """PRJ-106: upload with a kind; also among the files on the tab "Dokumente"."""
        upload = reverse("projects:subrental_document_add", args=[self.project.pk, self.nord.pk])
        response = self.client.post(
            upload,
            {"file": SimpleUploadedFile("ab.pdf", PDF), "kind": "confirmation", "title": "AB 77"},
            follow=True,
        )
        self.assertIn("Dokument abgelegt. Es steht auch bei den Dateien des Projekts.", self.messages_of(response))
        stored = ProjectFile.objects.get()
        self.assertEqual((stored.supplier, stored.supplier_document_kind), (self.nord, "confirmation"))
        page = self.assert_ok(self.client.get(self.page_url))
        self.assertIn("AB 77", page)
        self.assertIn("Auftragsbestätigung", page)
        documents = self.assert_ok(self.client.get(reverse("documents:list", args=[self.project.pk])))
        self.assertIn("Auftragsbestätigung · ", documents)
        self.assertIn(f'href="{self.page_url}">Zumietung bei Verleih Nord</a>', documents)
        # The kind can be changed with the file.
        edit = reverse("projects:file_edit", args=[self.project.pk, stored.pk])
        self.client.post(edit, form_data(self.client.get(edit), "title", supplier_document_kind="invoice"))
        stored.refresh_from_db()
        self.assertEqual(stored.supplier_document_kind, "invoice")
        refused = self.client.post(upload, {"file": SimpleUploadedFile("x.exe", b"MZ"), "kind": "offer"})
        self.assertIn("Dateien dieser Art können nicht abgelegt werden.", self.assert_ok(refused))

    def test_correspondence_with_the_supplier(self) -> None:
        """PRJ-106: write from the page with the project's tag; mails from and to the supplier show there."""
        configure_mailbox()
        incoming = import_mail(
            make_mail(f"Angebot [RL#{self.project.number}]", sender="Dispo <dispo@verleih-nord.example>"),
            self.project,
            assigned_by=AssignedBy.TAG,
        )
        other = import_mail(
            make_mail(f"Frage [RL#{self.project.number}]", sender="kunde@stadt.example"),
            self.project,
            assigned_by=AssignedBy.TAG,
        )
        page = self.assert_ok(self.client.get(self.page_url))
        self.assertIn(f"/mails/{incoming.pk}/", page)
        self.assertNotIn(f"/mails/{other.pk}/", page)
        compose = reverse("mail:compose", args=[self.project.pk]) + f"?supplier={self.nord.pk}"
        self.assertIn(f'href="{compose.replace("&", "&amp;")}"', page)
        written = self.client.get(compose)
        data = form_data(written, "subject", body="Bitte bestätigen.")
        self.assertEqual(data["to"], "Herr Maier <dispo@verleih-nord.example>")
        self.assertEqual(data["subject"], f"Zumietung für {self.project.name}")
        self.assertIn("Die Mail wird dort abgelegt.", self.assert_ok(written))
        with capture_smtp() as sent:
            response = self.client.post(compose, data)
        self.assertRedirects(response, self.page_url + "#mails", fetch_redirect_response=False)
        (message,) = sent
        self.assertIn(f"[RL#{self.project.number}]", message["Subject"])
        mail = ProjectMail.objects.get(direction="out")
        self.assertEqual(mail.supplier, self.nord)
        self.assertIn(f"/mails/{mail.pk}/", self.assert_ok(self.client.get(self.page_url)))

    def test_a_mail_is_put_to_a_subrental_by_hand(self) -> None:
        """PRJ-106: on the page of the mail – "Gehört zu einer Zumietung?"."""
        configure_mailbox()
        self.subrent(supplier=self.nord)
        mail = import_mail(
            make_mail(f"Lieferung [RL#{self.project.number}]", sender="fahrer@spedition.example"),
            self.project,
            assigned_by=AssignedBy.TAG,
        )
        detail = self.assert_ok(self.client.get(reverse("mail:detail", args=[self.project.pk, mail.pk])))
        self.assertIn("Gehört zu einer Zumietung?", detail)
        target = reverse("projects:mail_supplier", args=[self.project.pk, mail.pk])
        response = self.client.post(target, {"supplier": self.nord.pk}, follow=True)
        self.assertIn("Die Mail gehört zur Zumietung bei Verleih Nord.", self.messages_of(response))
        mail.refresh_from_db()
        self.assertEqual(mail.supplier, self.nord)
        self.assertIn(f'href="{self.page_url}">bei Verleih Nord</a>', self.assert_ok(response))
        self.client.post(target, {"supplier": ""})
        mail.refresh_from_db()
        self.assertIsNone(mail.supplier)

    def test_the_forms_on_the_page_are_complete(self) -> None:
        """Every form of the page sends to an address of its own."""
        self.subrent(supplier=self.nord)
        targets = {form.target for form in forms_of(self.client.get(self.page_url))}
        self.assertIn(reverse("projects:subrental_lines", args=[self.project.pk, self.nord.pk]), targets)
        self.assertIn(reverse("projects:subrental_document_add", args=[self.project.pk, self.nord.pk]), targets)
