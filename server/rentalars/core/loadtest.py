# SPDX-License-Identifier: GPL-3.0-or-later
"""Bulk test data and timings for the performance proof (NFA-006 to NFA-010, scenario 11).

Scenario 11 of the catalogue asks for an installation with 100 user accounts,
20,000 material items and 1,000 projects, in which

* a project with 500 lines in 20 groups opens in under one second, and
* adding a line, including its availability check, answers in under half a
  second.

Since stage 3 the installation also has a person for every account, three
crew lines in every project (20 in the big one) and a year of time entries –
20,000 of them, about what 100 people record in a year. Since stage 5 every
item has its place in a storage tree (two halls, shelves, compartments), and
the items of two main categories have an inspection every twelve months,
recorded at some day of the last 14 months – so about a fifth of them is
overdue, and the packlist of the big project has hints to show. Since
stage 6 there is also a festival: a whole project with 20 lines of its own
and three stages one after the other with 100 lines each, of which 30 are
taken over from the stage before (PRJ-044, PRJ-060).

:func:`create_load_test_data` builds that installation; :func:`measure` takes
the two timings – and those of the usual pages, which NFA-012 wants
answered in under a second, including those of personnel and time entry. The command ``measure_performance`` runs both and prints the
result (see ``docs/betrieb/betrieb.md``).

The data is written with bulk inserts, bypassing the services, because
creating 20,000 items one by one would take minutes. It is therefore only
meant for a test installation and refuses to run where real data exists.
"""

from __future__ import annotations

import datetime
import itertools
import random
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.models import Role, User
from rentalars.accounts.rights import Rights
from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.customers.models import Customer
from rentalars.masterdata.models import Category, StorageLocation, TaxRate, Unit
from rentalars.material import numbering
from rentalars.material.models import Inspection, InspectionResult, InspectionType, MaterialItem, MaterialModel
from rentalars.personnel.models import JobFunction, Person, PersonJobFunction
from rentalars.products.models import BillingMode, Product, ProductKind
from rentalars.projects import services as project_services
from rentalars.projects.models import (
    CrewLine,
    Group,
    MaterialLine,
    Project,
    ProjectStatus,
    suggested_hours,
)
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus, hours_between

#: Name of the project with 500 lines; the measurement looks it up by this name.
BIG_PROJECT_NAME = "Lasttest: Großprojekt"

#: Number of the whole project with three stages (stage 6); its parts are LT-FEST-1 to LT-FEST-3.
FESTIVAL_NUMBER = "LT-FEST"

#: Main categories the generated products are spread over.
#: ADM-011: categories of the start data.
CATEGORY_CODES = ("L", "T", "K", "R", "M")

#: Main categories whose items have an inspection (stage 5).
INSPECTED_CATEGORY_CODES = ("L", "K")

BATCH = 2000

