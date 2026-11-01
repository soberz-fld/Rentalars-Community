# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``core`` module."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    """Shared building blocks: audit log, number ranges, settings, first-run setup."""

    name = "rentalars.core"
    label = "core"
    verbose_name = _("System")

    def ready(self) -> None:
        """Install the start data once after the database tables exist; make the shared tasks known."""
        # NFA-077: "migrate" stops with a clear message on a database too old to update (checks of the database).
        from rentalars.core import checks  # noqa: F401
        from rentalars.core.defaults import install_defaults_after_migrate
        from rentalars.core.jobs import register

        post_migrate.connect(install_defaults_after_migrate, sender=self)
        # UIX-024: /projects/2026-0042/ and /products/L-010/ – registered before any address is read.
        from django.urls import register_converter

        from rentalars.core.converters import ArticleNumberConverter, ProjectNumberConverter

        register_converter(ProjectNumberConverter, "project")
        register_converter(ArticleNumberConverter, "product")
        # S1: Pillow reads only the picture formats the program needs.
        from rentalars.core.pictures import restrict_decoders

        restrict_decoders()
        # B12: Django's "---------" in a selection becomes "– please choose –".
        from rentalars.core.choices import replace_dashes

        replace_dashes()
        # NFA-041: imports and the full export run in the background.
        register("import", "rentalars.core.imports:run_job")
        register("export", "rentalars.core.export:run_job")
        # ADM-010: a backup from the browser, in the format of "rentalars backup".
        register("backup", "rentalars.core.backup:run_job")
        # UIX-029: a management command run by "sudo rentalars …" speaks the operator's language
        # (deploy/lib.sh, "manage" passes RENTALARS_LANG); the application itself is not affected.
        import os

        from django.utils import translation

        language = os.environ.get("RENTALARS_LANG", "")
        if language in ("de", "en"):
            translation.activate(language)
