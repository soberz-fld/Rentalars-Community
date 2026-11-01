# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the wishes: offer options (DOK-013), sums in the project list (PRJ-085), the deployment view
printable and as mail attachment (PRJ-081). The festival is that of ``tests.unit.test_062_documents``."""

from __future__ import annotations

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.documents.models import Document, DocumentKind, DocumentTemplate
from rentalars.projects.models import Project
from tests.helpers import at, make_person, make_project, make_user, plan
from tests.mailbox import capture_smtp, configure_mailbox
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_062_documents import stadtfest


class OfferOptionsPageTests(UiTestCase):
    """DOK-013 on the tab "Documents" and in the settings of the document templates."""

    def setUp(self) -> None:
        super().setUp()
        self.project = stadtfest().project
        self.url = reverse("documents:list", args=[self.project.pk])
        self.create = reverse("documents:create", args=[self.project.pk])

    def offer_form(self, **changes: str) -> dict[str, object]:
        return form_data(self.client.get(self.url), "kind", kind="offer", **changes)

    def test_the_form_offers_the_level_of_detail_and_the_validity_in_days(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        options = page[page.index('class="offer-options"') :]
        self.assertTrue(options.startswith('class="offer-options" data-show-if="kind=offer"'))
        for text in (
            "Umfang",
            "mit Positionen",
            "nur Teilgruppen",
            'name="detail" value="lines"',
            "Gültigkeit in Tagen",
            'data-validity data-validity-from="2027-03-01"',
            'name="valid_until" value="2027-03-15"',
            'name="validity_days" value="14"',
            "data-validity-date",
            "data-validity-days",
        ):
            self.assertIn(text, options)
        data = form_data(self.client.get(self.url), "kind")
        self.assertEqual((data["detail"], data["validity_days"]), ("lines", "14"))

    def test_an_offer_with_only_groups_and_a_validity_in_days(self) -> None:
        made = self.client.post(self.create, self.offer_form(detail="groups", validity_days="30"), follow=True)
        self.assertIn("Angebot AN-2027-0001 erstellt.", self.messages_of(made))
        offer = Document.objects.get()
        self.assertEqual((offer.detail, offer.valid_until), ("groups", datetime.date(2027, 3, 31)))
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("gültig bis 31.03.2027", page)
        self.assertIn("nur Teilgruppen", page[page.index("AN-2027-0001") :])
        draft = self.client.post(reverse("documents:preview", args=[self.project.pk]), self.offer_form(detail="groups"))
        self.assertTrue(draft.content.startswith(b"%PDF"))

    def test_date_and_days_in_step_are_taken_and_differing_ones_refused(self) -> None:
        """With the script both fields arrive in step; typed in by hand they may not."""
        self.client.post(self.create, self.offer_form(valid_until="2027-03-21", validity_days="20"))
        self.assertEqual(Document.objects.get().valid_until, datetime.date(2027, 3, 21))
        refused = self.client.post(
            self.create, self.offer_form(valid_until="2027-03-21", validity_days="30"), follow=True
        )
        self.assertIn(
            "30 Tage nach dem 01.03.2027 ist der 31.03.2027, nicht der 21.03.2027. Gib eines von beiden an.",
            self.messages_of(refused),
        )
        self.assertEqual(Document.objects.count(), 1)
        too_long = self.client.post(self.create, self.offer_form(validity_days="4000"), follow=True)
        self.assertTrue(self.messages_of(too_long))
        self.assertEqual(Document.objects.count(), 1)

    def test_the_default_validity_is_set_in_the_template_of_the_offer(self) -> None:
        offer = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        change = reverse("admin:documents_documenttemplate_change", args=[offer.pk])
        page = self.assert_ok(self.client.get(change))
        self.assertIn('name="validity_days"', page)
        self.assertIn("Gültigkeit in Tagen", page)
        data = form_data(self.client.get(change), "title", validity_days="30")
        self.assertEqual(self.client.post(change, data).status_code, 302)
        offer.refresh_from_db()
        self.assertEqual(offer.validity_days, 30)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('name="validity_days" value="30"', page)
        self.assertIn('name="valid_until" value="2027-03-31"', page)
        self.client.post(self.create, self.offer_form())
        self.assertEqual(Document.objects.get().valid_until, datetime.date(2027, 3, 31))
        # The other kinds have no validity.
        invoice = DocumentTemplate.objects.get(kind=DocumentKind.INVOICE)
        other = self.assert_ok(self.client.get(reverse("admin:documents_documenttemplate_change", args=[invoice.pk])))
        self.assertNotIn('name="validity_days"', other)


class ProjectListSumsPageTests(UiTestCase):
    """PRJ-085: sums as columns of the project list – chosen, not by default; as the rights allow."""

    def setUp(self) -> None:
        super().setUp()
        self.project = stadtfest().project
        self.url = reverse("projects:list")

    def test_the_sums_are_offered_but_not_shown(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        for key in ("planned_hours", "material_revenue", "personnel_revenue", "net_total", "gross_total"):
            self.assertIn(f'name="columns" value="{key}">', page)
        for key in ("material_cost", "personnel_cost", "profit"):
            self.assertIn(f'name="columns" value="{key}">', page)
        for label in ("Geplante Mannstunden", "Material-Einnahme", "Personalkosten", "Gewinn"):
            self.assertIn(label, page)
        self.assertNotIn("1.848,00", page)

    def test_chosen_sums_show_for_each_project(self) -> None:
        columns = "number,planned_hours,material_revenue,personnel_revenue,net_total,gross_total,material_cost,"
        page = self.assert_ok(self.client.get(self.url, {"cols": columns + "personnel_cost,profit"}))
        row = page[page.index(self.project.number) :]
        for value in ("1.488,00 €", "360,00 €", "1.848,00 €", "2.199,12 €", "650,00 €", "280,00 €", "918,00 €"):
            self.assertIn(value, row)
        self.assertIn('<td class="num nowrap" data-label="Geplante Mannstunden">8</td>', row)
        # UIX-015: sortable as well – sorted in Python, as the sums are calculated, not stored.
        self.assertRegex(
            page, r'<th class="num nowrap" scope="col"><a href="\?[^"]*sort=net_total[^"]*">Summe netto</a>'
        )

    def test_the_columns_follow_the_rights_of_the_planning(self) -> None:
        Role.objects.create(name="Vertrieb", module_levels={"projects": 2}, special_rights=["prices"])
        sales = self.browser_for("vera", "Vertrieb")
        page = self.assert_ok(sales.get(self.url, {"cols": "all"}))
        self.assertIn("1.848,00 €", page)
        self.assertIn('value="planned_hours"', page)
        for key in ("material_cost", "personnel_cost", "profit"):
            self.assertNotIn(f'value="{key}"', page)
        self.assertNotIn("918,00", page)
        planner = self.browser_for("paula", "Personaldisposition")
        page = self.assert_ok(planner.get(self.url, {"cols": "all"}))
        self.assertIn('value="personnel_cost"', page)
        self.assertIn("280,00 €", page)
        for key in ("net_total", "material_revenue", "profit"):
            self.assertNotIn(f'value="{key}"', page)

    def test_crew_sees_no_sums_of_its_deployments(self) -> None:
        """AUT-023: a project known only through a crew line shows no hours, no amounts."""
        user = make_user("ben", roles=("Freie Kraft",))
        plan(self.project, "Bühne", make_person("Ben Braun", user=user), start=at(10, 8), end=at(10, 12))
        page = self.assert_ok(self.browser_of(user).get(self.url, {"cols": "number,planned_hours"}))
        self.assertIn(self.project.number, page)
        self.assertIn('<td class="num nowrap" data-label="Geplante Mannstunden"></td>', page)
        self.assertNotIn('value="net_total"', page)

    def test_the_csv_file_carries_the_chosen_sums(self) -> None:
        response = self.client.get(self.url, {"cols": "number,net_total,profit", "format": "csv"})
        lines = response.content.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "Nummer;Summe netto;Kalkulierter Gewinn")
        self.assertIn(f"{self.project.number};1848;918", lines)

    def test_a_page_of_projects_needs_a_bounded_number_of_queries(self) -> None:
        for index in range(12):
            make_project(f"Projekt {index}")

        def queries(parameters: dict[str, str]) -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assert_ok(self.client.get(self.url, parameters))
            return len(captured)

        plain, sums = queries({}), queries({"cols": "all"})
        for index in range(12, 30):
            make_project(f"Projekt {index}")
        self.assertEqual(queries({"cols": "all"}), sums)
        self.assertLess(sums - plain, 15)
        self.assertEqual(Project.objects.count(), 31)


class DeploymentOverviewPageTests(UiTestCase):
    """PRJ-081: "Print / PDF" on the tab "Deployment", and the PDF as attachment of a mail."""

    def setUp(self) -> None:
        super().setUp()
        self.project = stadtfest().project
        self.user = make_user("ben", roles=("Freie Kraft",))
        plan(self.project, "Bühne", make_person("Ben Braun", user=self.user), start=at(10, 8), end=at(10, 12))
        self.pdf = reverse("documents:deployment_pdf", args=[self.project.pk])

    def test_the_tab_has_a_button_for_the_pdf(self) -> None:
        crew = self.browser_of(self.user)
        page = self.assert_ok(crew.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertIn('class="deployment-view"', page)
        self.assertIn(f'href="{self.pdf}"', page)
        self.assertIn("Drucken / PDF", page)
        response = crew.get(self.pdf)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f"Einsatzuebersicht-{self.project.number}.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertTrue(self.client.get(self.pdf).content.startswith(b"%PDF"))

    def test_nobody_else_gets_the_pdf(self) -> None:
        other = self.browser_for("otto", "Freie Kraft")
        self.assertEqual(other.get(self.pdf).status_code, 404)

    def test_sent_along_with_a_mail_when_ticked(self) -> None:
        configure_mailbox()
        compose = f"/projects/{self.project.pk}/mails/new/"
        page = self.assert_ok(self.client.get(compose))
        self.assertIn('value="deployment"', page)
        self.assertIn("Einsatzübersicht (PDF)", page)
        data = form_data(self.client.get(compose), "subject")
        self.assertNotIn("deployment", data.get("documents", []))
        data.update(to="crew@example.de", subject="Einsatz", body="Anbei die Übersicht.", documents=["deployment"])
        with capture_smtp() as sent:
            self.client.post(compose, data, follow=True)
        (message,) = sent
        self.assertEqual(
            [part.get_filename() for part in message.iter_attachments()],
            [f"Einsatzuebersicht-{self.project.number}.pdf"],
        )
