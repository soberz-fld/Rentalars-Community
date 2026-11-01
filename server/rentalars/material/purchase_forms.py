# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of "Kauf einpflegen": the head of a purchase and its positions (MAT-061; MAT-019, MAT-050).

The positions are a Django formset with the prefix ``pos``. Rows are added
by the page script (``data-formset``) or, without it, by the button "another
position"; a row is removed with its box "remove". A row nobody touched is
ignored. Rows that came from an invoice carry its text (``source``) and must
be ticked as checked before the purchase can be saved – nothing read from an
invoice is taken over unseen.

MAT-075: the page starts with one row – further rows come one
at a time from the user or as many as the invoice has from reading it
(:data:`EMPTY_ROWS`). Below the rows the sum of the positions, net and gross,
next to the total of the invoice (:func:`purchase_sums`). A price may be typed
with thousands separators ("1.072,50", :class:`AmountField`; MAT-076).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.forms import StyledForm, mark_required
from rentalars.core.money import decimal_separator, money
from rentalars.masterdata.models import Category, StorageLocation
from rentalars.material import purchases, services
from rentalars.material.forms import LocationChoiceField, stock_products
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.material.numbering import parse_inventory_number

#: The prefix of the positions in the form.
PREFIX = "pos"
#: How many empty rows a new page and the button "another position" offer – MAT-075: one;
#: further ones are added by the AI or the user (it was three).
EMPTY_ROWS = 1
#: Rows a page may hold beyond the most positions – typed rows next to a full invoice; refused on saving.
SPARE_ROWS = 3
#: A total of the invoice as the page carries it from one step to the next: ``1072.50``.
_TOTAL = r"^\d{1,12}\.\d{2}$"


class AmountField(forms.DecimalField):
    """A price as people write it: ``1.072,50``, ``1072,50``, ``1.072,50 €`` – English ``1,072.50`` (MAT-076).

    Django's own field takes no thousands separator (``USE_THOUSAND_SEPARATOR`` is off), so "1.072,50" was
    refused; this one reads it as :func:`rentalars.material.purchases.parse_amount` reads invoices – in the
    style of the interface language.
    """

    def to_python(self, value: Any) -> Decimal | None:
        """The typed text read with thousands separators; what it cannot read, Django's field refuses as before."""
        if isinstance(value, str) and value.strip():
            amount = purchases.parse_amount(value, decimal_comma=decimal_separator() == ",")
            if amount is not None:
                value = amount
        return super().to_python(value)


def product_named(text: str) -> Any:
    """The product a typed text means: its article number, alone or in front of its name ("K-005 XLR 5 m").

    Raises:
        ValidationError: No product with stock of its own has this article number, or it is customer material
            (MAT-076, PRD-043: what is bought is the company's).
    """
    text = (text or "").strip()
    if not text:
        return None
    products = stock_products().select_related("owner")
    product = products.filter(article_number__iexact=text).first()
    if product is None:
        product = products.filter(article_number__iexact=text.split()[0]).first()
    if product is None:
        raise ValidationError(
            _("There is no rental or sale product with the article number %(text)s.") % {"text": text}
        )
    if product.owner_id is not None:
        raise ValidationError(purchases.customer_product_error(product))
    return product


