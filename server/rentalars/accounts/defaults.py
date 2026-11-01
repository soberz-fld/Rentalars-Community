# SPDX-License-Identifier: GPL-3.0-or-later
"""Start data for accounts: the suggested roles of chapter 4."""

from __future__ import annotations

from typing import Any

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight

READ, WRITE, DELETE = int(Level.READ), int(Level.WRITE), int(Level.DELETE)

#: The roles a fresh installation starts with. They are suggestions:
#: administrators can change them and add their own (AUT-010).
ROLES: list[dict[str, Any]] = [
    {
        "name": "Administrator",
        "description": "Nutzer, Rechte, Stammdaten, Systemeinstellungen",
        "module_levels": dict.fromkeys(Module.values, DELETE),
        "special_rights": list(SpecialRight.values),
    },
    {
        "name": "Projektleitung",
        "description": "Projekte anlegen, Material und Personal disponieren, kalkulieren",
        "module_levels": {
            # AUT-036: creates and changes projects, does not delete them; reads products.
            Module.PROJECTS: WRITE,
            Module.PACKING: WRITE,
            Module.CUSTOMERS: WRITE,
            Module.PRODUCTS: READ,
            Module.MATERIAL: READ,
            Module.PERSONNEL: READ,
            Module.TIME_TRACKING: WRITE,
            Module.EMAIL: WRITE,
            Module.REPORTS: READ,
        },
        "special_rights": [
            SpecialRight.PRICES,
            SpecialRight.PURCHASE_PRICES,
            SpecialRight.PERSONNEL_COSTS,
            SpecialRight.CORRESPONDENCE_READ,
            SpecialRight.CORRESPONDENCE_WRITE,
            SpecialRight.APPROVE_TIMES,
            SpecialRight.PLAN_ANY_JOB_FUNCTION,
            SpecialRight.AVAILABILITY,  # AUT-032
        ],
    },
    {
        "name": "Lager",
        "description": "Material pflegen, Packlisten abarbeiten, Ausgabe und Rücknahme, Defekte",
        # AUT-036: creates and changes material, does not delete it; reads correspondence.
        "module_levels": {
            Module.MATERIAL: WRITE,
            Module.PACKING: WRITE,
            Module.PRODUCTS: READ,
            Module.PROJECTS: READ,
        },
        # AUT-032: the warehouse works with stock and shortages.
        "special_rights": [SpecialRight.PURCHASE_PRICES, SpecialRight.AVAILABILITY, SpecialRight.CORRESPONDENCE_READ],
    },
    {
        "name": "Personaldisposition",
        "description": "Personen, Funktionen, Stundensätze, Verfügbarkeiten, Zeiten freigeben",
        "module_levels": {
            Module.PERSONNEL: DELETE,
            Module.TIME_TRACKING: DELETE,
            Module.PROJECTS: READ,
        },
        "special_rights": [
            SpecialRight.PERSONNEL_COSTS,
            SpecialRight.APPROVE_TIMES,
            SpecialRight.PLAN_ANY_JOB_FUNCTION,
            SpecialRight.AVAILABILITY,  # AUT-032: nothing changes for those who had it before
        ],
    },
    {
        # Crew packs in its own projects – also offline in the companion app –, 1:1 what the packing list
        # says: adding material while packing needs write on the project (``packing.services.may_add_material``).
        # AUT-031 (requirement): in its projects only the overview with the phases, the packing list and the
        # chat – no planning, schedule, access, history, "Offene Punkte" or shortages, whatever a membership says –,
        # and no availability of material. Its service cases it works on all the same (``projects.case_work``).
        "name": "Crew",
        "description": "Eigene Einsätze sehen, eigene Zeiten erfassen, Packliste abarbeiten",
        # AUT-036: reads correspondence – the open messages of its cases (EML-055).
        "module_levels": {Module.PROJECTS: READ, Module.PACKING: WRITE, Module.TIME_TRACKING: WRITE},
        "special_rights": [SpecialRight.CORRESPONDENCE_READ],
        "project_scope": ProjectScope.DEPLOYMENT,
    },
    {
        # AUT-036: the least – own deployments and times, no project information (overview without planning)
        # and no availability of material.
        "name": "Freie Kraft",
        "description": "Nur das Wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos",
        "module_levels": {Module.PROJECTS: READ, Module.PACKING: READ, Module.TIME_TRACKING: WRITE},
        "special_rights": [],
        "project_scope": ProjectScope.DEPLOYMENT,
    },
    {
        "name": "Nur-Lesen",
        "description": "Einsicht ohne Änderungsrechte, z. B. Buchhaltung oder Geschäftsführung",
        "module_levels": {module: READ for module in Module.values if module != Module.ADMINISTRATION},
        "special_rights": [
            SpecialRight.PRICES,
            SpecialRight.PURCHASE_PRICES,
            SpecialRight.PERSONNEL_COSTS,
            SpecialRight.CORRESPONDENCE_READ,
            SpecialRight.AVAILABILITY,  # AUT-032
        ],
    },
]


def install() -> None:
    """Create the suggested roles that do not exist yet."""
    for definition in ROLES:
        if Role.objects.filter(name=definition["name"]).exists():
            continue
        role = Role(
            name=definition["name"],
            description=definition["description"],
            module_levels={str(module): level for module, level in definition["module_levels"].items()},
            special_rights=[str(right) for right in definition["special_rights"]],
            project_scope=definition.get("project_scope", ProjectScope.ALL),
        )
        role.full_clean()
        role.save()
