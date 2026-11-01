# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helpers that keep the tests short and readable.

The helpers create exactly what a test names and nothing more. The start data
of a fresh installation (categories L, T, K …, units, tax rates, roles) is
already present in every test database, because it is installed after
``migrate``. The categories S, A, F and the units "Stück" and "Meter" of
older installations are created when a test first asks for them
(ADM-011).
"""

from __future__ import annotations

import contextlib
import datetime
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from unittest import TestCase as PlainTestCase
from unittest import mock
from zoneinfo import ZoneInfo

from django.apps import apps
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from rentalars.accounts.models import Role, User
from rentalars.accounts.rights import Rights
from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import SystemSettings
from rentalars.customers.models import Customer
from rentalars.customers.services import save_customer
from rentalars.masterdata.models import Category, Manufacturer, ProductKindDefault, TaxRate, Unit
from rentalars.material import numbering
from rentalars.material.models import MaterialItem, MaterialModel, TrackingMode
from rentalars.material.services import create_items
from rentalars.personnel import services as personnel_services
from rentalars.personnel.models import EmploymentKind, JobFunction, Person
from rentalars.products.models import DEFAULT_BILLING_MODE, BillingMode, Product, ProductKind
from rentalars.projects import crew as crew_services
from rentalars.projects import services as project_services
from rentalars.projects.models import CrewLine, Group, Project, ProjectStatus
from rentalars.projects.services import LineResult
from rentalars.timetracking import services as time_services
from rentalars.timetracking.models import TimeEntry

BERLIN = ZoneInfo("Europe/Berlin")

#: Rights of a user who may do everything; for tests that are not about rights.
ALL_RIGHTS = Rights.everything()

PASSWORD = "correct horse battery staple"


def at(day: int, hour: int = 0, minute: int = 0, *, month: int = 3, year: int = 2027) -> datetime.datetime:
    """Return a moment in March 2027 (Berlin time), e.g. ``at(10, 8)`` = 10 March, 08:00."""
    return datetime.datetime(year, month, day, hour, minute, tzinfo=BERLIN)


#: The moment at which every test takes place: 1 March 2027, 08:00 – shortly
#: before the projects of the examples, which run from the 10th to the 13th.
NOW = at(1, 8)

#: A moment after the work of the examples, for tests that record hours: times
#: cannot be recorded before they were worked (ZEI-022). Sunday, 28 March 2027.
LATER = at(28, 18)

#: Where the stopped clock stands; :func:`set_clock` moves it within a test.
_CLOCK = [NOW]


def _now() -> datetime.datetime:
    """The stopped clock."""
    return _CLOCK[0]


def set_clock(moment: datetime.datetime) -> None:
    """Move the stopped clock, e.g. to :data:`LATER`; every test starts again at :data:`NOW`."""
    _CLOCK[0] = moment


def clock() -> datetime.datetime:
    """Where the stopped clock stands now."""
    return _CLOCK[0]


@contextlib.contextmanager
def clock_at_least(moment: datetime.datetime) -> Iterator[None]:
    """Let the clock stand at ``moment`` for a moment, if it stands earlier, and put it back afterwards.

    For creating the data a test starts from: hours worked on 10 March are
    recorded "after" 10 March, whatever day the test itself plays on.
    """
    before = _CLOCK[0]
    _CLOCK[0] = max(before, moment)
    try:
        yield
    finally:
        _CLOCK[0] = before


def stop_the_clock(test: PlainTestCase) -> None:
    """Let ``timezone.now()`` answer :data:`NOW` for the duration of a test.

    The examples in the tests use fixed dates in March 2027. Parts of the
    application compare dates with today – the list of open shortages looks
    one year ahead, an overdue project counts as still out. Without a fixed
    "today" the same test would pass this year and fail the next.

    Two places have to be changed, because the application reaches the
    clock in two ways: by calling ``timezone.now()``, and through model
    fields that were given the function itself as their default when the
    models were loaded (``created_at``, the time stamp of the change log).
    """
    _CLOCK[0] = NOW
    test.addCleanup(set_clock, NOW)
    patcher = mock.patch("django.utils.timezone.now", _now)
    patcher.start()
    test.addCleanup(patcher.stop)
    for field in _FIELDS_DEFAULTING_TO_NOW:
        _set_default(field, _now)
        test.addCleanup(_set_default, field, _REAL_NOW)


def _set_default(field: Any, default: Any) -> None:
    """Give a model field another default; Django remembers the old one in a cache that must go too."""
    field.default = default
    field.__dict__.pop("_get_default", None)


#: The real clock, kept before any test replaces it.
_REAL_NOW = timezone.now

_FIELDS_DEFAULTING_TO_NOW = [
    field for model in apps.get_models() for field in model._meta.concrete_fields if field.default is _REAL_NOW
]


class RentalarsTestCase(TestCase):
    """Base class: an installation whose first-run setup is already done, on 1 March 2027."""

    def setUp(self) -> None:
        super().setUp()
        stop_the_clock(self)
        system_settings = SystemSettings.load()
        system_settings.setup_completed = True
        system_settings.save()
        SetupRequiredMiddleware.reset()
        numbering.reset_cache()
        # Kept results (the shortages of the start page) must not reach from one test into the next.
        cache.clear()


#: ADM-011: master data of older installations that the examples of the tests still use. New
#: installations no longer get the categories S, A and F or the units "Stück" and "Meter"; installations that
#: had them keep them. They are created the first time a test asks for them.
LEGACY_CATEGORIES = {
    "S": ("Sonstiges", True, ProductKindDefault.RENTAL, "Stück"),
    "A": ("Aufpreise", False, ProductKindDefault.SURCHARGE, "Pauschal"),
    "F": ("Fahrt/Transport", False, ProductKindDefault.INCIDENTAL, "Pauschal"),  # PRD-045
}
LEGACY_UNITS = {"Stück": "Stk.", "Meter": "m"}


def unit(name: str) -> Unit:
    """Return the unit with this name; "Stück" and "Meter" of older installations are created when needed."""
    if name in LEGACY_UNITS:
        return Unit.objects.get_or_create(name=name, defaults={"abbreviation": LEGACY_UNITS[name]})[0]
    return Unit.objects.get(name=name)


def category(code: str) -> Category:
    """Return the main category with the given code, e.g. ``category("K")``; S, A and F are created when needed."""
    if code in LEGACY_CATEGORIES:
        name, has_own_stock, kind, unit_name = LEGACY_CATEGORIES[code]
        return Category.objects.get_or_create(
            parent=None,
            code=code,
            defaults={
                "name": name,
                "has_own_stock": has_own_stock,
                "default_product_kind": kind,
                "default_unit": unit(unit_name),
            },
        )[0]
    return Category.objects.get(parent__isnull=True, code=code)


#: The role the start role "Freie Kraft" was: reads the projects it is assigned to, sees availability.
ASSIGNED_READER = "Zugeordnet lesend"


def assigned_reader_role() -> Role:
    """A role for assigned projects only, which reads them – a membership can open the planning to it (AUT-025).

    The start role "Freie Kraft" opens the overview (AUT-036); tests of memberships use this one.
    """
    from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight

    role, _created = Role.objects.get_or_create(
        name=ASSIGNED_READER,
        defaults={
            "module_levels": {
                str(Module.PROJECTS): int(Level.READ),
                str(Module.PACKING): int(Level.READ),
                str(Module.TIME_TRACKING): int(Level.WRITE),
            },
            "special_rights": [str(SpecialRight.AVAILABILITY)],
            "project_scope": ProjectScope.ASSIGNED,
        },
    )
    return role


def make_user(username: str = "anna", *, roles: tuple[str, ...] = (), superuser: bool = False) -> User:
    """Create a user who can log in with ``PASSWORD``."""
    user = User.objects.create_user(username, f"{username}@example.de", PASSWORD, is_superuser=superuser)
    if roles:
        if ASSIGNED_READER in roles:
            assigned_reader_role()
        user.roles.set(Role.objects.filter(name__in=roles))
    return user


def make_product(
    article_number: str, name: str | None = None, *, price: str | None = "10.00", **fields: Any
) -> Product:
    """Create a product; the category follows from the article number's letters."""
    code = article_number.split("-")[0]
    kind = fields.pop("kind", ProductKind.RENTAL)
    product = Product(
        article_number=article_number,
        name=name or f"Produkt {article_number}",
        category=fields.pop("category", None) or category(code),
        unit=fields.pop("unit", None) or unit("Stück"),
        tax_rate=fields.pop("tax_rate", None) or TaxRate.get_default(),
        kind=kind,
        billing_mode=fields.pop("billing_mode", DEFAULT_BILLING_MODE[kind]),
        price=Decimal(price) if price is not None else None,
        **fields,
    )
    product.full_clean()
    product.save()
    return product


