# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the projects module."""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from rentalars.accounts.models import User
from rentalars.accounts.rights import Module, Rights, SpecialRight
from rentalars.core.forms import DATETIME_FORMAT, RowLayoutMixin, StyledForm, StyledModelForm, mark_required
from rentalars.core.i18n import local_pattern
from rentalars.core.models import SystemSettings
from rentalars.core.money import format_decimal
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress, Venue
from rentalars.masterdata.models import DocumentType, TaxRate, Unit
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.material.numbering import parse_inventory_number
from rentalars.personnel.models import JobFunction, Person, PersonJobFunction
from rentalars.products.models import BillingMode
from rentalars.projects.discounts import maximum_of_material_line
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.lines import alternative_choices, group_alternative_choices
from rentalars.projects.models import (
    INHERITED_FIELDS,
    CrewBilling,
    CrewLine,
    Group,
    GroupKind,
    LineVariant,
    MaterialLine,
    Project,
    ProjectAccessLevel,
    ProjectFile,
    ProjectPhase,
    ProjectTemplate,
    RequestStatus,
    SupplierDocumentKind,
    SurchargeTargetType,
)
from rentalars.projects.subrental_forms import check_subrental_status, subrental_status_field, supplier_field


class _TreeOrderIterator(forms.models.ModelChoiceIterator):
    """Offers groups in the order of the planning: a group, its subgroups, the next group (PRJ-037)."""

    def __iter__(self) -> Any:
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        for group in GroupTree(self.queryset).ordered:
            yield self.choice(group)


class GroupChoiceField(forms.ModelChoiceField):
    """Choose a group of a project; subgroups are named with their path: "Licht › Front-Traverse" (PRJ-037)."""

    iterator = _TreeOrderIterator

    def label_from_instance(self, obj: Group) -> str:  # type: ignore[override]
        """The path of the group; its parents are cached by the tree, so it costs no query."""
        return obj.path


class TakeoverChoiceField(forms.ModelChoiceField):
    """Choose the line of another subproject to take over from: "2026-0042-1 Bühne 1: 6 × Spot (until 12.6.)"."""

    def label_from_instance(self, obj: MaterialLine) -> str:  # type: ignore[override]
        """Part, quantity, title and when the pieces are free there."""
        until = timezone.localtime(obj.end).strftime(local_pattern("%d.%m. %H:%M"))
        return _("%(number)s %(name)s: %(quantity)s × %(title)s (back there %(until)s)") % {
            "number": obj.project.number,
            "name": obj.project.name,
            "quantity": obj.quantity_display,
            "title": obj.title,
            "until": until,
        }


def default_period() -> tuple[datetime.datetime, datetime.datetime]:
    """Suggest a period for a new project: tomorrow, at the usual start and end times."""
    system_settings = SystemSettings.load()
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    zone = timezone.get_current_timezone()
    start = datetime.datetime.combine(tomorrow, system_settings.default_start_time, tzinfo=zone)
    end = datetime.datetime.combine(tomorrow, system_settings.default_end_time, tzinfo=zone)
    if end <= start:
        end += datetime.timedelta(days=1)
    return start, end


