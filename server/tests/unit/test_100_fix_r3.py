# SPDX-License-Identifier: GPL-3.0-or-later
"""Review round 3: fixes in the planning, the products and the documents (R3-1 … R3-10).

Each test names the finding it guards. They fail on the code before the fix.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from rentalars.accounts.models import Role
from rentalars.core.models import SystemSettings
from rentalars.documents.content import build_priced
from rentalars.masterdata.models import Category
from rentalars.material import partial_dates
from rentalars.material.models import ItemBlock, MaterialItem
from rentalars.products import suggestions
from rentalars.products.relation_models import ProductRelation, RelationKind
from rentalars.projects import services
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.forms import OverallDiscountForm
from rentalars.projects.models import MaterialLine, ProjectStatus
from rentalars.projects.overall_target import solve
from rentalars.projects.planning import build_planning
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_html
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_model,
    make_product,
    make_project,
    make_stock,
    ready_for_invoices,
)
from tests.ui.base import UiTestCase
from tests.unit.test_100_products_planning import items_of, make_pack, vat_project
from tests.unit.test_100_relations import Scene

D = Decimal


class PinnedItemsAfterDeletionTests(RentalarsTestCase):
    """(R3-1) Deleting the first pinned item must not leave pins nobody sees."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack()
        self.project = make_project("Anteil", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line

    def reload(self) -> MaterialLine:
        return MaterialLine.objects.get(pk=self.line.pk)

    def test_the_first_remaining_item_is_promoted(self) -> None:
        first, second, third = items_of(self.pack, 1, 2, 3)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[first, second, third])
        first.delete()
        line = self.reload()
        self.assertEqual(line.preferred_item_id, second.pk)
        self.assertEqual(line.wished_item_ids, [second.pk, third.pk])
        self.assertEqual(list(line.further_preferred_items.values_list("pk", flat=True)), [third.pk])

    def test_a_deleted_further_item_just_goes(self) -> None:
        first, second = items_of(self.pack, 1, 2)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[first, second])
        second.delete()
        self.assertEqual(self.reload().wished_item_ids, [first.pk])

    def test_the_only_item_deleted_leaves_no_wish(self) -> None:
        (only,) = items_of(self.pack, 1)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[only])
        only.delete()
        self.assertEqual(self.reload().wished_item_ids, [])

    def test_all_pinned_items_deleted_at_once_leave_no_pin_behind(self) -> None:
        pinned = items_of(self.pack, 1, 2, 3)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=pinned)
        MaterialItem.objects.filter(pk__in=[item.pk for item in pinned]).delete()
        line = self.reload()
        self.assertIsNone(line.preferred_item_id)
        self.assertEqual(line.further_preferred_items.count(), 0)

    def test_the_planning_shows_the_promoted_item_and_the_rivalry_is_real(self) -> None:
        first, second = items_of(self.pack, 1, 2)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[first, second])
        first.delete()
        other = make_project("Konkurrenz", rental_days=1)
        rival = add_line(other, self.pack, 1).line
        services.update_line(rival, rights=ALL_RIGHTS, preferred_items=[second])
        # the pin of the first project on ``second`` is visible now, so the rivalry is real and shown in both
        self.assertEqual(build_planning(self.project).all_lines[0].wish.item.pk, second.pk)
        self.assertTrue(build_planning(other).all_lines[0].wish.warnings)

    def test_further_pins_without_a_first_one_do_not_count_as_rivals(self) -> None:
        """Rows left behind by older data: a pin the planning cannot show is no rival."""
        second = items_of(self.pack, 2)[0]
        MaterialLine.objects.filter(pk=self.line.pk).update(preferred_item=None)
        self.line.further_preferred_items.set([second])
        other = make_project("Konkurrenz", rental_days=1)
        rival = add_line(other, self.pack, 1).line
        services.update_line(rival, rights=ALL_RIGHTS, preferred_items=[second])
        self.assertEqual(build_planning(other).all_lines[0].wish.warnings, [])


