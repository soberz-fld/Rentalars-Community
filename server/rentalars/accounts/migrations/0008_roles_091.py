# SPDX-License-Identifier: GPL-3.0-or-later
"""The role "Crew" sees the overview only; seeing the availability of material is a special right.

The requirements:

* By default the role "Crew" does not see the open items or shortages, and the planning, schedule, access and history
  of projects are not visible to it. The project access
  "assigned projects, overview without planning" (``deployment``) is new: in
  its projects the role opens the overview ("Überblick") with the phases, the
  packing list and the chat, never the planning, whatever a membership says.
* Seeing the availability of material is a special right of its own; by default the crew does not have it. The special right
  ``availability`` ("See availability of material") is new.

What this step changes in an existing installation:

* The role named "Crew" (the German and the English start name are the same)
  gets the project access ``deployment`` – only while it still has its start
  rights for what is touched: "assigned projects only", read on projects and
  no special right. It does not get the new special right.
* Every other role gets the special right ``availability``, so nothing
  changes for its users – also a role "Crew" the company changed; that one
  keeps its project access and is noted in the change log as left as it is
  (event ``role.crew_left_as_is``).

Each change is written to the change log as "Aktualisierung", by the
role's ID, with the values before and after. A fresh database (start data
not installed yet) gets the new start roles from ``accounts.defaults``.

Going back: the project access ``deployment`` becomes
"assigned projects only" again for every role, and the special right
``availability`` is taken from every role.
"""

from django.db import migrations, models
from django.utils import timezone

ACTOR = "Aktualisierung 0.9.1"
CREW = "Crew"
#: ``accounts.rights.Level.READ``, as stored in ``Role.module_levels``.
READ = 1
PROJECTS = "projects"
ASSIGNED, DEPLOYMENT = "assigned", "deployment"
AVAILABILITY = "availability"
#: The event noted for a role "Crew" the company changed (``core.history``).
LEFT_AS_IS_EVENT = "role.crew_left_as_is"


def _level(levels, module):
    try:
        return int((levels or {}).get(module, 0))
    except (TypeError, ValueError):
        return 0


def has_crew_start_rights(role):
    """The role "Crew" with its start rights for what this step touches: projects and special rights."""
    return (
        role.name == CREW
        and role.project_scope == ASSIGNED
        and _level(role.module_levels, PROJECTS) == READ
        and not list(role.special_rights or [])
    )


def update_roles(apps, schema_editor):
    """The data step of this migration."""
    role_model = apps.get_model("accounts", "Role")
    entries = []  # (role, action, changes, event)
    for role in role_model.objects.order_by("pk"):
        if has_crew_start_rights(role):
            role_model.objects.filter(pk=role.pk).update(project_scope=DEPLOYMENT)
            entries.append((role, "updated", {"project_scope": [ASSIGNED, DEPLOYMENT]}, ""))
            continue
        rights = list(role.special_rights or [])
        if AVAILABILITY not in rights:
            after = sorted({*rights, AVAILABILITY})
            role_model.objects.filter(pk=role.pk).update(special_rights=after)
            entries.append((role, "updated", {"special_rights": [rights, after]}, ""))
        if role.name == CREW:
            entries.append((role, "event", {"name": role.name}, LEFT_AS_IS_EVENT))
    if not entries:
        return
    system_settings = apps.get_model("core", "SystemSettings").objects.filter(pk=1).first()
    if system_settings is None or not system_settings.defaults_installed:
        return  # a fresh database: nothing to report
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


def back_to_090(apps, schema_editor):
    """Going back: "assigned projects only" instead of ``deployment``; no special right ``availability``."""
    role_model = apps.get_model("accounts", "Role")
    role_model.objects.filter(project_scope=DEPLOYMENT).update(project_scope=ASSIGNED)
    for role in role_model.objects.all():
        rights = list(role.special_rights or [])
        if AVAILABILITY in rights:
            role_model.objects.filter(pk=role.pk).update(
                special_rights=[right for right in rights if right != AVAILABILITY]
            )


class Migration(migrations.Migration):
    """The new project access "overview without planning" and the new roles."""

    dependencies = [
        ("accounts", "0007_crew_packing_084"),
        ("core", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="project_scope",
            field=models.CharField(
                choices=[
                    ("all", "all projects"),
                    ("assigned", "assigned projects only"),
                    ("deployment", "assigned projects only, overview without planning"),
                ],
                default="all",
                help_text=(
                    "“Assigned projects only”: the rights on projects and packing lists hold only in projects the "
                    "user is a member of or is scheduled for as crew. “Overview without planning”: there only the "
                    "overview, the packing list and the chat."
                ),
                max_length=10,
                verbose_name="project access",
            ),
        ),
        migrations.RunPython(update_roles, back_to_090),
    ]
