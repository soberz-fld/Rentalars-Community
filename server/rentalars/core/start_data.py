# SPDX-License-Identifier: GPL-3.0-or-later
"""The start data of a new installation in German or English (UIX-029).

A fresh installation creates its start data in German – the roles, units,
tax rates, main categories, the rental scale, the storage location, the job
functions with their service products, the subrental product E-001, the kinds
of project documents, the project template "Dry Hire" and the automations of
the service cases (the modules' ``defaults``, some data migrations). An
installation whose language is English (``language = en`` in the
configuration file, or "English" chosen in the first-run setup) gets them in
English: :func:`localise` renames every record that still carries its start
name – nothing the company created or renamed itself is touched. Codes stay
as they are (the category codes T, L, M …, "19 %").

When this happens
-----------------
* Right after the start data was installed (``core.defaults.install_defaults``),
  in the language of the installation.
* In the first-run setup, in the language chosen there
  (``core.setup.complete_setup``).

Existing installations are never changed: their start data is their data.
"""

from __future__ import annotations

import importlib
from typing import Any

#: Roles: German name → (English name, German description, English description).
ROLES = {
    "Administrator": (
        "Administrator",
        "Nutzer, Rechte, Stammdaten, Systemeinstellungen",
        "Users, rights, master data, system settings",
    ),
    "Projektleitung": (
        "Project management",
        "Projekte anlegen, Material und Personal disponieren, kalkulieren",
        "Create projects, plan material and personnel, calculate",
    ),
    "Lager": (
        "Warehouse",
        "Material pflegen, Packlisten abarbeiten, Ausgabe und Rücknahme, Defekte",
        "Look after material, work through packing lists, issue and return, defects",  # UIX-029
    ),
    "Personaldisposition": (
        "Personnel planning",
        "Personen, Funktionen, Stundensätze, Verfügbarkeiten, Zeiten freigeben",
        "People, job functions, hourly rates, availability, approving times",
    ),
    "Crew": (
        "Crew",
        # Crew packs (write on packing in its own projects).
        "Eigene Einsätze sehen, eigene Zeiten erfassen, Packliste abarbeiten",
        "See own deployments, record own times, work through the packing list",
    ),
    "Freie Kraft": (
        "Freelancer",
        "Nur das Wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos",
        "Only the essentials: own deployments and time recording, no project information",
    ),
    "Nur-Lesen": (
        "Read only",
        "Einsicht ohne Änderungsrechte, z. B. Buchhaltung oder Geschäftsführung",
        "Viewing without the right to change, e.g. accounting or management",
    ),
}

#: Units: (German name, German abbreviation) → (English name, English abbreviation).
UNITS = {
    ("Stück (Miete)", "Stk."): ("Piece (rental)", "pcs."),
    ("Stück (Verkauf)", "Stk."): ("Piece (sale)", "pcs."),
    ("Set (Miete)", "Set"): ("Kit (rental)", "kit"),
    ("Set (Verkauf)", "Set"): ("Kit (sale)", "kit"),
    ("Stunde", "Std."): ("Hour", "h"),
    ("Tag", "Tag"): ("Day", "day"),
    ("Kilometer", "km"): ("Kilometre", "km"),
    ("Pauschal", "psch."): ("Flat rate", "flat"),
    ("Angefangener Liter", "l"): ("Litre or part of one", "l"),
    ("Angefangener Meter", "m"): ("Metre or part of one", "m"),
    ("Angefangenes Kilogramm", "kg"): ("Kilogram or part of one", "kg"),
}

#: Main categories by code: German name → English name.
CATEGORIES = {
    "T": ("Ton", "Sound"),
    "L": ("Licht", "Lighting"),
    "M": ("Video/Medien", "Video/media"),
    "R": ("Rigging/Traverse", "Rigging/truss"),
    "K": ("Kabel", "Cables"),
    "V": ("Verkauf", "Sale"),
    "E": ("Extern zugemietetes Material", "Material subrented from others"),
    "D": ("Veranstaltungstechnik-Dienstleistung", "Event technology services"),
    "C": ("Fremdmaterial", "Customer material"),
    "N": ("Nebenkosten", "Incidental costs"),
    "FZ": ("Fuhrpark", "Fleet"),  # LOG-002
}
CATEGORY_FIELDS = {("K", "Länge"): "Length"}

TAX_RATES = {"steuerfrei": "tax-free"}
STORAGE_LOCATIONS = {"Hauptlager": "Main warehouse"}
RENTAL_SCALES = {"Standardstaffel": "Standard scale"}

