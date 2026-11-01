# SPDX-License-Identifier: GPL-3.0-or-later
"""The page that makes labels (MAT-026, MAT-056).

Items are chosen by their IDs – typed, as ranges like ``0100-0120``, or
handed over from the item list – and the PDF is made at once. A large batch
is made in the background and announced when ready (NFA-041).

MAT-056: "Drucken" opens the labels as a page of their own whose
print dialog opens by itself – one label per page in its exact size, for a
label printer chosen there (:func:`labels_print`). Einstellungen → Etiketten
says what they show (:func:`label_settings_page`).

MAT-066 (labels): the page of a material model leads here with all its items
chosen (``?model=``, :func:`_form_data`); the page of an item asks in a small
dialog which label to print and opens it at once (:func:`item_labels`).
"""

from __future__ import annotations

import re
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.core.i18n import file_name
from rentalars.material import labels
from rentalars.material.models import ARCHIVED_STATUSES, MaterialItem
from rentalars.material.numbering import format_inventory_number, parse_inventory_number


class LabelForm(StyledForm):
    """Which items, which sheet, which code."""

    items = forms.CharField(
        label=gettext_lazy("IDs"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=gettext_lazy("Separated by commas or spaces; ranges as 0100-0120."),
    )
    id_from = forms.CharField(label=gettext_lazy("or all from ID"), required=False, max_length=10)
    id_to = forms.CharField(label=gettext_lazy("to ID"), required=False, max_length=10)
    label_format = forms.ChoiceField(label=gettext_lazy("Label"), choices=labels.format_choices)
    code = forms.ChoiceField(
        label=gettext_lazy("Code"),
        choices=labels.CODE_CHOICES,
        initial=labels.CODE_QR,
        required=False,  # MAT-056: the three labels need none; empty is the QR code
        help_text=gettext_lazy("The labels small, large and cable always have the QR code of Settings → Labels."),
    )
    skip = forms.IntegerField(
        label=gettext_lazy("Leave free at the start"),
        min_value=0,
        max_value=64,
        initial=0,
        required=False,
        help_text=gettext_lazy("For a sheet that is partly used already."),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # MAT-056: the label of Einstellungen → Etiketten is suggested – at first the small one.
        self.fields["label_format"].initial = labels.default_format()

    def numbers(self) -> list[int]:
        """The inventory numbers asked for, in the order given, without repeats.

        Raises:
            ValidationError: A part is no ID, or there are too many.
        """
        numbers: list[int] = []
        text = self.cleaned_data.get("items", "")
        for part in re.split(r"[\s,;]+", text.strip()):
            if not part:
                continue
            if "-" in part.strip("-"):
                first, last = (parse_inventory_number(value) for value in part.split("-", 1))
                if last < first:
                    first, last = last, first
                if last - first > labels.MAX_LABELS:
                    raise ValidationError(_("At most %(count)d labels at once.") % {"count": labels.MAX_LABELS})
                numbers.extend(range(first, last + 1))
            else:
                numbers.append(parse_inventory_number(part))
        start, end = self.cleaned_data.get("id_from", "").strip(), self.cleaned_data.get("id_to", "").strip()
        if start or end:
            first = parse_inventory_number(start or end)
            last = parse_inventory_number(end or start)
            if last - first > labels.MAX_LABELS:
                raise ValidationError(_("At most %(count)d labels at once.") % {"count": labels.MAX_LABELS})
            numbers.extend(range(min(first, last), max(first, last) + 1))
        unique = list(dict.fromkeys(numbers))
        if len(unique) > labels.MAX_LABELS:
            raise ValidationError(_("At most %(count)d labels at once.") % {"count": labels.MAX_LABELS})
        return unique


def chosen_items(numbers: list[int]) -> list[MaterialItem]:
    """The existing, not archived items with these numbers, in the order asked for."""
    found = {
        item.inventory_number: item
        for item in MaterialItem.objects.filter(inventory_number__in=numbers)
        .exclude(status__in=ARCHIVED_STATUSES)
        # PRD-043: the owner of customer material is printed on its label.
        .select_related("material_model__default_product__owner", "product_override__owner")
    }
    return [found[number] for number in numbers if number in found]


def id_ranges(numbers: list[int]) -> str:
    """IDs as the form takes them, runs shortened: ``0100-0120, 0125`` (MAT-066)."""
    parts: list[str] = []
    numbers = sorted(set(numbers))
    index = 0
    while index < len(numbers):
        end = index
        while end + 1 < len(numbers) and numbers[end + 1] == numbers[end] + 1:
            end += 1
        first, last = format_inventory_number(numbers[index]), format_inventory_number(numbers[end])
        parts.append(first if end == index else f"{first}-{last}")
        index = end + 1
    return ", ".join(parts)


def _form_data(request: HttpRequest) -> QueryDict | None:
    """What the form of the page gets: the parameters of the address, completed (MAT-066).

    * ``model``: the material model's items that are not archived, when no
      IDs are named – the button "Etiketten" of the model's page;
    * a missing label: the one suggested under Einstellungen → Etiketten, so
      that a link naming only IDs (``?items=0042``, the item list's "Etiketten")
      shows them at once instead of "required". Not when the PDF or the print is
      asked for – those come from the form, which always names the label.
    """
    if not request.GET:
        return None
    data = request.GET.copy()
    model = data.get("model", "")
    if model.isdigit() and not any(data.get(name, "").strip() for name in ("items", "id_from", "id_to")):
        numbers = (
            MaterialItem.objects.filter(material_model_id=int(model))
            .exclude(status__in=ARCHIVED_STATUSES)
            .values_list("inventory_number", flat=True)
        )
        data["items"] = id_ranges(list(numbers))
    if not data.get("label_format") and not (data.get("pdf") or data.get("print")):
        data["label_format"] = labels.default_format()
    return data


def _chosen(request: HttpRequest) -> tuple[LabelForm, list[MaterialItem], dict[str, Any]]:
    """The form of the page, the items it names and the options of the labels."""
    form = LabelForm(_form_data(request))
    items: list[MaterialItem] = []
    if form.is_bound and form.is_valid():
        try:
            items = chosen_items(form.numbers())
        except ValidationError as error:
            form.add_error(None, error)
    options: dict[str, Any] = {}
    if form.is_bound and form.is_valid():
        options = {
            "label_format": form.cleaned_data["label_format"],
            "code": form.cleaned_data.get("code") or labels.CODE_QR,
            "skip": form.cleaned_data.get("skip") or 0,
        }
    return form, items, options


@module_required(Module.MATERIAL)
def labels_print(request: HttpRequest) -> HttpResponse:
    """MAT-056: the labels as a page that opens the print dialog of the browser by itself.

    At most :data:`labels.MAX_LABELS_DIRECT` labels at once – a printer
    dialog with thousands of pages helps nobody; more are made as a PDF in
    the background on the page of the labels.
    """
    _form, items, options = _chosen(request)
    if not items:
        messages.error(request, _("Choose the items first."))
        return redirect(f"{reverse('material:labels')}?{request.GET.urlencode()}")
    if len(items) > labels.MAX_LABELS_DIRECT:
        messages.error(
            request,
            _("At most %(count)d labels can be printed from the browser at once; make the PDF instead.")
            % {"count": labels.MAX_LABELS_DIRECT},
        )
        return redirect(f"{reverse('material:labels')}?{request.GET.urlencode()}")
    return HttpResponse(labels.render_labels_html(items, for_browser=True, **options))


@module_required(Module.MATERIAL)
def labels_page(request: HttpRequest) -> HttpResponse:
    """Choose items and label, then print or make the PDF (MAT-026, MAT-056)."""
    form, items, options = _chosen(request)
    if items and request.GET.get("print") and len(items) <= labels.MAX_LABELS_DIRECT:
        return redirect(f"{reverse('material:labels_print')}?{request.GET.urlencode()}")
    if items and request.GET.get("pdf"):
        if len(items) > labels.MAX_LABELS_DIRECT:
            from rentalars.core.jobs import start_job

            job = start_job(
                "labels",
                {"numbers": [item.inventory_number for item in items], **options},
                user=request.user,
                title=_("Labels for %(count)d items") % {"count": len(items)},
            )
            messages.success(request, _("The labels are being made. You will be told when the PDF is ready."))
            return redirect("core:job", pk=job.pk)
        pdf = labels.render_labels_pdf(items, **options)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{file_name("labels", extension="pdf")}"'
        return response
    return render(
        request,
        "material/labels.html",
        {
            "form": form,
            "items": items,
            "item_count": len(items),
            "too_many": len(items) > labels.MAX_LABELS_DIRECT,
            "direct_limit": labels.MAX_LABELS_DIRECT,
            # MAT-056: the formats that take the code chosen here; the three labels always have the QR code.
            "sheet_formats": "|".join(labels.FORMATS),
        },
    )


@module_required(Module.MATERIAL)
def item_labels(request: HttpRequest, pk: int) -> HttpResponse:
    """MAT-066: which label for this item – each choice opens it ready to print (MAT-056).

    A small dialog over the item's page: the three labels of Einstellungen →
    Etiketten (the one suggested there first) and the sheets and the roll of
    MAT-026; each opens the print page of exactly this item in a tab of its
    own, whose print dialog opens by itself (:func:`labels_print`). "More
    settings" leads to the page of the labels. Without JavaScript the same
    choice is a page of its own.
    """
    item = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)
    suggested = labels.default_format()

    def choice(key: str, name: Any) -> dict[str, Any]:
        query = urlencode({"items": item.display_id, "label_format": key})
        return {
            "key": key,
            "name": name,
            "url": f"{reverse('material:labels_print')}?{query}",
            "suggested": key == suggested,
        }

    kinds = [choice(key, name) for key, name in labels.format_choices()]
    context = {
        "item": item,
        "label_choices": sorted(
            (entry for entry in kinds if labels.is_layout(entry["key"])), key=lambda entry: not entry["suggested"]
        ),
        "sheet_choices": [entry for entry in kinds if not labels.is_layout(entry["key"])],
        "more_url": f"{reverse('material:labels')}?{urlencode({'items': item.display_id})}",
        "as_page": not request.headers.get("HX-Request"),
    }
    template = "material/item_labels.html" if context["as_page"] else "material/_item_labels.html"
    return render(request, template, context)


# --- MAT-056: Einstellungen → Etiketten -------------------------------------------------


class LabelSettingsForm(StyledModelForm):
    """What the three labels of MAT-056 show: logo, names, phone, web address, texts, QR code."""

    class Meta:
        from rentalars.material.models import LabelSettings

        model = LabelSettings
        fields = [
            "company_name",
            "cable_name",
            "logo",
            "phone_caption",
            "phone",
            "id_caption",
            "url",
            "wrap_text",
            "notice",
            "qr_target",
            "default_kind",
            "cable_length_mm",
        ]
        widgets = {"notice": forms.Textarea(attrs={"rows": 3, "maxlength": 300})}


def preview_labels() -> list[tuple[str, Any, Any]]:
    """MAT-056: the three labels for the sample item 0427, as the settings stand – ``(kind, name, label)``."""
    from rentalars.material.label_layouts import LAYOUTS, lay_out
    from rentalars.material.models import LabelKind, LabelSettings

    sample = MaterialItem(inventory_number=427)
    text = labels.layout_texts([sample])[0]
    length = LabelSettings.load().cable_length_mm
    return [(kind, LabelKind(kind).label, lay_out(LAYOUTS[kind], text, length_mm=length)) for kind in LAYOUTS]


@module_required(Module.ADMINISTRATION)
def label_settings_page(request: HttpRequest) -> HttpResponse:
    """Einstellungen → Etiketten: logo, name, texts and QR code of the labels, with a preview (MAT-056)."""
    from rentalars.material.models import LabelSettings

    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    settings_row = LabelSettings.load()
    form = LabelSettingsForm(request.POST or None, request.FILES or None, instance=settings_row)
    if request.method == "POST":
        if not can_write:
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved."))
            return redirect("material:label_settings")
    return render(
        request,
        "material/label_settings.html",
        {"form": form, "can_write": can_write, "previews": preview_labels(), "settings_row": settings_row},
    )
