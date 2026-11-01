# SPDX-License-Identifier: GPL-3.0-or-later
"""WSGI entry point: the application server (Gunicorn) imports ``application``."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rentalars.settings")

application = get_wsgi_application()

# Read URL table, language file and templates now, not during the first
# request of each worker process (NFA-012), and keep the garbage collector
# from looking through all of that again and again (NFA-013). Both are
# explained in rentalars/core/warmup.py.
# (The import can only come after Django is set up, hence E402.)
from rentalars.core.warmup import set_startup_objects_aside, warm_up  # noqa: E402

warm_up()
set_startup_objects_aside()
