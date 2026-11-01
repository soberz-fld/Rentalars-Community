# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: the check of a database account (NFA-066) and the table fingerprint (NFA-068).

The account check runs against a recorded conversation with the server: the
statements it sends and the rows a MariaDB 10.11 answered. The same checks
ran against real servers (10.11 and 11.8) in the installation tests
(docs/betrieb/installation.md, section "Erprobung").
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from django.core.management import call_command
from django.test import SimpleTestCase

from rentalars.core.database_account import (
    DatabaseError,
    Finding,
    german,
    inspect_account,
    judge_grants,
    names_only,
    try_tables,
)
from rentalars.core.management.commands.database_fingerprint import database_fingerprint
from rentalars.products.models import Product
from tests.helpers import RentalarsTestCase, make_product


class FakeServer:
    """Answers the statements of the check like a MariaDB server would."""

    def __init__(
        self,
        user: str = "rentalars@%",
        grants: list[str] | None = None,
        roles: dict[str, list[str]] | None = None,
        version: str = "11.8.3-MariaDB-ubu2604",
        cipher: str = "",
        charset: str = "utf8mb4",
        tables: list[str] | None = None,
        encrypt: str = "OFF",
        plugins: list[str] | None = None,
        failing: str = "",
    ) -> None:
        self.user = user
        self.grants = (
            grants
            if grants is not None
            else [
                f"GRANT USAGE ON *.* TO `{user.split('@')[0]}`@`%` IDENTIFIED BY PASSWORD '*ABC'",
                f"GRANT ALL PRIVILEGES ON `rentalars`.* TO `{user.split('@')[0]}`@`%`",
            ]
        )
        self.roles = roles or {}
        self.version = version
        self.cipher = cipher
        self.charset = charset
        self.tables = tables or []
        self.encrypt = encrypt
        self.plugins = plugins or []
        self.failing = failing
        self.statements: list[str] = []

    def __call__(self, statement: str) -> list[tuple[str | None, ...]]:
        self.statements.append(statement)
        if self.failing and self.failing in statement:
            raise DatabaseError("ERROR 1142 (42000): CREATE command denied")
        if statement == "SELECT VERSION()":
            return [(self.version,)]
        if statement == "SELECT CURRENT_USER()":
            return [(self.user,)]
        if statement == "SHOW GRANTS FOR CURRENT_USER()":
            return [(line,) for line in self.grants]
        if "APPLICABLE_ROLES" in statement:
            return [(role,) for role in self.roles]
        if statement.startswith("SHOW GRANTS FOR `"):
            role = statement.removeprefix("SHOW GRANTS FOR `").removesuffix("`")
            return [(line,) for line in self.roles[role]]
        if "Ssl_cipher" in statement:
            return [("Ssl_cipher", self.cipher)]
        if "SCHEMATA" in statement:
            return [(self.charset, f"{self.charset}_general_ci")]
        if "information_schema.TABLES" in statement:
            return [(table,) for table in self.tables]
        if "innodb_encrypt_tables" in statement:
            return [(self.encrypt,)]
        if "PLUGINS" in statement:
            return [(plugin,) for plugin in self.plugins]
        return []


def texts(findings: list[Finding]) -> list[str]:
    return [finding.text(lambda message: message) for finding in findings]


