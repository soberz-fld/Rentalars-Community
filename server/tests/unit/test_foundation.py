# SPDX-License-Identifier: GPL-3.0-or-later
"""The foundations: configuration, change log, number ranges, rights, money (NFA, ADM, AUT)."""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, Rights, SpecialRight, rights_of
from rentalars.config import CONFIG_ENVIRONMENT_VARIABLE, ConfigurationError, find_config_path, load_config
from rentalars.core.audit import acting_as, record_event
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry, NumberRange, NumberRangeKey
from rentalars.core.money import format_decimal, format_money, money, percentage_of
from rentalars.customers.models import Customer
from rentalars.masterdata.models import Category
from rentalars.material import numbering
from rentalars.material.models import MaterialItem
from tests.helpers import (
    RentalarsTestCase,
    add_line,
    category,
    make_customer,
    make_item,
    make_model,
    make_product,
    make_project,
    make_user,
)

D = Decimal


class ConfigurationTests(SimpleTestCase):
    """The single configuration file (NFA-034)."""

    def write(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "rentalars.conf"
        path.write_text(text, encoding="utf-8")
        return path

    def test_complete_production_file(self) -> None:
        config = load_config(
            self.write(
                "[rentalars]\nurl = https://rentalars.example.de/\nsecret_key = geheim\ndata_dir = /var/lib/rentalars\n"
                "[database]\nname = rentalars\nuser = rentalars\npassword = sicher\n"
                "[email]\nhost = smtp.example.de\nport = 465\nuse_ssl = yes\nuse_tls = no\nfrom_address = rentalars@example.de\n"
            )
        )
        self.assertEqual(config.environment, "production")
        self.assertFalse(config.debug)
        self.assertEqual(config.url, "https://rentalars.example.de")
        self.assertEqual(config.host_name, "rentalars.example.de")
        self.assertTrue(config.uses_https)
        self.assertEqual(
            (config.database.engine, config.database.name, config.database.password), ("mariadb", "rentalars", "sicher")
        )
        self.assertEqual(
            (config.email.host, config.email.port, config.email.use_ssl, config.email.use_tls),
            ("smtp.example.de", 465, True, False),
        )
        self.assertTrue(config.serve_media_via_nginx)

    def test_production_refuses_to_start_without_secrets(self) -> None:
        """Guessing a secret would be worse than not starting. Also NFA-008."""
        with self.assertRaisesRegex(ConfigurationError, "secret_key"):
            load_config(self.write("[rentalars]\nurl = https://x.example\n[database]\npassword = p\n"))
        with self.assertRaisesRegex(ConfigurationError, "password"):
            load_config(self.write("[rentalars]\nsecret_key = s\n[database]\nname = rentalars\n"))

    def test_production_must_use_mariadb_and_never_runs_in_debug_mode(self) -> None:
        """NFA-001."""
        with self.assertRaisesRegex(ConfigurationError, "MariaDB"):
            load_config(self.write("[rentalars]\nsecret_key = s\n[database]\nengine = sqlite\n"))
        # NFA-073: a production file needs an https:// address – the default http://localhost is refused.
        config = load_config(
            self.write("[rentalars]\nurl = https://x.example\nsecret_key = s\ndebug = true\n[database]\npassword = p\n")
        )
        self.assertFalse(config.debug)

    def test_wrong_values_are_named(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "environment"):
            load_config(self.write("[rentalars]\nenvironment = staging\n"))
        with self.assertRaisesRegex(ConfigurationError, "engine"):
            load_config(self.write("[rentalars]\nenvironment = development\n[database]\nengine = postgres\n"))
        with self.assertRaisesRegex(ConfigurationError, "not a valid configuration file"):
            load_config(self.write("das ist keine Konfiguration\n"))

    def test_development_file_may_use_sqlite(self) -> None:
        config = load_config(
            self.write(
                "[rentalars]\nenvironment = development\ndebug = yes\n[database]\nengine = sqlite\nname = /tmp/x.sqlite3\n"
            )
        )
        self.assertTrue(config.debug)
        self.assertEqual((config.database.engine, config.database.name), ("sqlite", "/tmp/x.sqlite3"))
        self.assertFalse(config.serve_media_via_nginx)

    def test_without_file_the_development_defaults_apply(self) -> None:
        without_variable = {name: value for name, value in os.environ.items() if name != CONFIG_ENVIRONMENT_VARIABLE}
        with (
            mock.patch.dict("os.environ", without_variable, clear=True),
            mock.patch("rentalars.config.DEFAULT_CONFIG_PATH", Path("/nonexistent/rentalars.conf")),
        ):
            self.assertIsNone(find_config_path())
            config = load_config()
        self.assertEqual((config.environment, config.database.engine, config.debug), ("development", "sqlite", True))

    def test_environment_variable_must_point_to_a_file(self) -> None:
        with (
            mock.patch.dict("os.environ", {CONFIG_ENVIRONMENT_VARIABLE: "/nonexistent/rentalars.conf"}),
            self.assertRaisesRegex(ConfigurationError, "does not exist"),
        ):
            find_config_path()
        path = self.write("[rentalars]\nenvironment = test\n")
        with mock.patch.dict("os.environ", {CONFIG_ENVIRONMENT_VARIABLE: str(path)}):
            self.assertEqual(find_config_path(), path)


class MoneyTests(SimpleTestCase):
    """Amounts are decimals, rounded commercially, shown the German way (NFA-003)."""

    def test_rounding_half_up_to_cents(self) -> None:
        self.assertEqual(money(D("2.345")), D("2.35"))
        self.assertEqual(money(D("2.344")), D("2.34"))
        self.assertEqual(money(D("-2.345")), D("-2.35"))
        self.assertEqual(percentage_of(D("310.00"), D("10")), D("31.00"))
        self.assertEqual(percentage_of(D("99.99"), D("12.5")), D("12.50"))
        self.assertEqual(percentage_of(D("100"), D("0")), D("0.00"))

    def test_display(self) -> None:
        self.assertEqual(format_money(D("1668.4")), "1.668,40 €")
        self.assertEqual(format_money(D("-12")), "-12,00 €")
        self.assertEqual(format_money(None), "")
        self.assertEqual(format_decimal(D("1.500")), "1,5")
        self.assertEqual(format_decimal(D("12.00")), "12")
        self.assertEqual(format_decimal(None), "")


class NumberRangeTests(RentalarsTestCase):
    """Number ranges (ADM-003, PRJ-002, MAT-003)."""

    def test_project_numbers_carry_the_year_and_count_up(self) -> None:
        """ADM-014: year and running number, without "P-" again – 2027-0001."""
        first = make_project("Erstes")
        second = make_project("Zweites")
        year, counter = first.number.split("-")
        self.assertEqual(len(year), 4)
        self.assertEqual(int(second.number.split("-")[1]), int(counter) + 1)

    def test_numbers_already_in_use_are_skipped(self) -> None:
        """A counter that was set back must not stop anybody from creating projects or customers."""
        first = make_project("Erstes")
        second = make_project("Zweites")
        NumberRange.objects.filter(key=NumberRangeKey.PROJECT).update(next_value=1)
        third = make_project("Drittes")
        self.assertEqual(len({first.number, second.number, third.number}), 3)
        self.assertEqual(int(third.number.split("-")[1]), 3)

        used = first.customer.number
        NumberRange.objects.filter(key=NumberRangeKey.CUSTOMER).update(next_value=int(used))
        self.assertEqual(int(make_customer("Neuer Kunde").number), int(used) + 1)

    def test_formatting_with_prefix_and_leading_zeros(self) -> None:
        number_range = NumberRange.objects.get(key=NumberRangeKey.PROJECT)
        self.assertEqual(number_range.format(42, year=2027), "2027-0042")  # ADM-014
        number_range.prefix = "P"
        number_range.min_digits = 2
        self.assertEqual(number_range.format(7), "P07")
        self.assertEqual(number_range.format(12345), "P12345")

    def test_counter_is_moved_behind_the_highest_used_number_only_forward(self) -> None:
        NumberRange.ensure_next_is_above(NumberRangeKey.MATERIAL_ITEM, 1650)
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value, 1651)
        NumberRange.ensure_next_is_above(NumberRangeKey.MATERIAL_ITEM, 10)
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value, 1651)

    def test_material_ids_have_four_digits_and_grow_beyond_9999(self) -> None:
        self.assertEqual(numbering.format_inventory_number(42), "0042")
        self.assertEqual(numbering.format_inventory_number(10000), "10000")
        self.assertEqual(numbering.parse_inventory_number("0042"), 42)
        self.assertEqual(numbering.parse_inventory_number(42.0), 42)
        self.assertEqual(numbering.parse_inventory_number("42.0"), 42)
        for wrong in ("", "abc", "0", "-5", "4 2", True, 4.5):
            with self.assertRaises(ValidationError, msg=repr(wrong)):
                numbering.parse_inventory_number(wrong)

    def test_a_chosen_id_moves_the_counter_so_that_it_is_never_given_again(self) -> None:
        """MAT-001."""
        model = make_model("Rack", category_code="R")
        make_item(model, 500)
        from rentalars.material.services import create_items

        self.assertEqual(create_items(model, 1)[0].inventory_number, 501)
        self.assertEqual(MaterialItem.objects.count(), 2)

    def test_id_ranges_for_typed_prefixes(self) -> None:
        self.assertEqual(numbering.id_range_for_prefix("05"), (500, 599))
        self.assertEqual(numbering.id_range_for_prefix("0500"), (500, 500))
        self.assertEqual(numbering.id_range_for_prefix("1"), (1000, 1999))
        self.assertIsNone(numbering.id_range_for_prefix("Rack"))
        self.assertIsNone(numbering.id_range_for_prefix("12345"))


