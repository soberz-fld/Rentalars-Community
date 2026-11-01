# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom fields of material items (MAT-071, MAT-072, MAT-073).

The requirement: custom fields for models.

* Einstellungen → Eigene Felder: definitions with a type (text, long text,
  number with unit, date, yes/no, choice list, web and e-mail address), an
  optional check pattern, a help text and the marks "in lists", "unique" and
  "only with the right to see purchase prices"; Feldsätze group them, each
  field required or optional, in an order.
* A material model gets at most one fieldset; every item of the model has
  its fields with values of its own – in the forms "Neue Exemplare" (also as
  a duplicate) and "Exemplar bearbeiten", on the item page, in the history.
* Fields marked "in lists" are columns of the item list – sorted, filtered,
  in the CSV file; the item search finds values; the import reads columns
  named like a field; the API reads and writes everything.
* The category-specific fields (MAT-009, MAT-010) stay as they are.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, Rights
from rentalars.core.audit import acting_as
from rentalars.customfields import services
from rentalars.customfields.models import (
    CustomField,
    CustomFieldValue,
    Fieldset,
    FieldsetEntry,
    FieldType,
    ModelFieldset,
)
from rentalars.material.filters import search_items
from rentalars.material.history import item_history
from rentalars.material.importer import import_material, read_table, resolve_mapping
from rentalars.material.models import MaterialItem, MaterialModel
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_item, make_items, make_model, make_user
from tests.ui.base import UiTestCase, form_data


def make_field(name: str, field_type: str = FieldType.TEXT, **values: Any) -> CustomField:
    """A custom field, checked as the form checks it."""
    field = CustomField(name=name, field_type=field_type, **values)
    field.full_clean()
    field.save()
    return field


def make_fieldset(name: str, *fields: CustomField, required: tuple[CustomField, ...] = ()) -> Fieldset:
    """A fieldset with the fields in this order; ``required`` ones are required."""
    fieldset = Fieldset.objects.create(name=name)
    for position, field in enumerate(fields, start=1):
        FieldsetEntry.objects.create(fieldset=fieldset, field=field, position=position, is_required=field in required)
    return fieldset


def role(name: str, levels: dict[str, int], *special: str) -> Role:
    """A role with module levels and special rights."""
    return Role.objects.create(
        name=name, module_levels={str(k): int(v) for k, v in levels.items()}, special_rights=list(special)
    )


def user_with(username: str, role_obj: Role) -> Any:
    """A user with one role."""
    user = make_user(username)
    user.roles.set([role_obj])
    return user


class NetworkSetup:
    """A switch model with the fieldset "Netzwerkgerät": MAC address (required, unique, pattern), firmware, ports."""

    def build(self) -> None:
        self.mac = make_field(
            "MAC-Adresse",
            pattern=r"[0-9A-F]{2}(:[0-9A-F]{2}){5}",
            help_text="Sechs Hex-Paare mit Doppelpunkt",
            is_unique=True,
            show_in_lists=True,
        )
        self.firmware = make_field("Firmware", show_in_lists=True)
        self.ports = make_field("Ports", FieldType.NUMBER, unit="Stk", show_in_lists=True)
        self.checked = make_field("Prüfplakette bis", FieldType.DATE)
        self.value = make_field("Versicherungswert", FieldType.NUMBER, unit="€", is_sensitive=True, show_in_lists=True)
        self.fieldset = make_fieldset(
            "Netzwerkgerät",
            self.mac,
            self.firmware,
            self.ports,
            self.checked,
            self.value,
            required=(self.mac,),
        )
        self.model = make_model("Switch 24 Port")
        services.assign_fieldset(self.model, self.fieldset)


# --- Values ---------------------------------------------------------------------------------------------


