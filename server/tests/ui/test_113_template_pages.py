# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages for editing the content of a project template (PRJ-135)."""

from __future__ import annotations

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.projects import template_content as content
from rentalars.projects.models import OpenItem, PhaseKind, ProjectPhase, ProjectTemplate
from rentalars.projects.project_templates import save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    add_group,
    add_line,
    at,
    job_function,
    make_project,
    make_stock,
    plan,
)
from tests.ui.base import UiTestCase


class TemplateContentPageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-001", 10, "Lautsprecher", price="20.00")
        self.source = make_project("Stadtfest 2027", start=at(10, 12), end=at(12, 12))
        self.stage = add_group(self.source, "Bühne")
        add_line(self.source, self.speaker, 4, group=self.stage)
        self.tech = job_function("Tontechnik", price="40.00")
        plan(self.source, self.tech)
        ProjectPhase.objects.create(project=self.source, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 18))
        OpenItem.objects.create(project=self.source, text="Strom klären")
        self.template = save_as_template(self.source, name="Stadtfest", rights=ALL_RIGHTS)
        content.open_for_editing(self.template)
        self.url = reverse("projects:template_content", args=[self.template.pk])

    def stored(self) -> dict:
        return ProjectTemplate.objects.get(pk=self.template.pk).content

    def key(self, section: str) -> int:
        return self.stored()[section][0]["key"]

    def add_url(self, section: str, **query: str) -> str:
        url = reverse("projects:template_entry_add", args=[self.template.pk, section])
        return url + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "")

    def edit_url(self, section: str, key: int) -> str:
        return reverse("projects:template_entry_edit", args=[self.template.pk, section, key])

    def test_the_list_links_to_the_content_and_the_content_shows_everything(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:templates")))
        self.assertIn(self.url, page)
        page = self.assert_ok(self.client.get(self.url))
        for text in ("Bühne", "Lautsprecher", "Tontechnik", "Strom klären"):
            self.assertIn(text, page)
        self.assertIn(self.add_url("groups"), page)
        self.assertIn(reverse("projects:template_edit", args=[self.template.pk]), page)

    def test_add_a_group_and_a_product_line(self) -> None:
        response = self.client.post(
            self.add_url("groups"), {"name": "Licht", "kind": "normal", "parent": str(self.key("groups"))}
        )
        self.assertRedirects(response, self.url + "#groups", fetch_redirect_response=False)
        light = next(g for g in self.stored()["groups"] if g["name"] == "Licht")
        self.assertEqual(light["parent"], self.key("groups"))
        cable = make_stock("K-001", 50, "Kabel", price="2.00")
        self.client.post(
            self.add_url("lines"),
            {
                "as": "product",
                "product": str(cable.pk),
                "quantity": "20",
                "group": str(light["key"]),
                "period": "project",
            },
        )
        line = next(line for line in self.stored()["lines"] if line["product"] == cable.pk)
        self.assertEqual((line["group"], line["quantity"]), (light["key"], "20.00"))

    def test_the_form_for_a_line_asks_for_the_product(self) -> None:
        page = self.assert_ok(self.client.get(self.add_url("lines", **{"as": "product"})))
        self.assertIn("data-typeahead-value", page)
        self.assertIn('name="as" value="product"', page)
        free = self.assert_ok(self.client.get(self.add_url("lines", **{"as": "free"})))
        self.assertIn('name="title"', free)
        self.assertNotIn("data-typeahead-value", free)

    def test_a_free_line_and_a_text(self) -> None:
        self.client.post(
            self.add_url("lines"),
            {"as": "free", "title": "Anfahrt", "quantity": "1", "unit_price": "80,00", "period": "project"},
        )
        self.client.post(self.add_url("lines"), {"as": "text", "title": "Alles inklusive"})
        titles = {line["title"]: line for line in self.stored()["lines"] if line["title"]}
        self.assertEqual(titles["Anfahrt"]["unit_price"], "80.00")
        self.assertTrue(titles["Alles inklusive"]["is_text"])

    def test_change_a_line_and_keep_what_the_form_does_not_show(self) -> None:
        key = self.key("lines")
        # A preferred model and the hours are not on the form; they must survive a change of the quantity.
        template = ProjectTemplate.objects.get(pk=self.template.pk)
        stored = template.content
        stored["lines"][0]["hours"] = "3.50"
        template.content = stored
        template.save(update_fields=["content"])
        page = self.assert_ok(self.client.get(self.edit_url("lines", key)))
        self.assertIn('name="quantity" value="4"', page.replace("4,00", "4").replace("4.00", "4"))
        self.client.post(
            self.edit_url("lines", key),
            {"product": str(self.speaker.pk), "quantity": "6", "period": "project", "group": str(self.key("groups"))},
        )
        line = self.stored()["lines"][0]
        self.assertEqual((line["quantity"], line["hours"]), ("6.00", "3.50"))

    def test_the_period_of_a_crew_place_in_hours_from_the_end(self) -> None:
        key = self.key("crew")
        response = self.client.post(
            self.edit_url("crew", key),
            {"job_function": str(self.tech.pk), "period": "end", "from_hours": "3", "to_hours": "1", "phase": ""},
        )
        self.assertEqual(response.status_code, 302)
        entry = self.stored()["crew"][0]
        self.assertEqual(
            (entry["own_period"], entry["anchor"], entry["start"], entry["end"]), (True, "end", -10800, -3600)
        )
        page = self.assert_ok(self.client.get(self.edit_url("crew", key)))
        self.assertIn('name="from_hours" value="3"', page)

    def test_a_period_that_ends_before_it_begins_is_refused(self) -> None:
        response = self.client.post(
            self.add_url("crew"),
            {"job_function": str(self.tech.pk), "period": "start", "from_hours": "5", "to_hours": "2"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.stored()["crew"]), 1)

    def test_a_phase_needs_a_period_and_a_crew_place_can_name_it(self) -> None:
        response = self.client.post(self.add_url("phases"), {"kind": "setup", "period": "project"})
        self.assertEqual(response.status_code, 200)
        self.client.post(
            self.add_url("phases"), {"kind": "setup", "period": "start", "from_hours": "20", "to_hours": "24"}
        )
        self.assertEqual(len(self.stored()["phases"]), 2)
        self.client.post(
            self.edit_url("crew", self.key("crew")),
            {"job_function": str(self.tech.pk), "period": "project", "phase": "1"},
        )
        self.assertEqual(self.stored()["crew"][0]["phase"], 1)

    def test_open_items_are_added_changed_and_deleted_by_their_text(self) -> None:
        self.client.post(self.add_url("open_items"), {"text": "Hotel buchen"})
        self.assertEqual(self.stored()["open_items"], ["Strom klären", "Hotel buchen"])
        edit = self.edit_url("open_items", 0)
        page = self.assert_ok(self.client.get(edit, {"expect": "Strom klären"}))
        self.assertIn('name="expect" value="Strom klären"', page)
        self.client.post(edit, {"text": "Strom bestellen", "expect": "Strom klären"})
        self.assertEqual(self.stored()["open_items"][0], "Strom bestellen")
        # Somebody else changed the list: the page is out of date, nothing is changed.
        response = self.client.post(edit, {"text": "Falsch", "expect": "Strom klären"}, follow=True)
        self.assertEqual(self.stored()["open_items"][0], "Strom bestellen")
        self.assertTrue(self.messages_of(response))
        delete = reverse("projects:template_entry_delete", args=[self.template.pk, "open_items", 1])
        self.client.post(delete, {"expect": "Hotel buchen"})
        self.assertEqual(self.stored()["open_items"], ["Strom bestellen"])

    def test_move_entries(self) -> None:
        self.client.post(self.add_url("open_items"), {"text": "Zweiter"})
        move = reverse("projects:template_entry_move", args=[self.template.pk, "open_items", 1])
        self.client.post(move, {"direction": "up", "expect": "Zweiter"})
        self.assertEqual(self.stored()["open_items"], ["Zweiter", "Strom klären"])
        self.assertEqual(self.client.get(move).status_code, 405)

    def test_delete_a_group_keeps_or_removes_its_content(self) -> None:
        key = self.key("groups")
        delete = reverse("projects:template_entry_delete", args=[self.template.pk, "groups", key])
        page = self.assert_ok(self.client.get(delete))
        self.assertIn("with_content", page)
        self.client.post(delete)
        self.assertEqual(self.stored()["groups"], [])
        self.assertEqual(len(self.stored()["lines"]), 1)
        self.assertIsNone(self.stored()["lines"][0]["group"])

    def test_delete_a_group_with_its_content(self) -> None:
        key = self.key("groups")
        self.client.post(
            reverse("projects:template_entry_delete", args=[self.template.pk, "groups", key]), {"with_content": "1"}
        )
        self.assertEqual((self.stored()["groups"], self.stored()["lines"]), ([], []))

    def test_an_entry_that_is_gone_says_so(self) -> None:
        url = self.edit_url("groups", 999)
        response = self.client.get(url, follow=True)
        self.assertEqual(response.redirect_chain[-1][0].split("#")[0], self.url)
        self.assertTrue(self.messages_of(response))
        self.assertEqual(self.client.get(self.edit_url("sections", 1)).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("projects:template_entry_delete", args=[self.template.pk, "groups", 999])
            ).status_code,
            302,
        )

    def test_notes_and_rental_days(self) -> None:
        url = reverse("projects:template_notes", args=[self.template.pk])
        self.assert_ok(self.client.get(url))
        self.client.post(url, {"notes": "Bitte Strom prüfen", "rental_days": "3"})
        self.assertEqual((self.stored()["notes"], self.stored()["rental_days"]), ("Bitte Strom prüfen", 3))
        self.assertIn("Bitte Strom prüfen", self.assert_ok(self.client.get(self.url)))

    def test_a_change_is_in_the_audit_trail_and_reaches_new_projects(self) -> None:
        from rentalars.core.models import AuditLogEntry
        from rentalars.projects.project_templates import apply_template

        self.client.post(self.add_url("open_items"), {"text": "Hotel buchen"})
        self.assertTrue(AuditLogEntry.objects.filter(event="project_template.content_changed").exists())
        target = make_project("Weinfest", start=at(20, 12, month=4), end=at(22, 12, month=4))
        apply_template(ProjectTemplate.objects.get(pk=self.template.pk), target, rights=ALL_RIGHTS)
        self.assertEqual(
            sorted(OpenItem.objects.filter(project=target).values_list("text", flat=True)),
            ["Hotel buchen", "Strom klären"],
        )

    def test_prices_stay_as_they_are_for_somebody_without_the_price_right(self) -> None:
        free = content.add_entry(
            ProjectTemplate.objects.get(pk=self.template.pk),
            "lines",
            {"title": "Anfahrt", "quantity": 1, "unit_price": "80.00"},
            rights=ALL_RIGHTS,
        )
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.browser_for("paul", "Planung ohne Preise")
        page = self.assert_ok(planner.get(self.edit_url("lines", free)))
        self.assertNotIn('name="unit_price"', page)
        planner.post(
            self.edit_url("lines", free), {"as": "free", "title": "Anfahrt weit", "quantity": "2", "period": "project"}
        )
        line = next(line for line in self.stored()["lines"] if line["key"] == free)
        self.assertEqual((line["title"], line["unit_price"]), ("Anfahrt weit", "80.00"))

    def test_without_the_right_to_write_projects_there_is_no_page(self) -> None:
        Role.objects.create(name="Nur Projekte", module_levels={"projects": 1})
        reader = self.browser_for("reader", "Nur Projekte")
        self.assertEqual(reader.get(self.url).status_code, 403)
        self.assertEqual(reader.post(self.add_url("open_items"), {"text": "x"}).status_code, 403)
        self.assertEqual(self.stored()["open_items"], ["Strom klären"])
