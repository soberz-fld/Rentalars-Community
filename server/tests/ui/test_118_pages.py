# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages — operation and wording (B1 – B12) of the review."""

from __future__ import annotations

from django.urls import reverse

from rentalars.core.forms import SETTINGS_SECTIONS, SystemSettingsForm, settings_sections
from rentalars.core.models import CompanyProfile, SystemSettings
from tests.ui.base import UiTestCase, form_data


class SettingsInOneFormTests(UiTestCase):
    """B1: what is typed in one box is not lost by saving; B4: the settings come in sections."""

    def test_all_boxes_are_saved_with_one_button(self) -> None:
        url = reverse("core:company_settings")
        page = self.client.get(url)
        data = form_data(page, containing="company-name")
        self.assertIn("system-password_min_length", data)
        data.update({"form": "all", "company-phone": "030 123456", "system-password_min_length": "12"})
        self.assertRedirects(self.client.post(url, data), url)
        self.assertEqual(CompanyProfile.load().phone, "030 123456")
        self.assertEqual(SystemSettings.load().password_min_length, 12)

    def test_one_mistake_saves_nothing(self) -> None:
        url = reverse("core:company_settings")
        data = form_data(self.client.get(url), containing="company-name")
        data.update({"form": "all", "company-phone": "030 999", "system-password_min_length": "1"})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CompanyProfile.load().phone, "")
        self.assertContains(response, 'role="alert"')
        self.assertTrue(response.context["system_form"].errors)

    def test_there_is_one_save_button(self) -> None:
        html = self.client.get(reverse("core:company_settings")).content.decode()
        self.assertEqual(html.count("Alle Einstellungen speichern") + html.count("Save all settings"), 1)
        for old in (">Einstellungen speichern</button>", ">Save settings</button>", ">Save company data</button>"):
            self.assertNotIn(old, html)

    def test_every_field_is_in_a_section(self) -> None:
        form = SystemSettingsForm(instance=SystemSettings.load(), prefix="system")
        shown = [field.name for _id, _title, fields in settings_sections(form) for field in fields]
        self.assertCountEqual(shown, list(form.fields))
        self.assertEqual(len(shown), len(set(shown)))
        named = {name for _id, _title, names in SETTINGS_SECTIONS for name in names}
        self.assertEqual(named, set(form.fields), "a new setting belongs in a section of SETTINGS_SECTIONS")