class ValueRuleTests(RentalarsTestCase):
    """Every type checks and stores its values in one canonical form; people read them formatted."""

    def test_number_with_unit(self) -> None:
        field = make_field("Länge", FieldType.NUMBER, unit="m")
        self.assertEqual(field.clean_value("12,5"), "12.5")
        self.assertEqual(field.clean_value("12.50 m"), "12.5")
        self.assertEqual(field.clean_value("1.234,5"), "1234.5")
        self.assertEqual(field.clean_value(Decimal("100.00")), "100")
        self.assertEqual(field.clean_value(3), "3")
        self.assertEqual(field.display_value("12.5"), "12,5 m")
        self.assertEqual(field.typed_value("12.5"), Decimal("12.5"))
        self.assertEqual(field.label_with_unit, "Länge (m)")
        with self.assertRaises(ValidationError) as caught:
            field.clean_value("lang")
        self.assertIn("„lang“ ist keine Zahl für das Feld Länge.", caught.exception.messages)

    def test_date_yes_no_choice(self) -> None:
        date = make_field("Prüfung", FieldType.DATE)
        self.assertEqual(date.clean_value("01.03.2027"), "2027-03-01")
        self.assertEqual(date.clean_value("2027-03-01"), "2027-03-01")
        self.assertEqual(date.display_value("2027-03-01"), "01.03.2027")
        with self.assertRaises(ValidationError):
            date.clean_value("morgen")
        flag = make_field("Mit Netzteil", FieldType.BOOLEAN)
        self.assertEqual([flag.clean_value(word) for word in ("ja", "x", "true", True)], ["yes"] * 4)
        self.assertEqual([flag.clean_value(word) for word in ("nein", "0", False)], ["no"] * 3)
        self.assertEqual(flag.display_value("yes"), "ja")
        self.assertIs(flag.typed_value("no"), False)
        with self.assertRaises(ValidationError):
            flag.clean_value("vielleicht")
        choice = make_field("Stecker", FieldType.CHOICE, choices=["Schuko", "CEE 16A"])
        self.assertEqual(choice.clean_value("cee 16a"), "CEE 16A")
        with self.assertRaises(ValidationError) as caught:
            choice.clean_value("Powercon")
        self.assertIn("Schuko, CEE 16A", caught.exception.messages[0])

    def test_addresses_text_and_pattern(self) -> None:
        url = make_field("Handbuch", FieldType.URL)
        self.assertEqual(url.clean_value("example.com/handbuch.pdf"), "https://example.com/handbuch.pdf")
        with self.assertRaises(ValidationError):
            url.clean_value("kein link")
        mail = make_field("Hersteller-Support", FieldType.EMAIL)
        self.assertEqual(mail.clean_value(" support@example.com "), "support@example.com")
        with self.assertRaises(ValidationError):
            mail.clean_value("support(at)example")
        text = make_field("Notiz kurz")
        self.assertEqual(text.clean_value("  zwei\n Zeilen "), "zwei Zeilen")
        with self.assertRaises(ValidationError):
            text.clean_value("x" * 251)
        long = make_field("Beschreibung lang", FieldType.LONG_TEXT)
        self.assertEqual(long.clean_value("a\r\nb"), "a\nb")
        mac = make_field("MAC", pattern=r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", help_text="Sechs Hex-Paare")
        self.assertEqual(mac.clean_value("00:1A:2B:3C:4D:5E"), "00:1A:2B:3C:4D:5E")
        with self.assertRaises(ValidationError) as caught:
            mac.clean_value("00-1A")
        self.assertEqual(caught.exception.messages, ["„00-1A“ hat nicht das Format des Feldes MAC. Sechs Hex-Paare"])

    def test_definitions_are_checked(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            make_field("Leer", FieldType.CHOICE)
        self.assertIn("choices", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            make_field("Kaputt", pattern="[a-")
        self.assertIn("pattern", caught.exception.message_dict)
        field = make_field("Nur Text", unit="m", choices=["a"], pattern="")
        self.assertEqual((field.unit, field.choices), ("", []))  # only numbers have a unit, only choice lists options
        for name in ("Nur Text", "nur text"):  # imports and the API find a field by its name, whatever the case
            with self.assertRaises(ValidationError) as caught:
                make_field(name)
            self.assertEqual(
                caught.exception.message_dict["name"], ["Ein eigenes Feld mit diesem Namen gibt es schon."]
            )


class DefinitionChangeTests(RentalarsTestCase, NetworkSetup):
    """A changed definition must fit the values items have; deleting asks about values."""

    def setUp(self) -> None:
        super().setUp()
        self.build()
        self.items = make_items(self.model, 2)

    def test_type_change_must_fit_the_values(self) -> None:
        services.store_values(self.items[0], {self.firmware: "1.2b"})
        self.firmware.field_type = FieldType.NUMBER
        with self.assertRaises(ValidationError) as caught:
            self.firmware.full_clean()
        self.assertIn("„1.2b“", caught.exception.messages[0])
        services.store_values(self.items[0], {self.firmware: "1,50"})
        self.firmware.full_clean()
        self.firmware.save()
        # The stored text follows the new type.
        self.assertEqual(CustomFieldValue.objects.get(field=self.firmware).value, "1.5")

    def test_unique_needs_different_values(self) -> None:
        for item in self.items:
            services.store_values(item, {self.firmware: "2.0"})
        self.firmware.is_unique = True
        with self.assertRaises(ValidationError) as caught:
            self.firmware.full_clean()
        self.assertIn("is_unique", caught.exception.message_dict)

    def test_sensitive_values_move_with_the_mark(self) -> None:
        services.store_values(self.items[0], {self.firmware: "2.0"})
        self.firmware.is_sensitive = True
        self.firmware.full_clean()
        self.firmware.save()
        row = CustomFieldValue.objects.get(field=self.firmware)
        self.assertEqual((row.value, row.protected_value), ("", "2.0"))
        self.assertFalse(search_items(MaterialItem.objects.all(), "2.0").exists())  # protected values are not searched

    def test_delete_field_asks_about_values(self) -> None:
        services.store_values(self.items[0], {self.firmware: "2.0"})
        with self.assertRaises(ValidationError) as caught:
            services.delete_field(self.firmware, with_values=False)
        self.assertIn("1 Exemplar hat einen Wert im Feld „Firmware“", caught.exception.messages[0])
        self.assertEqual(services.delete_field(self.firmware, with_values=True), 1)
        self.assertFalse(CustomField.objects.filter(name="Firmware").exists())
        self.assertFalse(FieldsetEntry.objects.filter(fieldset=self.fieldset, field__name="Firmware").exists())
        self.assertEqual(services.delete_field(self.checked, with_values=False), 0)

    def test_a_fieldset_in_use_stays(self) -> None:
        with self.assertRaises(ValidationError):
            services.delete_fieldset(self.fieldset)
        services.assign_fieldset(self.model, None)
        services.delete_fieldset(self.fieldset)
        self.assertFalse(Fieldset.objects.exists())
        self.assertTrue(CustomField.objects.filter(name="Firmware").exists())


# --- Settings pages -------------------------------------------------------------------------------------


class SettingsPageTests(UiTestCase):
    """Einstellungen → Eigene Felder and Feldsätze: list, create, edit, delete – for who manages master data."""

    def test_settings_lead_to_the_pages(self) -> None:
        text = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(reverse("customfields:field_list"), text)
        self.assertIn("Eigene Felder", text)
        self.assertIn("Feldsätze", text)

    def test_create_change_and_delete_a_field(self) -> None:
        page = self.client.get(reverse("customfields:field_create"))
        text = self.assert_ok(page)
        self.assertIn("Neues eigenes Feld", text)
        self.assertIn("In Listen als Spalte wählbar", text)
        self.assertIn('class="required"', text)  # the name is marked as required (UIX-035)
        data = form_data(page, containing="name", name="Kabellänge", field_type="number", unit="m", show_in_lists="on")
        response = self.client.post(reverse("customfields:field_create"), data)
        self.assertRedirects(response, reverse("customfields:field_list"))
        field = CustomField.objects.get(name="Kabellänge")
        self.assertEqual((field.field_type, field.unit, field.show_in_lists), ("number", "m", True))
        listing = self.assert_ok(self.client.get(reverse("customfields:field_list")))
        self.assertIn("Kabellänge", listing)
        self.assertIn("Zahl mit Einheit (m)", listing)
        # A choice list without options is refused at the options.
        edit = self.client.get(reverse("customfields:field_edit", args=[field.pk]))
        refused = self.client.post(
            reverse("customfields:field_edit", args=[field.pk]),
            form_data(edit, containing="name", field_type="choice", options=""),
        )
        self.assertContains(refused, "Eine Auswahlliste braucht mindestens einen Auswahlwert.")
        saved = self.client.post(
            reverse("customfields:field_edit", args=[field.pk]),
            form_data(edit, containing="name", field_type="choice", options="Schuko\nCEE 16A\n"),
        )
        self.assertRedirects(saved, reverse("customfields:field_list"))
        field.refresh_from_db()
        self.assertEqual(field.choices, ["Schuko", "CEE 16A"])
        response = self.client.post(reverse("customfields:field_delete", args=[field.pk]))
        self.assertRedirects(response, reverse("customfields:field_list"))
        self.assertFalse(CustomField.objects.exists())

    def test_deleting_a_field_with_values_needs_the_tick(self) -> None:
        field = make_field("Firmware")
        model = make_model("Switch")
        services.assign_fieldset(model, make_fieldset("Netz", field))
        item = make_items(model, 1)[0]
        services.store_values(item, {field: "1.0"})
        page = self.assert_ok(self.client.get(reverse("customfields:field_edit", args=[field.pk])))
        self.assertIn("Den Wert von 1 Exemplar mitlöschen", page)
        refused = self.client.post(reverse("customfields:field_delete", args=[field.pk]), follow=True)
        self.assertIn("Wer das Feld löscht, löscht auch diesen Wert", self.messages_of(refused)[0])
        self.assertTrue(CustomField.objects.exists())
        done = self.client.post(
            reverse("customfields:field_delete", args=[field.pk]), {"with_values": "1"}, follow=True
        )
        self.assertIn("Das eigene Feld „Firmware“ und der Wert von 1 Exemplar sind gelöscht.", self.messages_of(done))
        self.assertFalse(CustomFieldValue.objects.exists())

    def test_create_and_edit_a_fieldset(self) -> None:
        mac, firmware = make_field("MAC-Adresse"), make_field("Firmware")
        page = self.client.get(reverse("customfields:fieldset_create"))
        self.assert_ok(page)
        data = form_data(
            page,
            containing="name",
            name="Netzwerkgerät",
            **{f"use_{mac.pk}": "on", f"required_{mac.pk}": "on", f"position_{mac.pk}": "2"},
            **{f"use_{firmware.pk}": "on", f"position_{firmware.pk}": "1"},
        )
        self.assertRedirects(
            self.client.post(reverse("customfields:fieldset_create"), data), reverse("customfields:fieldset_list")
        )
        fieldset = Fieldset.objects.get(name="Netzwerkgerät")
        self.assertEqual(
            [(entry.field.name, entry.is_required) for entry in fieldset.entries_in_order()],
            [("Firmware", False), ("MAC-Adresse", True)],
        )
        listing = self.assert_ok(self.client.get(reverse("customfields:fieldset_list")))
        self.assertIn("Firmware, MAC-Adresse *", listing)
        # Taking a field out deletes its entry.
        edit = self.client.get(reverse("customfields:fieldset_edit", args=[fieldset.pk]))
        self.client.post(
            reverse("customfields:fieldset_edit", args=[fieldset.pk]),
            form_data(edit, containing="name", **{f"use_{firmware.pk}": None}),
        )
        self.assertEqual([entry.field.name for entry in fieldset.entries_in_order()], ["MAC-Adresse"])
        # A fieldset a model has cannot be deleted.
        model = make_model("Switch")
        services.assign_fieldset(model, fieldset)
        refused = self.client.post(reverse("customfields:fieldset_delete", args=[fieldset.pk]), follow=True)
        self.assertIn("1 Materialmodell hat den Feldsatz „Netzwerkgerät“", " ".join(self.messages_of(refused)))
        services.assign_fieldset(model, None)
        self.client.post(reverse("customfields:fieldset_delete", args=[fieldset.pk]))
        self.assertFalse(Fieldset.objects.exists())

    def test_rights(self) -> None:
        field = make_field("Firmware")
        warehouse = self.browser_for("lager", "Lager")  # material, but no settings
        self.assertEqual(warehouse.get(reverse("customfields:field_list")).status_code, 403)
        reader = self.browser_of(user_with("leser", role("Einstellungen lesen", {Module.ADMINISTRATION: Level.READ})))
        text = self.assert_ok(reader.get(reverse("customfields:field_list")))
        self.assertNotIn("Neues eigenes Feld", text)
        self.assertNotIn(reverse("customfields:field_edit", args=[field.pk]), text)
        self.assertEqual(reader.get(reverse("customfields:field_edit", args=[field.pk])).status_code, 403)
        writer = self.browser_of(user_with("schreiber", role("Einstellungen", {Module.ADMINISTRATION: Level.WRITE})))
        self.assert_ok(writer.get(reverse("customfields:field_edit", args=[field.pk])))
        self.assertEqual(writer.post(reverse("customfields:field_delete", args=[field.pk])).status_code, 403)


# --- Material models and items --------------------------------------------------------------------------


class ModelAndItemPageTests(UiTestCase, NetworkSetup):
    """The fieldset at the model; the values in the forms and on the page of an item."""

    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_model_form_and_page(self) -> None:
        other = make_model("Router")
        page = self.client.get(reverse("material:model_edit", args=[other.pk]))
        self.assertContains(page, "Eigene Felder der Exemplare")
        data = form_data(page, containing="name", **{"cfs-fieldset": str(self.fieldset.pk)})
        self.assertRedirects(
            self.client.post(reverse("material:model_edit", args=[other.pk]), data),
            reverse("material:model_detail", args=[other.pk]),
        )
        self.assertEqual(services.fieldset_of(other), self.fieldset)
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[other.pk])))
        self.assertIn("Netzwerkgerät", detail)
        self.assertIn("MAC-Adresse", detail)
        # A copy of the model starts with its fieldset (MAT-064).
        copy = self.client.get(reverse("material:model_create") + f"?copy={other.pk}")
        self.assertEqual(form_data(copy, containing="name")["cfs-fieldset"], str(self.fieldset.pk))
        # The history of the model tells.
        self.assertTrue(ModelFieldset.objects.filter(material_model=other).exists())

    def test_one_new_item_needs_the_required_values(self) -> None:
        url = reverse("material:item_create", args=[self.model.pk])
        page = self.client.get(url)
        text = self.assert_ok(page)
        self.assertIn("Eigene Felder", text)
        self.assertIn('data-require-if="count=1"', text)  # required while one item is created
        self.assertIn('data-show-if="count=1"', text)  # the unique MAC address only for one item
        data = form_data(page, containing="count", count="1")
        refused = self.client.post(url, data)
        self.assertEqual(refused.status_code, 200)
        self.assertFalse(MaterialItem.objects.exists())
        data.update({f"cf-f{self.mac.pk}": "00:1A:2B:3C:4D:5E", f"cf-f{self.ports.pk}": "24"})
        self.assertRedirects(self.client.post(url, data), reverse("material:model_detail", args=[self.model.pk]))
        item = MaterialItem.objects.get()
        self.assertEqual(services.stored_values(item)[self.mac.pk], "00:1A:2B:3C:4D:5E")
        self.assertEqual(services.stored_values(item)[self.ports.pk], "24")

    def test_several_new_items_may_leave_required_values_empty(self) -> None:
        url = reverse("material:item_create", args=[self.model.pk])
        data = form_data(self.client.get(url), containing="count", count="3")
        data[f"cf-f{self.firmware.pk}"] = "2.1"
        data[f"cf-f{self.mac.pk}"] = "00:1A:2B:3C:4D:5E"
        refused = self.client.post(url, data)
        self.assertContains(refused, "Ein eindeutiges Feld kann nicht für mehrere Exemplare denselben Wert bekommen.")
        data[f"cf-f{self.mac.pk}"] = ""
        response = self.client.post(url, data, follow=True)
        self.assertIn("3 neuen Exemplaren fehlen Pflichtangaben eigener Felder", " ".join(self.messages_of(response)))
        items = list(MaterialItem.objects.order_by("inventory_number"))
        self.assertEqual(len(items), 3)
        self.assertTrue(all(services.stored_values(item) == {self.firmware.pk: "2.1"} for item in items))
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[items[0].pk])))
        self.assertIn("Eine Pflichtangabe fehlt: MAC-Adresse.", page)
        self.assertIn("Pflichtangabe fehlt", page)

    def test_edit_item_and_its_page_and_history(self) -> None:
        item = make_items(self.model, 1)[0]
        other = make_items(self.model, 1)[0]
        services.store_values(other, {self.mac: "AA:AA:AA:AA:AA:AA"})
        url = reverse("material:item_edit", args=[item.pk])
        page = self.client.get(url)
        data = form_data(page, containing="serial_number")
        refused = self.client.post(url, data)
        self.assertContains(refused, "Dieses Feld ist zwingend erforderlich.")
        data[f"cf-f{self.mac.pk}"] = "AA:AA:AA:AA:AA:AA"
        self.assertContains(self.client.post(url, data), "hat schon den Wert")
        data[f"cf-f{self.mac.pk}"] = "00:1A:2B:3C:4D:5E"
        data[f"cf-f{self.checked.pk}"] = "2027-06-30"
        data[f"cf-f{self.value.pk}"] = "1200,50"
        self.assertRedirects(self.client.post(url, data), reverse("material:item_detail", args=[item.pk]))
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
        self.assertIn("00:1A:2B:3C:4D:5E", detail)
        self.assertIn("30.06.2027", detail)
        self.assertIn("1200,5 €", detail)
        self.assertIn("vertraulich", detail)
        history = self.assert_ok(self.client.get(reverse("material:item_history", args=[item.pk])))
        self.assertIn("Eigenes Feld „MAC-Adresse“ eingetragen", history)
        # Changed again: old → new in the history.
        data[f"cf-f{self.mac.pk}"] = "00:1A:2B:3C:4D:5F"
        self.client.post(url, data)
        rows = item_history(item, Rights.everything())
        changed = next(row for row in rows if row.summary == "Eigenes Feld „MAC-Adresse“ geändert")
        self.assertEqual((changed.changes[0].old, changed.changes[0].new), ("00:1A:2B:3C:4D:5E", "00:1A:2B:3C:4D:5F"))

    def test_sensitive_values_need_the_purchase_price_right(self) -> None:
        item = make_items(self.model, 1)[0]
        services.store_values(item, {self.mac: "00:1A:2B:3C:4D:5E", self.value: "999"})
        no_prices = role("Lager ohne Preise", {Module.MATERIAL: Level.DELETE})
        browser = self.browser_of(user_with("ohnepreis", no_prices))
        detail = self.assert_ok(browser.get(reverse("material:item_detail", args=[item.pk])))
        self.assertIn("00:1A:2B:3C:4D:5E", detail)
        self.assertNotIn("Versicherungswert", detail)
        form = browser.get(reverse("material:item_edit", args=[item.pk]))
        data = form_data(form, containing="serial_number")
        self.assertNotIn(f"cf-f{self.value.pk}", data)
        data[f"cf-f{self.firmware.pk}"] = "3.0"
        self.assertEqual(browser.post(reverse("material:item_edit", args=[item.pk]), data).status_code, 302)
        self.assertEqual(services.stored_values(MaterialItem.objects.get(pk=item.pk))[self.value.pk], "999")  # kept
        # The history names the change of a sensitive value, not the value.
        services.store_values(item, {self.value: "1000"})
        rights = Rights(module_levels={Module.MATERIAL: Level.READ})
        row = next(row for row in item_history(item, rights) if "Versicherungswert" in row.summary)
        self.assertEqual(row.changes[0].new, "(nicht sichtbar)")
        self.assertNotIn(
            "1000", str([(change.old, change.new) for row in item_history(item, rights) for change in row.changes])
        )

    def test_duplicate_copies_the_values_but_not_the_unique_ones(self) -> None:
        item = make_items(self.model, 1)[0]
        services.store_values(item, {self.mac: "00:1A:2B:3C:4D:5E", self.firmware: "2.1"})
        page = self.client.get(reverse("material:item_create", args=[self.model.pk]) + f"?copy={item.pk}")
        data = form_data(page, containing="count")
        self.assertEqual(data[f"cf-f{self.firmware.pk}"], "2.1")
        self.assertEqual(data[f"cf-f{self.mac.pk}"], "")

    def test_values_outside_the_fieldset_stay_and_show_apart(self) -> None:
        item = make_items(self.model, 1)[0]
        services.store_values(item, {self.firmware: "2.1"})
        FieldsetEntry.objects.filter(field=self.firmware).delete()
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
        self.assertIn("Werte von Feldern, die nicht mehr zum Feldsatz gehören", detail)
        self.assertIn("2.1", detail)

    def test_the_purchase_names_items_lacking_required_values(self) -> None:
        items = make_items(self.model, 2)
        services.store_values(items[0], {self.mac: "00:1A:2B:3C:4D:5E"})
        ids = ",".join(item.display_id for item in items)
        page = self.assert_ok(self.client.get(reverse("material:purchase_done") + f"?items={ids}"))
        self.assertIn("Einem neuen Exemplar fehlt eine Pflichtangabe eigener Felder", page)
        self.assertIn(reverse("material:item_edit", args=[items[1].pk]), page)