class PurchaseHeadForm(StyledForm):
    """What the whole purchase shares: supplier, invoice number and date, net or gross, start ID, the invoice.

    IMP-014: prices may be entered gross with the tax rate they include; they
    are stored net (only for who may see purchase prices, AUT-019).
    """

    supplier_name = forms.CharField(
        label=_("Bought from"),
        required=False,
        max_length=120,
        help_text=_("Choose from the suggestions or type a new name: the supplier is created with the items."),
    )
    invoice_number = forms.CharField(label=_("Invoice number"), max_length=60, required=False)
    purchase_date = forms.DateField(label=_("Invoice date"), required=False)
    prices = forms.ChoiceField(
        label=_("The prices are"), choices=[("net", _("net")), ("gross", _("gross"))], initial="net", required=False
    )
    price_tax_rate = forms.ChoiceField(
        label=_("Gross prices include"), required=False, help_text=_("Only for gross prices.")
    )
    inventory_number = forms.CharField(
        label=_("Start ID"),
        required=False,
        help_text=_(
            "Empty: the next free IDs. Otherwise the first item gets this ID, each further one – also of the "
            "following positions – the next free ID after it."
        ),
    )
    purchase_note = forms.CharField(
        label=_("Purchase note"), max_length=250, required=False, help_text=_("For all items of the purchase.")
    )
    invoice = forms.FileField(
        label=_("Invoice"),
        required=False,
        help_text=_("Attached to every new item. Only a PDF with text can be read; a scanned invoice cannot."),
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf,image/png,image/jpeg"}),
    )
    #: MAT-075: the totals of the read invoice, carried from step to step to compare the sum with.
    invoice_total_net = forms.RegexField(regex=_TOTAL, required=False, widget=forms.HiddenInput)
    invoice_total_gross = forms.RegexField(regex=_TOTAL, required=False, widget=forms.HiddenInput)

    def __init__(self, *args: Any, rights: Rights, remembered: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from rentalars.material.importer import default_tax_rate, tax_rate_choices

        self.with_prices = rights.has(SpecialRight.PURCHASE_PRICES)
        rates = tax_rate_choices()
        if not self.with_prices:
            # AUT-019: the totals of the invoice are purchase prices as well (MAT-075).
            del self.fields["invoice_total_net"]
            del self.fields["invoice_total_gross"]
        if not self.with_prices or not rates:
            # AUT-019: without the right no prices at all; without a tax rate only net prices.
            del self.fields["prices"]
            del self.fields["price_tax_rate"]
        else:
            remembered = remembered if isinstance(remembered, dict) else {}
            self.fields["price_tax_rate"].choices = rates
            if remembered.get("prices") in {"net", "gross"}:
                self.fields["prices"].initial = remembered["prices"]
            rate = remembered.get("price_tax_rate")
            self.fields["price_tax_rate"].initial = rate if rate in dict(rates) else (default_tax_rate() or rates[0][0])
        self.fields["inventory_number"].widget.attrs["inputmode"] = "numeric"
        self.fields["invoice_number"].widget.attrs["autocomplete"] = "off"

    def clean_inventory_number(self) -> int | None:
        """Parse a typed start ID and make sure it is free (MAT-050)."""
        text = self.cleaned_data.get("inventory_number", "").strip()
        if not text:
            return None
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        if MaterialItem.objects.filter(inventory_number=number).exists():
            raise forms.ValidationError(_("This ID is already taken."))
        return number

    def clean(self) -> dict[str, Any]:
        """A gross price needs one of the active tax rates (IMP-014).

        Review (MAT-075): a total of the invoice that is no amount (``1072.50``) – only a crafted request
        sends one – is ignored, not refused: nobody could see or fix the hidden field.
        """
        cleaned = super().clean() or {}
        for name in ("invoice_total_net", "invoice_total_gross"):
            if self._errors and self._errors.pop(name, None) is not None:
                cleaned[name] = ""
        cleaned["gross_rate"] = None
        if cleaned.get("prices") == "gross":
            try:
                cleaned["gross_rate"] = services.gross_tax_rate(cleaned.get("price_tax_rate"))
            except ValidationError as error:
                self.add_error("price_tax_rate", error.message_dict.get("price_tax_rate", error.messages))
        return cleaned

    def head(self) -> purchases.Head:
        """The head as :func:`rentalars.material.purchases.create_purchase` expects it."""
        data = self.cleaned_data
        return purchases.Head(
            supplier_name=data.get("supplier_name", ""),
            invoice_number=data.get("invoice_number", ""),
            invoice_date=data.get("purchase_date"),
            gross_rate=data.get("gross_rate"),
            start_number=data.get("inventory_number"),
            purchase_note=data.get("purchase_note", ""),
        )

    @property
    def price_entry(self) -> dict[str, str] | None:
        """The choice "net or gross", for the view to remember it as the other price forms do (MAT-059)."""
        cleaned = getattr(self, "cleaned_data", None)
        if "prices" not in self.fields or cleaned is None:
            return None
        return {"prices": cleaned.get("prices") or "net", "price_tax_rate": cleaned.get("price_tax_rate") or ""}


class PositionForm(StyledForm):
    """One position: a model – chosen, or typed as a new one with its category –, number, price, serial numbers.

    The model is typed with suggestions; the name of an existing model (in
    any case) chooses it, any other name makes a new model of that name with
    the category, manufacturer and product given in the row (MAT-048).
    """

    model_name = forms.CharField(label=_("Model"), max_length=200, required=False)
    category = forms.ChoiceField(label=_("Category"), required=False)
    manufacturer_name = forms.CharField(label=_("Manufacturer"), max_length=120, required=False)
    product_text = forms.CharField(
        label=_("Product"), max_length=250, required=False, help_text=_("Article number; empty: none yet.")
    )
    count = forms.IntegerField(
        label=_("Number of items"), min_value=1, max_value=services.MAX_ITEMS_PER_BATCH, initial=1, required=False
    )
    unit_price = AmountField(label=_("Price per piece"), min_value=0, max_digits=10, decimal_places=2, required=False)
    price_for_set = forms.BooleanField(
        label=_("Bought as a set"),
        required=False,
        help_text=_("The price is that of all pieces together; the first item gets it."),
    )
    serial_numbers = forms.CharField(
        label=_("Serial numbers"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("One per line, in the order of the IDs. An empty line: that item has none."),
    )
    storage_location = LocationChoiceField(
        label=_("Storage location"), queryset=StorageLocation.objects.filter(is_active=True), required=False
    )
    article_number = forms.CharField(label=_("Supplier's article number"), max_length=120, required=False)
    #: The position as the invoice said it, for the user to compare – it comes and goes with the form.
    source = forms.CharField(required=False, max_length=400, widget=forms.HiddenInput)
    #: Models that may be meant, one name per line (from the proposal).
    candidates = forms.CharField(required=False, max_length=1000, widget=forms.HiddenInput)
    #: MAT-076: why a category or product the AI proposed was not filled in, one per line.
    hint = forms.CharField(required=False, max_length=1000, widget=forms.HiddenInput)
    confirmed = forms.BooleanField(label=_("Checked"), required=False)

    def __init__(self, *args: Any, rights: Rights, shared: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        shared = shared if shared is not None else shared_choices()
        self.fields["category"].choices = shared["categories"]
        self.fields["storage_location"].choices = shared["locations"]
        if shared["default_location"] is not None:
            self.fields["storage_location"].initial = shared["default_location"]  # MAT-052
        if not rights.has(SpecialRight.PURCHASE_PRICES):
            # AUT-019: without the right the price is not part of the form – nor the set, which is about prices.
            del self.fields["unit_price"]
            del self.fields["price_for_set"]
        self.fields["count"].widget.attrs["inputmode"] = "numeric"
        for name in ("model_name", "manufacturer_name", "product_text", "article_number"):
            self.fields[name].widget.attrs["autocomplete"] = "off"
        # UIX-051 (UIX-035): what ``clean`` asks for – the model always; the category in the part
        # "New model", which only a new model needs; "checked" for a row from the invoice, the only one that shows it.
        for name in ("model_name", "category", "confirmed"):
            mark_required(self.fields[name])

    # --- What the template shows ---------------------------------------------------------------------

    @property
    def model_value(self) -> str:
        """The model name as it stands in the row."""
        return str(self["model_name"].value() or "").strip()

    @property
    def is_new_model(self) -> bool:
        """Whether the typed name is no existing model – the row then needs category and so on."""
        name = self.model_value
        return bool(name) and not MaterialModel.objects.filter(name__iexact=name).exists()

    @property
    def candidate_names(self) -> list[str]:
        """The models that may be meant, from the proposal."""
        return [name for name in str(self["candidates"].value() or "").splitlines() if name.strip()][:5]

    @property
    def from_invoice(self) -> str:
        """The position as the invoice said it; empty for a row typed by hand."""
        return str(self["source"].value() or "")

    @property
    def hints(self) -> list[str]:
        """What the user should know about the row from the invoice (MAT-076): a proposal that was not filled in."""
        return [line for line in str(self["hint"].value() or "").splitlines() if line.strip()][:5]

    @property
    def serial_count(self) -> int:
        """How many serial number fields the page script shows at first (MAT-050)."""
        try:
            return max(1, min(services.MAX_ITEMS_PER_BATCH, int(self["count"].value() or 1)))
        except (TypeError, ValueError):
            return 1

    # --- Checking ----------------------------------------------------------------------------------

    def clean(self) -> dict[str, Any]:
        """Resolve the model (or check the new one), the product and the serial numbers; rows from an invoice need "checked"."""
        cleaned = super().clean() or {}
        name = (cleaned.get("model_name") or "").strip()
        model = MaterialModel.objects.filter(name__iexact=name).first() if name else None
        cleaned["model"] = model
        cleaned["category_object"] = None
        cleaned["product"] = None
        if not name:
            self.add_error("model_name", _("Which model? Choose one, or type the name of a new one."))
        elif model is None:
            category_id = str(cleaned.get("category") or "")
            category = (
                Category.objects.filter(pk=int(category_id), is_active=True).first() if category_id.isdigit() else None
            )
            if category is None:
                self.add_error("category", _("“%(name)s” is a new model: choose its category.") % {"name": name})
            cleaned["category_object"] = category
            try:
                cleaned["product"] = product_named(cleaned.get("product_text", ""))
            except ValidationError as error:
                self.add_error("product_text", error)
        count = cleaned.get("count") or 1
        cleaned["count"] = count
        per_item = 1 if model is not None and model.is_bulk else count
        try:
            cleaned["serial_list"] = services.check_serial_numbers(
                (cleaned.get("serial_numbers") or "").splitlines(), per_item
            )
        except ValidationError as error:
            self.add_error("serial_numbers", error.message_dict["serial_numbers"])
        if cleaned.get("source") and not cleaned.get("confirmed"):
            self.add_error("confirmed", _("This row comes from the invoice: check it, then tick “checked”."))
        return cleaned

    def position(self) -> purchases.Position:
        """The row as :func:`rentalars.material.purchases.create_purchase` expects it."""
        data = self.cleaned_data
        new_model = None
        if data.get("model") is None:
            new_model = purchases.NewModel(
                name=data["model_name"].strip(),
                category=data["category_object"],
                manufacturer=data.get("manufacturer_name", ""),
                product=data.get("product"),
            )
        return purchases.Position(
            model=data.get("model"),
            new_model=new_model,
            count=data["count"],
            unit_price=data.get("unit_price"),
            price_for_set=bool(data.get("price_for_set")),
            serial_numbers=data.get("serial_list") or [],
            storage_location=data.get("storage_location"),
            supplier_article_number=data.get("article_number", ""),
        )


class BasePositionFormSet(forms.BaseFormSet):
    """The positions: at least one, at most :data:`purchases.MAX_POSITIONS`; untouched rows are ignored.

    A page shown again (more rows, a proposal filled in) carries its rows as
    ``initial`` of extra forms – the management form always says "no initial
    forms" – so that an untouched row stays an empty one.
    """

    def initial_form_count(self) -> int:
        """Every row is an extra row: an empty one may stay empty."""
        return super().initial_form_count() if self.is_bound else 0

    def add_fields(self, form: forms.Form, index: int | None) -> None:
        """The box that removes a row says so."""
        super().add_fields(form, index)
        if "DELETE" in form.fields:
            form.fields["DELETE"].label = _("Remove the row")

    def clean(self) -> None:
        """At least one position, and not more items than one step may create (MAT-006)."""
        super().clean()
        if any(self.errors):
            return
        rows = self.filled_forms()
        if not rows:
            raise ValidationError(_("Enter at least one position."))
        if len(rows) > purchases.MAX_POSITIONS:
            raise ValidationError(_("At most %(count)d positions per purchase.") % {"count": purchases.MAX_POSITIONS})

    def filled_forms(self) -> list[PositionForm]:
        """The rows that hold a position: touched and not removed."""
        return [
            form
            for form in self.forms
            if form.has_changed() and not (self.can_delete and self._should_delete_form(form))
        ]

    def positions(self) -> list[purchases.Position]:
        """The positions in the order of the page."""
        return [form.position() for form in self.filled_forms()]


PositionFormSet = forms.formset_factory(
    PositionForm,
    formset=BasePositionFormSet,
    extra=0,
    can_delete=True,
    max_num=purchases.MAX_POSITIONS,
    validate_max=True,
    absolute_max=purchases.MAX_POSITIONS + SPARE_ROWS,
)


def position_formset(
    data: Any = None, *, rights: Rights, rows: list[dict[str, Any]] | None = None
) -> BasePositionFormSet:
    """The positions: bound to a sent form, or – shown anew – with ``rows`` as the values of their fields."""
    kwargs = {"rights": rights, "shared": shared_choices()}
    if data is not None:
        return PositionFormSet(data, prefix=PREFIX, form_kwargs=kwargs)
    rows = rows if rows is not None else [{} for _row in range(EMPTY_ROWS)]
    factory = forms.formset_factory(
        PositionForm,
        formset=BasePositionFormSet,
        extra=len(rows),
        can_delete=True,
        max_num=purchases.MAX_POSITIONS + SPARE_ROWS,
        absolute_max=purchases.MAX_POSITIONS + SPARE_ROWS,
    )
    return factory(initial=rows, prefix=PREFIX, form_kwargs=kwargs)


def shared_choices() -> dict[str, Any]:
    """What every row offers alike – categories, storage locations, the default location – read once per page."""
    from rentalars.masterdata.models import remember_location_paths

    default = StorageLocation.get_default()
    locations = remember_location_paths(StorageLocation.objects.filter(is_active=True))
    return {
        "categories": Category.objects.choices(empty_label="–"),
        "locations": [("", _("– please choose –")), *[(location.pk, location.path) for location in locations]],
        "default_location": default.pk if default is not None else None,
    }


#: The fields of a row that are carried over when the page is shown again.
ROW_FIELDS = (
    "model_name",
    "category",
    "manufacturer_name",
    "product_text",
    "count",
    "unit_price",
    "price_for_set",
    "serial_numbers",
    "storage_location",
    "article_number",
    "source",
    "candidates",
    "hint",
    "confirmed",
)


def rows_of(formset: BasePositionFormSet) -> list[dict[str, Any]]:
    """The values of the sent rows, without checking them – removed rows left out (more rows, a proposal)."""
    rows = []
    for form in formset.forms:
        if formset.can_delete and form["DELETE"].value():
            continue
        rows.append({name: form[name].value() for name in ROW_FIELDS if name in form.fields})
    return rows


def is_empty_row(row: dict[str, Any]) -> bool:
    """Whether a row holds nothing a person typed."""
    return not any(
        str(row.get(name) or "").strip()
        for name in (
            "model_name",
            "manufacturer_name",
            "product_text",
            "unit_price",
            "serial_numbers",
            "article_number",
            "source",
        )
    )


def rows_from_proposal(proposal: dict[str, Any], *, rights: Rights) -> list[dict[str, Any]]:
    """The positions of a proposal as rows of the form – each to be checked (``source``)."""
    from rentalars.core.money import format_money

    with_prices = rights.has(SpecialRight.PURCHASE_PRICES)
    default_location = StorageLocation.get_default()
    rows = []
    for position in proposal.get("positions") or []:
        quantity = int(position.get("quantity") or 1)
        price = position.get("unit_price") or ""
        described = str(position.get("description") or "")
        if price and with_prices:
            # MAT-076: with thousands separators, as the invoice writes it ("1.072,50"), to compare at a glance.
            described = f"{described} · {quantity} × {format_money(Decimal(price), currency='').strip()}"
        elif quantity != 1:
            described = f"{described} · {quantity} ×"
        row: dict[str, Any] = {
            "model_name": position.get("model") or "",
            "manufacturer_name": position.get("manufacturer") or "",
            "count": quantity,
            "article_number": position.get("article_number") or "",
            "source": described[:400],
            "candidates": "\n".join(candidate["name"] for candidate in position.get("candidates") or [])[:1000],
            "confirmed": False,
            # MAT-076: serial numbers, category and product as the proposal has them.
            "serial_numbers": "\n".join(str(serial) for serial in position.get("serial_numbers") or []),
            "category": str(position["category_id"]) if position.get("category_id") else "",
            "product_text": position.get("product") or "",
            "hint": "\n".join(str(hint) for hint in position.get("hints") or [])[:1000],
        }
        if with_prices and price:
            row["unit_price"] = Decimal(price)  # shown in the user's format ("99,00"), as typed prices are
        if default_location is not None:
            row["storage_location"] = default_location.pk
        rows.append(row)
    return rows


# --- The sum of the positions (MAT-075) --------------------------------------------------------------------


@dataclass
class PurchaseSums:
    """The sum of the positions as typed, net and gross, next to the totals of the invoice (MAT-075).

    The requirement: below "Kauf einpflegen", the sum (net and gross) of the positions entered, for cross-checking. The page script computes the same while the user types (``static/js/app.js``).
    """

    #: The sum of the positions as Rentalars stores them, net.
    net: Decimal
    #: The sum gross; ``None`` without a tax rate to compute it with.
    gross: Decimal | None
    #: Whether the prices are typed gross (MAT-059) – then the gross sum is exact and the net one computed.
    gross_entered: bool
    #: The tax rate gross and net are converted with: that of the purchase (IMP-014).
    rate: Decimal | None
    #: Positions on the page (rows nobody typed in left out) and those without a price (counted as 0).
    positions: int
    unpriced: int
    #: The totals of the invoice, if reading it found them.
    invoice_net: Decimal | None = None
    invoice_gross: Decimal | None = None

    @property
    def compared(self) -> str:
        """Which sum is compared with the invoice: ``"gross"``, ``"net"`` or ``""`` if none can be."""
        if self.invoice_gross is not None and self.gross is not None:
            return "gross"
        if self.invoice_net is not None:
            return "net"
        return ""

    @property
    def difference(self) -> Decimal | None:
        """The sum of the positions minus the total of the invoice – gross where both are known, else net."""
        if self.compared == "gross":
            return self.gross - self.invoice_gross  # type: ignore[operator]
        if self.compared == "net":
            return self.net - self.invoice_net  # type: ignore[operator]
        return None

    @property
    def max_pieces(self) -> int:
        """The most pieces of one row, as the form takes them – for the page script."""
        return services.MAX_ITEMS_PER_BATCH

    @property
    def has_invoice(self) -> bool:
        """Whether a total of the invoice is known."""
        return self.invoice_net is not None or self.invoice_gross is not None

    @property
    def unpriced_text(self) -> str:
        """The text "2 positions without price – they count as 0", for the page."""
        return self.unpriced_texts()[0 if self.unpriced == 1 else 1].replace("{count}", str(self.unpriced))

    @staticmethod
    def unpriced_texts() -> tuple[str, str]:
        """The text for one and for several positions without price, ``{count}`` for the number – the script's too."""
        return tuple(  # type: ignore[return-value]
            ngettext(
                "%(count)s position without price – it counts as 0.",
                "%(count)s positions without price – they count as 0.",
                number,
            )
            % {"count": "{count}"}
            for number in (1, 2)
        )


def _row_count(value: Any) -> int:
    """The number of pieces of a row as typed; empty or not a number: 1, as the form takes it."""
    try:
        return max(1, min(services.MAX_ITEMS_PER_BATCH, int(str(value).strip())))
    except (TypeError, ValueError):
        return 1


def _row_price(value: Any) -> Decimal | None:
    """The price of a row as typed ("1.072,50") or proposed; ``None`` if there is none the form would take."""
    price = purchases.parse_amount(value, decimal_comma=decimal_separator() == ",")
    if price is None or price < 0 or price >= Decimal("100000000") or price != money(price):
        return None  # not a price the form takes: negative, too large, more than two decimal places
    return price


def _total(head: PurchaseHeadForm, name: str) -> Decimal | None:
    """A total of the invoice as the page carries it (``1072.50``); ``None`` if there is none.

    Review (MAT-075): read through the field itself, as the cleaned form reads it – only an amount of
    the pattern :data:`_TOTAL` counts; anything else a crafted request sends ("NaN", "Infinity", "1e999999")
    is ignored instead of breaking the page.
    """
    if name not in head.fields:
        return None  # AUT-019: without the right to see purchase prices
    try:
        text = head.fields[name].clean(head[name].value())
    except ValidationError:
        return None
    return Decimal(text) if text else None


def purchase_sums(head: PurchaseHeadForm, formset: BasePositionFormSet) -> PurchaseSums | None:
    """The sum of the positions on the page – as typed, not yet checked – and the totals of the invoice.

    ``None`` without the right to see purchase prices (AUT-019). Each row counts its price times its number of
    pieces, a price for a set once (MAT-054); a row without price counts 0. Prices typed gross (MAT-059): the gross
    sum adds them, the net sum adds what Rentalars stores – each price net, rounded to cents (IMP-014). Prices
    typed net: the gross sum is the net sum with the tax rate of the purchase, rounded once, as an invoice does.
    """
    if not head.with_prices:
        return None
    from rentalars.material.importer import default_tax_rate, gross_factor, tax_rate_choices

    gross_entered = "prices" in head.fields and head["prices"].value() == "gross"
    rate = None
    if "price_tax_rate" in head.fields:
        chosen = str(head["price_tax_rate"].value() or "")
        rate_text = chosen if chosen in dict(tax_rate_choices()) else default_tax_rate()
        rate = Decimal(rate_text) if rate_text else None
    net = gross = Decimal("0.00")
    positions = unpriced = 0
    for row in rows_of(formset):
        if is_empty_row(row):
            continue
        positions += 1
        price = _row_price(row.get("unit_price"))
        if price is None:
            unpriced += 1
            continue
        pieces = 1 if row.get("price_for_set") in (True, "on", "true", "True", "1") else _row_count(row.get("count"))
        if gross_entered and rate is not None:
            gross += price * pieces
            net += services.net_from_gross(price, rate) * pieces
        else:
            net += price * pieces
    if not gross_entered:
        gross = money(net * gross_factor(rate)) if rate is not None else None
    return PurchaseSums(
        net=money(net),
        gross=money(gross) if gross is not None else None,
        gross_entered=gross_entered,
        rate=rate,
        positions=positions,
        unpriced=unpriced,
        invoice_net=_total(head, "invoice_total_net"),
        invoice_gross=_total(head, "invoice_total_gross"),
    )
