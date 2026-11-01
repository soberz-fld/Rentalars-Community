# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that a database account is fit for Rentalars – and no more than that (NFA-066).

Rentalars needs every right on its own database and nothing else. An account
that can do more – the administrator ``root``, or any other account with
rights on the whole server or on further databases – is refused. If the
application is ever attacked, the damage then stays inside its own database,
and the password in the configuration file cannot open anything else.

The judgement is made from what the server itself says about the account
(``SHOW GRANTS``), including the rights the account gets through roles. The
name alone would not do: an administrator account can be called anything.

This module is used in two ways:

* By the server scripts – installation, ``rentalars move-database``,
  ``rentalars status`` – **before** anything is written, when Rentalars and
  its Python libraries may not be installed yet. Then it runs as a script
  with the system's Python and talks to the server through the ``mariadb``
  command line client::

      python3 rentalars/core/database_account.py --client-file client.cnf --database rentalars

  For that reason it imports nothing but the standard library at module
  level. Its messages come in German from the application's own translation
  file.

* By the self-check of the running application (NFA-037) through
  :func:`inspect_account` with a Django cursor.
"""

from __future__ import annotations

import argparse
import contextlib
import gettext as stdlib_gettext
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

#: The oldest MariaDB that Rentalars runs on (Django 5.2 needs 10.5; 10.6 is
#: the oldest long-term version that was still maintained in 2026).
MINIMUM_MARIADB = (10, 6)
MINIMUM_TEXT = "{}.{}".format(*MINIMUM_MARIADB)

#: The account name that is always refused, whatever its rights (an explicit
#: requirement; the rights check would refuse it anyway).
ADMINISTRATOR_NAMES = frozenset({"root"})

#: Hosts that mean "the MariaDB on this server".
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})


def gettext_noop(message: str) -> str:
    """Mark a text for translation without translating it (found by ``makemessages``)."""
    return message


# --- Results --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One sentence of the result: an English text with placeholders, and their values."""

    message: str
    params: dict[str, object] = field(default_factory=dict)
    #: A short name for findings that the caller acts on, e.g. ``"charset"``.
    code: str = ""

    def text(self, translate: Callable[[str], str]) -> str:
        """The sentence in the language of ``translate``."""
        params = {key: _translated(value, translate) for key, value in self.params.items()}
        return translate(self.message) % params if params else translate(self.message)


def _translated(value: object, translate: Callable[[str], str]) -> object:
    """Translate a value that is itself a finding (e.g. "the role x"), leave the rest."""
    return value.text(translate) if isinstance(value, Finding) else value


@dataclass
class Report:
    """What was found out about an account and its database."""

    database: str
    user: str = ""
    server_version: str = ""
    tls_cipher: str = ""
    charset: str = ""
    collation: str = ""
    table_count: int = 0
    holds_rentalars: bool = False
    encrypts_tables: bool = False
    encryption_setting: str = ""
    key_management: str = ""
    #: Reasons to refuse the account. Empty means: fit for Rentalars.
    problems: list[Finding] = field(default_factory=list)
    #: Things worth knowing that do not stop anything.
    notes: list[Finding] = field(default_factory=list)

    @property
    def is_fit(self) -> bool:
        """Whether Rentalars may use the account."""
        return not self.problems


#: Runs one SQL statement and returns its rows; every value as text (``None`` for NULL).
Query = Callable[[str], list[tuple[str | None, ...]]]


# --- Rights --------------------------------------------------------------------------------------

_IDENTIFIER = r"(?:`(?:[^`]|``)*`|'(?:[^']|'')*'|[^\s.`'@]+|\*)"
_PROXY_GRANT = re.compile(r"^GRANT PROXY ON ")
_OBJECT_GRANT = re.compile(
    rf"^GRANT (?P<privileges>.+?) ON (?:(?P<routine>FUNCTION|PROCEDURE|PACKAGE BODY|PACKAGE) )?"
    rf"(?P<database>{_IDENTIFIER})\.(?P<object>{_IDENTIFIER}) TO ",
    re.S,
)
_ROLE_GRANT = re.compile(rf"^GRANT (?P<role>{_IDENTIFIER}) TO ")
_DEFAULT_ROLE = re.compile(r"^SET DEFAULT ROLE ")