class ItemListTests(UiTestCase, NetworkSetup):
    """Fields marked "in lists" are columns: shown, sorted, filtered, exported; the search finds values."""

    def setUp(self) -> None:
        super().setUp()
        self.build()
        self.items = make_items(self.model, 3)
        for item, ports, firmware in zip(self.items, ("8", "24", "100"), ("2.1", "1.0", "3.5"), strict=True):
            services.store_values(item, {self.ports: ports, self.firmware: firmware})
        services.store_values(self.items[0], {self.value: "500"})

    def test_column_sort_filter_and_csv(self) -> None:
        url = reverse("material:item_list")
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Ports (Stk)", page)  # offered in the chooser, not shown by default
        key = f"cf{self.ports.pk}"
        shown = self.client.get(url, {"cols": f"id,{key}", "sort": f"-{key}"})
        rows = shown.context["rows"]
        self.assertEqual([row.cells[1].html for row in rows], ["100 Stk", "24 Stk", "8 Stk"])  # numbers as numbers
        filtered = self.client.get(url, {"cols": f"id,{key}", f"cf{self.firmware.pk}": "3.5"})
        self.assertEqual([row.pk for row in filtered.context["rows"]], [self.items[2].pk])
        self.assertContains(self.client.get(url), f'name="cf{self.firmware.pk}"')  # the filter field
        csv_text = self.client.get(url, {"cols": f"id,{key},cf{self.value.pk}", "format": "csv"}).content.decode()
        self.assertIn("Ports (Stk)", csv_text)
        self.assertIn("Versicherungswert (€)", csv_text)
        self.assertIn(f"{self.items[0].display_id};8;500", csv_text)

    def test_sensitive_column_only_with_the_right(self) -> None:
        browser = self.browser_of(user_with("ohnepreis", role("Lager ohne Preise", {Module.MATERIAL: Level.READ})))
        url = reverse("material:item_list")
        page = self.assert_ok(browser.get(url))
        self.assertNotIn("Versicherungswert", page)
        csv_text = browser.get(url, {"cols": "all", "format": "csv"}).content.decode()
        self.assertNotIn("Versicherungswert", csv_text)
        self.assertIn("Ports (Stk)", csv_text)
        # Filtering by the sensitive field does nothing without the right.
        response = browser.get(url, {f"cf{self.value.pk}": "500"})
        self.assertEqual(len(response.context["rows"]), 3)

    def test_group_by_a_custom_column_and_remember_it(self) -> None:
        url = reverse("material:item_list")
        key = f"cf{self.firmware.pk}"
        page = self.assert_ok(self.client.get(url, {"cols": f"id,{key}", "group": key}))
        self.assertIn(f'<option value="{key}" selected>', page)
        # The column choice is kept like any other (UIX-015).
        self.client.post(reverse("core:table_columns", args=["material_items"]), {"columns": ["id", key], "next": url})
        shown = self.client.get(url)
        self.assertEqual([column.key for column in shown.context["table"].columns], ["id", key])

    def test_the_values_of_a_page_come_from_one_query(self) -> None:
        from django.test import RequestFactory

        from rentalars.material.tables import ITEM_TABLE

        request = RequestFactory().get(f"/material/?cols=id,cf{self.ports.pk},cf{self.firmware.pk}")
        request.user = self.admin_user
        state = ITEM_TABLE.state(request)
        items = list(MaterialItem.objects.select_related("storage_location", "installed_in__storage_location"))
        with self.assertNumQueries(1):  # the custom values of all rows (NFA-012)
            rows = state.rows(items)
        self.assertEqual([str(row.cells[2].html) for row in rows], ["8 Stk", "24 Stk", "100 Stk"])  # after "Firmware"
        make_items(self.model, 5)
        more = list(MaterialItem.objects.select_related("storage_location", "installed_in__storage_location"))
        with self.assertNumQueries(1):
            state.csv_text(more)

    def test_search_finds_values(self) -> None:
        self.assertEqual(list(search_items(MaterialItem.objects.all(), "3.5")), [self.items[2]])
        self.assertFalse(search_items(MaterialItem.objects.all(), "500").exists())  # sensitive values are not searched
        response = self.client.get(reverse("material:item_list"), {"q": "3.5"})
        self.assertEqual([row.pk for row in response.context["rows"]], [self.items[2].pk])