class ProjectRulesTests(SimpleTestCase):
    """Rules of the project itself that a machine can check (NFA-004, NFA-052, NFA-053)."""

    databases = {"default"}

    def test_no_model_was_changed_without_a_migration(self) -> None:
        """NFA-004: the tables only ever change through versioned, repeatable migrations."""
        from django.core.management import call_command

        call_command("makemigrations", "--check", "--dry-run", verbosity=0)

    def test_licence_text_and_notice_are_part_of_the_package(self) -> None:
        """NFA-052: GPL, version 3 or later, with the text of the licence and a copyright notice."""
        root = Path(__file__).resolve().parent.parent.parent
        licence = (root / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", licence)
        self.assertIn("Version 3, 29 June 2007", licence)
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("GPL-3.0-or-later", readme)
        self.assertIn("Copyright ©", readme)
        self.assertIn('license = "GPL-3.0-or-later"', (root / "pyproject.toml").read_text(encoding="utf-8"))

    def test_every_library_has_a_licence_that_fits_the_gpl(self) -> None:
        """NFA-053: the same check the continuous integration runs; AGPL and unknown licences fail it."""
        import subprocess
        import sys

        root = Path(__file__).resolve().parent.parent.parent
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "check_licenses.py")], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ChangeLogHygieneTests(RentalarsTestCase):
    """What is deliberately *not* in the change log, and in which language it is written (ADM-005)."""

    def test_a_counter_moving_on_is_not_logged_but_a_change_by_hand_is(self) -> None:
        before = AuditLogEntry.objects.filter(content_type__model="numberrange").count()
        NumberRange.allocate(NumberRangeKey.PROJECT)
        NumberRange.allocate(NumberRangeKey.PROJECT)
        NumberRange.ensure_next_is_above(NumberRangeKey.MATERIAL_ITEM, 1650)
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value, 1651)
        self.assertEqual(AuditLogEntry.objects.filter(content_type__model="numberrange").count(), before)

        number_range = NumberRange.objects.get(key=NumberRangeKey.PROJECT)
        number_range.next_value = 500
        number_range.save()
        self.assertEqual(AuditLogEntry.objects.filter(content_type__model="numberrange").count(), before + 1)

    def test_records_are_named_in_the_language_of_the_installation(self) -> None:
        """Commands such as "migrate" run without a language; the log must not turn English for that."""
        from django.utils import translation

        with translation.override(None):
            number_range = NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM)
            number_range.min_digits = 5
            number_range.save()
        entry = AuditLogEntry.objects.filter(content_type__model="numberrange").latest("pk")
        self.assertEqual(entry.object_repr, "Material-IDs")


