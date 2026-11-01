# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for people: rates, job functions, absences, accounts (PER-005, PER-007, PER-029).

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.i18n import LazyCall, LocalText, format_date
from rentalars.personnel.models import Absence, JobFunction, Person, PersonJobFunction


def save_person(person: Person) -> Person:
    """Validate and save a person (PER-001)."""
    person.full_clean()
    person.save()
    return person


def set_person_active(person: Person, *, active: bool, acting_user: Any = None) -> None:
    """Deactivate a person, or bring the person back (PER-001).

    A deactivated person is no longer offered for planning and cannot record
    times or log in (AUT-026); everything recorded so far stays.

    Raises:
        ValidationError: Somebody deactivates the own account, or the last
            account with access to the settings would be lost.
    """
    from rentalars.accounts.services import set_user_active

    set_user_active(person.user, active=active, acting_user=acting_user)
    person.refresh_from_db()


def delete_person(person: Person) -> None:
    """Delete a person who was never planned and never recorded a time.

    Raises:
        ValidationError: The person has crew lines or time entries. Such a
            person is deactivated or anonymised instead (NFA-009).
    """
    from rentalars.accounts.services import _is_last_administrator

    user = person.user
    if _is_last_administrator(user):
        raise ValidationError(_("The last account with access to the settings cannot be deactivated."))
    if user.last_login is not None:
        raise ValidationError(
            _("This person has logged in already and cannot be deleted. Deactivate or anonymise the person instead.")
        )
    documents = [qualification.document for qualification in person.qualifications.all() if qualification.document]
    try:
        with transaction.atomic():
            person.delete()
            # The account goes with the person (AUT-026); it was never used.
            user.delete()
    except ProtectedError as error:
        raise ValidationError(
            _(
                "This person was scheduled for projects or recorded times and cannot be deleted. Deactivate or anonymise the person instead."
            )
        ) from error
    for document in documents:
        # The qualifications went with the person; their certificates leave the disk too (PER-014).
        document.delete(save=False)


# --- Job functions and their service products (PRD-044, PER-037) ----------------------------

#: PRD-044: the code and name of the category for service products, created only if an installation has none.
SERVICE_CATEGORY = ("D", "Dienstleistung")


def service_category() -> Any:
    """The main category new service products go to (PRD-044).

    The active main category that presets the kind "service" – D first, as
    in the start data ("Veranstaltungstechnik-Dienstleistung") –, else the
    main category D whatever it presets. An installation without either gets
    a main category D "Dienstleistung" (or, with D taken, "DL"): without
    stock, presetting services by the hour.
    """
    from rentalars.masterdata.models import Category, ProductKindDefault, Unit
    from rentalars.products.models import ProductKind

    main = Category.objects.filter(parent__isnull=True)
    services = list(main.filter(is_active=True, default_product_kind=ProductKind.SERVICE).order_by("code", "pk"))
    found = next((category for category in services if category.code == SERVICE_CATEGORY[0]), None)
    found = found or (services[0] if services else None) or main.filter(code=SERVICE_CATEGORY[0]).first()
    if found is not None:
        return found
    code = SERVICE_CATEGORY[0] if not main.filter(code=SERVICE_CATEGORY[0]).exists() else "DL"
    category = main.filter(name__iexact=SERVICE_CATEGORY[1]).first()
    if category is not None:
        return category
    category = Category(
        name=SERVICE_CATEGORY[1],
        code=code,
        has_own_stock=False,
        default_product_kind=ProductKindDefault.SERVICE,
        default_unit=Unit.objects.filter(name__iexact="Stunde").first(),
    )
    category.full_clean()
    category.save()
    return category


