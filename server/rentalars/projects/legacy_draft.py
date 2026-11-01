# SPDX-License-Identifier: GPL-3.0-or-later
"""The proposal of one old invoice: what is read from it and edited in the preview (legacy import; PRJ-130).

The requirement: import of old projects based on invoices. Whatever reads an invoice – the AI
(:mod:`rentalars.ai.legacy_invoices`) or the text patterns (:mod:`rentalars.projects.legacy_text`) – hands over a
:class:`Draft`: customer, invoice head, positions and the totals the invoice states. The preview edits it, the checks
(:mod:`rentalars.projects.legacy_import`) read it, the confirmation creates objects from it.

* A draft is *data from outside*: :meth:`Draft.from_json` and :meth:`Draft.from_post` take only the known keys and
  types, cut every text to the length of its column (MariaDB enforces them, SQLite does not), clean control
  characters, and parse every number with :func:`decimal_of` – a decimal that is finite and of sensible size, never a
  float, never ``NaN``.
* It is stored as JSON (``LegacyImportItem.proposal``): amounts and dates as plain text (``"1234.50"``,
  ``"2025-03-10"``), independent of the language of the page.
* Texts and numbers typed in the preview are read in the language of the page (:func:`rentalars.core.money.parse_decimal`).

Matching against what exists lives here too: customers (:func:`customer_candidates`), products
(:func:`product_suggestions`), units and tax rates.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from rentalars.core.money import CENT, money, parse_decimal

ZERO = Decimal("0")

#: The most positions of one invoice – a guard against a runaway answer (as for purchases).
MAX_LINES = 100

#: The length of each text, as the column that takes it (MariaDB enforces them).
LIMITS = {
    "name": 200,
    "name_addition": 200,
    "street": 200,
    "postal_code": 20,
    "city": 120,
    "country": 80,
    "vat_id": 30,
    "email": 254,
    "number": 40,  # Document.number
    "event_name": 200,  # Project.name
    "venue": 250,  # Project.venue
    "title": 200,  # MaterialLine.title
    "note": 2000,
    "unit": 12,  # Unit.abbreviation
    "currency": 3,
}

#: The largest money amount and quantity that fits the columns (``DecimalField(max_digits=10, decimal_places=2)``).
MAX_PRICE = Decimal("99999999.99")
MAX_QUANTITY = Decimal("99999999.99")
#: A document's totals have 12 digits.
MAX_TOTAL = Decimal("9999999999.99")

_NUMBER_SHAPE = re.compile(r"[+-]?[\d.,'   ]{1,32}")
_NUMBER_NOT_ALLOWED = re.compile(r"[^\d.,\s'+\-  ]")


def clip(value: Any, limit: int) -> str:
    """A short single-line text: strings and numbers only, control characters removed, blanks squeezed, cut to ``limit``."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int | float | Decimal):
        value = str(value)
    if not isinstance(value, str):
        return ""
    cleaned = "".join(character for character in value if unicodedata.category(character)[0] != "C")
    return " ".join(cleaned.split())[:limit]


def long_text(value: Any, limit: int = LIMITS["note"]) -> str:
    """A text that may have line breaks: control characters other than line breaks removed, cut to ``limit``."""
    if not isinstance(value, str):
        return ""
    cleaned = "".join(
        character
        for character in value.replace("\r\n", "\n").replace("\r", "\n")
        if character == "\n" or unicodedata.category(character)[0] != "C"
    )
    return cleaned.strip()[:limit]