#: The usual pages and API calls that NFA-012 wants answered in under a second.
USUAL_PAGES = (
    ("Start page", "/"),
    ("List of projects", "/projects/"),
    ("List of material items (first page of all items)", "/material/"),
    ("List of material items, searched by text", "/material/?q=Modell+7"),
    ("List of material models", "/material/models/"),
    ("List of products", "/products/"),
    ("List of customers", "/customers/"),
    ("Open shortages of all projects", "/shortages/"),
    ("Hints above the planning, fetched after every change of a line", "/projects/{project}/planning/notes/"),
    ("Packlist of the project with 500 lines", "/projects/{project}/packlist/"),
    (
        "Packlist of the project with 500 lines in the order of the storage places",
        "/projects/{project}/packlist/?order=location",
    ),
    ("Price overview of the project with 500 lines", "/projects/{project}/prices/"),
    ("Search for a word across everything", "/search/?q=Lasttest"),
    ("API: list of material items", "/api/v1/material-items"),
    ("API: list of projects", "/api/v1/projects"),
    ("API: list of products with their stock", "/api/v1/products"),
    # Stage 3: personnel and time entry.
    ("Deployment view of the project with 500 lines", "/projects/{project}/deployment/"),
    ("List of people", "/personnel/"),
    ("Availability of the people", "/personnel/availability/"),
    ("Times waiting for approval", "/times/approval/"),
    ("Hours report of the current month, all people", "/times/report/"),
    ("Hours report of the last full month, all people", "/times/report/?since={month_start}&until={month_end}"),
    ("Hours report of the last full month as CSV", "/times/report/?since={month_start}&until={month_end}&format=csv"),
    ("API: list of time entries", "/api/v1/time-entries"),
    # ZEI-019: expenses per month and person, and the list of the API.
    ("Expenses of the last full month, all people", "/times/report/expenses/?since={month_start}&until={month_end}"),
    ("API: list of expenses", "/api/v1/expenses"),
    ("API: list of people", "/api/v1/people"),
    # Stage 4: overviews over weeks and the correspondence.
    ("Calendar of the month", "/schedule/?month={month}"),
    ("Timeline of four weeks", "/schedule/timeline/?from={week_start}&weeks=4"),
    ("Personnel plan of two weeks, all people", "/schedule/personnel/?from={week_start}&weeks=2"),
    # VFG-029: the utilization opens with days in hours now; "weeks" keeps this the page of two weeks.
    ("Utilization of a category, two weeks", "/schedule/products/?category={category}&from={week_start}&weeks=2"),
    ("Projects with open items", "/projects/open-items/"),
    ("Course of the project with 500 lines", "/projects/{project}/course/"),
    ("Self-check of the installation", "/administration/self-check/"),
    ("API: calendar of four weeks", "/api/v1/calendar?from={week_start}&weeks=4"),
    # Stage 5: lists with chosen columns, the week, timelines, documents (NFA-044).
    ("Calendar of the week of the big project", "/schedule/?view=week&week={week_start}"),
    ("List of material items with all columns", "/material/?cols=all"),
    ("List of products with all columns", "/products/?cols=all"),
    ("List of products as CSV, all columns", "/products/?cols=all&format=csv"),
    ("Timeline of a product, eight weeks", "/products/{product}/timeline/?from={week_start}&weeks=8"),
    ("Timeline of a material item, eight weeks", "/material/items/{item}/timeline/?from={week_start}&weeks=8"),
    ("Timeline of a person, eight weeks", "/personnel/people/{person}/timeline/?from={week_start}&weeks=8"),
    ("Inspections of all items", "/material/inspections/"),
    # Documents and files on one tab (PRJ-079).
    ("Documents and files of the project with 500 lines", "/projects/{project}/documents/"),
    ("API: timeline of a product", "/api/v1/products/{product}/timeline?from={week_start}&weeks=8"),
    # Additions that came up in use.
    ("Changes of the project page, asked every 20 seconds", "/changes/?keys=notifications,project:{project_pk}"),
    ("Timeline of two days in hours", "/schedule/timeline/?from={week_start}&days=2"),
    ("Personnel plan of one day in hours, all people", "/schedule/personnel/?from={week_start}&days=1"),
    # The material utilization in the same days view (VFG-029), ten days in six-hour columns.
    (
        "Utilization of a category, ten days in hours",
        "/schedule/products/?category={category}&from={week_start}&days=10",
    ),
    ("Availability calendar of a person", "/personnel/people/{person}/availability/"),
    ("Project templates", "/projects/templates/"),
    ("Access log", "/administration/access-log/"),
    ("Mail log", "/administration/mail/log/"),
    # Additions that came up in use.
    ("List of projects with all columns, sums included", "/projects/?cols=all"),
    # What the app takes along to work without network (PCK-026) – every confirmed project not finished.
    ("API: packlists for the app without network", "/api/v1/offline/packlists"),
    # PRJ-090: the list of the service cases, in the browser and through the API.
    ("List of service cases", "/projects/service-cases/"),
    ("API: list of service cases", "/api/v1/service-cases"),
    # UIX-010: the chat of the big project, and the question of every project page with the chat.
    ("Chat of the project with 500 lines", "/projects/{project}/chat/"),
    (
        "Changes of a project page with its chat, asked every 20 seconds",
        "/changes/?keys=notifications,project:{project_pk},chat:{project_pk}",
    ),
    ("API: chat of the project", "/api/v1/projects/{project_pk}/chat"),
    # VFG-034: Planning → Follow-ups, every follow-up as a table – with all columns, and grouped by user.
    ("Follow-ups of all projects, all columns", "/schedule/follow-ups/?cols=all"),
    ("Follow-ups of all projects, grouped by user", "/schedule/follow-ups/?group=user"),
)

