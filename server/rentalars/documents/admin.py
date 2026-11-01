# SPDX-License-Identifier: GPL-3.0-or-later
"""Templates and text blocks of the documents in the administration interface (DOK-005, ADM-007)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from rentalars.core.admin_tables import TableAdminMixin
from rentalars.documents.models import FREE_KINDS, DocumentKind, DocumentTemplate, TextBlock, text_block_kinds


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(TableAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Heading, introduction, closing text and footer of each kind of document.

    One template per kind exists from the start; they are changed, not added
    or deleted. Placeholders: {project}, {project_name}, {customer}, {period},
    {venue}, {due_date}, {payment_terms}; for the offer {valid_until} (DOK-010)
    and {validity_days} (DOK-013). The template of the offer also says how
    many days a new offer is valid (DOK-013); the others do not show the field.
    Each template says whether new documents print the description of the products, and – for the kinds
    made without a project – which introduction such a document starts with.
    """

    list_display = ["kind", "title", "show_logo"]
    readonly_fields = ["kind"]
    #: DOK-018: with the link to the default texts in English or German.
    change_list_template = "documents/admin_template_list.html"

    def get_exclude(self, request: HttpRequest, obj: Any = None) -> Any:
        """DOK-013: the validity in days belongs to the offer only."""
        excluded = list(super().get_exclude(request, obj) or [])
        if obj is None or obj.kind != DocumentKind.OFFER:
            excluded.append("validity_days")
        # The descriptions of the products belong to the documents that list products; a cancellation takes
        # over those of its invoice. The introduction without a project to the kinds made without one.
        if obj is None or obj.kind in {DocumentKind.CREW_SHEET, DocumentKind.CANCELLATION}:
            excluded.append("print_product_descriptions")
        if obj is None or obj.kind not in FREE_KINDS:
            excluded.append("free_introduction")
        return excluded

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Every kind has its template already."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Templates are changed, not deleted."""
        return False


class TextBlockForm(forms.ModelForm):  # type: ignore[type-arg]
    """The kinds a block is offered for, as tick boxes."""

    kinds = forms.MultipleChoiceField(
        label=_("for"),
        choices=text_block_kinds,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("None ticked: all kinds."),
    )

    class Meta:
        model = TextBlock
        fields = ["name", "text", "kinds", "is_active"]


@admin.register(TextBlock)
class TextBlockAdmin(TableAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Paragraphs that can be added when a document is made, e.g. terms of rental (DOK-005)."""

    form = TextBlockForm
    list_display = ["name", "is_active"]
    search_fields = ["name", "text"]