def unquote(identifier: str) -> str:
    """``rentalars`` from `` `rentalars` `` or ``'rentalars'``."""
    if len(identifier) >= 2 and identifier[0] == identifier[-1] and identifier[0] in "`'":
        quote = identifier[0]
        return identifier[1:-1].replace(quote * 2, quote)
    return identifier


def _split_privileges(text: str) -> list[str]:
    """``SELECT (a, b), INSERT`` → ``["SELECT", "INSERT"]``: commas inside brackets do not split."""
    privileges, depth, current = [], 0, ""
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            privileges.append(current)
            current = ""
        else:
            current += character
    privileges.append(current)
    return [re.sub(r"\s*\(.*\)\s*$", "", privilege).strip().upper() for privilege in privileges if privilege.strip()]


def names_only(pattern: str, database: str) -> bool:
    """Whether a database name from a grant means exactly ``database`` and nothing more.

    In a grant, ``_`` and ``%`` are wildcards unless escaped with a backslash.
    Almost every real grant writes ``rentalars_db`` without escaping the
    underscore; that is accepted as meaning the one database. A ``%`` is not.
    """
    if pattern == database:
        return "%" not in pattern
    unescaped = re.sub(r"\\(.)", r"\1", pattern)
    has_open_percent = re.search(r"(?<!\\)%", pattern) is not None
    return unescaped == database and not has_open_percent


def judge_grants(lines: Iterable[str], database: str, who: Finding) -> tuple[list[Finding], list[str]]:
    """Judge the grants of one account or role.

    Returns the problems found and the roles that are granted on top (whose
    grants have to be judged as well).
    """
    problems: list[Finding] = []
    roles: list[str] = []
    server_wide: list[str] = []
    elsewhere: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or _DEFAULT_ROLE.match(line):
            continue
        if _PROXY_GRANT.match(line):
            problems.append(Finding(gettext_noop("%(who)s may act as other users (PROXY)."), {"who": who}))
            continue
        grant = _OBJECT_GRANT.match(line)
        if grant:
            privileges = _split_privileges(grant["privileges"])
            target = unquote(grant["database"])
            if target == "*":
                server_wide.extend(privilege for privilege in privileges if privilege != "USAGE")
            elif not names_only(target, database):
                elsewhere.append(target)
            continue
        role = _ROLE_GRANT.match(line)
        if role:
            roles.append(unquote(role["role"]))
            continue
        problems.append(
            Finding(gettext_noop("Rentalars cannot judge this line of the rights: %(line)s"), {"line": line})
        )
    if server_wide:
        problems.append(
            Finding(
                gettext_noop("%(who)s has rights on the whole database server: %(privileges)s."),
                {"who": who, "privileges": ", ".join(dict.fromkeys(server_wide))},
            )
        )
    if elsewhere:
        problems.append(
            Finding(
                gettext_noop("%(who)s also has rights on other databases: %(databases)s."),
                {"who": who, "databases": ", ".join(dict.fromkeys(elsewhere))},
            )
        )
    return problems, roles


def judge_account(query: Query, user: str, database: str) -> list[Finding]:
    """Judge the rights of the connected account, including all roles it can use."""
    problems: list[Finding] = []
    is_administrator = user.split("@", 1)[0].lower() in ADMINISTRATOR_NAMES
    if is_administrator:
        problems.append(
            Finding(
                gettext_noop(
                    "The user %(user)s is the administrator of the database server and is never used by Rentalars."
                ),
                {"user": user.split("@", 1)[0]},
            )
        )
    account = Finding(gettext_noop("The user %(user)s"), {"user": user})
    own, pending = judge_grants([row[0] or "" for row in query("SHOW GRANTS FOR CURRENT_USER()")], database, account)
    problems.extend(own)
    # Every role the account can switch on counts, not only the default one.
    pending += [row[0] or "" for row in query("SELECT ROLE_NAME FROM information_schema.APPLICABLE_ROLES")]
    seen: set[str] = set()
    while pending:
        role = pending.pop()
        if not role or role in seen:
            continue
        seen.add(role)
        role_finding = Finding(gettext_noop("The role %(role)s"), {"role": role})
        try:
            lines = [row[0] or "" for row in query(f"SHOW GRANTS FOR {quote(role)}")]
        except DatabaseError as error:
            problems.append(
                Finding(
                    gettext_noop("The rights of the role %(role)s cannot be read: %(error)s"),
                    {"role": role, "error": str(error)},
                )
            )
            continue
        found, more = judge_grants(lines, database, role_finding)
        problems.extend(found)
        pending.extend(more)
    if problems and not is_administrator:
        problems.append(
            Finding(
                gettext_noop(
                    "Rentalars needs a user with all rights on the database %(database)s and no others, for instance:"
                    " CREATE USER 'rentalars'@'%%' IDENTIFIED BY '…'; GRANT ALL PRIVILEGES ON `%(database)s`.* TO"
                    " 'rentalars'@'%%';"
                ),
                {"database": database},
            )
        )
    return problems