#: Stage 6: the pages of a whole project with three stages of 100 lines (PRJ-046, PRJ-048, PRJ-060). They
#: look at every part, so their queries grow with the number of parts – never with the number of lines.
FAMILY_PAGES = (
    ("Whole project with three stages: overview of the parts", "/projects/{festival}/parts/"),
    ("Whole project with three stages: planning of a stage with lines taken over", "/projects/{festival_part}/"),
    ("Whole project with three stages: price overview with all parts", "/projects/{festival}/prices/"),
    ("Whole project with three stages: packlist of all parts", "/projects/{festival}/packlist/family/"),
    ("API: whole project with three stages", "/api/v1/projects/{festival_pk}/family"),
)


def page_path(path: str, project: Project) -> str:
    """Fill in the placeholders of a path of :data:`USUAL_PAGES`.

    The big project, the last full month, the month and the Monday of the
    big project's start, and the category with the most products; for the
    timelines a product of the big project, one of its items and a person
    with deployments.
    """
    this_month = timezone.localdate().replace(day=1)
    month_end = this_month - datetime.timedelta(days=1)
    start = timezone.localtime(project.start).date()
    week_start = start - datetime.timedelta(days=start.weekday())
    category = Category.objects.filter(code=CATEGORY_CODES[0]).values_list("pk", flat=True).first() or ""
    product = project.material_lines.filter(product__isnull=False).values_list("product_id", flat=True).first() or ""
    item = MaterialItem.objects.filter(material_model__default_product_id=product).values_list("pk", flat=True).first()
    person = Person.objects.filter(crew_lines__isnull=False).values_list("pk", flat=True).first() or ""
    festival = (
        Project.objects.filter(number=FESTIVAL_NUMBER).values_list("pk", flat=True).first() or ""
        if "{festival_pk}" in path
        else ""
    )
    return path.format(
        project=project.number,  # the readable address (UIX-024)
        project_pk=project.pk,
        festival=FESTIVAL_NUMBER,
        festival_part=f"{FESTIVAL_NUMBER}-2",
        festival_pk=festival,
        product=product,
        item=item or "",
        person=person,
        month_start=month_end.replace(day=1).isoformat(),
        month_end=month_end.isoformat(),
        month=start.strftime("%Y-%m"),
        week_start=week_start.isoformat(),
        category=category,
    )


#: Pages measured as one of the people with a user account: what the crew opens.
OWN_PAGES = (
    ("Start page with one's own deployments", "/"),
    ("One's own times of the week", "/times/"),
    ("Quick time entry dialog", "/times/quick/"),
    # ZEI-019
    ("One's own expenses of the month", "/times/expenses/"),
    ("Expense dialog", "/times/expenses/new/"),
    # PRJ-108
    ("One's own service cases", "/me/service-cases/"),
)


@dataclass(frozen=True)
class LoadTestSize:
    """How much data to create. The defaults are the numbers of scenario 11."""

    users: int = 100
    items: int = 20_000
    projects: int = 1_000
    products: int = 400
    customers: int = 200
    lines_per_project: int = 10
    big_project_lines: int = 500
    big_project_groups: int = 20
    crew_lines_per_project: int = 3
    big_project_crew_lines: int = 20
    time_entries: int = 20_000


@dataclass
class Timing:
    """One measured step."""

    label: str
    seconds: float
    limit_seconds: float
    queries: int

    @property
    def ok(self) -> bool:
        """Whether the step stayed below its limit."""
        return self.seconds < self.limit_seconds