def decimal_of(
    value: Any, *, places: int | None = None, limit: Decimal = MAX_PRICE, negative: bool = False
) -> Decimal | None:
    """A number from stored JSON or from an answer: a ``Decimal`` that is finite and within ``limit``; else ``None``.

    Text is read as plain (``"1234.50"``) – the language of the page does not matter for stored values. ``float``
    comes through its text, never as a binary fraction. ``places`` rounds (commercially) to that many places.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or abs(number) > limit or (number < 0 and not negative):
        return None
    if places is not None:
        number = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return number


def typed_decimal(
    text: str, *, places: int | None = None, limit: Decimal = MAX_PRICE, negative: bool = False
) -> Decimal | None:
    """A number typed on the page, in the language of the page (``1.234,50`` or ``1,234.50``); ``None`` if it is none."""
    text = (text or "").strip()
    if not text or len(text) > 32 or _NUMBER_NOT_ALLOWED.search(text) or not _NUMBER_SHAPE.fullmatch(text):
        return None
    try:
        number = parse_decimal(text.replace(" ", " ").replace(" ", " "))
    except (InvalidOperation, ValueError):
        return None
    return decimal_of(number, places=places, limit=limit, negative=negative)


def canon(value: Decimal | None) -> str:
    """A decimal as stored: plain digits with a point, no exponent; empty for ``None``."""
    return "" if value is None else format(value, "f")


def date_of(value: Any) -> datetime.date | None:
    """A date from stored JSON (``2025-03-10``) or typed (``10.03.2025``); ``None`` if it is none or implausible."""
    if isinstance(value, datetime.date):
        return value
    text = clip(value, 12)
    for pattern, order in ((r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"), (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "dmy")):
        match = re.fullmatch(pattern, text)
        if match is None:
            continue
        parts = dict(zip(order, (int(part) for part in match.groups()), strict=True))
        try:
            found = datetime.date(parts["y"], parts["m"], parts["d"])
        except ValueError:
            return None
        return found if datetime.date(1970, 1, 1) <= found <= datetime.date(2100, 12, 31) else None
    return None


def iso(value: datetime.date | None) -> str:
    """A date as stored."""
    return value.isoformat() if value else ""


#: What a position of an old invoice is: the three divisions of an invoice document (DOK-025) – material
#: becomes a material line, personnel a crew line, logistics a vehicle booking with a trip at a flat rate.
KIND_MATERIAL = "material"
KIND_CREW = "crew"
KIND_LOGISTICS = "logistics"
KINDS = (KIND_MATERIAL, KIND_CREW, KIND_LOGISTICS)

#: A word in the text of a position that points to staff or to transport; found anywhere in a word ("Tontechniker").
_CREW_WORDS = (
    "techniker", "technician", "ingenieur", "engineer", "operator", "helfer", "personal", "stagehand", "rigger",
    "crew", "fachkraft", "meister", "betreuung", "fahrer", "driver", "regie", "produktionsleitung", "projektleitung",
    "bühnenmeister", "arbeitszeit", "arbeitsstunde", "staff", "aufbaupersonal", "techn.",
)  # fmt: skip
_LOGISTICS_WORDS = (
    "transport", "fahrt", "anfahrt", "abfahrt", "rückfahrt", "lieferung", "anlieferung", "abholung", "spedition",
    "kilometer", "sprinter", "lkw", "transporter", "fahrzeug", "kurier", "delivery", "pickup", "freight", "shipping",
    "trailer", "anhänger", "logistik", "logistic", "vehicle", "pkw",
)  # fmt: skip
#: Words that contain a word of the lists above and mean something else ("Regiepult" is a desk, not "Regie").
_FALSE_FRIENDS = (
    "regiepult", "personalcomputer", "anhängerkupplung", "auffahrt", "einfahrt", "ausfahrt", "durchfahrt",
    "transportcase", "transportbox", "transportkoffer", "transportwagen", "transportrolle", "transportkiste",
)  # fmt: skip
HOUR_UNITS = frozenset({"h", "std", "stunde", "stunden", "hour", "hours", "hrs", "hr"})
_KM_UNITS = frozenset({"km", "kilometer"})


def kind_of(value: Any) -> str:
    """A kind from an answer or stored JSON: one of :data:`KINDS`; ``""`` if it is none (the patterns then guess)."""
    text = clip(value, 20).casefold()
    aliases = {
        "personnel": KIND_CREW,
        "personal": KIND_CREW,
        "staff": KIND_CREW,
        "crew": KIND_CREW,
        "logistics": KIND_LOGISTICS,
        "logistik": KIND_LOGISTICS,
        "transport": KIND_LOGISTICS,
        "material": KIND_MATERIAL,
        "equipment": KIND_MATERIAL,
    }
    return aliases.get(text, "")


def guess_kind(title: str, unit: str = "", note: str = "") -> str:
    """Whether a position is material, personnel or logistics, by its words and unit – a proposal the preview shows.

    A unit of hours and words for staff say personnel, kilometres and words for transport say logistics; whatever says
    nothing is material. Rentals "per day" are no hint: the unit "Tag" counts for nothing.
    """
    text = f"{title} {note}".casefold()
    for friend in _FALSE_FRIENDS:
        text = text.replace(friend, " ")
    unit_text = clip(unit, LIMITS["unit"]).strip(". ").casefold()
    crew = sum(word in text for word in _CREW_WORDS) + (1 if unit_text in HOUR_UNITS else 0)
    logistics = sum(word in text for word in _LOGISTICS_WORDS) + (2 if unit_text in _KM_UNITS else 0)
    if logistics > crew:
        return KIND_LOGISTICS
    if crew > logistics:
        return KIND_CREW
    return KIND_MATERIAL


def title_and_details(value: Any, limit: int = LIMITS["title"]) -> tuple[str, str]:
    """The text of a position as the title (its first line, cut at a blank to ``limit``) and the rest as the description.

    Old invoices print "Funkmikrofon-Set" and below it "Sennheiser EW 100, inkl. Akkus …": the title is the first line,
    nothing of the rest is lost – a first line that is longer than the column goes over into the description.
    """
    text = long_text(value, 4000)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return "", ""
    first, rest = lines[0], lines[1:]
    if len(first) > limit:
        cut = first.rfind(" ", 0, limit)
        cut = cut if cut >= limit // 2 else limit
        rest.insert(0, first[cut:].strip())
        first = first[:cut].strip()
    return first, "\n".join(rest)[: LIMITS["note"]]


# --- The parts of a draft ------------------------------------------------------------------------------------------


@dataclass
class CustomerPart:
    """The customer as the invoice names him, and which customer of the system it is (or that it is a new one)."""

    #: The customer of the system chosen for it; ``None``: a new customer is created when the invoice is taken over.
    customer_id: int | None = None
    name: str = ""
    name_addition: str = ""
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = ""
    vat_id: str = ""
    email: str = ""
    #: Confirms a new customer although one with the same name or VAT ID exists.
    allow_duplicate: bool = False

    @classmethod
    def from_json(cls, raw: Any) -> CustomerPart:
        """Read the stored part strictly."""
        raw = raw if isinstance(raw, dict) else {}
        customer_id = raw.get("customer_id")
        part = cls(
            customer_id=customer_id if isinstance(customer_id, int) and not isinstance(customer_id, bool) else None,
            allow_duplicate=raw.get("allow_duplicate") is True,
        )
        for name in ("name", "name_addition", "street", "postal_code", "city", "country", "email"):
            setattr(part, name, clip(raw.get(name), LIMITS[name]))
        part.vat_id = vat_id_of(raw.get("vat_id"))
        return part

    def to_json(self) -> dict[str, Any]:
        """The part for the database."""
        return {
            "customer_id": self.customer_id,
            "name": self.name,
            "name_addition": self.name_addition,
            "street": self.street,
            "postal_code": self.postal_code,
            "city": self.city,
            "country": self.country,
            "vat_id": self.vat_id,
            "email": self.email,
            "allow_duplicate": self.allow_duplicate,
        }


def vat_id_of(value: Any) -> str:
    """A VAT ID as the customer master data keeps it: capitals, no blanks, cut to the column."""
    return "".join(clip(value, 60).split()).upper()[: LIMITS["vat_id"]]


@dataclass
class InvoicePart:
    """The head of the invoice: number, date, service period, event, and whether it was paid."""

    number: str = ""
    date: datetime.date | None = None
    service_start: datetime.date | None = None
    service_end: datetime.date | None = None
    event_name: str = ""
    venue: str = ""
    currency: str = "EUR"
    due_on: datetime.date | None = None
    paid: bool = False
    paid_on: datetime.date | None = None

    @classmethod
    def from_json(cls, raw: Any) -> InvoicePart:
        """Read the stored part strictly."""
        raw = raw if isinstance(raw, dict) else {}
        number = re.sub(r"[^A-Za-z0-9\-/._ ]", "", clip(raw.get("number"), LIMITS["number"] * 2)).strip()
        return cls(
            number=number[: LIMITS["number"]],
            date=date_of(raw.get("date")),
            service_start=date_of(raw.get("service_start")),
            service_end=date_of(raw.get("service_end")),
            event_name=clip(raw.get("event_name"), LIMITS["event_name"]),
            venue=clip(raw.get("venue"), LIMITS["venue"]),
            currency=currency_of(raw.get("currency")),
            due_on=date_of(raw.get("due_on")),
            paid=raw.get("paid") is True,
            paid_on=date_of(raw.get("paid_on")),
        )

    def to_json(self) -> dict[str, Any]:
        """The part for the database."""
        return {
            "number": self.number,
            "date": iso(self.date),
            "service_start": iso(self.service_start),
            "service_end": iso(self.service_end),
            "event_name": self.event_name,
            "venue": self.venue,
            "currency": self.currency,
            "due_on": iso(self.due_on),
            "paid": self.paid,
            "paid_on": iso(self.paid_on),
        }


def currency_of(value: Any) -> str:
    """A currency as its code: "€", "Euro" → ``EUR``; an empty value is ``EUR``, the currency of the system."""
    text = clip(value, 12).casefold()
    if text in {"", "€", "eur", "euro", "euros"}:
        return "EUR"
    return text.upper() if re.fullmatch(r"[a-z]{3}", text) else text.upper()[: LIMITS["currency"]]


@dataclass
class Totals:
    """The totals the invoice states – what the positions are compared with."""

    net: Decimal | None = None
    tax: Decimal | None = None
    gross: Decimal | None = None

    @classmethod
    def from_json(cls, raw: Any) -> Totals:
        """Read the stored part strictly."""
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            net=decimal_of(raw.get("net"), places=2, limit=MAX_TOTAL, negative=True),
            tax=decimal_of(raw.get("tax"), places=2, limit=MAX_TOTAL, negative=True),
            gross=decimal_of(raw.get("gross"), places=2, limit=MAX_TOTAL, negative=True),
        )

    def to_json(self) -> dict[str, str]:
        """The part for the database."""
        return {"net": canon(self.net), "tax": canon(self.tax), "gross": canon(self.gross)}


@dataclass
class Suggestion:
    """A product of the catalogue that may be the position of the invoice."""

    product_id: int
    label: str
    score: float = 0.0


@dataclass
class Line:
    """One position of the invoice. A *text line* only carries a text (a heading, a remark)."""

    title: str = ""
    note: str = ""
    quantity: Decimal = Decimal("1")
    unit: str = ""
    unit_price: Decimal = ZERO
    discount: Decimal = ZERO
    #: The tax rate in percent as the invoice states it; ``None`` if unknown (the preview asks).
    tax_percent: Decimal | None = None
    #: The product (material), the vehicle product (logistics); for personnel see ``job_function_id``.
    product_id: int | None = None
    is_text: bool = False
    #: ``material``, ``crew`` or ``logistics``; ``""``: not decided yet (the reading proposes one).
    kind: str = ""
    #: The job function of a crew line.
    job_function_id: int | None = None
    #: What the invoice prints as the net amount of this position, if it was read – a check against quantity × price.
    amount: Decimal | None = None
    suggestions: list[Suggestion] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: Any) -> Line:
        """Read one stored position strictly."""
        raw = raw if isinstance(raw, dict) else {}
        is_text = raw.get("is_text") is True
        product_id = raw.get("product_id")
        job_function_id = raw.get("job_function_id")
        suggestions = []
        for entry in raw.get("suggestions") or []:
            if isinstance(entry, dict) and isinstance(entry.get("product_id"), int):
                score = entry.get("score")
                suggestions.append(
                    Suggestion(
                        entry["product_id"],
                        clip(entry.get("label"), 260),
                        float(score) if isinstance(score, int | float) and not isinstance(score, bool) else 0.0,
                    )
                )
        return cls(
            title=clip(raw.get("title"), LIMITS["title"]),
            note=long_text(raw.get("note")),
            quantity=decimal_of(raw.get("quantity"), places=2, limit=MAX_QUANTITY) or ZERO if not is_text else ZERO,
            unit=clip(raw.get("unit"), LIMITS["unit"]),
            unit_price=ZERO if is_text else decimal_of(raw.get("unit_price"), places=2, negative=True) or ZERO,
            discount=ZERO if is_text else decimal_of(raw.get("discount"), places=2, limit=Decimal("100")) or ZERO,
            tax_percent=decimal_of(raw.get("tax_percent"), places=2, limit=Decimal("100")),
            product_id=product_id
            if isinstance(product_id, int) and not isinstance(product_id, bool) and not is_text
            else None,
            is_text=is_text,
            kind=kind_of(raw.get("kind")),
            job_function_id=job_function_id
            if isinstance(job_function_id, int) and not isinstance(job_function_id, bool) and not is_text
            else None,
            amount=decimal_of(raw.get("amount"), places=2, limit=MAX_TOTAL, negative=True),
            suggestions=suggestions[:5],
        )

    def to_json(self) -> dict[str, Any]:
        """The position for the database."""
        return {
            "title": self.title,
            "note": self.note,
            "quantity": canon(self.quantity),
            "unit": self.unit,
            "unit_price": canon(self.unit_price),
            "discount": canon(self.discount),
            "tax_percent": canon(self.tax_percent),
            "product_id": self.product_id,
            "is_text": self.is_text,
            "kind": self.kind,
            "job_function_id": self.job_function_id,
            "amount": canon(self.amount),
            "suggestions": [
                {"product_id": entry.product_id, "label": entry.label, "score": round(entry.score, 2)}
                for entry in self.suggestions
            ],
        }

    @property
    def division(self) -> str:
        """The kind of the position, ``material`` while it is not decided."""
        return self.kind if self.kind in KINDS else KIND_MATERIAL

    @property
    def base(self) -> Decimal:
        """Quantity × unit price, in cents; nothing for a text line."""
        return ZERO if self.is_text else money(self.quantity * self.unit_price)

    @property
    def net(self) -> Decimal:
        """The net amount of the position after its discount, in cents – as a project line is calculated."""
        if self.is_text:
            return ZERO
        base = self.base
        return base - money(base * self.discount / Decimal(100))


@dataclass
class Draft:
    """Everything read from one invoice, in the form the preview edits (stored in ``LegacyImportItem.proposal``)."""

    customer: CustomerPart = field(default_factory=CustomerPart)
    invoice: InvoicePart = field(default_factory=InvoicePart)
    lines: list[Line] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)
    #: How it was read: ``ai``, ``text`` (patterns) or ``manual``.
    source: str = "manual"
    #: A note for the user about the reading: the end of a long invoice was not read, the AI was unreachable …
    note: str = ""
    #: What could not be read from a form field, by field key – for the preview, not stored.
    typed_errors: dict[str, str] = field(default_factory=dict)
    #: The text of a field that could not be read, to show it again – for the preview, not stored.
    typed_text: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: Any) -> Draft:
        """Read a stored (or answered) proposal strictly: known keys and types only, texts cut, numbers parsed here."""
        raw = raw if isinstance(raw, dict) else {}
        lines = raw.get("lines")
        lines = lines if isinstance(lines, list) else []
        source = clip(raw.get("source"), 10)
        return cls(
            customer=CustomerPart.from_json(raw.get("customer")),
            invoice=InvoicePart.from_json(raw.get("invoice")),
            lines=[Line.from_json(entry) for entry in lines[:MAX_LINES]],
            totals=Totals.from_json(raw.get("totals")),
            source=source if source in {"ai", "text", "manual"} else "manual",
            note=clip(raw.get("note"), 500),
        )

    def to_json(self) -> dict[str, Any]:
        """The proposal for the database."""
        return {
            "customer": self.customer.to_json(),
            "invoice": self.invoice.to_json(),
            "lines": [line.to_json() for line in self.lines],
            "totals": self.totals.to_json(),
            "source": self.source,
            "note": self.note,
        }

    @property
    def priced_lines(self) -> list[Line]:
        """The positions that carry an amount: all but the text lines."""
        return [line for line in self.lines if not line.is_text]

    @property
    def net_total(self) -> Decimal:
        """The sum of the net amounts of the positions."""
        return sum((line.net for line in self.priced_lines), ZERO)

    def tax_shares(self) -> list[tuple[Decimal | None, Decimal, Decimal]]:
        """Per tax rate (``None``: unknown): the net amount and the tax, the rate highest first."""
        nets: dict[Decimal | None, Decimal] = {}
        for line in self.priced_lines:
            nets[line.tax_percent] = nets.get(line.tax_percent, ZERO) + line.net
        shares = [(rate, net, money(net * (rate or ZERO) / Decimal(100))) for rate, net in nets.items()]
        return sorted(shares, key=lambda share: -(share[0] if share[0] is not None else Decimal(-1)))

    @property
    def tax_total(self) -> Decimal:
        """The tax of all positions, per rate rounded as the documents round it."""
        return sum((tax for _rate, _net, tax in self.tax_shares()), ZERO)

    def range_problems(self) -> list[tuple[str, str]]:
        """Amounts that fit their own column but whose products and sums do not fit the totals.

        Every single number is within its limit when it is read, but quantity × price of one position, the sum of
        the positions and net plus tax can still be larger than a document can hold (12 digits) – MariaDB would
        refuse the row with an error page. Returns ``(field key, "line" | "total")`` for each place; the checks of
        the preview turn them into messages.
        """
        problems = []
        for index, line in enumerate(self.lines):
            if not line.is_text and abs(line.base) > MAX_TOTAL:
                problems.append((f"lines.{index}.unit_price", "line"))
        if not problems:
            net = self.net_total
            if abs(net) > MAX_TOTAL:
                problems.append(("total_net", "total"))
            elif abs(net + self.tax_total) > MAX_TOTAL:
                problems.append(("total_gross", "total"))
        return problems


# --- Reading the preview form ------------------------------------------------------------------------------------------


def _flag(data: Mapping[str, Any], key: str) -> bool:
    """A tick box of a form: ticked if the key is there with a value that is not "off"."""
    return str(data.get(key, "")).lower() in {"on", "1", "true", "yes"}


def draft_from_post(data: Mapping[str, Any], prefix: str, previous: Draft) -> Draft:
    """The draft as the preview form sent it; what is not in the form stays as it was (``previous``).

    ``prefix`` is the item's (``i12-``). Numbers are read in the language of the page; what cannot be read is kept as
    typed in ``typed_text`` and named in ``typed_errors`` – the checks then block taking the invoice over.
    """
    draft = Draft(source=previous.source, note=previous.note)
    errors, texts = draft.typed_errors, draft.typed_text

    def text(key: str, limit: int) -> str:
        return clip(data.get(prefix + key), limit)

    choice = str(data.get(prefix + "customer_choice", "")).strip()
    draft.customer = CustomerPart(
        customer_id=int(choice) if choice.isdigit() and int(choice) < 2**31 else None,
        name=text("customer_name", LIMITS["name"]),
        name_addition=text("customer_name_addition", LIMITS["name_addition"]),
        street=text("customer_street", LIMITS["street"]),
        postal_code=text("customer_postal_code", LIMITS["postal_code"]),
        city=text("customer_city", LIMITS["city"]),
        country=text("customer_country", LIMITS["country"]),
        vat_id=vat_id_of(data.get(prefix + "customer_vat_id")),
        email=text("customer_email", LIMITS["email"]),
        allow_duplicate=_flag(data, prefix + "customer_allow_duplicate"),
    )

    def day(key: str) -> datetime.date | None:
        raw = text(key, 12)
        found = date_of(raw)
        if raw and found is None:
            errors[key] = "date"
            texts[key] = raw
        return found

    number = re.sub(r"[^A-Za-z0-9\-/._ ]", "", text("number", LIMITS["number"] * 2)).strip()[: LIMITS["number"]]
    draft.invoice = InvoicePart(
        number=number,
        date=day("date"),
        service_start=day("service_start"),
        service_end=day("service_end"),
        event_name=text("event_name", LIMITS["event_name"]),
        venue=text("venue", LIMITS["venue"]),
        currency=currency_of(data.get(prefix + "currency", previous.invoice.currency)),
        due_on=previous.invoice.due_on,
        paid=_flag(data, prefix + "paid"),
        paid_on=day("paid_on"),
    )

    def amount(key: str, **options: Any) -> Decimal | None:
        raw = text(key, 40)
        found = typed_decimal(raw, **options)
        if raw and found is None:
            errors[key] = "number"
            texts[key] = raw
        return found

    draft.totals = Totals(
        net=amount("total_net", places=2, limit=MAX_TOTAL, negative=True),
        tax=amount("total_tax", places=2, limit=MAX_TOTAL, negative=True),
        gross=amount("total_gross", places=2, limit=MAX_TOTAL, negative=True),
    )
    count = str(data.get(prefix + "lines-count", "0"))
    total = min(int(count) if count.isdigit() and len(count) < 5 else 0, MAX_LINES + 20)
    for index in range(total):
        key = f"{prefix}l{index}-"
        if _flag(data, key + "remove"):
            continue
        is_text = _flag(data, key + "is_text")
        position = f"lines.{index}."
        title = clip(data.get(key + "title"), LIMITS["title"])
        old = previous.lines[index] if index < len(previous.lines) else None
        line = Line(title=title, is_text=is_text, unit=clip(data.get(key + "unit"), LIMITS["unit"]))
        # The description is typed in the preview; a form without the field (an older page) keeps what was read.
        if key + "note" in data:
            line.note = long_text(data.get(key + "note"))
        elif old is not None:
            line.note = old.note
        kind = kind_of(data.get(key + "kind"))
        line.kind = kind if kind else (old.kind if old is not None else "")
        if not is_text:
            for name, option, default in (
                ("quantity", {"places": 2, "limit": MAX_QUANTITY}, Decimal("1")),
                ("unit_price", {"places": 2, "negative": True}, ZERO),
                ("discount", {"places": 2, "limit": Decimal("100")}, ZERO),
                ("tax", {"places": 2, "limit": Decimal("100")}, None),
            ):
                raw = clip(data.get(key + name), 40)
                found = typed_decimal(raw, **option) if raw else None
                if raw and found is None:
                    errors[position + name] = "number"
                    texts[position + name] = raw
                if name == "tax":
                    line.tax_percent = found
                else:
                    setattr(line, name, found if found is not None else default)
            product = str(data.get(key + "product", "")).strip()
            line.product_id = int(product) if product.isdigit() and int(product) < 2**31 else None
            function = str(data.get(key + "job_function", "")).strip()
            line.job_function_id = int(function) if function.isdigit() and int(function) < 2**31 else None
            if old is not None and old.division != line.division:
                # The kind was changed: what was chosen for the old kind (a product, a function) does not fit the new.
                line.product_id = line.job_function_id = None
        # Suggestions and the printed amount belong to the position as read; they travel with a row of the same title.
        if old is not None and old.title == title:
            line.suggestions, line.amount = old.suggestions, old.amount
            if old.division != line.division and not is_text:
                suggest_for_lines([line])  # the kind was changed: propose a function / vehicle / product that fits it
        draft.lines.append(line)
    return draft


# --- Matching against what exists --------------------------------------------------------------------------------------


@dataclass
class CustomerCandidate:
    """A customer of the system that may be the one named on the invoice."""

    customer_id: int
    name: str
    number: str
    place: str
    reason: str
    #: The VAT ID or the whole name is the same: a safe match; else only a similar name.
    certain: bool


def customer_candidates(part: CustomerPart, *, limit: int = 6) -> list[CustomerCandidate]:
    """The customers that may be the one on the invoice: same VAT ID, same name, similar name; the surest first."""
    from rentalars.customers.models import Customer
    from rentalars.customers.services import find_duplicates, normalised_name

    found: dict[int, CustomerCandidate] = {}

    def add(customer: Any, reason: str, certain: bool) -> None:
        current = found.get(customer.pk)
        if current is None or (certain and not current.certain):
            found[customer.pk] = CustomerCandidate(
                customer.pk,
                customer.name,
                customer.number,
                " ".join(f"{customer.postal_code} {customer.city}".split()),
                str(reason),
                certain,
            )

    if part.vat_id:
        for customer in Customer.objects.filter(vat_id=part.vat_id, anonymised_at__isnull=True)[:limit]:
            add(customer, _("same VAT ID"), True)
    if part.name:
        wanted = normalised_name(part.name)
        if wanted:
            for duplicate in find_duplicates(part.name, part.email)[: limit * 2]:
                same = normalised_name(duplicate.customer.name) == wanted
                add(duplicate.customer, _("same name") if same else duplicate.reason, same)
    if part.name:
        _add_by_address_and_spelling(part, add, found)
    ordered = sorted(found.values(), key=lambda candidate: (not candidate.certain, candidate.name.casefold()))
    return ordered[:limit]


def _add_by_address_and_spelling(part: CustomerPart, add: Any, found: dict[int, CustomerCandidate]) -> None:
    """More ways to recognise a customer: the same postal code and street, or a name spelled a little differently.

    The same postal code and street with a name that is alike (at least 0.7) is a safe match – an old invoice often
    spells the company a bit differently than the customer file does. A name that is alike (at least 0.85) but sits at
    another address is only offered.
    """
    from rentalars.customers.models import Customer
    from rentalars.customers.services import normalised_name

    wanted = normalised_name(part.name)
    if not wanted:
        return
    pool = Customer.objects.filter(anonymised_at__isnull=True)
    street = " ".join(part.street.casefold().split())
    nearby = Q()
    if part.postal_code:
        nearby |= Q(postal_code=part.postal_code)
    for word in sorted(wanted.split(), key=len, reverse=True)[:2]:
        nearby |= Q(name__icontains=word)
    for customer in pool.filter(nearby).order_by("pk")[:300]:
        other = normalised_name(customer.name)
        score = max(  # the words in any order: "Stadtwerke Beispielburg" and "Beispielburg Stadtwerke"
            SequenceMatcher(None, wanted, other).ratio(),
            SequenceMatcher(None, " ".join(sorted(wanted.split())), " ".join(sorted(other.split()))).ratio(),
        )
        same_address = bool(
            street
            and part.postal_code
            and customer.postal_code == part.postal_code
            and " ".join((customer.street or "").casefold().split()) == street
        )
        if same_address and score >= 0.7:
            add(customer, _("same address and a similar name"), True)
        elif score >= 0.85:
            add(customer, _("similar name"), False)


def best_customer(part: CustomerPart) -> CustomerCandidate | None:
    """The one customer that surely is meant (same VAT ID or same name, and only one such); else ``None``."""
    certain = [candidate for candidate in customer_candidates(part) if candidate.certain]
    return certain[0] if len(certain) == 1 else None


_FILLER = frozenset({"stk", "stück", "st", "pcs", "x", "mit", "für", "und", "inkl", "the", "and", "with", "for", "von"})


def _words(text: str) -> list[str]:
    """The words of a position's text that tell products apart: lower case, no filler, three letters or more."""
    folded = unicodedata.normalize("NFKC", text or "").casefold().replace("ß", "ss")
    return [word for word in re.findall(r"[\w]+", folded) if len(word) >= 3 and word not in _FILLER]