#: Job functions, and their service products of the same name.
JOB_FUNCTIONS = {
    "Techniker": "Technician",
    "Lichttechniker": "Lighting technician",
    "Tontechniker": "Sound technician",
    "Medientechniker": "Video technician",
    "Stagehand": "Stagehand",
    "Lager": "Warehouse",
    "Projektplanung": "Project planning",
    "Sonstiges": "Other",
}

#: The general subrental product E-001: (name, note) German → English.
SUBRENTAL_PRODUCT = {
    (
        "Zumietung",
        "Allgemeines Produkt für zugemietetes Material. Bezeichnung, Lieferant und Preise stehen an der Position.",
    ): (
        "Subrental",
        "General product for subrented material. Title, supplier and prices are given on the line.",
    ),
}

#: The start list of tax accounts (SKR 03): number → (German name, English name); the migration of the master data
#: creates them in German, the English installation renames those it finds under their German name.
TAX_ACCOUNTS = {
    "0027": ("EDV-Software", "Computer software"),
    "0200": ("Technische Anlagen und Maschinen", "Technical equipment and machinery"),
    "0320": ("Pkw", "Cars"),
    "0350": ("Lkw", "Trucks"),
    "0400": ("Betriebsausstattung", "Operating equipment"),
    "0410": ("Geschäftsausstattung", "Business equipment"),
    "0420": ("Büroeinrichtung", "Office furniture"),
    "0480": ("Geringwertige Wirtschaftsgüter", "Low-value assets"),
    "3100": ("Fremdleistungen", "External services"),
    "3200": ("Wareneingang", "Goods received"),
    "3300": ("Wareneingang 7 % Vorsteuer", "Goods received, 7 % input tax"),
    "3400": ("Wareneingang 19 % Vorsteuer", "Goods received, 19 % input tax"),
    "3800": ("Bezugsnebenkosten", "Incidental acquisition costs"),
    "3850": ("Zölle und Einfuhrabgaben", "Customs duties and import charges"),
    "4210": ("Miete", "Rent"),
    "4240": ("Gas, Strom, Wasser", "Gas, electricity, water"),
    "4360": ("Versicherungen", "Insurance"),
    "4500": ("Fahrzeugkosten", "Vehicle costs"),
    "4530": ("Laufende Kfz-Betriebskosten", "Running vehicle costs"),
    "4540": ("Kfz-Reparaturen", "Vehicle repairs"),
    "4600": ("Werbekosten", "Advertising costs"),
    "4650": ("Bewirtungskosten", "Entertainment costs"),
    "4660": ("Reisekosten Arbeitnehmer", "Travel costs, employees"),
    "4670": ("Reisekosten Unternehmer", "Travel costs, owner"),
    "4710": ("Verpackungsmaterial", "Packaging material"),
    "4730": ("Ausgangsfrachten", "Outgoing freight"),
    "4806": ("Wartungskosten für Hard- und Software", "Maintenance of hardware and software"),
    "4809": ("Sonstige Reparaturen und Instandhaltungen", "Other repairs and maintenance"),
    "4810": ("Mieten für Einrichtungen (bewegliche Wirtschaftsgüter)", "Rent of equipment (movable assets)"),
    "4900": ("Sonstige betriebliche Aufwendungen", "Other operating expenses"),
    "4910": ("Porto", "Postage"),
    "4920": ("Telefon", "Telephone"),
    "4930": ("Bürobedarf", "Office supplies"),
    "4950": ("Rechts- und Beratungskosten", "Legal and consulting fees"),
    "4955": ("Buchführungskosten", "Bookkeeping costs"),
    "4970": ("Nebenkosten des Geldverkehrs", "Bank charges"),
    "4980": ("Betriebsbedarf", "Operating supplies"),
    "4985": ("Werkzeuge und Kleingeräte", "Tools and small equipment"),
}

#: Kinds of project documents (masterdata 0003, 0009).
DOCUMENT_TYPES = {
    "Bühnenplan": "Stage plan",
    "Rider": "Rider",
    "Ablaufplan": "Running order",
    "Hallenplan": "Hall plan",
    "Vertrag": "Contract",
    "Bestellung": "Order",
    "Sonstiges": "Other",
    "Showfile": "Show file",
}

