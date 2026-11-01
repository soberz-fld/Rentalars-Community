# SPDX-License-Identifier: GPL-3.0-or-later
"""The material lines of the planning – a warning at a too high discount, the product link, text lines.

The requirements:

1. A discount above the maximum rate of the planning line gives a warning (before, the maximum was simply entered).
   (PER-026) – the stored discount stays as typed, the price takes
   the maximum, and the planning now says so: line dialog, bulk, groups, personnel, vehicle bookings, API.
2. In the planning of a project the product number is a link to the product, and the box "Verfügbarkeit" there shows
   the period of the project the user came from. (PRJ-010, PRD-041)
3. In the planning of a project, in the same row as "Position ohne Produkt" and "MVR-Datei importieren", a button
   "Textposition einfügen" adds a line without value or product that holds only a text.
   (PRJ-017, PRJ-075, PRJ-082, DOK-003, DOK-013)
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.documents import content as builder
from rentalars.documents import services as documents
from rentalars.documents.models import DocumentKind
from rentalars.documents.pdf import render_html
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.packing.services import get_packlist, lines_of
from rentalars.products.models import BillingMode, ProductKind
from rentalars.projects import services
from rentalars.projects.discounts import capped_lines_warning, group_discount_warning, maximum_of_material_line
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.lines import BulkAction, change_lines, duplicate_line
from rentalars.projects.models import CrewLine, LineVariant, MaterialLine, ProjectStatus
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_html
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.project_templates import apply_template, save_as_template
from rentalars.projects.split import split_into_subprojects
from tests.api.base import API, ApiTestCase
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
    make_stock,
    plan,
    ready_for_invoices,
)
from tests.ui.base import UiTestCase, form_data

D = Decimal

#: The words of the warning at a line, in German (PER-026).
LINE_WARNING = "Der Rabatt von 30 % liegt über dem Höchstsatz dieser Position (20 %); angerechnet werden 20 %."


def limited(article_number: str = "L-010", price: str = "100.00", maximum: str | None = "20") -> object:
    """A product billed as a flat price, whose discount may be at most ``maximum`` percent (PER-026)."""
    return make_product(
        article_number,
        price=price,
        billing_mode=BillingMode.FLAT,
        max_discount_percent=D(maximum) if maximum is not None else None,
    )


# --- 1. The warning at a discount above the maximum -------------------------------------------------


class DiscountWarningServiceTests(RentalarsTestCase):
    """The services answer with ``warnings``; the stored discount stays as typed, the price takes the maximum."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.spot = limited()

    def test_adding_a_line_with_a_too_high_discount_warns(self) -> None:
        result = add_line(self.project, self.spot, 1, discount_percent=D("30"))
        self.assertEqual(result.warnings, [LINE_WARNING])
        self.assertEqual(result.line.discount_percent, D("30"))
        self.assertEqual(compute_project_prices(self.project).net_total, D("80.00"))

    def test_changing_a_line_warns_only_for_a_discount_above_the_maximum(self) -> None:
        line = add_line(self.project, self.spot, 1).line
        for typed in ("20", "5", "0"):
            self.assertEqual(services.update_line(line, rights=ALL_RIGHTS, discount_percent=D(typed)).warnings, [])
        warned = services.update_line(line, rights=ALL_RIGHTS, discount_percent=D("30"))
        self.assertEqual(warned.warnings, [LINE_WARNING])
        # Another change does not repeat the warning about the discount that stands.
        self.assertEqual(services.update_line(line, rights=ALL_RIGHTS, quantity=D("2")).warnings, [])

    def test_a_product_without_maximum_never_warns(self) -> None:
        free = limited("L-020", maximum=None)
        self.assertEqual(add_line(self.project, free, 1, discount_percent=D("90")).warnings, [])

    def test_a_duplicate_and_the_customers_discount_say_nothing(self) -> None:
        line = add_line(self.project, self.spot, 1, discount_percent=D("30")).line
        copy = duplicate_line(line, rights=ALL_RIGHTS)
        self.assertEqual(copy.warnings, [])

    def test_the_stricter_maximum_of_a_service_counts(self) -> None:
        sound = job_function("Tontechnik", price="40.00")
        sound.max_discount_percent = D("15")
        sound.save()
        product = sound.service_product
        product.max_discount_percent = D("25")
        product.save()
        from tests.helpers import add_line_before_071

        line = add_line_before_071(self.project, product, 1).line
        self.assertEqual(product.kind, ProductKind.SERVICE)
        self.assertEqual(maximum_of_material_line(line), D("15"))

    def test_several_lines_in_one_text(self) -> None:
        self.assertEqual(capped_lines_warning(D("30"), []), "")
        one = capped_lines_warning(D("30"), [("Spot", D("20"))])
        self.assertIn("Höchstsatz einer Position: Spot (20 %)", one)
        two = capped_lines_warning(D("30"), [("Spot", D("20")), ("Wash", D("10"))])
        self.assertIn("bei 2 Positionen über dem Höchstsatz: Spot (20 %); Wash (10 %)", two)

    def test_the_overall_discount_has_no_maximum(self) -> None:
        add_line(self.project, self.spot, 1)
        services.set_overall_discount(self.project, rights=ALL_RIGHTS, percent=D("50"))
        self.assertEqual(compute_project_prices(self.project).net_total, D("50.00"))