def quote(identifier: str) -> str:
    """Quote a name for SQL with backticks."""
    return "`" + identifier.replace("`", "``") + "`"


# --- The whole inspection ------------------------------------------------------------------------


class DatabaseError(Exception):
    """A statement failed; the message is the server's."""


def parse_version(version: str) -> tuple[int, int]:
    """``(11, 8)`` from ``11.8.3-MariaDB-ubu2604``."""
    match = re.match(r"(\d+)\.(\d+)", version)
    return (int(match[1]), int(match[2])) if match else (0, 0)


def inspect_account(
    query: Query,
    database: str,
    *,
    expect_tls: bool = False,
    tls_verified: bool = False,
    require_empty: bool = False,
) -> Report:
    """Find out everything about the connected account and its database.

    Args:
        query: Runs a statement on the connection that is to be judged.
        database: The database Rentalars is to use.
        expect_tls: The connection was asked to be encrypted; refuse it if it is not.
        tls_verified: The server certificate is checked against a CA (only for the note).
        require_empty: For a new installation: the database must not hold tables.
    """
    report = Report(database=database)
    report.server_version = query("SELECT VERSION()")[0][0] or ""
    report.user = query("SELECT CURRENT_USER()")[0][0] or ""

    if "mariadb" not in report.server_version.lower():
        report.problems.append(
            Finding(
                gettext_noop(
                    "The server is not MariaDB but %(version)s. Rentalars needs MariaDB %(minimum)s or newer."
                ),
                {"version": report.server_version, "minimum": MINIMUM_TEXT},
            )
        )
    elif parse_version(report.server_version) < MINIMUM_MARIADB:
        report.problems.append(
            Finding(
                gettext_noop("MariaDB %(version)s is too old. Rentalars needs MariaDB %(minimum)s or newer."),
                {"version": report.server_version, "minimum": MINIMUM_TEXT},
            )
        )

    report.problems.extend(judge_account(query, report.user, database))

    status = query("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
    report.tls_cipher = (status[0][1] or "") if status else ""
    if report.tls_cipher:
        if tls_verified:
            report.notes.append(
                Finding(
                    gettext_noop(
                        "The connection is encrypted (%(cipher)s); the certificate of the server was checked."
                    ),
                    {"cipher": report.tls_cipher},
                )
            )
        else:
            report.notes.append(
                Finding(
                    gettext_noop(
                        "The connection is encrypted (%(cipher)s), but nobody checked whose certificate the server shows."
                        " Against eavesdropping that is enough; against an attacker in the network it is not. A CA file"
                        " closes that gap."
                    ),
                    {"cipher": report.tls_cipher},
                )
            )
    elif expect_tls:
        report.problems.append(Finding(gettext_noop("The connection is not encrypted, although TLS was asked for.")))

    schema = query(
        "SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA"
        " WHERE SCHEMA_NAME = DATABASE()"
    )
    if schema:
        report.charset, report.collation = schema[0][0] or "", schema[0][1] or ""
    tables = [
        row[0] or ""
        for row in query("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")
    ]
    report.table_count = len(tables)
    report.holds_rentalars = "django_migrations" in tables
    if report.charset and report.charset != "utf8mb4":
        report.problems.append(
            Finding(
                gettext_noop(
                    "The database %(database)s uses the character set %(charset)s; Rentalars needs utf8mb4. On an empty"
                    " database: ALTER DATABASE `%(database)s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                ),
                {"database": database, "charset": report.charset},
                code="charset",
            )
        )
    if require_empty and tables:
        if report.holds_rentalars:
            report.problems.append(
                Finding(
                    gettext_noop(
                        "The database %(database)s already holds the data of a Rentalars. Install into an empty database"
                        " and restore a backup afterwards (docs/betrieb/sicherung.md)."
                    ),
                    {"database": database},
                )
            )
        else:
            report.problems.append(
                Finding(
                    gettext_noop(
                        "The database %(database)s is not empty: it holds %(count)s tables. Rentalars needs an empty one."
                    ),
                    {"database": database, "count": len(tables)},
                )
            )

    # At-rest encryption is a matter of the server (NFA-067). Every account
    # may read these two values; the exact state of each table may not be.
    setting = query("SELECT @@GLOBAL.innodb_encrypt_tables")
    report.encryption_setting = (setting[0][0] or "") if setting else ""
    plugins = query(
        "SELECT PLUGIN_NAME FROM information_schema.PLUGINS WHERE PLUGIN_TYPE = 'ENCRYPTION' AND PLUGIN_STATUS = 'ACTIVE'"
    )
    report.key_management = ", ".join(row[0] or "" for row in plugins)
    report.encrypts_tables = bool(report.key_management) and report.encryption_setting.upper() in {"ON", "FORCE", "1"}
    if report.encrypts_tables:
        report.notes.append(
            Finding(
                gettext_noop("The server encrypts its tables (innodb_encrypt_tables = %(setting)s, keys: %(plugin)s)."),
                {"setting": report.encryption_setting, "plugin": report.key_management},
            )
        )
    else:
        report.notes.append(Finding(gettext_noop("The server does not encrypt its tables.")))
    return report


#: Every kind of statement Rentalars runs when it brings its database up to date.
TRIAL_STATEMENTS = (
    "CREATE TABLE {a} (id BIGINT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(50) NOT NULL) ENGINE=InnoDB",
    "CREATE TABLE {b} (id BIGINT AUTO_INCREMENT PRIMARY KEY, a_id BIGINT NOT NULL,"
    " CONSTRAINT {fk} FOREIGN KEY (a_id) REFERENCES {a} (id)) ENGINE=InnoDB",
    "CREATE INDEX {index} ON {a} (name)",
    "ALTER TABLE {a} ADD COLUMN note VARCHAR(20) NULL",
    "INSERT INTO {a} (name) VALUES ('Rentalars')",
    "INSERT INTO {b} (a_id) SELECT id FROM {a}",
    "UPDATE {a} SET note = 'checked'",
    "DELETE FROM {b}",
    "DROP TABLE {b}",
    "DROP TABLE {a}",
)


def try_tables(query: Query, user: str, database: str) -> list[Finding]:
    """Create, change and drop two small tables – the proof that migrations will work."""
    prefix = f"rentalars_check_{secrets.token_hex(4)}"
    names = {
        "a": quote(f"{prefix}_a"),
        "b": quote(f"{prefix}_b"),
        "fk": quote(f"{prefix}_fk"),
        "index": quote(f"{prefix}_name"),
    }
    try:
        for statement in TRIAL_STATEMENTS:
            query(statement.format(**names))
    except DatabaseError as error:
        for name in (names["b"], names["a"]):
            with contextlib.suppress(DatabaseError):
                query(f"DROP TABLE IF EXISTS {name}")
        return [
            Finding(
                gettext_noop("The user %(user)s cannot create and change tables in %(database)s: %(error)s"),
                {"user": user, "database": database, "error": str(error)},
            )
        ]
    return []


# --- Command line ----------------------------------------------------------------------------------


def command_line_query(client_file: str, database: str) -> Query:
    """A :data:`Query` that runs each statement with the ``mariadb`` client."""

    def run(statement: str) -> list[tuple[str | None, ...]]:
        result = subprocess.run(  # noqa: S603 - the statement is ours
            [  # noqa: S607 - the client of the system, found on its PATH
                "mariadb",
                f"--defaults-extra-file={client_file}",
                "--batch",
                "--raw",
                "--skip-column-names",
                "--connect-timeout=10",
                database,
                "-e",
                statement,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip().splitlines()
            raise DatabaseError(message[-1] if message else f"mariadb exited with {result.returncode}")
        return [
            tuple(None if value == "NULL" else value for value in line.split("\t"))
            for line in result.stdout.splitlines()
        ]

    return run


def _only_charset_problem(report: Report) -> bool:
    """Whether the character set is the one thing that keeps the account from being fit."""
    return all(problem.code == "charset" for problem in report.problems)


def german() -> Callable[[str], str]:
    """The translation of the application into German, read without Django."""
    locale_dir = Path(__file__).resolve().parents[2] / "locale"
    return stdlib_gettext.translation("django", localedir=str(locale_dir), languages=["de"], fallback=True).gettext


def operator_translation() -> Callable[[str], str]:
    """UIX-029: German when the operator's locale is German (as in deploy/lib.sh, ``operator_language``), else English."""
    locale = (
        os.environ.get("RENTALARS_LANG")
        or os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    return german() if locale.startswith("de") else (lambda message: message)


def main(argv: list[str] | None = None) -> int:
    """Check an account from the command line; exit status 0 fit, 1 refused, 2 no connection."""
    parser = argparse.ArgumentParser(description="Check a MariaDB account for Rentalars (NFA-066).")
    parser.add_argument("--client-file", required=True, help="[client] file with host, port, user, password, TLS")
    parser.add_argument("--database", required=True)
    parser.add_argument("--expect-tls", action="store_true")
    parser.add_argument("--tls-verified", action="store_true")
    parser.add_argument("--require-empty", action="store_true", help="refuse a database that holds tables")
    parser.add_argument("--fix-charset", action="store_true", help="switch an EMPTY database to utf8mb4")
    parser.add_argument("--try-tables", action="store_true", help="create and drop two tables as a trial")
    parser.add_argument("--brief", action="store_true", help="one line, for rentalars status")
    arguments = parser.parse_args(argv)
    translate = operator_translation()
    query = command_line_query(arguments.client_file, arguments.database)

    def inspect() -> Report:
        return inspect_account(
            query,
            arguments.database,
            expect_tls=arguments.expect_tls,
            tls_verified=arguments.tls_verified,
            require_empty=arguments.require_empty,
        )

    try:
        report = inspect()
    except DatabaseError as error:
        print(translate(gettext_noop("No connection to the database: %(error)s")) % {"error": error})
        return 2
    fixable = report.charset and report.charset != "utf8mb4" and report.table_count == 0
    if arguments.fix_charset and fixable and _only_charset_problem(report):
        try:
            query(f"ALTER DATABASE {quote(arguments.database)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        except DatabaseError as error:
            report.problems.append(
                Finding(
                    gettext_noop("The character set of %(database)s could not be changed: %(error)s"),
                    {"database": arguments.database, "error": str(error)},
                )
            )
        else:
            report = inspect()
            report.notes.append(
                Finding(
                    gettext_noop("The character set of %(database)s was changed to utf8mb4."),
                    {"database": arguments.database},
                )
            )
    if arguments.try_tables and report.is_fit:
        report.problems.extend(try_tables(query, report.user, arguments.database))

    if arguments.brief:
        state = gettext_noop("fit") if report.is_fit else gettext_noop("REFUSED")
        tls = gettext_noop("encrypted connection") if report.tls_cipher else gettext_noop("unencrypted connection")
        stored = gettext_noop("tables encrypted") if report.encrypts_tables else gettext_noop("tables not encrypted")
        version = "{}.{}".format(*parse_version(report.server_version))
        print(f"{report.user}, MariaDB {version}, {translate(tls)}, {translate(stored)}: {translate(state)}")
        for problem in report.problems:
            print(f"  {problem.text(translate)}")
        return 0 if report.is_fit else 1

    print(
        translate(gettext_noop("Account: %(user)s on %(version)s"))
        % {"user": report.user, "version": report.server_version}
    )
    for note in report.notes:
        print(f"  {note.text(translate)}")
    refused = translate(gettext_noop("Refused:"))
    for problem in report.problems:
        print(f"  {refused} {problem.text(translate)}")
    return 0 if report.is_fit else 1


if __name__ == "__main__":
    sys.exit(main())