#: The project template "Dry Hire" (PRJ-095): name, description, notes and the texts of its phases.
DRY_HIRE_ENGLISH_NAME = "Dry Hire (rental without crew)"
DRY_HIRE_ENGLISH_DESCRIPTION = (
    "Rental without our crew: the customer collects the material at the warehouse and brings it back. With the "
    "phases packing, handover to the customer, return and follow-up work – without crew and without lines; you "
    "plan the material as usual."
)
DRY_HIRE_TEXTS = {
    "Dry Hire: Der Kunde holt das Material im Lager ab und bringt es zurück – ohne Personal und ohne Transport von "
    "uns.": "Dry hire: the customer collects the material at the warehouse and brings it back – without our crew "
    "and without transport.",
    "Lager": "Warehouse",
    "Material zusammenstellen, prüfen und für die Abholung bereitstellen.": (
        "Put the material together, check it and set it aside for collection."
    ),
    "Übergabe an den Kunden (Abholung)": "Handover to the customer (collection)",
    "Material mit dem Kunden durchgehen, Lieferschein unterschreiben lassen.": (
        "Go through the material with the customer, have the delivery note signed."
    ),
    "Rücknahme": "Return",
    "Der Kunde bringt das Material zurück: Vollständigkeit prüfen, Schäden notieren.": (
        "The customer brings the material back: check that everything is there, note any damage."
    ),
    "Auspacken, Eingangskontrolle, einlagern.": "Unpack, check what came in, put it away.",
}


def role_names(german: str) -> list[str]:
    """The names a start role may have: ``["Freie Kraft", "Freelancer"]`` – for code that looks a role up."""
    english = ROLES.get(german, (german,))[0]
    return [german, english] if english != german else [german]


def _pick(pair: tuple[Any, Any], language: str) -> tuple[Any, Any]:
    """(name it may have now, name it gets) for a German/English pair."""
    german, english = pair
    return (german, english) if language == "en" else (english, german)


def _rename(queryset: Any, field: str, old: str, new: str, **extra: Any) -> int:
    """Rename the records whose ``field`` is ``old`` (exactly) – one by one, so that the change log notes it."""
    count = 0
    if old == new and not extra:
        return 0
    for record in queryset.filter(**{field: old}):
        setattr(record, field, new)
        for name, value in extra.items():
            setattr(record, name, value)
        record.save()
        count += 1
    return count


def localise(language: str) -> int:
    """Give the start data the names of a language ("de" or "en"), as far as they still carry the other one's.

    Returns:
        How many records were renamed.
    """
    from rentalars.accounts.models import Role
    from rentalars.masterdata.models import (
        Category,
        CategoryField,
        DocumentType,
        RentalScale,
        StorageLocation,
        TaxAccount,
        TaxRate,
        Unit,
    )
    from rentalars.personnel.models import JobFunction
    from rentalars.products.models import Product, ProductKind
    from rentalars.projects.models import ProjectTemplate

    if language not in ("de", "en"):
        return 0
    count = 0
    for german, (english, german_text, english_text) in ROLES.items():
        old, new = _pick((german, english), language)
        old_text, new_text = _pick((german_text, english_text), language)
        for role in Role.objects.filter(name=old, description=old_text):
            role.name, role.description = new, new_text
            role.save()
            count += 1
    for (german, german_short), (english, english_short) in UNITS.items():
        (old, old_short), (new, new_short) = _pick(((german, german_short), (english, english_short)), language)
        for unit in Unit.objects.filter(name=old, abbreviation=old_short):
            unit.name, unit.abbreviation = new, new_short
            unit.save()
            count += 1
    for code, pair in CATEGORIES.items():
        old, new = _pick(pair, language)
        count += _rename(Category.objects.filter(parent__isnull=True, code=code), "name", old, new)
    for (code, german), english in CATEGORY_FIELDS.items():
        old, new = _pick((german, english), language)
        count += _rename(
            CategoryField.objects.filter(category__code=code, category__parent__isnull=True), "label", old, new
        )
    for mapping, model, field in (
        (TAX_RATES, TaxRate, "name"),
        (STORAGE_LOCATIONS, StorageLocation, "name"),
        (RENTAL_SCALES, RentalScale, "name"),
        (DOCUMENT_TYPES, DocumentType, "name"),
    ):
        for german, english in mapping.items():
            old, new = _pick((german, english), language)
            count += _rename(model.objects.all(), field, old, new)
    for number, pair in TAX_ACCOUNTS.items():
        old, new = _pick(pair, language)
        count += _rename(TaxAccount.objects.filter(number=number), "name", old, new)
    for german, english in JOB_FUNCTIONS.items():
        old, new = _pick((german, english), language)
        if old == new:
            continue
        for function in JobFunction.objects.filter(name=old).select_related("service_product"):
            product = function.service_product
            function.name = new
            function.save()
            if product is not None and product.name == old:
                product.name = new
                product.save()
            count += 1
    for (german, german_note), (english, english_note) in SUBRENTAL_PRODUCT.items():
        (old, old_note), (new, new_note) = _pick(((german, german_note), (english, english_note)), language)
        for product in Product.objects.filter(kind=ProductKind.SUBRENTAL, article_number="E-001", name=old):
            product.name = new
            if product.note == old_note:
                product.note = new_note
            product.save()
            count += 1
    count += _localise_dry_hire(ProjectTemplate, language)
    count += _localise_automations(language)
    count += _localise_document_templates(language)
    count += _localise_surcharge_rules(language)
    count += _localise_label_captions(language)
    count += _localise_audit_todos(language)
    return count


