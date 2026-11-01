# SPDX-License-Identifier: GPL-3.0-or-later
"""Electrical inspections after DGUV Vorschrift 3 and DIN VDE 0701-0702 (MAT-078; MAT-030, MAT-031).

An inspection type marked "electrical" (``InspectionType.is_electrical``) asks for what the standard
checks, in its order: visual inspection, protective conductor resistance R_PE, insulation resistance R_ISO,
protective conductor current I_PE and touch current I_B, function test – with the protection class of the
device, the length of its cord and the test device used. This module holds

* the **limits** as data, in one place (:data:`LIMITS`, with their source),
* which measurements an inspection of a protection class **needs** (:data:`REQUIRED`, with their source),
* which measurement **applies** to which protection class (:data:`MEASUREMENTS`),
* the **evaluation** (:func:`evaluate`): every value against its limit and the suggested result –
  "passed" when the visual inspection passed, every measurement the protection class needs was made, no
  function test failed and every value given is within its limit; otherwise "failed" with the reasons
  (a needed value that was not measured is a reason, too),
* the **rules** of recording (:func:`clean_values`): the protection class and the visual inspection are
  needed, a value only where it applies, and "passed" against the suggestion only with a reason in the note.

The page, its live check, the API and the printed protocol all use it; nothing else knows a limit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.money import format_decimal
from rentalars.material.models import InspectionResult, InspectionType, ProtectionClass


@dataclass(frozen=True)
class Limits:
    """The limits of an electrical inspection; see :data:`LIMITS`."""

    #: Protective conductor resistance R_PE at most, for a cord up to ``pe_resistance_up_to_m``.
    pe_resistance_ohm: Decimal
    pe_resistance_up_to_m: Decimal
    #: … plus ``pe_resistance_step_ohm`` for every further ``pe_resistance_step_m`` begun …
    pe_resistance_step_ohm: Decimal
    pe_resistance_step_m: Decimal
    #: … but never more than this.
    pe_resistance_max_ohm: Decimal
    #: Insulation resistance R_ISO at least, by protection class.
    insulation_resistance_mohm: Mapping[str, Decimal]
    #: Protective conductor current I_PE at most.
    pe_current_ma: Decimal
    #: Touch current I_B at most.
    touch_current_ma: Decimal


#: The limits of DIN VDE 0701-0702:2008-06 ("Prüfung nach Instandsetzung, Änderung elektrischer Geräte –
#: Wiederholungsprüfung elektrischer Geräte – Allgemeine Anforderungen für die elektrische Sicherheit"),
#: sections 5.3 to 5.7 and table 1 – the standard that DGUV Vorschrift 3 (§ 5) and DGUV Information 203-071
#: name for portable devices. The only place in Rentalars where a limit is written down.
LIMITS = Limits(
    # 5.3: 0.3 Ω for cords up to 5 m, plus 0.1 Ω for every further 7.5 m begun, 1 Ω at most.
    pe_resistance_ohm=Decimal("0.3"),
    pe_resistance_up_to_m=Decimal("5"),
    pe_resistance_step_ohm=Decimal("0.1"),
    pe_resistance_step_m=Decimal("7.5"),
    pe_resistance_max_ohm=Decimal("1"),
    # 5.4, table 1: 1 MΩ for protection class I, 2 MΩ for II, 0.25 MΩ for III.
    insulation_resistance_mohm=MappingProxyType(
        {
            ProtectionClass.I.value: Decimal("1"),
            ProtectionClass.II.value: Decimal("2"),
            ProtectionClass.III.value: Decimal("0.25"),
        }
    ),
    # 5.5, table 1: 3.5 mA protective conductor current (class I).
    pe_current_ma=Decimal("3.5"),
    # 5.6, table 1: 0.5 mA touch current (class II; class I at conductive parts without protective conductor).
    touch_current_ma=Decimal("0.5"),
)


@dataclass(frozen=True)
class Requirement:
    """A check an electrical inspection of a protection class needs: one of ``any_of`` measured; see :data:`REQUIRED`."""

    #: The measurements (names of :data:`MEASUREMENTS`) of which one is enough – the methods the standard allows.
    any_of: tuple[str, ...]
    #: The reason for "failed" when none of them was measured.
    missing: Any


_INSULATION_MISSING = _("Insulation check missing: measure the insulation resistance or a leakage current.")

#: What an electrical inspection must measure, by protection class (MAT-078, measured values needed) –
#: after DIN VDE 0701-0702:2008-06, sections 5.3 to 5.6 and its test sequence, as DGUV Information 203-071 explains
#: it for portable devices: a device of protection class I needs its protective conductor resistance R_PE (5.3) and
#: a check of its insulation – the insulation resistance R_ISO (5.4) or, the alternative methods of the standard,
#: the protective conductor current I_PE (5.5) or the touch current I_B (5.6); class II needs R_ISO or I_B; for
#: class III (safety extra-low voltage) the visual inspection is enough, R_ISO is measured where it can be.
#: A value that applies but was not measured is no reason for "passed": without these the suggestion is "failed".
REQUIRED: Mapping[str, tuple[Requirement, ...]] = MappingProxyType(
    {
        ProtectionClass.I.value: (
            Requirement(("pe_resistance_ohm",), _("Protective conductor resistance not measured.")),
            Requirement(("insulation_resistance_mohm", "pe_current_ma", "touch_current_ma"), _INSULATION_MISSING),
        ),
        ProtectionClass.II.value: (
            Requirement(("insulation_resistance_mohm", "touch_current_ma"), _INSULATION_MISSING),
        ),
        ProtectionClass.III.value: (),
    }
)


@dataclass(frozen=True)
class Measurement:
    """One value an electrical inspection measures.

    Attributes:
        name: The field of ``Inspection``, of the form and of the API.
        letter, index: The symbol, ``R`` and ``PE`` for R_PE.
        label: What it is called.
        unit: Its unit.
        classes: The protection classes it applies to.
        maximum: ``True``: the value must not exceed its limit; ``False``: it must reach it.
    """

    name: str
    letter: str
    index: str
    label: Any
    unit: str
    classes: frozenset[str]
    maximum: bool

    @property
    def symbol(self) -> str:
        """The symbol as plain text, ``RPE`` – as test devices print it."""
        return f"{self.letter}{self.index}"

    @property
    def symbol_html(self) -> SafeString:
        """The symbol with its index set below: R<sub>PE</sub>."""
        return format_html("{}<sub>{}</sub>", self.letter, self.index)

    @property
    def applies_to_text(self) -> str:
        """For which protection classes it is measured, e.g. "protection class I"."""
        names = [value for value in ProtectionClass.values if value in self.classes]
        if len(names) == 1:
            return gettext("protection class %(class)s") % {"class": names[0]}
        return gettext("protection classes %(first)s and %(last)s") % {
            "first": ", ".join(names[:-1]),
            "last": names[-1],
        }


_ALL = frozenset(ProtectionClass.values)

#: The measurements in the order of the standard (and of the form and the protocol).
MEASUREMENTS: tuple[Measurement, ...] = (
    Measurement("pe_resistance_ohm", "R", "PE", _("Protective conductor resistance"), "Ω", frozenset({"I"}), True),
    Measurement("insulation_resistance_mohm", "R", "ISO", _("Insulation resistance"), "MΩ", _ALL, False),
    Measurement("pe_current_ma", "I", "PE", _("Protective conductor current"), "mA", frozenset({"I"}), True),
    # Class I where it is measured: at conductive parts that are not connected to the protective conductor.
    Measurement("touch_current_ma", "I", "B", _("Touch current"), "mA", frozenset({"I", "II"}), True),
)

MEASUREMENTS_BY_NAME = {measurement.name: measurement for measurement in MEASUREMENTS}

#: Everything an electrical inspection records besides date, inspector, result and note – the fields of the
#: form, of the API and of ``Inspection``.
ELECTRICAL_FIELDS = (
    "protection_class",
    "cord_length_m",
    "test_device",
    "visual_check_passed",
    *MEASUREMENTS_BY_NAME,
    "function_test_passed",
)


def pe_resistance_limit(cord_length_m: Decimal | None) -> Decimal:
    """The highest protective conductor resistance for a cord of this length (DIN VDE 0701-0702, 5.3).

    0.3 Ω up to 5 m, 0.1 Ω more for every further 7.5 m begun, 1 Ω at most: 10 m → 0.4 Ω, 12.5 m → 0.4 Ω,
    12.6 m → 0.5 Ω, 50 m → 0.9 Ω, 60 m → 1 Ω. Without a length the limit of a short cord applies.
    """
    if cord_length_m is None or cord_length_m <= LIMITS.pe_resistance_up_to_m:
        return LIMITS.pe_resistance_ohm
    steps = ((cord_length_m - LIMITS.pe_resistance_up_to_m) / LIMITS.pe_resistance_step_m).to_integral_value(
        rounding=ROUND_CEILING
    )
    return min(LIMITS.pe_resistance_ohm + LIMITS.pe_resistance_step_ohm * steps, LIMITS.pe_resistance_max_ohm)


def limit_for(measurement: Measurement, protection_class: str, cord_length_m: Decimal | None = None) -> Decimal | None:
    """The limit of a measurement for a device of this protection class; ``None`` if it does not apply."""
    if protection_class not in measurement.classes:
        return None
    if measurement.name == "pe_resistance_ohm":
        return pe_resistance_limit(cord_length_m)
    if measurement.name == "insulation_resistance_mohm":
        return LIMITS.insulation_resistance_mohm[protection_class]
    if measurement.name == "pe_current_ma":
        return LIMITS.pe_current_ma
    return LIMITS.touch_current_ma


def _amount(value: Decimal | None, unit: str) -> str:
    """``0,52 Ω`` in the active language."""
    return f"{format_decimal(value)} {unit}" if value is not None else ""


@dataclass(frozen=True)
class ValueCheck:
    """One measured value against its limit."""

    measurement: Measurement
    value: Decimal | None
    #: The limit for the protection class; ``None`` if the measurement does not apply (or no class is known).
    limit: Decimal | None
    protection_class: str
    cord_length_m: Decimal | None
    #: Review: the protection class needs this value (or one of its alternatives) and none was measured.
    required_missing: bool = False

    @property
    def applies(self) -> bool:
        """Whether the measurement belongs to an inspection of this protection class."""
        return self.limit is not None

    @property
    def within(self) -> bool | None:
        """``True`` within the limit, ``False`` outside it, ``None`` not measured or not applicable."""
        if self.value is None or self.limit is None:
            return None
        return self.value <= self.limit if self.measurement.maximum else self.value >= self.limit

    @property
    def value_text(self) -> str:
        """The value with its unit, ``0,52 Ω``; empty if not measured."""
        return _amount(self.value, self.measurement.unit)

    @property
    def limit_text(self) -> str:
        """The limit, ``≤ 0,4 Ω`` or ``≥ 1 MΩ``; empty if it does not apply."""
        if self.limit is None:
            return ""
        return f"{'≤' if self.measurement.maximum else '≥'} {_amount(self.limit, self.measurement.unit)}"

    @property
    def limit_note(self) -> str:
        """What the limit depends on: the length of the cord for R_PE, else nothing."""
        if self.measurement.name != "pe_resistance_ohm" or self.limit is None:
            return ""
        if self.cord_length_m is None or self.cord_length_m <= LIMITS.pe_resistance_up_to_m:
            return gettext("cord up to %(length)s m – enter the length of a longer one") % {
                "length": format_decimal(LIMITS.pe_resistance_up_to_m)
            }
        return gettext("for %(length)s m of cord") % {"length": format_decimal(self.cord_length_m)}

    @property
    def verdict(self) -> str:
        """``ok``, ``exceeded``, ``missing`` (applies, not measured) or ``not_applicable``."""
        if not self.applies:
            return "not_applicable"
        within = self.within
        return "missing" if within is None else "ok" if within else "exceeded"

    @property
    def verdict_text(self) -> str:
        """The verdict in words."""
        if not self.applies:
            if not self.protection_class:
                return gettext("choose the protection class")
            return gettext("only for %(classes)s") % {"classes": self.measurement.applies_to_text}
        return {
            "ok": gettext("within the limit"),
            "exceeded": gettext("outside the limit"),
            "missing": gettext("not measured"),
        }[self.verdict]


@dataclass(frozen=True)
class Evaluation:
    """All values of an electrical inspection against their limits, and the result they suggest."""

    protection_class: str
    cord_length_m: Decimal | None
    visual_check_passed: bool | None
    function_test_passed: bool | None
    checks: tuple[ValueCheck, ...]

    @property
    def complete(self) -> bool:
        """Whether the protection class is known – without it there are no limits."""
        return self.protection_class in ProtectionClass.values

    @property
    def has_entries(self) -> bool:
        """Whether anything was entered yet: visual inspection, function test or a value."""
        return (
            self.visual_check_passed is not None
            or self.function_test_passed is not None
            or any(check.value is not None for check in self.checks)
        )

    @property
    def exceeded(self) -> list[ValueCheck]:
        """The values outside their limits."""
        return [check for check in self.checks if check.within is False]

    @property
    def missing_requirements(self) -> list[Requirement]:
        """What the protection class needs and was not measured (:data:`REQUIRED`)."""
        measured = {check.measurement.name for check in self.checks if check.value is not None}
        return [
            requirement
            for requirement in REQUIRED.get(self.protection_class, ())
            if not measured.intersection(requirement.any_of)
        ]

    @property
    def reasons(self) -> list[str]:
        """Why the values speak for "failed"; empty if they speak for "passed".

        Review (MAT-078): a measurement the protection class needs and that was not made is a reason, too.
        """
        reasons = []
        if self.visual_check_passed is None:
            reasons.append(gettext("Visual inspection not recorded."))
        elif not self.visual_check_passed:
            reasons.append(gettext("Visual inspection not passed."))
        reasons.extend(str(requirement.missing) for requirement in self.missing_requirements)
        for check in self.exceeded:
            reasons.append(
                gettext("%(symbol)s %(value)s is outside the limit %(limit)s.")
                % {"symbol": check.measurement.symbol, "value": check.value_text, "limit": check.limit_text}
            )
        if self.function_test_passed is False:
            reasons.append(gettext("Function test not passed."))
        return reasons

    @property
    def suggested_result(self) -> str:
        """``passed`` or ``failed``; empty while the protection class is not known."""
        if not self.complete:
            return ""
        return InspectionResult.FAILED.value if self.reasons else InspectionResult.PASSED.value

    @property
    def suggested_result_label(self) -> str:
        """The suggested result in words."""
        return str(InspectionResult(self.suggested_result).label) if self.suggested_result else ""

    def needs_reason(self, result: str) -> bool:
        """Whether choosing ``result`` needs a reason in the note: "passed" although the values speak against it."""
        return result == InspectionResult.PASSED and self.suggested_result == InspectionResult.FAILED

    def as_dict(self) -> dict[str, Any]:
        """The evaluation as plain data for the API."""
        return {
            "protection_class": self.protection_class,
            "cord_length_m": _plain(self.cord_length_m),
            "values": [
                {
                    "name": check.measurement.name,
                    "symbol": check.measurement.symbol,
                    "unit": check.measurement.unit,
                    "value": _plain(check.value),
                    "limit": _plain(check.limit),
                    "limit_kind": "max" if check.measurement.maximum else "min",
                    "applies": check.applies,
                    "within_limit": check.within,
                    # Review: needed for the protection class (alone or as an alternative), not measured.
                    "required_missing": check.required_missing,
                }
                for check in self.checks
            ],
            "suggested_result": self.suggested_result,
            "reasons": self.reasons,
        }


def _plain(value: Decimal | None) -> str | None:
    """A number as the API writes decimals: a text with a point, ``"0.4"``; ``None`` stays."""
    return None if value is None else format(value.normalize(), "f")


def _decimal(value: Any) -> Decimal | None:
    """A number given as Decimal, int, float or text (``"0,52"``); ``None`` for empty or not a number.

    Review (MAT-078, MAT-010): "NaN" and "Infinity" are no numbers – a stored "NaN" broke the page.
    """
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _largest(name: str) -> Decimal:
    """The largest value the field ``name`` of ``Inspection`` holds: 9999.99 for the cord length."""
    from rentalars.material.models import Inspection

    field = Inspection._meta.get_field(name)
    return Decimal(10) ** (field.max_digits - field.decimal_places) - Decimal(1).scaleb(-field.decimal_places)


def _yes_no(value: Any) -> bool | None:
    """``True``, ``False`` or ``None`` (not done, does not apply)."""
    return None if value is None else bool(value)


def evaluate(values: Mapping[str, Any]) -> Evaluation:
    """Judge the values of an electrical inspection (keys of :data:`ELECTRICAL_FIELDS`; missing ones are empty)."""
    protection_class = str(values.get("protection_class") or "")
    cord_length = _decimal(values.get("cord_length_m"))
    measured = {name: _decimal(values.get(name)) for name in MEASUREMENTS_BY_NAME}
    # Review: the measurements of the needs (REQUIRED) of which none was made.
    unmet = {
        name
        for requirement in REQUIRED.get(protection_class, ())
        if all(measured[name] is None for name in requirement.any_of)
        for name in requirement.any_of
    }
    checks = tuple(
        ValueCheck(
            measurement=measurement,
            value=measured[measurement.name],
            limit=limit_for(measurement, protection_class, cord_length),
            protection_class=protection_class,
            cord_length_m=cord_length,
            required_missing=measurement.name in unmet,
        )
        for measurement in MEASUREMENTS
    )
    return Evaluation(
        protection_class=protection_class,
        cord_length_m=cord_length,
        visual_check_passed=values.get("visual_check_passed"),
        function_test_passed=values.get("function_test_passed"),
        checks=checks,
    )


def evaluate_inspection(inspection: Any) -> Evaluation:
    """The evaluation of a recorded inspection."""
    return evaluate({name: getattr(inspection, name) for name in ELECTRICAL_FIELDS})


def clean_values(
    inspection_type: InspectionType, values: Mapping[str, Any] | None, *, result: str, note: str
) -> dict[str, Any]:
    """Check what an inspection records besides date, inspector and result; return the fields to store.

    For an electrical inspection: the protection class and the visual inspection are needed; a value is
    empty where it was not measured, never negative, and only given where it applies to the protection class
    (R_PE and I_PE for class I, I_B for I and II). "Passed" although the values speak for "failed" needs a
    reason in the note – also when a measurement the class needs (:data:`REQUIRED`)
    was not made. Any other inspection takes no measured values.

    Raises:
        ValidationError: By the names of :data:`ELECTRICAL_FIELDS` (and ``note``, ``inspection_type``).
    """
    given = {name: value for name, value in (values or {}).items() if value not in (None, "")}
    if not inspection_type.is_electrical:
        if given:
            raise ValidationError(
                {
                    "inspection_type": _("Only an electrical inspection takes measured values; “%(type)s” is none.")
                    % {"type": inspection_type.name}
                }
            )
        return {}
    errors: dict[str, Any] = {}
    protection_class = str(given.get("protection_class", ""))
    if protection_class not in ProtectionClass.values:
        errors["protection_class"] = _("Choose the protection class: the limits depend on it.")
    if given.get("visual_check_passed") not in (True, False):
        errors["visual_check_passed"] = _("Did the visual inspection pass?")
    if given.get("function_test_passed") not in (True, False, None):
        errors["function_test_passed"] = _("Did the function test pass?")
    cleaned: dict[str, Any] = {
        "protection_class": protection_class,
        "test_device": str(given.get("test_device", "")).strip()[:120],
        "visual_check_passed": _yes_no(given.get("visual_check_passed")),
        "function_test_passed": _yes_no(given.get("function_test_passed")),
    }
    for name in ("cord_length_m", *MEASUREMENTS_BY_NAME):
        value = _decimal(given.get(name))
        if name in given and value is None:
            errors[name] = _("Enter a number.")
        elif value is not None and value < 0:
            errors[name] = _("A measured value is never negative.")
        elif value is not None and value > _largest(name):
            # Review (MAT-010): a cord length taken from the category may be more than the field holds.
            errors[name] = _("The value is too large (at most %(maximum)s).") % {
                "maximum": format_decimal(_largest(name))
            }
        elif value is not None and name in MEASUREMENTS_BY_NAME and protection_class in ProtectionClass.values:
            measurement = MEASUREMENTS_BY_NAME[name]
            if protection_class not in measurement.classes:
                errors[name] = _("Only measured for %(classes)s. Leave it empty for protection class %(class)s.") % {
                    "classes": measurement.applies_to_text,
                    "class": protection_class,
                }
        cleaned[name] = value
    if errors:
        raise ValidationError(errors)
    evaluation = evaluate(cleaned)
    if evaluation.needs_reason(result) and not (note or "").strip():
        raise ValidationError(
            {
                "note": _(
                    "The values speak for “failed”: %(reasons)s If the item passed nonetheless, give the reason "
                    "in the note."
                )
                % {"reasons": " ".join(evaluation.reasons)}
            }
        )
    return cleaned


# --- The length of the cord, from the category-specific values (MAT-009, MAT-013) -------------------------------

#: Labels of a category field that holds the length of a cable (the start data has "Länge" in m for "Kabel").
LENGTH_FIELD_LABELS = frozenset({"länge", "length", "kabellänge", "leitungslänge", "cable length", "cord length"})
#: The units such a field may have, with their factor to metres.
LENGTH_UNITS = MappingProxyType({"m": Decimal("1"), "cm": Decimal("0.01"), "mm": Decimal("0.001")})


def cord_length_of(item: Any, *, fields_by_category: dict[int, list[Any]] | None = None) -> Decimal | None:
    """The length of the item's cord in metres, from the category-specific field "Länge" – its own value first.

    The field of the category (or of the parent it inherits from) whose label is "Länge" or "Length" and
    whose unit is m, cm or mm; ``None`` if there is no such field or no value. MAT-010: a stored
    value that is no finite number ("NaN", "Infinity" from before the field refused them) counts as none.

    ``fields_by_category``: a dictionary the caller keeps across many items (a mass inspection, MAT-082) – the
    fields of a category are then asked for once, not per item.
    """
    from rentalars.masterdata.models import FieldType

    model = item.material_model
    if fields_by_category is None:
        fields = list(model.category.applicable_fields())
    else:
        if model.category_id not in fields_by_category:
            fields_by_category[model.category_id] = list(model.category.applicable_fields())
        fields = fields_by_category[model.category_id]
    for field in fields:
        factor = LENGTH_UNITS.get(field.unit.strip().lower())
        if field.field_type != FieldType.NUMBER or factor is None:
            continue
        if field.label.strip().lower() not in LENGTH_FIELD_LABELS:
            continue
        key = str(field.pk)
        for stored in ((item.field_value_overrides or {}).get(key), (model.field_values or {}).get(key)):
            value = _decimal(stored)
            if value is not None:
                return (value * factor).normalize()
    return None