class AuditLogTests(RentalarsTestCase):
    """The change log (ADM-005, PRJ-009, MAT-025)."""

    def entries(self, instance: object) -> list[AuditLogEntry]:
        return list(AuditLogEntry.for_object(instance).order_by("timestamp", "id"))  # type: ignore[arg-type]

    def test_only_real_changes_are_logged_with_old_and_new_value(self) -> None:
        user = make_user("anna")
        customer = make_customer("Stadtwerke")
        loaded = Customer.objects.get(pk=customer.pk)
        with acting_as(user):
            loaded.save()  # nothing changed
            loaded.city = "Musterstadt"
            loaded.save()
            loaded.city = "Musterstadt"
            loaded.save()  # again nothing changed
        entries = self.entries(customer)
        self.assertEqual([entry.action for entry in entries], ["created", "updated"])
        self.assertEqual(entries[1].changes, {"city": ["", "Musterstadt"]})
        self.assertEqual((entries[1].actor, entries[1].actor_label), (user, "anna"))

    def test_changes_made_after_a_reload_compare_with_the_reloaded_state(self) -> None:
        customer = make_customer("Stadtwerke")
        Customer.objects.filter(pk=customer.pk).update(city="Altstadt")
        customer.refresh_from_db()
        customer.city = "Neustadt"
        customer.save()
        self.assertEqual(self.entries(customer)[-1].changes, {"city": ["Altstadt", "Neustadt"]})

    def test_values_changed_in_place_are_noticed(self) -> None:
        """JSON fields can be changed without assigning them anew."""
        role = Role.objects.create(name="Werkstatt", module_levels={"material": 1})
        loaded = Role.objects.get(pk=role.pk)
        loaded.module_levels["material"] = 2
        loaded.save()
        self.assertEqual(self.entries(role)[-1].changes, {"module_levels": [{"material": 1}, {"material": 2}]})

    def test_deletion_is_logged_and_jobs_without_user_carry_their_name(self) -> None:
        customer = make_customer("Stadtwerke")
        pk = customer.pk
        with acting_as("system:import"):
            customer.delete()
        entry = AuditLogEntry.objects.filter(object_id=str(pk), action="deleted").get()
        self.assertEqual((entry.actor, entry.actor_label, entry.object_repr), (None, "system:import", "Stadtwerke"))

    def test_lines_appear_in_the_history_of_their_project(self) -> None:
        """PRJ-032."""
        project = make_project()
        line = add_line(project, make_product("L-010", price="20.00"), 2).line
        line.quantity = D("3")
        line.save()
        history = AuditLogEntry.for_object(project)
        self.assertTrue(
            history.filter(content_type__model="materialline", object_id=str(line.pk), action="updated").exists()
        )

    def test_prices_in_the_history_need_the_price_right(self) -> None:
        """AUT-019."""
        project = make_project()
        line = add_line(project, make_product("L-010", price="20.00"), 2).line
        line.unit_price = D("25.00")
        line.note = "mit Torblende"
        line.save()
        entry = AuditLogEntry.objects.filter(
            content_type__model="materialline", object_id=str(line.pk), action="updated"
        ).get()
        with_prices = describe([entry], Rights.everything())[0]
        without = describe([entry], Rights(module_levels={Module.PROJECTS: Level.READ}))[0]
        self.assertEqual({change.name for change in with_prices.changes}, {"unit_price", "note"})
        self.assertEqual({change.name for change in without.changes}, {"note"})

    def test_business_events_are_readable(self) -> None:
        project = make_project()
        entry = record_event(project, "setup.completed")
        self.assertEqual(entry.action, "event")
        described = describe([entry], Rights.everything())[0]
        self.assertTrue(described.summary)