def create_service_product(name: str, *, price: Decimal | None = None) -> Any:
    """Create the service product of a new job function: same name, next free number, by the hour (PRD-044).

    Category, tax rate and unit come from the category of services
    (:func:`service_category`); the unit is "Stunde" where the category
    presets none. Without a price the product waits for one (PER-037): its
    crew lines cost the customer 0 until it is entered.

    Raises:
        ValidationError: The installation has no tax rate yet.
    """
    from rentalars.masterdata.models import Unit
    from rentalars.products.models import DEFAULT_BILLING_MODE, BillingMode, Product, ProductKind
    from rentalars.products.services import presets_for_category

    category = service_category()
    presets = presets_for_category(category)
    billing_mode = presets["billing_mode"] if presets["kind"] == ProductKind.SERVICE else ""
    if billing_mode not in (BillingMode.HOURLY, BillingMode.EFFORT, BillingMode.FLAT, *BillingMode.daily_modes()):
        billing_mode = DEFAULT_BILLING_MODE[ProductKind.SERVICE]
    unit = (
        (presets["unit"] if presets["kind"] == ProductKind.SERVICE else None)
        or Unit.objects.filter(name__iexact="Stunde").first()
        or presets["unit"]
    )
    if presets["tax_rate"] is None or unit is None:
        raise ValidationError(
            _("Create a tax rate and a unit first: the service product of the job function needs them.")
        )
    product = Product(
        article_number=presets["article_number"],
        category=category,
        name=(name or "").strip(),
        unit=unit,
        tax_rate=presets["tax_rate"],
        kind=ProductKind.SERVICE,
        billing_mode=billing_mode,
        price=price,
    )
    product.full_clean()
    product.save()
    return product


@transaction.atomic
def save_job_function(job_function: JobFunction, *, price: Decimal | None = None) -> JobFunction:
    """Validate and save a job function together with its service product (PRD-044).

    A new function gets its service product of the same name – with
    ``price`` as its price per hour, if given. A function that is renamed
    renames its product along, as long as the two had the same name.

    Raises:
        ValidationError: A rule of the function or of the new product is violated.
    """
    old_name = (
        JobFunction.objects.filter(pk=job_function.pk).values_list("name", flat=True).first()
        if job_function.pk
        else None
    )
    job_function.full_clean()
    if job_function.service_product_id is None:
        job_function.service_product = create_service_product(job_function.name, price=price)
    job_function.save()
    product = job_function.service_product
    if old_name and old_name != job_function.name and product.name == old_name:
        product.name = job_function.name
        product.full_clean()
        product.save()
    return job_function


def delete_job_function(job_function: JobFunction) -> None:
    """Delete a job function nobody has and nobody was planned in – with its service product (PRD-044).

    Raises:
        ValidationError: People have the function, it was planned or times
            were recorded in it, or its service product is planned as a
            material line of a project. Such a function is deactivated.
    """
    product = job_function.service_product
    try:
        with transaction.atomic():
            job_function.delete()
            product.delete()
    except ProtectedError as error:
        raise ValidationError(
            _("This job function is in use: people have it or it was planned. Deactivate it instead.")
        ) from error


# --- Job functions and rates (PER-005, PER-007, PER-029) --------------------------


def job_functions_of(person: Person) -> list[JobFunction]:
    """Return the job functions a person is assigned to, by name (PER-005)."""
    return list(JobFunction.objects.filter(rates__person=person).distinct().order_by("name"))


def has_job_function(person: Person, job_function: JobFunction) -> bool:
    """Whether a person is assigned to a job function (PER-006)."""
    return PersonJobFunction.objects.filter(person=person, job_function=job_function).exists()


def _day(at: datetime.date | datetime.datetime | None) -> datetime.date:
    """A day from a day, a moment (its local day) or nothing (today)."""
    if at is None:
        return timezone.localdate()
    if isinstance(at, datetime.datetime):
        return timezone.localtime(at).date() if timezone.is_aware(at) else at.date()
    return at


def applicable_row(rows: list[PersonJobFunction], day: datetime.date) -> PersonJobFunction | None:
    """The rate row of one person and job function that applies on a day (PER-007, PER-029).

    * The row with the latest "valid from" that is not after the day;
    * else the row without "valid from", which counts from always;
    * else – all rows begin later – the earliest one: somebody whose first
      rate is entered "from next month" still has a rate for a job tomorrow.

    The row applies as a whole: an empty rate in it means "no own rate",
    not "the rate of the row before".
    """
    if not rows:
        return None
    dated = sorted(
        (row for row in rows if row.valid_from is not None), key=lambda row: row.valid_from or datetime.date.min
    )
    begun = [row for row in dated if (row.valid_from or datetime.date.min) <= day]
    if begun:
        return begun[-1]
    undated = [row for row in rows if row.valid_from is None]
    if undated:
        return undated[0]
    return dated[0]


