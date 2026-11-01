# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the service cases (PRJ-090)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.models import User
from rentalars.core.forms import StyledForm, StyledModelForm, mark_required
from rentalars.customers.models import Contact, Customer
from rentalars.projects.follow_up_views import FollowUpForm
from rentalars.projects.forms import offer_new_contact
from rentalars.projects.models import CaseStatus, CaseWaitingFor, Project, ProjectKind
from rentalars.projects.service_cases import CASE_FIELDS

#: AUT-033, AUT-034: what only who may see customers sees and changes of a service case – the page
#: of the case hides it from the others; the edit form leaves it out for them and the API keeps it (``case_api``).
CUSTOMER_SIDE = ("customer", "is_internal", "contact", "case_contact")


class ServiceCaseForm(StyledModelForm):
    """What a service case is about, for whom, who reported it and who takes care of it (PRJ-090).

    The customer is typed with suggestions, as in the project form (PRJ-070);
    It is required, as for a project – somebody who is no customer
    yet is created as one from the suggestions. The description stays
    optional. The contacts offered are those of the chosen customer.

    AUT-033, AUT-034: ``customer_fields=False`` – for who may not see customers – leaves out
    the customer's side (:data:`CUSTOMER_SIDE`): no customer, contact, "internal" or who reported it, not even
    the list of a customer's contacts; the case keeps them as they are.

    PRJ-140: with ``rights`` that allow changing customers, the contact field ends with "New contact person …",
    as in the project form (:func:`rentalars.projects.forms.offer_new_contact`).
    """

    class Meta:
        model = Project
        fields = list(CASE_FIELDS)
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}
        labels = {
            "name": _("What is it about?"),
            "notes": _("Description"),
            "manager": _("Responsible"),
            "is_internal": _("Internal – our own material, no customer"),
        }

    def __init__(self, *args: Any, customer_fields: bool = True, rights: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The model checks a new case as a case; the form asks for the customer (PRJ-090) – unless the case
        # is internal (MAT-057): a repair of the company's own material.
        self.instance.kind = ProjectKind.SERVICE_CASE
        self.fields["manager"].queryset = User.objects.filter(is_active=True)
        self.fields["manager"].help_text = _("Is told that the case is theirs.")
        self.shows_customer = customer_fields
        self.new_contact_sent = False  # set by offer_new_contact; the form without the customer's side never has it
        if not customer_fields:
            for name in CUSTOMER_SIDE:
                del self.fields[name]
            return
        self.fields["customer"].widget = forms.HiddenInput()
        self.fields["customer"].required = False
        mark_required(self.fields["customer"], "is_internal=")
        self.fields["is_internal"].help_text = _("E.g. the repair of a defect of our own material.")
        customers = Customer.objects.filter(is_active=True)
        if self.instance.customer_id:
            customers = customers | Customer.objects.filter(pk=self.instance.customer_id)
        self.fields["customer"].queryset = customers.order_by("name")
        self.fields["customer"].help_text = _("Not a customer yet? Type the name and choose “… as a new customer”.")
        customer_id = self.data.get("customer") or self.initial.get("customer") or self.instance.customer_id
        if hasattr(customer_id, "pk"):
            customer_id = customer_id.pk
        # PRJ-140: as in the project form, whoever may change the customers creates the contact right here.
        offer_new_contact(self, rights, customer_id)
        self.fields["contact"].queryset = (
            Contact.objects.filter(customer_id=customer_id)
            if str(customer_id or "").isdigit()
            else Contact.objects.none()
        )
        self.fields["contact"].help_text = _("Contacts of the chosen customer.")

    def clean(self) -> dict[str, Any]:
        """The customer is needed unless the case is internal (PRJ-090, MAT-057)."""
        data = super().clean()
        if self.new_contact_sent:
            # The choice "New contact person" is no contact: the dialog did not open, so nothing was created.
            self.add_error(
                "contact",
                _("The dialog for a new contact person did not open. Choose a contact or create one at the customer."),
            )
        if not self.shows_customer:
            if not self.instance.is_internal and not self.instance.customer_id:
                # The case keeps its customer; one it lacks is chosen by somebody who may see customers.
                self.add_error(
                    None, _("The case has no customer yet. Somebody who may see customers chooses it first.")
                )
            return data
        if data.get("is_internal"):
            data["customer"] = None
            data["contact"] = None
        elif not data.get("customer") and "customer" not in self.errors:
            self.add_error("customer", _("Choose the customer of the service case."))
        return data

    @property
    def customer_text(self) -> str:
        """What the customer field shows: the name of the chosen customer."""
        value = self.data.get("customer") if self.is_bound else self.initial.get("customer", self.instance.customer_id)
        if hasattr(value, "name"):
            return value.name
        customer = Customer.objects.filter(pk=value).first() if str(value or "").isdigit() else None
        return customer.name if customer is not None else ""


class CaseStatusForm(StyledForm):
    """The status of a case (PRJ-090) – on the page of the case, one list with every status."""

    case_status = forms.ChoiceField(
        label=_("Status"),
        choices=CaseStatus.choices,
        # PRJ-112: the hint below the list says that three statuses open the follow-up dialog.
        widget=forms.Select(attrs={"aria-describedby": "case-status-hint"}),
    )


class CaseStatusFollowUpForm(FollowUpForm):
    """PRJ-112: a status that needs a follow-up – the follow-up dialog with the status and what the case waits for.

    The day is required (the base form), the time for "waiting to close"
    (``service_cases.set_case_status`` checks it, also for the API); what the
    case waits for only for "waiting".
    """

    case_status = forms.ChoiceField(choices=CaseStatus.choices, widget=forms.HiddenInput)
    case_waiting_for = forms.ChoiceField(
        label=_("Waiting for"),
        choices=[("", "–"), *CaseWaitingFor.choices],
        required=False,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        status = self.data.get("case_status") if self.is_bound else self.initial.get("case_status")
        if status == CaseStatus.CLOSING:
            self.fields["follow_up_on"].label = _("Close on")
            self.fields["follow_up_at"].required = True
            self.fields["follow_up_at"].help_text = _(
                "If nothing happens in the case until then, it is closed. A new mail or chat message opens it again."
            )
        if status == CaseStatus.WAITING:
            self.fields["case_waiting_for"].required = True
        else:
            del self.fields["case_waiting_for"]

    def follow_up(self) -> dict[str, Any]:
        """The follow-up as ``service_cases.set_case_status`` takes it."""
        data = self.cleaned_data
        return {
            "on": data["follow_up_on"],
            "at": data.get("follow_up_at"),
            "user": data["follow_up_user"],
            "note": data.get("follow_up_note", ""),
        }


class ParticipantForm(StyledForm):
    """Add a person to a service case – or change function and note of one taking part (PRJ-108).

    Not crew planning: no period, no request, no availability check.
    """

    person = forms.ModelChoiceField(label=_("Person"), queryset=None)
    job_function = forms.ModelChoiceField(
        label=_("Job function"),
        queryset=None,
        required=False,
        help_text=_("Optional – what the person does in the case."),
    )
    note = forms.CharField(label=_("Note"), max_length=250, required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        from rentalars.personnel.models import JobFunction, Person

        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = Person.objects.filter(is_active=True, anonymised_at__isnull=True).order_by(
            "last_name", "first_name"
        )
        self.fields["job_function"].queryset = JobFunction.objects.filter(is_active=True).order_by("name")
        self.fields["job_function"].empty_label = _("– none –")