class DiscountWarningPageTests(UiTestCase):
    """The planning says it: line dialog, live hint, several lines, groups, personnel, vehicles."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.line = add_line(self.project, limited(), 1, group=self.group).line
        self.edit = reverse("projects:line_edit", args=[self.project.pk, self.line.pk])

    def test_the_line_dialog_warns_and_keeps_what_was_typed(self) -> None:
        dialog = self.htmx("get", self.edit)
        self.assertIn("Die Position erlaubt höchstens 20 %.", self.assert_ok(dialog))
        response = self.htmx("post", self.edit, form_data(dialog, discount_percent="30"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(LINE_WARNING, response.content.decode())
        self.line.refresh_from_db()
        self.assertEqual(self.line.discount_percent, D("30"))
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertNotIn(LINE_WARNING, page)  # a message is shown once

    def test_no_warning_up_to_the_maximum(self) -> None:
        dialog = self.htmx("get", self.edit)
        response = self.htmx("post", self.edit, form_data(dialog, discount_percent="20"))
        self.assertNotIn("liegt über dem Höchstsatz", response.content.decode())

    def test_without_page_script_the_message_waits_on_the_page(self) -> None:
        dialog = self.htmx("get", self.edit)
        response = self.client.post(self.edit, form_data(dialog, discount_percent="30"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(LINE_WARNING, self.messages_of(response))

    def test_the_dialog_hints_while_typing(self) -> None:
        availability = reverse("projects:line_availability", args=[self.project.pk])
        dialog = self.assert_ok(self.htmx("get", self.edit))
        self.assertIn('id="discount-hint"', dialog)
        hint = self.htmx("get", availability, {"line": self.line.pk, "discount_percent": "30"}).content.decode()
        self.assertIn('id="discount-hint"', hint)
        self.assertIn(LINE_WARNING, hint)
        hint = self.htmx("get", availability, {"line": self.line.pk, "discount_percent": "10,5"}).content.decode()
        self.assertNotIn("liegt über dem Höchstsatz", hint)
        for nonsense in ("abc", ""):
            hint = self.htmx("get", availability, {"line": self.line.pk, "discount_percent": nonsense})
            self.assertNotIn("liegt über dem Höchstsatz", hint.content.decode())
        # Without the price right there is no discount field and no hint.
        Role.objects.create(name="Planer ohne Preise", module_levels={"projects": 3, "products": 2})
        planner = self.browser_for("paul", "Planer ohne Preise")
        hint = self.htmx("get", availability, {"line": self.line.pk, "discount_percent": "30"}, client=planner)
        self.assertNotIn("liegt über dem Höchstsatz", hint.content.decode())
        self.assertNotIn("discount-hint", hint.content.decode())

    def test_several_lines_at_once_name_the_capped_ones(self) -> None:
        wash = add_line(self.project, limited("L-020", maximum="10"), 1).line
        free = add_line(self.project, limited("L-030", maximum=None), 1).line
        bulk = reverse("projects:lines_bulk", args=[self.project.pk])
        response = self.htmx(
            "post",
            bulk,
            {"lines": [self.line.pk, wash.pk, free.pk], "action": "discount", "discount_percent": "30"},
        )
        text = response.content.decode()
        self.assertIn("bei 2 Positionen über dem Höchstsatz", text)
        self.assertIn("(20 %)", text)
        self.assertIn("(10 %)", text)
        wash.refresh_from_db()
        self.assertEqual(wash.discount_percent, D("30"))
        response = self.htmx("post", bulk, {"lines": [free.pk], "action": "discount", "discount_percent": "30"})
        self.assertNotIn("liegt über dem Höchstsatz", response.content.decode())

    def test_a_group_discount_and_a_group_price_warn(self) -> None:
        url = reverse("projects:group_edit", args=[self.project.pk, self.group.pk])
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, discount_percent="30"))
        text = response.content.decode()
        self.assertIn("Der Rabatt von 30 % für die Gruppe „Licht“ liegt bei einigen ihrer Positionen", text)
        self.assertIn("angerechnet werden insgesamt 20 %", text)
        # A flat price below what the maximum allows.
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, discount_percent="", flat_price="50,00"))
        self.assertIn("Der Pauschalpreis von 50,00 € für die Gruppe „Licht“ liegt unter dem", response.content.decode())
        # Changing the name only says nothing.
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, name="Licht vorn"))
        self.assertNotIn("Pauschalpreis von", response.content.decode())
        # A discount in euros.
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, flat_price="", discount_amount="40,00"))
        self.assertIn("Der Rabatt von 40,00 € für die Gruppe „Licht vorn“", response.content.decode())

    def test_a_group_within_the_maximum_says_nothing(self) -> None:
        url = reverse("projects:group_edit", args=[self.project.pk, self.group.pk])
        response = self.htmx("post", url, form_data(self.htmx("get", url), discount_percent="10"))
        self.assertNotIn("liegt bei einigen", response.content.decode())
        self.assertEqual(group_discount_warning(self.group), "")

    def test_a_person_with_a_discount_above_the_maximum_of_the_function(self) -> None:
        sound = job_function("Tontechnik", price="40.00")
        sound.max_discount_percent = D("10")
        sound.save()
        line = plan(self.project, sound, make_person("Anna Becker", rates={"Tontechnik": "35.00"}))
        url = reverse("projects:crew_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, "start", discount_percent="25"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Der Rabatt von 25 % liegt über dem Höchstsatz der Funktion „Tontechnik“ (10 %); angerechnet werden 10 %.",
            response.content.decode(),
        )
        line.refresh_from_db()
        self.assertEqual(line.discount_percent, D("25"))
        response = self.htmx("post", url, form_data(dialog, "start", discount_percent="10"))
        self.assertNotIn("liegt über dem Höchstsatz", response.content.decode())

    def test_several_people_at_once(self) -> None:
        sound = job_function("Tontechnik", price="40.00")
        sound.max_discount_percent = D("10")
        sound.save()
        anna, tom = make_person("Anna Becker"), make_person("Tom Richter")
        lines = [plan(self.project, sound, person) for person in (anna, tom)]
        bulk = reverse("projects:crew_bulk_edit", args=[self.project.pk])
        dialog = self.htmx("get", bulk, {"crew_lines": [line.pk for line in lines]})
        data = form_data(dialog, "discount_percent", discount_percent="25")
        data["crew_lines"] = [line.pk for line in lines]
        response = self.htmx("post", bulk, data)
        self.assertEqual(response.status_code, 200, response.content.decode()[:600])
        self.assertIn("bei 2 Positionen über dem Höchstsatz", response.content.decode())
        self.assertEqual(set(CrewLine.objects.values_list("discount_percent", flat=True)), {D("25")})

    def test_a_vehicle_booking(self) -> None:
        from rentalars.projects import logistics
        from tests.unit.test_090_logistics import make_fleet

        fleet = make_fleet()
        fleet["car"].max_discount_percent = D("5")
        fleet["car"].save()
        booking = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=fleet["car"], item=fleet["van"])
        url = reverse("projects:vehicle_edit", args=[self.project.pk, booking.pk])
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, discount_percent="10"))
        self.assertIn(
            "Der Rabatt von 10 % liegt über dem Höchstsatz dieser Buchung (5 %); angerechnet werden 5 %.",
            response.content.decode(),
        )
        response = self.htmx("post", url, form_data(dialog, discount_percent="5"))
        self.assertNotIn("liegt über dem Höchstsatz", response.content.decode())


class DiscountWarningApiTests(ApiTestCase):
    """The API answers 2xx with a list ``warnings`` (PER-026, API-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.line = add_line(self.project, limited(), 1, group=self.group).line
        self.base = f"{API}/projects/{self.project.pk}"

    def test_a_line_post_and_patch(self) -> None:
        created = self.admin.post(
            f"{self.base}/material-lines",
            {"product": limited("L-040").pk, "quantity": "1", "discount_percent": "30"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["warnings"], [LINE_WARNING])
        self.assertEqual(created.json()["discount_percent"], "30.00")
        url = f"{self.base}/material-lines/{self.line.pk}"
        patched = self.admin.patch(url, {"discount_percent": "30"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.json()["warnings"], [LINE_WARNING])
        self.assertEqual(patched.json()["price"]["amount"], "80.00")
        fine = self.admin.patch(url, {"discount_percent": "10"}, format="json")
        self.assertEqual(fine.json()["warnings"], [])
        self.assertEqual(self.admin.get(url).json()["warnings"], [])
        self.assertTrue(all(row["warnings"] == [] for row in self.admin.get(f"{self.base}/material-lines").json()))

    def test_bulk(self) -> None:
        response = self.admin.post(
            f"{self.base}/material-lines/bulk",
            {"lines": [self.line.pk], "action": "discount", "discount_percent": "30"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        (warning,) = response.json()["warnings"]
        self.assertIn("Höchstsatz einer Position", warning)
        quiet = self.admin.post(
            f"{self.base}/material-lines/bulk", {"lines": [self.line.pk], "action": "optional"}, format="json"
        )
        self.assertEqual(quiet.json()["warnings"], [])

    def test_groups(self) -> None:
        url = f"{self.base}/groups/{self.group.pk}"
        patched = self.admin.patch(url, {"discount_percent": "30"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        (warning,) = patched.json()["warnings"]
        self.assertIn("für die Gruppe „Licht“", warning)
        self.assertEqual(self.admin.patch(url, {"name": "Licht 2"}, format="json").json()["warnings"], [])
        created = self.admin.post(f"{self.base}/groups", {"name": "Neu", "flat_price": "10.00"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["warnings"], [])
        self.assertEqual(self.admin.get(url).json()["warnings"], [])

    def test_people(self) -> None:
        sound = job_function("Tontechnik", price="40.00")
        sound.max_discount_percent = D("10")
        sound.save()
        person = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        crew = f"{self.base}/crew-lines"
        created = self.admin.post(
            crew, {"job_function": sound.pk, "person": person.pk, "discount_percent": "25"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        (line,) = created.json()
        self.assertIn("Höchstsatz der Funktion „Tontechnik“", line["warnings"][0])
        patched = self.admin.patch(f"{crew}/{line['id']}", {"discount_percent": "30"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertIn("angerechnet werden 10 %", patched.json()["warnings"][0])
        self.assertEqual(
            self.admin.patch(f"{crew}/{line['id']}", {"discount_percent": "5"}, format="json").json()["warnings"], []
        )
        bulk = self.admin.post(
            f"{crew}/bulk",
            {"lines": [line["id"]], "action": "edit", "values": {"discount_percent": "25"}},
            format="json",
        )
        self.assertEqual(bulk.status_code, 200, bulk.content)
        self.assertIn("Höchstsatz einer Position", bulk.json()["warnings"][0])
        quiet = self.admin.post(crew + "/bulk", {"lines": [line["id"]], "action": "firm"}, format="json")
        self.assertEqual(quiet.json()["warnings"], [])

    def test_vehicle_bookings(self) -> None:
        from tests.unit.test_090_logistics import make_fleet

        fleet = make_fleet()
        fleet["car"].max_discount_percent = D("5")
        fleet["car"].save()
        created = self.admin.post(
            f"{self.base}/logistics", {"item": fleet["van"].pk, "discount_percent": "10"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertIn("Höchstsatz dieser Buchung (5 %)", created.json()["warnings"][0])
        url = f"{self.base}/logistics/{created.json()['id']}"
        patched = self.admin.patch(url, {"discount_percent": "20"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertIn("angerechnet werden 5 %", patched.json()["warnings"][0])
        self.assertEqual(self.admin.patch(url, {"discount_percent": "5"}, format="json").json()["warnings"], [])


# --- 2. The product number in the planning leads to the product -------------------------------------


class ProductLinkTests(UiTestCase):
    """PRJ-010, PRD-041: the product number is a link; the product page shows the period of the project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.product = make_stock("L-010", 5, "Spot")
        self.line = add_line(self.project, self.product, 2).line
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.product_page = reverse("products:detail", args=[self.product.pk])

    def row_of(self, page: str) -> str:
        row = page[page.index(f'data-line="{self.line.pk}"') :]
        return row[: row.index("</tr>")]

    def test_the_number_links_to_the_product_with_the_project(self) -> None:
        row = self.row_of(self.assert_ok(self.client.get(self.detail)))
        self.assertIn(f'<a class="artno" href="{self.product_page}?project={self.project.pk}"', row)
        self.assertIn("Produkt öffnen: Verfügbarkeit für den Zeitraum dieses Projekts", row)

    def test_without_the_right_to_read_products_the_number_is_plain_text(self) -> None:
        Role.objects.create(name="Nur Projekte", module_levels={"projects": 3})
        row = self.row_of(self.assert_ok(self.browser_for("paul", "Nur Projekte").get(self.detail)))
        self.assertIn('<span class="artno">L-010</span>', row)
        self.assertNotIn(self.product_page, row)

    def test_more_lines_cost_no_more_queries(self) -> None:
        """The link is filled into one address looked up once – not looked up per row (NFA-014)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assert_ok(self.client.get(self.detail))
            return len(captured)

        self.client.get(self.detail)  # warm caches that live longer than a request
        few = queries()
        for number in range(2, 12):
            add_line(self.project, make_stock(f"L-1{number:02d}", 3), 1)
        many = queries()
        self.assertLessEqual(many, few + 3)

    def test_the_line_dialog_links_the_number_too(self) -> None:
        url = reverse("projects:line_edit", args=[self.project.pk, self.line.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn(f'<a class="artno" href="{self.product_page}?project={self.project.pk}">L-010</a>', dialog)
        Role.objects.create(name="Nur Projekte", module_levels={"projects": 3})
        plain = self.assert_ok(self.htmx("get", url, client=self.browser_for("paul", "Nur Projekte")))
        self.assertIn('<span class="artno">L-010</span>', plain)
        self.assertNotIn(self.product_page, plain)

    def test_the_product_page_shows_the_period_of_the_project(self) -> None:
        page = self.assert_ok(self.client.get(self.product_page, {"project": self.project.pk}))
        self.assertIn(f"Zeitraum des Projekts {self.project.number}", page)
        self.assertIn(reverse("projects:detail", args=[self.project.pk]), page)
        self.assertIn(f"Zurück zu {self.project.number} Stadtfest", page)
        self.assertIn("10.03.2027 00:00", page)
        self.assertIn("12.03.2027 00:00", page)
        self.assertIn(f'name="project" value="{self.project.pk}"', page)
        # The period is computed right away: the box shows a verdict, not an empty form.
        plain = self.assert_ok(self.client.get(self.product_page))
        self.assertNotIn("Zeitraum des Projekts", plain)
        self.assertNotIn('name="project"', plain)

    def test_a_period_typed_by_hand_wins(self) -> None:
        page = self.assert_ok(
            self.client.get(
                self.product_page,
                {"project": self.project.pk, "start": "2027-04-01T08:00", "end": "2027-04-02T08:00"},
            )
        )
        self.assertIn("01.04.2027 08:00", page)
        self.assertNotIn("10.03.2027 00:00", page)

    def test_wrong_values_are_ignored(self) -> None:
        for value in ("abc", "-1", "0", "9" * 40, "99999999", "1;2", ""):
            page = self.assert_ok(self.client.get(self.product_page, {"project": value}))
            self.assertNotIn("Zeitraum des Projekts", page, value)

    def test_a_digit_that_is_not_a_number_is_ignored(self) -> None:
        """ "²".isdigit() is true but int("²") fails: it must not end in a 500."""
        for value in ("²", "①", "٣"):
            page = self.assert_ok(self.client.get(self.product_page, {"project": value}))
            self.assertNotIn("Zeitraum des Projekts", page, value)
        self.assert_ok(self.client.get(reverse("products:list"), {"category": "²", "owner": "²"}))
        self.assert_ok(self.client.get(reverse("products:create"), {"category": "²", "owner": "²"}))

    def test_a_project_the_user_may_not_read_is_ignored(self) -> None:
        # Projects of her own only (AUT-017); this one is not assigned to her.
        Role.objects.create(
            name="Produktleser zugeordnet",
            module_levels={"projects": 1, "products": 1},
            special_rights=["availability"],
            project_scope="assigned",
        )
        reader = self.browser_for("rita", "Produktleser zugeordnet")
        page = self.assert_ok(reader.get(self.product_page, {"project": self.project.pk}))
        self.assertNotIn("Zeitraum des Projekts", page)
        self.assertNotIn(self.project.name, page)

    def test_a_user_without_the_availability_right_does_not_crash(self) -> None:
        Role.objects.create(name="Produktleser", module_levels={"projects": 2, "products": 1})
        reader = self.browser_for("paul", "Produktleser")
        page = self.assert_ok(reader.get(self.product_page, {"project": self.project.pk}))
        self.assertNotIn("Verfügbarkeit", page)  # no right, no box – and so no period either
        self.assertNotIn("Zeitraum des Projekts", page)

    def test_the_period_of_a_changed_project(self) -> None:
        project = make_project("Frühjahr", start=at(20, 8), end=at(22, 18))
        page = self.assert_ok(self.client.get(self.product_page, {"project": project.pk}))
        self.assertIn("20.03.2027 08:00", page)
        self.assertIn("22.03.2027 18:00", page)


# --- 3. The text line --------------------------------------------------------------------------------


def text_lines_of(project) -> list[MaterialLine]:
    """The text lines of a project in the order of the planning."""
    return list(project.material_lines.filter(is_text=True).order_by("position", "id"))


class TextLineCase(RentalarsTestCase):
    """A project with a group, two lines and a text line between them."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.group = add_group(self.project, "Licht")
        self.first = add_line(self.project, limited(maximum=None), 2, group=self.group).line
        self.text = services.add_text_line(self.project, title="Aufbau ab 14 Uhr", note="Zufahrt über Tor 2").line
        self.second = add_line(self.project, limited("L-020", "50.00", maximum=None), 1).line


class TextLineServiceTests(TextLineCase):
    """The service and the model rules (PRJ-017)."""

    def test_a_text_line_has_nothing_but_text(self) -> None:
        line = self.text
        self.assertTrue(line.is_text)
        self.assertEqual((line.kind, str(line), line.is_free_line), ("text", "Aufbau ab 14 Uhr", False))
        self.assertEqual((line.product, line.quantity, line.unit_price, line.discount_percent), (None, 0, 0, 0))
        self.assertEqual((line.title, line.note), ("Aufbau ab 14 Uhr", "Zufahrt über Tor 2"))
        self.assertEqual(line.variant, LineVariant.NORMAL)
        self.assertEqual(line.start, self.project.start)

    def test_a_text_line_can_be_put_into_a_group(self) -> None:
        line = services.add_text_line(self.project, title="Vorn", group=self.group).line
        self.assertEqual(line.group, self.group)
        self.assertGreater(line.position, self.first.position)

    def test_the_rules(self) -> None:
        with self.assertRaises(ValidationError):
            services.add_text_line(self.project, title="  ")
        broken = [
            ({"product": self.first.product}, "product"),
            ({"quantity": D("1")}, "quantity"),
            ({"unit_price": D("5")}, "quantity"),
            ({"discount_percent": D("5")}, "quantity"),
            ({"variant": LineVariant.OPTIONAL}, "variant"),
            ({"is_sale": True}, "is_text"),
            ({"supplier": None, "covers_line": self.first}, "is_text"),
        ]
        for values, key in broken:
            line = MaterialLine.objects.get(pk=self.text.pk)
            for name, value in values.items():
                setattr(line, name, value)
            with self.assertRaises(ValidationError, msg=str(values)) as caught:
                line.full_clean()
            self.assertIn(key, caught.exception.message_dict, str(values))

    def test_a_closed_project_takes_no_text(self) -> None:
        done = make_project("Fertig", status=ProjectStatus.CLOSED)
        with self.assertRaises(ValidationError):
            services.add_text_line(done, title="Zu spät")

    def test_labels(self) -> None:
        from rentalars.projects.lines import line_label

        self.assertEqual(line_label(self.text), "Aufbau ab 14 Uhr")

    def test_sums_and_taxes_do_not_see_it(self) -> None:
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.net_total, D("250.00"))
        self.assertEqual(prices.by_line_id[self.text.pk].amount, D("0.00"))
        self.assertTrue(prices.by_line_id[self.text.pk].is_text)
        self.assertEqual(sum(share.net for share in prices.tax_lines), D("250.00"))
        self.assertEqual(prices.by_group_id[self.group.pk].subtotal, D("200.00"))

    def test_a_group_with_a_text_line_keeps_its_discount(self) -> None:
        services.add_text_line(self.project, title="Hinweis", group=self.group)
        services.update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_group_id[self.group.pk].subtotal, D("180.00"))
        services.update_group(self.group, rights=ALL_RIGHTS, discount_percent=None, flat_price=D("150.00"))
        self.assertEqual(compute_project_prices(self.project).by_group_id[self.group.pk].subtotal, D("150.00"))

    def test_availability_and_the_packlist_do_not_see_it(self) -> None:
        self.assertEqual({line.pk for line in lines_of(get_packlist(self.project))}, {self.first.pk, self.second.pk})
        result = services.add_text_line(self.project, title="Noch ein Hinweis")
        self.assertEqual(result.availability.status, "unchecked")
        from rentalars.availability.services import open_shortages

        # The two lines are short (their products have no stock); the text lines are not part of it.
        self.assertEqual({found.line.pk for found in open_shortages()}, {self.first.pk, self.second.pk})

    def test_the_text_line_is_copied_as_a_text_line(self) -> None:
        copy = duplicate_line(self.text, rights=ALL_RIGHTS).line
        self.assertTrue(copy.is_text)
        self.assertEqual(
            (copy.title, copy.note, copy.position), (self.text.title, self.text.note, self.text.position + 1)
        )
        self.assertEqual(MaterialLine.objects.filter(is_text=True).count(), 2)

    def test_bulk_actions(self) -> None:
        result = change_lines(self.project, [self.text.pk, self.first.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual(result.changed_ids, [self.first.pk])
        (skipped,) = result.skipped
        self.assertEqual((skipped.line.pk, skipped.reason), (self.text.pk, "ist eine Textposition ohne Preis"))
        result = change_lines(
            self.project, [self.text.pk], BulkAction.DISCOUNT, rights=ALL_RIGHTS, discount_percent=D("5")
        )
        self.assertEqual(result.changed_ids, [])
        self.assertEqual(MaterialLine.objects.get(pk=self.text.pk).discount_percent, 0)
        moved = change_lines(self.project, [self.text.pk], BulkAction.MOVE, rights=ALL_RIGHTS, group=self.group)
        self.assertEqual(moved.changed_ids, [self.text.pk])
        self.assertEqual(MaterialLine.objects.get(pk=self.text.pk).group, self.group)
        deleted = change_lines(self.project, [self.text.pk], BulkAction.DELETE, rights=ALL_RIGHTS)
        self.assertEqual(deleted.changed_ids, [self.text.pk])
        self.assertFalse(MaterialLine.objects.filter(pk=self.text.pk).exists())

    def test_an_alternative_is_never_a_text_line(self) -> None:
        from rentalars.projects.lines import alternative_choices

        groups = alternative_choices(self.project, excluded=set())
        offered = [line_id for _path, lines in groups for line_id, _label in lines]
        self.assertIn(self.first.pk, offered)
        self.assertNotIn(self.text.pk, offered)

    def test_nothing_is_an_alternative_to_a_text_line(self) -> None:
        """(text lines; PRJ-128): the line would count for nothing – refused wherever it is asked."""
        with self.assertRaises(ValidationError):
            services.update_line(
                self.first, rights=ALL_RIGHTS, variant=LineVariant.ALTERNATIVE, alternative_to=self.text
            )
        line = MaterialLine.objects.get(pk=self.second.pk)
        line.variant, line.alternative_to = LineVariant.ALTERNATIVE, self.text
        with self.assertRaises(ValidationError) as caught:
            line.full_clean()
        self.assertIn("alternative_to", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            change_lines(
                self.project, [self.second.pk], BulkAction.ALTERNATIVE, rights=ALL_RIGHTS, alternative_to=self.text
            )
        self.assertIn("alternative_to", caught.exception.message_dict)
        self.second.refresh_from_db()
        self.assertEqual((self.second.variant, self.second.alternative_to_id), (LineVariant.NORMAL, None))
        self.assertEqual(compute_project_prices(self.project).net_total, D("250.00"))

    def test_a_text_line_is_no_position_in_the_figures_of_a_part(self) -> None:
        """(text lines; PRJ-128): "Positionen" of the family overview counts material."""
        from rentalars.projects.family import figures_of
        from rentalars.projects.planning import build_planning

        self.assertEqual(figures_of(build_planning(self.project), is_whole=False).lines, 2)

    def test_moving_the_period_does_not_count_the_text_line(self) -> None:
        from rentalars.schedule import moves

        move = moves.MoveRequest(project=self.project, what=moves.PERIOD, start=at(11, 8), end=at(13, 18))
        outcome = moves.perform_move(move, rights=ALL_RIGHTS)
        self.assertEqual(outcome.material_lines, 2)  # the two lines of material, not the text line
        self.text.refresh_from_db()
        self.assertEqual(self.text.start, at(11, 8))

    def test_a_surcharge_refers_to_no_text_line(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        surcharge = add_line(self.project, night).line
        with self.assertRaises(ValidationError):
            services.set_surcharge_targets(surcharge, [{"type": "line", "id": self.text.pk}])
        services.set_surcharge_targets(surcharge, [{"type": "line", "id": self.first.pk}])

    def test_sorting(self) -> None:
        services.arrange_lines(self.project, [(self.group.pk, [self.first.pk]), (None, [self.text.pk, self.second.pk])])
        self.text.refresh_from_db()
        self.second.refresh_from_db()
        self.assertLess(self.text.position, self.second.position)
        services.arrange_lines(self.project, [(self.group.pk, [self.first.pk]), (None, [self.second.pk, self.text.pk])])
        self.text.refresh_from_db()
        self.second.refresh_from_db()
        self.assertLess(self.second.position, self.text.position)

    def test_the_change_log_has_the_text_line(self) -> None:
        from rentalars.core.models import AuditLogEntry

        entries = AuditLogEntry.objects.filter(
            object_id=str(self.text.pk), content_type__model="materialline", action="created"
        )
        self.assertEqual(entries.count(), 1)
        self.assertTrue(entries.get().changes["is_text"])

    def test_changing_the_flag_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            services.update_line(self.first, rights=ALL_RIGHTS, is_text=True)


class TextLineDocumentTests(TextLineCase):
    """The text line is printed on offers, order confirmations and invoices – and counts for nothing there."""

    def test_offer_confirmation_and_invoice_have_it(self) -> None:
        ready_for_invoices(self.project.customer)
        for kind in (DocumentKind.OFFER, DocumentKind.ORDER_CONFIRMATION, DocumentKind.INVOICE):
            document = documents.create_document(self.project, kind)
            content = builder.from_json(document.content)
            texts = [p for section in content.sections for p in section.positions if p.is_text]
            self.assertEqual(len(texts), 1, kind)
            (position,) = texts
            self.assertEqual(
                (position.number, position.title, position.details, position.counts, position.amount),
                ("", "Aufbau ab 14 Uhr", "Zufahrt über Tor 2", False, D("0")),
                kind,
            )
            self.assertEqual(document.net_total, D("250.00"), kind)
            self.assertEqual(len(content.positions), 2, kind)  # what counts: the two lines
            numbers = [p.number for section in content.sections for p in section.positions]
            self.assertEqual(sorted(n for n in numbers if n), ["1", "2"], kind)  # the text takes no number

    def test_the_pdf_prints_the_text(self) -> None:
        pdf = documents.preview(self.project, DocumentKind.OFFER)
        self.assertTrue(pdf.startswith(b"%PDF"))
        content = documents.build_content(
            self.project, DocumentKind.OFFER, number="AN-1", issued_on=datetime.date(2027, 3, 2)
        )
        html = render_html(content, documents.template_for(DocumentKind.OFFER))
        self.assertIn("Aufbau ab 14 Uhr", html)
        self.assertIn("Zufahrt über Tor 2", html)
        self.assertIn('class="text-row"', html)

    def test_the_xrechnung_has_no_line_for_it(self) -> None:
        ready_for_invoices(self.project.customer)
        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        root = ET.fromstring(invoice.xml_file.read())
        cac = "{" + NAMESPACES["cac"] + "}"
        self.assertEqual(len(root.findall(f"{cac}InvoiceLine")), 2)
        self.assertNotIn("Aufbau ab 14 Uhr", ET.tostring(root, encoding="unicode"))

    def test_a_cancellation_keeps_it(self) -> None:
        ready_for_invoices(self.project.customer)
        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        cancellation = builder.negated(
            builder.from_json(invoice.content), title="Storno", number="ST-1", issued_on=datetime.date(2027, 3, 2)
        )
        texts = [p for section in cancellation.sections for p in section.positions if p.is_text]
        self.assertEqual([(p.title, p.amount) for p in texts], [("Aufbau ab 14 Uhr", D("0"))])

    def test_the_group_only_view_keeps_the_text(self) -> None:
        content = builder.build_priced(
            self.project, DocumentKind.OFFER, title="Angebot", number="AN-1", issued_on=datetime.date(2027, 3, 2)
        )
        shortened = builder.only_groups(content)
        titles = [p.title for section in shortened.sections for p in section.positions]
        self.assertIn("Aufbau ab 14 Uhr", titles)

    def test_the_delivery_note_does_not_list_it(self) -> None:
        content = builder.build_delivery_note(
            self.project, title="Lieferschein", number="LS-1", issued_on=datetime.date(2027, 3, 2)
        )
        self.assertNotIn("Aufbau ab 14 Uhr", str(content.as_json()))


class TextLinePriceOverviewTests(TextLineCase):
    """The price overview shows it as a row of text: page, CSV, PDF."""

    def test_page_csv_and_pdf(self) -> None:
        html = render_price_overview_html(self.project, with_lines=True, rights=ALL_RIGHTS, user=None)
        self.assertIn("Aufbau ab 14 Uhr", html)
        self.assertIn("Zufahrt über Tor 2", html)
        csv = render_price_overview_csv(self.project, rights=ALL_RIGHTS, user=None)
        self.assertIn("Aufbau ab 14 Uhr", csv)
        row = next(line for line in csv.splitlines() if "Aufbau ab 14 Uhr" in line)
        self.assertNotIn("0,00", row)


class TextLinePageTests(UiTestCase):
    """The button, the dialog, the row of the planning."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.group = add_group(self.project, "Licht")
        self.first = add_line(self.project, limited(maximum=None), 2, group=self.group).line
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.add = reverse("projects:text_line_add", args=[self.project.pk])

    def test_the_button_stands_beside_the_line_without_product(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("Textposition einfügen", page)
        self.assertIn(self.add, page)
        self.assertLess(page.index("Position ohne Produkt"), page.index("Textposition einfügen"))
        reader = self.assert_ok(self.browser_for("nora", "Nur-Lesen").get(self.detail))
        self.assertNotIn("Textposition einfügen", reader)
        self.assertNotIn(self.add, reader)

    def test_the_dialog_inserts_a_text_line(self) -> None:
        dialog = self.htmx("get", self.add)
        text = self.assert_ok(dialog)
        self.assertIn('name="title"', text)
        self.assertIn('name="note"', text)
        self.assertIn('name="group"', text)
        self.assertNotIn('name="quantity"', text)
        self.assertNotIn('name="unit_price"', text)
        response = self.htmx(
            "post", self.add, form_data(dialog, title="Aufbau ab 14 Uhr", note="Tor 2", group=self.group.pk)
        )
        self.assertEqual(response.status_code, 200, response.content.decode()[:500])
        (line,) = text_lines_of(self.project)
        self.assertEqual((line.title, line.note, line.group), ("Aufbau ab 14 Uhr", "Tor 2", self.group))
        self.assertIn("Aufbau ab 14 Uhr", response.content.decode())

    def test_the_group_can_be_preselected(self) -> None:
        dialog = self.htmx("get", self.add, {"group": self.group.pk})
        self.assertEqual(form_data(dialog)["group"], str(self.group.pk))

    def test_a_text_is_required(self) -> None:
        dialog = self.htmx("get", self.add)
        response = self.htmx("post", self.add, form_data(dialog, title=""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(text_lines_of(self.project), [])
        self.assertIn("errorlist", response.content.decode())

    def test_a_forged_alternative_to_a_text_line_is_refused(self) -> None:
        """(text lines; PRJ-128): the dialogs do not offer the text line, and a posted ID does not get through."""
        text = services.add_text_line(self.project, title="Aufbau ab 14 Uhr").line
        second = add_line(self.project, limited("L-020", "50.00", maximum=None), 1).line
        edit = reverse("projects:line_edit", args=[self.project.pk, second.pk])
        dialog = self.htmx("get", edit)
        page = self.assert_ok(dialog)
        offered = re.search(r'<select[^>]*name="alternative_to".*?</select>', page, re.S)
        self.assertIsNotNone(offered)
        self.assertNotIn(f'value="{text.pk}"', offered.group(0))
        response = self.htmx("post", edit, form_data(dialog, variant=LineVariant.ALTERNATIVE, alternative_to=text.pk))
        self.assertEqual(response.status_code, 200)
        second.refresh_from_db()
        self.assertEqual((second.variant, second.alternative_to_id), (LineVariant.NORMAL, None))
        bulk = reverse("projects:lines_bulk", args=[self.project.pk])
        self.htmx("post", bulk, {"action": "alternative", "lines": [second.pk], "alternative_to": text.pk})
        second.refresh_from_db()
        self.assertEqual((second.variant, second.alternative_to_id), (LineVariant.NORMAL, None))
        dialog = reverse("projects:lines_alternative", args=[self.project.pk])
        sent = self.htmx("post", dialog, {"lines": [second.pk], "alternative_to": text.pk})
        self.assertEqual(sent.status_code, 200)
        second.refresh_from_db()
        self.assertEqual((second.variant, second.alternative_to_id), (LineVariant.NORMAL, None))

    def test_the_surcharge_dialog_does_not_offer_the_text_line(self) -> None:
        text = services.add_text_line(self.project, title="Aufbau ab 14 Uhr").line
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        surcharge = add_line(self.project, night).line
        page = self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, surcharge.pk])))
        self.assertIn(f'value="line:{self.first.pk}"', page)
        self.assertNotIn(f'value="line:{text.pk}"', page)

    def test_a_number_that_is_not_a_number_is_ignored(self) -> None:
        """ "²".isdigit() is true and int("²") fails: the address ?group=² must not end in a 500."""
        for value in ("²", "①", "٣"):
            response = self.htmx("get", self.add, {"group": value})
            self.assertEqual(response.status_code, 200, value)
            self.assertNotEqual(form_data(response).get("group"), value)
        bulk = reverse("projects:lines_bulk", args=[self.project.pk])
        for data in (
            {"action": "move", "lines": ["²", self.first.pk], "group": "²"},
            {"action": "alternative", "lines": [self.first.pk], "alternative_to": "²"},
        ):
            self.assertEqual(self.htmx("post", bulk, data).status_code, 200, data)
        sent = self.htmx(
            "post",
            reverse("projects:lines_alternative", args=[self.project.pk]),
            {"lines": [self.first.pk], "alternative_to": "²"},
        )
        self.assertEqual(sent.status_code, 200)

    def test_without_page_script(self) -> None:
        response = self.client.post(self.add, {"title": "Hinweis", "note": "", "group": ""})
        self.assertIn(response.status_code, (200, 302))
        self.assertEqual(len(text_lines_of(self.project)), 1)

    def test_who_only_reads_cannot_insert(self) -> None:
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertEqual(self.htmx("get", self.add, client=reader).status_code, 403)
        self.assertEqual(self.htmx("post", self.add, {"title": "Nein"}, client=reader).status_code, 403)
        self.assertEqual(text_lines_of(self.project), [])

    def test_the_row_in_the_planning(self) -> None:
        text = services.add_text_line(self.project, title="Aufbau ab 14 Uhr", note="Zufahrt\nüber Tor 2").line
        page = self.assert_ok(self.client.get(self.detail))
        row = page[page.index(f'data-line="{text.pk}"') :]
        row = row[: row.index("</tr>")]
        self.assertIn('class="is-text"', row)
        self.assertIn("Aufbau ab 14 Uhr", row)
        self.assertIn("Zufahrt<br>über Tor 2", row)
        self.assertNotIn("0,00", row)
        self.assertIn(f'name="lines" value="{text.pk}"', row)
        self.assertIn("drag-handle", row)
        self.assertIn(reverse("projects:line_edit", args=[self.project.pk, text.pk]), row)
        self.assertIn(reverse("projects:line_duplicate", args=[self.project.pk, text.pk]), row)
        self.assertIn(reverse("projects:line_delete", args=[self.project.pk, text.pk]), row)
        self.assertNotIn("availability", row)
        # Without prices the row has fewer cells but is still one row of text.
        Role.objects.create(name="Planer ohne Preise", module_levels={"projects": 3, "products": 2})
        plain = self.assert_ok(self.browser_for("paul", "Planer ohne Preise").get(self.detail))
        self.assertIn("Aufbau ab 14 Uhr", plain)

    def test_totals_and_the_group_subtotal_do_not_change(self) -> None:
        before = self.assert_ok(self.client.get(self.detail))
        services.add_text_line(self.project, title="Hinweis", group=self.group)
        after = self.assert_ok(self.client.get(self.detail))
        for amount in ("200,00", "238,00"):
            self.assertEqual(before.count(amount), after.count(amount), amount)

    def test_the_edit_dialog_has_text_note_and_group_only(self) -> None:
        text = services.add_text_line(self.project, title="Hinweis").line
        url = reverse("projects:line_edit", args=[self.project.pk, text.pk])
        dialog = self.htmx("get", url)
        page = self.assert_ok(dialog)
        for name in ("title", "note", "group"):
            self.assertIn(f'name="{name}"', page)
        for name in ("quantity", "unit_price", "discount_percent", "variant", "start", "end"):
            self.assertNotIn(f'name="{name}"', page)
        self.assertNotIn("line-availability", page)
        response = self.htmx("post", url, form_data(dialog, title="Neuer Hinweis", group=self.group.pk))
        self.assertEqual(response.status_code, 200)
        text.refresh_from_db()
        self.assertEqual((text.title, text.group), ("Neuer Hinweis", self.group))
        self.assertTrue(text.is_text)

    def test_duplicate_move_and_delete(self) -> None:
        text = services.add_text_line(self.project, title="Hinweis").line
        copy = self.htmx("post", reverse("projects:line_duplicate", args=[self.project.pk, text.pk]))
        self.assertEqual(copy.status_code, 200)
        self.assertEqual(len(text_lines_of(self.project)), 2)
        bulk = reverse("projects:lines_bulk", args=[self.project.pk])
        response = self.htmx("post", bulk, {"lines": [text.pk], "action": "optional"})
        self.assertIn("ist eine Textposition ohne Preis", response.content.decode())
        response = self.htmx("post", bulk, {"lines": [text.pk], "action": "move", "group": self.group.pk})
        self.assertEqual(response.status_code, 200)
        text.refresh_from_db()
        self.assertEqual(text.group, self.group)
        self.htmx("post", reverse("projects:line_delete", args=[self.project.pk, text.pk]))
        self.assertEqual(len(text_lines_of(self.project)), 1)

    def test_the_price_overview_page(self) -> None:
        services.add_text_line(self.project, title="Hinweis im Preis")
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn("Hinweis im Preis", page)
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.project.pk])).content.decode()
        self.assertIn("Hinweis im Preis", csv)
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.project.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))


class TextLineCopyTests(TextLineCase):
    """Group copy, project duplicate, template, split: the text line goes along (PRJ-014, PRJ-076, PRJ-050)."""

    def test_copying_a_group(self) -> None:
        services.add_text_line(self.project, title="Im Licht", group=self.group)
        copy = services.copy_group(self.group, self.project, rights=ALL_RIGHTS)
        self.assertEqual(
            sorted(self.project.material_lines.filter(group=copy).values_list("is_text", "title")),
            [(False, self.first.title), (True, "Im Licht")],
        )

    def test_duplicating_the_project(self) -> None:
        copy = duplicate_project(
            self.project,
            name="Stadtfest 2028",
            start=at(10, year=2028),
            end=at(12, year=2028),
            rights=ALL_RIGHTS,
            user=None,
        )
        (line,) = text_lines_of(copy)
        self.assertEqual((line.title, line.note), ("Aufbau ab 14 Uhr", "Zufahrt über Tor 2"))
        self.assertEqual(compute_project_prices(copy).net_total, D("250.00"))
        self.assertEqual(copy.material_lines.count(), 3)

    def test_a_template(self) -> None:
        template = save_as_template(self.project, name="Vorlage", rights=ALL_RIGHTS)
        self.assertEqual(template.counts["lines"], 3)
        target = make_project("Neu", start=at(20, 12, month=4), end=at(22, 12, month=4))
        result = apply_template(template, target, rights=ALL_RIGHTS)
        self.assertEqual(result.lines, 3)
        (line,) = text_lines_of(target)
        self.assertEqual((line.title, line.note), ("Aufbau ab 14 Uhr", "Zufahrt über Tor 2"))
        self.assertIsNone(line.product)
        self.assertEqual(line.quantity, 0)

    def test_splitting_a_group_takes_its_text_lines(self) -> None:
        services.add_text_line(self.project, title="Im Licht", group=self.group)
        (part,) = split_into_subprojects(self.project, [self.group.pk]).parts
        self.assertEqual([line.title for line in text_lines_of(part)], ["Im Licht"])
        self.assertEqual([line.title for line in text_lines_of(self.project)], ["Aufbau ab 14 Uhr"])

    def test_the_project_keeps_planning_with_text_lines_in_every_status(self) -> None:
        services.change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.assertEqual(len(text_lines_of(self.project)), 1)
        self.assertEqual(CrewLine.objects.filter(project=self.project).count(), 0)


class TextLineApiTests(ApiTestCase):
    """``"is_text": true`` on the existing line endpoints (PRJ-017, API-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.line = add_line(self.project, limited(maximum=None), 2, group=self.group).line
        self.base = f"{API}/projects/{self.project.pk}"
        self.lines = f"{self.base}/material-lines"

    def create(self, **values: object) -> dict:
        response = self.admin.post(self.lines, {"is_text": True, **values}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_create_read_change_and_delete(self) -> None:
        body = self.create(title="Aufbau ab 14 Uhr", note="Tor 2", group=self.group.pk)
        self.assertEqual(
            (body["is_text"], body["kind"], body["title"], body["note"], body["group"]),
            (True, "text", "Aufbau ab 14 Uhr", "Tor 2", self.group.pk),
        )
        self.assertEqual(body["warnings"], [])
        url = f"{self.lines}/{body['id']}"
        self.assertEqual(self.admin.get(url).json()["is_text"], True)
        self.assertFalse(self.admin.get(f"{self.lines}/{self.line.pk}").json()["is_text"])
        patched = self.admin.patch(url, {"title": "Neu"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual((patched.json()["title"], patched.json()["is_text"]), ("Neu", True))
        self.assertEqual(patched.json()["price"]["amount"], "0.00")
        listed = {row["id"]: row for row in self.admin.get(self.lines).json()}
        self.assertTrue(listed[body["id"]]["is_text"])
        self.assertEqual(self.admin.delete(url).status_code, 204)
        self.assertFalse(MaterialLine.objects.filter(pk=body["id"]).exists())

    def test_a_text_line_takes_no_product_and_no_numbers(self) -> None:
        for values, field in (
            ({"product": self.line.product_id}, "product"),
            ({"quantity": "2"}, "quantity"),
            ({"unit_price": "5.00"}, "unit_price"),
            ({"discount_percent": "5"}, "discount_percent"),
        ):
            response = self.admin.post(self.lines, {"is_text": True, "title": "Text", **values}, format="json")
            self.assert_error(response, 400, "validation_error", field)
        self.assert_error(
            self.admin.post(self.lines, {"is_text": True, "title": " "}, format="json"),
            400,
            "validation_error",
            "title",
        )
        self.assertEqual(MaterialLine.objects.filter(is_text=True).count(), 0)

    def test_the_flag_cannot_be_changed_later(self) -> None:
        body = self.create(title="Text")
        self.assert_error(
            self.admin.patch(f"{self.lines}/{body['id']}", {"is_text": False}, format="json"),
            400,
            "validation_error",
            "is_text",
        )
        self.assert_error(
            self.admin.patch(f"{self.lines}/{self.line.pk}", {"is_text": True}, format="json"),
            400,
            "validation_error",
            "is_text",
        )
        same = self.admin.patch(f"{self.lines}/{self.line.pk}", {"is_text": False, "quantity": "3"}, format="json")
        self.assertEqual(same.status_code, 200, same.content)

    def test_a_reader_cannot_create_one(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assert_error(
            reader.post(self.lines, {"is_text": True, "title": "Nein"}, format="json"), 403, "permission_denied"
        )

    def test_duplicate_and_bulk(self) -> None:
        body = self.create(title="Text")
        copy = self.admin.post(f"{self.lines}/{body['id']}/duplicate")
        self.assertEqual(copy.status_code, 201, copy.content)
        self.assertEqual((copy.json()["is_text"], copy.json()["title"]), (True, "Text"))
        bulk = self.admin.post(
            f"{self.lines}/bulk", {"lines": [body["id"], self.line.pk], "action": "optional"}, format="json"
        )
        data = bulk.json()
        self.assertEqual(data["changed"], [self.line.pk])
        self.assertEqual([row["line"] for row in data["skipped"]], [body["id"]])
        self.assertEqual(data["skipped"][0]["reason"], "ist eine Textposition ohne Preis")

    def test_the_price_overview_and_the_totals(self) -> None:
        self.create(title="Text", note="Mehr")
        overview = self.admin.get(f"{self.base}/price-overview").json()
        rows = overview["without_group"]["lines"]
        (row,) = [row for row in rows if row["is_text"]]
        self.assertEqual((row["title"], row["quantity"]), ("Text", "0.00"))
        self.assertTrue(row["is_text"])
        self.assertEqual(row["note"], "Mehr")
        self.assertEqual(self.admin.get(f"{self.base}/totals").json()["net_total"], "200.00")

    def test_documents_and_planning_carry_it(self) -> None:
        self.create(title="Aufbau ab 14 Uhr")
        planning = self.admin.get(f"{self.base}/planning").json()
        self.assertIn("Aufbau ab 14 Uhr", str(planning))
        ready_for_invoices(self.project.customer)
        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        self.assertEqual(sum(1 for s in invoice.content["sections"] for p in s["positions"] if p["is_text"]), 1)
        self.assertEqual(invoice.net_total, D("200.00"))
