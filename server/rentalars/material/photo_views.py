# SPDX-License-Identifier: GPL-3.0-or-later
"""The photos of a model or an item (MAT-090).

A photo is uploaded on the detail page of the model or item; several at once. Each is made anew
(``rentalars.core.photos``: JPEG, at most 2048 pixels, the place stays, everything else is removed) and gets a preview.
The business rule lives in ``material.services.add_file`` – the API and these pages use the same function (API-002).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required
from rentalars.material import services
from rentalars.material.models import MaterialFileKind, MaterialItem, MaterialModel

#: How many photos one upload may carry – a form with a hundred files is a mistake, not a wish.
MAX_PHOTOS_PER_UPLOAD = 20


def photo_context(owner: MaterialModel | MaterialItem, rights: Any) -> dict[str, Any]:
    """The photos of a model or an item for ``material/_photos.html``; an item also shows those of its model."""
    own = services.visible_files(
        owner.files.filter(kind=MaterialFileKind.PICTURE).order_by("uploaded_at", "id"), rights
    )
    context: dict[str, Any] = {"photos": list(own)}
    if isinstance(owner, MaterialItem):
        model_photos = services.visible_files(
            owner.material_model.files.filter(kind=MaterialFileKind.PICTURE).order_by("uploaded_at", "id"), rights
        )
        context["model_photos"] = list(model_photos)
    return context


def head_picture(owner: MaterialModel | MaterialItem, rights: Any) -> Any:
    """The photo in the head of a page: the first of the owner, for an item else the first of its model."""
    pictures = services.visible_files(
        owner.files.filter(kind=MaterialFileKind.PICTURE).order_by("uploaded_at", "id"), rights
    )
    found = pictures.first()
    if found is None and isinstance(owner, MaterialItem):
        found = services.visible_files(
            owner.material_model.files.filter(kind=MaterialFileKind.PICTURE).order_by("uploaded_at", "id"), rights
        ).first()
    return found


def _store(request: HttpRequest, owner: MaterialModel | MaterialItem) -> None:
    """Store the uploaded photos and say what happened: how many, and which one was refused and why."""
    uploads = request.FILES.getlist("photos")
    if not uploads:
        messages.error(request, _("Choose at least one photo."))
        return
    if len(uploads) > MAX_PHOTOS_PER_UPLOAD:
        messages.error(
            request,
            ngettext("At most %(count)d photo at a time.", "At most %(count)d photos at a time.", MAX_PHOTOS_PER_UPLOAD)
            % {"count": MAX_PHOTOS_PER_UPLOAD},
        )
        return
    stored = 0
    for uploaded in uploads:
        try:
            services.add_file(owner, uploaded, kind=MaterialFileKind.PICTURE, user=request.user)
        except ValidationError as error:
            reason = " ".join(error.messages)
            messages.error(request, _("%(name)s: %(reason)s") % {"name": uploaded.name, "reason": reason})
        else:
            stored += 1
    if stored:
        messages.success(
            request, ngettext("%(count)d photo stored.", "%(count)d photos stored.", stored) % {"count": stored}
        )


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def model_photos(request: HttpRequest, pk: int) -> HttpResponse:
    """Add photos to a model."""
    material_model = get_object_or_404(MaterialModel, pk=pk)
    _store(request, material_model)
    return redirect(reverse("material:model_detail", args=[material_model.pk]) + "#photos")


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_photos(request: HttpRequest, pk: int) -> HttpResponse:
    """Add photos to an item."""
    item = get_object_or_404(MaterialItem, pk=pk)
    _store(request, item)
    return redirect(reverse("material:item_detail", args=[item.pk]) + "#photos")