def make_model(
    name: str,
    product: Product | None = None,
    *,
    category_code: str | None = None,
    manufacturer: str | None = None,
    bulk: bool = False,
) -> MaterialModel:
    """Create a material model, optionally assigned to a product."""
    model = MaterialModel(
        name=name,
        category=category(category_code) if category_code else (product.category if product else category("S")),
        default_product=product,
        manufacturer=Manufacturer.objects.get_or_create(name=manufacturer)[0] if manufacturer else None,
        tracking_mode=TrackingMode.BULK if bulk else TrackingMode.ITEMS,
    )
    model.full_clean()
    model.save()
    return model


def make_items(model: MaterialModel, count: int = 1, **fields: Any) -> list[MaterialItem]:
    """Create ``count`` items of a model with consecutive IDs."""
    return create_items(model, count, **fields)


def make_item(model: MaterialModel, inventory_number: int, **fields: Any) -> MaterialItem:
    """Create one item with a specific ID, e.g. ``make_item(rack_model, 500)``."""
    return create_items(model, 1, inventory_number=inventory_number, **fields)[0]


def make_stock(article_number: str, count: int, name: str | None = None, *, price: str = "10.00") -> Product:
    """Create a product together with one material model and ``count`` items."""
    product = make_product(article_number, name, price=price)
    model = make_model(f"Modell {article_number}", product)
    make_items(model, count)
    return product


