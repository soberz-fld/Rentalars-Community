# SPDX-License-Identifier: GPL-3.0-or-later
"""Accessories and replacements, and the suggestions made from them (PRD-023, VFG-015).

The requirement: suggestions for replacements and accessories. A product names accessories (with the
pieces per piece, required or recommended, a note) and replacements; the planning of a project suggests the
accessories not planned yet and, for a short line, the replacements that are free in its period – a hint, never a
block, dismissible per project, the numbers from the availability engine. Browser and API do the same.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.rights import SpecialRight
from rentalars.products import services as product_services
from rentalars.products import suggestions
from rentalars.products.models import ProductKind
from rentalars.products.relation_models import DismissedSuggestion, ProductRelation, RelationKind
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_customer,
    make_product,
    make_project,
    make_stock,
)
from tests.ui.base import UiTestCase

WITHOUT_AVAILABILITY = dataclasses.replace(
    ALL_RIGHTS, special_rights=frozenset(ALL_RIGHTS.special_rights) - {SpecialRight.AVAILABILITY}
)


class Scene:
    """Speakers (3 in stock) with a required cable (1 per speaker) and a stand (1 per 2 speakers), a stand-in speaker."""

    def prepare(self) -> None:
        self.speaker = make_stock("S-100", 3, "Lautsprecher Alpha")
        self.cable = make_stock("K-100", 20, "Speakon-Kabel")
        self.stand = make_stock("T-100", 10, "Lautsprecherstativ")
        self.stand_in = make_stock("S-101", 8, "Lautsprecher Beta")
        self.cable_relation = suggestions.add_relation(
            self.speaker, self.cable, RelationKind.ACCESSORY, is_required=True, note="Speakon"
        )
        self.stand_relation = suggestions.add_relation(
            self.speaker, self.stand, RelationKind.ACCESSORY, quantity_per_piece="0.5"
        )
        self.replace_relation = suggestions.add_relation(self.speaker, self.stand_in, RelationKind.REPLACEMENT)
        self.project = make_project("Stadtfest")


class RelationRulesTests(Scene, RentalarsTestCase):
    """What may be named as accessory or replacement."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_order_and_flags(self) -> None:
        grouped = suggestions.relations_of(self.speaker)
        self.assertEqual([row.related_product for row in grouped[RelationKind.ACCESSORY]], [self.cable, self.stand])
        self.assertTrue(self.cable_relation.is_required)
        self.assertEqual(self.stand_relation.quantity_per_piece, Decimal("0.50"))
        suggestions.move_relation(self.stand_relation, "up")
        grouped = suggestions.relations_of(self.speaker)
        self.assertEqual([row.related_product for row in grouped[RelationKind.ACCESSORY]], [self.stand, self.cable])
        suggestions.move_relation(self.stand_relation, "up")  # already first: nothing changes
        self.assertEqual(suggestions.relations_of(self.speaker)[RelationKind.ACCESSORY][0].related_product, self.stand)
        changed = suggestions.update_relation(
            self.stand_relation, note="Höhe 2 m", is_required=True, quantity_per_piece="1,5"
        )
        self.assertEqual(
            (changed.note, changed.is_required, changed.quantity_per_piece), ("Höhe 2 m", True, Decimal("1.5"))
        )

    def test_refused(self) -> None:
        with self.assertRaises(ValidationError):
            suggestions.add_relation(self.speaker, self.speaker, RelationKind.ACCESSORY)
        with self.assertRaises(ValidationError) as caught:
            suggestions.add_relation(self.speaker, self.cable, RelationKind.ACCESSORY)  # twice
        self.assertIn("schon eingetragen", str(caught.exception))
        service = make_product("D-100", "Technikerstunde", kind=ProductKind.SERVICE)
        with self.assertRaises(ValidationError):
            suggestions.add_relation(self.speaker, service, RelationKind.ACCESSORY)
        with self.assertRaises(ValidationError):
            suggestions.add_relation(self.speaker, self.cable, "other")
        with self.assertRaises(ValidationError):
            suggestions.add_relation(self.speaker, self.stand, RelationKind.ACCESSORY, quantity_per_piece="0")
        customer = make_customer()
        theirs = make_product("C-900", "Kundenlautsprecher", owner=customer, price=None)
        with self.assertRaises(ValidationError):
            suggestions.add_relation(self.speaker, theirs, RelationKind.ACCESSORY)
        kit = make_product("S-200", "Beschallungsset", kind=ProductKind.KIT)
        product_services.set_kit_components(kit, [(self.speaker, 2)])
        with self.assertRaises(ValidationError) as caught:
            suggestions.add_relation(kit, self.stand_in, RelationKind.REPLACEMENT)
        self.assertIn("Set", str(caught.exception))
        suggestions.add_relation(kit, self.cable, RelationKind.ACCESSORY)  # a kit may have accessories

    def test_a_replacement_is_never_required_and_can_go_both_ways(self) -> None:
        extra = make_stock("S-102", 2, "Lautsprecher Gamma")
        relation = suggestions.add_relation(
            self.speaker, extra, RelationKind.REPLACEMENT, is_required=True, quantity_per_piece="2", both_ways=True
        )
        self.assertFalse(relation.is_required)
        back = ProductRelation.objects.get(product=extra, related_product=self.speaker)
        self.assertEqual((back.kind, back.quantity_per_piece), (RelationKind.REPLACEMENT, Decimal("0.50")))

    def test_removing_it(self) -> None:
        suggestions.delete_relation(self.cable_relation)
        self.assertEqual(len(suggestions.relations_of(self.speaker)[RelationKind.ACCESSORY]), 1)
        self.assertEqual([row.product for row in suggestions.used_as_relation(self.stand)], [self.speaker])