@dataclass(frozen=True)
class Rate:
    """What an hour and a day of a person in a job function cost on a day (PER-007, PER-009, PER-029).

    ``hourly`` and ``daily`` are the rates to calculate with: the person's
    own, else the guide value of the job function (PRJ-052), else ``None``.
    ``own_hourly`` and ``own_daily`` are the person's own only.
    """

    hourly: Decimal | None
    daily: Decimal | None
    own_hourly: Decimal | None = None
    own_daily: Decimal | None = None
    #: PER-035: the rate of an hour beyond the limit of hours per day; see :meth:`RateBook.rate`.
    above_limit: Decimal | None = None
    own_above_limit: Decimal | None = None
    #: The person is assigned to the job function (PER-005); else only the guide values count.
    assigned: bool = False
    #: The "valid from" of the row that applies; ``None`` for a row that counts from always.
    valid_from: datetime.date | None = None

    @property
    def hourly_is_guide(self) -> bool:
        """The hourly rate is the guide value of the job function, not the person's own."""
        return self.own_hourly is None and self.hourly is not None

    @property
    def daily_is_guide(self) -> bool:
        """The day rate is the guide value of the job function, not the person's own."""
        return self.own_daily is None and self.daily is not None


class RateBook:
    """The rate rows of some people, read with one query, for finding many rates (PER-029).

    For the costs of many crew lines at once::

        book = RateBook([line.person_id for line in lines])
        for line in lines:
            rate = book.rate(line.person_id, line.job_function, line.start)
    """

    def __init__(self, people: Iterable[int]) -> None:
        self.rows: dict[tuple[int, int], list[PersonJobFunction]] = defaultdict(list)
        ids = {pk for pk in people if pk is not None}
        if ids:
            for row in PersonJobFunction.objects.filter(person_id__in=ids):
                self.rows[(row.person_id, row.job_function_id)].append(row)

    def rate(
        self, person_id: int | None, job_function: JobFunction, at: datetime.date | datetime.datetime | None = None
    ) -> Rate:
        """The :class:`Rate` of a person – or of an open place, ``person_id=None`` – in a job function on a day.

        PER-035: the rate from the limit is the person's own; a person with an
        own hourly rate but none from the limit costs that hourly rate beyond
        the limit too. Without own hourly rate the guide value from the limit
        of the function counts, else its guide value per hour.
        """
        row = applicable_row(self.rows.get((person_id, job_function.pk), []), _day(at)) if person_id else None
        own_hourly = row.hourly_rate if row is not None else None
        own_daily = row.daily_rate if row is not None else None
        own_above = row.hourly_rate_above_limit if row is not None else None
        hourly = own_hourly if own_hourly is not None else job_function.guide_cost_rate
        if own_above is not None:
            above = own_above
        elif own_hourly is not None:
            above = own_hourly
        else:
            guide_above = job_function.guide_cost_rate_above_limit
            above = guide_above if guide_above is not None else hourly
        return Rate(
            hourly=hourly,
            daily=own_daily if own_daily is not None else job_function.guide_daily_cost_rate,
            own_hourly=own_hourly,
            own_daily=own_daily,
            above_limit=above,
            own_above_limit=own_above,
            assigned=row is not None,
            valid_from=row.valid_from if row is not None else None,
        )


def rate_for(
    person: Person | None, job_function: JobFunction, at: datetime.date | datetime.datetime | None = None
) -> Rate:
    """What an hour and a day of a person in a job function cost on a day – for the costs (PER-029).

    The rates of the row that applies on the day (:func:`applicable_row`);
    a rate the person does not have – no row, or the row leaves it empty –
    is the guide value of the job function. ``person=None`` is an open
    place: the guide values. ``at`` is a day or a moment (its local day);
    default today. One query.

    Example: Anna in sound engineering, rows "–/– always" and "35.00/280.00
    from 1 July"; guide values 30.00 an hour, 250.00 a day. On 30 June the
    rates are 30.00 and 250.00 (guide values), on 1 July 35.00 and 280.00.
    """
    return RateBook([person.pk] if person is not None else []).rate(
        person.pk if person is not None else None, job_function, at
    )


