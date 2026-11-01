# SPDX-License-Identifier: GPL-3.0-or-later
"""Contact persons with first and last name, and the greeting of mails per contact (KND-004).

The requirement: a new contact person of a customer has separate first and last names, and the greeting in mails can be
set individually.

* A contact has a first name (optional) and a last name (needed); ``name`` stays the full name, derived from them, so
  lists, search, exports and the API keep working. Contacts from before are split by a data migration that does
  not change the name shown; old API clients that send only ``name`` still work.
* The greeting of mails to a contact is set per contact: formal ("Sehr geehrte Frau Berg,"), personal ("Hallo
  Anna,") or an own text. The mail form and the reply draft of the AI begin with it; documents and automatic
  answers have the placeholders ``{greeting}`` / ``{anrede}``.
"""

from __future__ import annotations

import importlib
import pathlib
from decimal import Decimal
from typing import Any

from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import translation

from rentalars.ai import drafts
from rentalars.ai.models import Source
from rentalars.automations import engine
from rentalars.core import import_exports, imports
from rentalars.core.audit import AuditedModel
from rentalars.core.models import AuditLogEntry
from rentalars.core.tabular import Table, resolve_mapping
from rentalars.customers import greetings
from rentalars.customers.models import Contact, Customer, GreetingStyle
from rentalars.customers.names import first_name_for_greeting, join_name, parse_name, split_name
from rentalars.customers.services import anonymise_customer, export_customer
from rentalars.documents import content as document_content
from rentalars.documents.lexware import contact_body
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_customer, make_project
from tests.ui.base import UiTestCase, form_data
from tests.unit import test_083_ai
from tests.unit.test_092_exports import records, table_of, text_of

migration_0009 = importlib.import_module("rentalars.customers.migrations.0009_split_contact_names_095")


def contact(customer: Customer, **fields: Any) -> Contact:
    """A saved contact."""
    return Contact.objects.create(customer=customer, **fields)


