# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for lines of the planning: PRJ-072, PRJ-075, DOK-010, PER-026."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.documents.models import Document, DocumentKind
from rentalars.masterdata.models import RentalScale
from rentalars.personnel.models import JobFunction
from rentalars.products.models import BillingMode
from rentalars.projects.models import LineVariant, MaterialLine, ProjectStatus
from rentalars.projects.services import update_line
from tests.helpers import (
    ALL_RIGHTS,
    add_group,
    add_line,
    job_function,
    make_product,
    make_project,
    make_stock,
    plan,
    ready_for_invoices,
)
from tests.ui.base import UiTestCase, form_data

D = Decimal


def flat(article_number: str, price: str) -> object:
    """A product billed as a flat price, so that amounts are quantity × price."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT)


class VariantAndDuplicatePageTests(UiTestCase):
    """PRJ-075 in the planning: the choice in the dialog, the badge, the copy."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.line = add_line(self.project, flat("L-010", "100.00"), 2, group=self.group).line
        self.detail = reverse("projects:detail", args=[self.project.pk])

    def test_the_dialog_makes_a_line_optional(self) -> None:
        url = reverse("projects:line_edit", args=[self.project.pk, self.line.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn('name="variant"', dialog)
        self.assertIn("Zählt als", dialog)
        response = self.htmx("post", url, form_data(self.htmx("get", url), variant="optional"))
        self.assertEqual(response.status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual(self.line.variant, LineVariant.OPTIONAL)
        page = self.assert_ok(self.client.get(self.detail))
        row = page[page.index(f'data-line="{self.line.pk}"') :]
        row = row[: row.index("</tr>")]
        self.assertIn('data-variant="optional"', row)
        self.assertIn("nicht in der Summe", row)
        self.assertIn("Optionale Positionen, nicht enthalten", page)

    def test_alternative_lines_have_their_own_total(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, variant=LineVariant.ALTERNATIVE)
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("Alternative Positionen, nicht enthalten", page)
        overview = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn("Alternative Positionen, nicht enthalten", overview)
        self.assertIn("nicht in der Summe", overview)

    def test_duplicating_a_line_puts_the_copy_below_it(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        duplicate_url = reverse("projects:line_duplicate", args=[self.project.pk, self.line.pk])
        self.assertIn(f'hx-post="{duplicate_url}"', page)
        self.assertIn("Position duplizieren", page)

        response = self.htmx("post", duplicate_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Reswap"], "none")  # a patch of the touched group
        copy = MaterialLine.objects.exclude(pk=self.line.pk).get()
        text = response.content.decode()
        self.assertLess(text.index(f'data-line="{self.line.pk}"'), text.index(f'data-line="{copy.pk}"'))
        self.assertEqual((copy.group_id, copy.quantity, copy.unit_price), (self.group.pk, D("2"), D("100.00")))

    def test_duplicating_needs_write_access(self) -> None:
        reader = self.browser_for("nora", "Nur-Lesen")
        response = reader.post(reverse("projects:line_duplicate", args=[self.project.pk, self.line.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MaterialLine.objects.count(), 1)


class ScaleHintPageTests(UiTestCase):
    """PRJ-072: switching to the current scale used to leave the hints in place of the planning."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        add_line(self.project, make_stock("L-010", 6, price="20.00"), 4)
        RentalScale.objects.get(is_default=True).publish(
            [(1, Decimal("1")), (2, Decimal("2"))], extra_day_increment=Decimal("1")
        )
        self.detail = reverse("projects:detail", args=[self.project.pk])

    def test_forms_among_the_hints_do_not_inherit_the_selection_of_the_hints(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        start = page.index('<div id="planning-notes"')
        tag = page[start : page.index("\n", start)]
        self.assertIn('hx-select="#planning-notes > *"', tag)
        self.assertIn('hx-disinherit="hx-select hx-target hx-swap"', tag)

    def test_switching_the_scale_answers_with_the_whole_planning(self) -> None:
        response = self.htmx("post", reverse("projects:refresh_scales", args=[self.project.pk]))
        text = self.assert_ok(response)
        self.assertEqual(
            (response["HX-Retarget"], response["HX-Reswap"], response["HX-Reselect"]),
            ("#planning", "outerHTML", "#planning"),
        )
        self.assertTrue(text.lstrip().startswith('<div id="planning"'))
        self.assertIn('id="group-none"', text)
        self.assertIn('id="planning-totals"', text)
        self.assertNotIn("alte Staffel", text)
        self.assertIn("160,00", text)


class MaximumDiscountPageTests(UiTestCase):
    """PER-026: the maximum discount in the job function and where it bites."""

    def test_job_function_form_and_list(self) -> None:
        url = reverse("personnel:job_function_create")
        page = self.assert_ok(self.client.get(url))
        self.assertIn('name="max_discount_percent"', page)
        self.client.post(
            url,
            form_data(self.client.get(url), "max_discount_percent", name="Bühnenmeisterei", max_discount_percent="5"),
        )
        self.assertEqual(JobFunction.objects.get(name="Bühnenmeisterei").max_discount_percent, D("5"))
        listing = self.assert_ok(self.client.get(reverse("personnel:job_function_list")))
        self.assertIn("Höchstrabatt", listing)
        self.assertIn("5 %", listing)

    def test_without_the_price_right_the_maximum_is_not_shown(self) -> None:
        Role.objects.create(name="Personal ohne Preise", module_levels={"personnel": 3})
        planner = self.browser_for("pia", "Personal ohne Preise")
        page = self.assert_ok(planner.get(reverse("personnel:job_function_create")))
        self.assertNotIn("max_discount_percent", page)
        self.assertNotIn("Höchstrabatt", self.assert_ok(planner.get(reverse("personnel:job_function_list"))))

    def test_crew_dialog_takes_a_discount_and_the_planning_shows_the_limit(self) -> None:
        stagehand = job_function("Stagehand", price="30.00")
        stagehand.max_discount_percent = D("5")
        stagehand.save()
        project = make_project()
        line = plan(project, stagehand, planned_hours=D("10"))
        url = reverse("projects:crew_edit", args=[project.pk, line.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn('name="discount_percent"', dialog)
        self.assertIn("Die Funktion erlaubt höchstens 5 %.", dialog)
        self.htmx("post", url, form_data(self.htmx("get", url), discount_percent="10"))
        line.refresh_from_db()
        self.assertEqual(line.discount_percent, D("10"))
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        crew = page[page.index('id="planning-crew"') :]
        self.assertIn("− 5 %", crew)
        self.assertIn("höchstens 5 % (Funktion)", crew)
        self.assertIn("285,00", crew)
        overview = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[project.pk])))
        self.assertIn("höchstens 5 % (Funktion)", overview)
        self.assertIn("285,00", overview)


class OfferPageTests(UiTestCase):
    """DOK-010 on the tab "Documents"."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=ready_for_invoices(), status=ProjectStatus.INQUIRY)
        add_line(self.project, flat("L-010", "100.00"), 2)
        self.url = reverse("documents:list", args=[self.project.pk])

    def test_offer_comes_first_with_its_validity(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        select = page[page.index('name="kind"') :]
        self.assertTrue(select[select.index("<option") :].startswith('<option value="offer"'))
        self.assertIn('data-show-if="kind=offer"', page)
        self.assertIn('name="valid_until"', page)

    def test_making_an_offer(self) -> None:
        data = form_data(self.client.get(self.url), "kind", kind="offer", valid_until="2027-03-20")
        draft = self.client.post(reverse("documents:preview", args=[self.project.pk]), data)
        self.assertTrue(draft.content.startswith(b"%PDF"))
        made = self.client.post(reverse("documents:create", args=[self.project.pk]), data, follow=True)
        self.assertIn("Angebot AN-2027-0001 erstellt.", self.messages_of(made))
        offer = Document.objects.get()
        self.assertEqual((offer.kind, offer.valid_until), (DocumentKind.OFFER, datetime.date(2027, 3, 20)))
        self.assertFalse(offer.xml_file)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("gültig bis 20.03.2027", page)
        # A second offer is welcome.
        self.client.post(reverse("documents:create", args=[self.project.pk]), data)
        self.assertEqual(Document.objects.filter(kind=DocumentKind.OFFER).count(), 2)

    def test_offers_need_the_price_right(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.browser_for("paul", "Planung ohne Preise")
        page = self.assert_ok(planner.get(self.url))
        self.assertIn('value="delivery_note"', page)
        self.assertNotIn('value="offer"', page)
        planner.post(reverse("documents:create", args=[self.project.pk]), {"kind": "offer"})
        self.assertFalse(Document.objects.exists())