class ContactSelect(forms.Select):
    """The contact field of the project form: the contacts of the customer and, last, "Neuer Ansprechpartner …" (PRJ-140).

    The last choice is no value: choosing it opens a dialog that creates the contact (``data-create-url``, see
    ``static/js/app.js``), and the field goes back to what it showed. A value sent all the same is ignored by the form.
    """

    NEW = "__new__"

    def __init__(self, *args: Any, create_url: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.create_url = create_url

    def optgroups(self, name: str, value: Any, attrs: dict[str, Any] | None = None) -> Any:
        """The contacts and, last, the choice that creates a new one."""
        groups = super().optgroups(name, value, attrs)
        if self.create_url:
            index = sum(len(options) for _group, options, _i in groups)
            option = self.create_option(name, self.NEW, _("+ New contact person …"), False, index)
            option["attrs"]["data-create-url"] = self.create_url  # a <select> does not hand its attributes to options
            groups.append((None, [option], index))
        return groups


def offer_new_contact(form: forms.BaseForm, rights: Any, customer_id: Any) -> None:
    """The last choice "New contact person" of the field "contact" (PRJ-140; also in the service case form).

    Whoever may change the customers can create the contact right here: the choice opens a dialog.

    Sets ``form.new_contact_sent`` when the choice came with the form all the same (the dialog did not open, e.g.
    without script); the field is emptied then and the form reports it in ``clean``. An anonymised customer gets no new
    contacts.
    """
    form.new_contact_sent = False  # type: ignore[attr-defined]
    chosen = Customer.objects.filter(pk=customer_id).first() if str(customer_id or "").isdigit() else None
    if rights is not None and rights.can_write(Module.CUSTOMERS) and chosen is not None and not chosen.is_anonymised:
        attrs = dict(form.fields["contact"].widget.attrs)
        create_url = reverse("customers:contact_quick_create", args=[int(customer_id)])
        form.fields["contact"].widget = ContactSelect(attrs=attrs, create_url=f"{create_url}?field=contact")
    if form.is_bound and form.data.get("contact") == ContactSelect.NEW:
        form.new_contact_sent = True  # type: ignore[attr-defined]
        form.data = form.data.copy()
        form.data["contact"] = ""


class ProjectForm(StyledModelForm):
    """Master data and periods of a project (PRJ-003 to PRJ-005)."""

    class Meta:
        model = Project
        fields = [
            "name",
            "is_internal",
            "customer",
            "contact",
            "billing_address",
            "delivery_address",
            "venue_site",
            "venue",
            "manager",
            "start",
            "end",
            "event_start",
            "event_end",
            "rental_days",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, parent: Project | None = None, rights: Rights | None = None, **kwargs: Any) -> None:
        #: PRJ-044: the whole project of a subproject – given when one is added, or the instance's.
        instance = kwargs.get("instance")
        self.parent = parent or (instance.parent if instance is not None and instance.parent_id else None)
        if self.parent is not None:
            # PRJ-045: customer and billing are those of the whole project; contacts and addresses are its.
            kwargs.setdefault("initial", {})["customer"] = self.parent.customer_id
        super().__init__(*args, **kwargs)
        # PRJ-070: customer and venue are typed with suggestions (and can be created there); the
        # field itself carries the key in a hidden input of the type-ahead (core/_typeahead_field.html).
        self.fields["customer"].widget = forms.HiddenInput()
        self.fields["venue_site"].widget = forms.HiddenInput()
        # PRJ-076: a new project can start from a template.
        if self.instance.pk is None and ProjectTemplate.objects.exists():
            self.fields["template"] = forms.ModelChoiceField(
                label=_("Template"),
                queryset=ProjectTemplate.objects.all(),
                required=False,
                empty_label=_("– without template –"),
                help_text=_("Groups, lines, crew places and schedule of the template are added after saving."),
            )
        customers = Customer.objects.filter(is_active=True)
        if self.instance.pk:
            # Keep the current customer selectable even if it was deactivated since.
            customers = customers | Customer.objects.filter(pk=self.instance.customer_id)
        self.fields["customer"].queryset = customers.order_by("name")
        self.fields["manager"].queryset = User.objects.filter(is_active=True)
        customer_id = self.data.get("customer") or self.initial.get("customer") or self.instance.customer_id
        if hasattr(customer_id, "pk"):
            customer_id = customer_id.pk
        if self.parent is not None:
            customer_id = self.parent.customer_id
        offer_new_contact(self, rights, customer_id)
        self.fields["contact"].queryset = (
            Contact.objects.filter(customer_id=customer_id) if customer_id else Contact.objects.none()
        )
        self.fields["contact"].help_text = _(
            "Contacts of the chosen customer. Save once to see those of a different customer."
        )
        # KND-005: the further addresses of the customer; a new project takes the defaults.
        #: The customer whose addresses the page offers; sent back as "addresses_for".
        self.addresses_for = customer_id or ""
        if self.is_bound and str(self.data.get("addresses_for", "")) != str(customer_id or ""):
            # The page offered the addresses of another customer (or none, before a customer was chosen):
            # the chosen customer's defaults take their place.
            self.data = self.data.copy()
            chosen = (
                Customer.objects.filter(pk=customer_id).first()
                if str(customer_id).isascii() and str(customer_id).isdigit()
                else None
            )
            for name, kind in (("billing_address", AddressKind.BILLING), ("delivery_address", AddressKind.DELIVERY)):
                default = chosen.default_address(kind) if chosen is not None else None
                self.data[name] = str(default.pk) if default is not None else ""
        for name, kind in (("billing_address", AddressKind.BILLING), ("delivery_address", AddressKind.DELIVERY)):
            addresses = (
                CustomerAddress.objects.filter(customer_id=customer_id, kind=kind)
                if customer_id
                else CustomerAddress.objects.none()
            )
            self.fields[name].queryset = addresses
            if not addresses:
                self.fields[name].widget = forms.HiddenInput()
            elif not self.instance.pk and name not in self.initial:
                default = next((address for address in addresses if address.is_default), None)
                if default is not None:
                    self.initial[name] = default.pk
        # KND-009: venues of the master data; the free text stays for anything else.
        venues = Venue.objects.filter(is_active=True)
        if self.instance.venue_site_id:
            venues = venues | Venue.objects.filter(pk=self.instance.venue_site_id)
        self.fields["venue_site"].queryset = venues.order_by("name")
        self.fields["venue_site"].label = _("Venue")
        self.fields["venue"].label = _("Place, free text")
        self.fields["venue"].help_text = _("For a place that is not among the venues, or to add “hall 3”.")
        for name in ("start", "end"):
            self.fields[name].help_text = ""
        if self.parent is not None:
            for name in INHERITED_FIELDS:
                del self.fields[name]
                # The model checks a part against its whole project (PRJ-044, PRJ-045) while the form validates.
                setattr(self.instance, name, getattr(self.parent, name))
            self.instance.parent = self.parent
        if "customer" in self.fields:
            # UIX-035: the customer is needed unless the project is internal; the model checks it (PRJ-001).
            mark_required(self.fields["customer"], "is_internal=")

    def clean(self) -> dict[str, Any]:
        """The choice "New contact person" is no contact: the dialog did not open, so nothing was created."""
        data = super().clean()
        if self.new_contact_sent:
            self.add_error(
                "contact",
                _("The dialog for a new contact person did not open. Choose a contact or create one at the customer."),
            )
        return data

    @property
    def event_warning(self) -> str:
        """PRJ-005 (event end; PRJ-127): the warning if the event ends after the material is back, else ``""``.

        From the values typed when the form is bound and valid, else from the project – the page script
        (``[data-event-warning]``) keeps it up to date while the fields are changed.
        """
        from rentalars.projects.period_warnings import event_after_material_back, event_warning_text

        if self.is_bound:
            end = getattr(self, "cleaned_data", {}).get("end")
            event_end = getattr(self, "cleaned_data", {}).get("event_end")
        else:
            end = self.initial.get("end", self.instance.end if self.instance.pk else None)
            event_end = self.initial.get("event_end", self.instance.event_end)
        return event_warning_text() if event_after_material_back(end, event_end) else ""

    @property
    def is_subproject(self) -> bool:
        """Whether the form is about a part of a whole project (PRJ-044)."""
        return self.parent is not None

    def _chosen(self, name: str, model: Any) -> Any:
        """The object the field holds now – bound value, initial value or the instance's."""
        value = (
            self.data.get(name) if self.is_bound else self.initial.get(name, getattr(self.instance, f"{name}_id", None))
        )
        if hasattr(value, "pk"):
            return value
        return (
            model.objects.filter(pk=value).first()
            if str(value or "").isascii() and str(value or "").isdigit()
            else None
        )

    @property
    def customer_text(self) -> str:
        """What the customer field shows: the name of the chosen customer."""
        customer = self._chosen("customer", Customer)
        return customer.name if customer is not None else ""

    @property
    def venue_text(self) -> str:
        """What the venue field shows: the name of the chosen venue."""
        venue = self._chosen("venue_site", Venue)
        return venue.name if venue is not None else ""


class OverallDiscountForm(StyledForm):
    """The discount on the whole project: percent, amount – or a target amount, net or gross (PRJ-123).

    (discount target.) With a target amount the user types the total the project should come to, after the
    discount; the percentage is calculated and stored (``rentalars.projects.overall_target``). Exactly one of the four
    fields counts: the one that was typed; a field that still shows what the project has is ignored when another one
    was typed.
    """

    VALUE_FIELDS = ("percent", "amount", "target_net", "target_gross")

    percent = forms.DecimalField(
        label=_("Overall discount in percent"), min_value=0, max_value=100, decimal_places=6, required=False
    )
    amount = forms.DecimalField(
        label=_("Overall discount as amount"), min_value=0, max_digits=10, decimal_places=2, required=False
    )
    target_net = forms.DecimalField(
        label=_("Target amount net"), min_value=0, max_digits=12, decimal_places=2, required=False
    )
    target_gross = forms.DecimalField(
        label=_("Target amount gross"), min_value=0, max_digits=12, decimal_places=2, required=False
    )

    def __init__(self, *args: Any, project: Project, **kwargs: Any) -> None:
        self.project = project
        percent = project.overall_discount_percent
        if percent is not None:
            # Without the zeros of the six places the column holds: "12,5", not "12,500000" (and still a number, so
            # that the form can tell whether it was changed).
            percent = percent.normalize()
            percent = percent.quantize(Decimal(1)) if percent.as_tuple().exponent > 0 else percent
        kwargs.setdefault("initial", {"percent": percent, "amount": project.overall_discount_amount})
        super().__init__(*args, **kwargs)
        self.fields["percent"].help_text = _(
            "Taken off the net total of the project, after surcharges. Use one of the four fields; "
            "empty fields remove the discount."
        )
        self.fields["target_net"].help_text = _(
            "The net total the project should come to after the discount. The percentage is calculated and stored."
        )
        self.fields["target_gross"].help_text = _(
            "The gross total (with tax) the project should come to after the discount. The percentage is calculated "
            "and stored."
        )

    def _typed(self) -> list[str]:
        """The fields that were changed and hold a value – a typed ``0`` counts, an emptied field does not."""
        return [
            name for name in self.VALUE_FIELDS if name in self.changed_data and self.cleaned_data.get(name) is not None
        ]

    def chosen(self) -> str | None:
        """Which field counts: the typed one; ``None`` if the discount is removed.

        A field that is unchanged is ignored as soon as another one was typed. Without any change the project's
        discount stays (the form was saved as it opened); an emptied field removes it.
        """
        typed = self._typed()
        if typed:
            return typed[0]
        return next((name for name in ("percent", "amount") if self.cleaned_data.get(name)), None)

    def clean(self) -> dict[str, Any]:
        """Only one of the four."""
        data = super().clean()
        typed = self._typed()
        if len(typed) > 1:
            if typed == ["percent", "amount"]:
                self.add_error("amount", _("Use only one of: overall discount in percent, as an amount."))
            else:
                self.add_error(
                    typed[1], _("Use only one of: percentage, amount, target amount net, target amount gross.")
                )
        return data

    def figures(self) -> Any:
        """What the typed value leads to, for the live preview – ``None`` if nothing usable is typed.

        Returns:
            ``(percent text, DiscountFigures)`` of the typed value, or an error text as ``str``.
        """
        from rentalars.projects.overall_target import preview_of

        return preview_of(self.project, self.cleaned_data, self.chosen())


class GroupForm(StyledModelForm):
    """Name, place, description and price adjustment of a group (PRJ-014, PRJ-037, PRJ-039, PRJ-040)."""

    #: PRJ-037: the way to move a group without dragging it.
    parent = GroupChoiceField(
        label=_("Parent group"),
        queryset=Group.objects.none(),
        required=False,
        empty_label=_("– none: top level –"),
        help_text=_("The group moves into this one, with its lines and subgroups, as its last subgroup."),
    )

    class Meta:
        model = Group
        fields = [
            "name",
            "parent",
            "kind",
            "alternative_to",
            "rental_days",
            "discount_percent",
            "discount_amount",
            "flat_price",
            "description",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, rights: Rights, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not rights.has(SpecialRight.PRICES):
            for name in ("discount_percent", "discount_amount", "flat_price"):
                del self.fields[name]
        group = self.instance
        # Only places that keep the rules of PRJ-037: not inside itself, not deeper than three levels.
        tree = GroupTree(Group.objects.filter(project_id=group.project_id))
        allowed = tree.possible_parents(tree.by_id.get(group.pk))
        self.fields["parent"].queryset = Group.objects.filter(pk__in=[other.pk for other in allowed])
        self.fields["kind"].help_text = _("A subgroup of an optional or alternative group counts as such as well.")
        # PRJ-083: the group an alternative could replace – not itself, not above or below it.
        offered = [pk for pk, _label in group_alternative_choices(group)] if group.pk else []
        self.fields["alternative_to"] = GroupChoiceField(
            label=_("Alternative to"),
            queryset=Group.objects.filter(pk__in=offered),
            required=False,
            empty_label=_("– only for an alternative –"),
            help_text=_("Which group an alternative group could replace."),
        )
        # UIX-051 (UIX-035): required while the group is an alternative (``clean``).
        mark_required(self.fields["alternative_to"], f"{self.add_prefix('kind')}={GroupKind.ALTERNATIVE}")

    def clean(self) -> dict[str, Any]:
        """PRJ-083: an alternative names the group it could replace."""
        cleaned = super().clean() or {}
        if cleaned.get("kind") == GroupKind.ALTERNATIVE and not cleaned.get("alternative_to"):
            self.add_error("alternative_to", _("Choose the group this one could replace."))
        elif cleaned.get("kind") != GroupKind.ALTERNATIVE:
            cleaned["alternative_to"] = None
        return cleaned


class LineForm(RowLayoutMixin, StyledForm):
    """Edit a material line. Which fields appear depends on the kind of line and on the rights.

    The form does not save by itself. ``changes()`` returns the values that
    differ from the line, and the view passes them to
    ``projects.services.update_line`` – the same function the API uses.
    """

    title = forms.CharField(label=_("Title"), max_length=200)
    quantity = forms.DecimalField(label=_("Quantity"), min_value=0, decimal_places=2)
    group = GroupChoiceField(
        label=_("Group"), queryset=Group.objects.none(), required=False, empty_label=_("– without group –")
    )
    start = forms.DateTimeField(label=_("From"))
    end = forms.DateTimeField(label=_("Until"))
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Appears on the packing list."),
    )
    #: PRJ-075: an optional or alternative line is priced, but not added up, not invoiced and not packed.
    variant = forms.ChoiceField(
        label=_("Counts as"),
        choices=LineVariant.choices,
        required=False,
        help_text=_(
            "Optional and alternative lines show their price, but are not part of the total, the invoice "
            "or the packing list. Their material is only reserved like an option."
        ),
    )

    #: Fields that belong together stand side by side (UIX-014): above all
    #: "from" and "until".
    LAYOUT = (
        ("title",),
        ("quantity", "group"),
        ("variant", "alternative_to"),
        ("taken_over_from",),
        ("start", "end"),
        ("rental_days", "manual_scale_factor"),
        ("unit_price", "discount_percent"),
        ("hours", "quantity_is_estimate"),
        ("is_sale",),
        ("tax_rate", "unit"),
        ("supplier", "subrental_status"),
        ("purchase_price", "picked_up_at_supplier"),
        ("surcharge_percent",),
        ("targets",),
        ("preferred_model", "preferred_item_number"),
        ("further_item_numbers",),
        ("note",),
    )

    #: Form fields whose value goes into a line field of another name.
    FIELD_TARGETS = {"preferred_item_number": "preferred_item"}

    def __init__(self, *args: Any, line: MaterialLine, rights: Rights, **kwargs: Any) -> None:
        self.line = line
        self.rights = rights
        kwargs.setdefault("initial", {}).update(self._initial_from_line())
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = line.project.groups.all()
        product = line.product
        can_price = rights.has(SpecialRight.PRICES)

        if line.is_text:
            # A text line has the text, a longer text and the group – nothing else.
            for name in list(self.fields):
                if name not in {"title", "note", "group"}:
                    del self.fields[name]
            self.fields["title"].label = _("Text")
            self.fields["note"].label = _("Further text")
            self.fields["note"].help_text = _("Optional; printed below the text.")
            self.fields["note"].widget.attrs["rows"] = 3
            self.style_fields()
            self.without_browser_history()
            return
        if line.is_percent_surcharge:
            # A percentage surcharge has no quantity or period of its own.
            for name in ("quantity", "start", "end", "group"):
                del self.fields[name]
            self._add_surcharge_fields(can_price)
        else:
            # PRD-047: a product has one price, so the switch is offered only where the line
            # can take the other – a line that sold a rental product before is rented again by unticking it.
            other_price = None if product is None else (product.price if line.is_sale else product.sale_price)
            if other_price is not None:
                self.fields["is_sale"] = forms.BooleanField(
                    label=_("Sell instead of renting"),
                    required=False,
                    help_text=_(
                        "Untick to rent the pieces at the price of the product. Selling it again needs a sale product."
                    )
                    if line.is_sale
                    else _("A sale takes the pieces out of the stock for good."),
                )
            if line.billing_mode == BillingMode.HOURLY and not line.is_sale:
                self.fields["hours"] = forms.DecimalField(
                    label=_("Hours"), min_value=0, decimal_places=2, required=False
                )
            if line.billing_mode == BillingMode.EFFORT and not line.is_sale:
                self.fields["quantity_is_estimate"] = forms.BooleanField(
                    label=_("Quantity is an estimate"),
                    required=False,
                    help_text=_("Untick once the actual effort is entered."),
                )
            if line.uses_rental_days:
                self.fields["rental_days"] = forms.IntegerField(
                    label=_("Rental days"),
                    min_value=1,
                    max_value=999,
                    required=False,
                    help_text=_("Empty: the days follow the period."),
                )
            if can_price:
                self.fields["unit_price"] = forms.DecimalField(
                    label=_("Unit price (net)"), min_value=0, decimal_places=2
                )
                maximum = maximum_of_material_line(line)
                self.fields["discount_percent"] = forms.DecimalField(
                    label=_("Discount in percent"),
                    min_value=0,
                    max_value=100,
                    decimal_places=2,
                    required=False,
                    # The maximum is told before the discount is typed – and, above it, while it is typed.
                    help_text=(
                        _("The line allows at most %(percent)s %%.") % {"percent": format_decimal(maximum)}
                        if maximum is not None
                        else ""
                    ),
                )
                if line.uses_rental_days:
                    self.fields["manual_scale_factor"] = forms.DecimalField(
                        label=_("Scale factor by hand"),
                        min_value=0,
                        decimal_places=3,
                        required=False,
                        help_text=_("Empty: the factor follows the rental days."),
                    )
                if line.is_free_line:
                    self.fields["tax_rate"] = forms.ModelChoiceField(
                        label=_("Tax rate"), queryset=TaxRate.objects.filter(is_active=True)
                    )
            if line.is_free_line:
                self.fields["unit"] = forms.ModelChoiceField(
                    label=_("Unit"), queryset=Unit.objects.filter(is_active=True), required=False
                )
            if line.is_subrental:
                # PRJ-101: the supplier is typed with suggestions (and can be created there); "Status" starts "open".
                self.fields["supplier"] = supplier_field(line.supplier)
                self.fields["subrental_status"] = subrental_status_field()
                # PRJ-097: fetched at the supplier and brought back – trips of the project.
                self.fields["picked_up_at_supplier"] = forms.BooleanField(
                    label=_("Picked up at the supplier"),
                    required=False,
                    help_text=_("Then the trips of the project fetch it at packing and bring it back afterwards."),
                )
                if rights.has(SpecialRight.PURCHASE_PRICES):
                    self.fields["purchase_price"] = forms.DecimalField(
                        label=_("Purchase price per unit"),
                        min_value=0,
                        decimal_places=2,
                        required=False,
                        help_text=_("What the supplier charges per unit for the whole period."),
                    )
            if product is not None and product.tracks_stock:
                self._add_preference_fields()
            if product is not None and (product.tracks_stock or product.is_kit) and line.project.is_in_family:
                self._add_takeover_field()
        if line.is_covering_subrental:
            # PRJ-055, PRJ-084: it is not charged and is a part of the line it covers, shown below it: no
            # price of its own, no group, nothing to choose about counting (PRJ-075). What is asked is
            # supplier, quantity, purchase price and status.
            for name in ("variant", "group", "unit_price", "discount_percent", "manual_scale_factor", "rental_days"):
                self.fields.pop(name, None)
            self.fields.pop("is_sale", None)
        else:
            # PRJ-083: an alternative names the line it could replace.
            self.fields["alternative_to"] = forms.ChoiceField(
                label=_("Alternative to"),
                choices=[("", _("– please choose –")), *alternative_choices(line.project, excluded={line.pk})],
                required=False,
                help_text=_("The line this one could replace."),
            )
            self.initial["alternative_to"] = line.alternative_to_id or ""
            # UIX-051 (UIX-035): required while the line is an alternative (``clean``).
            mark_required(self.fields["alternative_to"], f"{self.add_prefix('variant')}={LineVariant.ALTERNATIVE}")
        if line.is_customer_material:
            # PRJ-096: the customer's own material is taken along – no price, no discount, nothing to choose
            # about counting.
            for name in (
                "variant",
                "alternative_to",
                "unit_price",
                "discount_percent",
                "manual_scale_factor",
                "rental_days",
                "is_sale",
            ):
                self.fields.pop(name, None)
        self.style_fields()
        # Browsers offer earlier entries for fields they have seen before; in a
        # quantity or price field that only gets in the way (UIX-014).
        self.without_browser_history()

    def _add_takeover_field(self) -> None:
        """PRJ-060: the line of another part of the whole project whose pieces this line takes over."""
        line = self.line
        others = [pk for pk in line.project.family_ids() if pk != line.project_id]
        candidates = MaterialLine.objects.filter(
            project_id__in=others, product_id=line.product_id, is_sale=False, start__lt=line.start
        ).exclude(variant__gt="")
        if line.taken_over_from_id:
            candidates = candidates | MaterialLine.objects.filter(pk=line.taken_over_from_id)
        if not line.taken_over_from_id and not candidates.exists():
            return
        self.fields["taken_over_from"] = TakeoverChoiceField(
            label=_("Taken over from"),
            queryset=candidates.select_related("project").order_by("project__number", "start", "pk"),
            required=False,
            empty_label=_("– from the warehouse –"),
            help_text=_("The pieces come straight from that line of another subproject and are charged only there."),
        )

    def _add_preference_fields(self) -> None:
        """Fields for the wish for a specific model or item (PRJ-064)."""
        product = self.line.product
        models = MaterialModel.objects.filter(default_product=product) | MaterialModel.objects.filter(
            items__product_override=product
        )
        self.fields["preferred_model"] = forms.ModelChoiceField(
            label=_("Specific model"),
            queryset=models.distinct().order_by("name"),
            required=False,
            empty_label=_("– any –"),
            help_text=_("Internal hint for the warehouse. Appears on the packing list, never on customer documents."),
        )
        self.fields["preferred_item_number"] = forms.CharField(
            label=_("Specific item (ID)"),
            required=False,
            help_text=_("ID of the one item that should go out. Empty: any item."),
        )
        if self.line.preferred_item_id:
            self.initial["preferred_item_number"] = self.line.preferred_item.display_id
        # (piece share): a line of several pieces can wish for one item per piece.
        if self.line.pieces_total > 1:
            self.fields["further_item_numbers"] = forms.CharField(
                label=_("Further specific items (IDs)"),
                required=False,
                help_text=ngettext(
                    "IDs of further items, separated by commas. Each wished item covers one of the %(count)d piece of "
                    "this line; the others come from any item of the product.",
                    "IDs of further items, separated by commas. Each wished item covers one of the %(count)d pieces "
                    "of this line; the others come from any item of the product.",
                    self.line.pieces_total,
                )
                % {"count": self.line.pieces_total},
            )
            self.initial["further_item_numbers"] = ", ".join(item.display_id for item in self.line.wished_items[1:])

    def _initial_from_line(self) -> dict[str, Any]:
        """The current values of the line for all fields the form may show."""
        line = self.line
        names = [
            "title",
            "quantity",
            "group",
            "start",
            "end",
            "note",
            "is_sale",
            "hours",
            "quantity_is_estimate",
            "rental_days",
            "unit_price",
            "discount_percent",
            "manual_scale_factor",
            "tax_rate",
            "unit",
            "supplier",
            "subrental_status",
            "picked_up_at_supplier",
            "purchase_price",
            "surcharge_percent",
            "preferred_model",
            "variant",
            "taken_over_from",
        ]
        return {name: getattr(line, name) for name in names}

    def _add_surcharge_fields(self, can_price: bool) -> None:
        """Fields of a percentage surcharge: the percentage and what it refers to (PRD-031)."""
        line = self.line
        if can_price:
            self.fields["surcharge_percent"] = forms.DecimalField(
                label=_("Surcharge in percent"), min_value=0, max_value=1000, decimal_places=2
            )
        choices: list[tuple[str, Any]] = [("project", _("The whole project"))]
        choices += [
            (f"group:{group.pk}", _("Group: %(name)s") % {"name": group.path})
            for group in GroupTree(line.project.groups.all()).ordered
        ]
        choices += [
            (f"line:{other.pk}", _("Line: %(title)s") % {"title": f"{other.quantity_display} × {other.title}"})
            for other in line.project.material_lines.select_related("product")
            if other.pk != line.pk
            and not other.is_surcharge
            and not other.is_covering_subrental
            and not other.is_text  # (text lines; PRJ-128): a text line has no amount
        ]
        current = []
        for target in line.surcharge_targets.all():
            if target.target_type == SurchargeTargetType.PROJECT:
                current.append("project")
            elif target.target_type == SurchargeTargetType.GROUP:
                current.append(f"group:{target.target_group_id}")
            elif target.target_type == SurchargeTargetType.LINE:
                current.append(f"line:{target.target_line_id}")
        self.fields["targets"] = forms.MultipleChoiceField(
            label=_("Refers to"),
            choices=choices,
            initial=current,
            required=False,
            widget=forms.CheckboxSelectMultiple,
            help_text=_("The percentage is taken from these amounts after discounts, and never from other surcharges."),
        )

    def clean_preferred_item_number(self) -> MaterialItem | None:
        """Turn the typed ID into the item; unknown IDs are rejected (PRJ-064)."""
        text = (self.cleaned_data.get("preferred_item_number") or "").strip()
        if not text:
            return None
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        item = MaterialItem.objects.filter(inventory_number=number).select_related("material_model").first()
        if item is None:
            raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
        return item

    def clean_further_item_numbers(self) -> list[MaterialItem]:
        """Turn the typed IDs, separated by commas, into the items; unknown IDs are rejected (piece share)."""
        items: list[MaterialItem] = []
        for text in re.split(r"[,;\s]+", self.cleaned_data.get("further_item_numbers") or ""):
            if not text:
                continue
            try:
                number = parse_inventory_number(text)
            except ValidationError as error:
                raise forms.ValidationError(error.messages) from error
            item = MaterialItem.objects.filter(inventory_number=number).select_related("material_model").first()
            if item is None:
                raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
            items.append(item)
        return items

    def clean_alternative_to(self) -> MaterialLine | None:
        """The chosen line of the project (PRJ-083); the list offers only lines that may be named."""
        value = self.cleaned_data.get("alternative_to") or ""
        if not (str(value).isascii() and str(value).isdigit()):
            return None
        # (text lines; PRJ-128): never a text line, whatever was posted.
        return self.line.project.material_lines.filter(pk=int(value), is_text=False).first()

    def clean(self) -> dict[str, Any]:
        """The end must be after the start; an alternative names what it could replace (PRJ-083)."""
        cleaned = super().clean() or {}
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        if "alternative_to" in self.fields:
            if cleaned.get("variant") == LineVariant.ALTERNATIVE and cleaned.get("alternative_to") is None:
                self.add_error("alternative_to", _("Choose the line this one could replace."))
            elif cleaned.get("variant") != LineVariant.ALTERNATIVE:
                cleaned["alternative_to"] = None
        if "subrental_status" in self.fields:
            check_subrental_status(self, "subrental_status")  # PRJ-101
        item, model = cleaned.get("preferred_item_number"), cleaned.get("preferred_model")
        if item is not None and model is not None and item.material_model_id != model.pk:
            if "preferred_model" in self.changed_data:
                self.add_error(
                    "preferred_model",
                    _("The item %(id)s is of the model %(model)s. Remove the item to choose another model.")
                    % {"id": item.display_id, "model": item.material_model.name},
                )
            else:
                # The item was changed, the model still shows the old one: the item decides.
                cleaned["preferred_model"] = item.material_model
        return cleaned

    def changes(self) -> dict[str, Any]:
        """Return the submitted values that differ from the line, without the surcharge targets."""
        changed: dict[str, Any] = {}
        for name, value in self.cleaned_data.items():
            if name in {"targets", "further_item_numbers"}:
                continue
            if name == "discount_percent" and value is None:
                value = 0
            target = self.FIELD_TARGETS.get(name, name)
            if getattr(self.line, target) != value:
                changed[target] = value
        if "preferred_item" in changed and "preferred_model" in self.cleaned_data:
            # Say what the dialog shows for the model too: a chosen item fixes
            # its model, a removed item leaves the model as it is chosen.
            item = changed["preferred_item"]
            changed["preferred_model"] = item.material_model if item else self.cleaned_data["preferred_model"]
        if "further_item_numbers" in self.fields:
            self._add_wished_items(changed)
        return changed

    def _add_wished_items(self, changed: dict[str, Any]) -> None:
        """All wished items at once, if they differ from the line's: the first field plus the further ones."""
        first = self.cleaned_data.get("preferred_item_number")
        wanted: list[MaterialItem] = []
        for item in ([first] if first else []) + self.cleaned_data.get("further_item_numbers", []):
            if item.pk not in {known.pk for known in wanted}:
                wanted.append(item)
        if [item.pk for item in wanted] != self.line.wished_item_ids:
            changed.pop("preferred_item", None)
            changed["preferred_items"] = wanted
            changed["preferred_model"] = wanted[0].material_model if wanted else self.cleaned_data["preferred_model"]

    def targets(self) -> list[dict[str, Any]] | None:
        """Return the chosen surcharge targets as the service expects them, or ``None``."""
        if "targets" not in self.cleaned_data:
            return None
        result: list[dict[str, Any]] = []
        for value in self.cleaned_data["targets"]:
            kind, _separator, identifier = value.partition(":")
            result.append({"type": kind, "id": int(identifier) if identifier else None})
        return result


class FreeLineForm(StyledForm):
    """Add a line without product: text, quantity and price (PRJ-017)."""

    title = forms.CharField(label=_("Title"), max_length=200)
    quantity = forms.DecimalField(label=_("Quantity"), min_value=0, decimal_places=2, initial=1)
    unit = forms.ModelChoiceField(label=_("Unit"), queryset=Unit.objects.filter(is_active=True), required=False)
    unit_price = forms.DecimalField(label=_("Unit price (net)"), min_value=0, decimal_places=2, initial=0)
    tax_rate = forms.ModelChoiceField(label=_("Tax rate"), queryset=TaxRate.objects.filter(is_active=True))
    group = GroupChoiceField(
        label=_("Group"), queryset=Group.objects.none(), required=False, empty_label=_("– without group –")
    )

    def __init__(self, *args: Any, project: Project, rights: Rights, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = project.groups.all()
        self.fields["tax_rate"].initial = TaxRate.get_default()
        if not rights.has(SpecialRight.PRICES):
            del self.fields["unit_price"]
            del self.fields["tax_rate"]
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")


class TextLineForm(StyledForm):
    """Add a line that only carries a text – a heading or a remark (text line; PRJ-128)."""

    title = forms.CharField(
        label=_("Text"),
        max_length=200,
        help_text=_(
            "For example a heading or a remark: “Setup from 2 pm”. Printed on offers, order confirmations and invoices."
        ),
    )
    note = forms.CharField(
        label=_("Further text"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Optional; printed below the text."),
    )
    group = GroupChoiceField(
        label=_("Group"), queryset=Group.objects.none(), required=False, empty_label=_("– without group –")
    )

    def __init__(self, *args: Any, project: Project, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = project.groups.all()
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")


class SubrentalForm(StyledForm):
    """Subrent the pieces a line is short of (PRJ-054, PRJ-084).

    The subrental is a part of the line it covers; the customer pays the
    price of that line (PRJ-055). So what is asked is the supplier, how many
    pieces, what the supplier charges and where the order stands – never a
    rental price.
    """

    quantity = forms.IntegerField(label=_("Quantity"), min_value=1)
    purchase_price = forms.DecimalField(
        label=_("Purchase price per unit"),
        min_value=0,
        decimal_places=2,
        required=False,
        help_text=_("What the supplier charges per unit for the whole period."),
    )

    def __init__(self, *args: Any, rights: Rights, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # PRJ-101: the supplier is typed with suggestions (and can be created there); "Status" starts "open".
        self.fields["supplier"] = supplier_field(None)
        self.fields["status"] = subrental_status_field(required=False)
        if not rights.has(SpecialRight.PURCHASE_PRICES):
            del self.fields["purchase_price"]
        self.without_browser_history()

    def clean(self) -> dict[str, Any]:
        """PRJ-101: a status other than "open" needs a supplier."""
        cleaned = super().clean() or {}
        check_subrental_status(self, "status")
        return cleaned

    def without_browser_history(self) -> None:
        """Keep the browser from offering earlier entries in the fields (UIX-014)."""
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")


class LineAlternativeForm(StyledForm):
    """Make lines an alternative to another line of the planning (PRJ-083).

    One line through its button "Alternative", or several lines chosen on
    the planning (PRJ-082). The list offers the lines in the order of the
    planning, grouped by their groups.
    """

    alternative_to = forms.ChoiceField(
        label=_("Alternative to"),
        help_text=_("The line the chosen lines could replace."),
        error_messages={"required": _("Choose the line this one could replace.")},
    )

    def __init__(self, *args: Any, project: Project, lines: list[MaterialLine], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.project = project
        self.lines = lines
        excluded = {line.pk for line in lines}
        self.fields["alternative_to"].choices = [
            ("", _("– please choose –")),
            *alternative_choices(project, excluded=excluded),
        ]
        current = {line.alternative_to_id for line in lines}
        if len(current) == 1 and None not in current:
            self.initial["alternative_to"] = current.pop()

    def clean_alternative_to(self) -> MaterialLine:
        """The chosen line of the project."""
        value = self.cleaned_data.get("alternative_to") or ""
        # (text lines; PRJ-128): never a text line, whatever was posted.
        line = (
            self.project.material_lines.filter(pk=int(value), is_text=False).first()
            if str(value).isascii() and str(value).isdigit()
            else None
        )
        if line is None:
            raise forms.ValidationError(_("Choose the line this one could replace."))
        return line


class GroupAlternativeForm(StyledForm):
    """Make a group an alternative to another group of the planning (PRJ-083)."""

    alternative_to = GroupChoiceField(
        label=_("Alternative to"),
        queryset=Group.objects.none(),
        empty_label=_("– please choose –"),
        help_text=_("The group this one could replace."),
        error_messages={"required": _("Choose the group this one could replace.")},
    )

    def __init__(self, *args: Any, group: Group, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        offered = [pk for pk, _label in group_alternative_choices(group)]
        self.fields["alternative_to"].queryset = Group.objects.filter(pk__in=offered)
        if group.alternative_to_id:
            self.initial["alternative_to"] = group.alternative_to_id


def people_with_functions() -> list[tuple[Person, set[int]]]:
    """The active people, each with the IDs of the job functions assigned to them (PER-005).

    Two queries: the people, and their rate rows with the job functions joined (NFA-014) – the planning
    page can then afford the list of phases of the crew form (PRJ-080).
    """
    people = Person.objects.filter(is_active=True).prefetch_related(
        Prefetch("rates", queryset=PersonJobFunction.objects.select_related("job_function"))
    )
    return [(person, {rate.job_function_id for rate in person.rates.all()}) for person in people]


class PersonSelect(forms.Select):
    """A list of people whose options say which job functions each person has (PER-025).

    ``data-functions="3,7"`` on every option; the page script shows only the
    people with the job function chosen in the same form. A planner with the
    right to plan outside the job functions (``data-any``) sees the others
    too, marked as such.
    """

    def __init__(self, *args: Any, functions_of: dict[Any, set[int]] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.functions_of = functions_of or {}

    def create_option(self, name: str, value: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """One option, with the job functions of its person."""
        option = super().create_option(name, value, *args, **kwargs)
        key = str(getattr(value, "value", value))
        if key and key.isascii() and key.isdigit():
            option["attrs"]["data-functions"] = ",".join(str(pk) for pk in sorted(self.functions_of.get(int(key), ())))
        return option


def people_choices(
    job_function: JobFunction | None = None, *, include_others: bool = False, keep: Person | None = None
) -> tuple[list[tuple[Any, str]], dict[int, set[int]]]:
    """The people a planner may choose for a job function, and the functions of each (PER-006, PER-025).

    Only people who have the job function are offered – a person appears in
    the list once the job function is assigned in the personnel data.
    Without a job function (the short form below the crew block, where it is
    chosen in the same form) everybody with any job function is in the list
    and the page script narrows it. ``include_others`` adds the people
    without the function for planners who may deviate; ``keep`` is a person
    already planned who would otherwise be missing (deactivated, or the
    function taken away since).
    """
    rows = []
    functions_of: dict[int, set[int]] = {}
    for person, functions in people_with_functions():
        functions_of[person.pk] = functions
        has_it = job_function.pk in functions if job_function is not None else bool(functions)
        if not has_it and not include_others and (keep is None or keep.pk != person.pk):
            continue
        names = sorted({rate.job_function.name for rate in person.rates.all()})
        label = f"{person.sort_name} ({', '.join(names)})" if names else person.sort_name
        rows.append((not has_it, person.sort_name.lower(), person.pk, label))
    choices = [(pk, label) for _order, _name, pk, label in sorted(rows)]
    if keep is not None and keep.pk not in functions_of:
        choices.append((keep.pk, keep.sort_name))
    return choices, functions_of


def phase_label(phase: ProjectPhase) -> str:
    """A phase with its period, for a list to choose from: "Setup (Fri 12.03. 08:00 – 20:00)" (PRJ-080)."""
    start, end = timezone.localtime(phase.start), timezone.localtime(phase.end)
    until = dateformat.format(end, "H:i" if start.date() == end.date() else "D d.m. H:i")
    return f"{phase.label} ({dateformat.format(start, local_pattern('D d.m. H:i'))} – {until})"


class PhaseSelect(forms.Select):
    """A list of the phases of a project whose options carry their periods (PRJ-080).

    ``data-start`` and ``data-end`` on every option, in the format of the
    date fields; choosing a phase makes the page script fill in "from" and
    "until" of the same form (``data-fills-period``).
    """

    def __init__(self, *args: Any, periods: dict[int, tuple[str, str]] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.periods = periods or {}
        self.attrs["data-fills-period"] = "start,end"

    def create_option(self, name: str, value: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """One option, with the period of its phase."""
        option = super().create_option(name, value, *args, **kwargs)
        key = str(getattr(value, "value", value))
        if key.isascii() and key.isdigit() and int(key) in self.periods:
            option["attrs"]["data-start"], option["attrs"]["data-end"] = self.periods[int(key)]
        return option


def phase_field(
    project: Project | None, *, keep: ProjectPhase | None = None, offer_new: bool = False
) -> forms.ModelChoiceField:
    """The field "Phase" of the crew forms: the phases of the project with their periods (PRJ-080).

    The phases are read once, here; the list does not ask the database again.

    PRJ-094: with ``offer_new`` – for whoever may edit the project – the list
    names the dialog for a new phase (``data-new-phase-url``). The page script
    adds the entry "New phase …" that opens it, and puts the new phase into
    the list; without the script there is no such entry.
    """
    phases = list(project.phases.all()) if project is not None else []
    if keep is not None and keep.pk not in {phase.pk for phase in phases}:
        phases.append(keep)
    periods = {
        phase.pk: (
            timezone.localtime(phase.start).strftime(DATETIME_FORMAT),
            timezone.localtime(phase.end).strftime(DATETIME_FORMAT),
        )
        for phase in phases
    }
    field = forms.ModelChoiceField(
        label=_("Phase"),
        queryset=ProjectPhase.objects.filter(project=project) if project is not None else ProjectPhase.objects.none(),
        required=False,
        empty_label=_("– no phase –"),
        widget=PhaseSelect(periods=periods),
        help_text=_("Choosing a phase takes over its period."),
    )
    field.choices = [("", _("– no phase –")), *((phase.pk, phase_label(phase)) for phase in phases)]
    if offer_new and project is not None:
        field.widget.attrs["data-new-phase-url"] = reverse("projects:phase_dialog", args=[project])
        field.widget.attrs["data-new-phase-label"] = _("New phase …")
    return field


def _period_of_phase(form: forms.Form, cleaned: dict[str, Any]) -> None:
    """PRJ-080: with a phase, "from" and "until" left empty or untouched mean the phase's period.

    The page script fills in the period when a phase is chosen; without it,
    the service takes the period of the phase for what is not given (see
    ``crew.add_crew_lines`` and ``crew.update_crew_line``).
    """
    if cleaned.get("phase") is None:
        return
    for name in ("start", "end"):
        if not cleaned.get(name) or name not in form.changed_data:
            cleaned[name] = None


class CrewAddForm(StyledForm):
    """The short form below the crew block: job function, person or open places (PRJ-019, PRJ-020).

    With the phase (PRJ-080): chosen with the period of the phase,
    or preset when the form is opened for a phase on the page "Zeitplanung".
    """

    job_function = forms.ModelChoiceField(
        label=_("Job function"), queryset=JobFunction.objects.filter(is_active=True), empty_label=_("– choose –")
    )
    person = forms.ModelChoiceField(
        label=_("Person"),
        queryset=Person.objects.filter(is_active=True),
        required=False,
        empty_label=_("– still open –"),
        widget=PersonSelect,
    )
    count = forms.IntegerField(label=_("Places"), min_value=1, max_value=50, initial=1)
    start = forms.DateTimeField(label=_("From"), required=False)
    end = forms.DateTimeField(label=_("Until"), required=False)
    # PER-041 (firm planning): the person is planned without request – and told.
    firm = forms.BooleanField(label=_("Planned firmly (without request)"), required=False)

    def __init__(
        self,
        *args: Any,
        project: Project | None = None,
        may_plan_any: bool = False,
        phase: ProjectPhase | None = None,
        offer_new_phase: bool = False,
        **kwargs: Any,
    ) -> None:
        if project is not None:
            # "2 × stagehand, Saturday 08–14": the period starts as the project's – or the phase's – and is
            # narrowed here.
            period = phase or project
            kwargs.setdefault("initial", {}).update(
                {"start": timezone.localtime(period.start), "end": timezone.localtime(period.end)}
            )
            if phase is not None:
                kwargs["initial"]["phase"] = phase.pk
        # IDs of their own: the form sits on the planning page next to the forms of the lines.
        kwargs.setdefault("auto_id", "crew-%s")
        super().__init__(*args, **kwargs)
        # PRJ-094: "New phase …" in the list, for whoever may edit the project.
        self.fields["phase"] = phase_field(project, offer_new=offer_new_phase)
        choices, functions_of = people_choices(include_others=may_plan_any)
        self.fields["person"].choices = [("", _("– still open –")), *choices]
        self.fields["person"].widget.functions_of = functions_of
        self.fields["person"].widget.attrs["data-people-for"] = "job_function"
        if may_plan_any:
            self.fields["person"].widget.attrs["data-any"] = "1"
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")

    @property
    def has_phases(self) -> bool:
        """Whether the project has phases to choose from (PRJ-080)."""
        return len(self.fields["phase"].choices) > 1

    @property
    def offers_new_phase(self) -> bool:
        """Whether the page script may offer "New phase …" in the list (PRJ-094)."""
        return "data-new-phase-url" in self.fields["phase"].widget.attrs

    def clean(self) -> dict[str, Any]:
        """The end must be after the start; a phase brings its period (PRJ-080); only a person is planned firmly."""
        cleaned = super().clean() or {}
        _period_of_phase(self, cleaned)
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        if cleaned.get("firm") and not cleaned.get("person"):
            self.add_error("firm", _("Plan a person first; an open place cannot be planned firmly."))
        return cleaned


class VehicleLineChoiceField(forms.ModelChoiceField):
    """LOG-008: a booked vehicle of the project, by its title and licence plate."""

    def label_from_instance(self, obj: Any) -> str:
        """The booking in short: "Sprinter (B-RL 123)"."""
        return obj.label


class CrewLineForm(RowLayoutMixin, StyledForm):
    """Edit a crew line in a dialog. Prices and costs appear only with the matching rights (AUT-019).

    Like :class:`LineForm`, the form does not save by itself: ``changes()``
    returns what differs from the line, and the view passes it to
    ``projects.crew.update_crew_line`` – the same function the API uses.
    """

    # A crew line always has a job function, so the list offers no empty choice.
    job_function = forms.ModelChoiceField(
        label=_("Job function"), queryset=JobFunction.objects.none(), empty_label=None
    )
    person = forms.ModelChoiceField(
        label=_("Person"),
        queryset=Person.objects.none(),
        required=False,
        empty_label=_("– still open –"),
        widget=PersonSelect,
    )
    start = forms.DateTimeField(label=_("From"))
    end = forms.DateTimeField(label=_("Until"))
    planned_hours = forms.DecimalField(label=_("Planned hours"), min_value=0, decimal_places=2)
    meeting_point = forms.CharField(label=_("Meeting point"), max_length=200, required=False)
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Visible to the person in the deployment view."),
    )
    # PER-041: planned without request; unticked again, the line is "not asked" and can be asked.
    firm = forms.BooleanField(
        label=_("Planned firmly (without request)"),
        required=False,
        help_text=_("The person is told instead of asked. A person who accepted already counts as planned firmly."),
    )

    LAYOUT = (
        ("job_function", "person"),
        ("firm",),
        ("phase",),
        ("start", "end"),
        ("planned_hours", "meeting_point"),
        ("vehicle_line", "is_driver"),
        ("billing", "days"),
        ("unit_price", "discount_percent"),
        ("hours_limit", "unit_price_above_limit"),
        ("time_surcharges_on_price",),
        ("hourly_rate", "daily_rate"),
        ("hourly_rate_above_limit", "cost_flat_rate"),
        ("time_surcharges_on_cost",),
        ("note",),
    )

    def __init__(
        self, *args: Any, line: CrewLine, rights: Rights, offer_new_phase: bool = False, **kwargs: Any
    ) -> None:
        self.line = line
        names = ["job_function", "person", "start", "end", "planned_hours", "meeting_point", "note", "days"]
        names += ["billing", "unit_price", "discount_percent", "hourly_rate", "daily_rate", "cost_flat_rate"]
        names += ["hours_limit", "unit_price_above_limit", "hourly_rate_above_limit"]  # PER-035
        names += ["time_surcharges_on_price", "time_surcharges_on_cost"]  # PER-009
        kwargs.setdefault("initial", {}).update({name: getattr(line, name) for name in names})
        kwargs["initial"]["phase"] = line.phase_id
        kwargs["initial"]["vehicle_line"] = line.vehicle_line_id
        kwargs["initial"]["is_driver"] = line.is_driver
        kwargs["initial"]["firm"] = line.request_status == RequestStatus.FIRM  # PER-041
        super().__init__(*args, **kwargs)
        # PRJ-080: the phase; choosing one takes over its period. PRJ-094: "New phase …" for whoever edits the project.
        self.fields["phase"] = phase_field(line.project, keep=line.phase, offer_new=offer_new_phase)
        # LOG-008: who travels with which motor vehicle of the project, and who drives it.
        vehicles = line.project.vehicle_lines.filter(product__vehicle_type="car").select_related("item__vehicle")
        if vehicles.exists() or line.vehicle_line_id:
            self.fields["vehicle_line"] = VehicleLineChoiceField(
                label=_("Vehicle"), queryset=vehicles, required=False, empty_label=_("– no vehicle –")
            )
            self.fields["is_driver"] = forms.BooleanField(label=_("Drives the vehicle"), required=False)
        functions = JobFunction.objects.filter(is_active=True) | JobFunction.objects.filter(pk=line.job_function_id)
        self.fields["job_function"].queryset = functions.distinct().order_by("name")
        people = Person.objects.filter(is_active=True) | Person.objects.filter(pk=line.person_id or 0)
        self.fields["person"].queryset = people.distinct()
        may_plan_any = rights.has(SpecialRight.PLAN_ANY_JOB_FUNCTION)
        # Everybody who has a job function, narrowed by the page script to the chosen one (PER-025).
        choices, functions_of = people_choices(None, include_others=may_plan_any, keep=line.person)
        self.fields["person"].choices = [("", _("– still open –")), *choices]
        self.fields["person"].widget.functions_of = functions_of
        self.fields["person"].widget.attrs["data-people-for"] = "job_function"
        if may_plan_any:
            self.fields["person"].widget.attrs["data-any"] = "1"
        if rights.has(SpecialRight.PRICES):
            self.fields["billing"] = forms.ChoiceField(
                label=_("Billing"),
                choices=CrewBilling.choices,
                help_text=_(
                    "By effort: approved hours are charged; until then the planned hours as an estimate. "
                    "Per day: the days × the price per day."
                ),
            )
            self.fields["unit_price"] = forms.DecimalField(
                label=_("Price (net)"),
                min_value=0,
                decimal_places=2,
                help_text=_("Per hour; with “per day” per day; with “flat rate” the price of the whole deployment."),
            )
            # PER-035: hour tiers per day, taken from the service product; only for billing by the hour.
            self.fields["hours_limit"] = forms.DecimalField(
                label=_("Limit in hours per day"),
                min_value=Decimal("0.25"),
                max_value=Decimal("23.75"),
                decimal_places=2,
                required=False,
                help_text=_("By plan or by effort: the hours of one day beyond this cost the price from the limit."),
            )
            self.fields["unit_price_above_limit"] = forms.DecimalField(
                label=_("Price per hour from the limit"), min_value=0, decimal_places=2, required=False
            )
            # PER-009: surcharges for night, Sunday and holidays on the price of this line.
            self.fields["time_surcharges_on_price"] = forms.BooleanField(
                label=_("Surcharges for night, Sunday and holidays on the price"),
                required=False,
                help_text=_("By plan or by effort; the percentages are set under Settings → Surcharges."),
            )
        if rights.has(SpecialRight.PRICES) or line.is_billed_per_day:
            # PER-029: the days charged per day; empty follows the period, like the rental days of a line.
            self.fields["days"] = forms.IntegerField(
                label=_("Days"),
                min_value=1,
                max_value=999,
                required=False,
                help_text=_("Charged with “per day”. Empty: the calendar days of the period (now %(days)d).")
                % {"days": line.period_days},
            )
            # PER-026: the job function may allow less; the calculation then takes its maximum.
            maximum = line.job_function.max_discount_percent
            self.fields["discount_percent"] = forms.DecimalField(
                label=_("Discount in percent"),
                min_value=0,
                max_value=100,
                decimal_places=2,
                required=False,
                help_text=(
                    _("The job function allows at most %(percent)s %%.") % {"percent": format_decimal(maximum)}
                    if maximum is not None
                    else ""
                ),
            )
        if rights.has(SpecialRight.PERSONNEL_COSTS):
            self.fields["hourly_rate"] = forms.DecimalField(
                label=_("Hourly rate (internal)"),
                min_value=0,
                decimal_places=2,
                required=False,
                help_text=_("Taken from the person when assigned. Change it only for this deployment."),
            )
            # PER-029: what a day of the person costs; a line billed per day costs days × this.
            self.fields["daily_rate"] = forms.DecimalField(
                label=_("Day rate (internal)"),
                min_value=0,
                decimal_places=2,
                required=False,
                help_text=_("Taken from the person when assigned; used with “per day”. Empty: the guide value."),
            )
            self.fields["cost_flat_rate"] = forms.DecimalField(
                label=_("Flat rate for the person"),
                min_value=0,
                decimal_places=2,
                required=False,
                help_text=_("Internal cost of the whole deployment, instead of hours × hourly rate."),
            )
            # PER-035: the cost of an hour beyond the limit of hours per day.
            self.fields["hourly_rate_above_limit"] = forms.DecimalField(
                label=_("Hourly rate from the limit (internal)"),
                min_value=0,
                decimal_places=2,
                required=False,
                help_text=_("Taken from the person when assigned. Empty: the hourly rate."),
            )
            # PER-009: surcharges for night, Sunday and holidays on the costs of this line.
            self.fields["time_surcharges_on_cost"] = forms.BooleanField(
                label=_("Surcharges for night, Sunday and holidays on the costs"),
                required=False,
                help_text=_("By plan or by effort, not with a flat rate for the person."),
            )
        self.style_fields()
        self.without_browser_history()

    def clean(self) -> dict[str, Any]:
        """The end must be after the start."""
        cleaned = super().clean() or {}
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        return cleaned

    def changes(self) -> dict[str, Any]:
        """Return the submitted values that differ from the line; an empty discount is none.

        PRJ-080: a new phase with "from" and "until" left as they were brings
        the period of the phase – the page script fills it in, and without
        the script ``crew.update_crew_line`` does.
        """
        cleaned = dict(self.cleaned_data)
        # PER-041: "planned firmly" is no field of the line – passed only when the box changed.
        firm = cleaned.pop("firm", False)
        if "firm" in self.changed_data and firm != (self.line.request_status == RequestStatus.FIRM):
            return {**self._changed_values(cleaned), "firm": firm}
        return self._changed_values(cleaned)

    def _changed_values(self, cleaned: dict[str, Any]) -> dict[str, Any]:
        """The values of the form that differ from the line (see :meth:`changes`)."""
        if "discount_percent" in cleaned and cleaned["discount_percent"] is None:
            cleaned["discount_percent"] = 0
        if "vehicle_line" in cleaned and cleaned["vehicle_line"] is None:
            cleaned["is_driver"] = False  # LOG-008: nobody drives without a vehicle
        phase = cleaned.get("phase")
        if phase is not None and phase.pk != self.line.phase_id:
            for name in ("start", "end"):
                if name not in self.changed_data:
                    cleaned.pop(name, None)
        return {name: value for name, value in cleaned.items() if getattr(self.line, name) != value}


class MembershipForm(StyledForm):
    """Give a user access to one project (AUT-016, AUT-025).

    On a subproject the level "no access" is offered as well: it takes away,
    in this part, what a membership of the whole project gives (PRJ-049).
    """

    user = forms.ModelChoiceField(label=_("User"), queryset=User.objects.filter(is_active=True))
    level = forms.ChoiceField(label=_("Access"), choices=ProjectAccessLevel.choices, initial=ProjectAccessLevel.READ)

    def __init__(self, *args: Any, project: Project | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if project is None or not project.parent_id:
            self.fields["level"].choices = [
                choice for choice in ProjectAccessLevel.choices if choice[0] != ProjectAccessLevel.NONE
            ]


class PhaseForm(StyledModelForm):
    """One phase of a project with period and place (PRJ-006).

    PRJ-080: a phase with crew lines asks whether they move along when its
    period changes – ticked by default (see ``crew.move_with_phase``).
    """

    move_crew = forms.BooleanField(label=_("Move the crew of this phase along"), required=False, initial=True)

    class Meta:
        model = ProjectPhase
        fields = ["kind", "title", "start", "end", "venue_site", "location", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        venues = Venue.objects.filter(is_active=True)
        if self.instance.venue_site_id:
            venues = venues | Venue.objects.filter(pk=self.instance.venue_site_id)
        self.fields["venue_site"].queryset = venues.order_by("name")
        self.fields["venue_site"].label = _("Venue")
        if not self.instance.pk:  # PRJ-116 (phase length; PRJ-124): a new phase starts with at most eight hours
            self.fields["end"].help_text = _("A new phase starts with at most eight hours. You may make it longer.")
        self.crew_count = self.instance.crew_lines.count() if self.instance.pk else 0
        # LOG-001: the vehicle bookings of the phase go along with its crew.
        self.vehicle_count = self.instance.vehicle_lines.count() if self.instance.pk else 0
        if self.crew_count:
            self.fields["move_crew"].help_text = ngettext(
                "%(count)d crew line belongs to this phase. If the period changes, a line with the period of the "
                "phase gets the new one; any other line moves by as much as the start of the phase.",
                "%(count)d crew lines belong to this phase. If the period changes, a line with the period of the "
                "phase gets the new one; any other line moves by as much as the start of the phase.",
                self.crew_count,
            ) % {"count": self.crew_count}
        if self.vehicle_count:
            self.fields["move_crew"].label = _("Move the crew and the vehicles of this phase along")
            vehicles = ngettext(
                "%(count)d vehicle booking belongs to it and moves the same way.",
                "%(count)d vehicle bookings belong to it and move the same way.",
                self.vehicle_count,
            ) % {"count": self.vehicle_count}
            self.fields["move_crew"].help_text = f"{self.fields['move_crew'].help_text} {vehicles}".strip()
        if not self.crew_count and not self.vehicle_count:
            del self.fields["move_crew"]


class OpenItemsForm(StyledForm):
    """Note what is still open (PRJ-059): one item per line."""

    texts = forms.CharField(
        label=_("Still open"),
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("e.g. setup times\ncontact on site")}),
        help_text=_("One item per line."),
    )

    def items(self) -> list[str]:
        """The lines that were typed."""
        return [line for line in self.cleaned_data["texts"].splitlines() if line.strip()]


class ProjectFileForm(StyledForm):
    """Upload a file to a project (PRJ-007)."""

    file = forms.FileField(label=_("File"))
    title = forms.CharField(label=_("Title"), max_length=200, required=False)
    document_type = forms.ModelChoiceField(
        label=_("Document type"), queryset=DocumentType.objects.none(), required=False
    )
    visible_to_crew = forms.ChoiceField(
        label=_("Visible to the crew"),
        choices=[("", _("as the document type says")), ("yes", _("yes")), ("no", _("no"))],
        required=False,
    )
    # PRJ-089: a show file notes its console or software and the version; suggestions from core.showfiles.
    show_system = forms.CharField(
        label=_("Console or software"),
        max_length=80,
        required=False,
        widget=forms.TextInput(attrs={"list": "show-systems", "autocomplete": "off"}),
        help_text=_("Recognised from the file name where it is unambiguous."),
    )
    show_version = forms.CharField(label=_("Software version"), max_length=40, required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        from rentalars.projects.showfiles import DocumentTypeSelect, endings_map

        super().__init__(*args, **kwargs)
        self.fields["document_type"].queryset = DocumentType.objects.filter(is_active=True)
        # PRJ-089: choosing a show file picks the type "Showfile" and the console its ending tells.
        self.fields["document_type"].widget = DocumentTypeSelect(choices=self.fields["document_type"].choices)
        self.fields["file"].widget.attrs["data-show-endings"] = endings_map()

    @property
    def show_system_names(self) -> list[str]:
        """PRJ-089: the consoles and programs to suggest."""
        from rentalars.core.showfiles import system_names

        return system_names()

    @property
    def max_upload_mb(self) -> int:
        """PRJ-089, NFA-007: the largest file to upload, as set in the settings."""
        from rentalars.core.models import SystemSettings

        return int(SystemSettings.load().max_upload_mb)

    def visibility(self) -> bool | None:
        """``True``/``False`` if chosen, ``None`` for the default of the document type."""
        value = self.cleaned_data.get("visible_to_crew")
        return {"yes": True, "no": False}.get(value or "")


class ProjectFileEditForm(StyledModelForm):
    """Title, document type and visibility of a stored file; PRJ-106: the kind of a supplier's document."""

    class Meta:
        model = ProjectFile
        # PRJ-089: console, version and the mark of the current show of a show file.
        fields = [
            "title",
            "document_type",
            "visible_to_crew",
            "supplier_document_kind",
            "show_system",
            "show_version",
            "is_current_show",
        ]
        widgets = {"show_system": forms.TextInput(attrs={"list": "show-systems", "autocomplete": "off"})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        from rentalars.projects.showfiles import DocumentTypeSelect

        super().__init__(*args, **kwargs)
        self.fields["document_type"].queryset = DocumentType.objects.filter(is_active=True)
        self.fields["document_type"].widget = DocumentTypeSelect(choices=self.fields["document_type"].choices)
        kind = self.fields["supplier_document_kind"]
        if self.instance.supplier_id:
            kind.required = True
            kind.choices = SupplierDocumentKind.choices
        else:
            kind.disabled = True  # only a document of a supplier has a kind

    @property
    def show_system_names(self) -> list[str]:
        """PRJ-089: the consoles and programs to suggest."""
        from rentalars.core.showfiles import system_names

        return system_names()


class DuplicateForm(StyledForm):
    """A copy of a project for a new period (PRJ-029)."""

    name = forms.CharField(label=_("Name"), max_length=200)
    start = forms.DateTimeField(label=_("material out from"))
    end = forms.DateTimeField(label=_("material back by"))
    with_material = forms.BooleanField(label=_("with the material"), required=False, initial=True)
    with_crew = forms.BooleanField(label=_("with the personnel needed (as open places)"), required=False)
    # LOG-001: the vehicle bookings and the vehicles on the trips.
    with_logistics = forms.BooleanField(label=_("with the logistics (vehicles and their trips)"), required=False)
    # PRJ-029, PRJ-044: only for a whole project with parts, and only for a part.
    with_subprojects = forms.BooleanField(
        label=_("with the subprojects"),
        required=False,
        initial=True,
        help_text=_(
            "Every subproject keeps its place relative to the start and its length. "
            "Material taken over between them stays taken over."
        ),
    )
    as_subproject = forms.BooleanField(
        label=_("as a new subproject of the same whole project"),
        required=False,
        initial=True,
        help_text=_(
            "Its period has to lie within that of the whole project. Without the tick the copy becomes a "
            "project of its own, and material taken over from other subprojects is planned as normal lines."
        ),
    )

    def __init__(self, *args: Any, source: Project | None = None, may_add_part: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if source is None or source.parent_id or not source.has_subprojects:
            del self.fields["with_subprojects"]
        if source is None or not source.parent_id or not may_add_part:
            del self.fields["as_subproject"]
        else:
            self.fields["as_subproject"].label = _("as a new subproject of %(number)s %(name)s") % {
                "number": source.parent.number,
                "name": source.parent.name,
            }

    def clean(self) -> dict[str, Any]:
        """The end must follow the start."""
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] <= data["start"]:
            self.add_error("end", _("The end must be after the start."))
        return data