# --- Import ---------------------------------------------------------------------------------------------


def material(text: str, *, dry_run: bool = False, rights: Rights | None = None) -> Any:
    """Import CSV text as material and return the report."""
    data = read_table(io.BytesIO(text.encode("utf-8")), "liste.csv")
    with acting_as("system:test"):
        return import_material(data, resolve_mapping(data.headers, {}), dry_run=dry_run, rights=rights)


class ImportTests(RentalarsTestCase, NetworkSetup):
    """Columns named like a custom field fill it; wrong values are errors of their row."""

    def setUp(self) -> None:
        super().setUp()
        self.build()
        self.model.category.refresh_from_db()
        self.category = self.model.category.name

    def test_values_are_imported_and_checked(self) -> None:
        head = "ID;Artikelname;Kategorie;MAC-Adresse;Ports;Prüfplakette bis"
        report = material(f"{head}\n0042;Switch 24 Port;{self.category};00:1A:2B:3C:4D:5E;24;30.06.2027\n")
        self.assertTrue(report.ok, report.errors)
        item = MaterialItem.objects.get(inventory_number=42)
        self.assertEqual(
            services.stored_values(item),
            {self.mac.pk: "00:1A:2B:3C:4D:5E", self.ports.pk: "24", self.checked.pk: "2027-06-30"},
        )
        # A change is a change of the row (IMP-011).
        report = material(
            f"{head}\n0042;Switch 24 Port;{self.category};00:1A:2B:3C:4D:5E;48;30.06.2027\n", dry_run=True
        )
        row = report.as_dict()["rows"][0]
        self.assertEqual(row["status"], "changed")
        self.assertEqual(row["changes"][0]["label"], "Ports (eigenes Feld)")
        self.assertEqual((row["changes"][0]["old"], row["changes"][0]["new"]), ("24 Stk", "48 Stk"))
        # Wrong values are errors of their row, and nothing is imported.
        report = material(f"{head}\n0043;Switch 24 Port;{self.category};kaputt;viele;morgen\n")
        self.assertFalse(report.ok)
        self.assertEqual({issue.column for issue in report.errors}, {"MAC-Adresse", "Ports", "Prüfplakette bis"})
        self.assertFalse(MaterialItem.objects.filter(inventory_number=43).exists())
        # The unique MAC address cannot be taken twice.
        report = material(f"{head}\n0044;Switch 24 Port;{self.category};00:1A:2B:3C:4D:5E;8;\n")
        self.assertIn("hat schon den Wert", report.errors[0].message)

    def test_field_outside_the_fieldset_and_sensitive_columns(self) -> None:
        head = "ID;Artikelname;Kategorie;Firmware;Versicherungswert"
        report = material(f"{head}\n0050;Mischpult;{self.category};1.0;\n")
        self.assertFalse(report.ok)
        self.assertIn("hat kein eigenes Feld „Firmware“", report.errors[0].message)
        # An empty cell of a field outside the fieldset is fine.
        self.assertTrue(material(f"{head}\n0050;Mischpult;{self.category};;\n").ok)
        # Without the right to see purchase prices the sensitive column is left out, with a warning.
        rights = Rights(module_levels={Module.MATERIAL: Level.WRITE})
        report = material(f"{head}\n0051;Switch 24 Port;{self.category};1.0;999\n", rights=rights)
        self.assertTrue(report.ok, report.errors)
        self.assertIn("Versicherungswert", [issue.column for issue in report.warnings])
        item = MaterialItem.objects.get(inventory_number=51)
        self.assertEqual(services.stored_values(item), {self.firmware.pk: "1.0"})


