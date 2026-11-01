# SPDX-License-Identifier: GPL-3.0-or-later
"""Form building blocks shared by all modules, and the forms of the core module."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.models import User
from rentalars.core.defaults import PROJECT_PREFIX
from rentalars.core.models import CompanyProfile, NumberRange, SystemSettings

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


def mark_required(field: forms.Field, when: str = "") -> None:
    """Mark a field the rules of the model require although the form field itself is optional (UIX-035).

    The page then shows the asterisk of a required field at its label, and
    assistive technology hears "required". ``when`` is a condition in the
    form of ``data-show-if`` ("kind=rental|kit"): the field is required only
    while it holds, and the page script switches the asterisk and the
    ``required`` state of the field with it. Nothing changes in the
    validation: the model still decides, e.g. the price of a product
    (PRD-013).
    """
    if when:
        field.widget.attrs["data-require-if"] = when
    else:
        field.widget.attrs["aria-required"] = "true"


def routed_errors(form: forms.BaseForm, error: ValidationError) -> ValidationError:
    """The errors of a rule, each under a field the form really has.

    A rule names the model field an error belongs to; ``error_field_map`` of
    the form says where such errors appear when the form shows the field
    under another name. Errors of fields the form does not have go to the top
    of the form instead of being lost.
    """
    if not hasattr(error, "error_dict"):
        return error
    field_map = getattr(form, "error_field_map", {})
    routed: dict[str, list[Any]] = {}
    for name, field_errors in error.error_dict.items():
        target = field_map.get(name, name)
        if target != NON_FIELD_ERRORS and target not in form.fields:
            target = NON_FIELD_ERRORS
        routed.setdefault(target, []).extend(field_errors)
    return ValidationError(routed)


def add_validation_error(form: forms.BaseForm, error: ValidationError) -> None:
    """Show the ``ValidationError`` a service raised on the form – a plain form as well as a model form.

    Views used ``form._update_errors(error)``, a private method of Django's
    ``ModelForm``; a plain ``Form`` (writing a mail, ``mail.ComposeForm``)
    has none, so the user got a server error instead of the message. This
    goes through the public ``add_error`` instead.
    """
    form.add_error(None, routed_errors(form, error))


class StyledFormMixin:
    """Adjusts widgets so that forms work well with German input and on phones.

    * Decimal fields accept the German comma ("12,50") and show it.
    * Date and time fields use the browser's own pickers, which are far
      easier to use on a phone than typed dates (UIX-001).
    """

    fields: dict[str, forms.Field]

    def style_fields(self) -> None:
        """Apply the adjustments; call at the end of ``__init__``."""
        for field in self.fields.values():
            if isinstance(field, forms.DecimalField):
                field.localize = True
                field.widget = forms.TextInput(attrs={"inputmode": "decimal", **field.widget.attrs})
                field.widget.is_localized = True
            elif isinstance(field, forms.DateTimeField):
                field.widget = forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_FORMAT)
                field.input_formats = [DATETIME_FORMAT, "%Y-%m-%dT%H:%M:%S"]
            elif isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
                field.input_formats = ["%Y-%m-%d"]
            elif isinstance(field, forms.TimeField):
                field.widget = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
                field.input_formats = ["%H:%M", "%H:%M:%S"]
            elif isinstance(field, forms.IntegerField):
                field.widget.attrs.setdefault("inputmode", "numeric")


class RowLayoutMixin:
    """Lets a form say which of its fields stand side by side (UIX-014).

    ``LAYOUT`` lists the rows; each row names the fields that share it. A
    field the form does not have (because of the rights of the user, or the
    kind of record) is simply left out; a field that is missing in ``LAYOUT``
    gets a row of its own at the end, so that nothing is forgotten.

    Example::

        LAYOUT = (("title",), ("quantity", "group"), ("start", "end"), ("note",))
    """

    LAYOUT: ClassVar[tuple[tuple[str, ...], ...]] = ()
    fields: dict[str, forms.Field]

    def rows(self) -> list[list[forms.BoundField]]:
        """The fields of the form, row by row."""
        placed: set[str] = set()
        rows: list[list[forms.BoundField]] = []
        for names in self.LAYOUT:
            row = [self[name] for name in names if name in self.fields]  # type: ignore[index]
            if row:
                rows.append(row)
                placed.update(names)
        rows.extend([self[name]] for name in self.fields if name not in placed)  # type: ignore[index]
        return rows

    def without_browser_history(self) -> None:
        """Keep the browser from offering earlier entries in the fields of this form (UIX-014)."""
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    """A model form with the adjustments of :class:`StyledFormMixin`.

    The business rules live in the models' ``clean()`` methods and name the
    model field an error belongs to. A form does not always show that field
    under the same name, or at all. ``error_field_map`` says where such
    errors should appear; errors for fields the form does not have are shown
    at the top of the form instead of being lost.
    """

    #: ``{model field name: form field name}``
    error_field_map: ClassVar[dict[str, str]] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.style_fields()

    def _update_errors(self, errors: ValidationError) -> None:
        """Route errors raised by the model (Django's own validation) to fields this form really has."""
        super()._update_errors(routed_errors(self, errors))


class StyledForm(StyledFormMixin, forms.Form):
    """A plain form with the adjustments of :class:`StyledFormMixin`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.style_fields()


class CompanyProfileForm(StyledModelForm):
    """The company's own data (ADM-001)."""

    class Meta:
        model = CompanyProfile
        fields = [
            "name",
            "street",
            "postal_code",
            "city",
            "country",
            "phone",
            "email",
            "website",
            "tax_number",
            "vat_id",
            "bank_name",
            "iban",
            "bic",
            "logo",
            "register_details",
            "payment_terms_days",
            "warehouse_address",  # PRJ-097
            "document_language",  # UIX-029
        ]


class SystemSettingsForm(StyledModelForm):
    """Buffer times, usual times, password policy and login protection (ADM-004)."""

    class Meta:
        model = SystemSettings
        fields = [
            "buffer_before_hours",
            "buffer_after_hours",
            "default_start_time",
            "default_end_time",
            "password_min_length",
            "login_max_attempts",
            "login_lockout_minutes",
            "session_idle_minutes",
            "two_factor_for_administrators",
            "max_upload_mb",
            "maps_load_at_once",  # UIX-034
            "mail_tag_prefix",
            "people_see_own_rates",
            "ask_again_on_new_times",  # PER-034
            # ZEI-018: hints at conspicuous time entries; ZEI-019: travel costs per kilometre.
            "time_hints_enabled",  # ZEI-018: all hints on or off
            "time_hint_day_hours",
            "time_hint_break_hours",
            "time_hint_break_minutes",
            "time_hint_long_break_hours",
            "time_hint_long_break_minutes",
            "time_hint_rest_hours",
            "expense_km_rate",
            "expense_deduct_commute",  # ZEI-027
            "api_requests_per_minute",
            "retention_security_log_days",
            "retention_change_log_days",
            "retention_notifications_days",
            "retention_jobs_days",
            "retention_access_log_days",
        ]
        # ADM-014: the example of the tag with a project number of today.

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """ADM-015: "Answer to deployment requests" (PER-032) is chosen here; it is kept with the mail settings."""
        from rentalars.mail.models import CrewAnswerMode, MailSettings

        super().__init__(*args, **kwargs)
        self.mail_settings = MailSettings.load()
        stored = MailSettings._meta.get_field("crew_answers")
        self.fields["crew_answers"] = forms.ChoiceField(
            label=stored.verbose_name,
            choices=CrewAnswerMode.choices,
            initial=self.mail_settings.crew_answers,
            widget=forms.RadioSelect,
            help_text=stored.help_text,
        )

    def save(self, commit: bool = True) -> SystemSettings:
        """Store the settings, and the answer to deployment requests with the mail settings (ADM-015)."""
        from rentalars.mail.services import save_settings

        saved = super().save(commit=commit)
        if commit and self.mail_settings.crew_answers != self.cleaned_data["crew_answers"]:
            self.mail_settings.crew_answers = self.cleaned_data["crew_answers"]
            save_settings(self.mail_settings)
        return saved


#: B4: the settings in sections, in the order of the page – (id, title, field names). A field that
#: is in none of them is shown in a last section "Further settings", so that none is lost.
SETTINGS_SECTIONS: tuple[tuple[str, Any, tuple[str, ...]], ...] = (
    (
        "planning",
        _("Planning and buffer times"),
        (
            "buffer_before_hours",
            "buffer_after_hours",
            "default_start_time",
            "default_end_time",
            "ask_again_on_new_times",
        ),
    ),
    (
        "security",
        _("Security and login"),
        (
            "password_min_length",
            "login_max_attempts",
            "login_lockout_minutes",
            "session_idle_minutes",
            "two_factor_for_administrators",
            "api_requests_per_minute",
        ),
    ),
    ("files", _("Uploads and maps"), ("max_upload_mb", "maps_load_at_once")),
    ("mail", _("E-mail"), ("mail_tag_prefix", "crew_answers")),
    (
        "personnel",
        _("Personnel and times"),
        (
            "people_see_own_rates",
            "time_hints_enabled",
            "time_hint_day_hours",
            "time_hint_break_hours",
            "time_hint_break_minutes",
            "time_hint_long_break_hours",
            "time_hint_long_break_minutes",
            "time_hint_rest_hours",
            "expense_km_rate",
            "expense_deduct_commute",
        ),
    ),
    (
        "retention",
        _("Retention periods"),
        (
            "retention_security_log_days",
            "retention_change_log_days",
            "retention_notifications_days",
            "retention_jobs_days",
            "retention_access_log_days",
        ),
    ),
)


def settings_sections(form: forms.BaseForm) -> list[tuple[str, Any, list[Any]]]:
    """The fields of the settings form in sections for the page (B4): ``[(id, title, [bound fields])]``."""
    placed: set[str] = set()
    sections = []
    for section_id, title, names in SETTINGS_SECTIONS:
        fields = [form[name] for name in names if name in form.fields]
        placed.update(names)
        if fields:
            sections.append((section_id, title, fields))
    rest = [form[name] for name in form.fields if name not in placed]
    if rest:
        sections.append(("further", _("Further settings"), rest))
    return sections


class AccountingSwitchForm(StyledModelForm):
    """The box "Buchhaltung und Rechnungswesen": whether Rentalars is the accounting program (DOK-014, DOK-055)."""

    class Meta:
        model = SystemSettings
        fields = ["invoices_enabled"]


class NumberRangeForm(StyledModelForm):
    """Format and counter of one number range (ADM-003)."""

    class Meta:
        model = NumberRange
        fields = ["prefix", "min_digits", "next_value", "reset_yearly"]


class SetupForm(StyledForm):
    """Everything the first-run setup asks for on one page (NFA-033)."""

    company_name = forms.CharField(label=_("Company name"), max_length=200)
    street = forms.CharField(label=_("Street and number"), max_length=200, required=False)
    postal_code = forms.CharField(label=_("Postal code"), max_length=20, required=False)
    city = forms.CharField(label=_("City"), max_length=120, required=False)
    # UIX-029: the start data, the documents and the first administrator in this language.
    language = forms.ChoiceField(
        label=_("Language"),
        choices=[("de", "Deutsch"), ("en", "English")],
        required=False,  # not sent (a script, an older form): the installation's
        help_text=_(
            "The language of the documents to customers and of the start data (roles, units, categories …). "
            "Each user chooses the language of the interface."
        ),
    )

    username = forms.CharField(label=_("Username"), max_length=150)
    first_name = forms.CharField(label=_("First name"), max_length=150, required=False)
    last_name = forms.CharField(label=_("Last name"), max_length=150, required=False)
    email = forms.EmailField(label=_("E-mail address"))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password_repeat = forms.CharField(
        label=_("Repeat password"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    # ADM-014: project numbers are year and running number by default – 2026-0001.
    project_prefix = forms.CharField(
        label=_("Prefix of project numbers"),
        max_length=30,
        required=False,
        initial=PROJECT_PREFIX,
        help_text=_("{year} is replaced by the current year: 2026-0001."),
    )
    project_next = forms.IntegerField(label=_("Next project number"), min_value=1, initial=1)
    customer_next = forms.IntegerField(label=_("Next customer number"), min_value=1, initial=10001)
    material_next = forms.IntegerField(
        label=_("Next material ID"),
        min_value=1,
        initial=1,
        help_text=_("If you import an existing list, the counter continues after its highest ID automatically."),
    )

    default_tax_rate = forms.DecimalField(
        label=_("Standard tax rate in percent"), min_value=0, max_value=100, decimal_places=2, initial=19
    )
    # ADM-018: the job functions of the start data get a price and internal costs per hour at once – 0 €
    # would make every crew line free of charge until somebody notices.
    personnel_price = forms.DecimalField(
        label=_("Price per hour for the customer"),
        min_value=0,
        max_digits=8,
        decimal_places=2,
        initial=Decimal("45.00"),
        help_text=_("Net, for every job function (technician, lighting technician, stagehand …)."),
    )
    personnel_cost = forms.DecimalField(
        label=_("Internal costs per hour"),
        min_value=0,
        max_digits=8,
        decimal_places=2,
        initial=Decimal("30.00"),
        help_text=_("What an hour of work costs the company, as long as a crew line has no person yet."),
    )
    with_demo_data = forms.BooleanField(
        label=_("Create sample data"),
        required=False,
        help_text=_("Some products, material, customers and projects to try things out."),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """UIX-029: the language proposed is that of the page – the browser's, else the installation's."""
        from django.utils.translation import get_language

        from rentalars.core.i18n import installation_language, supported

        super().__init__(*args, **kwargs)
        self.fields["language"].initial = supported(get_language()) or installation_language()

    def clean(self) -> dict[str, Any]:
        """Check the administrator account: passwords match and satisfy the policy."""
        cleaned = super().clean() or {}
        password = cleaned.get("password")
        if password and password != cleaned.get("password_repeat"):
            self.add_error("password_repeat", _("The two passwords do not match."))
        if password:
            candidate = User(
                username=cleaned.get("username", ""),
                email=cleaned.get("email", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                password_validation.validate_password(password, candidate)
            except ValidationError as error:
                self.add_error("password", error)
        return cleaned
