# SPDX-License-Identifier: GPL-3.0-or-later
"""Audits in the material management (MAT-067, MAT-068, MAT-069, MAT-070).

Requirement: audits in the material management. The settings hold an audit interval (default 2 years). An audit is a short check of
the material. In that context small things can be noted on an item (such as "Label fehlt" or, for cables, "Klett fehlt"); they appear
like open points in the material management, in the tab "Offene Punkte" with the sub-tabs "Modelle ohne Produkt" and
"Material mit To-Do".

Decided: an audit mode of its own – IDs typed or scanned one after the other, per item "in Ordnung" or to-dos by quick pick; due
audits and open to-dos under "Offene Punkte"; to-dos also at any time on the item.

* Einstellungen → Audits: the interval (24 months; 0 is off) and the quick picks.
* Due: last audit + interval; never audited: creation in Rentalars + interval; archived items and bulk material never.
* The audit mode, the box on the item's page, the history, the three sub-tabs of "Offene Punkte", the API.
"""

from __future__ import annotations

import datetime
import importlib

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from rentalars.accounts.models import Role
from rentalars.core.models import CompanyProfile
from rentalars.material import audits
from rentalars.material.audit_models import AuditResult, AuditSettings, ItemAudit, ItemTodo
from rentalars.material.history import item_history
from rentalars.material.models import ItemStatus, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, make_item, make_model, make_product, make_user, set_clock
from tests.ui.base import UiTestCase, form_data


def created(item: MaterialItem, moment: datetime.datetime) -> MaterialItem:
    """Pretend the item was entered in Rentalars at ``moment`` (the change log is not the point here)."""
    MaterialItem.objects.filter(pk=item.pk).update(created_at=moment)
    item.refresh_from_db()
    return item


def audited(item: MaterialItem, moment: datetime.datetime, result: str = AuditResult.OK) -> ItemAudit:
    return ItemAudit.objects.create(item=item, audited_at=moment, result=result)


def set_interval(months: int) -> None:
    row = AuditSettings.load()
    row.interval_months = months
    row.save()


class AuditCase(RentalarsTestCase):
    """A microphone 0427, a cable 0428 and a rack 0500 without product – all entered today, 1 March 2027."""

    def setUp(self) -> None:
        super().setUp()
        self.microphone = make_item(make_model("Shure SM58", make_product("T-010")), 427)
        self.cable = make_item(make_model("XLR-Kabel 10 m", make_product("K-010")), 428)
        self.rack = make_item(make_model("Rack 19 Zoll"), 500)


class SettingsTests(RentalarsTestCase):
    """Einstellungen → Audits: 24 months unless set otherwise, and short quick picks for event technology."""

    def test_defaults(self) -> None:
        row = AuditSettings.load()
        self.assertEqual(row.interval_months, 24)
        self.assertTrue(row.is_active)
        self.assertEqual(row.quick_todo_list, ["Label fehlt", "Klett fehlt", "Beschädigt", "Reinigen", "Teile fehlen"])

    def test_quick_picks_are_tidied_and_limited(self) -> None:
        row = AuditSettings.load()
        row.quick_todos = "  Label fehlt \n\nlabel FEHLT\nStecker   locker\n"
        row.full_clean()
        self.assertEqual(row.quick_todos, "Label fehlt\nStecker locker")
        row.quick_todos = "\n".join(f"Punkt {number}" for number in range(13))
        with self.assertRaises(ValidationError) as caught:
            row.full_clean()
        self.assertIn("Höchstens 12 Einträge in der Schnellauswahl.", caught.exception.message_dict["quick_todos"])
        row.quick_todos = "x" * 61
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_off_is_zero(self) -> None:
        set_interval(0)
        self.assertFalse(AuditSettings.load().is_active)

    def test_english_company_gets_english_quick_picks(self) -> None:
        """UIX-029: the update for an English company, and the start data of an English installation."""
        migration = importlib.import_module("rentalars.material.migrations.0007_audits_092")
        AuditSettings.objects.all().delete()
        company = CompanyProfile.load()
        company.document_language = "en"
        company.save()
        migration.create_audit_settings(django_apps, None)
        self.assertEqual(AuditSettings.load().quick_todo_list[:2], ["Label missing", "Velcro missing"])
        from rentalars.core import start_data

        start_data._localise_audit_todos("de")
        self.assertEqual(AuditSettings.load().quick_todo_list[0], "Label fehlt")
        row = AuditSettings.load()
        row.quick_todos = "Eigenes"
        row.save()
        self.assertEqual(start_data._localise_audit_todos("en"), 0)  # changed by the company: left alone


