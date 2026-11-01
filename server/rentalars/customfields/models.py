# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom fields of material items (MAT-071, MAT-072, MAT-073).

"Custom-Fields bei Modellen."

Four tables:

``CustomField``
    A definition: name, type (text, long text, number with unit, date,
    yes/no, choice list, web address, e-mail address), an optional check
    pattern, a help text and three marks – choosable as a column in lists,
    unique across all items, visible only with the right to see purchase
    prices.
``Fieldset`` and ``FieldsetEntry``
    A named group of fields; each field of a fieldset has a position and is
    required or optional there. One field can be part of several fieldsets.
``ModelFieldset``
    The fieldset of a material model – at most one per model. Kept here, not
    as a column of the material model, so that the material tables stay as
    they are.
``CustomFieldValue``
    The value of one field for one *item*. Values belong to items, not to
    models – unlike the category-specific fields (MAT-009, MAT-010), whose
    values belong to the material model and are defined per category.

A value is stored as text in a canonical form – a number as ``12.5``, a
date as ``2027-03-01``, yes/no as ``yes``/``no`` – and read typed by its
field (:meth:`CustomField.typed_value`). The value of a field marked
"only with the right to see purchase prices" is kept in the column
``protected_value`` instead of ``value``: the change log hides that column
from readers without the right (``audit_sensitive``, AUT-019), and the item
search never looks into it.

