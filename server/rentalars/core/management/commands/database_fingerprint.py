# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``database_fingerprint``: a checksum of every table (NFA-067, NFA-068).

Moving the database to another server (``rentalars move-database``) or
encrypting it (``rentalars encryption enable``) must not change a single
value. Both run this command before and after and compare the two outputs:
for every table the number of rows and a SHA-256 checksum over all values.

The checksum is computed here, from the values as Python reads them, and not
by the database server (``CHECKSUM TABLE``): two MariaDB versions may compute
that differently for the same data. It does not depend on the order of the
rows either – each row is hashed on its own and the hashes are added up – so
a server that returns them in another order gives the same result.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection

#: Rows fetched at a time: a big table is never held in memory as a whole.
BATCH_SIZE = 2000
_MODULUS = 2**256


def table_fingerprint(table: str) -> dict[str, Any]:
    """Return ``{"rows": …, "checksum": …}`` for one table."""
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        columns = [column.name for column in connection.introspection.get_table_description(cursor, table)]
        cursor.execute(f"SELECT {', '.join(quote(column) for column in columns)} FROM {quote(table)}")  # noqa: S608 - names from the introspection, quoted
        total = rows = 0
        while batch := cursor.fetchmany(BATCH_SIZE):
            for row in batch:
                digest = hashlib.sha256(repr(tuple(row)).encode("utf-8")).digest()
                total = (total + int.from_bytes(digest, "big")) % _MODULUS
                rows += 1
    return {"rows": rows, "checksum": f"{total:064x}"}


def database_fingerprint() -> dict[str, Any]:
    """Return the fingerprint of every table of the database."""
    tables = sorted(connection.introspection.table_names())
    return {"tables": {table: table_fingerprint(table) for table in tables}}


class Command(BaseCommand):
    """Prints the row count and checksum of every table as JSON."""

    help = "Prints the number of rows and a checksum of every table, to compare two copies of the database."

    def handle(self, *args: Any, **options: Any) -> None:
        """Print the fingerprint as JSON."""
        self.stdout.write(json.dumps(database_fingerprint(), indent=1, sort_keys=True))