class SettingsPageTests(UiTestCase):
    """The page under Einstellungen, changed with write access to the settings."""

    def test_saved_from_the_page(self) -> None:
        administration = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'<a href="{reverse("material:audit_settings")}">Audits</a>', administration)
        page = self.client.get(reverse("material:audit_settings"))
        self.assertIn("Audit-Intervall (Monate)", self.assert_ok(page))
        data = form_data(page, containing="interval_months", interval_months="12", quick_todos="Label fehlt\nNetzteil")
        self.assertRedirects(
            self.client.post(reverse("material:audit_settings"), data), reverse("material:audit_settings")
        )
        row = AuditSettings.load()
        self.assertEqual((row.interval_months, row.quick_todo_list), (12, ["Label fehlt", "Netzteil"]))

    def test_read_only_for_who_may_read_the_settings(self) -> None:
        Role.objects.create(name="Einstellungen lesen", module_levels={"administration": 1, "material": 1})
        reader = self.browser_for("rita", "Einstellungen lesen")
        page = self.assert_ok(reader.get(reverse("material:audit_settings")))
        self.assertIn("<fieldset disabled>", page)
        self.assertEqual(reader.post(reverse("material:audit_settings"), {"interval_months": "6"}).status_code, 403)
        self.assertEqual(AuditSettings.load().interval_months, 24)
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.get(reverse("material:audit_settings")).status_code, 403)


class DueTests(AuditCase):
    """Due: last audit + interval; never audited: entered + interval; never for archived items and bulk material."""

    def test_never_audited_counts_from_the_creation(self) -> None:
        # A fresh installation is not flooded: what was entered today is due in two years.
        self.assertFalse(audits.due_items().exists())
        self.assertEqual(audits.state_of(self.microphone).due_date, datetime.date(2029, 3, 1))
        created(self.microphone, at(1, 23, year=2025))  # exactly 24 months ago: due today
        created(self.cable, at(2, 9, year=2025))  # one day later: due tomorrow
        self.assertEqual(list(audits.due_items()), [self.microphone])
        state = audits.state_of(self.microphone)
        self.assertEqual((state.due_date, state.is_due, state.never_audited), (datetime.date(2027, 3, 1), True, True))
        self.assertFalse(audits.state_of(self.cable).is_due)

    def test_the_last_audit_counts_whatever_it_found(self) -> None:
        for item in (self.microphone, self.cable, self.rack):
            created(item, at(1, 8, year=2020))
        audited(self.microphone, at(15, 10, month=2, year=2025), AuditResult.TODOS)
        audited(self.cable, at(10, 10, month=1, year=2027))
        due = list(audits.due_items())
        # Oldest first: never audited since 2020 before audited in February 2025.
        self.assertEqual(due, [self.rack, self.microphone])
        self.assertEqual(audits.state_of(self.microphone).due_date, datetime.date(2027, 2, 15))
        self.assertEqual(audits.state_of(self.cable).due_date, datetime.date(2029, 1, 10))
        self.assertEqual(due[1].open_todo_count, 0)
        self.assertIsNotNone(due[1].last_audit_at)

    def test_archived_items_and_bulk_material_are_never_due(self) -> None:
        cable_ties = make_item(make_model("Kabelbinder", make_product("S-001"), bulk=True), 900, quantity=100)
        for item in (self.microphone, cable_ties):
            created(item, at(1, 8, year=2020))
        self.microphone.status = ItemStatus.RETIRED
        self.microphone.save()
        self.assertFalse(audits.due_items().exists())
        self.assertEqual(audits.state_of(self.microphone).no_due_reason, audits.ARCHIVED)
        self.assertEqual(audits.state_of(cable_ties).no_due_reason, audits.BULK)
        self.assertIsNone(audits.state_of(cable_ties).due_date)

    def test_interval_zero_switches_audits_off(self) -> None:
        created(self.microphone, at(1, 8, year=2020))
        set_interval(0)
        self.assertFalse(audits.due_items().exists())
        state = audits.state_of(self.microphone)
        self.assertEqual((state.due_date, state.no_due_reason), (None, audits.OFF))

    def test_the_end_of_a_month(self) -> None:
        """31 January + 1 month = 28 February – the list and the item's page agree."""
        set_interval(1)
        created(self.microphone, at(1, 8, month=1))
        created(self.cable, at(1, 8, month=1))
        audited(self.microphone, at(31, 18, month=1))
        audited(self.cable, at(1, 9, month=2))
        set_clock(at(28, 8, month=2))
        self.assertEqual(audits.state_of(self.microphone).due_date, datetime.date(2027, 2, 28))
        self.assertEqual(list(audits.due_items()), [self.microphone])
        self.assertEqual(audits.state_of(self.cable).due_date, datetime.date(2027, 3, 1))


