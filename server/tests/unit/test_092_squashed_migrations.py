# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations are squashed; an older database is refused clearly (NFA-077).

The requirement: clean up legacy where necessary; backward compatibility is not required for older versions.
An installation that is recent enough is updated as before; an older one must be updated
first.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase

from rentalars.core.checks import database_not_too_old, partially_applied_squashes
from tests.helpers import RentalarsTestCase


class SquashedMigrationsTests(SimpleTestCase):
    """The squashed migrations replace every old migration – and nothing newer."""

    def test_every_squash_replaces_only_migrations_up_to_090(self) -> None:
        loader = MigrationLoader(None, ignore_no_migrations=True)
        squashes = {key: migration for key, migration in loader.disk_migrations.items() if migration.replaces}
        self.assertTrue(squashes)
        for (app, name), migration in squashes.items():
            with self.subTest(migration=f"{app}.{name}"):
                # Django's form: the next migration of the module is numbered after the last one replaced.
                self.assertEqual(name, f"{migration.replaces[0][1][:4]}_squashed_{migration.replaces[-1][1]}")
                self.assertTrue(all(target[0] == app for target in migration.replaces))
                self.assertFalse([target for target in migration.replaces if target[1].endswith("_091")])

    def test_no_old_migration_file_is_left(self) -> None:
        """A replaced migration whose file is still there would be used for an older database."""
        loader = MigrationLoader(None, ignore_no_migrations=True)
        replaced = {tuple(target) for migration in loader.disk_migrations.values() for target in migration.replaces}
        self.assertFalse(replaced & set(loader.disk_migrations))


class OlderDatabaseTests(RentalarsTestCase):
    """An older database: "migrate" stops before it changes anything and says what to do."""

    def test_a_new_database_has_every_replaced_migration_recorded(self) -> None:
        self.assertEqual(partially_applied_squashes(connection), [])
        self.assertEqual(database_not_too_old(databases=["default"]), [])

    def test_an_older_database_is_refused(self) -> None:
        # Did not have the squashed migrations yet.
        MigrationRecorder(connection).migration_qs.filter(
            app__in=["products", "projects"], name__in=["0008_vehicles_090", "0029_logistics_090"]
        ).delete()
        self.assertEqual(
            partially_applied_squashes(connection),
            [("products", "0001_squashed_0008_vehicles_090"), ("projects", "0004_squashed_0029_logistics_090")],
        )
        errors = database_not_too_old(databases=["default"])
        self.assertEqual([error.id for error in errors], ["rentalars.E001"])
        self.assertIn("0.9.0", errors[0].msg)
        self.assertIn("products.0001_squashed_0008_vehicles_090", errors[0].hint)
        with self.assertRaises(SystemCheckError):
            call_command("migrate", verbosity=0, interactive=False, skip_checks=False)

    def test_only_the_checks_of_the_database_look(self) -> None:
        """A start without --database (runserver, gunicorn, check) does not ask the database."""
        MigrationRecorder(connection).migration_qs.filter(app="products", name="0008_vehicles_090").delete()
        self.assertEqual(database_not_too_old(databases=None), [])