class GrantTests(SimpleTestCase):
    """NFA-066: all rights on the one database, none beyond it."""

    def test_the_rights_of_a_fitting_user_pass(self) -> None:
        report = inspect_account(FakeServer(), "rentalars")
        self.assertTrue(report.is_fit, texts(report.problems))

    def test_root_is_refused_by_name(self) -> None:
        report = inspect_account(FakeServer(user="root@localhost"), "rentalars")
        self.assertFalse(report.is_fit)
        self.assertIn("administrator of the database server", texts(report.problems)[0])

    def test_rights_on_the_whole_server_are_refused_whatever_the_name(self) -> None:
        server = FakeServer(
            user="rentalars_admin@%",
            grants=[
                "GRANT ALL PRIVILEGES ON *.* TO `rentalars_admin`@`%` IDENTIFIED BY PASSWORD '*1' WITH GRANT OPTION"
            ],
        )
        problems = texts(inspect_account(server, "rentalars").problems)
        self.assertIn("The user rentalars_admin@% has rights on the whole database server: ALL PRIVILEGES.", problems)

    def test_a_single_server_right_is_enough_to_refuse(self) -> None:
        server = FakeServer(
            grants=[
                "GRANT PROCESS ON *.* TO `rentalars`@`%`",
                "GRANT ALL PRIVILEGES ON `rentalars`.* TO `rentalars`@`%`",
            ]
        )
        self.assertIn("PROCESS", texts(inspect_account(server, "rentalars").problems)[0])

    def test_rights_on_other_databases_are_refused(self) -> None:
        server = FakeServer(
            grants=[
                "GRANT USAGE ON *.* TO `rentalars`@`%`",
                "GRANT ALL PRIVILEGES ON `rentalars`.* TO `rentalars`@`%`",
                "GRANT SELECT ON `buchhaltung`.`kunden` TO `rentalars`@`%`",
            ]
        )
        self.assertIn("other databases: buchhaltung", texts(inspect_account(server, "rentalars").problems)[0])

    def test_rights_through_a_role_count(self) -> None:
        server = FakeServer(
            grants=[
                "GRANT `dba` TO `rentalars`@`%`",
                "GRANT USAGE ON *.* TO `rentalars`@`%`",
                "GRANT ALL PRIVILEGES ON `rentalars`.* TO `rentalars`@`%`",
                "SET DEFAULT ROLE `dba` FOR `rentalars`@`%`",
            ],
            roles={
                "dba": ["GRANT `backup` TO `dba`", "GRANT SELECT ON *.* TO `dba`"],
                "backup": ["GRANT RELOAD ON *.* TO `backup`"],
            },
        )
        problems = texts(inspect_account(server, "rentalars").problems)
        self.assertIn("The role dba has rights on the whole database server: SELECT.", problems)
        self.assertIn("The role backup has rights on the whole database server: RELOAD.", problems)

    def test_proxy_rights_are_refused(self) -> None:
        problems, _ = judge_grants(["GRANT PROXY ON ''@'%' TO 'rentalars'@'%'"], "rentalars", Finding("X"))
        self.assertEqual(texts(problems), ["X may act as other users (PROXY)."])

    def test_a_line_that_cannot_be_judged_is_refused(self) -> None:
        problems, _ = judge_grants(["REVOKE SOMETHING NEW"], "rentalars", Finding("X"))
        self.assertIn("cannot judge", texts(problems)[0])

    def test_column_rights_with_commas_are_read_as_one_right(self) -> None:
        problems, roles = judge_grants(
            ["GRANT SELECT (`a`, `b`), INSERT ON `rentalars`.`t` TO `rentalars`@`%`"], "rentalars", Finding("X")
        )
        self.assertEqual((problems, roles), ([], []))

    def test_database_names_with_wildcards(self) -> None:
        self.assertTrue(names_only("rentalars_db", "rentalars_db"))
        self.assertTrue(names_only("rentalars\\_db", "rentalars_db"))
        self.assertFalse(names_only("rentalars%", "rentalars_db"))
        self.assertFalse(names_only("rentalars\\_%", "rentalars_db"))
        self.assertFalse(names_only("andere", "rentalars_db"))

    def test_the_problems_end_with_the_statement_that_creates_a_fitting_user(self) -> None:
        server = FakeServer(grants=["GRANT ALL PRIVILEGES ON *.* TO `rentalars`@`%`"])
        self.assertIn(
            "GRANT ALL PRIVILEGES ON `rentalars`.* TO 'rentalars'@'%';",
            texts(inspect_account(server, "rentalars").problems)[-1],
        )