def rate_on(person: Person, job_function: JobFunction, day: datetime.date | None = None) -> Decimal | None:
    """Return the person's own hourly rate in a job function on a day (PER-007).

    The hourly rate of the row that applies (:func:`applicable_row`).

    Returns:
        The rate, or ``None`` if the person is not assigned to the function
        or has no own hourly rate there (PER-029). For the costs use
        :func:`rate_for`, which falls back to the guide value.

    Example: rates 35.00 from 1 January and 38.00 from 1 July. On 30 June
    the answer is 35.00, on 1 July 38.00.
    """
    return rate_for(person, job_function, day).own_hourly


def current_rates(person: Person, day: datetime.date | None = None) -> list[PersonJobFunction]:
    """Return, for each job function of a person, the rate row that applies on a day (PER-007, PER-029)."""
    day = day or timezone.localdate()
    by_function: dict[int, list[PersonJobFunction]] = defaultdict(list)
    for row in person.rates.select_related("job_function"):
        by_function[row.job_function_id].append(row)
    result = [applicable_row(rows, day) for rows in by_function.values()]
    return sorted((row for row in result if row is not None), key=lambda row: row.job_function.name.lower())


def rate_history(person: Person) -> list[PersonJobFunction]:
    """All rate rows of a person: by job function, the row without a date first, then by date (PER-007)."""
    return sorted(
        person.rates.select_related("job_function"),
        key=lambda row: (
            row.job_function.name.lower(),
            row.valid_from is not None,
            row.valid_from or datetime.date.min,
        ),
    )


def set_rate(
    person: Person,
    job_function: JobFunction,
    hourly_rate: Decimal | None = None,
    valid_from: datetime.date | None = None,
    *,
    daily_rate: Decimal | None = None,
    hourly_rate_above_limit: Decimal | None = None,
) -> PersonJobFunction:
    """Assign a job function to a person, or give it new rates from a day on (PER-005, PER-007, PER-029).

    Both rates are optional, and so is the day: without ``valid_from`` the
    rates count from always (the row without a date). Rates for a day that
    already has a row replace that row's rates (a typo is corrected); any
    other day adds a row, and the older rows stay as the history. PER-035:
    ``hourly_rate_above_limit`` is the cost of an hour beyond the limit of
    hours per day of the service product.

    Existing crew lines and time entries keep the rate they were created
    with (PRJ-021, ZEI-008).
    """
    rows = PersonJobFunction.objects.filter(person=person, job_function=job_function)
    row = (rows.filter(valid_from=valid_from) if valid_from else rows.filter(valid_from__isnull=True)).first()
    if row is None:
        row = PersonJobFunction(person=person, job_function=job_function, valid_from=valid_from)
    row.hourly_rate = hourly_rate
    row.daily_rate = daily_rate
    row.hourly_rate_above_limit = hourly_rate_above_limit
    row.full_clean()
    row.save()
    return row


def assign_job_function(person: Person, job_function: JobFunction) -> bool:
    """Give a person a job function without own rates, if it does not have it yet (PER-005, PER-029).

    This is what someone may do who plans people but does not see their
    costs (AUT-019): the guide values of the function count. Rates the person
    has in that function stay untouched. Returns whether it was new.
    """
    if PersonJobFunction.objects.filter(person=person, job_function=job_function).exists():
        return False
    set_rate(person, job_function)
    return True


def has_own_rates(person: Person, job_function: JobFunction) -> bool:
    """Whether a person has an hourly or day rate of its own in a job function, on any day (PER-029)."""
    return (
        PersonJobFunction.objects.filter(person=person, job_function=job_function)
        .exclude(hourly_rate__isnull=True, daily_rate__isnull=True, hourly_rate_above_limit__isnull=True)
        .exists()
    )


@transaction.atomic
def remove_job_function(person: Person, job_function: JobFunction) -> None:
    """Take a job function away from a person, with all its rates (PER-005).

    Crew lines and time entries in that function stay as they are; the
    person just cannot be planned in it any more (PER-006).
    """
    for row in PersonJobFunction.objects.filter(person=person, job_function=job_function):
        row.delete()


# --- Absences (PER-011, PER-012) ---------------------------------------------------


