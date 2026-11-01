#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line entry point for administrative tasks.

Examples::

    python manage.py migrate            # create or update the database tables
    python manage.py runserver          # start the development server
    python manage.py test               # run all automated tests
    python manage.py import_material --help
"""

import os
import sys


def main() -> None:
    """Hand the command line over to Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rentalars.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
