# SPDX-License-Identifier: GPL-3.0-or-later
"""Sample data for trying things out (NFA-017, NFA-033).

Creates a small but complete world: categories with products, material with
items of several manufacturers, a rack with installed devices, a kit, some
customers, and projects in different statuses – including one with a
shortage, so that the red light and the subrental suggestion can be seen.

The data is created through the same services the application uses, so it is
valid by construction. Running the function twice does nothing the second
time.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from rentalars.accounts.rights import Rights
from rentalars.core.audit import acting_as
from rentalars.customers.models import Contact, Customer, CustomerKind
from rentalars.customers.services import save_customer
from rentalars.masterdata.models import Category, Manufacturer, ProductKindDefault, Supplier, TaxRate, Unit
from rentalars.material.models import ConnectionType, MaterialModel, TrackingMode
from rentalars.material.services import create_items, install_item
from rentalars.personnel import services as people
from rentalars.personnel.models import Absence, AbsenceKind, EmploymentKind, JobFunction, Person
from rentalars.products.models import BillingMode, Product, ProductKind, SurchargeType
from rentalars.products.services import set_kit_components
from rentalars.projects import course, crew
from rentalars.projects import services as projects
from rentalars.projects.models import GroupKind, ProjectStatus
from rentalars.timetracking import services as times

ALL_RIGHTS = Rights.everything()


#: ADM-011: main categories of the samples that the start data no longer has; created when missing.
EXTRA_CATEGORIES = {
    "S": ("Sonstiges", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    "A": ("Aufpreise", False, ProductKindDefault.SURCHARGE, "Pauschal"),
    # PRD-045: transport is incidental costs, no longer a service.
    "F": ("Fahrt/Transport", False, ProductKindDefault.INCIDENTAL, "Pauschal"),
}


def _category(code: str) -> Category:
    category = Category.objects.filter(parent__isnull=True, code=code).first()
    if category is None and code in EXTRA_CATEGORIES:
        name, has_own_stock, kind, unit_name = EXTRA_CATEGORIES[code]
        category = Category(
            name=name,
            code=code,
            has_own_stock=has_own_stock,
            default_product_kind=kind,
            default_unit=_unit(unit_name),
        )
        category.full_clean()
        category.save()
    if category is None:
        raise Category.DoesNotExist(code)
    return category


def _unit(name: str) -> Unit:
    """A unit of the start data (ADM-011)."""
    unit = Unit.objects.filter(name=name).first()
    if unit is None and name.startswith("Stück"):
        unit = Unit.objects.filter(name="Stück").first()
    if unit is None:
        raise Unit.DoesNotExist(name)
    return unit


def _product(article_number: str, name: str, price: str | None, **fields: Any) -> Product:
    """Create a product; category and defaults follow from the article number."""
    kind = fields.pop("kind", ProductKind.RENTAL)
    unit_name = fields.pop("unit", "Stück (Verkauf)" if kind == ProductKind.SALE else "Stück (Miete)")
    billing_mode = fields.pop(
        "billing_mode", BillingMode.DAILY_PER_PIECE if kind == ProductKind.RENTAL else BillingMode.FLAT
    )
    product = Product(
        article_number=article_number,
        name=name,
        category=fields.pop("category", None) or _category(article_number.split("-")[0]),
        unit=_unit(unit_name),
        tax_rate=TaxRate.get_default(),
        kind=kind,
        billing_mode=billing_mode,
        price=Decimal(price) if price is not None else None,
        **fields,
    )
    product.full_clean()
    product.save()
    return product


def _material(name: str, product: Product | None, count: int, **fields: Any) -> list[Any]:
    """Create a material model with ``count`` items."""
    manufacturer_name = fields.pop("manufacturer", None)
    item_fields = fields.pop("item_fields", {})
    model = MaterialModel(
        name=name,
        category=fields.pop("category", None) or (product.category if product else _category("S")),
        default_product=product,
        manufacturer=Manufacturer.objects.get_or_create(name=manufacturer_name)[0] if manufacturer_name else None,
        **fields,
    )
    model.full_clean()
    model.save()
    if model.tracking_mode == TrackingMode.BULK:
        return create_items(model, 1, **item_fields)
    return create_items(model, count, **item_fields)


@transaction.atomic
def create_demo_data() -> bool:
    """Create the sample data unless products other than the start data exist.

    Returns:
        ``True`` if data was created, ``False`` if the installation already
        had data of its own.
    """
    # PER-037: the start data brings the service products of its job functions – they are no data of one's own.
    if Product.objects.exclude(kind__in=(ProductKind.SUBRENTAL, ProductKind.SERVICE)).exists() or (
        Customer.objects.exists()
    ):
        return False

    with acting_as("system:demo"):
        thomann, _created = Supplier.objects.get_or_create(
            name="Musikhaus Muster", defaults={"email": "bestellung@example.de"}
        )
        # PRJ-106: contact person, address and phone of their own – the address finds the supplier's mails.
        Supplier.objects.get_or_create(
            name="Rent-All Verleih",
            defaults={"contact": "Disposition", "email": "dispo@example.de", "phone": "0221 555 01 23"},
        )
        bought = {"supplier": thomann, "purchase_date": datetime.date(2023, 4, 12)}

        # Sub-categories show the hierarchy of MAT-008.
        microphones = Category(name="Mikrofone", parent=_category("T"))
        microphones.save()
        wireless = Category(name="Funkstrecken", parent=microphones)
        wireless.save()

        xlr5 = _product("K-005", "XLR-Kabel 5 m", "1.50")
        xlr10 = _product("K-010", "XLR-Kabel 10 m", "2.00")
        schuko = _product("K-020", "Schuko-Verlängerung 10 m", "2.50")
        led = _product("L-010", "LED-Scheinwerfer RGBW", "20.00")
        moving = _product("L-020", "Moving Head Spot", "45.00")
        truss = _product("R-010", "Traverse 4-Punkt 2 m", "9.00")
        speaker = _product("T-010", "Aktivbox 12 Zoll", "35.00")
        stand = _product("S-020", "Boxenstativ", "5.00")
        mixer = _product("T-030", "Digitalmischpult 32 Kanal", "120.00")
        receiver = _product("T-050", "Funkempfänger", "25.00", category=wireless)
        rack = _product("T-500", "Funkrack 4 Kanal", "140.00", category=wireless)
        case = _product("S-600", "Zubehörcase", "8.00")
        kit = _product("T-100", "Aktivbox-Set", "40.00", kind=ProductKind.KIT, billing_mode=BillingMode.DAILY_PER_KIT)
        set_kit_components(kit, [(speaker, 1), (stand, 1), (xlr10, 1)])
        gaffa = _product("V-001", "Gaffa-Tape schwarz 50 m", None, kind=ProductKind.SALE, sale_price=Decimal("14.90"))
        # PRD-045: transport is incidental costs – planned like material, without stock.
        transport = _product("F-001", "Transport Sprinter", "95.00", kind=ProductKind.INCIDENTAL, unit="Pauschal")
        express = _product("A-001", "Expresszuschlag", "50.00", kind=ProductKind.SURCHARGE, unit="Pauschal")
        night = _product(
            "A-002",
            "Nachtzuschlag",
            None,
            kind=ProductKind.SURCHARGE,
            unit="Pauschal",
            surcharge_type=SurchargeType.PERCENT,
            surcharge_percent=Decimal("10"),
        )

        _material("Cordial CPM 5 FM", xlr5, 12, manufacturer="Cordial", item_fields=bought)
        _material("Sommer Cable Stage 22 5 m", xlr5, 8, manufacturer="Sommer Cable")
        _material("Cordial CPM 10 FM", xlr10, 14, manufacturer="Cordial", item_fields=bought)
        _material("Schuko 3G1,5 10 m", schuko, 20)
        # MAT-049: the power of one piece, a field of every model.
        _material(
            "Cameo Flat Pro 12",
            led,
            12,
            manufacturer="Cameo",
            specification="12 × 10 W RGBWA, DMX",
            power_w=Decimal("130"),
        )
        _material("Robe Pointe", moving, 6, manufacturer="Robe", power_w=Decimal("470"))
        _material("Global Truss F34 200", truss, 16, manufacturer="Global Truss")
        _material("RCF ART 712-A", speaker, 6, manufacturer="RCF", item_fields=bought)
        _material("K&M 21460", stand, 8, manufacturer="König & Meyer")
        _material("Behringer X32", mixer, 2, manufacturer="Behringer")
        receivers = _material("Sennheiser EM 300-500 G4", receiver, 6, manufacturer="Sennheiser")
        (rack_item,) = _material("Funkrack 4 HE", rack, 1)
        (case_item,) = _material("Case Zubehör groß", case, 1)
        # Four receivers are permanently installed in the rack, one lies loosely
        # in the accessory case, one is free (MAT-036).
        for installed in receivers[:4]:
            install_item(installed, rack_item, connection_type=ConnectionType.FIXED)
        install_item(receivers[4], case_item, connection_type=ConnectionType.LOOSE)
        _material("Gaffa-Tape schwarz", gaffa, 1, tracking_mode=TrackingMode.BULK, item_fields={"quantity": 40})
        # Material without product shows up in the list of PRD-005.
        _material("Leiter 3-teilig", None, 2)

        town = save_customer(
            Customer(
                name="Stadt Musterstadt, Kulturamt",
                street="Rathausplatz 1",
                postal_code="12345",
                city="Musterstadt",
                email="kultur@example.de",
            )
        )
        Contact(
            customer=town,
            salutation="Frau",
            first_name="Petra",
            last_name="Sommer",
            position="Veranstaltungsleitung",
            email="p.sommer@example.de",
            phone="01234 567-12",
        ).save()
        club = save_customer(
            Customer(name="Jazzclub Beispiel e. V.", street="Hafenstraße 12", postal_code="12345", city="Musterstadt")
        )
        Contact(
            customer=club,
            first_name="Jonas",
            last_name="Weber",
            greeting_style="personal",
            position="Technik",
            phone="0100 5550123",
        ).save()
        private = save_customer(
            Customer(name="Miriam Krause", kind=CustomerKind.PRIVATE, city="Neudorf", phone="0151 5550199")
        )

        now = timezone.localtime().replace(hour=8, minute=0, second=0, microsecond=0)

        def period(days_from_now: int, length: int) -> dict[str, datetime.datetime]:
            start = now + datetime.timedelta(days=days_from_now)
            return {"start": start, "end": start + datetime.timedelta(days=length, hours=10)}

        festival = projects.create_project(
            name="Stadtfest Hauptbühne",
            customer=town,
            venue="Marktplatz Musterstadt",
            status=ProjectStatus.CONFIRMED,
            contact=town.contacts.first(),
            rental_days=2,
            **period(10, 3),
        )
        front = projects.add_group(festival, rights=ALL_RIGHTS, name="Licht Front-Traverse")
        rear = projects.add_group(festival, rights=ALL_RIGHTS, name="Licht Rear-Traverse")
        sound = projects.add_group(festival, rights=ALL_RIGHTS, name="Ton FOH")
        fog = projects.add_group(festival, rights=ALL_RIGHTS, name="Nebel und Effekte", kind=GroupKind.OPTIONAL)
        projects.add_line(festival, rights=ALL_RIGHTS, product=led, quantity=8, group=front)
        projects.add_line(festival, rights=ALL_RIGHTS, product=truss, quantity=6, group=front)
        projects.add_line(festival, rights=ALL_RIGHTS, product=moving, quantity=4, group=rear)
        projects.add_line(festival, rights=ALL_RIGHTS, product=truss, quantity=6, group=rear)
        projects.add_line(festival, rights=ALL_RIGHTS, product=kit, quantity=4, group=sound)
        projects.add_line(festival, rights=ALL_RIGHTS, product=mixer, quantity=1, group=sound)
        projects.add_line(festival, rights=ALL_RIGHTS, product=rack, quantity=1, group=sound)
        projects.add_line(festival, rights=ALL_RIGHTS, product=xlr5, quantity=12, group=sound)
        projects.add_line(festival, rights=ALL_RIGHTS, product=moving, quantity=2, group=fog)
        projects.add_line(festival, rights=ALL_RIGHTS, product=schuko, quantity=10)
        projects.add_line(festival, rights=ALL_RIGHTS, product=transport, quantity=2)
        projects.add_line(festival, rights=ALL_RIGHTS, product=gaffa, quantity=3)
        surcharge = projects.add_line(festival, rights=ALL_RIGHTS, product=night, quantity=1).line
        projects.set_surcharge_targets(surcharge, [{"type": "group", "id": front.pk}, {"type": "group", "id": rear.pk}])

        # Overlaps the festival and wants more spotlights than are left: a shortage.
        jazz = projects.create_project(
            name="Jazznacht",
            customer=club,
            venue="Jazzclub Beispiel, Hafenstraße 12",
            status=ProjectStatus.OPTION,
            **period(11, 1),
        )
        projects.add_line(jazz, rights=ALL_RIGHTS, product=led, quantity=6)
        projects.add_line(jazz, rights=ALL_RIGHTS, product=speaker, quantity=2)
        projects.add_line(jazz, rights=ALL_RIGHTS, product=express, quantity=1)

        wedding = projects.create_project(
            name="Hochzeit Krause", customer=private, venue="Gut Neudorf", status=ProjectStatus.INQUIRY, **period(24, 1)
        )
        projects.add_line(wedding, rights=ALL_RIGHTS, product=kit, quantity=2)
        projects.add_line(wedding, rights=ALL_RIGHTS, product=led, quantity=6)

        _add_phases(festival)
        _create_people_and_times(festival, jazz, now)

    return True


def _add_phases(festival: Any) -> None:
    """The course of the festival, from the site visit to the follow-up work (PRJ-006, PRJ-092).

    The site visit lies a week before the rental period and the follow-up
    work at its very end: the calendar and the timeline show both.
    """
    first = timezone.localtime(festival.start)
    last = timezone.localtime(festival.end)

    def moment(day: datetime.datetime, hour: int, minute: int = 0) -> datetime.datetime:
        return day.replace(hour=hour, minute=minute)

    market, warehouse = "Marktplatz Musterstadt", "Lager"
    show_day = first + datetime.timedelta(days=1)
    for kind, title, start, end, place, notes in (
        (
            "planning",
            "Ortsbegehung mit dem Kulturamt",
            moment(first - datetime.timedelta(days=7), 10),
            moment(first - datetime.timedelta(days=7), 11, 30),
            market,
            "Stromanschlüsse, Zufahrt für den Sprinter, Standort FOH",
        ),
        ("loading", "", moment(first, 8), moment(first, 11), warehouse, ""),
        ("setup", "", moment(first, 12), moment(first, 19), market, ""),
        ("event", "Stadtfest", moment(show_day, 11), moment(show_day + datetime.timedelta(days=1), 23), market, ""),
        ("teardown", "", moment(last, 8), moment(last, 13), market, ""),
        ("aftercare", "", moment(last, 14), moment(last, 18), warehouse, "Auspacken, Eingangskontrolle, einlagern"),
    ):
        course.add_phase(festival, kind=kind, title=title, start=start, end=end, location=place, notes=notes)


def _create_people_and_times(festival: Any, jazz: Any, now: datetime.datetime) -> None:
    """Sample data of stage 3: job functions with prices, people with rates, crew lines, times.

    Shows on purpose what the planning warns about: Anna is planned in two
    projects at the same time (PRJ-022), one stagehand place is still open
    (PRJ-020), and one time entry waits for approval (ZEI-012).
    """

    def function(name: str, price: str | None, guide: str, **tiers: str) -> JobFunction:
        """A job function of the start data (PER-037) – created if missing – with the price of its service product."""
        job_function = JobFunction.objects.filter(name=name).first() or people.save_job_function(JobFunction(name=name))
        job_function.guide_cost_rate = Decimal(guide)
        if "guide_above_limit" in tiers:
            job_function.guide_cost_rate_above_limit = Decimal(tiers["guide_above_limit"])
        people.save_job_function(job_function)
        product = job_function.service_product
        product.price = Decimal(price) if price is not None else None
        product.billing_mode = BillingMode.HOURLY
        if "limit" in tiers:
            # PER-035: from the 11th hour of a day the higher price.
            product.hours_limit, product.price_above_limit = Decimal(tiers["limit"]), Decimal(tiers["above"])
        product.full_clean()
        product.save()
        return job_function

    sound = function("Tontechniker", "45.00", "32.00", limit="10", above="55.00", guide_above_limit="38.00")
    light = function("Lichttechniker", "42.00", "30.00")
    hand = function("Stagehand", "28.00", "18.00")
    warehouse = function("Lager", None, "18.00")

    def person(first: str, last: str, kind: str, rates: dict[JobFunction, str], **fields: Any) -> Person:
        created = people.save_person(Person(first_name=first, last_name=last, kind=kind, **fields))
        for job_function, rate in rates.items():
            people.set_rate(created, job_function, Decimal(rate), datetime.date(2024, 1, 1))
        return created

    anna = person(
        "Anna",
        "Becker",
        EmploymentKind.EMPLOYEE,
        {sound: "35.00", hand: "20.00", warehouse: "20.00"},
        email="anna.becker@example.de",
        phone="0170 5550101",
        share_phone=True,
    )
    tom = person(
        "Tom",
        "Richter",
        EmploymentKind.FREELANCER,
        {light: "38.00"},
        email="tom@richter-licht.example.de",
        phone="0171 5550102",
        company="Richter Lichtdesign",
        city="Musterstadt",
    )
    lea = person("Lea", "Vogel", EmploymentKind.TEMPORARY, {hand: "16.00"}, phone="0151 5550103")

    show_day = festival.start + datetime.timedelta(days=1)
    build = {"start": festival.start, "end": festival.start + datetime.timedelta(hours=8)}
    show = {"start": show_day, "end": show_day + datetime.timedelta(hours=14)}
    crew.add_crew_lines(
        festival, rights=ALL_RIGHTS, job_function=sound, person=anna, meeting_point="Marktplatz, FOH", **show
    )
    crew.add_crew_lines(
        festival, rights=ALL_RIGHTS, job_function=light, person=tom, meeting_point="Marktplatz, Bühne", **show
    )
    crew.add_crew_lines(
        festival, rights=ALL_RIGHTS, job_function=hand, person=lea, meeting_point="Lager, Rampe", **build
    )
    crew.add_crew_lines(festival, rights=ALL_RIGHTS, job_function=hand, meeting_point="Lager, Rampe", **build)
    # The jazz night falls on the show day of the festival: Anna is booked twice.
    crew.add_crew_lines(
        jazz,
        rights=ALL_RIGHTS,
        job_function=sound,
        person=anna,
        start=jazz.start + datetime.timedelta(hours=8),
        end=jazz.start + datetime.timedelta(hours=14),
    )
    people.save_absence(
        Absence(
            person=lea,
            kind=AbsenceKind.VACATION,
            start=now + datetime.timedelta(days=20),
            end=now + datetime.timedelta(days=27),
        )
    )

    internal = projects.create_project(
        name="Lager und Werkstatt",
        is_internal=True,
        status=ProjectStatus.CONFIRMED,
        start=now - datetime.timedelta(days=30),
        end=now + datetime.timedelta(days=335),
    )
    earlier = now - datetime.timedelta(days=3)
    approved = times.create_entry(
        person=anna,
        project=internal,
        job_function=warehouse,
        start=earlier + datetime.timedelta(hours=1),
        end=earlier + datetime.timedelta(hours=5),
        rights=ALL_RIGHTS,
        user=None,
        note="Kabel geprüft und sortiert",
        submit=True,
    )
    times.approve_entries([approved], rights=ALL_RIGHTS, user=None)
    times.create_entry(
        person=anna,
        project=internal,
        job_function=warehouse,
        start=earlier + datetime.timedelta(days=1, hours=1),
        end=earlier + datetime.timedelta(days=1, hours=7),
        rights=ALL_RIGHTS,
        user=None,
        break_minutes=30,
        note="Rücknahme und Reinigung",
        submit=True,
    )