Values of fields that are not (or no longer) part of the fieldset of the
item's model are kept; the item page lists them apart, and they come back
when the field belongs to the fieldset again.
"""

from __future__ import annotations

import contextlib
import datetime
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.i18n import local_pattern
from rentalars.core.money import decimal_separator
from rentalars.core.tabular import FALSE_WORDS, TRUE_WORDS, parse_date
from rentalars.customfields import patterns
from rentalars.material.models import MaterialItem, MaterialModel

#: The most characters of a value of the type "text" (one line) and "long text".
TEXT_LENGTH = 250
LONG_TEXT_LENGTH = 4000
#: The most characters of a web or e-mail address.
ADDRESS_LENGTH = 500


class PatternTooComplexError(ValidationError):
    """Checking a value against the check pattern of its field took too long (MAT-071, ReDoS)."""


class FieldType(models.TextChoices):
    """The types of a custom field (MAT-071)."""

    TEXT = "text", _("text")
    LONG_TEXT = "long_text", _("long text")
    NUMBER = "number", _("number with unit")
    DATE = "date", _("date")
    BOOLEAN = "boolean", _("yes/no")
    CHOICE = "choice", _("choice list")
    URL = "url", _("web address")
    EMAIL = "email", _("e-mail address")


#: The types a check pattern applies to: their stored text is what people typed (normalised).
PATTERN_TYPES = frozenset({FieldType.TEXT, FieldType.LONG_TEXT, FieldType.NUMBER, FieldType.URL, FieldType.EMAIL})


def parse_number(value: Any) -> Decimal:
    """Read a number: ``12.5``, ``12,5``, ``1.234,5`` or ``1,234.5`` – the last sign is the decimal one.

    A typed value, a cell of a spreadsheet and a value of the API all come here: the
    API sends ``12.5``, a German form ``12,5``. Raises ``ValueError`` for anything else.
    """
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = str(value).replace(" ", "").replace(" ", "").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(value) from error
    if not number.is_finite():
        raise ValueError(value)
    return number


def number_text(number: Decimal) -> str:
    """The canonical text of a number: ``12.5``, ``100``, ``0`` – no exponent, no trailing zeros."""
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class CustomField(AuditedModel):
    """The definition of a custom field of material items (MAT-071).

    A field can be marked ``is_sensitive``: its values are
    seen and set only by who may see purchase prices (AUT-019) – an insurance
    value, a leasing contract, a PIN.
    """

    name = models.CharField(
        _("name"),
        max_length=80,
        unique=True,
        error_messages={"unique": _("A custom field with this name already exists.")},
        help_text=_("Also the heading of its column in lists, exports and imports."),
    )
    field_type = models.CharField(_("type"), max_length=12, choices=FieldType.choices, default=FieldType.TEXT)
    unit = models.CharField(_("unit"), max_length=20, blank=True, help_text=_("For numbers, e.g. m, W, kg."))
    choices = models.JSONField(_("options"), default=list, blank=True)
    pattern = models.CharField(
        _("check pattern"),
        max_length=250,
        blank=True,
        help_text=_(
            "Optional: a regular expression every value must match, e.g. ^[0-9A-F]{2}(:[0-9A-F]{2}){5}$ for a MAC "
            "address. For text, long text, number, web and e-mail address."
        ),
    )
    help_text = models.CharField(
        _("help text"), max_length=250, blank=True, help_text=_("Shown below the field in the form.")
    )
    show_in_lists = models.BooleanField(
        _("choosable as a column in lists"),
        default=False,
        help_text=_("The item list offers the field as a column – to show, sort, filter and export."),
    )
    is_unique = models.BooleanField(
        _("unique"),
        default=False,
        help_text=_("No two items may have the same value, e.g. a MAC address."),
    )
    is_sensitive = models.BooleanField(
        _("only with the right to see purchase prices"),
        default=False,
        help_text=_(
            "The values are shown, searched, exported and changed only by who may see purchase prices – also in "
            "the history and the API."
        ),
    )

    class Meta:
        verbose_name = _("custom field")
        verbose_name_plural = _("custom fields")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    # --- Definition ---------------------------------------------------------------------------

    @property
    def label_with_unit(self) -> str:
        """The name with the unit in brackets, e.g. ``Kabellänge (m)``."""
        return f"{self.name} ({self.unit})" if self.unit and self.field_type == FieldType.NUMBER else self.name

    @property
    def column(self) -> str:
        """The column of ``CustomFieldValue`` that holds the values of this field."""
        return "protected_value" if self.is_sensitive else "value"

    def visible_to(self, rights: Rights) -> bool:
        """Whether a user with these rights sees (and sets) the values of this field (AUT-019)."""
        return not self.is_sensitive or rights.has(SpecialRight.PURCHASE_PRICES)

    def clean(self) -> None:
        """Check the definition, and the stored values against a changed one."""
        super().clean()
        self.name = " ".join((self.name or "").split())
        self.unit = (self.unit or "").strip()
        self.pattern = (self.pattern or "").strip()
        options: list[str] = []
        for option in self.choices or []:
            text = " ".join(str(option).split())
            if text and text.casefold() not in {known.casefold() for known in options}:
                options.append(text)
        self.choices = options
        errors: dict[str, Any] = {}
        # Imports and the API find a field by its name whatever the case: "Firmware" and "firmware" would be one.
        if self.name and CustomField.objects.filter(name__iexact=self.name).exclude(pk=self.pk).exists():
            errors["name"] = _("A custom field with this name already exists.")
        if self.field_type == FieldType.CHOICE and not self.choices:
            errors["choices"] = _("A choice list needs at least one option.")
        if self.field_type != FieldType.CHOICE:
            self.choices = []
        if self.field_type != FieldType.NUMBER:
            self.unit = ""
        if self.pattern:
            if self.field_type not in PATTERN_TYPES:
                self.pattern = ""
            else:
                try:
                    re.compile(self.pattern)
                    # MAT-071: no pattern that can backtrack for minutes (ReDoS), see ``patterns``.
                    problems = patterns.pattern_problems(self.pattern)
                except re.error as error:
                    errors["pattern"] = _("This is no valid regular expression: %(error)s") % {"error": error}
                else:
                    if problems:
                        errors["pattern"] = problems
        if errors:
            raise ValidationError(errors)
        self._check_stored_values()

    def _check_stored_values(self) -> None:
        """A changed type, list of options, pattern or "unique" must fit the values items already have.

        Otherwise the values would no longer be what the field says. Up to
        three examples are named, with the item they belong to.
        """
        if self.pk is None:
            return
        problems: list[str] = []
        failed = 0
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for stored in CustomFieldValue.objects.filter(field_id=self.pk).select_related("item").order_by("item_id"):
            text = stored.stored
            if not text:
                continue
            try:
                canonical = self.clean_value(text)
            except PatternTooComplexError as error:
                # MAT-071: the first value that takes too long ends the check – not one per value.
                raise ValidationError({"pattern": error.messages}) from error
            except ValidationError:
                failed += 1
                if len(problems) < 3:
                    problems.append(f"„{text}“ ({stored.item.display_id})")
                continue
            key = canonical.casefold()
            if key in seen and len(duplicates) < 3:
                duplicates.append(f"„{canonical}“ ({seen[key]}, {stored.item.display_id})")
            seen.setdefault(key, stored.item.display_id)
        if failed:
            raise ValidationError(
                ngettext(
                    "%(count)s stored value does not fit the changed field: %(examples)s. Change this value first, "
                    "or keep the setting.",
                    "%(count)s stored values do not fit the changed field, e.g. %(examples)s. Change these values "
                    "first, or keep the setting.",
                    failed,
                )
                % {"count": failed, "examples": ", ".join(problems)}
            )
        if self.is_unique and duplicates:
            raise ValidationError(
                {
                    "is_unique": gettext("Several items have the same value: %(examples)s. Make them differ first.")
                    % {"examples": ", ".join(duplicates)}
                }
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save; stored values follow a changed definition (canonical text, the column of a sensitive field)."""
        before = (
            CustomField.objects.filter(pk=self.pk).values("field_type", "unit", "choices", "is_sensitive").first()
            if self.pk is not None
            else None
        )
        super().save(*args, **kwargs)
        forget_cached_fields()
        if before is None:
            return
        now = {
            "field_type": self.field_type,
            "unit": self.unit,
            "choices": self.choices,
            "is_sensitive": self.is_sensitive,
        }
        if now == before:
            return
        # Each value is saved on its own, so that the history of its item shows the change (AuditedModel).
        for stored in CustomFieldValue.objects.filter(field_id=self.pk).select_related("item"):
            stored.field = self
            text = stored.stored
            if text:
                # ``clean`` refuses a change that does not fit; a value set meanwhile stays as it is.
                with contextlib.suppress(ValidationError):
                    text = self.clean_value(text)
            stored.put(text)
            if stored.value != stored._loaded("value") or stored.protected_value != stored._loaded("protected_value"):
                stored.save()

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Delete the field with its values; :func:`rentalars.customfields.services.delete_field` asks first."""
        result = super().delete(*args, **kwargs)
        forget_cached_fields()
        return result

    # --- Values -------------------------------------------------------------------------------

    def clean_value(self, raw: Any) -> str:
        """Check a value against the type, the options and the pattern; return the text to store.

        Accepts what people type and what spreadsheets and the API send:
        ``12,5`` and ``12.5`` with or without the unit, dates as
        ``01.03.2027`` or ``2027-03-01`` (or a date), yes/no as ``ja``,
        ``nein``, ``x``, ``true``, ``1``; an option of a choice list in any
        case. Empty input gives ``""``.

        Raises:
            ValidationError: The value does not fit, e.g. text in a number field.
        """
        if raw is None:
            return ""
        text = raw.strip() if isinstance(raw, str) else raw
        if text == "":
            return ""
        canonical = self._canonical(text)
        if self.pattern and self.field_type in PATTERN_TYPES and not self._matches(canonical):
            message = gettext("“%(value)s” does not have the format of the field %(field)s.") % {
                "value": canonical,
                "field": self.name,
            }
            if self.help_text:
                message = f"{message} {self.help_text}"
            raise ValidationError(message)
        return canonical

    def _matches(self, canonical: str) -> bool:
        """Whether a value fits the check pattern – within a length and a time limit (MAT-071).

        Raises:
            ValidationError: The value is longer than a pattern is applied to.
            PatternTooComplexError: Matching took too long.
        """
        if len(canonical) > patterns.MAX_VALUE_LENGTH:
            raise ValidationError(self._too_long(patterns.MAX_VALUE_LENGTH))
        try:
            return patterns.full_match(self.pattern, canonical)
        except patterns.PatternTooSlowError as error:
            raise PatternTooComplexError(
                gettext(
                    "Check pattern too complex: checking the value of the field %(field)s took too long. Please "
                    "simplify the pattern under Settings → Custom fields."
                )
                % {"field": self.name},
                code="pattern_too_complex",
            ) from error

    def _canonical(self, value: Any) -> str:
        """The stored form of a value that is not empty; see :meth:`clean_value`."""
        names = {"value": value if not isinstance(value, datetime.date) else value.isoformat(), "field": self.name}
        kind = self.field_type
        if kind == FieldType.NUMBER:
            if isinstance(value, str) and self.unit and value.casefold().endswith(self.unit.casefold()):
                value = value[: -len(self.unit)].strip()
            try:
                return number_text(parse_number(value))
            except ValueError as error:
                raise ValidationError(
                    gettext("“%(value)s” is not a number for the field %(field)s.") % names
                ) from error
        if kind == FieldType.DATE:
            try:
                day = parse_date(value)
            except (ValueError, TypeError) as error:
                raise ValidationError(gettext("“%(value)s” is not a date for the field %(field)s.") % names) from error
            return day.isoformat() if day is not None else ""
        if kind == FieldType.BOOLEAN:
            if isinstance(value, bool):
                return "yes" if value else "no"
            word = str(value).strip().casefold()
            if word in TRUE_WORDS:
                return "yes"
            if word in FALSE_WORDS:
                return "no"
            raise ValidationError(gettext("“%(value)s” is neither yes nor no for the field %(field)s.") % names)
        text = str(value).strip()
        if kind == FieldType.CHOICE:
            for option in self.choices or []:
                if option == text or option.casefold() == text.casefold():
                    return option
            raise ValidationError(
                gettext("“%(value)s” is not one of the options of the field %(field)s: %(options)s.")
                % {**names, "options": ", ".join(self.choices or [])}
            )
        if kind == FieldType.LONG_TEXT:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if len(text) > LONG_TEXT_LENGTH:
                raise ValidationError(self._too_long(LONG_TEXT_LENGTH))
            return text
        text = " ".join(text.split())
        if kind == FieldType.URL:
            if "://" not in text:
                text = f"https://{text}"
            try:
                URLValidator(schemes=["http", "https"])(text)
            except ValidationError as error:
                raise ValidationError(
                    gettext("“%(value)s” is not a web address for the field %(field)s.") % names
                ) from error
            limit = ADDRESS_LENGTH
        elif kind == FieldType.EMAIL:
            try:
                EmailValidator()(text)
            except ValidationError as error:
                raise ValidationError(
                    gettext("“%(value)s” is not an e-mail address for the field %(field)s.") % names
                ) from error
            limit = ADDRESS_LENGTH
        else:
            limit = TEXT_LENGTH
        if len(text) > limit:
            raise ValidationError(self._too_long(limit))
        return text

    def _too_long(self, limit: int) -> str:
        return gettext("The value of the field %(field)s may have at most %(count)s characters.") % {
            "field": self.name,
            "count": limit,
        }

    def typed_value(self, stored: str) -> Any:
        """A stored value as Python value: ``Decimal``, ``date``, ``bool`` or text; ``None`` when empty."""
        if not stored:
            return None
        try:
            if self.field_type == FieldType.NUMBER:
                return Decimal(stored)
            if self.field_type == FieldType.DATE:
                return datetime.date.fromisoformat(stored)
        except (InvalidOperation, ValueError):
            return stored  # written before the type changed; shown as it is
        if self.field_type == FieldType.BOOLEAN:
            return stored == "yes"
        return stored

    def display_value(self, stored: str) -> str:
        """A stored value for people: ``12,5 m``, ``01.03.2027``, ``ja`` (UIX-029)."""
        value = self.typed_value(stored)
        if value is None:
            return ""
        if isinstance(value, bool):
            return gettext("yes") if value else gettext("no")
        if isinstance(value, Decimal):
            number = number_text(value).replace(".", decimal_separator())
            return f"{number} {self.unit}".strip()
        if isinstance(value, datetime.date):
            return value.strftime(local_pattern("%d.%m.%Y"))
        return str(value)

    def form_value(self, stored: str) -> str:
        """A stored value as a form field shows it: a number with the decimal sign of the language."""
        if self.field_type == FieldType.NUMBER and stored:
            return stored.replace(".", decimal_separator())
        return stored

    def holder_of(self, canonical: str, *, exclude_item: Any = None) -> CustomFieldValue | None:
        """For a unique field: the value of another item that is the same as ``canonical`` (case ignored)."""
        if not canonical:
            return None
        values = CustomFieldValue.objects.filter(field_id=self.pk).filter(
            Q(value__iexact=canonical) | Q(protected_value__iexact=canonical)
        )
        if exclude_item is not None:
            values = values.exclude(item_id=getattr(exclude_item, "pk", exclude_item))
        return values.select_related("item").order_by("item__inventory_number").first()


class Fieldset(AuditedModel):
    """A named group of custom fields; a material model gets one (MAT-072)."""

    name = models.CharField(
        _("name"),
        max_length=80,
        unique=True,
        error_messages={"unique": _("A fieldset with this name already exists.")},
    )
    description = models.CharField(_("description"), max_length=250, blank=True)

    class Meta:
        verbose_name = _("fieldset")
        verbose_name_plural = _("fieldsets")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def entries_in_order(self) -> list[FieldsetEntry]:
        """The fields of the fieldset in their order, each with whether it is required here."""
        return list(self.entries.select_related("field").order_by("position", "field__name"))


class FieldsetEntry(AuditedModel):
    """One field of a fieldset: its place and whether it is required there (MAT-072)."""

    fieldset = models.ForeignKey(Fieldset, verbose_name=_("fieldset"), on_delete=models.CASCADE, related_name="entries")
    field = models.ForeignKey(
        CustomField, verbose_name=_("custom field"), on_delete=models.CASCADE, related_name="fieldset_entries"
    )
    position = models.PositiveSmallIntegerField(_("position"), default=1)
    is_required = models.BooleanField(_("required field"), default=False)

    class Meta:
        verbose_name = _("field of a fieldset")
        verbose_name_plural = _("fields of fieldsets")
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["fieldset", "field"], name="customfields_entry_unique")]

    def __str__(self) -> str:
        return f"{self.fieldset.name}: {self.field.name}"

    def audit_parent(self) -> models.Model | None:
        """Changes show in the history of the fieldset."""
        return self.fieldset

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save; fieldsets kept for the request are read again."""
        super().save(*args, **kwargs)
        forget_cached_fields()

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Delete; fieldsets kept for the request are read again."""
        result = super().delete(*args, **kwargs)
        forget_cached_fields()
        return result


class ModelFieldset(AuditedModel):
    """The fieldset of a material model – at most one (MAT-072)."""

    material_model = models.OneToOneField(
        MaterialModel, verbose_name=_("material model"), on_delete=models.CASCADE, related_name="custom_fieldset"
    )
    fieldset = models.ForeignKey(
        Fieldset, verbose_name=_("fieldset"), on_delete=models.PROTECT, related_name="assignments"
    )

    class Meta:
        verbose_name = _("fieldset of a material model")
        verbose_name_plural = _("fieldsets of material models")

    def __str__(self) -> str:
        return f"{self.material_model.name}: {self.fieldset.name}"

    def audit_parent(self) -> models.Model | None:
        """The assignment shows in the history of the material model."""
        return self.material_model

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save; fieldsets kept for the request are read again."""
        super().save(*args, **kwargs)
        forget_cached_fields()

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Delete; fieldsets kept for the request are read again."""
        result = super().delete(*args, **kwargs)
        forget_cached_fields()
        return result


class CustomFieldValue(AuditedModel):
    """The value of one custom field for one item (MAT-073).

    Exactly one of ``value`` and ``protected_value`` holds the text: the
    second for a field visible only with the right to see purchase prices.
    An emptied value keeps its row, so that its history stays with the item.
    """

    item = models.ForeignKey(
        MaterialItem, verbose_name=_("material item"), on_delete=models.CASCADE, related_name="custom_values"
    )
    field = models.ForeignKey(
        CustomField, verbose_name=_("custom field"), on_delete=models.CASCADE, related_name="values"
    )
    value = models.TextField(_("value"), blank=True)
    protected_value = models.TextField(_("value only for who may see purchase prices"), blank=True)

    audit_sensitive = {"protected_value": SpecialRight.PURCHASE_PRICES}

    class Meta:
        verbose_name = _("value of a custom field")
        verbose_name_plural = _("values of custom fields")
        constraints = [models.UniqueConstraint(fields=["item", "field"], name="customfields_value_unique")]

    def __str__(self) -> str:
        return f"{self.item.display_id} {self.field.name}"

    def audit_parent(self) -> models.Model | None:
        """The value shows in the history of its item (MAT-025)."""
        return self.item

    @property
    def stored(self) -> str:
        """The stored text, whichever column holds it."""
        return self.protected_value or self.value

    def put(self, text: str) -> None:
        """Store a canonical text in the column its field asks for, and empty the other one."""
        if self.field.is_sensitive:
            self.value, self.protected_value = "", text
        else:
            self.value, self.protected_value = text, ""

    def column_matches(self) -> bool:
        """Whether the text sits in the column its field asks for (it moves when the field becomes sensitive)."""
        return not self.stored or bool(self.protected_value) == self.field.is_sensitive

    def _loaded(self, name: str) -> Any:
        """The value of a column as loaded from the database (``None`` for a new row)."""
        before = self._audit_before()
        return before.get(name) if before is not None else None

    @classmethod
    def audit_hidden(cls, entry: Any, rights: Rights) -> frozenset[str]:
        """The columns of a log entry hidden from this reader beyond ``audit_sensitive`` (MAT-071).

        A field marked sensitive after items had values: the log noted those
        values in the open column ``value``. Readers without the right to see
        purchase prices see none of them – whatever column an entry names. A
        value whose field is gone counts as sensitive if it ever was. Asked by
        the system-wide change log (``core.history.visible_changes``); the
        history of an item decides for all its entries at once
        (``customfields.history``).
        """
        if rights.has(SpecialRight.PURCHASE_PRICES):
            return frozenset()
        return frozenset({"value", "protected_value"}) if _sensitive_now(str(entry.object_id)) else frozenset()


def _sensitive_now(object_id: str) -> bool:
    """Whether the value with this ID belongs to a sensitive field – or, deleted, was ever protected; kept per request."""
    from rentalars.core.models import _request_cache

    cache = _request_cache.get()
    key = (SENSITIVE_CACHE_KEY, object_id)
    if cache is not None and key in cache:
        return cache[key]
    marked = (
        CustomFieldValue.objects.filter(pk=int(object_id)).values_list("field__is_sensitive", flat=True).first()
        if object_id.isdigit()
        else None
    )
    if marked is None:
        from rentalars.customfields.history import ever_protected

        marked = object_id in ever_protected({object_id})
    if cache is not None:
        cache[key] = marked
    return marked


def forget_cached_fields() -> None:
    """Drop the custom fields and fieldsets kept for the current request – after a definition changed."""
    from rentalars.core.models import _request_cache

    cache = _request_cache.get()
    if cache is not None:
        cache.pop(LIST_FIELDS_CACHE_KEY, None)
        prefixes = {ENTRIES_CACHE_KEY, SENSITIVE_CACHE_KEY}
        for key in [key for key in cache if isinstance(key, tuple) and key[:1] and key[0] in prefixes]:
            cache.pop(key, None)


#: Where the fields marked "in lists" are kept for the rest of a request (``core.models._request_cache``).
LIST_FIELDS_CACHE_KEY = "customfields_list_fields"
#: Where the fieldset entries of a material model are kept for the rest of a request, with the model's ID.
ENTRIES_CACHE_KEY = "customfields_entries"
#: Where it is kept for the rest of a request whether a value (by its ID) is sensitive now (MAT-071).
SENSITIVE_CACHE_KEY = "customfields_sensitive"
