# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for the geocoder (Nominatim) in tests (UIX-034).

:class:`FakeGeocoder` replaces ``rentalars.core.geocoding._send`` – the one
place that touches the network – and the wait between two requests. It
answers from a table of addresses and keeps every question asked::

    with FakeGeocoder({"Hauptstraße 1, 12345 Musterstadt": ("52.1", "13.2")}) as geocoder:
        maps.locate(page)
    self.assertEqual(len(geocoder.questions), 1)

No test of Rentalars reaches a server on the internet.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlsplit


class FakeGeocoder:
    """Answers like Nominatim from a table ``{address: (latitude, longitude)}``."""

    def __init__(
        self,
        places: dict[str, tuple[str, str]] | None = None,
        *,
        status: int = 200,
        error: BaseException | None = None,
        body: bytes | None = None,
    ) -> None:
        self.places = places or {}
        self.status = status
        self.error = error
        self.body = body
        #: The addresses asked for, in order.
        self.questions: list[str] = []
        #: The headers of the last request.
        self.headers: dict[str, str] = {}
        self.urls: list[str] = []
        self._stack: ExitStack | None = None

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        self.urls.append(url)
        self.headers = headers
        query = parse_qs(urlsplit(url).query).get("q", [""])[0]
        self.questions.append(query)
        if self.error is not None:
            raise self.error
        if self.body is not None:
            return self.status, self.body
        hit = self.places.get(query)
        answer: list[dict[str, Any]] = (
            [{"lat": hit[0], "lon": hit[1], "display_name": f"{query} (gefunden)"}] if hit else []
        )
        return self.status, json.dumps(answer).encode("utf-8")

    def __enter__(self) -> FakeGeocoder:
        self._stack = ExitStack()
        self._stack.enter_context(mock.patch("rentalars.core.geocoding._send", self))
        self._stack.enter_context(mock.patch("rentalars.core.geocoding._wait_turn", lambda: None))
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._stack is not None
        self._stack.close()
