# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``packing`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PackingConfig(AppConfig):
    """Packlists, issue and return (chapter 5.8)."""

    name = "rentalars.packing"
    label = "packing"
    verbose_name = _("Packing")

    def ready(self) -> None:
        """Let packing object to project status changes that contradict the packlist (PCK-019).

        PCK-026: a project that becomes confirmed gets its main packlist.
        """
        from django.db.models.signals import post_save

        from rentalars.packing.offline import ensure_packlist_on_confirmation
        from rentalars.packing.services import guard_project_status
        from rentalars.projects import services as project_services

        if guard_project_status not in project_services.status_guards:
            project_services.status_guards.append(guard_project_status)
        post_save.connect(
            ensure_packlist_on_confirmation, sender="projects.Project", dispatch_uid="packing.offline.confirmed"
        )