def make_customer(name: str = "Stadtwerke Musterstadt") -> Customer:
    """Create a customer with the next customer number."""
    return save_customer(Customer(name=name))


def make_project(
    name: str = "Stadtfest",
    *,
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
    status: str = ProjectStatus.CONFIRMED,
    customer: Customer | None = None,
    **fields: Any,
) -> Project:
    """Create a project; by default confirmed and from 10 to 12 March 2027."""
    return project_services.create_project(
        name=name,
        customer=customer or Customer.objects.first() or make_customer(),
        start=start or at(10),
        end=end or at(12),
        status=status,
        **fields,
    )


def add_line(project: Project, product: Product | None, quantity: int | str = 1, **fields: Any) -> LineResult:
    """Add a material line with all rights; returns line and availability."""
    return project_services.add_line(
        project, rights=ALL_RIGHTS, product=product, quantity=Decimal(str(quantity)), **fields
    )


def add_line_before_071(project: Project, product: Product, quantity: int | str = 1, **fields: Any) -> LineResult:
    """A material line of a service – refused by the planning (PRD-044), but kept."""
    from unittest import mock

    with mock.patch("rentalars.projects.services.plannable_as_material", return_value=True):
        return add_line(project, product, quantity, **fields)


def add_group(project: Project, name: str, **fields: Any) -> Group:
    """Add a group to a project with all rights."""
    return project_services.add_group(project, rights=ALL_RIGHTS, name=name, **fields)


def ready_for_invoices(customer: Customer | None = None) -> Customer:
    """Fill in the company and customer data an electronic invoice needs (DOK-006).

    Returns the customer, created as "Stadtwerke Musterstadt" if none is given.
    """
    from rentalars.core.models import CompanyProfile

    profile = CompanyProfile.load()
    profile.name, profile.street, profile.postal_code, profile.city = (
        "Licht & Ton GmbH",
        "Hafen 1",
        "12345",
        "Musterstadt",
    )
    profile.email, profile.vat_id, profile.iban, profile.bic = (
        "info@licht-ton.example",
        "DE999999999",
        "DE02120300000000202051",
        "BYLADEM1001",
    )
    profile.bank_name, profile.register_details = "Bank", "AG Musterstadt HRB 1"
    profile.phone = "0170 1234567"
    profile.save()
    customer = customer or make_customer()
    customer.street, customer.postal_code, customer.city, customer.email = (
        "Markt 1",
        "12345",
        "Musterstadt",
        "a@b.example",
    )
    customer.save()
    return customer


# --- Personnel and time (stage 3) -------------------------------------------------