class PluralTests(UiTestCase):
    """B2: one day is "1 Miettag", not "1 Miettage"; no text makes do with "(s)"."""

    def test_the_offer_says_one_rental_day(self) -> None:
        import datetime

        from rentalars.documents import content as content_builder
        from rentalars.documents.models import DocumentKind
        from tests.helpers import add_line, at, make_product, make_project

        one = make_project("Ein Tag", start=at(10, 8), end=at(10, 18))
        two = make_project("Zwei Tage", start=at(10, 8), end=at(11, 18))
        product = make_product("L-001", "Scheinwerfer", price="10.00")
        texts = []
        for project in (one, two):
            add_line(project, product, 1)
            content = content_builder.build_priced(
                project, DocumentKind.OFFER, title="Angebot", number="AN-1", issued_on=datetime.date(2027, 3, 1)
            )
            texts.append(" ".join(position.details for section in content.sections for position in section.positions))
        self.assertIn("1 Miettag", texts[0])
        self.assertNotIn("1 Miettage", texts[0])
        self.assertIn("2 Miettage", texts[1])

    def test_plural_of(self) -> None:
        from decimal import Decimal

        from rentalars.core.i18n import plural_of

        self.assertEqual(
            [plural_of(1), plural_of(Decimal("1.00")), plural_of(0), plural_of(2), plural_of("3")], [1, 1, 0, 2, 3]
        )
        self.assertEqual([plural_of(Decimal("1.5")), plural_of(None), plural_of("x")], [2, 2, 2])

    def test_no_message_is_written_with_brackets(self) -> None:
        """ "Position(en)", "item(s)": a text with a number says it right (``ngettext``), the bracket is no way out."""
        import ast
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2] / "rentalars"
        bracket = re.compile(r"[A-Za-zäöüß]\((?:s|en|n|e|er)\)(?![\w(])")
        # What is not a message: URLs, Python and file mask documentation.
        skip = re.compile(r"https?\(s\)|http\(s\)")
        found = []
        for path in root.rglob("*.py"):
            if "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    # Output of the commands is f-strings, not gettext calls: "3 task(s) run." is the same fault.
                    for part in node.values:
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            if bracket.search(part.value) and not skip.search(part.value):
                                found.append(f"{path.relative_to(root)}:{node.lineno}: {part.value[:70]}")
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name not in {
                    "_",
                    "gettext",
                    "gettext_lazy",
                    "pgettext",
                    "pgettext_lazy",
                    "ngettext",
                    "ngettext_lazy",
                }:
                    continue
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        if bracket.search(argument.value) and not skip.search(argument.value):
                            found.append(f"{path.relative_to(root)}:{node.lineno}: {argument.value[:70]}")
        for path in list((root.parent / "templates").rglob("*.html")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\{%\s*(?:translate|blocktranslate)[^%]*\w\((?:s|en|n)\)", line):
                    found.append(f"{path.name}:{number}")
        self.assertEqual(found, [])


class ConfirmationTests(UiTestCase):
    """B3: deleting, removing and cancelling asks first."""

    # Their buttons are built in Python (the form only sits below the table) and carry ``data-confirm`` there.
    BUTTON_IN_PYTHON = {
        ("templates/projects/templates.html", "projects:template_delete"),
        ("templates/automations/list.html", "automations:delete"),
    }

    def test_every_destructive_form_asks_first(self) -> None:
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2]
        pattern = re.compile(r"<form\b[^>]*?(?:action|hx-post)=\"\{% url '([\w:]+)'[^>]*>(.*?)</form>", re.S)
        words = re.compile(r"(delete|remove|cancel|anonym|revoke|clear)")
        found = []
        for path in sorted((root / "templates").rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            relative = str(path.relative_to(root))
            for match in pattern.finditer(text):
                name = match.group(1)
                if not words.search(name.split(":")[-1]) or (relative, name) in self.BUTTON_IN_PYTHON:
                    continue
                body = match.group(0)
                if "data-confirm" in body or "hx-confirm" in body:
                    continue
                tag = body[: body.index(">") + 1]
                identity = re.search(r"\bid=\"([^\"]+)\"", tag)
                if identity and re.search(
                    rf"form=\"{re.escape(identity.group(1))}\"[^>]*(?:data-confirm|hx-confirm)", text
                ):
                    continue
                found.append(f"{relative}:{text[: match.start()].count(chr(10)) + 1} {name}")
        self.assertEqual(found, [])

    def test_the_mass_takeover_asks_first(self) -> None:
        """Both ways to take over new product values in other records ask – and the product page names the number."""
        from decimal import Decimal

        from rentalars.projects.models import ProjectStatus
        from tests.helpers import add_line, make_project
        from tests.unit.test_051_lines import flat

        project = make_project("Hinterher", status=ProjectStatus.INQUIRY)
        lamp = flat("L-118", "20.00", name="Lampe")
        add_line(project, lamp, 4)
        lamp.price = Decimal("25.00")
        lamp.save()
        page = self.client.get(reverse("products:detail", args=[lamp.pk])).content.decode()
        panel = page[page.index('id="unconfirmed-changes"') :]
        panel = panel[: panel.index("</section>")]
        buttons = [part for part in panel.split("<button")[1:] if "Übernehmen" in part or "übernehmen" in part]
        self.assertGreaterEqual(len(buttons), 2)
        for part in buttons:
            self.assertIn("data-confirm=", part.split(">")[0])
        self.assertIn("in 1 Projekt übernehmen?", panel)
        planning = self.client.get(reverse("projects:detail", args=[project.pk]) + "?tab=planning").content.decode()
        self.assertIn("hx-confirm=", planning)
        self.assertIn("Die neuen Werte der Produkte in diesem Projekt übernehmen?", planning)