class ImportPageTests(UiTestCase, NetworkSetup):
    """The import page names the columns of custom fields it reads – the sensitive ones only with the right."""

    def test_the_page_names_the_custom_columns(self) -> None:
        self.build()
        page = self.assert_ok(self.client.get(reverse("material:import")))
        self.assertIn("Eigene Felder: eine Spalte mit dem Namen des Feldes als Überschrift", page)
        self.assertIn("Firmware, MAC-Adresse, Ports, Prüfplakette bis, Versicherungswert", page)
        browser = self.browser_of(user_with("ohnepreis", role("Lager ohne Preise", {Module.MATERIAL: Level.WRITE})))
        page = self.assert_ok(browser.get(reverse("material:import")))
        self.assertIn("Firmware, MAC-Adresse, Ports, Prüfplakette bis.", page)


# --- API ------------------------------------------------------------------------------------------------


class CustomFieldApiTests(ApiTestCase, NetworkSetup):
    """API-002, API-014: definitions, fieldsets, the fieldset of a model, the values of items."""

    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_custom_field_operations(self) -> None:
        listed = self.admin.get(f"{API}/custom-fields")
        self.assertEqual(listed.status_code, 200)
        self.assertIn("MAC-Adresse", [field["name"] for field in listed.json()["results"]])
        created = self.admin.post(
            f"{API}/custom-fields",
            {"name": "Stecker", "field_type": "choice", "choices": ["Schuko", "CEE"]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        field_id = created.json()["id"]
        self.assertEqual(self.admin.get(f"{API}/custom-fields/{field_id}").json()["value_count"], 0)
        replaced = self.admin.put(
            f"{API}/custom-fields/{field_id}",
            {
                "name": "Stecker",
                "field_type": "choice",
                "choices": ["Schuko", "CEE", "Powercon"],
                "show_in_lists": True,
            },
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        patched = self.admin.patch(f"{API}/custom-fields/{field_id}", {"help_text": "Am Gerät"}, format="json")
        self.assertEqual(patched.json()["help_text"], "Am Gerät")
        refused = self.admin.post(f"{API}/custom-fields", {"name": "Leer", "field_type": "choice"}, format="json")
        self.assert_error(refused, 400, "validation_error")
        self.assertEqual(self.admin.delete(f"{API}/custom-fields/{field_id}").status_code, 204)
        # A field with values only with delete_values.
        item = make_items(self.model, 1)[0]
        services.store_values(item, {self.firmware: "1.0"})
        self.assertEqual(self.admin.delete(f"{API}/custom-fields/{self.firmware.pk}").status_code, 400)
        self.assertEqual(
            self.admin.delete(f"{API}/custom-fields/{self.firmware.pk}?delete_values=true").status_code, 204
        )
        # Everybody reads the definitions; only settings write them.
        warehouse = self.client_for("lager", "Lager")
        self.assertEqual(warehouse.get(f"{API}/custom-fields").status_code, 200)
        self.assertEqual(warehouse.post(f"{API}/custom-fields", {"name": "X"}, format="json").status_code, 403)

    def test_fieldset_operations(self) -> None:
        listed = self.admin.get(f"{API}/custom-fieldsets")
        fieldset = listed.json()["results"][0]
        self.assertEqual(fieldset["name"], "Netzwerkgerät")
        self.assertEqual(
            fieldset["fields"][0], {"field": self.mac.pk, "name": "MAC-Adresse", "position": 1, "required": True}
        )
        self.assertEqual(fieldset["material_models"], [self.model.pk])
        created = self.admin.post(
            f"{API}/custom-fieldsets",
            {
                "name": "Licht",
                "fields": [{"field": self.firmware.pk, "position": 2}, {"field": self.ports.pk, "required": True}],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        new_id = created.json()["id"]
        detail = self.admin.get(f"{API}/custom-fieldsets/{new_id}").json()
        self.assertEqual([entry["name"] for entry in detail["fields"]], ["Ports", "Firmware"])
        put = self.admin.put(
            f"{API}/custom-fieldsets/{new_id}",
            {"name": "Licht", "fields": [{"field": self.firmware.pk}]},
            format="json",
        )
        self.assertEqual([entry["name"] for entry in put.json()["fields"]], ["Firmware"])
        patched = self.admin.patch(
            f"{API}/custom-fieldsets/{new_id}", {"description": "Für Scheinwerfer"}, format="json"
        )
        self.assertEqual(patched.json()["fields"][0]["name"], "Firmware")  # fields not sent stay
        twice = self.admin.patch(
            f"{API}/custom-fieldsets/{new_id}",
            {"fields": [{"field": self.mac.pk}, {"field": self.mac.pk}]},
            format="json",
        )
        self.assertEqual(twice.status_code, 400)
        self.assertEqual(self.admin.delete(f"{API}/custom-fieldsets/{self.fieldset.pk}").status_code, 400)  # in use
        self.assertEqual(self.admin.delete(f"{API}/custom-fieldsets/{new_id}").status_code, 204)

    def test_fieldset_of_a_material_model(self) -> None:
        model = self.admin.get(f"{API}/material-models/{self.model.pk}").json()
        self.assertEqual(model["fieldset"], self.fieldset.pk)
        other = make_model("Router")
        response = self.admin.patch(f"{API}/material-models/{other.pk}", {"fieldset": self.fieldset.pk}, format="json")
        self.assertEqual(response.json()["fieldset"], self.fieldset.pk)
        response = self.admin.patch(f"{API}/material-models/{other.pk}", {"fieldset": None}, format="json")
        self.assertIsNone(response.json()["fieldset"])
        self.assertIsNone(services.fieldset_of(MaterialModel.objects.get(pk=other.pk)))
        bad = self.admin.patch(f"{API}/material-models/{other.pk}", {"fieldset": 999}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_values_of_items(self) -> None:
        created = self.admin.post(
            f"{API}/material-items",
            {"material_model": self.model.pk, "custom_fields": {"MAC-Adresse": "00:1a:2b:3c:4d:5e"}},
            format="json",
        )
        self.assertEqual(created.status_code, 400)  # the pattern wants capitals
        missing = self.admin.post(f"{API}/material-items", {"material_model": self.model.pk}, format="json")
        error = self.assert_error(missing, 400, "validation_error", "custom_fields")
        self.assertIn("MAC-Adresse", str(error))
        created = self.admin.post(
            f"{API}/material-items",
            {
                "material_model": self.model.pk,
                "custom_fields": {"MAC-Adresse": "00:1A:2B:3C:4D:5E", "Ports": 24, "Versicherungswert": "1.200,50"},
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        values = created.json()["custom_fields"]
        self.assertEqual(values["MAC-Adresse"], "00:1A:2B:3C:4D:5E")
        self.assertEqual(values["Ports"], "24")
        self.assertEqual(values["Versicherungswert"], "1200.5")
        self.assertIsNone(values["Firmware"])
        item_id = created.json()["id"]
        patched = self.admin.patch(
            f"{API}/material-items/{item_id}",
            {"custom_fields": {"firmware": "2.0", "Prüfplakette bis": "30.06.2027"}},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.json()["custom_fields"]["Prüfplakette bis"], "2027-06-30")
        self.assertEqual(patched.json()["custom_fields"]["MAC-Adresse"], "00:1A:2B:3C:4D:5E")  # not sent, kept
        for wrong in ({"MAC-Adresse": None}, {"Unbekannt": "x"}, {"Ports": "viele"}):
            response = self.admin.patch(f"{API}/material-items/{item_id}", {"custom_fields": wrong}, format="json")
            self.assertEqual(response.status_code, 400, wrong)
        listed = self.admin.get(f"{API}/material-items", {"q": "2.0"}).json()["results"]
        self.assertEqual([entry["id"] for entry in listed], [item_id])
        filtered = self.admin.get(f"{API}/material-items", {f"cf{self.ports.pk}": "24"}).json()["results"]
        self.assertEqual([entry["id"] for entry in filtered], [item_id])
        # Without the right to see purchase prices the sensitive field is neither shown nor set.
        no_prices = self.client_of(user_with("ohnepreis", role("Lager ohne Preise", {Module.MATERIAL: Level.WRITE})))
        shown = no_prices.get(f"{API}/material-items/{item_id}").json()["custom_fields"]
        self.assertNotIn("Versicherungswert", shown)
        refused = no_prices.patch(
            f"{API}/material-items/{item_id}", {"custom_fields": {"Versicherungswert": "1"}}, format="json"
        )
        self.assertEqual(refused.status_code, 400)
        history = self.admin.get(f"{API}/material-items/{item_id}/history").json()
        self.assertIn("Eigenes Feld „Firmware“ eingetragen", [row["summary"] for row in history])

    def test_several_items_at_once(self) -> None:
        response = self.admin.post(
            f"{API}/material-models/{self.model.pk}/items",
            {"count": 2, "custom_fields": {"Firmware": "2.1"}},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual([item["custom_fields"]["Firmware"] for item in response.json()], ["2.1", "2.1"])
        unique = self.admin.post(
            f"{API}/material-models/{self.model.pk}/items",
            {"count": 2, "custom_fields": {"MAC-Adresse": "00:1A:2B:3C:4D:5E"}},
            format="json",
        )
        self.assertEqual(unique.status_code, 400)
        one = self.admin.post(f"{API}/material-models/{self.model.pk}/items", {"count": 1}, format="json")
        self.assertEqual(one.status_code, 400)  # one item needs its required values
        listed = self.admin.get(f"{API}/material-models/{self.model.pk}/items").json()["results"]
        self.assertEqual(len(listed), 2)


class CategoryFieldsStayTests(RentalarsTestCase):
    """The category-specific fields of MAT-009/MAT-010 are not touched: values per material model."""

    def test_category_fields_unchanged(self) -> None:
        from rentalars.masterdata.models import CategoryField

        model = make_model("Kabel 5 m")
        field = CategoryField.objects.create(category=model.category, label="Länge", field_type="number", unit="m")
        model.set_category_specific_value("5")
        model.save()
        item = make_item(model, 7)
        self.assertEqual(item.category_specific_display, "5 m")
        self.assertEqual(field.display_value("5"), "5 m")
        self.assertEqual(services.value_rows(item, Rights.everything()), [])