class SplitNameTests(RentalarsTestCase):
    """The rule that finds first and last name in a whole name (conservative: the last word is the last name)."""

    def test_the_rule(self) -> None:
        cases = {
            "Anna Berg": ("Anna", "Berg"),
            "Anna Maria Berg": ("Anna Maria", "Berg"),
            "Berg": ("", "Berg"),
            "Berg, Anna": ("Anna", "Berg"),
            "von Berg, Anna": ("Anna", "von Berg"),
            "Jan van der Berg": ("Jan", "van der Berg"),
            "Eva von Berg": ("Eva", "von Berg"),
            "von Berg": ("", "von Berg"),
            "Max zur Linden": ("Max", "zur Linden"),
            "Peter de Vries": ("Peter", "de Vries"),
            "Dr. Anna Berg": ("Dr. Anna", "Berg"),
            "  Anna   Berg  ": ("Anna", "Berg"),
            "Anna Berg, Technik": ("Anna", "Berg"),
            "Hans-Peter Meier-Lüdenscheidt": ("Hans-Peter", "Meier-Lüdenscheidt"),
            "": ("", ""),
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(split_name(name), expected)

    def test_noise_around_the_name(self) -> None:
        """KND-011 (contacts): trailing commas, remarks, parentheses and Frau/Herr/Mr/Ms/Mrs."""
        cases = {
            "Berg,": ("", "Berg"),
            "Anna Berg,": ("Anna", "Berg"),
            "Berg, Anna,": ("Anna", "Berg"),
            ",": ("", ""),
            "Anna Berg (Technik)": ("Anna", "Berg"),
            "Anna (Technik) Berg": ("Anna", "Berg"),
            "Anna Berg (Technik": ("Anna", "Berg"),
            "Frau Anna Berg": ("Anna", "Berg"),
            "Herr Jan van der Berg": ("Jan", "van der Berg"),
            "Mr. Jan Berg": ("Jan", "Berg"),
            "Ms Anna Berg": ("Anna", "Berg"),
            "Mrs Berg": ("", "Berg"),
            "Frau Dr. Anna Berg": ("Dr. Anna", "Berg"),
            "Frau Berg, Anna": ("Anna", "Berg"),
            "Herr": ("", "Herr"),  # a word alone stays what it is: a name
            "Anna Herr": ("Anna", "Herr"),
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(split_name(name), expected)

    def test_the_salutation_and_the_remark_are_set_aside_not_lost(self) -> None:
        parsed = parse_name("Frau Anna Berg, Technik")
        self.assertEqual(
            (parsed.first_name, parsed.last_name, parsed.salutation, parsed.remark), ("Anna", "Berg", "Frau", "Technik")
        )
        self.assertEqual(parse_name("Berg, Anna, Leiterin Technik").remark, "Leiterin Technik")
        self.assertEqual(parse_name("Anna Berg (Technik)").remark, "")  # text in parentheses is cut

    def test_joined_again(self) -> None:
        self.assertEqual(join_name("Anna", "Berg"), "Anna Berg")
        self.assertEqual(join_name("", "Berg"), "Berg")
        self.assertEqual(join_name(" Anna ", " van der Berg"), "Anna van der Berg")

    def test_titles_are_left_out_of_a_first_name_used_alone(self) -> None:
        self.assertEqual(first_name_for_greeting("Dr. Anna"), "Anna")
        self.assertEqual(first_name_for_greeting("Prof. Dr. Anna Maria"), "Anna Maria")
        self.assertEqual(first_name_for_greeting("Dipl.-Ing. Jan"), "Jan")
        self.assertEqual(first_name_for_greeting("Dr."), "")


class ContactModelTests(RentalarsTestCase):
    """``name`` is derived from the parts; a bare name is split; the last name is needed."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")

    def test_name_is_derived_from_the_parts(self) -> None:
        saved = contact(self.customer, first_name="Anna", last_name="Berg")
        self.assertEqual((saved.name, str(saved)), ("Anna Berg", "Anna Berg"))
        saved.first_name = "Anne"
        saved.save()
        self.assertEqual(Contact.objects.get(pk=saved.pk).name, "Anne Berg")

    def test_a_bare_name_is_split(self) -> None:
        saved = contact(self.customer, name="Jan van der Berg")
        saved.refresh_from_db()
        self.assertEqual((saved.first_name, saved.last_name, saved.name), ("Jan", "van der Berg", "Jan van der Berg"))

    def test_the_last_name_is_needed(self) -> None:
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as caught:
            Contact(customer=self.customer, first_name="Anna").full_clean()
        self.assertIn("last_name", caught.exception.message_dict)

    def test_the_default_greeting_is_formal(self) -> None:
        self.assertEqual(contact(self.customer, name="Anna Berg").greeting_style, GreetingStyle.FORMAL)

    def test_order_is_by_last_then_first_name(self) -> None:
        contact(self.customer, name="Zoe Adler")
        contact(self.customer, name="Anna Berg")
        contact(self.customer, name="Ben Berg")
        self.assertEqual([c.name for c in Contact.objects.all()], ["Zoe Adler", "Anna Berg", "Ben Berg"])

    def test_the_history_shows_the_parts_not_the_derived_name(self) -> None:
        saved = contact(self.customer, first_name="Anna", last_name="Berg")
        saved.last_name = "Bergmann"
        saved.save()
        changed = AuditLogEntry.for_object(saved).first()
        assert changed is not None
        self.assertEqual(set(changed.changes), {"last_name"})
        self.assertIn("name", Contact.audit_exclude)
        self.assertIsInstance(saved, AuditedModel)


class MigrationTests(RentalarsTestCase):
    """The data migration splits existing names without changing them, and runs again harmlessly."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")
        # Rows as they used to be: only a name; written around save() so that nothing is split yet.
        self.names = ["Anna Berg", "Berg, Anna", "Jan van der Berg", "Berg", "Eva von Berg", "Dr. Max Mustermann"]
        Contact.objects.bulk_create([Contact(customer=self.customer, name=name) for name in self.names])

    def names_now(self) -> dict[str, tuple[str, str]]:
        return {c.name: (c.first_name, c.last_name) for c in Contact.objects.all()}

    def test_forward_splits_and_keeps_the_name(self) -> None:
        self.assertTrue(all(parts == ("", "") for parts in self.names_now().values()))
        migration_0009.split_names(apps, None)
        self.assertEqual(sorted(self.names_now()), sorted(self.names))  # the name shown is unchanged
        parts = self.names_now()
        self.assertEqual(parts["Anna Berg"], ("Anna", "Berg"))
        self.assertEqual(parts["Berg, Anna"], ("Anna", "Berg"))
        self.assertEqual(parts["Jan van der Berg"], ("Jan", "van der Berg"))
        self.assertEqual(parts["Berg"], ("", "Berg"))
        self.assertEqual(parts["Eva von Berg"], ("Eva", "von Berg"))
        self.assertEqual(parts["Dr. Max Mustermann"], ("Dr. Max", "Mustermann"))

    def test_it_is_idempotent_and_leaves_edited_contacts_alone(self) -> None:
        Contact.objects.filter(name="Anna Berg").update(first_name="Annabelle", last_name="Berg-Meier")
        migration_0009.split_names(apps, None)
        before = self.names_now()
        migration_0009.split_names(apps, None)
        self.assertEqual(self.names_now(), before)
        self.assertEqual(before["Anna Berg"], ("Annabelle", "Berg-Meier"))

    def test_backward_rebuilds_a_name_that_no_longer_agrees(self) -> None:
        migration_0009.split_names(apps, None)
        Contact.objects.filter(name="Anna Berg").update(last_name="Bergmann")
        migration_0009.join_names(apps, None)
        self.assertEqual(
            sorted(c.name for c in Contact.objects.all()),
            sorted(["Anna Bergmann", *[n for n in self.names if n != "Anna Berg"]]),
        )

    def test_twenty_thousand_rows_in_batches(self) -> None:
        Contact.objects.bulk_create(
            [Contact(customer=self.customer, name=f"Vorname{i} Nachname{i}") for i in range(20_000)], batch_size=2000
        )
        migration_0009.split_names(apps, None)
        self.assertFalse(Contact.objects.filter(last_name="").exists())
        self.assertEqual(Contact.objects.get(name="Vorname19999 Nachname19999").first_name, "Vorname19999")


class GreetingTests(RentalarsTestCase):
    """The greeting line for every style, in German and English."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")

    def line(self, language: str, **fields: Any) -> str:
        return greetings.greeting(Contact(customer=self.customer, **fields), language)

    def test_formal_german(self) -> None:
        self.assertEqual(
            self.line("de", salutation="Frau", first_name="Anna", last_name="Berg"), "Sehr geehrte Frau Berg,"
        )
        self.assertEqual(
            self.line("de", salutation="Herr", first_name="Jan", last_name="Berg"), "Sehr geehrter Herr Berg,"
        )
        self.assertEqual(self.line("de", salutation="Herr", last_name="Berg"), "Sehr geehrter Herr Berg,")

    def test_formal_without_a_known_gender(self) -> None:
        self.assertEqual(self.line("de", first_name="Anna", last_name="Berg"), "Guten Tag Anna Berg,")
        self.assertEqual(
            self.line("de", salutation="Divers", first_name="Kim", last_name="Berg"), "Guten Tag Kim Berg,"
        )
        self.assertEqual(self.line("de", last_name="Berg"), "Guten Tag Berg,")

    def test_a_title_without_gender_gives_guten_tag_with_the_title(self) -> None:
        self.assertEqual(self.line("de", salutation="Dr", first_name="Anna", last_name="Berg"), "Guten Tag Dr. Berg,")
        self.assertEqual(self.line("de", salutation="Prof. Dr.", last_name="Berg"), "Guten Tag Prof. Dr. Berg,")

    def test_gender_and_title_together(self) -> None:
        self.assertEqual(self.line("de", salutation="Frau Dr.", last_name="Berg"), "Sehr geehrte Frau Dr. Berg,")
        self.assertEqual(self.line("de", salutation="Herr Prof.", last_name="Berg"), "Sehr geehrter Herr Prof. Berg,")

    def test_english(self) -> None:
        self.assertEqual(self.line("en", salutation="Ms", first_name="Anna", last_name="Berg"), "Dear Ms Berg,")
        self.assertEqual(self.line("en", salutation="Mr", last_name="Berg"), "Dear Mr Berg,")
        self.assertEqual(self.line("en", salutation="Frau", last_name="Berg"), "Dear Ms Berg,")
        self.assertEqual(self.line("en", first_name="Anna", last_name="Berg"), "Dear Anna Berg,")
        self.assertEqual(self.line("en", salutation="Dr", last_name="Berg"), "Dear Dr. Berg,")
        self.assertEqual(self.line("en", salutation="Frau Dr.", last_name="Berg"), "Dear Dr. Berg,")

    def test_personal(self) -> None:
        personal = {"greeting_style": GreetingStyle.PERSONAL, "first_name": "Anna", "last_name": "Berg"}
        self.assertEqual(self.line("de", **personal), "Hallo Anna,")
        self.assertEqual(self.line("en", **personal), "Hello Anna,")
        self.assertEqual(self.line("de", **{**personal, "first_name": "Dr. Anna"}), "Hallo Anna,")

    def test_personal_without_a_first_name_falls_back_to_the_formal_greeting(self) -> None:
        self.assertEqual(
            self.line("de", greeting_style=GreetingStyle.PERSONAL, salutation="Frau", last_name="Berg"),
            "Sehr geehrte Frau Berg,",
        )

    def test_custom_is_used_as_typed_in_any_language(self) -> None:
        custom = {"greeting_style": GreetingStyle.CUSTOM, "greeting_text": " Liebe Anna, ", "last_name": "Berg"}
        self.assertEqual(self.line("de", **custom), "Liebe Anna,")
        self.assertEqual(self.line("en", **custom), "Liebe Anna,")

    def test_custom_without_text_is_formal(self) -> None:
        self.assertEqual(
            self.line("de", greeting_style=GreetingStyle.CUSTOM, salutation="Frau", last_name="Berg"),
            "Sehr geehrte Frau Berg,",
        )

    def test_the_language_follows_the_documents_unless_given(self) -> None:
        saved = Contact(customer=self.customer, salutation="Frau", last_name="Berg")
        self.assertEqual(greetings.greeting(saved), "Sehr geehrte Frau Berg,")
        from rentalars.core.models import CompanyProfile

        CompanyProfile.objects.update_or_create(pk=1, defaults={"document_language": "en"})
        self.assertEqual(greetings.greeting(saved), "Dear Ms Berg,")

    def test_the_interface_language_does_not_change_the_line(self) -> None:
        saved = Contact(customer=self.customer, salutation="Frau", last_name="Berg")
        with translation.override("en"):
            self.assertEqual(greetings.greeting(saved, "de"), "Sehr geehrte Frau Berg,")

    def test_generic_greeting(self) -> None:
        self.assertEqual(greetings.generic_greeting("de"), "Guten Tag,")
        self.assertEqual(greetings.generic_greeting("en"), "Hello,")

    def test_the_language_of_a_mail_is_guessed(self) -> None:
        self.assertEqual(
            greetings.guess_language("Vielen Dank für Ihre Anfrage, wir schicken Ihnen das Angebot."), "de"
        )
        self.assertEqual(greetings.guess_language("Thank you for your request, we will send you the quote."), "en")
        self.assertEqual(greetings.guess_language("???", default="en"), "en")

    def test_a_contact_is_found_by_its_address(self) -> None:
        found = contact(self.customer, name="Anna Berg", email="Anna@Kulturamt.example")
        other = contact(make_customer("Anderer"), name="Zweite Berg", email="anna@kulturamt.example")
        self.assertEqual(greetings.contact_for_address("anna@kulturamt.example", customer_id=self.customer.pk), found)
        self.assertEqual(greetings.contact_for_address("anna@kulturamt.example", customer_id=other.customer_id), other)
        self.assertIsNone(greetings.contact_for_address("niemand@example.org"))
        self.assertIsNone(greetings.contact_for_address(""))


class ContactPageTests(UiTestCase):
    """The page of a contact: first and last name, salutation suggestions, greeting with preview."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")
        self.url = reverse("customers:contact_create", args=[self.customer.pk])

    def test_the_form_has_the_fields_in_order(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        order = ["salutation", "first_name", "last_name", "position", "email", "phone", "is_primary", "greeting_style"]
        positions = [page.index(f'name="{name}"') for name in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('name="name"', page)
        self.assertIn('<datalist id="salutation-suggestions">', page)
        self.assertIn('list="salutation-suggestions"', page)
        self.assertIn("Anrede in E-Mails", page)
        self.assertIn('data-show-if="greeting_style=custom"', page)

    def test_create_with_first_and_last_name(self) -> None:
        data = form_data(
            self.client.get(self.url),
            salutation="Frau",
            first_name="Anna",
            last_name="Berg",
            greeting_style="personal",
        )
        self.client.post(self.url, data)
        saved = Contact.objects.get()
        self.assertEqual((saved.name, saved.first_name, saved.last_name), ("Anna Berg", "Anna", "Berg"))
        self.assertEqual(saved.greeting_style, "personal")
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))
        self.assertIn("Anna Berg", page)
        self.assertIn("Hallo Anna,", page)  # the contact list shows the greeting

    def test_the_last_name_is_required_the_first_is_not(self) -> None:
        response = self.client.post(self.url, form_data(self.client.get(self.url), first_name="Anna", last_name=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Contact.objects.exists())
        self.assertEqual(response.content.decode().count("Dieses Feld ist zwingend erforderlich"), 1)
        self.client.post(self.url, form_data(self.client.get(self.url), first_name="", last_name="Berg"))
        self.assertEqual(Contact.objects.get().name, "Berg")

    def test_the_own_greeting_must_be_typed(self) -> None:
        data = form_data(self.client.get(self.url), last_name="Berg", greeting_style="custom", greeting_text="")
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Gib die Anrede ein", page)
        self.assertFalse(Contact.objects.exists())
        data["greeting_text"] = "Liebe Anna,"
        self.client.post(self.url, data)
        self.assertEqual(Contact.objects.get().greeting_text, "Liebe Anna,")

    def test_editing_shows_the_greeting_and_keeps_old_contacts_working(self) -> None:
        old = contact(self.customer, salutation="Herr", name="Jan Berg")
        url = reverse("customers:contact_edit", args=[self.customer.pk, old.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Vorschau:", page)
        self.assertIn("Sehr geehrter Herr Berg,", page)
        self.client.post(url, form_data(self.client.get(url), email="jan@example.org"))
        old.refresh_from_db()
        self.assertEqual((old.email, old.name), ("jan@example.org", "Jan Berg"))

    def test_the_preview_fragment(self) -> None:
        url = reverse("customers:greeting_preview")
        page = self.assert_ok(self.client.get(url, {"salutation": "Frau", "first_name": "Anna", "last_name": "Berg"}))
        self.assertIn("Vorschau:", page)
        self.assertIn("Sehr geehrte Frau Berg,", page)
        page = self.assert_ok(
            self.client.get(url, {"first_name": "Anna", "last_name": "Berg", "greeting_style": "personal"})
        )
        self.assertIn("Hallo Anna,", page)
        page = self.assert_ok(
            self.client.get(
                url, {"last_name": "Berg", "greeting_style": "custom", "greeting_text": "Liebe <b>Anna</b>,"}
            )
        )
        self.assertIn("Liebe &lt;b&gt;Anna&lt;/b&gt;,", page)  # escaped
        self.assertNotIn("Vorschau:", self.assert_ok(self.client.get(url)))  # nothing typed yet

    def test_the_preview_needs_the_right_to_write_customers(self) -> None:
        from tests.helpers import make_user

        reader = self.browser_of(make_user("lena", roles=("Technik",)))
        self.assertEqual(reader.get(reverse("customers:greeting_preview")).status_code, 403)


class ContactApiTests(ApiTestCase):
    """The API keeps ``name`` for old clients and knows first and last name and the greeting."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")
        self.url = f"{API}/customers/{self.customer.pk}/contacts"

    def test_old_style_create_with_only_a_name(self) -> None:
        response = self.admin.post(self.url, {"name": "Anna Maria Berg", "email": "a@example.org"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            (response.data["name"], response.data["first_name"], response.data["last_name"]),
            ("Anna Maria Berg", "Anna Maria", "Berg"),
        )
        self.assertEqual(response.data["greeting_style"], "formal")
        self.assertEqual(response.data["greeting"], "Guten Tag Anna Maria Berg,")

    def test_new_style_create(self) -> None:
        response = self.admin.post(
            self.url,
            {
                "salutation": "Frau",
                "first_name": "Anna",
                "last_name": "Berg",
                "greeting_style": "custom",
                "greeting_text": "Liebe Anna,",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["name"], "Anna Berg")
        self.assertEqual(response.data["greeting"], "Liebe Anna,")

    def test_the_parts_win_over_a_name_sent_with_them(self) -> None:
        response = self.admin.post(
            self.url, {"name": "Egal Wer", "first_name": "Anna", "last_name": "Berg"}, format="json"
        )
        self.assertEqual((response.data["first_name"], response.data["last_name"]), ("Anna", "Berg"))
        self.assertEqual(response.data["name"], "Anna Berg")

    def test_a_contact_needs_a_last_name(self) -> None:
        response = self.admin.post(self.url, {"first_name": "Anna"}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.admin.post(self.url, {}, format="json").status_code, 400)

    def test_old_style_update_by_name(self) -> None:
        saved = contact(self.customer, first_name="Anna", last_name="Berg")
        url = f"{self.url}/{saved.pk}"
        response = self.admin.patch(url, {"name": "Anna Bergmann"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["first_name"], response.data["last_name"]), ("Anna", "Bergmann"))
        # A PUT that sends back the name it read, with a changed phone number, changes no name.
        put = self.admin.put(url, {"name": "Anna Bergmann", "phone": "123"}, format="json")
        self.assertEqual(put.status_code, 200, put.data)
        self.assertEqual(
            (put.data["first_name"], put.data["last_name"], put.data["phone"]), ("Anna", "Bergmann", "123")
        )

    def test_new_style_update(self) -> None:
        saved = contact(self.customer, name="Anna Berg")
        response = self.admin.patch(f"{self.url}/{saved.pk}", {"first_name": "Anne"}, format="json")
        self.assertEqual((response.data["name"], response.data["last_name"]), ("Anne Berg", "Berg"))
        listed = self.admin.get(self.url).data
        self.assertEqual([row["name"] for row in listed], ["Anne Berg"])
        one = self.admin.get(f"{self.url}/{saved.pk}")
        self.assertEqual(one.data["greeting"], "Guten Tag Anne Berg,")

    def test_an_invalid_style_is_refused(self) -> None:
        saved = contact(self.customer, name="Anna Berg")
        response = self.admin.patch(f"{self.url}/{saved.pk}", {"greeting_style": "shouting"}, format="json")
        self.assertEqual(response.status_code, 400)


class ImportExportTests(RentalarsTestCase):
    """First and last name through the customer import and its export format."""

    def import_rows(self, header: list[str], *rows: list[str]) -> Any:
        table = Table(headers=header, rows=[list(row) for row in rows])
        kind = imports.get("customers")
        mapping = resolve_mapping(table.headers, {}, kind.fields)
        from rentalars.accounts.models import User

        user = User.objects.filter(is_superuser=True).first() or make_user_super()
        return imports.run(kind, table, mapping, dry_run=False, user=user)

    def test_contact_first_and_last_name_columns(self) -> None:
        report = self.import_rows(
            ["Name", "Ansprechperson Vorname", "Ansprechperson Nachname", "Anrede"],
            ["Kulturamt", "Anna", "Berg", "Frau"],
        )
        self.assertTrue(report.ok, report.errors)
        saved = Contact.objects.get()
        self.assertEqual(
            (saved.first_name, saved.last_name, saved.name, saved.salutation), ("Anna", "Berg", "Anna Berg", "Frau")
        )

    def test_only_a_name_is_split(self) -> None:
        self.import_rows(["Name", "Ansprechperson"], ["Kulturamt", "Jan van der Berg"])
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name), ("Jan", "van der Berg"))

    def test_lexware_style_first_and_last_name_columns(self) -> None:
        self.import_rows(
            ["Firmenname", "Ansprechpartner 1 Vorname", "Ansprechpartner 1 Nachname", "Ansprechpartner 1 E-Mail"],
            ["Kulturverein", "Eva", "von Müller", "eva@verein.example"],
        )
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name, saved.name), ("Eva", "von Müller", "Eva von Müller"))

    def test_company_row_with_first_and_last_name_is_the_contact(self) -> None:
        self.import_rows(["Firmenname", "Vorname", "Nachname"], ["Kulturverein", "Eva", "Müller"])
        self.assertEqual(Contact.objects.get().last_name, "Müller")

    def test_a_second_import_completes_a_first_name_but_never_replaces_a_name(self) -> None:
        customer = make_customer("Kulturamt")
        contact(customer, last_name="Berg", email="b@kulturamt.example")
        header = ["Name", "Ansprechperson Vorname", "Ansprechperson Nachname", "E-Mail der Ansprechperson"]
        self.import_rows(header, ["Kulturamt", "Anna", "Berg", "b@kulturamt.example"])
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name, saved.name), ("Anna", "Berg", "Anna Berg"))
        self.import_rows(header, ["Kulturamt", "Zoe", "Berg", "b@kulturamt.example"])
        self.assertEqual(Contact.objects.get().first_name, "Anna")

    def test_export_has_the_parts_and_round_trips(self) -> None:
        customer = make_customer("Kulturamt")
        contact(customer, salutation="Frau", first_name="Anna", last_name="Berg", email="a@kulturamt.example")
        contact(customer, first_name="Jan", last_name="van der Berg")
        contact(customer, name="Pat Kurz")
        contact(customer, last_name="Allein")
        text = text_of("customers")
        row = records(text)[0]
        self.assertEqual(
            (row["Ansprechperson"], row["Ansprechperson Vorname"], row["Ansprechperson Nachname"]),
            ("Anna Berg", "Anna", "Berg"),
        )
        self.assertEqual((row["Ansprechpartner 1 Vorname"], row["Ansprechpartner 1 Nachname"]), ("", "Allein"))
        self.assertEqual((row["Ansprechpartner 2 Vorname"], row["Ansprechpartner 2 Nachname"]), ("Pat", "Kurz"))
        kind = imports.get("customers")
        table = table_of(text)
        mapping = resolve_mapping(table.headers, {}, kind.fields)
        report = imports.run(kind, table, mapping, dry_run=True, user=make_user_super()).as_dict()
        self.assertEqual(report["row_counts"], {"new": 0, "changed": 0, "unchanged": 1, "error": 0}, report["rows"])
        self.assertIsNotNone(import_exports.get("customers"))


def make_user_super() -> Any:
    from tests.helpers import make_user

    return make_user("importer095", superuser=True)


class LexwareBodyTests(RentalarsTestCase):
    """The contact handed to Lexware Office carries the stored first and last name."""

    def test_first_and_last_name_are_handed_over(self) -> None:
        customer = make_customer("Kulturverein e. V.")
        contact(customer, salutation="Frau", first_name="Eva Maria", last_name="von Müller")
        person = contact_body(customer)["company"]["contactPersons"][0]
        self.assertEqual((person["firstName"], person["lastName"]), ("Eva Maria", "von Müller"))

    def test_a_last_name_alone(self) -> None:
        customer = make_customer("Kulturverein e. V.")
        contact(customer, last_name="Müller")
        person = contact_body(customer)["company"]["contactPersons"][0]
        self.assertEqual(person["lastName"], "Müller")
        self.assertNotIn("firstName", person)


class AnonymisingTests(RentalarsTestCase):
    """Anonymising a customer erases the parts of the names and the own greetings, in the data and in the log."""

    def test_nothing_of_the_contacts_stays(self) -> None:
        customer = make_customer("Miriam Krause")
        saved = contact(
            customer, first_name="Miriam", last_name="Krause", greeting_style="custom", greeting_text="Liebe Miriam,"
        )
        saved.greeting_text = "Liebe Miri,"
        saved.save()
        anonymise_customer(customer)
        self.assertFalse(Contact.objects.exists())
        for entry in AuditLogEntry.objects.filter(content_type__model="contact"):
            self.assertEqual(entry.changes, {})
            self.assertNotIn("Krause", entry.object_repr)
        self.assertNotIn(
            "Miriam", str(list(AuditLogEntry.objects.values_list("changes", "object_repr"))).replace("Anonym", "")
        )

    def test_the_information_for_a_person_names_the_parts_and_the_greeting(self) -> None:
        customer = make_customer("Miriam Krause")
        contact(customer, first_name="Miriam", last_name="Krause", greeting_style="personal")
        shown = export_customer(customer)["contacts"][0]  # type: ignore[index]
        self.assertEqual(
            (shown["first_name"], shown["last_name"], shown["greeting_style"]),  # type: ignore[index]
            ("Miriam", "Krause", "Persönlich mit Vorname (Hallo Anna)"),
        )


class MailFormTests(UiTestCase):
    """The mail form begins with the greeting of the contact the mail goes to."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")
        self.contact = contact(
            self.customer, salutation="Frau", first_name="Anna", last_name="Berg", email="anna@kulturamt.example"
        )
        self.project = make_project("Stadtfest", customer=self.customer)
        self.project.contact = self.contact
        self.project.save()
        self.url = reverse("mail:compose", args=[self.project.pk])

    def body_of(self, page: str) -> str:
        import html
        import re

        match = re.search(r'<textarea[^>]*name="body"[^>]*>(.*?)</textarea>', page, re.S)
        assert match, "no body field"
        return html.unescape(match.group(1)).lstrip("\n")

    def test_a_new_mail_to_the_project_contact_starts_with_the_greeting(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertTrue(self.body_of(page).startswith("Sehr geehrte Frau Berg,\n\n"), self.body_of(page))

    def test_the_greeting_follows_the_contact_setting(self) -> None:
        self.contact.greeting_style = "personal"
        self.contact.save()
        self.assertTrue(self.body_of(self.assert_ok(self.client.get(self.url))).startswith("Hallo Anna,"))

    def test_an_answer_starts_with_the_greeting_before_the_quote(self) -> None:
        mail = test_083_ai.add_mail(
            self.project,
            "Angebot",
            "Vielen Dank, bitte schicken Sie uns das Angebot.",
            sender=("A. Berg", "anna@kulturamt.example"),
        )
        page = self.assert_ok(self.client.get(self.url, {"answer": mail.pk}))
        body = self.body_of(page)
        self.assertTrue(body.startswith("Sehr geehrte Frau Berg,\n\n\n"), body)
        self.assertIn("> Vielen Dank", body)
        self.assertEqual(body.count("Sehr geehrte"), 1)

    def test_the_form_and_the_ai_draft_use_the_same_first_line(self) -> None:
        """KND-011 (contacts): the draft is put above the text; the page script drops the greeting of the text
        when the draft starts with the same line, so the mail greets once. That needs the same line on both sides."""
        mail = test_083_ai.add_mail(
            self.project,
            "Angebot",
            "Vielen Dank, bitte schicken Sie uns das Angebot.",
            sender=("A. Berg", "anna@kulturamt.example"),
        )
        first_line = self.body_of(self.assert_ok(self.client.get(self.url, {"answer": mail.pk}))).splitlines()[0]
        self.assertEqual(first_line, drafts.greeting_for(self.project, mail))
        self.assertIn("do not greet a second time", drafts.GREETING_RULE)

    def test_the_page_script_takes_a_doubled_greeting_out(self) -> None:
        import pathlib
        import shutil
        import subprocess
        import tempfile

        script = pathlib.Path(__file__).resolve().parents[2] / "static" / "js" / "app.js"
        source = script.read_text(encoding="utf-8")
        self.assertIn("data-ai-take-draft", source)
        self.assertIn('current.split("\\n", 1)[0].trim() === greeting', source)
        node = shutil.which("node")
        if node is None:
            return
        # The take-over, run against a text with the greeting and the quote, as the page holds it.
        start = source.index("take the reply draft by AI over")
        block = source[source.index("(function () {", start) : source.index("})();", start) + 5]
        harness = (
            "var assert = require('assert');\n"
            "var listeners = {};\n"
            "var source = {value: 'Sehr geehrte Frau Berg,\\n\\nvielen Dank.'};\n"
            "var target = {value: 'Sehr geehrte Frau Berg,\\n\\n\\nAm 1. schrieb Anna:\\n> Hallo',"
            " dispatchEvent: function () {}, focus: function () {}, setSelectionRange: function () {}};\n"
            "global.document = {addEventListener: function (t, f) { listeners[t] = f; },"
            " getElementById: function (id) { return id === 'd' ? source : target; },"
            " querySelector: function () { return null; }};\n"
            "global.Event = function () {};\n"
            "var button = {getAttribute: function (n) { return n === 'data-ai-take-draft' ? 'd' : 't'; }};\n"
            + block
            + "\nlisteners.click({target: {closest: function () { return button; }}});\n"
            "assert.strictEqual(target.value,"
            " 'Sehr geehrte Frau Berg,\\n\\nvielen Dank.\\n\\nAm 1. schrieb Anna:\\n> Hallo');\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            file = pathlib.Path(directory) / "take_draft.js"
            file.write_text(harness, encoding="utf-8")
            result = subprocess.run([node, str(file)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_english_mail_gets_the_english_greeting(self) -> None:
        mail = test_083_ai.add_mail(
            self.project,
            "Quote",
            "Thank you for your request, please send us the quote.",
            sender=("A. Berg", "anna@kulturamt.example"),
        )
        body = self.body_of(self.assert_ok(self.client.get(self.url, {"answer": mail.pk})))
        self.assertTrue(body.startswith("Dear Ms Berg,"), body)

    def test_an_unknown_recipient_changes_nothing(self) -> None:
        mail = test_083_ai.add_mail(
            self.project, "Angebot", "Hallo, bitte das Angebot.", sender=("Fremd", "fremd@example.org")
        )
        body = self.body_of(self.assert_ok(self.client.get(self.url, {"answer": mail.pk})))
        self.assertNotIn("Sehr geehrte", body)
        self.assertTrue(body.startswith("On ") or body.startswith("Am "), body)

    def test_a_project_without_contact_has_an_empty_body(self) -> None:
        self.project.contact = None
        self.project.save()
        self.assertEqual(self.body_of(self.assert_ok(self.client.get(self.url))).strip(), "")


class DraftPromptTests(test_083_ai.AITestCase):
    """The reply draft of the AI is told the greeting to use."""

    def system_prompt(self) -> str:
        return self.fake.chats[-1]["messages"][0]["content"]

    def run_draft(self) -> None:
        self.install_local()
        self.use("draft", Source.LOCAL)
        job = drafts.start(self.project, user=self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, "done", job.message)

    def test_the_prompt_names_the_greeting_of_the_contact(self) -> None:
        contact(
            self.project.customer,
            salutation="Frau",
            first_name="Jana",
            last_name="Berg",
            email="jana@kulturamt.example",
        )
        self.run_draft()
        self.assertIn("Begin the mail with exactly this greeting", self.system_prompt())
        self.assertIn("Sehr geehrte Frau Berg,", self.system_prompt())

    def test_a_personal_or_own_greeting_is_passed_verbatim(self) -> None:
        saved = contact(self.project.customer, first_name="Jana", last_name="Berg", email="jana@kulturamt.example")
        Contact.objects.filter(pk=saved.pk).update(greeting_style="custom", greeting_text="Liebe Jana,")
        self.run_draft()
        self.assertIn("Liebe Jana,", self.system_prompt())

    def test_without_a_known_contact_the_prompt_has_no_greeting_rule(self) -> None:
        self.run_draft()
        self.assertNotIn("exactly this greeting", self.system_prompt())

    def test_the_greeting_is_in_the_language_of_the_mail_answered(self) -> None:
        contact(self.project.customer, salutation="Frau", last_name="Berg", email="jana@kulturamt.example")
        test_083_ai.add_mail(self.project, "Quote", "Thank you for your request, please send us the quote.", days=3)
        self.run_draft()
        self.assertIn("Dear Ms Berg,", self.system_prompt())


class PlaceholderTests(RentalarsTestCase):
    """``{greeting}`` / ``{anrede}`` in the texts of documents and in automatic answers."""

    def test_documents_fill_the_greeting_of_the_projects_contact(self) -> None:
        customer = make_customer("Kulturamt")
        project = make_project("Stadtfest", customer=customer)
        values = document_content.placeholder_values(project)
        self.assertEqual((values["greeting"], values["anrede"]), ("", ""))
        project.contact = contact(customer, salutation="Herr", first_name="Jan", last_name="Berg")
        project.save()
        values = document_content.placeholder_values(project)
        self.assertEqual(
            document_content.fill("{greeting}\nText {project}", values).splitlines()[0], "Sehr geehrter Herr Berg,"
        )
        self.assertEqual(values["anrede"], "Sehr geehrter Herr Berg,")

    def test_the_inquiry_automation_offers_and_fills_the_placeholder(self) -> None:
        tokens = [token for token, _label in engine.placeholders_of(engine.Trigger.INQUIRY)]
        self.assertIn("{anrede}", tokens)
        with translation.override("en"):
            self.assertIn("{greeting}", [token for token, _label in engine.placeholders_of(engine.Trigger.INQUIRY)])
        customer = make_customer("Kulturamt")
        contact(customer, salutation="Frau", last_name="Berg", email="anna@kulturamt.example")
        self.assertEqual(engine._greeting_of_sender("anna@kulturamt.example"), "Sehr geehrte Frau Berg,")
        self.assertEqual(engine._greeting_of_sender("fremd@example.org"), "Guten Tag,")
        self.assertEqual(engine.fill("{greeting} danke", {"anrede": "Hallo,"}), "Hallo, danke")


class EverythingAboutAContactUsesTheFullName(RentalarsTestCase):
    """The contact shown in projects, documents and mail recipients stays the full name."""

    def test_the_full_name_is_what_the_rest_of_rentalars_reads(self) -> None:
        from rentalars.mail.addresses import customer_recipient

        customer = make_customer("Kulturamt")
        project = make_project("Stadtfest", customer=customer)
        project.contact = contact(customer, first_name="Anna", last_name="Berg", email="anna@kulturamt.example")
        project.save()
        self.assertEqual(document_content.project_data(project)["contact"], "Anna Berg")
        self.assertIn("Anna Berg", customer_recipient(project))


class ReviewContactNameTests(RentalarsTestCase):
    """KND-011 (contacts): findings of the review about the lengths of names and the rule that splits them."""

    LONG_WORD = "B" * 150
    LONG_PART = "Anna " + "B" * 140

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")

    def test_a_bare_name_brings_its_salutation_and_remark(self) -> None:
        saved = contact(self.customer, name="Frau Anna Berg, Technik")
        self.assertEqual(
            (saved.first_name, saved.last_name, saved.name, saved.salutation, saved.position),
            ("Anna", "Berg", "Anna Berg", "Frau", "Technik"),
        )

    def test_a_salutation_or_position_that_exists_is_kept(self) -> None:
        saved = contact(self.customer, name="Herr Jan Berg (Technik), Leiter", salutation="Dr.", position="Chef")
        self.assertEqual((saved.name, saved.salutation, saved.position), ("Jan Berg", "Dr.", "Chef"))

    def test_the_migration_does_not_stop_at_names_longer_than_the_columns(self) -> None:
        """MariaDB would refuse 150 characters for a column of 100 (error 1406) and stop the upgrade."""
        Contact.objects.bulk_create(
            [
                Contact(customer=self.customer, name=self.LONG_WORD),
                Contact(customer=self.customer, name=self.LONG_PART),
                Contact(customer=self.customer, name="Anna Berg"),
            ]
        )
        migration_0009.split_names(apps, None)
        saved = {c.name: c for c in Contact.objects.all()}
        self.assertEqual(sorted(saved), sorted([self.LONG_WORD, self.LONG_PART, "Anna Berg"]))  # names are untouched
        for name in (self.LONG_WORD, self.LONG_PART):
            self.assertEqual((saved[name].first_name, saved[name].last_name), ("", name[:100]))
        self.assertEqual((saved["Anna Berg"].first_name, saved["Anna Berg"].last_name), ("Anna", "Berg"))
        for one in saved.values():
            self.assertLessEqual(len(one.first_name), 100)
            self.assertLessEqual(len(one.last_name), 100)

    def test_backward_keeps_the_long_names_it_had_split_in_a_fallback(self) -> None:
        """The update test (20,000 contacts): the way back cut a 150-character name to the 100 of its part."""
        Contact.objects.bulk_create(
            [Contact(customer=self.customer, name=self.LONG_WORD), Contact(customer=self.customer, name=self.LONG_PART)]
        )
        migration_0009.split_names(apps, None)
        migration_0009.join_names(apps, None)
        self.assertEqual(
            sorted(c.name for c in Contact.objects.filter(name__in=[self.LONG_WORD, self.LONG_PART])),
            sorted([self.LONG_WORD, self.LONG_PART]),
        )

    def test_the_migration_keeps_salutation_and_remark_of_the_name(self) -> None:
        Contact.objects.bulk_create(
            [
                Contact(customer=self.customer, name="Frau Eva Berg, Technik"),
                Contact(customer=self.customer, name="Herr Max Moor, Technik", salutation="Dr.", position="Chef"),
            ]
        )
        migration_0009.split_names(apps, None)
        eva = Contact.objects.get(name="Frau Eva Berg, Technik")
        self.assertEqual(
            (eva.first_name, eva.last_name, eva.salutation, eva.position), ("Eva", "Berg", "Frau", "Technik")
        )
        max_ = Contact.objects.get(name="Herr Max Moor, Technik")
        self.assertEqual((max_.salutation, max_.position), ("Dr.", "Chef"))

    def test_the_backward_step_never_writes_more_than_the_name_takes(self) -> None:
        Contact.objects.bulk_create(
            [Contact(customer=self.customer, name="x", first_name="A" * 100, last_name="B" * 100)]
        )
        migration_0009.join_names(apps, None)
        self.assertEqual(len(Contact.objects.get().name), 200)

    def test_the_migration_has_its_own_copy_of_the_rule(self) -> None:
        """A migration must do the same on every installation, whatever the live rule becomes."""
        source = pathlib.Path(migration_0009.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from rentalars", source)
        self.assertNotIn("import rentalars", source)

    def test_first_and_last_name_together_must_fit_the_full_name(self) -> None:
        too_long = Contact(customer=self.customer, first_name="A" * 100, last_name="B" * 100)
        with self.assertRaises(ValidationError) as caught:
            too_long.full_clean()
        self.assertIn("last_name", caught.exception.message_dict)
        fits = Contact(customer=self.customer, first_name="A" * 99, last_name="B" * 100)
        fits.full_clean()
        fits.save()
        self.assertEqual(len(fits.name), 200)

    def test_a_long_bare_name_is_refused_not_cut(self) -> None:
        for name in (self.LONG_WORD, self.LONG_PART):
            with self.subTest(name=name[:8]), self.assertRaises(ValidationError):
                Contact(customer=self.customer, name=name).full_clean()

    def test_the_form_names_the_problem(self) -> None:
        from rentalars.customers.forms import ContactForm

        form = ContactForm(
            {"first_name": "A" * 100, "last_name": "B" * 100, "greeting_style": "formal"},
            instance=Contact(customer=self.customer),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("last_name", form.errors)
        long = ContactForm(
            {"last_name": "B" * 101, "greeting_style": "formal"}, instance=Contact(customer=self.customer)
        )
        self.assertFalse(long.is_valid())

    def test_an_own_greeting_must_be_typed_in_the_model_too(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            Contact(customer=self.customer, last_name="Berg", greeting_style="custom", greeting_text="  ").full_clean()
        self.assertIn("greeting_text", caught.exception.message_dict)
        Contact(
            customer=self.customer, last_name="Berg", greeting_style="custom", greeting_text="Liebe Anna,"
        ).full_clean()

    def test_the_form_shows_the_missing_greeting_once(self) -> None:
        from rentalars.customers.forms import ContactForm

        form = ContactForm(
            {"last_name": "Berg", "greeting_style": "custom", "greeting_text": ""},
            instance=Contact(customer=self.customer),
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors["greeting_text"]), 1)


class ReviewContactApiTests(ApiTestCase):
    """The API refuses what the browser refuses and handles long names without a server error."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturamt")
        self.url = f"{API}/customers/{self.customer.pk}/contacts"

    def test_long_names_are_a_400(self) -> None:
        for body in (
            {"name": "B" * 150},
            {"name": "Anna " + "B" * 140},
            {"first_name": "A" * 100, "last_name": "B" * 100},
            {"first_name": "A" * 101, "last_name": "Berg"},
        ):
            with self.subTest(body=list(body)):
                response = self.admin.post(self.url, body, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Contact.objects.exists())

    def test_the_longest_name_that_fits_is_accepted(self) -> None:
        response = self.admin.post(self.url, {"first_name": "A" * 99, "last_name": "B" * 100}, format="json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_an_own_greeting_without_text_is_a_400(self) -> None:
        response = self.admin.post(
            self.url, {"last_name": "Berg", "greeting_style": "custom", "greeting_text": ""}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "greeting_text")
        saved = contact(self.customer, last_name="Berg")
        again = self.admin.patch(f"{self.url}/{saved.pk}", {"greeting_style": "custom"}, format="json")
        self.assert_error(again, 400, "validation_error", "greeting_text")

    def test_a_bare_name_with_salutation_and_remark(self) -> None:
        response = self.admin.post(self.url, {"name": "Herr Jan Berg, Technik"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            (response.data["first_name"], response.data["last_name"], response.data["salutation"]),
            ("Jan", "Berg", "Herr"),
        )
        self.assertEqual((response.data["name"], response.data["position"]), ("Jan Berg", "Technik"))


class ReviewContactImportTests(RentalarsTestCase):
    """KND-011 (contacts): partial name columns in the customer import."""

    def import_rows(self, header: list[str], *rows: list[str]) -> Any:
        return ImportExportTests.import_rows(self, header, *rows)  # type: ignore[arg-type]

    def test_a_first_name_alone_is_the_contact_as_in_0_9_4(self) -> None:
        report = self.import_rows(
            ["Firmenname", "Ansprechpartner 1 Vorname"],
            ["Kulturverein", "Anna"],
        )
        self.assertTrue(report.ok, report.errors)
        saved = Contact.objects.get()
        self.assertEqual((saved.name, saved.first_name, saved.last_name), ("Anna", "", "Anna"))

    def test_a_first_name_alone_in_a_file_with_other_good_rows(self) -> None:
        report = self.import_rows(
            ["Firmenname", "Ansprechpartner 1 Vorname", "Ansprechpartner 1 Nachname"],
            ["Kulturverein", "Anna", ""],
            ["Stadtwerke", "Eva", "Müller"],
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(sorted(Contact.objects.values_list("name", flat=True)), ["Anna", "Eva Müller"])

    def test_a_first_name_alone_with_the_whole_name_in_the_heading(self) -> None:
        report = self.import_rows(
            ["Firmenname", "Ansprechpartner 1", "Ansprechpartner 1 Vorname"], ["Kulturverein", "Anna Berg", "Anna"]
        )
        self.assertTrue(report.ok, report.errors)
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name), ("Anna", "Berg"))

    def test_a_missing_first_name_is_read_from_the_full_name(self) -> None:
        report = self.import_rows(
            ["Name", "Ansprechperson", "Ansprechperson Vorname", "Ansprechperson Nachname"],
            ["Kulturamt", "Anna Berg", "", "Berg"],
        )
        self.assertTrue(report.ok, report.errors)
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name, saved.name), ("Anna", "Berg", "Anna Berg"))

    def test_a_missing_last_name_is_read_from_the_full_name(self) -> None:
        self.import_rows(
            ["Name", "Ansprechperson", "Ansprechperson Vorname", "Ansprechperson Nachname"],
            ["Kulturamt", "Anna Maria van Berg", "Anna Maria", ""],
        )
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name), ("Anna Maria", "van Berg"))

    def test_a_part_that_does_not_belong_to_the_full_name_is_not_guessed_from_it(self) -> None:
        self.import_rows(["Name", "Ansprechperson", "Ansprechperson Nachname"], ["Kulturamt", "Anna Berg", "Moor"])
        saved = Contact.objects.get()
        self.assertEqual((saved.first_name, saved.last_name), ("", "Moor"))

    def test_a_name_too_long_for_a_contact_is_a_row_error_not_a_crash(self) -> None:
        report = self.import_rows(
            ["Name", "Ansprechperson", "Anrede"], ["Kulturamt", "Anna " + "B" * 140, ""], ["Stadtwerke", "Eva Moor", ""]
        )
        self.assertFalse(Contact.objects.filter(name__startswith="Anna B").exists())
        self.assertTrue(report.as_dict()["rows"])


class ReviewAnonymisingDraftsTests(RentalarsTestCase):
    """KND-011 / DOK-022: anonymising a customer leaves no personal data in the log of its drafts."""

    def test_the_log_of_drafts_and_their_lines_is_scrubbed(self) -> None:
        from rentalars.documents import free
        from rentalars.documents.models import DocumentKind

        customer = make_customer("Miriam Krause")
        draft = free.create_draft(customer, DocumentKind.OFFER, reference="Geburtstag Miriam Krause")
        free.update_draft(draft, introduction="Liebe Miriam Krause")
        line = free.add_line(draft, title="Torte für Miriam", note="Allergie: Nüsse", unit_price=Decimal("5"))
        free.update_line(line, note="Allergie: Nüsse und Milch")
        gone = free.create_draft(customer, DocumentKind.OFFER, reference="Zweite Miriam")
        free.add_line(gone, title="Blumen Krause")
        free.delete_draft(gone)  # thrown away long before: its log entries stay
        before = str(list(AuditLogEntry.objects.values_list("object_repr", "changes")))
        self.assertIn("Miriam", before)  # the entries do hold the data now
        anonymise_customer(customer)
        for model in ("documentdraft", "draftline"):
            entries = AuditLogEntry.objects.filter(content_type__model=model)
            self.assertTrue(entries.exists(), model)
            for entry in entries:
                self.assertEqual(entry.changes, {}, (model, entry.object_repr))
                self.assertNotIn("Miriam", entry.object_repr)
                self.assertNotIn("Krause", entry.object_repr)
        everything = str(list(AuditLogEntry.objects.values_list("object_repr", "changes")))
        for word in ("Miriam", "Krause", "Torte", "Nüsse", "Blumen", "Geburtstag"):
            self.assertNotIn(word, everything.replace("Anonymisiert", ""), word)
