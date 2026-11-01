# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 19 – Verständlichkeit des Codes (catalogue chapter 11).

Three of the four statements can be checked by a machine and are checked
here. The fourth – a person with basic Python knowledge sets up a development
environment from the documentation without asking back – needs a person; the
test only makes sure that the guide exists and names the steps.
"""

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)

#: The scenarios of chapter 11 that belong to the stages built so far (1 to 5): all of them.
SCENARIOS_OF_BUILT_STAGES = tuple(range(1, 22))


def ruff(*arguments: str, text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run the style checker of the project."""
    executable = shutil.which("ruff") or str(Path(sys.executable).parent / "ruff")
    return subprocess.run([executable, *arguments], cwd=ROOT, input=text, capture_output=True, text=True, check=False)


class Scenario19CodeComprehensibility(SimpleTestCase):
    """NFA-055 to NFA-062."""

    def test_search_for_vfg_002_leads_to_the_availability_calculation(self) -> None:
        mentioning = [
            path.relative_to(ROOT).as_posix()
            for path in sorted((ROOT / "rentalars").rglob("*.py"))
            if "VFG-002" in path.read_text(encoding="utf-8")
        ]
        self.assertIn("rentalars/availability/engine.py", mentioning)

        description = ast.get_docstring(
            ast.parse((ROOT / "rentalars/availability/engine.py").read_text(encoding="utf-8"))
        )
        assert description is not None
        # The rule in words …
        self.assertIn("highest quantity reserved at the same time", description)
        # … with a worked example in numbers …
        self.assertRegex(description, r"(?s)stock is 9.*books 6.*3 are free")
        self.assertIn("short of 1", description)
        # … and the reason why the peak counts and not the sum.
        self.assertRegex(description, r"Why the \*peak\* and not the \*sum\*")
        self.assertIn("need six cables, not twelve", description)

    def test_the_rule_is_also_found_from_its_test(self) -> None:
        """NFA-057: the ID leads to the code *and* to the test."""
        tests = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").rglob("*.py"))
        self.assertIn("VFG-002", tests)

    def test_check_reports_a_function_without_description(self) -> None:
        """NFA-056."""
        undocumented = '"""A module."""\n\n\ndef price_of(line):\n    return line.quantity * line.unit_price\n'
        result = ruff("check", "--stdin-filename", "rentalars/projects/example.py", "-", text=undocumented)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("D103", result.stdout)

        documented = undocumented.replace("    return", '    """Return quantity times unit price."""\n    return')
        result = ruff("check", "--stdin-filename", "rentalars/projects/example.py", "-", text=documented)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_the_whole_code_passes_the_check(self) -> None:
        """Style, formatting and descriptions are uniform and checked automatically (NFA-062)."""
        result = ruff("check", ".")
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        formatting = ruff("format", "--check", ".")
        self.assertEqual(formatting.returncode, 0, formatting.stdout[-2000:])

    def test_every_scenario_of_the_built_stages_has_a_test_of_the_same_name(self) -> None:
        folder = ROOT / "tests" / "acceptance"
        for number in SCENARIOS_OF_BUILT_STAGES:
            files = list(folder.glob(f"test_scenario_{number:02d}_*.py"))
            self.assertEqual(len(files), 1, f"scenario {number}")
            source = files[0].read_text(encoding="utf-8")
            self.assertRegex(source, rf"class Scenario{number:02d}\w+\(", files[0].name)
            self.assertRegex(source, rf"Acceptance scenario {number} – ", files[0].name)

    def test_scenario_titles_match_the_catalogue(self) -> None:
        catalogue = (ROOT / "docs/anforderungen/Rentalars_Anforderungskatalog.md").read_text(encoding="utf-8")
        titles = dict(re.findall(r"^Szenario (\d+) – (.+)$", catalogue, flags=re.MULTILINE))
        for number in SCENARIOS_OF_BUILT_STAGES:
            source = next((ROOT / "tests" / "acceptance").glob(f"test_scenario_{number:02d}_*.py")).read_text(
                encoding="utf-8"
            )
            self.assertIn(f"Acceptance scenario {number} – {titles[str(number)]}", source)

    def test_code_is_english_and_uses_the_terms_of_the_translation_list(self) -> None:
        """NFA-061, catalogue 2.1: one thing has one name everywhere."""
        names = set()
        for path in (ROOT / "rentalars").rglob("*.py"):
            if "migrations" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ClassDef | ast.FunctionDef):
                    names.add(node.name)
        for expected in (
            "MaterialItem",
            "MaterialModel",
            "MaterialLine",
            "KitComponent",
            "RentalScale",
            "Packlist",
            "Group",
            "JobFunction",
            "CrewLine",
            "TimeEntry",
            "Absence",
        ):
            self.assertIn(expected, names)
        german = [
            name
            for name in names
            if re.search(
                r"(?i)exemplar|teilgruppe|zumiet|staffel|packliste|verfuegbar|kunde|funktion|stundensatz|zeiteintrag|freigabe|pauschale|abwesenheit|einsatz",
                name,
            )
        ]
        self.assertEqual(german, [])

    def test_developer_documentation_explains_setup_and_core_flows(self) -> None:
        """NFA-058."""
        guide = (ROOT / "docs/dev/getting-started.md").read_text(encoding="utf-8")
        for step in (
            "python3 -m venv",
            "pip install -r requirements-dev.txt",
            "manage.py migrate",
            "manage.py test",
            "manage.py runserver",
        ):
            self.assertIn(step, guide)
        for name in ("architecture.md", "data-model.md", "core-flows.md", "decisions.md", "traceability.md"):
            self.assertTrue((ROOT / "docs/dev" / name).is_file(), name)
        flows = (ROOT / "docs/dev/core-flows.md").read_text(encoding="utf-8")
        for topic in ("Availability", "Price calculation", "Import"):
            self.assertIn(topic, flows)
