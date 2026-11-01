# SPDX-License-Identifier: GPL-3.0-or-later
"""The start rights of four roles (AUT-010, AUT-031, AUT-032, AUT-036).

The requirements:

* "Freie Kraft": the description "Nur das wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos";
  no availability of material; the project access "assigned projects only, overview without planning".
* "Crew": reads correspondence.
* "Lager": creates and changes material, does not delete it; reads correspondence.
* "Projektleitung": reads products; creates and changes projects, does not delete them.

What this step changes in an existing installation: a role that still has *all* the earlier start rights –
module levels, special rights and project access, by its name – gets the new ones, and its description too if
that is still the earlier one. A role the company changed is left as it is and noted in the change log (event
``role.defaults_left_as_is``): its users keep what they have.

Each change is written to the change log as "Aktualisierung", by the role's ID, with the values before and
after. A fresh database (start data not installed yet) gets the new start roles from ``accounts.defaults``.

Going back: a role that still has the new start rights gets the earlier ones.
"""

from django.db import migrations
from django.utils import timezone

ACTOR = "Aktualisierung 0.9.4"
LEFT_AS_IS_EVENT = "role.defaults_left_as_is"
READ, WRITE, DELETE = 1, 2, 3

#: name -> (rights, rights); each: module levels, special rights, project access, description.
ROLES = {
    "Projektleitung": (
        {
            "levels": {
                "projects": DELETE,
                "packing": WRITE,
                "customers": WRITE,
                "products": WRITE,
                "material": READ,
                "personnel": READ,
                "time_tracking": WRITE,
                "email": WRITE,
                "reports": READ,
            },
            "special": [
                "prices",
                "purchase_prices",
                "personnel_costs",
                "correspondence_read",
                "correspondence_write",
                "approve_times",
                "plan_any_job_function",
                "availability",
            ],
            "scope": "all",
            "description": "Projekte anlegen, Material und Personal disponieren, kalkulieren",
        },
        {
            "levels": {
                "projects": WRITE,
                "packing": WRITE,
                "customers": WRITE,
                "products": READ,
                "material": READ,
                "personnel": READ,
                "time_tracking": WRITE,
                "email": WRITE,
                "reports": READ,
            },
            "special": [
                "prices",
                "purchase_prices",
                "personnel_costs",
                "correspondence_read",
                "correspondence_write",
                "approve_times",
                "plan_any_job_function",
                "availability",
            ],
            "scope": "all",
            "description": "Projekte anlegen, Material und Personal disponieren, kalkulieren",
        },
    ),
    "Lager": (
        {
            "levels": {"material": DELETE, "packing": WRITE, "products": READ, "projects": READ},
            "special": ["purchase_prices", "availability"],
            "scope": "all",
            "description": "Material pflegen, Packlisten abarbeiten, Ausgabe und Rücknahme, Defekte",
        },
        {
            "levels": {"material": WRITE, "packing": WRITE, "products": READ, "projects": READ},
            "special": ["purchase_prices", "availability", "correspondence_read"],
            "scope": "all",
            "description": "Material pflegen, Packlisten abarbeiten, Ausgabe und Rücknahme, Defekte",
        },
    ),
    "Crew": (
        {
            "levels": {"projects": READ, "packing": WRITE, "time_tracking": WRITE},
            "special": [],
            "scope": "deployment",
            "description": "Eigene Einsätze sehen, eigene Zeiten erfassen, Packliste abarbeiten",
        },
        {
            "levels": {"projects": READ, "packing": WRITE, "time_tracking": WRITE},
            "special": ["correspondence_read"],
            "scope": "deployment",
            "description": "Eigene Einsätze sehen, eigene Zeiten erfassen, Packliste abarbeiten",
        },
    ),
    "Freie Kraft": (
        {
            "levels": {"projects": READ, "packing": READ, "time_tracking": WRITE},
            "special": ["availability"],
            "scope": "assigned",
            "description": "Eingeschränktes Konto: eigene Einsätze und Zeiten, keine Preise",
        },
        {
            "levels": {"projects": READ, "packing": READ, "time_tracking": WRITE},
            "special": [],
            "scope": "deployment",
            "description": "Nur das wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos",
        },
    ),
}