class RecordTests(AuditCase):
    """Recording audits and to-dos, and what the history of the item says about them."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_user("anna")

    def test_in_order_and_with_to_dos(self) -> None:
        audit = audits.record_audit(self.microphone, user=self.anna)
        self.assertEqual(
            (audit.result, audit.audited_by, audit.audited_at), (AuditResult.OK, self.anna, timezone.now())
        )
        found = audits.record_audit(
            self.cable, todos=["Klett fehlt", " klett   FEHLT ", "", "Label fehlt"], note="Rolle 3", user=self.anna
        )
        self.assertEqual(found.result, AuditResult.TODOS)
        self.assertEqual([todo.text for todo in found.todos.all()], ["Klett fehlt", "Label fehlt"])
        self.assertEqual(found.note, "Rolle 3")
        # The same to-do open already is not noted twice – not in an audit, not on the item's page.
        again = audits.record_audit(self.cable, todos=["Label fehlt"], user=self.anna)
        self.assertEqual(again.todos.count(), 0)
        self.assertEqual(audits.add_todo(self.cable, "LABEL fehlt", user=self.anna).audit, found)
        self.assertEqual(self.cable.todos.filter(done_at__isnull=True).count(), 2)

    def test_to_dos_found_done(self) -> None:
        label = audits.add_todo(self.cable, "Label fehlt", user=self.anna)
        other = audits.add_todo(self.microphone, "Reinigen", user=self.anna)
        audits.record_audit(self.cable, done=[label.pk, other.pk, "x"], user=self.anna)
        label.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((label.done_by, label.done_at), (self.anna, timezone.now()))
        self.assertTrue(other.is_open)  # only to-dos of the item audited
        self.assertFalse(audits.complete_todo(label, user=self.anna))  # done already

    def test_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            audits.add_todo(self.cable, "   ")
        self.assertEqual(caught.exception.message_dict["text"], ["Sag, was zu tun ist."])
        with self.assertRaises(ValidationError):
            audits.record_audit(self.cable, todos=["x" * 201])
        with self.assertRaises(ValidationError) as caught:
            audits.record_audit(self.cable, audited_at=timezone.now() + datetime.timedelta(days=1))
        self.assertIn("audited_at", caught.exception.message_dict)
        self.assertFalse(ItemAudit.objects.exists())

    def test_the_history_of_the_item(self) -> None:
        audit = audits.record_audit(self.cable, todos=["Klett fehlt"], note="Rolle 3", user=self.anna)
        audits.complete_todo(audit.todos.get(), user=self.anna)
        summaries = [row.summary for row in item_history(self.cable, ALL_RIGHTS)]
        self.assertIn("Audit: mit To-Dos – Rolle 3", summaries)
        self.assertIn("To-Do notiert: Klett fehlt", summaries)
        self.assertIn("To-Do erledigt: Klett fehlt", summaries)
        self.assertNotIn(
            "Audit: mit To-Dos – Rolle 3", [row.summary for row in item_history(self.microphone, ALL_RIGHTS)]
        )


class AuditModePageTests(UiTestCase):
    """Materialverwaltung → Audit: one item after the other, plain forms, fast with the keyboard."""

    def setUp(self) -> None:
        super().setUp()
        self.microphone = make_item(make_model("Shure SM58", make_product("T-010")), 427)
        self.cable = make_item(make_model("XLR-Kabel 10 m", make_product("K-010")), 428)
        self.url = reverse("material:audit")

    def test_the_id_field_takes_every_form_of_an_id(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('<a href="/material/audit/" aria-current="page">Audit</a>', page)
        self.assertIn('id="audit-id" name="id" value="" autocomplete="off" required', page)
        self.assertIn('aria-describedby="audit-id-help" autofocus>', page)
        self.assertIn("In dieser Runde noch nichts geprüft.", page)
        for typed in (
            "0427",
            "427",
            "#0427",
            " # 0427 ",
            "https://rentalars.example/m/0427",
            "https://equip.example/id/0427?x=1",
        ):
            with self.subTest(typed=typed):
                shown = self.assert_ok(self.client.get(self.url, {"id": typed}))
                self.assertIn(">0427</a> Shure SM58</h2>", shown)
                # The next field has the focus: Enter records "in order" (the field belongs to its form).
                self.assertIn('id="audit-next" name="next" maxlength="200" autofocus', shown)
                self.assertNotIn('aria-describedby="audit-id-help" autofocus>', shown)
        unknown = self.client.get(self.url, {"id": "0999"})
        self.assertEqual(self.messages_of(unknown), ["Es gibt kein Exemplar mit der ID 0999."])
        self.assertIn('value="0999"', self.assert_ok(unknown))
        text = self.client.get(self.url, {"id": "Rack"})
        self.assertEqual(self.messages_of(text), ["„Rack“ ist keine gültige ID."])

    def test_in_order_then_the_next_id(self) -> None:
        shown = self.client.get(self.url, {"id": "0427"})
        page = self.assert_ok(shown)
        # Plain forms, no page script needed.
        item_part = page[page.index('class="panel audit-item"') : page.index('id="audit-round-title"')]
        self.assertNotIn("hx-", item_part)
        self.assertEqual(item_part.count('method="post" action="/material/audit/"'), 2)
        # Enter in the empty field: "in order", back to the ID field.
        response = self.client.post(self.url, form_data(shown, containing="next"), follow=True)
        self.assertRedirects(response, self.url)
        self.assertEqual(self.messages_of(response), ["0427 geprüft: in Ordnung."])
        audit = self.microphone.audits.get()
        self.assertEqual((audit.result, audit.audited_by), (AuditResult.OK, self.admin_user))
        page = self.assert_ok(response)
        self.assertIn('aria-describedby="audit-id-help" autofocus>', page)
        round_part = page[page.index('id="audit-round-title"') :]
        self.assertIn(">0427</a>", round_part)
        self.assertIn('<span class="badge green">in Ordnung</span>', round_part)
        # With an ID in the field: recorded, and the next item is shown at once.
        shown = self.client.get(self.url, {"id": "0427"})
        response = self.client.post(self.url, form_data(shown, containing="next", next="428"))
        self.assertRedirects(response, f"{self.url}?id=428", fetch_redirect_response=False)
        self.assertEqual(self.microphone.audits.count(), 2)
        self.assertIn(">0428</a> XLR-Kabel 10 m</h2>", self.assert_ok(self.client.get(response.url)))
        # The item audited again moves up; the list holds it once.
        page = self.assert_ok(self.client.get(self.url))
        self.assertEqual(page[page.index('id="audit-round-title"') :].count(">0427</a>"), 1)

    def test_quick_picks_free_text_and_to_dos_done(self) -> None:
        old = audits.add_todo(self.cable, "Stecker locker", user=self.admin_user)
        shown = self.client.get(self.url, {"id": "428"})
        page = self.assert_ok(shown)
        for pick in ("Label fehlt", "Klett fehlt", "Beschädigt", "Reinigen", "Teile fehlen"):
            self.assertIn(f'<input type="checkbox" name="todo" value="{pick}"><span>{pick}</span>', page)
        self.assertIn(f'name="done" value="{old.pk}"', page)
        data = form_data(
            shown, containing="todo_text", todo=["Klett fehlt", "Label fehlt"], todo_text="Mantel eingerissen"
        )
        data["done"] = [str(old.pk)]
        data["note"] = "Rolle 3"
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(self.messages_of(response), ["0428 geprüft: mit To-Dos."])
        audit = self.cable.audits.get()
        self.assertEqual((audit.result, audit.note), (AuditResult.TODOS, "Rolle 3"))
        self.assertEqual(
            sorted(audit.todos.values_list("text", flat=True)), ["Klett fehlt", "Label fehlt", "Mantel eingerissen"]
        )
        old.refresh_from_db()
        self.assertFalse(old.is_open)
        self.assertIn("3 To-Dos", self.assert_ok(response))
        # "Audit speichern" without anything ticked: in order.
        shown = self.client.get(self.url, {"id": "427"})
        self.client.post(self.url, form_data(shown, containing="todo_text"))
        self.assertEqual(self.microphone.audits.get().result, AuditResult.OK)

    def test_a_new_round(self) -> None:
        audits.record_audit(self.microphone, user=self.admin_user)
        shown = self.client.get(self.url, {"id": "427"})
        self.client.post(self.url, form_data(shown, containing="next"))
        self.assertIn("Neue Runde", self.assert_ok(self.client.get(self.url)))
        response = self.client.post(self.url, {"action": "new_round"}, follow=True)
        self.assertEqual(self.messages_of(response), ["Eine neue Runde beginnt."])
        self.assertIn("In dieser Runde noch nichts geprüft.", self.assert_ok(response))

    def test_only_for_who_may_change_the_material(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertNotIn(f'href="{self.url}"', self.assert_ok(reader.get(reverse("material:item_list"))))
        self.assertEqual(reader.get(self.url).status_code, 403)
        self.assertEqual(reader.post(self.url, {"item": self.microphone.pk, "action": "ok"}).status_code, 403)
        self.assertFalse(ItemAudit.objects.exists())
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.post(self.url, {"item": self.microphone.pk, "action": "ok"}).status_code, 302)


class ItemBoxTests(UiTestCase):
    """The box "Audit und To-Dos" on the page of an item, the badges in its head, its history."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_item(make_model("XLR-Kabel 10 m", make_product("K-010")), 428)
        self.url = reverse("material:item_detail", args=[self.cable.pk])

    def test_last_and_next_audit_and_quick_picks(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('<h2 id="audit-box-title">Audit und To-Dos</h2>', page)
        self.assertIn('<dt>Letztes Audit</dt>\n<dd><span class="muted">nie</span></dd>', page)
        self.assertIn('<span class="badge green">01.03.2029</span>', page)
        self.assertIn(f'href="{reverse("material:audit")}?id=0428"', page)
        self.assertIn('<button class="btn secondary small" type="submit" name="pick" value="Klett fehlt">', page)
        self.assertIn("Keine offenen To-Dos.", page)

    def test_noting_and_ticking_done(self) -> None:
        add = reverse("material:item_todo_add", args=[self.cable.pk])
        response = self.client.post(add, {"text": "", "pick": "Klett fehlt"}, follow=True)
        self.assertRedirects(response, f"{self.url}#audit")
        self.assertEqual(self.messages_of(response), ["To-Do notiert: Klett fehlt"])
        self.client.post(add, {"text": "  Stecker   locker "})
        self.assertEqual(self.client.post(add, {"text": " "}).status_code, 302)
        todos = list(self.cable.todos.all())
        self.assertEqual([todo.text for todo in todos], ["Klett fehlt", "Stecker locker"])
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn(f'<a class="badge yellow" href="{self.url}#audit">2 To-Dos</a>', page)
        self.assertIn("<strong>Klett fehlt</strong>", page)
        response = self.client.post(reverse("material:todo_done", args=[todos[0].pk]), follow=True)
        self.assertEqual(self.messages_of(response), ["To-Do erledigt: Klett fehlt"])
        page = self.assert_ok(response)
        self.assertIn(f'<a class="badge yellow" href="{self.url}#audit">1 To-Do</a>', page)
        self.assertIn("<del>Klett fehlt</del>", page)
        history = self.assert_ok(self.client.get(reverse("material:item_history", args=[self.cable.pk])))
        self.assertIn("To-Do notiert: Klett fehlt", history)
        self.assertIn("To-Do erledigt: Klett fehlt", history)

    def test_audit_due_in_the_head_and_the_audits_so_far(self) -> None:
        created(self.cable, at(1, 8, year=2024))
        page = self.assert_ok(self.client.get(reverse("material:item_inspections", args=[self.cable.pk])))
        self.assertIn("Audit fällig</a>", page)
        audits.record_audit(self.cable, todos=["Label fehlt"], note="Halle 2", user=self.admin_user)
        page = self.assert_ok(self.client.get(self.url))
        self.assertNotIn("Audit fällig</a>", page)
        self.assertIn("Bisherige Audits", page)
        self.assertIn('<span class="badge yellow">mit To-Dos</span>', page)
        self.assertIn("im Audit", page)

    def test_bulk_material_and_archived_items_are_never_due(self) -> None:
        cable_ties = make_item(make_model("Kabelbinder", make_product("S-001"), bulk=True), 900, quantity=100)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[cable_ties.pk])))
        self.assertIn('<span class="muted">nie – Mengenmaterial</span>', page)
        self.cable.status = ItemStatus.RETIRED
        self.cable.save()
        self.assertIn("nie – das Exemplar ist archiviert", self.assert_ok(self.client.get(self.url)))
        shown = self.assert_ok(self.client.get(reverse("material:audit"), {"id": "0428"}))
        self.assertIn(
            "Dieses Exemplar ist archiviert. Es braucht kein Audit; erfassen lässt sich trotzdem eines.", shown
        )
        set_interval(0)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[cable_ties.pk])))
        self.assertIn("nie – Audits sind ausgeschaltet", page)

    def test_readers_see_the_box_without_forms(self) -> None:
        todo = audits.add_todo(self.cable, "Label fehlt")
        reader = self.browser_for("rita", "Nur-Lesen")
        page = self.assert_ok(reader.get(self.url))
        self.assertIn("<strong>Label fehlt</strong>", page)
        self.assertNotIn(reverse("material:item_todo_add", args=[self.cable.pk]), page)
        self.assertNotIn(reverse("material:todo_done", args=[todo.pk]), page)
        self.assertEqual(reader.post(reverse("material:todo_done", args=[todo.pk])).status_code, 403)
        self.assertEqual(
            reader.post(reverse("material:item_todo_add", args=[self.cable.pk]), {"text": "x"}).status_code, 403
        )
        todo.refresh_from_db()
        self.assertTrue(todo.is_open)


