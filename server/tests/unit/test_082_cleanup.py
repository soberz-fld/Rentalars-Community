# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "clean-up": errors of services on every form (EML-024), every column sortable (UIX-015, UIX-040),
English names in the database (NFA-061), leftovers (NFA-062).

The pages – sorting by every column of every list, writing a mail that fails, the folded filters (UIX-038) – are
tested in ``tests/ui/test_082_cleanup_pages.py`` and ``tests/browser/test_082_cleanup_in_browser.py``.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from unittest import mock

from django import forms
from django.apps import apps
from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.test import RequestFactory, SimpleTestCase

import rentalars
from rentalars.core.forms import StyledForm, StyledModelForm, add_validation_error
from rentalars.core.tables import REGISTRY, Column, TableDefinition, natural_key
from rentalars.core.tabular import fold
from rentalars.customers.models import Customer
from rentalars.mail.forms import ComposeForm
from tests.helpers import RentalarsTestCase, make_project, make_user


def every_table() -> dict[str, TableDefinition]:
    """Every table of ``core.tables``: the modules that define them are imported first."""
    for module in pkgutil.walk_packages(rentalars.__path__, "rentalars."):
        if ".migrations" in module.name or module.name.endswith(("wsgi", "settings")):
            continue
        importlib.import_module(module.name)
    return dict(REGISTRY)


class _Plain(StyledForm):
    to = forms.CharField()


class _CustomerForm(StyledModelForm):
    error_field_map = {"city": "name"}

    class Meta:
        model = Customer
        fields = ["name"]


class AddValidationErrorTests(SimpleTestCase):
    """EML-024: a ``ValidationError`` of a service shows on any form – a plain one too."""

    def test_a_plain_form_has_no_private_method_of_model_forms(self) -> None:
        """The cause of "'ComposeForm' object has no attribute '_update_errors'"."""
        form = ComposeForm(data={}, file_choices=[], document_choices=[])
        self.assertFalse(hasattr(form, "_update_errors"))

    def test_errors_of_fields_the_form_has_and_has_not(self) -> None:
        form = _Plain(data={"to": "x"})
        self.assertTrue(form.is_valid())
        add_validation_error(form, ValidationError({"to": "Keine gültige Adresse.", "uploads": "Zu groß."}))
        self.assertEqual(form.errors["to"], ["Keine gültige Adresse."])
        self.assertEqual(form.non_field_errors(), ["Zu groß."])
        self.assertNotIn("to", form.cleaned_data)

    def test_an_error_without_field(self) -> None:
        form = _Plain(data={"to": "x"})
        form.is_valid()
        add_validation_error(form, ValidationError(["Senden ist nicht eingerichtet.", "Noch etwas."]))
        self.assertEqual(form.non_field_errors(), ["Senden ist nicht eingerichtet.", "Noch etwas."])

    def test_a_model_form_routes_by_its_map(self) -> None:
        form = _CustomerForm(data={"name": "Stadtwerke"})
        self.assertTrue(form.is_valid())
        add_validation_error(form, ValidationError({"city": "Ort fehlt.", "number": "Vergeben."}))
        self.assertEqual(form.errors["name"], ["Ort fehlt."])
        self.assertEqual(form.non_field_errors(), ["Vergeben."])

    def test_no_view_uses_the_private_method_any_more(self) -> None:
        for module in pkgutil.walk_packages(rentalars.__path__, "rentalars."):
            if module.name == "rentalars.core.forms" or ".migrations" in module.name:
                continue
            spec = importlib.util.find_spec(module.name)
            if spec is None or not spec.origin or not spec.origin.endswith(".py"):
                continue
            with open(spec.origin, encoding="utf-8") as source:
                self.assertNotIn("._update_errors(", source.read(), module.name)


class EveryColumnSortsTests(SimpleTestCase):
    """UIX-015, UIX-040: every heading sorts – also columns a user adds and computed ones."""

    def test_every_column_of_every_table_sorts_or_says_why_not(self) -> None:
        tables = every_table()
        self.assertGreater(len(tables), 30)
        unsortable = []
        for key, table in tables.items():
            if key.startswith("test_"):
                continue  # tables made up by tests
            for column in table.columns:
                with self.subTest(table=key, column=column.key):
                    if column.sort is None:
                        self.assertTrue(column.unsortable, f"{key}.{column.key} needs a sort or a reason")
                        # Only buttons and fields are no data – they are left out of the CSV file as well.
                        self.assertFalse(column.export, f"{key}.{column.key}")
                        unsortable.append(f"{key}.{column.key}")
                    else:
                        self.assertEqual(column.unsortable, "", f"{key}.{column.key}: sortable after all")
        # ZEI-030: eleven – the button "Korrigieren und freigeben" of Personal → Freigeben is the new one.
        # MAT-070: twelve – the button "Audit" of Offene Punkte → Audit fällig (material_audits_due.audit).
        self.assertLessEqual(len(unsortable), 12, unsortable)

    def test_every_column_of_the_master_data_lists_sorts(self) -> None:
        """The lists of Django's administration (UIX-040): a field, or a column with ``ordering``."""
        for model, model_admin in admin.site._registry.items():
            for name in model_admin.get_list_display(RequestFactory().get("/")):
                with self.subTest(model=model._meta.label, column=str(name)):
                    if callable(name):
                        self.assertTrue(hasattr(name, "admin_order_field"))
                        continue
                    try:
                        field = model._meta.get_field(name)
                    except FieldDoesNotExist:
                        attribute = getattr(model_admin, name, None)
                        self.assertTrue(hasattr(attribute, "admin_order_field"), name)
                    else:
                        self.assertFalse(field.many_to_many or field.one_to_many, name)

    def test_natural_order_of_computed_text(self) -> None:
        values = ["10 m", "5 m", "", "M10", "M8", "m9"]
        self.assertEqual(
            sorted(values, key=lambda value: (natural_key(value) is None, natural_key(value) or ())),
            ["5 m", "10 m", "M8", "m9", "M10", ""],
        )