#: The names the start roles have in an English installation (``core.start_data``), and the English descriptions of
#: "Freie Kraft" before and after – the only description that changes. Written out here: a migration does not import
#: code that may change later.
ENGLISH_NAMES = {
    "Projektleitung": "Project management",
    "Lager": "Warehouse",
    "Crew": "Crew",
    "Freie Kraft": "Freelancer",
}
ENGLISH_DESCRIPTIONS = {
    "Freie Kraft": (
        "Restricted account: own deployments and times, no prices",
        "Only the essentials: own deployments and time recording, no project information",
    ),
}


def _levels(role):
    """The module levels of a role as numbers, without the modules at level 0."""
    result = {}
    for module, level in (role.module_levels or {}).items():
        try:
            level = int(level)
        except (TypeError, ValueError):
            continue
        if level:
            result[str(module)] = level
    return result


def has_rights(role, rights):
    """Whether the role has exactly these start rights (module levels, special rights, project access)."""
    return (
        _levels(role) == rights["levels"]
        and sorted(role.special_rights or []) == sorted(rights["special"])
        and role.project_scope == rights["scope"]
    )


def _move(apps, source, target, event_for_left):
    """Give the roles that still have the ``source`` start rights the ``target`` ones; note the others."""
    role_model = apps.get_model("accounts", "Role")
    entries = []  # (role, action, changes, event)
    for name, pair in ROLES.items():
        old, new = (pair[source], pair[target])
        english = ENGLISH_NAMES[name]
        for role in role_model.objects.filter(name__in={name, english}).order_by("pk"):
            if not has_rights(role, old):
                if event_for_left and not has_rights(role, new):
                    entries.append((role, "event", {"name": role.name}, LEFT_AS_IS_EVENT))
                continue
            changes = {}
            values = {}
            if _levels(role) != new["levels"]:
                values["module_levels"] = {module: level for module, level in new["levels"].items()}
                changes["module_levels"] = [role.module_levels, values["module_levels"]]
            if sorted(role.special_rights or []) != sorted(new["special"]):
                values["special_rights"] = list(new["special"])
                changes["special_rights"] = [list(role.special_rights or []), values["special_rights"]]
            if role.project_scope != new["scope"]:
                values["project_scope"] = new["scope"]
                changes["project_scope"] = [role.project_scope, new["scope"]]
            old_text, new_text = old["description"], new["description"]
            if role.name == english != name and name in ENGLISH_DESCRIPTIONS:
                old_text, new_text = ENGLISH_DESCRIPTIONS[name][source], ENGLISH_DESCRIPTIONS[name][target]
            if role.description == old_text and old_text != new_text:
                values["description"] = new_text
                changes["description"] = [role.description, new_text]
            if values:
                role_model.objects.filter(pk=role.pk).update(**values)
                entries.append((role, "updated", changes, ""))
    return entries


def _note(apps, entries):
    """Write the entries to the change log – unless the database is a fresh one."""
    if not entries:
        return
    system_settings = apps.get_model("core", "SystemSettings").objects.filter(pk=1).first()
    if system_settings is None or not system_settings.defaults_installed:
        return
    content_type = apps.get_model("contenttypes", "ContentType").objects.get_or_create(
        app_label="accounts", model="role"
    )[0]
    entry_model = apps.get_model("core", "AuditLogEntry")
    now = timezone.now()
    entry_model.objects.bulk_create(
        [
            entry_model(
                timestamp=now,
                actor_label=ACTOR,
                action=action,
                event=event,
                content_type=content_type,
                object_id=str(role.pk),
                object_repr=role.name[:200],
                changes=changes,
            )
            for role, action, changes, event in entries
        ]
    )


def update_roles(apps, schema_editor):
    """The data step: the new start rights for the roles that still have the earlier ones."""
    _note(apps, _move(apps, 0, 1, event_for_left=True))


def back_to_093(apps, schema_editor):
    """Going back: the earlier start rights for the roles that still have the new ones."""
    _move(apps, 1, 0, event_for_left=False)


class Migration(migrations.Migration):
    """The start rights of the roles "Projektleitung", "Lager", "Crew" and "Freie Kraft"."""

    dependencies = [
        ("accounts", "0008_roles_091"),
        ("core", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(update_roles, back_to_093)]
