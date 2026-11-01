# SPDX-License-Identifier: GPL-3.0-or-later
"""What the labels of material items say: logo, name, phone, address, text and where the QR code leads (MAT-056).

Einstellungen → Etiketten. The three labels of MAT-056 – small
17 × 54 mm, large 29 × 90 mm and the cable label on the 29 mm roll – are laid
out like the P-touch templates of the operator (``material.label_layouts``);
what they show is set here, once for the company:

* a logo of its own for labels (black and white prints best) and the name
  printed next to it – by default the company's name; a shorter name for the
  narrow cable label;
* the phone number and the web address printed on the label, with the words
  in front of the phone number and of the ID;
* the text for whoever finds the item ("Hast du Equipment gefunden? …");
* the text repeated around a cable;
* where the QR code leads: a web address with ``{id}`` for the ID, e.g.
  ``https://equip.example.de/id/{id}``; empty: the item's page in Rentalars
  (``/m/0042``).

Imported at the end of ``rentalars/material/models.py`` so that Django finds it.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from rentalars.core.models import SingletonModel
from rentalars.core.uploads import validate_image_upload

#: MAT-056: the cable label is as long as the template unless set otherwise.
DEFAULT_CABLE_LENGTH_MM = 90
MIN_CABLE_LENGTH_MM = 60
MAX_CABLE_LENGTH_MM = 200

#: The placeholder of the ID in the address of the QR code.
ID_PLACEHOLDER = "{id}"


class LabelKind(models.TextChoices):
    """The three labels of MAT-056, laid out like the operator's P-touch templates."""

    SMALL = "small", _("Small, 17 × 54 mm")
    LARGE = "large", _("Large, 29 × 90 mm")
    CABLE = "cable", _("Cable, 29 mm roll")


class LabelSettings(SingletonModel):
    """The company's texts, logo and QR code target of the labels (MAT-056)."""

    company_name = models.CharField(
        _("name on labels"),
        max_length=120,
        blank=True,
        help_text=_("Printed next to the logo. Empty: the name of the company."),
    )
    cable_name = models.CharField(
        _("name on cable labels"),
        max_length=60,
        blank=True,
        help_text=_("The cable label has little room. Empty: the name on labels."),
    )
    logo = models.ImageField(
        _("logo for labels"),
        upload_to="labels/",
        blank=True,
        validators=[validate_image_upload],
        help_text=_("PNG or JPEG, at most 2 MB, square; black and white prints best on label printers."),
    )
    phone = models.CharField(
        _("phone number"), max_length=60, blank=True, help_text=_("Empty: the phone number of the company.")
    )
    phone_caption = models.CharField(
        _("words before the phone number"), max_length=40, blank=True, default="Telefonnummer:"
    )
    id_caption = models.CharField(_("words before the ID"), max_length=40, blank=True, default="Equipment-ID:")
    url = models.CharField(
        _("web address printed"),
        max_length=100,
        blank=True,
        help_text=_("As it is printed, e.g. EXAMPLE.DE. Empty: the website of the company."),
    )
    wrap_text = models.CharField(
        _("text around the cable"),
        max_length=100,
        blank=True,
        help_text=_("Repeated where the cable label wraps around the cable. Empty: the web address printed."),
    )
    notice = models.TextField(
        _("text for finders"),
        max_length=300,
        blank=True,
        help_text=_("Small print on the small and the large label, e.g. where to report a found item."),
    )
    qr_target = models.CharField(
        _("QR code leads to"),
        max_length=250,
        blank=True,
        help_text=_(
            "A web address with {id} for the ID, e.g. https://equip.example.de/id/{id}. "
            "Empty: the item's page in Rentalars."
        ),
    )
    default_kind = models.CharField(
        _("label suggested"), max_length=10, choices=LabelKind.choices, default=LabelKind.SMALL
    )
    cable_length_mm = models.PositiveSmallIntegerField(
        _("length of the cable label (mm)"),
        default=DEFAULT_CABLE_LENGTH_MM,
        validators=[MinValueValidator(MIN_CABLE_LENGTH_MM), MaxValueValidator(MAX_CABLE_LENGTH_MM)],
        help_text=_("Of the 29 mm roll; the text around the cable is repeated to fill it."),
    )

    audit_exclude = frozenset({"logo"})

    class Meta:
        verbose_name = _("label settings")
        verbose_name_plural = _("label settings")

    def __str__(self) -> str:
        return str(_("Label settings"))

    def clean(self) -> None:
        """The address of the QR code names the ID, and is a web address."""
        super().clean()
        target = (self.qr_target or "").strip()
        self.qr_target = target
        if target:
            errors = []
            if ID_PLACEHOLDER not in target:
                errors.append(_("Put {id} where the ID belongs – otherwise every label leads to the same page."))
            if not target.lower().startswith(("http://", "https://")):
                errors.append(_("Begin the address with https:// or http://."))
            if errors:
                raise ValidationError({"qr_target": errors})

    # --- What is printed, with the company's data where a field is empty ----------------------------

    def _company(self) -> Any:
        from rentalars.core.models import CompanyProfile

        return CompanyProfile.load()

    @property
    def printed_name(self) -> str:
        """The name next to the logo."""
        return self.company_name.strip() or self._company().name

    @property
    def printed_cable_name(self) -> str:
        """The name on the cable label."""
        return self.cable_name.strip() or self.printed_name

    @property
    def printed_phone(self) -> str:
        """The phone number printed."""
        return self.phone.strip() or self._company().phone

    @property
    def printed_url(self) -> str:
        """The web address printed: as typed, else the website of the company without ``https://``."""
        if self.url.strip():
            return self.url.strip()
        website = (self._company().website or "").strip()
        for prefix in ("https://", "http://"):
            website = website.removeprefix(prefix)
        return website.rstrip("/")

    @property
    def printed_wrap_text(self) -> str:
        """The text repeated around a cable."""
        return self.wrap_text.strip() or self.printed_url

    def qr_content(self, display_id: str) -> str:
        """What the QR code of an item holds: the address with the ID, else the item's page in Rentalars."""
        from django.conf import settings

        if self.qr_target:
            return self.qr_target.replace(ID_PLACEHOLDER, display_id)
        return f"{settings.RENTALARS_URL}/m/{display_id}"
