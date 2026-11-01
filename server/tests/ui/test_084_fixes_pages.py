# SPDX-License-Identifier: GPL-3.0-or-later
"""Page tests, area "fixes": the quick entry always offers a job function (ZEI-007), the pages of the
surcharges say plainly that only crew lines get them (PER-009, PER-040), English labels (UIX-029); crew packs on the
packing list, without adding material.
"""

from __future__ import annotations

import re

from django.urls import reverse

from rentalars.packing import services as packing
from rentalars.packing.models import PackEntry
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product
from rentalars.projects.models import MaterialLine
from rentalars.timetracking.models import TimeEntry
from tests.helpers import (
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
    set_clock,
)
from tests.ui.base import UiTestCase, form_data


class CrewPacklistPagesTests(UiTestCase):
    """Crew ticks and packs in its own project; "add material" is replaced by the reason."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 12, "XLR-Kabel 5 m")
        self.project = make_project()
        self.line = add_line(self.project, self.cable, 10).line
        lea = make_user("lea", roles=("Crew",))
        plan(self.project, job_function("Stagehand"), make_person("Lea Vogel", user=lea))
        self.crew = self.browser_of(lea)
        self.url = reverse("packing:packlist", args=[self.project.pk])

    def test_crew_packs_but_does_not_add_material(self) -> None:
        page = self.assert_ok(self.crew.get(self.url))
        self.assertIn("data-no-addendum", page)
        self.assertIn(
            "Material nachtragen dürfen nur Personen, die das Projekt ändern dürfen oder für alle Projekte packen.",
            page,
        )
        self.assertNotIn("add-material/", page)
        ticked = self.htmx(
            "post",
            reverse("packing:row", args=[self.project.pk]),
            {"line": self.line.pk, "product": self.cable.pk, "quantity": "10"},
            client=self.crew,
        )
        self.assert_ok(ticked)
        self.assertEqual(PackEntry.objects.get(line=self.line).packed_quantity, 10)
        # Sent anyway, adding material is refused and changes nothing.
        refused = self.crew.post(
            reverse("packing:action", args=[self.project.pk, "add-material"]),
            {"product": self.cable.pk, "quantity": "2"},
        )
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 1)
        issued = self.crew.post(reverse("packing:action", args=[self.project.pk, "issue"]))
        self.assertEqual(issued.status_code, 302)
        self.assertTrue(packing.get_packlist(self.project).is_issued)

    def test_the_warehouse_still_adds_material(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        page = self.assert_ok(warehouse.get(self.url))
        self.assertIn("add-material/", page)
        self.assertNotIn("data-no-addendum", page)
        added = warehouse.post(
            reverse("packing:action", args=[self.project.pk, "add-material"]),
            {"product": self.cable.pk, "quantity": "2"},
        )
        self.assertEqual(added.status_code, 302)
        self.assertTrue(MaterialLine.objects.filter(project=self.project, is_addendum=True).exists())


class QuickEntryJobFunctionTests(UiTestCase):
    """ZEI-007: a project without phases and crew, a person without job functions of her own."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(at(11, 18))  # the project runs: it is among the suggestions; its hours lie before
        self.project = make_project("Messe", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.kai_user = make_user("kai", roles=("Projektleitung",))
        make_person("Kai Kurz", user=self.kai_user)
        self.kai = self.browser_of(self.kai_user)
        self.quick = reverse("timetracking:quick")

    def test_the_job_function_is_never_empty_and_the_time_is_saved(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.kai)
        text = self.assert_ok(dialog)
        select = re.search(r'<select name="job_function".*?</select>', text, flags=re.S)
        self.assertIsNotNone(select)
        options = re.findall(r'<option value="(\d+)"', select.group(0))
        self.assertEqual(len(options), JobFunction.objects.filter(is_active=True).count())
        self.assertIn(f'<option value="{self.sound.pk}"', select.group(0))
        self.assertIn(" selected", select.group(0))  # one is preselected (ZEI-003)
        saved = self.htmx(
            "post",
            self.quick,
            form_data(dialog, job_function=str(self.sound.pk), day="2027-03-10", begin="08:00", end="12:00"),
            client=self.kai,
        )
        self.assertIn("Zeit erfasst", self.assert_ok(saved))
        self.assertEqual(
            (TimeEntry.objects.get().project, TimeEntry.objects.get().job_function), (self.project, self.sound)
        )


class SurchargePagesTests(UiTestCase):
    """PER-009, PER-040: settings and product pages say it plainly."""

    def test_the_settings_page_names_the_crew_lines_only(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:time_surcharges")))
        self.assertIn("Diese Zuschläge bekommen nur Personalpositionen – nie Material, Nebenkosten", page)
        self.assertIn("Zuschläge im Preis der Personalpositionen", page)
        self.assertIn("Zuschläge in den Personalkosten der Personalpositionen", page)
        self.assertIn("Andere Produkte haben keinen solchen Schalter", page)
        overview = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn("Nacht, Sonn- und Feiertage – nur für Personalpositionen, auf Preis und Kosten", overview)

    def test_in_english(self) -> None:
        self.admin_user.language = "en"
        self.admin_user.save()
        page = self.assert_ok(self.client.get(reverse("core:time_surcharges")))
        self.assertIn("Only crew lines get these surcharges", page)
        self.assertIn("from 0:00 to 4:00", page)
        self.assertNotIn("o'clock", page.replace("&#x27;", "'"))

    def test_a_product_that_is_no_service_keeps_no_switch(self) -> None:
        """The form shows the switch for services only; sent for another product it changes nothing."""
        spot = make_product("L-100", "Scheinwerfer")
        url = reverse("products:edit", args=[spot.pk])
        form = self.client.get(url)
        response = self.client.post(url, form_data(form, containing="time_surcharges", time_surcharges=None))
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        self.assertTrue(Product.objects.get(pk=spot.pk).time_surcharges)
        detail = self.assert_ok(self.client.get(reverse("products:detail", args=[spot.pk])))
        self.assertNotIn("Nacht, Sonn- und Feiertage", detail)
        # A service still can exclude its lines (as).
        service = job_function("Tontechnik", price="45.00").service_product
        url = reverse("products:edit", args=[service.pk])
        form = self.client.get(url)
        self.client.post(url, form_data(form, containing="time_surcharges", time_surcharges=None))
        self.assertFalse(Product.objects.get(pk=service.pk).time_surcharges)


class EnglishLabelPagesTests(UiTestCase):
    """UIX-029: the accounting settings in English say "debtor"; German stays."""

    def test_the_accounting_settings(self) -> None:
        url = reverse("documents:accounting")
        german = self.assert_ok(self.client.get(url))
        self.assertIn("Debitorenkonten", german)
        self.assertIn("Meist 4. Debitorenkonten haben eine Stelle mehr.", german)
        self.admin_user.language = "en"
        self.admin_user.save()
        english = self.assert_ok(self.client.get(url))
        self.assertIn("one debtor account per customer", english)
        self.assertIn("Number of digits of the general ledger accounts: 4 in most companies.", english)
        self.assertIn("(Beraternummer)", english)
        # What a reader sees – names of fields and addresses such as "?what=debitors" are no text.
        visible = re.sub(r"<[^>]*>", " ", re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", english))
        self.assertNotIn("debitor", visible.lower())