class OverallDiscountApiTests(ApiTestCase):
    """(R3-2, R3-9) Only real numbers get through; a dry run is refused where the real call is."""

    def url(self, project: object) -> str:
        return f"{API}/projects/{project.pk}/overall-discount"

    def test_values_that_are_no_numbers_answer_400(self) -> None:
        project = vat_project()
        for name in ("percent", "amount", "target_net", "target_gross"):
            for text in ("NaN", "-NaN", "sNaN", "Infinity", "-Infinity", "1e400", "1E+999"):
                for dry_run in (True, False):
                    response = self.admin.post(self.url(project), {name: text, "dry_run": dry_run}, format="json")
                    self.assertEqual(response.status_code, 400, (name, text, dry_run, response.content[:200]))
                    self.assertIn(name, response.json()["error"]["fields"])
        project.refresh_from_db()
        self.assertIsNone(project.overall_discount_percent)

    def test_numbers_beyond_the_columns_answer_400(self) -> None:
        project = vat_project()
        for name, text in (("amount", "1e30"), ("target_net", "99999999999"), ("percent", "100.5")):
            response = self.admin.post(self.url(project), {name: text}, format="json")
            self.assertEqual(response.status_code, 400, (name, text))

    def test_a_good_target_still_works(self) -> None:
        project = vat_project()
        response = self.admin.post(self.url(project), {"target_net": "180"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(D(response.json()["net_total"]), D("180.00"))

    def test_the_dialog_refuses_them_as_well(self) -> None:
        project = vat_project()
        for name in OverallDiscountForm.VALUE_FIELDS:
            for text in ("NaN", "Infinity", "1e400"):
                form = OverallDiscountForm({name: text}, project=project)
                self.assertFalse(form.is_valid(), (name, text))
                self.assertIn(name, form.errors)

    def test_a_dry_run_is_refused_for_a_closed_project_like_the_real_call(self) -> None:
        project = vat_project()
        project.status = "closed"
        project.save()
        for dry_run in (True, False):
            response = self.admin.post(self.url(project), {"target_net": "100", "dry_run": dry_run}, format="json")
            self.assertEqual(response.status_code, 400, dry_run)


class PrintedPercentTests(RentalarsTestCase):
    """(R3-3) Documents and CSV print the percentage as stored – not rounded to three places."""

    def project_with(self, percent: str, article: str = "L-909") -> object:
        project = make_project("P", rental_days=1, customer=ready_for_invoices())
        add_line(project, make_product(article, price="12345.67", billing_mode="flat"), 1)
        services.set_overall_discount(project, rights=ALL_RIGHTS, percent=D(percent))
        return project

    def title_of(self, project: object) -> str:
        content = build_priced(project, "offer", title="A", number="1", issued_on=datetime.date(2027, 3, 1))
        return next(section.title for section in content.sections if section.overall_discount)

    def test_the_document_prints_six_places_with_the_german_comma(self) -> None:
        with translation.override("de"):
            self.assertEqual(self.title_of(self.project_with("19.99994")), "Gesamtrabatt 19,99994 %")

    def test_round_values_keep_their_short_form(self) -> None:
        with translation.override("de"):
            self.assertEqual(self.title_of(self.project_with("10.000000")), "Gesamtrabatt 10 %")
            self.assertEqual(self.title_of(self.project_with("12.5", "L-908")), "Gesamtrabatt 12,5 %")

    def test_the_csv_and_the_pdf_overview_print_it_too(self) -> None:
        project = self.project_with("19.99994")
        with translation.override("de"):
            csv = render_price_overview_csv(project)
            html = render_price_overview_html(project)
        self.assertIn("Gesamtrabatt 19,99994 %", csv)
        self.assertIn("19,99994 %", html)

    def test_what_is_printed_gives_the_printed_discount_again(self) -> None:
        """The reason for the fix: the printed percentage and the printed amount fit each other to the cent."""
        project = make_project("Q", rental_days=1, customer=ready_for_invoices())
        add_line(project, make_product("L-910", price="12345.67", billing_mode="flat"), 1)
        result = solve(project, net=D("10000.00"))
        services.set_overall_discount(project, rights=ALL_RIGHTS, percent=result.percent)
        with translation.override("de"):
            title = self.title_of(project)
        printed = D(title.rsplit(" ", 2)[1].replace(",", "."))
        self.assertEqual((D("12345.67") * printed / 100).quantize(D("0.01"), ROUND_HALF_UP), result.discount)


class SuggestionCostTests(Scene, UiTestCase):
    """(R3-6) The panel runs after every change of the planning: its cost must stay small."""

    #: Before the fix: 107 queries for the service call and 116 for the request (10 lines, 8 of them short).
    SERVICE_LIMIT = 52
    REQUEST_LIMIT = 62

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        for number in range(10):
            product = make_stock(f"S-3{number:02d}", 4, f"Lautsprecher {number}")
            cable = make_stock(f"K-3{number:02d}", 4, f"Kabel {number}")
            suggestions.add_relation(product, cable, RelationKind.ACCESSORY)
            suggestions.add_relation(
                product, make_stock(f"R-3{number:02d}", 4, f"Ersatz {number}"), RelationKind.REPLACEMENT
            )
            add_line(self.project, product, 6)
        self.url = reverse("products:suggestions_panel", args=[self.project.pk])

    def test_ten_lines_cost_a_fixed_handful_of_queries(self) -> None:
        self.client.get(self.url)  # content types, rights and so on are cached from here on
        with CaptureQueriesContext(connection) as service:
            found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        with CaptureQueriesContext(connection) as request:
            response = self.client.get(self.url)
        self.assertEqual(len(found.accessories), 10)
        self.assertEqual(len(found.replacements), suggestions.MAX_REPLACEMENT_CHECKS)
        self.assertLessEqual(len(service), self.SERVICE_LIMIT)
        self.assertLessEqual(len(request), self.REQUEST_LIMIT)
        self.assertContains(response, 'data-suggestion-count="16"')

    def test_the_lines_are_judged_in_one_run_not_one_per_line(self) -> None:
        from rentalars.availability.engine import AvailabilityEngine

        calls = []
        original = AvailabilityEngine.line_availability
        AvailabilityEngine.line_availability = lambda self, line: calls.append(line) or original(self, line)
        try:
            suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        finally:
            AvailabilityEngine.line_availability = original
        self.assertEqual(calls, [])

    def test_the_slot_is_debounced_one_at_a_time_and_no_live_region_is_swapped(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        slot = page.split('<div id="suggestions"')[1].split("</div>")[0]
        self.assertIn('hx-trigger="load, planningChanged from:body delay:600ms"', slot)
        self.assertIn('hx-sync="this:queue last"', slot)
        self.assertNotIn("aria-live", slot)  # the swapped region is no live region ...
        self.assertIn("data-suggestion-status", page)  # ... a status line next to it is, written only on a change
        self.assertIn('aria-live="polite" data-suggestion-status', page)


class SharedAccessoryTests(Scene, UiTestCase):
    """(R3-4, R3-5) An accessory several products name; adding it twice; replacements already planned."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        # S-050 sorts before S-100: its relation comes first and is not required, the one of S-100 is.
        self.other = make_stock("S-050", 5, "Lautsprecher Gamma")
        self.other_relation = suggestions.add_relation(self.other, self.cable, RelationKind.ACCESSORY)

    def cable_suggestion(self) -> object:
        found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        return next((row for row in found.accessories if row.accessory == self.cable), None)

    def test_the_quantity_is_the_sum_over_all_products_that_name_the_accessory(self) -> None:
        add_line(self.project, self.speaker, 3)
        add_line(self.project, self.other, 2)
        suggestion = self.cable_suggestion()
        self.assertEqual(suggestion.quantity, 5)  # 3 × 1 + 2 × 1 – it was 3 (the first relation only)
        self.assertEqual(suggestion.relations, [self.other_relation, self.cable_relation])
        self.assertTrue(suggestion.is_required)  # one of them requires it
        self.assertEqual(suggestion.product_names, "Lautsprecher Gamma, Lautsprecher Alpha")

    def test_the_sum_is_rounded_up_once(self) -> None:
        suggestions.update_relation(self.other_relation, quantity_per_piece="0.5")
        suggestions.update_relation(self.cable_relation, quantity_per_piece="0.5")
        add_line(self.project, self.speaker, 1)
        add_line(self.project, self.other, 1)
        self.assertEqual(self.cable_suggestion().quantity, 1)  # 0.5 + 0.5, not 1 + 1

    def test_accepting_adds_the_sum_by_default(self) -> None:
        add_line(self.project, self.speaker, 3)
        add_line(self.project, self.other, 2)
        suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS)
        self.assertEqual(self.project.material_lines.get(product=self.cable).quantity, 5)

    def test_a_quantity_still_missing_after_adding_is_suggested_again(self) -> None:
        add_line(self.project, self.speaker, 3)
        add_line(self.project, self.other, 2)
        suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS, quantity=2)
        again = self.cable_suggestion()
        self.assertEqual((again.quantity, again.planned), (3, 2))
        suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS)  # the rest
        self.assertEqual(sum(line.quantity for line in self.project.material_lines.filter(product=self.cable)), 5)
        self.assertIsNone(self.cable_suggestion())

    def test_the_second_click_adds_nothing(self) -> None:
        add_line(self.project, self.speaker, 2)
        url = reverse("products:suggestion_accept", args=[self.project.pk, self.cable_relation.pk])
        self.htmx("post", url, {"quantity": "2"})
        second = self.htmx("post", url, {"quantity": "2"})
        self.assertEqual(self.project.material_lines.filter(product=self.cable).count(), 1)
        self.assertEqual(self.project.material_lines.get(product=self.cable).quantity, 2)
        self.assertIn("schon in der Planung", second.content.decode() + str(list(second.wsgi_request._messages)))

    def test_the_service_refuses_the_second_add_too(self) -> None:
        add_line(self.project, self.speaker, 2)
        suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS, quantity=2)
        self.assertEqual(self.project.material_lines.filter(product=self.cable).count(), 1)

    def test_an_accepted_replacement_is_not_suggested_or_added_again(self) -> None:
        add_line(self.project, self.speaker, 5)  # 3 in stock
        suggestions.accept(self.project, self.replace_relation.pk, rights=ALL_RIGHTS)
        found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        self.assertEqual(found.replacements, [])
        with self.assertRaises(ValidationError):
            suggestions.accept(self.project, self.replace_relation.pk, rights=ALL_RIGHTS)
        self.assertEqual(self.project.material_lines.filter(product=self.stand_in).count(), 1)

    def test_a_note_can_be_changed_when_the_related_product_is_deactivated(self) -> None:
        self.stand_in.is_active = False
        self.stand_in.save()
        url = reverse("products:relation_update", args=[self.speaker.pk, self.replace_relation.pk])
        self.client.post(url, {"quantity_per_piece": "2", "note": "geändert"})
        self.replace_relation.refresh_from_db()
        self.assertEqual((self.replace_relation.note, self.replace_relation.quantity_per_piece), ("geändert", 2))

    def test_a_deactivated_product_still_cannot_be_named_anew(self) -> None:
        dead = make_stock("T-900", 1, "Altes Stativ")
        dead.is_active = False
        dead.save()
        url = reverse("products:relation_add", args=[self.speaker.pk])
        self.client.post(url, {"related_product": dead.pk, "kind": "accessory", "quantity_per_piece": "1"})
        self.assertFalse(ProductRelation.objects.filter(related_product=dead).exists())


class PiecesLoweredBelowPinsTests(RentalarsTestCase):
    """(R3-8) A line cannot keep more wished items than it has pieces – not by lowering, not by copying."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack(pieces=3)
        self.project = make_project("Anteil", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=items_of(self.pack, 1, 2, 3))

    def test_lowering_below_the_pins_is_refused_and_names_the_lines(self) -> None:
        self.pack.pieces_per_product = 2
        with self.assertRaises(ValidationError) as caught:
            self.pack.full_clean()
        text = " ".join(caught.exception.message_dict["pieces_per_product"])
        self.assertIn(f"{self.project.number} (3 Exemplare, 2 Stück)", text)

    def test_the_same_when_the_project_is_finished(self) -> None:
        type(self.project).objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.pack.pieces_per_product = 2
        with self.assertRaises(ValidationError) as caught:
            self.pack.full_clean()
        self.assertIn("Exemplare", " ".join(caught.exception.message_dict["pieces_per_product"]))

    def test_lowering_to_what_the_pins_need_is_not_refused_by_them(self) -> None:
        type(self.project).objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.pack.pieces_per_product = 3
        self.pack.full_clean()

    def test_a_copy_keeps_no_more_pins_than_it_has_pieces(self) -> None:
        # Lowered behind the back of the form, as an old project can still have it.
        type(self.pack).objects.filter(pk=self.pack.pk).update(pieces_per_product=2)
        copy = duplicate_project(
            self.project, name="Kopie", start=at(10, year=2028), end=at(11, year=2028), rights=ALL_RIGHTS, user=None
        )
        copied = copy.material_lines.get(product=self.pack)
        self.assertEqual(len(copied.wished_item_ids), 2)
        self.assertEqual(copied.wished_item_ids, self.line.wished_item_ids[:2])
        copied.full_clean()  # and the line can be saved

    def test_a_copied_group_keeps_no_more_pins_than_it_has_pieces(self) -> None:
        group = add_group(self.project, "Kabel")
        grouped = add_line(self.project, self.pack, 1, group=group).line
        services.update_line(grouped, rights=ALL_RIGHTS, preferred_items=items_of(self.pack, 4, 5, 6))
        type(self.pack).objects.filter(pk=self.pack.pk).update(pieces_per_product=2)
        copy = services.copy_group(group, self.project, rights=ALL_RIGHTS)
        copied = MaterialLine.objects.get(group=copy)
        self.assertEqual(len(copied.wished_item_ids), 2)


class PinnedItemWarningsTests(RentalarsTestCase):
    """(R3-9) A wished item that is blocked in the period of the line is reported like a defective one."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack()
        self.project = make_project("Anteil", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line
        self.first, self.second = items_of(self.pack, 1, 2)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[self.first, self.second])

    def warnings(self) -> list[str]:
        return build_planning(self.project).all_lines[0].wish.warnings

    def test_a_block_in_the_period_is_a_warning(self) -> None:
        ItemBlock.objects.create(item=self.second, start=self.line.start, end=self.line.end, reason="Stecker gebrochen")
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn(f"{self.second.display_id} ist in diesem Zeitraum gesperrt: Stecker gebrochen", warnings[0])

    def test_a_block_outside_the_period_is_not(self) -> None:
        ItemBlock.objects.create(
            item=self.first,
            start=self.line.end + datetime.timedelta(days=2),
            end=self.line.end + datetime.timedelta(days=3),
            reason="später",
        )
        self.assertEqual(self.warnings(), [])


class PinnedItemListApiTests(ApiTestCase):
    """(R3-9) The list of lines asks a fixed number of questions however many lines wish for items."""

    def queries(self, lines: int) -> int:
        pack = make_pack(f"K-8{lines:02d}")
        project = make_project(f"Liste {lines}", rental_days=1)
        for number in range(lines):
            line = add_line(project, pack, 1).line
            services.update_line(
                line, rights=ALL_RIGHTS, preferred_items=items_of(pack, number * 2 + 1, number * 2 + 2)
            )
        url = f"{API}/projects/{project.pk}/material-lines"
        self.admin.get(url)
        with CaptureQueriesContext(connection) as queries:
            response = self.admin.get(url)
        self.assertEqual(response.status_code, 200)
        return len(queries)

    def test_the_number_of_queries_does_not_grow_with_the_lines(self) -> None:
        few, many = self.queries(2), self.queries(6)
        self.assertEqual(few, many)


class TwoDigitYearTests(RentalarsTestCase):
    """(R3-10) "12.05.15" is read as 2015, as the date field of the forms did before the partial dates."""

    def test_a_two_digit_year_is_read_like_strptime_does(self) -> None:
        cases = {
            "12.05.15": (datetime.date(2015, 5, 12), partial_dates.DAY),
            "1.5.15": (datetime.date(2015, 5, 1), partial_dates.DAY),
            "12/05/15": (datetime.date(2015, 5, 12), partial_dates.DAY),
            "12.05.68": (datetime.date(2068, 5, 12), partial_dates.DAY),
            "12.05.69": (datetime.date(1969, 5, 12), partial_dates.DAY),
            "12.05.99": (datetime.date(1999, 5, 12), partial_dates.DAY),
            "00.05.15": (datetime.date(2015, 5, 1), partial_dates.MONTH),
            "00.00.15": (datetime.date(2015, 1, 1), partial_dates.YEAR),
        }
        for text, (date, precision) in cases.items():
            with self.subTest(text):
                parsed = partial_dates.parse(text)
                self.assertEqual((parsed.date, parsed.precision), (date, precision))

    def test_nonsense_is_still_refused(self) -> None:
        for text in ("12.05.1", "12.05.150", "31.02.15", "12.13.15", "05.15", "15"):
            with self.subTest(text), self.assertRaises(ValueError):
                partial_dates.parse(text)

    def test_the_form_field_takes_it(self) -> None:
        self.assertEqual(partial_dates.PartialDateField().clean("12.05.15").date, datetime.date(2015, 5, 12))


class ModelSuggestRightsTests(UiTestCase):
    """(R3-10) The model search names the article number of a product only to who may read products."""

    def suggest(self, client: object) -> list[dict]:
        return client.get(reverse("material:model_suggest"), {"q": "Vergeben"}).json()

    def setUp(self) -> None:
        super().setUp()
        make_model("Vergebenes Modell", make_product("S-777", "Vergebenes Produkt"))
        Role.objects.create(name="Nur Material", module_levels={"material": 1})

    def test_a_material_reader_does_not_learn_the_article_number(self) -> None:
        rows = self.suggest(self.browser_for("kai", "Nur Material"))
        self.assertEqual([row["label"] for row in rows], ["Vergebenes Modell"])
        self.assertNotIn("S-777", str(rows))
        self.assertEqual(rows[0]["hint"], "gehört schon zu einem Produkt")

    def test_who_reads_products_sees_it(self) -> None:
        rows = self.suggest(self.client)
        self.assertEqual(rows[0]["hint"], "gehört schon zu S-777")


class StockStampTests(UiTestCase):
    """(R3-7) The stamp of the stock also moves with the buffers of the categories and the settings."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Bestand", rental_days=1)
        add_line(self.project, make_product("K-880", price="10.00"), 2)

    def stamp(self) -> str:
        key = f"stock:{self.project.pk}"
        return self.client.get(reverse("core:changes"), {"keys": key}).json()["stamps"][key]

    def test_a_buffer_of_a_category_moves_it(self) -> None:
        before = self.stamp()
        category = Category.objects.filter(parent__isnull=True).first()
        category.buffer_before_hours = D("3")
        category.save()
        self.assertNotEqual(self.stamp(), before)

    def test_the_buffers_of_the_settings_move_it(self) -> None:
        before = self.stamp()
        settings = SystemSettings.load()
        settings.buffer_after_hours = D("2")
        settings.save()
        self.assertNotEqual(self.stamp(), before)