def product_suggestions(title: str, *, limit: int = 3, minimum: float = 0.6) -> list[Suggestion]:
    """Products of the catalogue that may be the position, by the article number in its text or a similar name.

    Only products a closed project may carry as a position (rental, sale, kit, incidental costs, subrental) of the
    company – not services, surcharges, vehicles or a customer's own material. The candidates are narrowed by the
    longer words of the text, then ranked by how alike the names are (``difflib``); the article number of a product
    standing in the text counts as a certain match.
    """
    from rentalars.products.models import Product, ProductKind

    words = _words(title)
    if not words:
        return []
    condition = Q()
    for word in sorted(words, key=len, reverse=True)[:4]:
        condition |= Q(name__icontains=word) | Q(article_number__iexact=word)
    kinds = [ProductKind.RENTAL, ProductKind.SALE, ProductKind.KIT, ProductKind.INCIDENTAL, ProductKind.SUBRENTAL]
    candidates = Product.objects.filter(condition, is_active=True, owner__isnull=True, kind__in=kinds).only(
        "id", "article_number", "name"
    )[:200]
    wanted = " ".join(words)
    squeezed = (title or "").casefold()
    ranked = []
    for product in candidates:
        score = SequenceMatcher(None, wanted, " ".join(_words(product.name))).ratio()
        if product.article_number and re.search(
            rf"(?<![\w-]){re.escape(product.article_number.casefold())}(?![\w-])", squeezed
        ):
            score = max(score, 0.99)
        if score >= minimum:
            ranked.append(Suggestion(product.pk, clip(f"{product.article_number} {product.name}", 260), score))
    return sorted(ranked, key=lambda entry: (-entry.score, entry.label))[:limit]