#: MAT-056: the words before the phone number and the ID on the labels.
LABEL_CAPTIONS = {"phone_caption": ("Telefonnummer:", "Phone:"), "id_caption": ("Equipment-ID:", "Equipment ID:")}


def _localise_label_captions(language: str) -> int:
    """MAT-056: the words of the labels in the language of the start data, as long as nobody changed them."""
    from rentalars.material.models import LabelSettings

    settings_row = LabelSettings.load()
    changed = []
    for field, pair in LABEL_CAPTIONS.items():
        old, new = _pick(pair, language)
        if getattr(settings_row, field) == old and old != new:
            setattr(settings_row, field, new)
            changed.append(field)
    if changed:
        settings_row.save()
    return len(changed)


def _localise_audit_todos(language: str) -> int:
    """MAT-067: the quick picks for to-dos in the language of the start data, as long as nobody changed them."""
    from rentalars.material.audit_models import DEFAULT_QUICK_TODOS, ENGLISH_QUICK_TODOS, AuditSettings

    old, new = _pick(("\n".join(DEFAULT_QUICK_TODOS), "\n".join(ENGLISH_QUICK_TODOS)), language)
    settings_row = AuditSettings.load()
    if settings_row.quick_todos != old or old == new:
        return 0
    settings_row.quick_todos = new
    settings_row.save()
    return 1


def _localise_document_templates(language: str) -> int:
    """The start texts of the document templates (DOK-005), field by field as long as a field is unchanged."""
    from rentalars.documents.models import DocumentTemplate
    from rentalars.documents.services import DEFAULT_TEMPLATES, DEFAULT_TEMPLATES_ENGLISH

    old_texts, new_texts = _pick((DEFAULT_TEMPLATES, DEFAULT_TEMPLATES_ENGLISH), language)
    count = 0
    for template in DocumentTemplate.objects.all():
        old, new = old_texts.get(template.kind), new_texts.get(template.kind)
        if not old or not new:
            continue
        changed = False
        for field in ("title", "introduction", "closing"):
            if getattr(template, field) == old[field] and old[field] != new[field]:
                setattr(template, field, new[field])
                changed = True
        if changed:
            template.save()
            count += 1
    return count


def _localise_surcharge_rules(language: str) -> int:
    """The names of the rules of § 3b EStG the start data brings (ZEI-024), as long as they are unchanged."""
    from rentalars.core import surcharge_presets
    from rentalars.core.models import TimeSurchargeRule

    german, english = surcharge_presets.preset_names("de"), surcharge_presets.preset_names("en")
    count = 0
    for code in surcharge_presets.CODES:
        old, new = _pick((german[code], english[code]), language)
        count += _rename(TimeSurchargeRule.objects.filter(code=code), "name", old, new)
    return count


def _localise_dry_hire(template_model: Any, language: str) -> int:
    from rentalars.projects.defaults import DRY_HIRE_DESCRIPTION, DRY_HIRE_NAME

    names = (DRY_HIRE_NAME, DRY_HIRE_ENGLISH_NAME)
    old, new = _pick(names, language)
    old_description, new_description = _pick((DRY_HIRE_DESCRIPTION, DRY_HIRE_ENGLISH_DESCRIPTION), language)
    texts = DRY_HIRE_TEXTS if language == "en" else {english: german for german, english in DRY_HIRE_TEXTS.items()}
    count = 0
    for template in template_model.objects.filter(name=old):
        content = dict(template.content or {})
        content["notes"] = texts.get(content.get("notes", ""), content.get("notes", ""))
        phases = []
        for phase in content.get("phases", []):
            phase = dict(phase)
            for key in ("title", "location", "notes"):
                phase[key] = texts.get(phase.get(key, ""), phase.get(key, ""))
            phases.append(phase)
        content["phases"] = phases
        template.name = new
        if template.description == old_description:
            template.description = new_description
        template.content = content
        template.save()
        count += 1
    return count


def _localise_automations(language: str) -> int:
    """The automations of the service cases (ADM-013) – their names, as long as they are unchanged."""
    try:
        # NFA-077: the rules live in the squashed migration.
        module = importlib.import_module("rentalars.automations.migrations.0001_squashed_0003_defects_085")
        from rentalars.automations.models import Automation
    except (ImportError, LookupError):
        return 0
    count = 0
    for rule in getattr(module, "RULES", ()):
        german, english = rule[-2], rule[-1]
        old, new = _pick((german, english), language)
        count += _rename(Automation.objects.all(), "name", old, new)
    return count
