# SPDX-License-Identifier: GPL-3.0-or-later
"""The empty entry of a selection list (B12).

Django writes ``---------`` for "nothing chosen" in every selection of a model field or a ``ModelChoiceField``. Rentalars
writes "– please choose –" there, as it does where it sets the entry itself. Done once at the start, for the whole
program, so that no form needs to remember it.
"""

from __future__ import annotations

from typing import Any

from django.db.models import fields
from django.forms import models as form_models
from django.utils.translation import gettext_lazy as _

DJANGO_DASHES = "---------"

_done = False


def replace_dashes() -> None:
    """Replace Django's empty entry by "– please choose –" (once)."""
    global _done
    if _done:
        return
    _done = True
    # ``Field.get_choices`` takes this very list as the default of its argument ``blank_choice``.
    fields.BLANK_CHOICE_DASH[:] = [("", _("– please choose –"))]

    original = form_models.ModelChoiceField.__init__

    def with_text(self: Any, queryset: Any, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("empty_label", DJANGO_DASHES) == DJANGO_DASHES:
            kwargs["empty_label"] = _("– please choose –")
        original(self, queryset, *args, **kwargs)

    form_models.ModelChoiceField.__init__ = with_text  # type: ignore[method-assign]
