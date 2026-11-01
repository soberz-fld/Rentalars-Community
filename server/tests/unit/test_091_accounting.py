# SPDX-License-Identifier: GPL-3.0-or-later
"""DOK-019, DOK-020: the main entry "Buchhaltung" – the outgoing documents and the monthly statement.

Requirement: a main entry "Buchhaltung" between "Materialverwaltung" and "Kunden", to which the tab "Monatsabrechnung" moves from
"Projekte", and a table of all outgoing documents; the table requirements (columns, filters, sorting, groups) give all the other
possibilities.

* The entry stands between "Materialverwaltung" and "Kunden"; its tabs are "Ausgangsbelege" and
  "Monatsabrechnung", the latter no longer under "Projekte" and below /accounting/monthly/.
* "Ausgangsbelege": every document a customer gets – offers, order confirmations, delivery notes, invoices,
  cancellations; no crew dispositions – as a table of core/tables.py: columns, filters, sorting and groups by every
  column, CSV; the sums of the filtered documents per kind. For who sees prices and reads every project.
* The same through the API: ``GET /accounting/documents`` and ``GET /accounting/documents/totals``.
"""

from __future__ import annotations

import csv
import datetime
import io
import re
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import ProjectScope
from rentalars.core.navigation import entries_for
from rentalars.documents import outgoing, statements
from rentalars.documents.models import Document, DocumentKind, LexwareTransfer, MonthlyStatement, TransferState
from rentalars.documents.outgoing_tables import OUTGOING_TABLE
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import NOW, at, make_customer, make_project, make_user
from tests.ui.base import UiTestCase
from tests.unit.test_090_statements import MARCH, StatementSetup, invoices_in_rentalars

OUTGOING = "/accounting/documents/"
MONTHLY = "/accounting/monthly/"
D = Decimal

GROUP_ROW = re.compile(r'<tr class="table-group"><th colspan="\d+" scope="colgroup">(.*?)</th></tr>', re.S)
HEADER = re.compile(r'<th class="[^"]*"(?: aria-sort="\w+")? scope="col">(?:<a href="[^"]*">)?([^<]+)')

TITLES = {
    DocumentKind.OFFER: "Angebot",
    DocumentKind.ORDER_CONFIRMATION: "Auftragsbestätigung",
    DocumentKind.DELIVERY_NOTE: "Lieferschein",
    DocumentKind.INVOICE: "Rechnung",
    DocumentKind.CANCELLATION: "Stornorechnung",
    DocumentKind.CREW_SHEET: "Crew-Disposition",
}


def navigation_of(text: str) -> list[tuple[str, str]]:
    """The entries of the main navigation: (label, address)."""
    start = text.index('<ul class="nav">')
    part = text[start : text.index("</ul>", start)]
    return [(label.strip(), url) for url, label in re.findall(r'<a href="([^"]+)"[^>]*>.*?</svg>([^<>]+)</a>', part)]


def tabs_of(text: str) -> list[str]:
    """The labels of the tabs of a page."""
    start = text.index('<nav class="tabs"')
    return [label.strip() for label in re.findall(r">([^<>]+)</a>", text[start : text.index("</nav>", start)])]


def groups_of(text: str) -> list[str]:
    """The headings of the groups of the table, as plain text: ``Rechnung 2 Einträge``."""
    return [" ".join(re.sub(r"<[^>]+>", " ", heading).split()) for heading in GROUP_ROW.findall(text)]


def numbers_of(text: str) -> list[str]:
    """The document numbers of the rows, in their order."""
    return re.findall(r'title="PDF öffnen">([^<]+)</a>', text)


def csv_of(response: object) -> list[list[str]]:
    """The rows of a CSV answer."""
    text = response.content.decode("utf-8-sig")  # type: ignore[attr-defined]
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def make_document(project: object, kind: str, number: str, *, net: str | None = None, **fields: object) -> Document:
    """A stored document without the work of a PDF: what the list reads of it (DOK-007)."""
    gross = fields.pop("gross", None)
    if net is not None and gross is None:
        gross = str((D(net) * D("1.19")).quantize(D("0.01")))
    return Document.objects.create(
        project=project,
        kind=kind,
        number=number,
        title=TITLES[kind],
        issued_on=fields.pop("issued_on", datetime.date(2027, 2, 10)),
        net_total=D(net) if net is not None else None,
        gross_total=D(gross) if gross is not None else None,
        file=f"documents/{number}.pdf",
        sha256="0" * 64,
        content={"recipient": fields.pop("recipient", [project.customer_name, "Markt 1"])},  # type: ignore[attr-defined]
        **fields,
    )