def create_load_test_data(size: LoadTestSize | None = None, *, force: bool = False) -> dict[str, int]:
    """Fill the database with the amount of data scenario 11 describes.

    Args:
        size: How much to create; default is the full size of the scenario.
        force: Create the data even though the installation already has
            customers or projects.

    Returns:
        How many records of each kind were created.

    Raises:
        ValidationError: The installation already has data and ``force`` is
            not set. Load test data must never be mixed into real data by
            accident.
    """
    size = size or LoadTestSize()
    if not force and (Customer.objects.exists() or Project.objects.exists()):
        raise ValidationError(
            _("This installation already has customers or projects. Load test data belongs into a test installation.")
        )
    randomiser = random.Random(11)  # the same data on every run
    # ADM-011: the piece for renting; "Stück" in older installations.
    unit = Unit.objects.filter(name__in=("Stück (Miete)", "Stück")).order_by("-name").first()
    tax_rate = TaxRate.get_default()
    categories = {code: Category.objects.get(parent__isnull=True, code=code) for code in CATEGORY_CODES}

    with transaction.atomic():
        # Products: article numbers L-9001 … so that they never collide with real ones.
        products = []
        for index in range(size.products):
            code = CATEGORY_CODES[index % len(CATEGORY_CODES)]
            products.append(
                Product(
                    article_number=f"{code}-{9000 + index // len(CATEGORY_CODES) + 1}",
                    name=f"Lasttest-Produkt {index + 1}",
                    category=categories[code],
                    unit=unit,
                    tax_rate=tax_rate,
                    kind=ProductKind.RENTAL,
                    billing_mode=BillingMode.DAILY_PER_PIECE,
                    price=Decimal(5 + index % 40),
                )
            )
        Product.objects.bulk_create(products, batch_size=BATCH)
        products = list(Product.objects.filter(name__startswith="Lasttest-Produkt").order_by("pk"))

        # One material model per product; the items are spread evenly.
        MaterialModel.objects.bulk_create(
            [
                MaterialModel(name=f"Lasttest-Modell {index + 1}", category=product.category, default_product=product)
                for index, product in enumerate(products)
            ],
            batch_size=BATCH,
        )
        models = list(MaterialModel.objects.filter(name__startswith="Lasttest-Modell").order_by("pk"))
        places = _create_storage_places()
        first_id = NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value
        MaterialItem.objects.bulk_create(
            [
                MaterialItem(
                    inventory_number=first_id + index,
                    material_model=models[index % len(models)],
                    storage_location=places[index % len(places)],
                )
                for index in range(size.items)
            ],
            batch_size=BATCH,
        )
        inspections = _create_inspections(
            randomiser, [categories[code] for code in INSPECTED_CATEGORY_CODES], timezone.localdate()
        )
        NumberRange.ensure_next_is_above(NumberRangeKey.MATERIAL_ITEM, first_id + size.items - 1)
        numbering.reset_cache()

        role = Role.objects.filter(name="Projektleitung").first()
        users = User.objects.bulk_create(
            [
                User(
                    username=f"lasttest{index + 1:03d}", email=f"lasttest{index + 1:03d}@example.invalid", password="!"
                )
                for index in range(size.users)
            ],
            batch_size=BATCH,
        )
        if role is not None:
            users = list(User.objects.filter(username__startswith="lasttest"))
            User.roles.through.objects.bulk_create(
                [User.roles.through(user_id=user.pk, role_id=role.pk) for user in users], batch_size=BATCH
            )

        Customer.objects.bulk_create(
            [
                Customer(number=f"LT-{index + 1:05d}", name=f"Lasttest-Kunde {index + 1}")
                for index in range(size.customers)
            ],
            batch_size=BATCH,
        )
        customers = list(Customer.objects.filter(number__startswith="LT-").order_by("pk"))

        # Projects of three days each, spread over a year around today.
        today = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        statuses = [ProjectStatus.CONFIRMED, ProjectStatus.CONFIRMED, ProjectStatus.OPTION, ProjectStatus.INQUIRY]
        # Read back: ``bulk_create`` sets no primary keys on MariaDB.
        follow_up_users = list(User.objects.filter(username__startswith="lasttest").order_by("pk"))
        project_rows = []
        for index in range(size.projects):
            start = today + datetime.timedelta(days=index % 365 - 30)
            project_rows.append(
                Project(
                    number=f"LT-{index + 1:05d}",
                    name=f"Lasttest-Projekt {index + 1}",
                    customer=customers[index % len(customers)],
                    status=statuses[index % len(statuses)],
                    start=start,
                    end=start + datetime.timedelta(days=3),
                    rental_days=2,
                    # VFG-034, PRJ-109: every tenth project has a follow-up, every other one with a time.
                    **(
                        {
                            "follow_up_on": (start - datetime.timedelta(days=7)).date(),
                            "follow_up_at": datetime.time(9 + index % 8, 30) if index % 20 == 0 else None,
                            "follow_up_user": follow_up_users[index % len(follow_up_users)]
                            if follow_up_users
                            else None,
                            "follow_up_note": "Angebot nachfassen",
                        }
                        if index % 10 == 0
                        else {}
                    ),
                )
            )
        big_start = today + datetime.timedelta(days=10)
        project_rows.append(
            Project(
                number="LT-GROSS",
                name=BIG_PROJECT_NAME,
                customer=customers[0],
                status=ProjectStatus.CONFIRMED,
                start=big_start,
                end=big_start + datetime.timedelta(days=3),
                rental_days=2,
            )
        )
        Project.objects.bulk_create(project_rows, batch_size=BATCH)
        project_rows = list(Project.objects.filter(number__startswith="LT-").exclude(number="LT-GROSS").order_by("pk"))
        big_project = Project.objects.get(number="LT-GROSS")

        defaults = {product.pk: project_services.defaults_from_product(product) for product in products}

        def line(project: Project, product: Product, position: int, group: Group | None = None) -> MaterialLine:
            return MaterialLine(
                project=project,
                group=group,
                product=product,
                quantity=Decimal(randomiser.randint(1, 4)),
                start=project.start,
                end=project.end,
                position=position,
                **defaults[product.pk],
            )

        lines = []
        for project in project_rows:
            for position, product in enumerate(
                randomiser.sample(products, min(size.lines_per_project, len(products))), 1
            ):
                lines.append(line(project, product, position))
        Group.objects.bulk_create(
            [
                Group(project=big_project, name=f"Teilgruppe {index + 1}", position=index + 1)
                for index in range(size.big_project_groups)
            ]
        )
        groups = list(Group.objects.filter(project=big_project).order_by("position"))
        for index in range(size.big_project_lines):
            group = groups[index % len(groups)]
            lines.append(line(big_project, products[index % len(products)], index // len(groups) + 1, group))
        MaterialLine.objects.bulk_create(lines, batch_size=BATCH)

        crew_lines, time_entries = _create_people_and_times(
            size, randomiser, project_rows, big_project, tax_rate, now=timezone.now()
        )
        expenses = _create_expenses(size, randomiser, project_rows, now=timezone.now())  # ZEI-019
        chat_messages = _create_chat(big_project, now=timezone.now())  # UIX-010
        festival_lines = _create_festival(customers[1 % len(customers)], products, defaults, randomiser, today)

    return {
        "users": size.users,
        "products": len(products),
        "material_items": size.items,
        "customers": len(customers),
        "projects": len(project_rows) + 1,
        "whole_projects_with_parts": 1,
        "subprojects": 3,
        "material_lines": len(lines) + festival_lines,
        "people": size.users,
        "crew_lines": crew_lines,
        "time_entries": time_entries,
        "expenses": expenses,
        "chat_messages": chat_messages,
        "storage_places": len(places),
        "inspections": inspections,
    }


def _create_chat(project: Project, *, now: datetime.datetime) -> int:
    """UIX-010: a busy chat in the big project – 300 messages of ten people over two weeks."""
    from rentalars.chat.models import ChatMessage

    people = list(User.objects.filter(username__startswith="lasttest").order_by("pk")[:10])
    if not people:
        return 0
    rows = [
        ChatMessage(
            project=project,
            author=people[index % len(people)],
            author_name=people[index % len(people)].username,
            text=f"Lasttest-Nachricht {index + 1}: Aufbau ab 8 Uhr, Rampe frei halten.",
            created_at=now - datetime.timedelta(minutes=(300 - index) * 67),
        )
        for index in range(300)
    ]
    ChatMessage.objects.bulk_create(rows, batch_size=BATCH)
    return len(rows)


def _create_festival(
    customer: Customer,
    products: list[Product],
    defaults: dict[int, dict[str, Any]],
    randomiser: random.Random,
    today: datetime.datetime,
) -> int:
    """A whole project with three stages one after the other (PRJ-044, PRJ-060); returns the number of lines.

    The whole project has 20 lines of its own (central power, say). Each
    stage has 100 lines; the second and third take 30 of them over from the
    stage before. Built with bulk inserts like the rest; the numbers follow
    the rule of subprojects (``LT-FEST-1`` …).
    """
    start = today + datetime.timedelta(days=40)
    whole = Project.objects.create(
        number=FESTIVAL_NUMBER,
        name="Lasttest: Stadtfest",
        customer=customer,
        status=ProjectStatus.CONFIRMED,
        start=start,
        end=start + datetime.timedelta(days=7),
        rental_days=6,
    )
    parts = [
        Project.objects.create(
            number=f"{FESTIVAL_NUMBER}-{index + 1}",
            name=f"Lasttest: Bühne {index + 1}",
            customer=customer,
            parent=whole,
            status=ProjectStatus.CONFIRMED,
            start=start + datetime.timedelta(days=2 * index),
            end=start + datetime.timedelta(days=2 * index + 2),
            rental_days=2,
        )
        for index in range(3)
    ]

    def line(project: Project, product: Product, position: int, quantity: int) -> MaterialLine:
        return MaterialLine(
            project=project,
            product=product,
            quantity=Decimal(quantity),
            start=project.start,
            end=project.end,
            position=position,
            **defaults[product.pk],
        )

    chosen = randomiser.sample(products, 120)
    rows = [line(whole, product, position, 2) for position, product in enumerate(chosen[100:], 1)]
    rows += [line(parts[0], product, position, 2) for position, product in enumerate(chosen[:100], 1)]
    MaterialLine.objects.bulk_create(rows, batch_size=BATCH)
    count = len(rows)
    for earlier, later in itertools.pairwise(parts):
        sources = list(earlier.material_lines.order_by("position")[:30])
        taken = [line(later, source.product, position, 2) for position, source in enumerate(sources, 1)]
        for row, source in zip(taken, sources, strict=True):
            row.taken_over_from = source
        own = [line(later, product, position, 2) for position, product in enumerate(chosen[30:100], 31)]
        MaterialLine.objects.bulk_create(taken + own, batch_size=BATCH)
        count += len(taken) + len(own)
    return count


def _create_storage_places() -> list[StorageLocation]:
    """Two halls with ten shelves of ten compartments each: the 200 compartments."""
    halls = [StorageLocation.objects.create(name=f"Lasttest-Halle {name}") for name in "AB"]
    StorageLocation.objects.bulk_create(
        [StorageLocation(name=f"Regal {number:02d}", parent=hall) for hall in halls for number in range(1, 11)]
    )
    shelves = StorageLocation.objects.filter(parent__in=halls).order_by("pk")
    StorageLocation.objects.bulk_create(
        [StorageLocation(name=f"Fach {number:02d}", parent=shelf) for shelf in shelves for number in range(1, 11)],
        batch_size=BATCH,
    )
    return list(StorageLocation.objects.filter(parent__parent__in=halls).order_by("pk"))


def _create_inspections(randomiser: random.Random, categories: list[Category], today: datetime.date) -> int:
    """One inspection type every twelve months for the given main categories, and the inspections of their items.

    Nine items in ten were inspected at some day of the last 14 months; with
    the tenth never inspected, about a fifth of the items is overdue.
    """
    inspection_type, _created = InspectionType.objects.get_or_create(
        name="Lasttest: Elektrische Prüfung", defaults={"interval_months": 12}
    )
    inspection_type.categories.set(categories)
    item_ids = MaterialItem.objects.filter(
        material_model__name__startswith="Lasttest-Modell", material_model__category__in=categories
    ).values_list("pk", flat=True)
    rows = [
        Inspection(
            item_id=item_id,
            inspection_type=inspection_type,
            date=today - datetime.timedelta(days=randomiser.randint(0, 425)),
            inspector="Lasttest",
            result=InspectionResult.PASSED,
        )
        for item_id in item_ids
        if randomiser.random() < 0.9
    ]
    Inspection.objects.bulk_create(rows, batch_size=BATCH)
    return len(rows)


def _create_people_and_times(
    size: LoadTestSize,
    randomiser: random.Random,
    projects: list[Project],
    big_project: Project,
    tax_rate: TaxRate,
    *,
    now: datetime.datetime,
) -> tuple[int, int]:
    """Stage 3: a person for every load-test account, crew lines and a year of time entries.

    Every person has two job functions with an hourly rate. A tenth of the
    crew places stays open (PRJ-020). The time entries lie on working days
    of the past year, one shift per person and day at most, so that none of
    them overlaps another of the same person (ZEI-011); one in a hundred
    still waits for approval, the rest is approved.

    Returns:
        The number of crew lines and of time entries created.
    """
    functions = list(JobFunction.objects.filter(is_active=True).order_by("pk"))
    if not functions:
        functions = [JobFunction.objects.create(name="Lasttest-Funktion")]
    users = list(User.objects.filter(username__startswith="lasttest").order_by("username"))
    Person.objects.bulk_create(
        [
            Person(first_name="Lasttest", last_name=f"Person {index + 1:03d}", user=user)
            for index, user in enumerate(users)
        ],
        batch_size=BATCH,
    )
    people = list(Person.objects.filter(first_name="Lasttest").order_by("last_name"))
    own_functions = {person.pk: randomiser.sample(functions, min(2, len(functions))) for person in people}
    PersonJobFunction.objects.bulk_create(
        [
            PersonJobFunction(
                person=person,
                job_function=function,
                hourly_rate=Decimal(20 + randomiser.randint(0, 20)),
                valid_from=datetime.date(2020, 1, 1),
            )
            for person in people
            for function in own_functions[person.pk]
        ],
        batch_size=BATCH,
    )

    def crew_line(project: Project, position: int) -> CrewLine:
        person = None if randomiser.random() < 0.1 else randomiser.choice(people)
        function = own_functions[person.pk][0] if person else randomiser.choice(functions)
        return CrewLine(
            project=project,
            job_function=function,
            person=person,
            start=project.start,
            end=project.end,
            planned_hours=suggested_hours(project.start, project.end),
            position=position,
            title=function.name,
            unit_price=Decimal("45.00"),
            tax_rate=tax_rate,
            hourly_rate=Decimal("30.00") if person else None,
        )

    crew = [
        crew_line(project, position) for project in projects for position in range(1, size.crew_lines_per_project + 1)
    ]
    crew += [crew_line(big_project, position) for position in range(1, size.big_project_crew_lines + 1)]
    CrewLine.objects.bulk_create(crew, batch_size=BATCH)

    # Working days of the past year, newest first; one shift per person and day.
    days = [
        (now - datetime.timedelta(days=offset)).replace(hour=8, minute=0, second=0, microsecond=0)
        for offset in range(1, 400)
        if (now - datetime.timedelta(days=offset)).weekday() < 5
    ]
    entries = []
    for index in range(size.time_entries):
        person = people[index % len(people)]
        day = days[(index // len(people)) % len(days)]
        start = day + datetime.timedelta(minutes=30 * randomiser.randint(0, 4))
        end = start + datetime.timedelta(hours=randomiser.randint(4, 10))
        waiting = index % 100 == 0
        entries.append(
            TimeEntry(
                person=person,
                project=projects[index % len(projects)],
                job_function=own_functions[person.pk][0],
                start=start,
                end=end,
                break_minutes=30,
                hours=hours_between(start, end, 30),
                hourly_rate=Decimal("30.00"),
                status=TimeEntryStatus.SUBMITTED if waiting else TimeEntryStatus.APPROVED,
                submitted_at=end,
                decided_at=None if waiting else end,
            )
        )
    TimeEntry.objects.bulk_create(entries, batch_size=BATCH)
    return len(crew), len(entries)


def _create_expenses(
    size: LoadTestSize, randomiser: random.Random, projects: list[Project], *, now: datetime.datetime
) -> int:
    """ZEI-019: one expense for every ten time entries, over the past year; returns how many.

    Most are approved, those older than two months reimbursed, one in a
    hundred waits for approval; every fifth is a trip by kilometre.
    """
    from rentalars.timetracking.models import Expense, ExpenseKind

    people = list(Person.objects.filter(user__username__startswith="lasttest").order_by("pk"))
    if not people or not projects:
        return 0
    kinds = [ExpenseKind.MEALS, ExpenseKind.PARKING, ExpenseKind.LODGING, ExpenseKind.OTHER]
    rows = []
    for index in range(size.time_entries // 10):
        day = (now - datetime.timedelta(days=1 + index % 365)).date()
        waiting = index % 100 == 0
        by_kilometre = index % 5 == 0
        kilometres = Decimal(randomiser.randint(10, 300)) if by_kilometre else None
        paid_out = not waiting and (now.date() - day).days > 60
        rows.append(
            Expense(
                person=people[index % len(people)],
                project=projects[index % len(projects)],
                kind=ExpenseKind.TRAVEL if by_kilometre else kinds[index % len(kinds)],
                date=day,
                kilometres=kilometres,
                km_rate=Decimal("0.30") if by_kilometre else None,
                amount=kilometres * Decimal("0.30") if kilometres else Decimal(randomiser.randint(5, 120)),
                note=f"Lasttest {index}",
                status=TimeEntryStatus.SUBMITTED if waiting else TimeEntryStatus.APPROVED,
                reimbursed_on=day + datetime.timedelta(days=30) if paid_out else None,
            )
        )
    Expense.objects.bulk_create(rows, batch_size=BATCH)
    return len(rows)


def _timed(label: str, limit_seconds: float, action: Any, repeat: int, keep: str = "slowest") -> Timing:
    """Run ``action`` ``repeat`` times and keep the slowest (or the fastest) run.

    One run before the stopwatch starts is not counted: the very first call
    after a start reads templates from disk and fills caches. A server does
    that once per start, not once per click.
    """
    action()
    runs: list[tuple[float, int]] = []
    for _attempt in range(repeat):
        with CaptureQueriesContext(connection) as context:
            started = time.perf_counter()
            action()
            elapsed = time.perf_counter() - started
        runs.append((elapsed, len(context)))
    seconds, queries = max(runs) if keep == "slowest" else min(runs)
    return Timing(label, seconds, limit_seconds, queries)


def measure(*, repeat: int = 3, host: str = "localhost", keep: str = "slowest") -> list[Timing]:
    """Take the timings of scenario 11 on the data in the database.

    The pages are requested in-process through Django's test client: routing,
    rights check, database queries and template rendering are all included;
    only the network and NGINX are not. Each step runs ``repeat`` times and
    the *slowest* run counts – that is what a user may meet.

    ``keep="fastest"`` is for the automatic tests: they are to notice when
    the code has become slow, and must not fail because the machine that
    runs them was busy for a moment.

    The lines that are added for the measurement are removed again afterwards.

    Raises:
        ValidationError: The big project of the load test data is missing.
    """
    project = Project.objects.filter(name=BIG_PROJECT_NAME).first()
    if project is None:
        raise ValidationError(_("The load test data is missing. Run create_load_test_data first."))
    user = User.objects.filter(is_superuser=True, is_active=True).first()
    if user is None:
        user = User.objects.create_user("lasttest-admin", "lasttest-admin@example.invalid", None, is_superuser=True)
    # On a server the application only answers requests that arrived by HTTPS;
    # NGINX tells it so through this header (see deploy/nginx/rentalars-proxy.conf).
    client = Client(HTTP_HOST=host, HTTP_X_FORWARDED_PROTO="https")
    client.force_login(user)
    product = Product.objects.filter(name__startswith="Lasttest-Produkt").order_by("pk").first()
    rights = Rights.everything()

    def open_project() -> None:
        response = client.get(f"/projects/{project.pk}/")
        if response.status_code != 200:
            raise ValidationError(f"GET /projects/{project.pk}/ answered {response.status_code}")

    def open_planning_api() -> None:
        response = client.get(f"/api/v1/projects/{project.pk}/planning")
        if response.status_code != 200:
            raise ValidationError(f"GET planning answered {response.status_code}")

    # Everything with a higher ID was added by the measurement and is removed at the end.
    newest_line_before = MaterialLine.objects.order_by("-pk").values_list("pk", flat=True).first() or 0

    def add_line() -> None:
        project_services.add_line(project, rights=rights, product=product, quantity=1)

    def add_line_in_browser() -> None:
        response = client.post(
            f"/projects/{project.pk}/lines/add/",
            {"product": product.pk if product else "", "quantity": "1"},
            HTTP_HX_REQUEST="true",
        )
        if response.status_code != 200:
            raise ValidationError(f"POST line answered {response.status_code}")

    def open_page(path: str) -> Any:
        def action() -> None:
            response = client.get(path)
            if response.status_code != 200:
                raise ValidationError(f"GET {path} answered {response.status_code}")

        return action

    try:
        timings = [
            _timed("Open the project with 500 lines in 20 groups (browser page)", 1.0, open_project, repeat, keep),
            _timed("Read the same project through the API (planning)", 1.0, open_planning_api, repeat, keep),
            _timed("Add a line including the availability check (service)", 0.5, add_line, repeat, keep),
            _timed(
                "Add a line in the browser (answer with the refreshed planning)", 0.5, add_line_in_browser, repeat, keep
            ),
        ]
        # NFA-012: the usual pages and API calls, each under one second.
        timings += [
            _timed(label, 1.0, open_page(page_path(path, project)), repeat, keep) for label, path in USUAL_PAGES
        ]
        if Project.objects.filter(number=FESTIVAL_NUMBER).exists():
            timings += [
                _timed(label, 1.0, open_page(page_path(path, project)), repeat, keep) for label, path in FAMILY_PAGES
            ]
        # The same for what a person of the crew opens, as one of them.
        crew_user = User.objects.filter(username="lasttest001", person__isnull=False).first()
        if crew_user is not None:
            client.force_login(crew_user)
            timings += [_timed(label, 1.0, open_page(path), repeat, keep) for label, path in OWN_PAGES]
    finally:
        MaterialLine.objects.filter(project=project, pk__gt=newest_line_before).delete()
    return timings
