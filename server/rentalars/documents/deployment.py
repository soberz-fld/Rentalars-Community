# SPDX-License-Identifier: GPL-3.0-or-later
"""The deployment view of a project as PDF "Einsatzübersicht" (PRJ-081, AUT-025).

A quick summary of a job for the crew: when and where, the course, the
venue, one's own deployment, the crew with the contact data one may see,
one's own times. It is made with WeasyPrint like the documents of the
project and looks like them – letterhead with logo, company data in the
footer, the fonts of the installation (NFA-050); logo and additional footer
are those of the template of the crew disposition (DOK-004, DOK-005).

Unlike the documents it is not stored and gets no number: it shows the
deployment view as it is at that moment, with the time it was printed.

* From the tab "Deployment" it is the view of the person who prints it –
  exactly what the tab shows them (``projects.deployment``): planners see
  the whole crew with every contact; crew and freelancers their own
  deployment and the contact data colleagues released. Never a price, a
  rate or the customer (AUT-023).
* Sent along with a mail (EML-025) it is the neutral view of any colleague
  (``projects.deployment.neutral``): no own deployment, no own times,
  contact data only as released (PER-019).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from rentalars.core.i18n import file_name as download_name
from rentalars.documents.content import company_data
from rentalars.projects.deployment import DeploymentPicture, deployment_picture, neutral
from rentalars.projects.models import Project


def file_name(project: Project) -> str:
    """The name of the PDF, like those of the packlist and the price overview: ``Einsatzuebersicht-2027-0042.pdf``."""
    return download_name("deployment_view", project.number, extension="pdf")


def render_deployment_html(picture: DeploymentPicture) -> str:
    """The HTML document the PDF is made from."""
    from rentalars.documents.models import DocumentKind
    from rentalars.documents.pdf import _logo_url
    from rentalars.documents.services import template_for
    from rentalars.packing.pdf import _font_url

    template = template_for(DocumentKind.CREW_SHEET)
    return render_to_string(
        "documents/deployment_pdf.html",
        {
            "picture": picture,
            "project": picture.project,
            "company": company_data(),
            "footer": template.footer,
            "logo": _logo_url() if template.show_logo else "",
            "printed_at": timezone.localtime(),
            "fonts": {
                "regular": _font_url("barlow-latin-400-normal.woff2"),
                "semibold": _font_url("barlow-latin-600-normal.woff2"),
                "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
            },
        },
    )


def render_deployment_pdf(picture: DeploymentPicture) -> bytes:
    """The deployment view as PDF bytes."""
    from weasyprint import HTML

    return HTML(string=render_deployment_html(picture), base_url=str(settings.BASE_DIR)).write_pdf()


def deployment_pdf(project: Project, *, rights: Any, user: Any) -> bytes:
    """The PDF of the deployment view as the user sees it on the tab (PRJ-081)."""
    return render_deployment_pdf(deployment_picture(project, rights=rights, user=user))


def deployment_pdf_for_mail(project: Project) -> bytes:
    """The PDF of the deployment view to send along with a mail: as any colleague sees it (PRJ-081, EML-025)."""
    return render_deployment_pdf(neutral(project))