class SuggestionTests(Scene, RentalarsTestCase):
    """What the planning suggests."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_nothing_without_a_product_that_has_accessories(self) -> None:
        self.assertTrue(suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).is_empty)
        add_line(self.project, self.cable, 2)
        self.assertTrue(suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).is_empty)

    def test_accessories_with_a_sensible_quantity(self) -> None:
        add_line(self.project, self.speaker, 2)
        found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        self.assertEqual(
            [(row.accessory, row.quantity, row.is_required) for row in found.accessories],
            [(self.cable, 2, True), (self.stand, 1, False)],
        )
        self.assertEqual([row.free for row in found.accessories], [20, 10])
        self.assertEqual(found.replacements, [])  # two speakers are in stock: nothing is short
        # Rounded up: 3 speakers need 1.5 stands.
        add_line(self.project, self.speaker, 1)
        found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        self.assertEqual([row.quantity for row in found.accessories], [3, 2])

    def test_what_is_planned_is_not_suggested_again_not_even_inside_a_kit(self) -> None:
        add_line(self.project, self.speaker, 2)
        add_line(self.project, self.cable, 2)
        kit = make_product("S-201", "Stativpaket", kind=ProductKind.KIT)
        product_services.set_kit_components(kit, [(self.stand, 2)])
        add_line(self.project, kit, 1)
        self.assertTrue(suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).is_empty)

    def test_dismiss_and_bring_back(self) -> None:
        add_line(self.project, self.speaker, 2)
        self.assertEqual(suggestions.dismiss(self.project, [self.cable_relation.pk]), 1)
        self.assertEqual(suggestions.dismiss(self.project, [self.cable_relation.pk]), 0)  # twice: nothing new
        found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        self.assertEqual([row.accessory for row in found.accessories], [self.stand])
        self.assertEqual(found.dismissed, [self.cable_relation])
        # Other projects are not affected.
        other = make_project("Messe", start=at(20), end=at(22))
        add_line(other, self.speaker, 1)
        self.assertEqual(len(suggestions.suggestions_for_project(other, rights=ALL_RIGHTS).accessories), 2)
        self.assertEqual(suggestions.restore(self.project), 1)
        self.assertEqual(len(suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).accessories), 2)
        self.assertFalse(DismissedSuggestion.objects.exists())

    def test_accepting_adds_a_line_in_the_group_of_the_product(self) -> None:
        group = add_group(self.project, "Beschallung")
        add_line(self.project, self.speaker, 2, group=group)
        result = suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS)
        self.assertEqual((result.line.product, result.line.quantity, result.line.group), (self.cable, 2, group))
        self.assertEqual(
            [row.accessory for row in suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).accessories],
            [self.stand],
        )
        # A quantity of one's own.
        result = suggestions.accept(self.project, self.stand_relation.pk, rights=ALL_RIGHTS, quantity=4)
        self.assertEqual(result.line.quantity, 4)
        with self.assertRaises(ValidationError):
            suggestions.accept(self.project, self.stand_relation.pk, rights=ALL_RIGHTS, quantity=0)

    def test_accepting_something_that_does_not_belong_here(self) -> None:
        with self.assertRaises(ValidationError):
            suggestions.accept(self.project, self.cable_relation.pk, rights=ALL_RIGHTS)  # no speaker is planned
        with self.assertRaises(ValidationError):
            suggestions.accept(self.project, 999999, rights=ALL_RIGHTS)

    def test_a_short_line_gets_the_replacement_with_the_free_pieces(self) -> None:
        add_line(self.project, self.speaker, 5)  # 3 in stock: 2 are missing
        found = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS)
        self.assertEqual(len(found.replacements), 1)
        replacement = found.replacements[0]
        self.assertEqual(
            (replacement.replacement, replacement.reason, replacement.missing, replacement.quantity, replacement.free),
            (self.stand_in, "short", 2, 2, 8),
        )
        self.assertTrue(replacement.covers)

    def test_the_numbers_are_those_of_the_planning(self) -> None:
        """Another project holds 7 of the 8 stand-ins in the same period: one is left, the shortage is not covered."""
        other = make_project("Messe", start=at(10), end=at(12))
        add_line(other, self.stand_in, 7)
        add_line(self.project, self.speaker, 5)
        replacement = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).replacements[0]
        self.assertEqual((replacement.free, replacement.covers), (1, False))
        # (R3-5) A replacement that is planned already is not suggested again (it was, with 0 free).
        add_line(self.project, self.stand_in, 1)
        self.assertEqual(suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).replacements, [])

    def test_the_replacement_follows_the_ratio(self) -> None:
        suggestions.update_relation(self.replace_relation, quantity_per_piece="2")
        add_line(self.project, self.speaker, 5)
        replacement = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).replacements[0]
        self.assertEqual(replacement.quantity, 4)

    def test_a_deactivated_product_gets_its_replacement(self) -> None:
        add_line(self.project, self.speaker, 1)
        self.speaker.is_active = False
        self.speaker.save()
        replacement = suggestions.suggestions_for_project(self.project, rights=ALL_RIGHTS).replacements[0]
        self.assertEqual((replacement.reason, replacement.quantity), ("inactive", 1))

    def test_availability_only_for_who_may_see_it(self) -> None:
        add_line(self.project, self.speaker, 5)
        found = suggestions.suggestions_for_project(self.project, rights=WITHOUT_AVAILABILITY)
        self.assertEqual(found.replacements, [])  # they would tell that the line is short
        self.assertEqual([row.free for row in found.accessories], [None, None])
        self.assertEqual(len(found.accessories), 2)

    def test_accepting_a_replacement_leaves_the_short_line_alone(self) -> None:
        add_line(self.project, self.speaker, 5)
        result = suggestions.accept(self.project, self.replace_relation.pk, rights=ALL_RIGHTS)
        self.assertEqual((result.line.product, result.line.quantity), (self.stand_in, 2))
        self.assertEqual(self.project.material_lines.get(product=self.speaker).quantity, 5)


class RelationPageTests(Scene, UiTestCase):
    """The panel on the product page and the suggestions in the planning."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_the_panel_on_the_product_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[self.speaker.pk])))
        self.assertIn("Zubehör und Ersatz", page)
        self.assertIn("Speakon-Kabel", page)
        self.assertIn("Lautsprecher Beta", page)
        self.assertIn(reverse("products:relation_add", args=[self.speaker.pk]), page)
        # The product that is named: where it is used.
        stand_page = self.assert_ok(self.client.get(reverse("products:detail", args=[self.stand.pk])))
        self.assertIn("S-100", stand_page)
        # The page of the material model only shows.
        model = self.speaker.material_models.first() if hasattr(self.speaker, "material_models") else None
        if model is not None:
            model_page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
            self.assertIn("Speakon-Kabel", model_page)
            self.assertNotIn(reverse("products:relation_add", args=[self.speaker.pk]), model_page)

    def test_add_change_move_and_remove(self) -> None:
        extra = make_stock("T-101", 4, "Stativtasche")
        response = self.client.post(
            reverse("products:relation_add", args=[self.speaker.pk]),
            {"related_product": extra.pk, "kind": "accessory", "quantity_per_piece": "1", "note": "Transport"},
            follow=True,
        )
        self.assertIn("Gespeichert", " ".join(self.messages_of(response)))
        relation = ProductRelation.objects.get(product=self.speaker, related_product=extra)
        self.assertEqual((relation.note, relation.position), ("Transport", 2))
        self.client.post(
            reverse("products:relation_update", args=[self.speaker.pk, relation.pk]),
            {"quantity_per_piece": "3", "note": "Tasche", "is_required": "1"},
        )
        relation.refresh_from_db()
        self.assertEqual(
            (relation.quantity_per_piece, relation.note, relation.is_required), (Decimal("3.00"), "Tasche", True)
        )
        self.client.post(reverse("products:relation_move", args=[self.speaker.pk, relation.pk, "up"]))
        relation.refresh_from_db()
        self.assertEqual(relation.position, 1)
        response = self.client.post(
            reverse("products:relation_move", args=[self.speaker.pk, relation.pk, "sideways"]), follow=True
        )
        self.assertIn("Unbekannte Richtung", " ".join(self.messages_of(response)))
        self.client.post(reverse("products:relation_delete", args=[self.speaker.pk, relation.pk]))
        self.assertFalse(ProductRelation.objects.filter(pk=relation.pk).exists())

    def test_mistakes_are_named(self) -> None:
        response = self.client.post(
            reverse("products:relation_add", args=[self.speaker.pk]),
            {"related_product": self.speaker.pk, "kind": "accessory", "quantity_per_piece": "1"},
            follow=True,
        )
        self.assertIn("nicht sein eigenes Zubehör", " ".join(self.messages_of(response)))
        response = self.client.post(
            reverse("products:relation_add", args=[self.speaker.pk]), {"kind": "accessory"}, follow=True
        )
        self.assertIn("Wähle ein Produkt", " ".join(self.messages_of(response)))
        relation = self.cable_relation
        response = self.client.post(
            reverse("products:relation_update", args=[self.speaker.pk, relation.pk]),
            {"quantity_per_piece": "x"},
            follow=True,
        )
        self.assertIn("Stückzahl über 0", " ".join(self.messages_of(response)))
        # A relation of another product is not found under this one.
        self.assertEqual(
            self.client.post(reverse("products:relation_delete", args=[self.stand.pk, relation.pk])).status_code, 404
        )

    def test_only_who_may_write_products(self) -> None:
        reader = self.browser_for("lesend", "Nur-Lesen")
        self.assertEqual(
            reader.post(
                reverse("products:relation_add", args=[self.speaker.pk]),
                {"related_product": self.stand_in.pk, "kind": "accessory", "quantity_per_piece": "1"},
            ).status_code,
            403,
        )
        page = self.assert_ok(reader.get(reverse("products:detail", args=[self.speaker.pk])))
        self.assertIn("Speakon-Kabel", page)
        self.assertNotIn(reverse("products:relation_add", args=[self.speaker.pk]), page)

    def test_the_slot_in_the_planning_only_exists_with_relations(self) -> None:
        url = reverse("projects:detail", args=[self.project.pk])
        self.assertIn(
            reverse("products:suggestions_panel", args=[self.project.pk]), self.assert_ok(self.client.get(url))
        )
        ProductRelation.objects.all().delete()
        self.assertNotIn(
            reverse("products:suggestions_panel", args=[self.project.pk]), self.assert_ok(self.client.get(url))
        )

    def test_the_panel_accept_dismiss_and_restore(self) -> None:
        add_line(self.project, self.speaker, 5)
        panel_url = reverse("products:suggestions_panel", args=[self.project.pk])
        panel = self.assert_ok(self.client.get(panel_url))
        self.assertIn("Speakon-Kabel", panel)
        self.assertIn("Lautsprecher Beta", panel)  # the replacement for the two missing speakers
        self.assertIn("8 frei", panel)
        accept_url = reverse("products:suggestion_accept", args=[self.project.pk, self.cable_relation.pk])
        self.assertIn(accept_url, panel)
        # Accept: the planning answers and the cable is a line now.
        response = self.htmx("post", accept_url, {"quantity": "5"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.project.material_lines.get(product=self.cable).quantity, 5)
        self.assertNotIn(accept_url, self.assert_ok(self.client.get(panel_url)))
        # Dismiss all: the panel is empty, but says how to bring them back.
        dismiss_url = reverse("products:suggestion_dismiss", args=[self.project.pk])
        response = self.htmx("post", dismiss_url, {"relation": [self.stand_relation.pk, self.replace_relation.pk]})
        panel = response.content.decode()
        self.assertNotIn("Lautsprecherstativ", panel)
        self.assertIn("2 Vorschläge sind in diesem Projekt verworfen", panel)
        restored = self.htmx("post", reverse("products:suggestion_restore", args=[self.project.pk]))
        self.assertIn("Lautsprecherstativ", restored.content.decode())

    def test_a_quantity_that_is_no_number(self) -> None:
        add_line(self.project, self.speaker, 2)
        response = self.htmx(
            "post",
            reverse("products:suggestion_accept", args=[self.project.pk, self.cable_relation.pk]),
            {"quantity": "viele"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.project.material_lines.filter(product=self.cable).exists())

    def test_the_offer_step_only_shows_a_hint(self) -> None:
        add_line(self.project, self.speaker, 2)
        documents = self.assert_ok(self.client.get(reverse("documents:list", args=[self.project.pk])))
        self.assertIn(reverse("products:suggestions_panel", args=[self.project.pk]) + "?offer=1", documents)
        panel = self.assert_ok(
            self.client.get(reverse("products:suggestions_panel", args=[self.project.pk]), {"offer": "1"})
        )
        self.assertIn("Speakon-Kabel", panel)
        self.assertNotIn("<form", panel)
        self.assertNotIn("hx-post", panel)

    def test_a_reader_sees_the_panel_without_buttons(self) -> None:
        add_line(self.project, self.speaker, 2)
        reader = self.browser_for("lesend", "Nur-Lesen")
        panel = reader.get(reverse("products:suggestions_panel", args=[self.project.pk]))
        if panel.status_code == 200:
            self.assertNotIn("hx-post", panel.content.decode())
        self.assertEqual(
            reader.post(
                reverse("products:suggestion_accept", args=[self.project.pk, self.cable_relation.pk])
            ).status_code,
            403,
        )
        self.assertEqual(reader.post(reverse("products:suggestion_dismiss", args=[self.project.pk])).status_code, 403)
        self.assertEqual(reader.post(reverse("products:suggestion_restore", args=[self.project.pk])).status_code, 403)
        self.assertFalse(self.project.material_lines.filter(product=self.cable).exists())


class RelationApiTests(Scene, ApiTestCase):
    """Every operation through the API, with the rights of products and projects."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_manage_the_relations(self) -> None:
        url = f"{API}/products/{self.speaker.pk}/relations"
        listed = self.admin.get(url).json()
        self.assertEqual([row["article_number"] for row in listed["accessories"]], ["K-100", "T-100"])
        self.assertEqual([row["article_number"] for row in listed["replacements"]], ["S-101"])
        extra = make_stock("T-101", 4, "Stativtasche")
        created = self.admin.post(
            url,
            {"related_product": extra.pk, "kind": "accessory", "quantity_per_piece": "2", "note": "Tasche"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        new = created.json()["accessories"][-1]
        self.assertEqual((new["article_number"], new["note"], new["quantity_per_piece"]), ("T-101", "Tasche", "2.00"))
        one = f"{url}/{new['id']}"
        changed = self.admin.patch(one, {"is_required": True, "note": "muss mit"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["accessories"][-1]["is_required"], True)
        moved = self.admin.post(f"{one}/move", {"direction": "up"}, format="json")
        self.assertEqual(moved.json()["accessories"][1]["article_number"], "T-101")
        removed = self.admin.post(f"{one}/remove", {}, format="json")
        self.assertEqual(removed.status_code, 200, removed.content)
        self.assertEqual(len(removed.json()["accessories"]), 2)

    def test_errors_and_rights(self) -> None:
        url = f"{API}/products/{self.speaker.pk}/relations"
        self.assert_error(self.admin.post(url, {"kind": "accessory"}, format="json"), 400, "validation_error")
        self.assert_error(
            self.admin.post(url, {"related_product": self.speaker.pk, "kind": "accessory"}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(
            self.admin.post(url, {"related_product": self.stand.pk, "kind": "accessory"}, format="json"),
            400,
            "validation_error",
        )  # twice
        self.assert_error(
            self.admin.post(
                url,
                {"related_product": self.stand_in.pk, "kind": "accessory", "quantity_per_piece": "x"},
                format="json",
            ),
            400,
            "validation_error",
        )
        one = f"{url}/{self.cable_relation.pk}"
        self.assert_error(self.admin.post(f"{one}/move", {"direction": "left"}, format="json"), 400, "validation_error")
        self.assert_error(self.admin.patch(one, {"quantity_per_piece": "x"}, format="json"), 400, "validation_error")
        self.assertEqual(
            self.admin.patch(
                f"{API}/products/{self.stand.pk}/relations/{self.cable_relation.pk}", {}, format="json"
            ).status_code,
            404,
        )
        reader = self.client_for("lesend", "Nur-Lesen")
        self.assertEqual(reader.get(url).status_code, 200)
        self.assertEqual(
            reader.post(url, {"related_product": self.stand_in.pk, "kind": "accessory"}, format="json").status_code, 403
        )
        self.assertEqual(reader.patch(one, {"note": "x"}, format="json").status_code, 403)
        self.assertEqual(reader.post(f"{one}/move", {"direction": "up"}, format="json").status_code, 403)
        self.assertEqual(reader.post(f"{one}/remove", {}, format="json").status_code, 403)
        self.assertEqual(self.client_for("niemand").get(url).status_code, 403)

    def test_the_suggestions_of_a_project(self) -> None:
        add_line(self.project, self.speaker, 5)
        url = f"{API}/projects/{self.project.pk}/suggestions"
        body = self.admin.get(url).json()
        self.assertEqual(
            [(row["article_number"], row["quantity"], row["free"]) for row in body["accessories"]],
            [("K-100", 5, 20), ("T-100", 3, 10)],
        )
        self.assertEqual(
            [
                (row["article_number"], row["reason"], row["missing"], row["free"], row["covers"])
                for row in body["replacements"]
            ],
            [("S-101", "short", 2, 8, True)],
        )
        added = self.admin.post(f"{url}/{self.cable_relation.pk}/add", {"quantity": 6}, format="json")
        self.assertEqual(added.status_code, 201, added.content)
        self.assertEqual((added.json()["title"], added.json()["quantity"]), ("Speakon-Kabel", "6"))
        dismissed = self.admin.post(f"{url}/dismiss", {"relations": [self.stand_relation.pk]}, format="json")
        self.assertEqual(dismissed.json(), {"dismissed": 1})
        body = self.admin.get(url).json()
        self.assertEqual(body["accessories"], [])
        self.assertEqual(body["dismissed"], [self.stand_relation.pk])
        self.assertEqual(self.admin.get(url, {"dismissed": "1"}).json()["dismissed"], [self.stand_relation.pk])
        restored = self.admin.post(f"{url}/restore", {}, format="json")
        self.assertEqual(restored.json(), {"restored": 1})
        self.assertEqual(len(self.admin.get(url).json()["accessories"]), 1)

    def test_errors_and_rights_of_the_suggestions(self) -> None:
        add_line(self.project, self.speaker, 2)
        url = f"{API}/projects/{self.project.pk}/suggestions"
        self.assert_error(
            self.admin.post(f"{url}/{self.cable_relation.pk}/add", {"quantity": "x"}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(
            self.admin.post(f"{url}/{self.cable_relation.pk}/add", {"quantity": 0}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(
            self.admin.post(f"{url}/dismiss", {"relations": "all"}, format="json"), 400, "validation_error"
        )
        reader = self.client_for("lesend", "Nur-Lesen")
        self.assertEqual(reader.get(url).status_code, 200)
        self.assertEqual(reader.post(f"{url}/{self.cable_relation.pk}/add", {}, format="json").status_code, 403)
        self.assertEqual(reader.post(f"{url}/dismiss", {"relations": [1]}, format="json").status_code, 403)
        self.assertEqual(reader.post(f"{url}/restore", {}, format="json").status_code, 403)
        self.assertEqual(self.client_for("niemand").get(url).status_code, 403)
        self.assertEqual(self.admin.get(f"{API}/projects/999999/suggestions").status_code, 404)
