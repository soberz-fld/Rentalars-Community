# SPDX-License-Identifier: GPL-3.0-or-later
"""The start rights of four roles (AUT-036).

1. "Freie Kraft": the description names only the essentials (own deployments and time recording, no project info);
   no view of the availability of material; the project access is "assigned without planning" by default.
2. "Crew": may read the correspondence.
3. "Lager": may create and edit material but not delete it; may read the correspondence.
4. "Projektleitung": may read products; may create and edit projects but not delete them.

A fresh installation starts with these roles; an update changes the roles that still have the start rights
and leaves – and notes – those the company changed (``accounts/0009_role_defaults_094``).
"""

from __future__ import annotations

import importlib

from django.apps import apps

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight, rights_of
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry
from tests.helpers import RentalarsTestCase, make_user

MIGRATION = importlib.import_module("rentalars.accounts.migrations.0009_role_defaults_094")
FREELANCER_TEXT = "Nur das Wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos"


def role_state(name: str) -> tuple[dict[str, int], list[str], str]:
    """Module levels (without level 0), special rights and project access of a role."""
    role = Role.objects.get(name=name)
    levels = {module: int(level) for module, level in role.module_levels.items() if int(level)}
    return levels, sorted(role.special_rights), role.project_scope


class StartRolesTests(RentalarsTestCase):
    """The roles a fresh installation starts with."""

    def test_freie_kraft(self) -> None:
        role = Role.objects.get(name="Freie Kraft")
        self.assertEqual(role.description, FREELANCER_TEXT)
        self.assertEqual((role.special_rights, role.project_scope), ([], ProjectScope.DEPLOYMENT))
        rights = rights_of(make_user("frieda", roles=("Freie Kraft",)))
        self.assertFalse(rights.has(SpecialRight.AVAILABILITY))
        self.assertFalse(rights.reads_planning)

    def test_crew_reads_correspondence(self) -> None:
        rights = rights_of(make_user("carla", roles=("Crew",)))
        self.assertTrue(rights.has(SpecialRight.CORRESPONDENCE_READ))
        self.assertFalse(rights.has(SpecialRight.CORRESPONDENCE_WRITE))

    def test_lager_changes_material_but_does_not_delete_it(self) -> None:
        rights = rights_of(make_user("luka", roles=("Lager",)))
        self.assertEqual(rights.level(Module.MATERIAL), Level.WRITE)
        self.assertTrue(rights.has(SpecialRight.CORRESPONDENCE_READ))

    def test_projektleitung_reads_products_and_does_not_delete_projects(self) -> None:
        rights = rights_of(make_user("paula", roles=("Projektleitung",)))
        self.assertEqual(rights.level(Module.PRODUCTS), Level.READ)
        self.assertEqual(rights.level(Module.PROJECTS), Level.WRITE)
        self.assertEqual(rights.level(Module.CUSTOMERS), Level.WRITE)  # untouched


class UpdateTests(RentalarsTestCase):
    """accounts 0009: an older installation – its roles as they were, then the step."""

    def back(self) -> None:
        MIGRATION.back_to_093(apps, None)

    def test_the_roles_as_they_were(self) -> None:
        # Fresh installations write "Wichtigste"; the migration knows the older text.
        Role.objects.filter(name="Freie Kraft").update(description=FREELANCER_TEXT.replace("Wichtigste", "wichtigste"))
        self.back()
        self.assertEqual(
            role_state("Freie Kraft"), ({"projects": 1, "packing": 1, "time_tracking": 2}, ["availability"], "assigned")
        )
        self.assertEqual(
            Role.objects.get(name="Freie Kraft").description,
            "Eingeschränktes Konto: eigene Einsätze und Zeiten, keine Preise",
        )
        self.assertEqual(role_state("Crew")[1], [])
        self.assertEqual(role_state("Lager")[0]["material"], 3)
        self.assertEqual(role_state("Projektleitung")[0]["projects"], 3)
        self.assertEqual(role_state("Projektleitung")[0]["products"], 2)

    def test_the_roles_with_the_start_rights_get_the_new_ones(self) -> None:
        self.back()
        MIGRATION.update_roles(apps, None)
        freelancer = Role.objects.get(name="Freie Kraft")
        self.assertEqual((freelancer.special_rights, freelancer.project_scope), ([], "deployment"))
        self.assertEqual(freelancer.description, FREELANCER_TEXT)
        self.assertEqual(role_state("Crew")[1], ["correspondence_read"])
        self.assertEqual(role_state("Lager")[0]["material"], 2)
        self.assertIn("correspondence_read", role_state("Lager")[1])
        self.assertEqual(role_state("Projektleitung")[0]["projects"], 2)
        self.assertEqual(role_state("Projektleitung")[0]["products"], 1)
        # Nothing else is touched.
        self.assertEqual(role_state("Nur-Lesen")[2], "all")
        self.assertEqual(role_state("Personaldisposition")[0]["personnel"], 3)
        entries = AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.4")
        self.assertEqual(entries.count(), 4)
        entry = entries.get(object_id=str(freelancer.pk))
        self.assertEqual(entry.action, "updated")
        self.assertEqual(entry.changes["special_rights"], [["availability"], []])
        self.assertEqual(entry.changes["project_scope"], ["assigned", "deployment"])

    def test_a_role_the_company_changed_is_left_alone_and_noted(self) -> None:
        self.back()
        lager = Role.objects.get(name="Lager")
        lager.special_rights = [*lager.special_rights, SpecialRight.PRICES]
        lager.save()
        MIGRATION.update_roles(apps, None)
        lager.refresh_from_db()
        self.assertEqual(lager.module_levels["material"], 3)
        self.assertNotIn("correspondence_read", lager.special_rights)
        event = AuditLogEntry.objects.get(event="role.defaults_left_as_is")
        self.assertEqual((event.actor_label, event.object_id), ("Aktualisierung 0.9.4", str(lager.pk)))
        reader = rights_of(make_user("a", superuser=True))
        self.assertIn("behält ihre Rechte", describe([event], reader)[0].summary)
        self.assertEqual(role_state("Crew")[1], ["correspondence_read"])  # the others are changed

    def test_a_description_the_company_wrote_stays(self) -> None:
        self.back()
        Role.objects.filter(name="Freie Kraft").update(description="Externe Techniker")
        MIGRATION.update_roles(apps, None)
        role = Role.objects.get(name="Freie Kraft")
        self.assertEqual((role.description, role.project_scope), ("Externe Techniker", "deployment"))

    def test_running_it_twice_changes_nothing_more(self) -> None:
        self.back()
        MIGRATION.update_roles(apps, None)
        before = AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.4").count()
        MIGRATION.update_roles(apps, None)
        self.assertEqual(AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.4").count(), before)

    def test_going_back(self) -> None:
        MIGRATION.back_to_093(apps, None)
        self.assertEqual(role_state("Freie Kraft")[2], "assigned")
        MIGRATION.update_roles(apps, None)
        MIGRATION.back_to_093(apps, None)
        self.assertEqual(role_state("Projektleitung")[0]["projects"], 3)