def role(name: str, levels: dict[str, int], rights: list[str], scope: str = ProjectScope.ALL) -> Role:
    """A role of this test."""
    return Role.objects.create(name=name, module_levels=levels, special_rights=rights, project_scope=scope)


class DocumentsSetup:
    """Two customers; an offer, an order confirmation, a delivery note, an invoice and its cancellation, a second
    invoice – and a crew disposition, which is no outgoing document."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.paula.first_name, self.paula.last_name = "Paula", "Plan"
        self.paula.save()
        self.theater = make_customer("Theater am Markt")
        self.works = make_customer("Stadtwerke")
        self.fest = make_project("Stadtfest", customer=self.theater)
        self.fair = make_project("Messe", customer=self.works)
        self.offer = make_document(
            self.fest, DocumentKind.OFFER, "AN-2027-0001", net="100.00", issued_on=day(1), sent_at=at(1, 10, month=2)
        )
        self.order = make_document(
            self.fest, DocumentKind.ORDER_CONFIRMATION, "AB-2027-0001", net="100.00", issued_on=day(2)
        )
        self.delivery = make_document(self.fest, DocumentKind.DELIVERY_NOTE, "LS-2027-0001", issued_on=day(3))
        self.invoice = make_document(
            self.fest,
            DocumentKind.INVOICE,
            "RE-2027-0001",
            net="200.00",
            issued_on=day(4),
            sent_at=at(5, 9, month=2),
            sent_to="kasse@theater.example",
            created_by=self.paula,
        )
        self.cancellation = make_document(
            self.fest,
            DocumentKind.CANCELLATION,
            "RE-2027-0002",
            net="-200.00",
            issued_on=day(6),
            cancels=self.invoice,
        )
        self.invoice.cancelled_by = self.cancellation
        self.invoice.save(update_fields=["cancelled_by"])
        self.second = make_document(
            self.fair, DocumentKind.INVOICE, "RE-2027-0003", net="50.00", issued_on=datetime.date(2027, 3, 1)
        )
        self.crew = make_document(self.fest, DocumentKind.CREW_SHEET, "CD-2027-0001", issued_on=day(7))
        LexwareTransfer.objects.create(document=self.invoice, state=TransferState.DONE, transferred_at=NOW)


def day(number: int) -> datetime.date:
    """A day of February 2027."""
    return datetime.date(2027, 2, number)


# --- The entry and its tabs ----------------------------------------------------------------------------------


class NavigationTests(UiTestCase):
    """The entry "Buchhaltung" between "Materialverwaltung" and "Kunden", for whom it shows (DOK-019)."""

    def entry_of(self, client: object) -> str | None:
        """Where the entry "Buchhaltung" leads for a user; ``None`` without it."""
        text = self.assert_ok(client.get(reverse("core:home")))  # type: ignore[attr-defined]
        return dict(navigation_of(text)).get("Buchhaltung")

    def test_between_material_management_and_customers(self) -> None:
        labels = [label for label, _url in navigation_of(self.assert_ok(self.client.get(reverse("core:home"))))]
        position = labels.index("Buchhaltung")
        self.assertEqual(labels[position - 1 : position + 2], ["Materialverwaltung", "Buchhaltung", "Kunden"])
        self.assertEqual(self.entry_of(self.client), OUTGOING)

    def test_per_role(self) -> None:
        """Prices and every project: both tabs; without prices nothing; assigned projects: the statements only."""
        cases = {
            "Projektleitung": OUTGOING,
            "Nur-Lesen": OUTGOING,
            "Lager": "/accounting/incoming/",  # no prices of projects, but the purchase prices: the incoming invoices
            "Personaldisposition": None,
        }
        for name, expected in cases.items():
            with self.subTest(role=name):
                self.assertEqual(self.entry_of(self.browser_for(name.lower(), name)), expected)
        assigned = role("Disposition eigene", {"projects": 2, "customers": 1}, ["prices"], ProjectScope.ASSIGNED)
        user = make_user("ida")
        user.roles.set([assigned])
        browser = self.browser_of(user)
        # Reading the customers and seeing prices opens the monthly statement of the own cases (DOK-016), not the
        # list of every customer's documents.
        self.assertEqual(self.entry_of(browser), MONTHLY)
        self.assertEqual(tabs_of(self.assert_ok(browser.get(MONTHLY))), ["Monatsabrechnung"])
        self.assertEqual(browser.get(OUTGOING).status_code, 403)
        without_prices = role("Lesen ohne Preise", {"projects": 1, "customers": 1}, [])
        user = make_user("otto")
        user.roles.set([without_prices])
        self.assertIsNone(self.entry_of(self.browser_of(user)))
        # Every project but not the module "Customers": the outgoing documents – and the statements in the tabs, as
        # who reads every project sees the customers (AUT-023).
        all_projects = role("Buchhaltung", {"projects": 1}, ["prices"])
        user = make_user("berta")
        user.roles.set([all_projects])
        browser = self.browser_of(user)
        self.assertEqual(self.entry_of(browser), OUTGOING)
        self.assertEqual(
            tabs_of(self.assert_ok(browser.get(OUTGOING))), ["Ausgangsbelege", "Monatsabrechnung", "Offene Posten"]
        )
        self.assert_ok(browser.get(MONTHLY))

    def test_the_entry_as_data(self) -> None:
        from rentalars.accounts.rights import Rights

        links = entries_for(Rights.everything())
        entry = next(link for link in links if str(link.label) == "Buchhaltung")
        self.assertEqual(entry.icon, "invoice")
        self.assertEqual(
            entry.starts,
            (
                ("/accounting/", OUTGOING),
                (MONTHLY, MONTHLY),
                ("/accounting/incoming/", "/accounting/incoming/"),
                ("/accounting/assets/", "/accounting/assets/"),
            ),
        )
        # A page of a statement belongs to the tab "Monatsabrechnung": "Back" without a trail leads there.
        self.assertEqual(entry.start_for("/accounting/monthly/5/"), MONTHLY)


class TabsTests(StatementSetup, UiTestCase):
    """The tabs of "Buchhaltung"; the monthly statement moved there from "Projekte" (DOK-019)."""

    def test_the_outgoing_documents_first(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING))
        self.assertIn("<h1>Buchhaltung</h1>", text)
        self.assertEqual(
            tabs_of(text),
            [
                "Ausgangsbelege",
                "Monatsabrechnung",
                "Beleg erfassen",
                "Eingangsbelege",
                "Anlagenspiegel",
                "Verkäufe aus Bestand",
                "Offene Posten",  # DOK-048, DOK-045, DOK-043
                "Bank",  # DOK-050
                "EÜR",
                "Archiv",
                "Altprojekte importieren",
            ],
        )
        self.assertIn(f'<a href="{OUTGOING}" aria-current="page">Ausgangsbelege</a>', text)
        self.assertIn(f'<a href="{OUTGOING}" aria-current="page">', text.split('<ul class="nav">')[1])
        self.assertNotIn('class="back-link', text)  # a tab is a start page (UIX-041)
        # DATEV and Lexware Office stay in the settings – a way there.
        self.assertIn(reverse("documents:accounting"), text)

    def test_the_monthly_statement_moved(self) -> None:
        self.assertEqual(reverse("documents:statements"), MONTHLY)
        self.work(self.spot, at(3, 9), at(3, 12))
        text = self.assert_ok(self.client.get(MONTHLY, {"month": "2027-03"}))
        self.assertIn("<h1>Buchhaltung</h1>", text)
        self.assertIn(f'<a href="{MONTHLY}" aria-current="page">Monatsabrechnung</a>', text)
        self.assertIn("Monatsabrechnung März 2027", text)
        self.assertNotIn('class="back-link', text)
        response = self.client.post(
            reverse("documents:statement_create"), {"customer": self.customer.pk, "month": "2027-03"}
        )
        draft = MonthlyStatement.objects.get()
        self.assertRedirects(response, f"{MONTHLY}{draft.pk}/")
        page = self.assert_ok(self.client.get(f"{MONTHLY}{draft.pk}/"))
        self.assertEqual(
            tabs_of(page),
            [
                "Ausgangsbelege",
                "Monatsabrechnung",
                "Beleg erfassen",
                "Eingangsbelege",
                "Anlagenspiegel",
                "Verkäufe aus Bestand",
                "Offene Posten",  # DOK-048, DOK-045, DOK-043
                "Bank",  # DOK-050
                "EÜR",
                "Archiv",
                "Altprojekte importieren",
            ],
        )
        self.assertIn(f'<a href="{OUTGOING}" aria-current="page">', page.split('<ul class="nav">')[1])
        # NFA-074: the old addresses are gone, no redirect.
        for old in ("/projects/service-cases/monthly/", f"/projects/service-cases/monthly/{draft.pk}/"):
            self.assertEqual(self.client.get(old).status_code, 404)

    def test_no_longer_under_projects(self) -> None:
        for name in ("projects:list", "projects:cases", "projects:open_items"):
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name)))
                self.assertNotIn("Monatsabrechnung", tabs_of(text))
                self.assertNotIn(MONTHLY, tabs_of(text))


# --- The outgoing documents --------------------------------------------------------------------------------


class OutgoingPageTests(DocumentsSetup, UiTestCase):
    """Buchhaltung → Ausgangsbelege: a table of core/tables.py over every document a customer got (DOK-020)."""

    def test_the_documents_and_the_default_columns(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING))
        self.assertEqual(
            HEADER.findall(text), ["Nummer", "Art", "Datum", "Projekt", "Kunde", "Netto", "Steuer", "Brutto", "Status"]
        )
        # Newest first; no crew disposition – it goes to the crew.
        self.assertEqual(
            numbers_of(text),
            ["RE-2027-0003", "RE-2027-0002", "RE-2027-0001", "LS-2027-0001", "AB-2027-0001", "AN-2027-0001"],
        )
        self.assertNotIn("CD-2027-0001", text)
        # As stored: 200,00 net, 38,00 tax, 238,00 gross; the cancellation negative.
        for amount in ("200,00 €", "38,00 €", "238,00 €", "-238,00 €"):
            self.assertIn(amount, text)
        self.assertIn('<span class="badge ">storniert</span><div class="muted small">durch RE-2027-0002</div>', text)
        self.assertIn("storniert RE-2027-0001", text)  # the cancellation names its invoice
        self.assertIn('<span class="badge green">gesendet</span>', text)
        self.assertIn('<span class="badge yellow">nicht gesendet</span>', text)
        # Links: the PDF, and the project's tab "Dokumente".
        self.assertIn(f'href="{reverse("documents:file", args=[self.invoice.pk])}"', text)
        self.assertIn(f'href="{reverse("documents:list", args=[self.fest.pk])}"', text)
        self.assertIn('<tr class="is-muted">', text)  # the cancelled invoice

    def test_every_column_sorts_both_ways(self) -> None:
        state = OUTGOING_TABLE
        for column in state.columns:
            for sort in (column.key, f"-{column.key}"):
                with self.subTest(sort=sort):
                    text = self.assert_ok(self.client.get(OUTGOING, {"cols": "all", "sort": sort}))
                    self.assertEqual(len(numbers_of(text)), 6)
                    self.assertIn(f'aria-sort="{"descending" if sort.startswith("-") else "ascending"}"', text)
        # By gross: -238,00 €, 59,50 €, 119,00 € (order confirmation, offer: by number), 238,00 €; the delivery note has none.
        by_gross = numbers_of(self.assert_ok(self.client.get(OUTGOING, {"sort": "gross"})))
        priced = [number for number in by_gross if number != "LS-2027-0001"]
        self.assertEqual(priced, ["RE-2027-0002", "RE-2027-0003", "AB-2027-0001", "AN-2027-0001", "RE-2027-0001"])
        backwards = numbers_of(self.assert_ok(self.client.get(OUTGOING, {"sort": "-gross"})))
        self.assertEqual([number for number in backwards if number != "LS-2027-0001"], priced[::-1])
        by_kind = numbers_of(self.assert_ok(self.client.get(OUTGOING, {"sort": "kind"})))
        self.assertEqual(by_kind[:3], ["AN-2027-0001", "AB-2027-0001", "LS-2027-0001"])  # in the order of a project

    def test_every_shown_column_groups(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING, {"cols": "all"}))
        offered = re.findall(r'<option value="([\w-]+)"', text[text.index('name="group"') :].split("</select>")[0])
        self.assertEqual(offered, [column.key for column in OUTGOING_TABLE.columns])  # every column, in its order
        for key in offered:
            with self.subTest(group=key):
                page = self.assert_ok(self.client.get(OUTGOING, {"cols": "all", "group": key}))
                self.assertTrue(groups_of(page), key)
                self.assertEqual(len(numbers_of(page)), 6)

    def test_groups_count_the_whole_list(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING, {"group": "customer"}))
        self.assertEqual(groups_of(text), ["Stadtwerke 1 Eintrag", "Theater am Markt 5 Einträge"])
        text = self.assert_ok(self.client.get(OUTGOING, {"group": "kind"}))
        self.assertEqual(
            groups_of(text),
            [
                "Angebot 1 Eintrag",
                "Auftragsbestätigung 1 Eintrag",
                "Lieferschein 1 Eintrag",
                "Rechnung 2 Einträge",
                "Stornorechnung 1 Eintrag",
            ],
        )
        text = self.assert_ok(self.client.get(OUTGOING, {"group": "state"}))
        self.assertEqual(
            groups_of(text),
            ["nicht gesendet 3 Einträge", "gesendet 1 Eintrag", "storniert 1 Eintrag", "Stornorechnung 1 Eintrag"],
        )
        text = self.assert_ok(self.client.get(OUTGOING, {"cols": "number,month", "group": "month"}))
        # The groups in the order of their column – the months ascending –, the rows in the chosen order within.
        self.assertEqual(groups_of(text), ["Februar 2027 5 Einträge", "März 2027 1 Eintrag"])

    def test_filters(self) -> None:
        def numbers(**params: str) -> list[str]:
            return sorted(numbers_of(self.assert_ok(self.client.get(OUTGOING, params))))

        self.assertEqual(numbers(kind="invoice"), ["RE-2027-0001", "RE-2027-0003"])
        self.assertEqual(numbers(kind="bookable"), ["RE-2027-0001", "RE-2027-0002", "RE-2027-0003"])
        self.assertEqual(numbers(kind="delivery_note"), ["LS-2027-0001"])
        self.assertEqual(numbers(state="sent"), ["AN-2027-0001", "RE-2027-0001"])
        self.assertEqual(numbers(state="cancelled"), ["RE-2027-0001"])
        self.assertEqual(numbers(kind="invoice", state="not_cancelled"), ["RE-2027-0003"])
        self.assertEqual(numbers(customer=str(self.works.pk)), ["RE-2027-0003"])
        self.assertEqual(numbers(project=str(self.fair.pk)), ["RE-2027-0003"])
        self.assertEqual(numbers(since="2027-02-04", until="2027-02-06"), ["RE-2027-0001", "RE-2027-0002"])
        self.assertEqual(numbers(q="Messe"), ["RE-2027-0003"])
        self.assertEqual(numbers(q="AB-2027"), ["AB-2027-0001"])
        # DOK-011: the invoice in Lexware Office; the others not yet.
        self.assertEqual(numbers(lexware="done"), ["RE-2027-0001"])
        self.assertEqual(numbers(lexware="missing"), ["RE-2027-0002", "RE-2027-0003"])
        # A value the page does not know filters nothing, it does not fail.
        self.assertEqual(len(numbers(kind="crew_sheet", since="gestern")), 6)

    def test_the_filters_are_folded_and_offer_the_customers(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING, {"project": str(self.fair.pk)}))
        self.assertIn("data-filter-panel", text)
        self.assertIn(f'<option value="{self.works.pk}">Stadtwerke</option>', text)
        self.assertIn(f'<option value="{self.fair.pk}" selected>{self.fair.number} Messe</option>', text)
        self.assertIn('<option value="monthly">Monatsrechnungen der Servicefälle</option>', text)

    def test_sums_of_the_filtered_documents(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING))
        sums = text[text.index("Summen der gefilterten Belege") :]
        self.assertIn("<td>Rechnung</td>", sums)
        self.assertIn("250,00 €", sums)  # 200 + 50 net
        self.assertIn("<td>Stornorechnung</td>", sums)
        self.assertIn(
            '<tr class="sum"><td>Rechnungen und Stornorechnungen zusammen</td><td class="num" data-label="Anzahl">3</td>'
            '<td class="num" data-label="Netto">50,00 €</td><td class="num" data-label="Steuer">9,50 €</td>'
            '<td class="num" data-label="Brutto">59,50 €</td></tr>',
            sums,
        )
        self.assertIn('<td>Lieferschein</td><td class="num" data-label="Anzahl">1</td><td class="num muted"', sums)
        filtered = self.assert_ok(self.client.get(OUTGOING, {"kind": "offer"}))
        self.assertNotIn("zusammen", filtered)

    def test_csv(self) -> None:
        self.theater.name = '=HYPERLINK("http://evil.example")'
        self.theater.save()
        response = self.client.get(OUTGOING, {"format": "csv", "kind": "invoice"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = csv_of(response)
        self.assertEqual(rows[0], ["Nummer", "Art", "Datum", "Projekt", "Kunde", "Netto", "Steuer", "Brutto", "Status"])
        by_number = {row[0]: row for row in rows[1:]}
        self.assertEqual(set(by_number), {"RE-2027-0001", "RE-2027-0003"})
        first = by_number["RE-2027-0001"]
        self.assertEqual(first[1:3], ["Rechnung", "04.02.2027"])
        self.assertEqual(first[3], f"{self.fest.number} Stadtfest")
        self.assertEqual(first[4], '\'=HYPERLINK("http://evil.example")')  # no formula in a spreadsheet
        self.assertEqual(first[5:], ["200", "38", "238", "storniert (RE-2027-0002)"])
        every = csv_of(self.client.get(OUTGOING, {"format": "csv", "cols": "all"}))
        self.assertEqual(len(every[0]), len(OUTGOING_TABLE.columns))
        self.assertEqual(len(every), 7)  # heading and six documents – no crew disposition
        # The recipient as printed – the name of the time the document was made.
        self.assertIn("Theater am Markt", [row[every[0].index("Empfänger")] for row in every[1:]])

    def test_a_page_costs_the_same_queries_however_many_documents(self) -> None:
        def queries(**params: str) -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.client.get(OUTGOING, {"cols": "all", **params}).status_code, 200)
            return len(captured)

        # The first request of a session reads what it keeps for the next ones; the first export is logged.
        queries(), queries(format="csv")
        few, few_csv = queries(), queries(format="csv")
        fair = make_project("Messe 2", customer=self.works)
        for number in range(60):
            project = fair if number % 2 else make_project(f"Projekt {number}", customer=self.works)
            make_document(project, DocumentKind.INVOICE, f"RE-2027-1{number:03d}", net="10.00", created_by=self.paula)
        self.assertEqual(queries(), few)
        self.assertEqual(queries(format="csv"), few_csv)
        text = self.assert_ok(self.client.get(OUTGOING))
        self.assertEqual(len(numbers_of(text)), 50)  # paged like every list
        self.assertIn("66 Einträge", text)
        self.assertEqual(len(csv_of(self.client.get(OUTGOING, {"format": "csv"}))), 67)  # the CSV: every row


class OutgoingRightsTests(DocumentsSetup, UiTestCase):
    """Who sees the list: prices and every project – the CSV and the API alike (DOK-020)."""

    def test_without_prices_or_with_assigned_projects_only(self) -> None:
        storeman = self.browser_for("luka", "Lager")
        self.assertEqual(storeman.get(OUTGOING).status_code, 403)
        self.assertEqual(storeman.get(OUTGOING, {"format": "csv"}).status_code, 403)
        # Assigned to the project with the documents and with the price right – still not the list over all.
        own = role("Eigene Projekte", {"projects": 2, "customers": 2}, ["prices"], ProjectScope.ASSIGNED)
        user = make_user("ida")
        user.roles.set([own])
        ProjectMembership.objects.create(project=self.fest, user=user, level=ProjectAccessLevel.EDIT)
        browser = self.browser_of(user)
        self.assertEqual(browser.get(OUTGOING).status_code, 403)
        self.assertEqual(browser.get(OUTGOING, {"format": "csv"}).status_code, 403)

    def test_who_reads_everything_opens_every_document(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        text = self.assert_ok(reader.get(OUTGOING))
        self.assertEqual(len(numbers_of(text)), 6)
        self.assertNotIn(reverse("documents:accounting"), text)  # no settings: no way there


class MonthlyInvoiceTests(StatementSetup, UiTestCase):
    """DOK-016, DOK-020: a monthly invoice of service cases in the list – with its statement, for each case it bills."""

    def setUp(self) -> None:
        super().setUp()
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))
        self.draft = self.statement(MARCH)
        self.invoice = statements.create_invoice(self.draft, user=self.paula)

    def test_with_its_statement(self) -> None:
        text = self.assert_ok(self.client.get(OUTGOING, {"cols": "number,customer,statement,gross"}))
        self.assertIn(self.invoice.number, text)
        self.assertIn(f'<a href="{MONTHLY}{self.draft.pk}/">März 2027</a>', text)
        self.assertEqual(
            numbers_of(self.assert_ok(self.client.get(OUTGOING, {"kind": "monthly"}))), [self.invoice.number]
        )
        # The invoice belongs to the first case and bills the second: filtered by either, it is there.
        for case in (self.spot, self.mixer):
            page = self.assert_ok(self.client.get(OUTGOING, {"project": str(case.pk)}))
            self.assertEqual(numbers_of(page), [self.invoice.number])
        # Cancelled, its statement is a draft again; the invoice still says how many cases it billed.
        from rentalars.documents.services import cancel_invoice

        cancellation = cancel_invoice(self.invoice, user=self.paula)
        text = self.assert_ok(self.client.get(OUTGOING, {"cols": "number,statement", "kind": "monthly"}))
        self.assertEqual(sorted(numbers_of(text)), sorted([self.invoice.number, cancellation.number]))
        self.assertEqual(text.count("Monatsrechnung über 2 Servicefälle"), 2)

    def test_the_pdf_opens_for_who_sees_the_list(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        text = self.assert_ok(reader.get(OUTGOING))
        url = reverse("documents:file", args=[self.invoice.pk])
        self.assertIn(url, text)
        response = reader.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b"".join(response.streaming_content if response.streaming else [response.content]))


# --- API ----------------------------------------------------------------------------------------------------


class OutgoingApiTests(DocumentsSetup, ApiTestCase):
    """``GET /accounting/documents`` and ``/accounting/documents/totals`` (DOK-020; API-002)."""

    URL = f"{API}/accounting/documents"

    def test_the_list(self) -> None:
        response = self.admin.get(self.URL)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["count"], 6)
        numbers = [row["number"] for row in data["results"]]
        self.assertEqual(numbers[0], "RE-2027-0003")  # newest first
        self.assertNotIn("CD-2027-0001", numbers)
        invoice = next(row for row in data["results"] if row["number"] == "RE-2027-0001")
        self.assertEqual(
            {key: invoice[key] for key in ("kind", "net_total", "tax_total", "gross_total", "state", "lexware_state")},
            {
                "kind": "invoice",
                "net_total": "200.00",
                "tax_total": "38.00",
                "gross_total": "238.00",
                "state": "cancelled",
                "lexware_state": "done",
            },
        )
        self.assertEqual(invoice["cancelled_by_number"], "RE-2027-0002")
        self.assertEqual((invoice["customer"], invoice["customer_name"]), (self.theater.pk, "Theater am Markt"))
        self.assertEqual((invoice["recipient"], invoice["created_by_name"]), ("Theater am Markt", "Paula Plan"))
        self.assertEqual(invoice["pdf_url"], f"/api/v1/documents/{self.invoice.pk}/pdf")
        self.assertEqual(invoice["billed_projects"], [])
        delivery = next(row for row in data["results"] if row["number"] == "LS-2027-0001")
        self.assertIsNone(delivery["gross_total"])

    def test_filters_and_sort(self) -> None:
        def numbers(**params: str) -> list[str]:
            response = self.admin.get(self.URL, params)
            self.assertEqual(response.status_code, 200, response.content)
            return [row["number"] for row in response.json()["results"]]

        self.assertEqual(
            numbers(kind="invoice,cancellation", sort="number"), ["RE-2027-0001", "RE-2027-0002", "RE-2027-0003"]
        )
        self.assertEqual(numbers(kind="bookable", state="not_cancelled"), ["RE-2027-0003"])
        self.assertEqual(numbers(customer=str(self.works.pk)), ["RE-2027-0003"])
        self.assertEqual(numbers(project=str(self.fest.pk), kind="offer"), ["AN-2027-0001"])
        self.assertEqual(numbers(since="2027-03-01"), ["RE-2027-0003"])
        self.assertEqual(numbers(until="2027-02-01"), ["AN-2027-0001"])
        self.assertEqual(numbers(q="Lieferschein"), ["LS-2027-0001"])
        self.assertEqual(numbers(lexware="missing", sort="-number"), ["RE-2027-0003", "RE-2027-0002"])
        self.assertEqual(
            next(number for number in numbers(sort="gross_total") if number != "LS-2027-0001"), "RE-2027-0002"
        )
        self.assertEqual(numbers(sort="-kind")[0], "RE-2027-0002")
        self.assert_error(self.admin.get(self.URL, {"kind": "crew_sheet"}), 400, "validation_error", "kind")
        self.assert_error(self.admin.get(self.URL, {"since": "gestern"}), 400, "validation_error", "since")
        self.assert_error(self.admin.get(self.URL, {"sort": "content"}), 400, "validation_error", "sort")

    def test_totals(self) -> None:
        response = self.admin.get(f"{self.URL}/totals", {"since": "2027-02-01"})
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["count"], 6)
        kinds = {entry["kind"]: entry for entry in data["kinds"]}
        self.assertEqual(kinds["invoice"]["net_total"], "250.00")
        self.assertEqual(kinds["cancellation"]["gross_total"], "-238.00")
        self.assertIsNone(kinds["delivery_note"]["net_total"])
        self.assertEqual((data["bookable"]["net_total"], data["bookable"]["tax_total"]), ("50.00", "9.50"))
        only_offers = self.admin.get(f"{self.URL}/totals", {"kind": "offer"}).json()
        self.assertEqual((only_offers["count"], only_offers["bookable"]), (1, None))

    def test_rights(self) -> None:
        storeman = self.client_for("luka", "Lager")
        self.assertEqual(storeman.get(self.URL).status_code, 403)
        self.assertEqual(storeman.get(f"{self.URL}/totals").status_code, 403)
        own = role("Eigene Projekte", {"projects": 2, "customers": 2}, ["prices"], ProjectScope.ASSIGNED)
        user = make_user("ida")
        user.roles.set([own])
        ProjectMembership.objects.create(project=self.fest, user=user, level=ProjectAccessLevel.EDIT)
        self.assertEqual(self.client_of(user).get(self.URL).status_code, 403)
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(self.URL).json()["count"], 6)


class OutgoingServiceTests(DocumentsSetup, UiTestCase):
    """The rules behind the page and the API (DOK-020)."""

    def test_the_kinds_a_customer_gets(self) -> None:
        self.assertEqual(set(outgoing.CUSTOMER_KINDS), set(DocumentKind.values) - {DocumentKind.CREW_SHEET})
        self.assertNotIn(self.crew, outgoing.documents())

    def test_parse(self) -> None:
        from django.http import QueryDict

        filters = outgoing.parse(QueryDict("kind=invoice,cancellation&kind=invoice&customer=x&until=2027-02-30"))
        self.assertEqual(filters.kinds, ["invoice", "cancellation"])
        self.assertEqual(set(filters.errors), {"customer", "until"})
        self.assertEqual(filters.kind, "")
        self.assertEqual(outgoing.parse(QueryDict("kind=offer")).kind, "offer")