class ServerAndDatabaseTests(SimpleTestCase):
    def test_mysql_is_refused(self) -> None:
        report = inspect_account(FakeServer(version="8.4.2"), "rentalars")
        self.assertIn("not MariaDB", texts(report.problems)[0])

    def test_an_old_mariadb_is_refused(self) -> None:
        report = inspect_account(FakeServer(version="10.5.27-MariaDB"), "rentalars")
        self.assertIn("too old", texts(report.problems)[0])

    def test_a_connection_without_tls_is_refused_when_tls_was_asked_for(self) -> None:
        self.assertFalse(inspect_account(FakeServer(), "rentalars", expect_tls=True).is_fit)
        encrypted = inspect_account(FakeServer(cipher="TLS_AES_256_GCM_SHA384"), "rentalars", expect_tls=True)
        self.assertTrue(encrypted.is_fit)
        self.assertIn("nobody checked whose certificate", texts(encrypted.notes)[0])

    def test_another_character_set_is_refused(self) -> None:
        report = inspect_account(FakeServer(charset="latin1"), "rentalars")
        self.assertEqual([problem.code for problem in report.problems], ["charset"])

    def test_a_new_installation_needs_an_empty_database(self) -> None:
        self.assertTrue(inspect_account(FakeServer(), "rentalars", require_empty=True).is_fit)
        foreign = inspect_account(FakeServer(tables=["kunden"]), "rentalars", require_empty=True)
        self.assertIn("is not empty", texts(foreign.problems)[0])
        own = inspect_account(FakeServer(tables=["django_migrations"]), "rentalars", require_empty=True)
        self.assertIn("already holds the data of a Rentalars", texts(own.problems)[0])

    def test_the_encryption_of_the_server_is_reported(self) -> None:
        plain = inspect_account(FakeServer(), "rentalars")
        self.assertFalse(plain.encrypts_tables)
        self.assertIn("The server does not encrypt its tables.", texts(plain.notes))
        encrypting = inspect_account(FakeServer(encrypt="ON", plugins=["file_key_management"]), "rentalars")
        self.assertTrue(encrypting.encrypts_tables)
        self.assertIn("keys: file_key_management", texts(encrypting.notes)[-1])

    def test_the_trial_drops_its_tables_also_when_it_fails(self) -> None:
        server = FakeServer(failing="FOREIGN KEY")
        problems = try_tables(server, "rentalars@%", "rentalars")
        self.assertIn("cannot create and change tables", texts(problems)[0])
        self.assertTrue(server.statements[-1].startswith("DROP TABLE IF EXISTS"))
        self.assertEqual(try_tables(FakeServer(), "rentalars@%", "rentalars"), [])

    def test_the_messages_of_the_scripts_are_german(self) -> None:
        translate = german()
        self.assertEqual(
            translate("The server does not encrypt its tables."), "Der Server verschlüsselt seine Tabellen nicht."
        )


class FingerprintTests(RentalarsTestCase):
    """NFA-068: the comparison before switching to a moved or encrypted database."""

    def test_the_fingerprint_changes_with_every_value_and_not_with_the_order(self) -> None:
        product = make_product("L-001", "Scheinwerfer")
        make_product("L-002", "Nebel")
        before = database_fingerprint()["tables"]
        self.assertEqual(before["products_product"]["rows"], Product.objects.count())
        product.name = "Scheinwerfer!"
        product.save()
        changed = database_fingerprint()["tables"]
        self.assertNotEqual(before["products_product"]["checksum"], changed["products_product"]["checksum"])
        self.assertEqual(before["accounts_apitoken"], changed["accounts_apitoken"])

    def test_the_command_prints_json(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            call_command("database_fingerprint", stdout=output)
        self.assertIn("django_migrations", json.loads(output.getvalue())["tables"])