class RightsTests(RentalarsTestCase):
    """Roles and effective rights (AUT-010 to AUT-021)."""

    def test_highest_level_of_all_roles_counts(self) -> None:
        Role.objects.create(name="A", module_levels={"material": 1, "products": 3}, special_rights=["prices"])
        Role.objects.create(name="B", module_levels={"material": 2}, special_rights=["purchase_prices"])
        rights = rights_of(make_user("anna", roles=("A", "B")))
        self.assertEqual(
            (rights.level(Module.MATERIAL), rights.level(Module.PRODUCTS), rights.level(Module.CUSTOMERS)), (2, 3, 0)
        )
        self.assertTrue(rights.has(SpecialRight.PRICES) and rights.has(SpecialRight.PURCHASE_PRICES))
        self.assertFalse(rights.has(SpecialRight.REOPEN_PROJECTS))
        self.assertEqual(sorted(rights.readable_modules), ["material", "products"])

    def test_levels_include_the_lower_ones(self) -> None:
        rights = Rights(module_levels={"material": Level.WRITE})
        self.assertTrue(rights.can_read("material") and rights.can_write("material"))
        self.assertFalse(rights.can_delete("material"))

    def test_inactive_and_anonymous_users_have_no_rights(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        user = make_user("anna", superuser=True)
        user.is_active = False
        self.assertEqual(rights_of(user).readable_modules, [])
        self.assertEqual(rights_of(AnonymousUser()).readable_modules, [])

    def test_superuser_has_everything_whatever_the_roles_say(self) -> None:
        rights = rights_of(make_user("anna", superuser=True))
        self.assertTrue(all(rights.can_delete(module) for module in Module.values))
        self.assertEqual(set(rights.special_rights), set(SpecialRight.values))

    def test_token_restrictions_only_ever_narrow(self) -> None:
        """AUT-021."""
        full = Rights.everything()
        read_only = full.restricted(read_only=True, allowed_modules=[])
        self.assertTrue(read_only.can_read("projects"))
        self.assertFalse(read_only.can_write("projects"))
        self.assertTrue(read_only.has(SpecialRight.PRICES))
        self.assertFalse(read_only.has(SpecialRight.REOPEN_PROJECTS))
        material_only = full.restricted(read_only=False, allowed_modules=["material", "nonsense"])
        self.assertEqual(material_only.readable_modules, ["material"])
        weak = Rights(module_levels={"material": Level.READ}).restricted(
            read_only=False, allowed_modules=["material", "projects"]
        )
        self.assertEqual((weak.level("material"), weak.level("projects")), (1, 0))

    def test_role_rejects_unknown_modules_levels_and_rights(self) -> None:
        """AUT-014."""
        for fields in (
            {"module_levels": {"nonsense": 1}},
            {"module_levels": {"material": 9}},
            {"special_rights": ["everything"]},
        ):
            with self.assertRaises(ValidationError, msg=str(fields)):
                Role(name="Kaputt", **fields).full_clean()


class CategoryTreeTests(RentalarsTestCase):
    """Categories in lists and selection fields (MAT-008, PRD-009)."""

    def test_a_fresh_installation_starts_with_the_main_categories_of_the_catalogue(self) -> None:
        """PRD-027, ADM-011: the start assignment of codes, e.g. K for cables and E for everything external.

        PRD-043: C "Fremdmaterial" for the material customers keep here. PRD-045: N "Nebenkosten".
        LOG-002: FZ "Fuhrpark" for the vehicles and trailers.
        """
        codes = dict(Category.objects.filter(parent__isnull=True).values_list("code", "name"))
        self.assertEqual(sorted(codes), ["C", "D", "E", "FZ", "K", "L", "M", "N", "R", "T", "V"])
        self.assertEqual(codes["FZ"], "Fuhrpark")
        self.assertEqual(
            (codes["K"], codes["L"], codes["T"], codes["R"], codes["M"]),
            ("Kabel", "Licht", "Ton", "Rigging/Traverse", "Video/Medien"),
        )
        self.assertIn("Extern", codes["E"])

    def test_subcategories_follow_their_parent(self) -> None:
        sound = category("T")
        microphones = Category.objects.create(name="Mikrofone", parent=sound)
        Category.objects.create(name="Funkstrecken", parent=microphones)
        Category.objects.create(name="Dimmer", parent=category("L"))

        with self.assertNumQueries(1):
            paths = [entry.path for entry in Category.objects.in_tree_order()]

        self.assertEqual(paths, sorted(paths, key=str.lower))
        start = paths.index("Ton")
        self.assertEqual(paths[start : start + 3], ["Ton", "Ton > Mikrofone", "Ton > Mikrofone > Funkstrecken"])
        self.assertEqual(paths[paths.index("Licht") + 1], "Licht > Dimmer")

    def test_selection_fields_offer_active_categories_only(self) -> None:
        cables = category("K")
        cables.is_active = False
        cables.save()
        labels = [label for _value, label in Category.objects.choices()]
        self.assertEqual(str(labels[0]), "– bitte wählen –")  # B12
        self.assertNotIn("Kabel", labels)
        self.assertIn("Ton", labels)
        self.assertIn("Kabel", [entry.path for entry in Category.objects.in_tree_order()])
