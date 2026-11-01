# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks on the templates that no page test can make: mistakes that only show in a browser."""

import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from rentalars.core.warmup import set_startup_objects_aside, warm_up

TEMPLATES = Path(settings.BASE_DIR) / "templates"

#: An opening tag that sends a request through htmx.
REQUESTING_TAG = re.compile(r"<[a-z]+\b[^>]*?\bhx-(?:get|post)=[^>]*>", re.DOTALL)


class CommentTests(SimpleTestCase):
    """Notes for developers stay in the template and do not reach the page."""

    def test_no_short_comment_runs_over_several_lines(self) -> None:
        """``{# … #}`` is a comment only on one line; over two it is printed as text.

        The planning page once showed such a note to every user. Notes of
        several lines belong between ``{% comment %}`` and ``{% endcomment %}``.
        """
        broken = []
        for path in sorted(TEMPLATES.rglob("*")):
            if not path.is_file() or path.suffix not in {".html", ".txt"}:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if line.count("{#") != line.count("#}"):
                    broken.append(f"{path.relative_to(TEMPLATES)}:{number}")
        self.assertEqual(broken, [])


class WarmUpTests(TestCase):
    """NFA-012: the first request of a server process is not slower than the others."""

    def test_all_own_templates_are_loaded_without_touching_the_database(self) -> None:
        """A database connection opened before the server splits into workers would be shared by all of them."""
        own = [path for path in TEMPLATES.rglob("*") if path.is_file() and path.suffix in {".html", ".txt"}]
        with self.assertNumQueries(0):
            loaded = warm_up()
        self.assertEqual(loaded, len(own))
        self.assertGreater(loaded, 50)

    def test_the_server_warms_up_when_it_loads_the_application(self) -> None:
        wsgi = (Path(settings.BASE_DIR) / "rentalars" / "wsgi.py").read_text(encoding="utf-8")
        self.assertRegex(wsgi, r"(?m)^warm_up\(\)\nset_startup_objects_aside\(\)$")
        service = (Path(settings.BASE_DIR) / "deploy" / "systemd" / "rentalars.service").read_text(encoding="utf-8")
        self.assertIn("--preload", service)

    def test_what_was_loaded_at_start_is_set_aside_from_the_garbage_collector(self) -> None:
        """NFA-013: a search for garbage must not look through the whole application in mid-request."""
        with mock.patch("rentalars.core.warmup.gc") as collector:
            set_startup_objects_aside()
        self.assertEqual([call[0] for call in collector.method_calls], ["collect", "freeze"])

    def test_a_failure_is_logged_and_does_not_stop_the_start(self) -> None:
        with (
            mock.patch("rentalars.core.warmup._load_templates", side_effect=RuntimeError("broken")),
            self.assertLogs("rentalars.core.warmup", level="ERROR"),
        ):
            self.assertEqual(warm_up(), 0)


class HtmxTemplateTests(SimpleTestCase):
    """The small requests that change a page without loading it (UIX-009)."""

    def test_every_request_names_where_its_answer_goes(self) -> None:
        """htmx hands ``hx-target`` down to everything inside an element.

        A field that asks the server for something while it sits inside a
        form with ``hx-target="#dialog"`` would therefore replace the whole
        dialog with its answer – as the live availability check once did.
        The test client does not run scripts and cannot notice this, so the
        rule is checked here: whoever sends a request says where the answer
        belongs.
        """
        missing = []
        for path in sorted(TEMPLATES.rglob("*.html")):
            for tag in REQUESTING_TAG.finditer(path.read_text(encoding="utf-8")):
                if "hx-target=" not in tag.group(0):
                    missing.append(f"{path.relative_to(TEMPLATES)}: {tag.group(0)[:80]}")
        self.assertEqual(missing, [])

    def test_parts_of_the_planning_carry_the_ids_the_patch_relies_on(self) -> None:
        """A part can only be replaced on its own if page and patch use the same id for it."""
        patch = (TEMPLATES / "projects/_planning_patch.html").read_text(encoding="utf-8")
        # PRJ-037: the page puts each group into the tree through _group_node.html.
        page = (TEMPLATES / "projects/_planning.html").read_text(encoding="utf-8")
        page += (TEMPLATES / "projects/_group_node.html").read_text(encoding="utf-8")
        parts = (
            "_planning_messages",
            "_group",
            "_group_total",
            "_group_none",
            "_planning_surcharges",
            "_planning_totals",
        )
        for part in parts:
            self.assertIn(f"projects/{part}.html", patch)
            self.assertIn(f"projects/{part}.html", page)
            text = (TEMPLATES / f"projects/{part}.html").read_text(encoding="utf-8")
            self.assertIn('{% if oob %} hx-swap-oob="true"{% endif %}', text, part)

    def test_the_hints_about_all_lines_fetch_themselves_after_a_change(self) -> None:
        """They need the availability of every line and are therefore not part of a patch (NFA-013)."""
        patch = (TEMPLATES / "projects/_planning_patch.html").read_text(encoding="utf-8")
        page = (TEMPLATES / "projects/_planning.html").read_text(encoding="utf-8")
        notes = (TEMPLATES / "projects/_planning_notes.html").read_text(encoding="utf-8")
        self.assertIn("projects/_planning_notes.html", page)
        self.assertNotIn('include "projects/_planning_notes.html"', patch)
        self.assertIn("hx-get=\"{% url 'projects:planning_notes' project.pk %}\"", notes)
        self.assertIn('hx-trigger="planningChanged from:body"', notes)
        # Of two quick changes the later one counts: htmx queues a second fetch,
        # but only for a block that is still in the page when the first is done.
        self.assertIn('hx-swap="innerHTML"', notes)
        self.assertIn('hx-select="#planning-notes > *"', notes)
