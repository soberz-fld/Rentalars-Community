# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "hostile input": wrong types in single values are a 400, never a 5xx. (R4-2; API-008)

Five endpoints read single values from a JSON object without a serializer. A client that sends a number for a text,
a list for an ID, ``"abc"`` or ``1e999`` must get the uniform error answer. Where a value is accepted on purpose
(e.g. ``4.0`` for a whole number) the test says so; the one thing never allowed is a status of 500 or more.
"""

from __future__ import annotations

import json
from typing import Any

from rest_framework.exceptions import ValidationError

from rentalars.api.inputs import int_or_400, str_or_400
from tests.api.base import API, ApiTestCase
from tests.helpers import make_item, make_model, make_product, make_stock, unit

#: What a hostile client may send where a whole number or a text is expected (JSON: ``1e999`` reads as infinity).
HOSTILE = [1, 1.5, [1], {"a": 1}, "abc", "1e999", None, True, False, "", 10**30, -1, "٣", float("nan")]


def send(client: Any, method: str, url: str, body: dict[str, Any]) -> Any:
    """Send ``body`` as raw JSON (so that ``NaN`` and ``Infinity`` get through as a client would write them)."""
    return getattr(client, method)(url, data=json.dumps(body), content_type="application/json")


class InputHelperTests(ApiTestCase):
    """The two helpers: right values pass, everything else is a ValidationError."""

    def test_int_or_400(self) -> None:
        for value, expected in [(4, 4), (4.0, 4), ("4", 4), (" -7 ", -7), ("+3", 3)]:
            self.assertEqual(int_or_400(value, "x"), expected)
        self.assertEqual(int_or_400(None, "x", default=0), 0)
        self.assertEqual(int_or_400("", "x", default=0), 0)
        for value in [True, 1.5, float("inf"), float("nan"), [1], {"a": 1}, "abc", "1e999", "٣", 10**30, None, "4.0"]:
            with self.assertRaises(ValidationError, msg=repr(value)):
                int_or_400(value, "x")

    def test_str_or_400(self) -> None:
        self.assertEqual(str_or_400("a", "x"), "a")
        self.assertEqual(str_or_400(None, "x"), "")
        self.assertEqual(str_or_400(None, "x", default="d"), "d")
        for value in [1, 1.5, True, [1], {"a": 1}]:
            with self.assertRaises(ValidationError, msg=repr(value)):
                str_or_400(value, "x")


class BuiltInHostileTests(ApiTestCase):
    """``POST /material-items/{id}/built-in`` (R4-2b): material, quantity and note."""

    def setUp(self) -> None:
        super().setUp()
        rack = make_item(make_model("Rack", make_product("S-500", "Rack")), 500)
        cable_product = make_product("K-600", "Kabel", unit=unit("Meter"))
        self.cable = make_item(make_model("Kabel", cable_product, bulk=True), 600, quantity=100)
        self.url = f"{API}/material-items/{rack.pk}/built-in"

    def test_hostile_material_quantity_and_note(self) -> None:
        for value in HOSTILE:
            for field in ("material", "quantity", "note"):
                body: dict[str, Any] = {"material": self.cable.pk, "quantity": 1, "note": "x", field: value}
                response = send(self.admin, "post", self.url, body)
                self.assertLess(response.status_code, 500, (field, value, response.content))
        # The named bad values give the uniform answer.
        for value in ("abc", "1e999", [1], {"a": 1}, True):
            self.assert_error(
                send(self.admin, "post", self.url, {"material": value, "quantity": 1}), 400, "validation_error"
            )
        self.assert_error(
            send(self.admin, "post", self.url, {"material": self.cable.pk, "quantity": 1, "note": [1]}),
            400,
            "validation_error",
            "note",
        )
        # ``Infinity`` is no JSON: the parser refuses it as a malformed request.
        self.assertEqual(send(self.admin, "post", self.url, {"material": float("inf"), "quantity": 1}).status_code, 400)
        # A text number is accepted on purpose; so is a whole float.
        ok = send(self.admin, "post", self.url, {"material": str(self.cable.pk), "quantity": 2.0})
        self.assertEqual(ok.status_code, 201, ok.content)


class RelationHostileTests(ApiTestCase):
    """``POST /products/{id}/relations`` and ``PATCH .../{relation}`` (R4-2c, R4-2d)."""

    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("S-100", 3, "Lautsprecher")
        self.cable = make_stock("K-100", 5, "Kabel")
        self.url = f"{API}/products/{self.speaker.pk}/relations"

    def test_hostile_related_product(self) -> None:
        for value in HOSTILE:
            response = send(self.admin, "post", self.url, {"related_product": value, "kind": "accessory"})
            self.assertLess(response.status_code, 500, (value, response.content))
        for value in ("abc", "1e999", [1], {"a": 1}, True, 10**30):
            self.assert_error(
                send(self.admin, "post", self.url, {"related_product": value, "kind": "accessory"}),
                400,
                "validation_error",
            )

    def test_hostile_other_values_on_create(self) -> None:
        for value in HOSTILE:
            for field in ("kind", "note", "quantity_per_piece", "is_required", "both_ways"):
                body: dict[str, Any] = {"related_product": self.cable.pk, "kind": "accessory", field: value}
                response = send(self.admin, "post", self.url, body)
                self.assertLess(response.status_code, 500, (field, value, response.content))

    def test_hostile_values_on_change(self) -> None:
        created = send(self.admin, "post", self.url, {"related_product": self.cable.pk, "kind": "accessory"})
        self.assertEqual(created.status_code, 201, created.content)
        one = f"{self.url}/{created.json()['accessories'][0]['id']}"
        for value in HOSTILE:
            for field in ("note", "is_required", "quantity_per_piece"):
                response = send(self.admin, "patch", one, {field: value})
                self.assertLess(response.status_code, 500, (field, value, response.content))
        for value in (1, 1.5, [1], {"a": 1}, True):
            self.assert_error(send(self.admin, "patch", one, {"note": value}), 400, "validation_error", "note")
        self.assertEqual(send(self.admin, "patch", one, {"note": None}).status_code, 200)
        self.assertEqual(send(self.admin, "patch", one, {"note": "Speakon"}).status_code, 200)


class AutoSummariesHostileTests(ApiTestCase):
    """``PATCH /ai/auto-summaries`` (R4-2e): the window and the numbers."""

    url = f"{API}/ai/auto-summaries"

    def test_hostile_values(self) -> None:
        names = ("window_start", "window_end", "max_per_run", "token_budget", "min_interval_hours", "max_input_chars")
        for value in HOSTILE:
            for name in names:
                response = send(self.admin, "patch", self.url, {name: value})
                self.assertLess(response.status_code, 500, (name, value, response.content))
        for value in (1, 1.5, [1], {"a": 1}, True):
            for name in ("window_start", "window_end"):
                self.assert_error(send(self.admin, "patch", self.url, {name: value}), 400, "validation_error", name)
        ok = send(self.admin, "patch", self.url, {"window_start": "01:30", "window_end": "04:00"})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["window_start"], "01:30")