#: A suggestion this alike (or an article number in the text) is chosen beforehand; the user still checks it.
PRESELECT = 0.9


def job_functions_ranked(title: str) -> list[tuple[Any, float]]:
    """All job functions with how well their name fits the text of a position, the best first.

    A name that stands in the text ("Tontechniker" in "Tontechniker FOH") fits best; else the names are compared word by
    word. Only the order and the first one's score matter – the preview offers all of them.
    """
    from rentalars.personnel.models import JobFunction

    wanted = " ".join(_words(title))
    squeezed = (title or "").casefold()
    ranked = []
    for function in JobFunction.objects.select_related("service_product").order_by("name"):
        name = function.name.casefold()
        score = SequenceMatcher(None, wanted, " ".join(_words(function.name))).ratio()
        if name and name in squeezed:
            score = max(score, 0.95)
        ranked.append((function, score))
    return sorted(ranked, key=lambda entry: (-entry[1], -len(entry[0].name), entry[0].name.casefold()))


def vehicles_ranked(title: str) -> list[tuple[Any, float]]:
    """The motor-vehicle products of the fleet with how well their name fits the text of a position, the best first."""
    from rentalars.products.models import Product, ProductKind, VehicleType

    wanted = " ".join(_words(title))
    squeezed = (title or "").casefold()
    ranked = []
    products = Product.objects.filter(
        kind=ProductKind.VEHICLE, vehicle_type=VehicleType.CAR, is_active=True, owner__isnull=True
    ).order_by("name")
    for product in products:
        score = SequenceMatcher(None, wanted, " ".join(_words(product.name))).ratio()
        if product.name and product.name.casefold() in squeezed:
            score = max(score, 0.95)
        ranked.append((product, score))
    return sorted(ranked, key=lambda entry: (-entry[1], -len(entry[0].name), entry[0].name.casefold()))