def save_absence(absence: Absence) -> list[str]:
    """Validate and save an absence; return warnings that do not block saving.

    Returns:
        A warning for every crew line of the person that falls into the
        absence – the planner must know, but the absence is a fact and is
        saved all the same (PRJ-022).
    """
    absence.full_clean()
    absence.save()
    from rentalars.projects.models import CrewLine, ProjectStatus

    clashes = (
        CrewLine.objects.filter(person=absence.person, start__lt=absence.end, end__gt=absence.start)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .select_related("project", "job_function")
    )
    return [
        _("%(person)s is scheduled for %(project)s as %(function)s during this time.")
        % {"person": absence.person.name, "project": line.project, "function": line.job_function}
        for line in clashes
    ]


# --- Qualifications (PER-014) ------------------------------------------------------------------


def save_qualification(qualification: Any, *, document: Any = None) -> Any:
    """Check and store a qualification, with the scan of its certificate if given (PER-014).

    Without an expiry date, a type with a validity ("first aid: 24 months")
    suggests one from the date it was acquired.

    Raises:
        ValidationError: The person already has this qualification, the dates
            do not fit, or the file is not accepted (NFA-007).
    """
    from rentalars.core.uploads import validate_document_upload
    from rentalars.material.inspections import add_months
    from rentalars.personnel.models import Qualification

    kind = qualification.qualification_type
    if qualification.valid_until is None and qualification.acquired_on and kind.validity_months:
        qualification.valid_until = add_months(qualification.acquired_on, kind.validity_months)
    duplicate = Qualification.objects.filter(
        person_id=qualification.person_id, qualification_type_id=qualification.qualification_type_id
    ).exclude(pk=qualification.pk)
    if duplicate.exists():
        raise ValidationError(
            {"qualification_type": _("%(person)s already has this qualification; change it there.")
             % {"person": qualification.person}}
        )  # fmt: skip
    if document:
        validate_document_upload(document)
    qualification.full_clean(exclude=["document"])
    with transaction.atomic():
        if document:
            if qualification.document:
                qualification.document.delete(save=False)
            qualification.document_name = (document.name or "nachweis")[:255]
            qualification.document.save(document.name, document, save=False)
        qualification.save()
    return qualification


def delete_qualification(qualification: Any) -> None:
    """Remove a qualification and the stored certificate."""
    if qualification.document:
        qualification.document.delete(save=False)
    qualification.delete()


def check_expiring_qualifications() -> int:
    """Tell personnel planning – and the person – once when a qualification is about to expire (PER-014).

    "About to" means within :attr:`Qualification.SOON_DAYS` days, or already
    expired. Each qualification and expiry date is reported once; a renewed
    certificate (a new date) is reported again when its time comes. Returns
    how many were reported now.
    """
    from rentalars.notifications.models import DueNotice, Kind
    from rentalars.notifications.services import notify, personnel_planners
    from rentalars.personnel.models import Qualification

    limit = timezone.localdate() + datetime.timedelta(days=Qualification.SOON_DAYS)
    due = list(
        Qualification.objects.filter(valid_until__isnull=False, valid_until__lte=limit, person__is_active=True)
        .select_related("person__user", "qualification_type")
        .order_by("valid_until")
    )
    keys = {f"qualification:{item.pk}:{item.valid_until.isoformat()}": item for item in due}
    known = set(DueNotice.objects.filter(key__startswith="qualification:").values_list("key", flat=True))
    stale = [key for key in known if key not in keys]
    for start in range(0, len(stale), 500):
        DueNotice.objects.filter(key__in=stale[start : start + 500]).delete()
    new = [(key, item) for key, item in keys.items() if key not in known]
    if not new:
        return 0
    planners = personnel_planners()
    for key, item in new:
        DueNotice.objects.get_or_create(key=key)
        expired = item.valid_until < timezone.localdate()
        # UIX-029: written for each recipient in his language.
        title = LocalText(
            gettext_lazy("Expired: %(qualification)s of %(person)s")
            if expired
            else gettext_lazy("Expires on %(date)s: %(qualification)s of %(person)s"),
            qualification=item.qualification_type.name,
            person=item.person.name,
            date=LazyCall(format_date, item.valid_until),
        )
        notify(
            planners,
            Kind.QUALIFICATION_EXPIRY,
            title,
            url=reverse("personnel:person_detail", args=[item.person_id]) + "#qualifications",
        )
        if item.person.user_id and item.person.user not in planners:
            notify(
                [item.person.user],
                Kind.QUALIFICATION_EXPIRY,
                title,
                url=reverse("personnel:own_profile") + "#qualifications",
            )
    return len(new)