def job_function(name: str, *, price: str | None = None, guide: str | None = None) -> JobFunction:
    """Return the job function with this name; those of the start data (PER-037) exist already.

    Args:
        name: E.g. "Tontechnik".
        price: Gives the service product of the function (PRD-044: every
            function has its own, created with it) this price, billed by the
            hour (PER-008), and the name "<name>, Stunde".
        guide: The guide value for internal costs per hour (PRJ-052).
    """
    function = JobFunction.objects.filter(name=name).first() or personnel_services.save_job_function(
        JobFunction(name=name)
    )
    if price is not None:
        product = function.service_product
        product.name, product.price, product.billing_mode = f"{name}, Stunde", Decimal(price), BillingMode.HOURLY
        product.full_clean()
        product.save()
    if guide is not None:
        function.guide_cost_rate = Decimal(guide)
    function.full_clean()
    function.save()
    return function


def make_person(
    name: str = "Anna Becker",
    *,
    rates: dict[str, str] | None = None,
    user: User | None = None,
    kind: str = EmploymentKind.EMPLOYEE,
    **fields: Any,
) -> Person:
    """Create a person, e.g. ``make_person("Anna Becker", rates={"Tontechnik": "35.00"})``.

    ``rates`` assigns job functions with their hourly rates, valid from
    1 January 2027 – before the stopped clock of the tests. ``user`` links a
    user account (AUT-012).
    """
    first, _space, last = name.partition(" ")
    # Every account is a person (AUT-026): with ``user`` the person of that account gets the data.
    person = Person.objects.get(user=user) if user is not None else Person()
    for field_name, value in {"first_name": first, "last_name": last or first, "kind": kind, **fields}.items():
        setattr(person, field_name, value)
    person = personnel_services.save_person(person)
    for function_name, rate in (rates or {}).items():
        personnel_services.set_rate(person, job_function(function_name), Decimal(rate), datetime.date(2027, 1, 1))
    return person


def plan(project: Project, function: str | JobFunction, person: Person | None = None, **fields: Any) -> CrewLine:
    """Plan a person, or an open place, on a project with all rights; returns the crew line."""
    if isinstance(function, str):
        function = job_function(function)
    return crew_services.add_crew_lines(project, rights=ALL_RIGHTS, job_function=function, person=person, **fields)[0]


def record_time(
    person: Person,
    project: Project | None,
    function: str | JobFunction,
    start: datetime.datetime,
    end: datetime.datetime | None,
    *,
    approve: bool = False,
    **fields: Any,
) -> TimeEntry:
    """Record hours with all rights; ``approve=True`` hands them in and approves them.

    The clock is moved past the end for the moment of recording (ZEI-022),
    so that a test can start from times worked after its "today".
    """
    if isinstance(function, str):
        function = job_function(function)
    with clock_at_least(end or start):
        entry = time_services.create_entry(
            person=person,
            project=project,
            job_function=function,
            start=start,
            end=end,
            rights=ALL_RIGHTS,
            user=None,
            submit=fields.pop("submit", approve),
            **fields,
        )
        if approve:
            time_services.approve_entries([entry], rights=ALL_RIGHTS, user=None)
            entry.refresh_from_db()
    return entry


def make_internal_project(name: str = "Lager und Werkstatt") -> Project:
    """Create an internal project without customer, running all of 2027 (ZEI-010)."""
    return project_services.create_project(
        name=name, is_internal=True, start=at(1, month=1), end=at(31, month=12), status=ProjectStatus.CONFIRMED
    )


# --- Backups from the browser (ADM-010) ----------------------------------------------


def dumped_rows_visible() -> bool:
    """Whether a database dump made during a test can contain the test's rows.

    SQLite is copied through the test's own connection. ``mariadb-dump``
    runs in a connection of its own and cannot see rows of a test, which are
    never committed; there the dump holds the tables, but not their content.
    """
    from django.db import connection

    return connection.vendor == "sqlite"


def assert_dumped(test: PlainTestCase, sql: str, text: str) -> None:
    """Check that a dump holds ``text`` – or, where it cannot see it, at least the table of customers."""
    if dumped_rows_visible():
        test.assertIn(text, sql)
    else:
        test.assertIn("CREATE TABLE `customers_customer`", sql)
