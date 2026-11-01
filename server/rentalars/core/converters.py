# SPDX-License-Identifier: GPL-3.0-or-later
"""Readable addresses: ``/projects/2026-0042/`` and ``/products/L-010/`` (UIX-024).

Views keep working with primary keys. The converters turn the number in
the address into the key and back:

* **into the address** goes the project number or the article number,
  whether ``reverse`` gets the object, its key or the number;
* **from the address** both are accepted: the number, and – for older links and
  bookmarks – the bare key ``/projects/42/``.

ADM-012, ADM-014: a former project number is accepted as well – the
number with "P-" (``/projects/P-2026-0042/``,
now ``2026-0042`` again; see :mod:`rentalars.projects.numbers`). The
converter notes it for the request;
:class:`rentalars.core.middleware.FormerNumberRedirectMiddleware` then
answers a page request with a permanent redirect to the address of today,
so that bookmarks and links in old mails are corrected. The number of today
is looked up first; a former one costs a query only when that misses.

Reversing many addresses on one page (a list of 50 projects) must not cost
a query each (NFA-012): after a few single lookups, the converter reads all
numbers at once and keeps them for the rest of the request.
"""

from __future__ import annotations

import re
from typing import Any

#: Characters a number may contain to stand in an address as it is.
_SAFE = re.compile(r"^[A-Za-z0-9._~-]+$")

#: After this many single lookups in one request, all numbers are read at once.
_BULK_AFTER = 3


class _NumberConverter:
    """Base: ``model`` with the unique, readable ``field`` instead of the key."""

    regex = r"[^/]+"
    model_path = ""
    field = ""

    def _model(self) -> Any:
        from django.apps import apps

        return apps.get_model(self.model_path)

    def _maps(self) -> dict[str, Any] | None:
        """The maps of this request: key → number and number → key, filled as needed."""
        from rentalars.core.models import _request_cache

        cache = _request_cache.get()
        if cache is None:
            return None
        return cache.setdefault(("numbers", self.model_path), {"by_pk": {}, "by_number": {}, "misses": 0, "all": False})

    def _load_all(self, maps: dict[str, Any]) -> None:
        for pk, number in self._model().objects.values_list("pk", self.field):
            maps["by_pk"][pk] = number
            maps["by_number"][number] = pk
        maps["all"] = True

    def _number_of(self, pk: int) -> str | None:
        maps = self._maps()
        if maps is None:
            return self._model().objects.filter(pk=pk).values_list(self.field, flat=True).first()
        if pk not in maps["by_pk"] and not maps["all"]:
            maps["misses"] += 1
            if maps["misses"] > _BULK_AFTER:
                self._load_all(maps)
            else:
                number = self._model().objects.filter(pk=pk).values_list(self.field, flat=True).first()
                if number is not None:
                    maps["by_pk"][pk], maps["by_number"][number] = number, pk
        return maps["by_pk"].get(pk)

    def _pk_of(self, number: str) -> int | None:
        maps = self._maps()
        if maps is not None and number in maps["by_number"]:
            return maps["by_number"][number]
        pk = self._model().objects.filter(**{self.field: number}).values_list("pk", flat=True).first()
        if pk is not None and maps is not None:
            maps["by_pk"][pk], maps["by_number"][number] = number, pk
        return pk

    def _former(self, value: str) -> tuple[int, str] | None:
        """Key and number of today of the record that had ``value`` as its number before; none here."""
        return None

    def to_python(self, value: str) -> int:
        """The key of the number in the address; a former number and a bare key are accepted for old links."""
        pk = self._pk_of(value)
        if pk is None:
            # ADM-012, ADM-014: before the bare key – a former number ("0042") is a number, not a key.
            former = self._former(value)
            if former is not None:
                pk, number = former
                maps = self._maps()
                if maps is not None:
                    maps.setdefault("former", {})[value] = number
        if pk is None and value.isdigit():
            pk = int(value) if self._model().objects.filter(pk=int(value)).exists() else None
        if pk is None:
            raise ValueError(value)
        return pk

    def to_url(self, value: Any) -> str:
        """The number for the address – from an object, its key, or the number itself."""
        number = None
        if hasattr(value, "_meta"):
            number, pk = getattr(value, self.field), value.pk
        elif isinstance(value, int) or (isinstance(value, str) and value.isdigit() and self._pk_of(value) is None):
            pk = int(value)
            # The key 0 is the placeholder of ``placeholder_url`` – no record has it, so no lookup for it.
            number = None if pk == 0 else self._number_of(pk)
        else:
            number, pk = str(value), None
        if number and _SAFE.match(number):
            return number
        return str(pk if pk is not None else value)


class ProjectNumberConverter(_NumberConverter):
    """``<project:pk>``: the project number in the address, the key in the view."""

    model_path = "projects.Project"
    field = "number"

    def _former(self, value: str) -> tuple[int, str] | None:
        """ADM-012, ADM-014: the project whose former number is ``value`` (case ignored) – key and number of today."""
        from rentalars.projects.numbers import may_be_former

        if not may_be_former(value):
            return None
        row = (
            self._model().objects.filter(former_number__iexact=value).order_by("pk").values_list("pk", "number").first()
        )
        return (row[0], row[1]) if row is not None else None


def former_numbers_in_address() -> dict[str, str]:
    """ADM-012, ADM-014: the former project numbers the address of this request used, each with the number of today."""
    from rentalars.core.models import _request_cache

    cache = _request_cache.get()
    maps = cache.get(("numbers", ProjectNumberConverter.model_path)) if cache is not None else None
    return dict(maps.get("former", {})) if maps is not None else {}


class ArticleNumberConverter(_NumberConverter):
    """``<product:pk>``: the article number in the address, the key in the view."""

    model_path = "products.Product"
    field = "article_number"