class PythonSortTests(RentalarsTestCase):
    """UIX-015: a computed column sorts the list in Python – up to a length, else it says so."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("chef", superuser=True)
        self.table = TableDefinition(
            "test_082_python_sort",
            [
                Column("number", "Nummer", cell=lambda project: project.number, sort="number"),
                Column("length", "Länge", cell=lambda project: len(project.name), sort=lambda p: len(p.name)),
            ],
            default_sort="number",
        )
        self.addCleanup(REGISTRY.pop, "test_082_python_sort")
        for name in ("Mittel-Projekt", "Kurz", "Ein sehr langes Projekt"):
            make_project(name)

    def state(self, sort: str) -> object:
        request = RequestFactory().get("/", {"sort": sort})
        request.user = self.user
        return self.table.state(request)

    def test_sorted_by_the_computed_value_both_ways(self) -> None:
        from rentalars.projects.models import Project

        rows = self.state("length").order(Project.objects.all())
        self.assertEqual([project.name for project in rows], ["Kurz", "Mittel-Projekt", "Ein sehr langes Projekt"])
        rows = self.state("-length").order(Project.objects.all())
        self.assertEqual([project.name for project in rows], ["Ein sehr langes Projekt", "Mittel-Projekt", "Kurz"])

    def test_a_long_list_keeps_its_order_and_says_why(self) -> None:
        from rentalars.projects.models import Project

        state = self.state("length")
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            rows = state.order(Project.objects.all())
        self.assertEqual(state.sort, "number")
        self.assertIn("„Länge“", state.sort_notice)
        self.assertIn("höchstens 2", state.sort_notice)
        self.assertEqual(list(rows), list(Project.objects.order_by("number")))


class EnglishNamesInTheDatabaseTests(SimpleTestCase):
    """NFA-061: tables, columns and stored choice values are English."""

    GERMAN = re.compile(
        r"[äöüß]|(^|_)(kunde|projekt|anfrage|datum|preis|menge|lager|bezeichnung|rechnung|angebot|mitarbeiter|"
        r"einsatz|stunden|nummer|bemerkung|notiz|beschreibung|kategorie|hersteller|lieferant|anzahl|summe|steuer|"
        r"rabatt|zuschlag|fahrt|termin|ort|strasse|benutzer|rolle|passwort|einstellung|planung|packliste|pruefung|"
        r"miete|gewicht|vorlage|beleg|offen|erledigt|bestaetigt|angefragt|eingeplant|bestand|wiedervorlage)(_|$)"
    )

    def test_tables_columns_and_choice_values(self) -> None:
        found = []
        for model in apps.get_models():
            if not model.__module__.startswith("rentalars"):
                continue
            names = [model._meta.db_table]
            for field in model._meta.concrete_fields:
                names += [field.name, field.column]
                names += [str(value) for value, _label in (field.flatchoices or []) if isinstance(value, str)]
            found += [f"{model._meta.label}: {name}" for name in names if self.GERMAN.search(name.lower())]
        self.assertEqual(found, [])


class LeftoverTests(SimpleTestCase):
    """NFA-062: one helper for folding names instead of two copies."""

    def test_fold(self) -> None:
        self.assertEqual(fold("MÜLLER"), fold("Mueller"))
        self.assertEqual(fold("Crème"), "creme")

    def test_both_users_share_it(self) -> None:
        from rentalars.customers import importer
        from rentalars.projects import mvr

        self.assertIs(importer.fold, fold)
        self.assertIs(mvr.fold, fold)


class ReviewTests(SimpleTestCase):
    """Review: the projects of a bottleneck sort by their numbers (UIX-015); no empty "<>" (EML-038)."""

    def test_bottlenecks_by_their_project_numbers(self) -> None:
        from types import SimpleNamespace

        from rentalars.availability.shortage_tables import _project_numbers_key

        def entry(*numbers: str) -> dict[str, list[SimpleNamespace]]:
            return {"projects": [SimpleNamespace(number=number) for number in numbers]}

        rows = [entry("2026-0010"), entry("2026-0012", "2026-0009"), entry("2026-0011")]
        ordered = sorted(rows, key=_project_numbers_key)
        self.assertEqual([row["projects"][0].number for row in ordered], ["2026-0012", "2026-0010", "2026-0011"])

    def test_the_sender_without_an_address(self) -> None:
        from rentalars.mail.signature import sender_label

        with mock.patch("rentalars.mail.signature.sender_name", return_value="Reviewer | Licht & Ton GmbH"):
            self.assertEqual(sender_label(None, ""), "Reviewer | Licht & Ton GmbH")
            self.assertEqual(sender_label(None, "info@lt.example"), "Reviewer | Licht & Ton GmbH <info@lt.example>")