class OpenPointsTests(UiTestCase):
    """The tab "Ohne Produkt" became "Offene Punkte": material without product, material with to-do, audit due."""

    def setUp(self) -> None:
        super().setUp()
        self.microphone = make_item(make_model("Shure SM58", make_product("T-010")), 427)
        self.cable = make_item(make_model("XLR-Kabel 10 m", make_product("K-010")), 428)
        self.rack = make_item(make_model("Rack 19 Zoll"), 500)

    def test_the_tab_and_its_sub_tabs(self) -> None:
        items = self.assert_ok(self.client.get(reverse("material:item_list")))
        # MAT-070 (tests/unit/test_093_material_small.py): the tab shows the sum of its sub-tabs.
        self.assertIn('<a href="/material/open-points/">Offene Punkte <span class="badge accent">1</span></a>', items)
        self.assertNotIn("Ohne Produkt", items)
        self.assertIn('<a href="/material/open-points/">Anzeigen</a>', items)  # "1 Exemplar hat kein Produkt …"
        page = self.assert_ok(self.client.get(reverse("material:open_without_product")))
        self.assertIn(
            '<a href="/material/open-points/" aria-current="page">Offene Punkte <span class="badge accent">1</span></a>',
            page,
        )
        self.assertIn(
            '<a href="/material/open-points/" aria-current="page">Material ohne Produkt <span class="badge accent">1'
            "</span></a>",
            page,
        )
        self.assertIn(">0500<", page)
        self.assertNotIn(">0427<", page)
        self.assertIn('<a href="/material/open-points/to-dos/">Material mit To-Do</a>', page)
        self.assertIn('<a href="/material/open-points/audits/">Audit fällig</a>', page)
        # The filters keep to the sub-tab.
        self.assertNotIn(
            ">0500<", self.assert_ok(self.client.get(reverse("material:open_without_product"), {"q": "Shure"}))
        )

    def test_material_with_to_do(self) -> None:
        label = audits.add_todo(self.microphone, "Label fehlt", user=self.admin_user)
        velcro = audits.add_todo(self.cable, "Klett fehlt", user=self.admin_user)
        cable_label = audits.add_todo(self.cable, "Label fehlt", user=self.admin_user)
        audits.complete_todo(audits.add_todo(self.rack, "Reinigen"), user=self.admin_user)  # done
        retired = make_item(make_model("Altes Pult"), 600)
        audits.add_todo(retired, "Entsorgen")
        retired.status = ItemStatus.RETIRED
        retired.save()
        url = reverse("material:open_todos")
        page = self.assert_ok(self.client.get(url))
        self.assertIn('Material mit To-Do <span class="badge accent">3</span>', page)
        for text in ("Label fehlt", "Klett fehlt"):
            self.assertIn(f'<td data-label="To-Do">{text}</td>', page)
        self.assertNotIn("Reinigen</td>", page)
        self.assertNotIn("Entsorgen", page)
        self.assertIn('name="todos"', page)
        # Filters, groups and CSV of the standard tables.
        only_labels = self.assert_ok(self.client.get(url, {"todo": "Label fehlt"}))
        self.assertNotIn(">Klett fehlt</td>", only_labels)
        self.assertNotIn(">Klett fehlt</td>", self.assert_ok(self.client.get(url, {"q": "0427"})))
        grouped = self.assert_ok(self.client.get(url, {"group": "todo"}))
        self.assertIn('<tr class="table-group">', grouped)
        response = self.client.get(url, {"format": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        csv = response.content.decode()
        self.assertIn("ID;Artikelname;To-Do;Notiert;Notiert von", csv)
        self.assertIn("0427;Shure SM58;Label fehlt;01.03.2027 08:00;admin", csv)
        # Ticked and marked done together.
        response = self.client.post(
            reverse("material:todos_done"), {"todos": [label.pk, cable_label.pk], "next": f"{url}?todo=Label+fehlt"}
        )
        self.assertRedirects(response, f"{url}?todo=Label+fehlt", fetch_redirect_response=False)
        self.assertEqual(list(audits.open_todos()), [velcro])
        self.assertEqual(self.messages_of(self.client.get(response.url)), ["2 To-Dos erledigt."])

    def test_audit_due(self) -> None:
        created(self.microphone, at(1, 8, year=2023))
        created(self.cable, at(1, 8, year=2024))
        audits.add_todo(self.cable, "Klett fehlt")
        url = reverse("material:open_audits")
        page = self.assert_ok(self.client.get(url))
        self.assertIn('Audit fällig <span class="badge accent">2</span>', page)
        self.assertIn("Ein Exemplar ist 24 Monate nach seinem letzten Audit fällig", page)
        self.assertLess(page.index(">0427<"), page.index(">0428<"))  # oldest first
        self.assertNotIn(">0500<", page)
        self.assertIn(f'href="{reverse("material:audit")}?id=0427"', page)
        self.assertIn('<span class="badge red">01.03.2025</span>', page)
        csv = self.client.get(url, {"format": "csv"}).content.decode()
        self.assertIn("ID;Artikelname;Letztes Audit;Fällig seit;Offene To-Dos", csv)
        self.assertIn("0428;XLR-Kabel 10 m;;01.03.2026;1", csv)
        self.assertNotIn("Aktionen", csv)
        set_interval(0)
        off = self.assert_ok(self.client.get(url))
        self.assertIn("Audits sind ausgeschaltet: Kein Audit wird fällig.", off)
        self.assertNotIn(">0427<", off)

    def test_rights(self) -> None:
        todo = audits.add_todo(self.cable, "Klett fehlt")
        created(self.cable, at(1, 8, year=2024))
        reader = self.browser_for("rita", "Nur-Lesen")
        todos = self.assert_ok(reader.get(reverse("material:open_todos")))
        self.assertIn(">Klett fehlt</td>", todos)
        self.assertNotIn('name="todos"', todos)
        due = self.assert_ok(reader.get(reverse("material:open_audits")))
        self.assertIn(">0428<", due)
        self.assertNotIn(f'href="{reverse("material:audit")}?id=0428"', due)
        self.assertEqual(reader.post(reverse("material:todos_done"), {"todos": [todo.pk]}).status_code, 403)
        Role.objects.create(name="Nur Produkte", module_levels={"products": 1})
        seller = self.browser_for("vera", "Nur Produkte")
        for name in ("open_without_product", "open_todos", "open_audits"):
            self.assertEqual(seller.get(reverse(f"material:{name}")).status_code, 403, name)
        self.assertEqual(seller.get(reverse("material:open_todos"), {"format": "csv"}).status_code, 403)


class AuditApiTests(ApiTestCase):
    """API-002: every operation of the audits through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.microphone = make_item(make_model("Shure SM58", make_product("T-010")), 427)
        self.cable = make_item(make_model("XLR-Kabel 10 m", make_product("K-010")), 428)

    def test_audits_of_an_item(self) -> None:
        url = f"{API}/material-items/{self.cable.pk}/audits"
        state = self.admin.get(url).json()
        self.assertEqual(
            (state["last_audit"], state["next_audit"], state["audit_due"], state["audits"]),
            (None, "2029-03-01", False, []),
        )
        response = self.admin.post(url, {}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["result"], "ok")
        found = self.admin.post(
            url, {"todos": ["Klett fehlt", "klett fehlt", ""], "note": "Rolle 3"}, format="json"
        ).json()
        self.assertEqual((found["result"], [todo["text"] for todo in found["todos"]]), ("todos", ["Klett fehlt"]))
        paper = self.admin.post(url, {"audited_at": "2026-05-04T10:00:00+02:00"}, format="json")
        self.assertEqual(paper.status_code, 201, paper.content)
        state = self.admin.get(url).json()
        self.assertEqual(len(state["audits"]), 3)
        self.assertEqual(state["next_audit"], "2029-03-01")
        future = self.admin.post(url, {"audited_at": "2030-01-01T10:00:00+01:00"}, format="json")
        self.assert_error(future, 400, "validation_error", "audited_at")
        self.assert_error(self.admin.post(url, {"todos": "Klett"}, format="json"), 400, "validation_error")

    def test_to_dos(self) -> None:
        url = f"{API}/material-items/{self.cable.pk}/todos"
        created_todo = self.admin.post(url, {"text": "Label fehlt"}, format="json")
        self.assertEqual(created_todo.status_code, 201, created_todo.content)
        todo = created_todo.json()
        self.assertEqual((todo["text"], todo["is_open"], todo["display_id"]), ("Label fehlt", True, "0428"))
        self.assert_error(self.admin.post(url, {"text": " "}, format="json"), 400, "validation_error", "text")
        self.admin.post(f"{API}/material-items/{self.microphone.pk}/todos", {"text": "Reinigen"}, format="json")
        done = self.admin.post(f"{url}/{todo['id']}/done")
        self.assertEqual(done.status_code, 200, done.content)
        self.assertFalse(done.json()["is_open"])
        self.assertEqual(
            self.admin.post(f"{API}/material-items/{self.microphone.pk}/todos/{todo['id']}/done").status_code, 404
        )
        self.assertEqual([row["text"] for row in self.admin.get(url, {"open": "false"}).json()], ["Label fehlt"])
        self.assertEqual(self.admin.get(url, {"open": "true"}).json(), [])
        everything = self.admin.get(f"{API}/material-todos").json()
        self.assertEqual([row["text"] for row in everything], ["Reinigen"])
        self.assertEqual(
            [row["text"] for row in self.admin.get(f"{API}/material-todos", {"open": "false"}).json()], ["Label fehlt"]
        )
        self.assertEqual(self.admin.get(f"{API}/material-todos", {"q": "0428"}).json(), [])
        self.assertEqual(len(self.admin.get(f"{API}/material-todos", {"text": "Reinigen"}).json()), 1)

    def test_due_audits_and_the_fields_of_items(self) -> None:
        created(self.microphone, at(1, 8, year=2024))
        ItemTodo.objects.create(item=self.microphone, text="Label fehlt")
        due = self.admin.get(f"{API}/material-audits/due").json()
        self.assertEqual(
            due,
            [
                {
                    "item": self.microphone.pk,
                    "display_id": "0427",
                    "name": "Shure SM58",
                    "last_audit": None,
                    "next_audit": "2026-03-01",
                    "open_todos": 1,
                }
            ],
        )
        items = {row["display_id"]: row for row in self.admin.get(f"{API}/material-items").json()["results"]}
        self.assertEqual(
            (items["0427"]["audit_due"], items["0427"]["next_audit"], items["0427"]["open_todos"]),
            (True, "2026-03-01", 1),
        )
        self.assertEqual((items["0428"]["audit_due"], items["0428"]["last_audit"]), (False, None))
        only_due = self.admin.get(f"{API}/material-items", {"audit_due": "true"}).json()["results"]
        self.assertEqual([row["display_id"] for row in only_due], ["0427"])
        not_due = self.admin.get(f"{API}/material-items", {"audit_due": "false"}).json()["results"]
        self.assertEqual([row["display_id"] for row in not_due], ["0428"])
        with_todos = self.admin.get(f"{API}/material-items", {"open_todos": "true"}).json()["results"]
        self.assertEqual([row["display_id"] for row in with_todos], ["0427"])
        single = self.admin.get(f"{API}/material-items/{self.cable.pk}").json()
        self.assertEqual((single["next_audit"], single["open_todos"]), ("2029-03-01", 0))

    def test_settings(self) -> None:
        url = f"{API}/audit-settings"
        self.assertEqual(self.admin.get(url).json()["interval_months"], 24)
        changed = self.admin.patch(url, {"interval_months": 12, "quick_todos": "Label fehlt\nNetzteil"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["quick_todo_list"], ["Label fehlt", "Netzteil"])
        too_many = "\n".join(f"Punkt {number}" for number in range(13))
        self.assert_error(self.admin.patch(url, {"quick_todos": too_many}, format="json"), 400, "validation_error")
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(warehouse.get(url).status_code, 403)

    def test_rights(self) -> None:
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(f"{API}/material-items/{self.cable.pk}/audits").status_code, 200)
        self.assertEqual(reader.get(f"{API}/material-todos").status_code, 200)
        self.assertEqual(
            reader.post(f"{API}/material-items/{self.cable.pk}/audits", {}, format="json").status_code, 403
        )
        self.assertEqual(
            reader.post(f"{API}/material-items/{self.cable.pk}/todos", {"text": "x"}, format="json").status_code, 403
        )
        todo = ItemTodo.objects.create(item=self.cable, text="Label fehlt")
        self.assertEqual(reader.post(f"{API}/material-items/{self.cable.pk}/todos/{todo.pk}/done").status_code, 403)
        Role.objects.create(name="Nur Produkte", module_levels={"products": 1})
        seller = self.client_for("vera", "Nur Produkte")
        self.assertEqual(seller.get(f"{API}/material-audits/due").status_code, 403)
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(
            warehouse.post(f"{API}/material-items/{self.cable.pk}/audits", {}, format="json").status_code, 201
        )