def suggest_for_lines(lines: list[Line]) -> None:
    """Fill in the suggestions of every position (and choose something beforehand where it is as good as certain).

    Material: products by article number and name. Personnel: the job function whose name fits. Logistics: the
    motor vehicle – beforehand when the fleet has only one or one name stands in the text.
    """
    for line in lines:
        if line.is_text:
            continue
        line.kind = line.kind or guess_kind(line.title, line.unit, line.note)
        if line.kind == KIND_CREW:
            line.suggestions = []
            line.product_id = None
            if line.job_function_id is None:
                ranked = job_functions_ranked(line.title)
                if ranked and ranked[0][1] >= PRESELECT_FUNCTION:
                    line.job_function_id = ranked[0][0].pk
        elif line.kind == KIND_LOGISTICS:
            line.suggestions = []
            line.job_function_id = None
            if line.product_id is None:
                ranked = vehicles_ranked(line.title)
                if len(ranked) == 1 or (ranked and ranked[0][1] >= PRESELECT_FUNCTION):
                    line.product_id = ranked[0][0].pk
        else:
            line.job_function_id = None
            line.suggestions = product_suggestions(line.title)
            if line.product_id is None and line.suggestions and line.suggestions[0].score >= PRESELECT:
                line.product_id = line.suggestions[0].product_id


