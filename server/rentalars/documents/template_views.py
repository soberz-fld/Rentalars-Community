# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser view of Settings → Document templates → template texts in English or German (DOK-018).

The page shows, for the language chosen, which heading, introduction and
closing text of each template its default text would change, with own texts
marked and not ticked; the button takes over what is ticked
(``documents.template_texts``). Reading needs read access to the settings
(module "Administration"), taking over write access – as the other pages of
the settings (e.g. ``accounting_views``).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.i18n import LANGUAGE_CHOICES, document_language
from rentalars.documents import template_texts


@module_required(Module.ADMINISTRATION)
def template_defaults(request: HttpRequest) -> HttpResponse:
    """Compare the templates with the default texts of a language; take over the ticked ones (DOK-018)."""
    rights = request_rights(request)
    can_edit = rights.can_write(Module.ADMINISTRATION)
    source = request.POST if request.method == "POST" else request.GET
    language = source.get("language", "")
    if language not in template_texts.LANGUAGES:
        language = template_texts.suggested_language()
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        chosen = request.POST.getlist("fields")
        result = template_texts.take_over(
            language,
            chosen=chosen,
            seen={key: request.POST.get(f"seen-{key}", "") for key in chosen},
            document_language=request.POST.get("document_language") == "1",
        )
        _report(request, result)
        return redirect(f"{reverse('documents:template_defaults')}?language={language}")
    comparisons = template_texts.compare(language)
    current_document_language = document_language()
    return render(
        request,
        "documents/template_defaults.html",
        {
            "language": language,
            "comparisons": comparisons,
            "has_changes": any(comparison.changes for comparison in comparisons),
            "has_own": any(comparison.has_own for comparison in comparisons),
            "document_language": current_document_language,
            "document_language_name": dict(LANGUAGE_CHOICES).get(current_document_language, ""),
            "can_edit": can_edit,
        },
    )


def _report(request: HttpRequest, result: template_texts.Result) -> None:
    """Say on the page what was taken over, what was left and why."""
    if result.changed:
        messages.success(
            request,
            ngettext(
                "%(count)d text was replaced by its default text.",
                "%(count)d texts were replaced by their default texts.",
                len(result.changed),
            )
            % {"count": len(result.changed)},
        )
    if result.stale:
        messages.warning(
            request,
            ngettext(
                "%(count)d text was changed in the meantime and was not overwritten. Look at it again.",
                "%(count)d texts were changed in the meantime and were not overwritten. Look at them again.",
                len(result.stale),
            )
            % {"count": len(result.stale)},
        )
    if result.document_language_changed:
        messages.success(
            request,
            _("The language of the documents is now %(language)s.")
            % {"language": dict(LANGUAGE_CHOICES)[result.language]},
        )
    if not result.changed and not result.stale and not result.document_language_changed:
        messages.info(request, _("Nothing was chosen; the templates stay as they are."))