#: A job function or vehicle this alike to the text of a position is chosen beforehand; the user still checks it.
PRESELECT_FUNCTION = 0.6


def unit_for(text: str) -> Any:
    """The unit of the master data an invoice's unit text names ("Stk", "Std."); ``None`` if there is none."""
    from rentalars.masterdata.models import Unit

    wanted = clip(text, LIMITS["unit"]).strip(". ").casefold()
    if not wanted:
        return None
    aliases = {"st": "stk", "stück": "stk", "pcs": "stk", "std": "h", "stunde": "h", "stunden": "h", "tage": "tag"}
    candidates = {wanted, aliases.get(wanted, wanted)}
    for unit in Unit.objects.filter(is_active=True):
        if {unit.abbreviation.strip(". ").casefold(), unit.name.strip(". ").casefold()} & candidates:
            return unit
    return None


def tax_rate_for(percent: Decimal | None, on: datetime.date | None = None) -> Any:
    """The tax rate of the master data with this percentage – the default one first, then the newest; else ``None``."""
    from rentalars.masterdata.models import TaxRate

    if percent is None:
        return None
    rates = list(TaxRate.objects.filter(rate=percent, is_active=True))
    if not rates:
        return None
    valid = [rate for rate in rates if on is None or rate.valid_from <= on] or rates
    return sorted(valid, key=lambda rate: (not rate.is_default, -rate.valid_from.toordinal(), rate.pk))[0]


def net_from_gross(gross: Decimal, percent: Decimal) -> Decimal:
    """The net price of a gross price (the same rounding as the purchase entry: to cents)."""
    return (gross / (Decimal(1) + percent / Decimal(100))).quantize(CENT, rounding=ROUND_HALF_UP)
