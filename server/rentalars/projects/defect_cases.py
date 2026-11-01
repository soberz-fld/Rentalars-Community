# SPDX-License-Identifier: GPL-3.0-or-later
"""A service case of a defect report (MAT-057, ADM-013).

A defect reported in the material administration, on the item's page, on
return or through the API (MAT-023, PCK-017) becomes a service case – at
once, by the automation "Defektmeldung → Servicefall" (Einstellungen →
Automationen, active by default), or later by hand: the rule may instead put
the report under Projekte → Anfragen, where "Als Servicefall" opens the
form of a new case filled from the report.

What the case gets
    * a title – "Defekt 0042 SM58" or the rule's subject with placeholders –
      and as description what was found defective, where and by whom, with
      the address of the item (the rule's text with placeholders, if any);
    * the customer: for customer material (PRD-043) its owner; else the case
      is *internal* – our own material, no customer (``Project.is_internal``);
    * "reported by": who reported the defect;
    * responsible: the user the rule names (optional);
    * the photo of the report among the files of the case;
    * ``source_defect``: the report, shown on the case and on the item's page.

One report makes one case: a second attempt is refused, and the waiting
inquiry of the report is taken off the list when the case is made.

``projects`` points to ``material`` (``Project.source_defect``) – the usual
direction. ``mail`` is above: the inquiry is looked up through the reverse
relation, never imported.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.projects.models import Project
from rentalars.projects.service_cases import create_case

#: The longest title of a case (``Project.name``).
TITLE_LENGTH = 200


def _reporter(report: Any) -> str:
    user = report.reported_by
    return (user.get_full_name() or user.username) if user is not None else ""


def item_link(report: Any) -> str:
    """The address of the item's page in Rentalars."""
    return f"{settings.RENTALARS_URL}{reverse('material:item_detail', args=[report.item_id])}"


def values_of(report: Any) -> dict[str, str]:
    """The placeholders of a defect report for the texts of a rule (``automations.engine``)."""
    item = report.item
    model = item.material_model
    product = item.product
    return {
        "id": item.display_id,
        "modell": model.name,
        "kurzname": model.display_short_name,
        "produkt": product.name if product is not None else "",
        "seriennummer": item.serial_number,
        "beschreibung": report.description,
        "gefunden": report.context,
        "gemeldet_von": _reporter(report),
        "gemeldet_am": formats.date_format(timezone.localtime(report.reported_at), local_pattern("d.m.Y H:i")),
        "link": item_link(report),
    }


def default_title(report: Any) -> str:
    """Title such as "Defekt 0042 SM58", in the language active (the automations write in that of the documents)."""
    item = report.item
    return (_("Defect %(id)s %(name)s") % {"id": item.display_id, "name": item.material_model.display_short_name})[
        :TITLE_LENGTH
    ]


def default_description(report: Any) -> str:
    """What was found, where, by whom and when – and the address of the item."""
    values = values_of(report)
    lines = [report.description.strip(), ""]
    lines.append(_("Item: %(id)s %(model)s") % {"id": values["id"], "model": values["modell"]})
    if values["seriennummer"]:
        lines.append(_("Serial number: %(serial)s") % {"serial": values["seriennummer"]})
    if values["gefunden"]:
        lines.append(_("Found: %(where)s") % {"where": values["gefunden"]})
    if values["gemeldet_von"]:
        lines.append(
            _("Reported by %(name)s on %(moment)s") % {"name": values["gemeldet_von"], "moment": values["gemeldet_am"]}
        )
    else:
        lines.append(_("Reported on %(moment)s") % {"moment": values["gemeldet_am"]})
    lines.append(values["link"])
    return "\n".join(lines).strip()


def owner_of(report: Any) -> Any:
    """The customer the item belongs to – customer material (PRD-043) – else ``None``."""
    product = report.item.product
    return product.owner if product is not None and product.owner_id else None


def suggestions(report: Any) -> dict[str, Any]:
    """The start values of the form of a new case made of a report by hand."""
    owner = owner_of(report)
    initial: dict[str, Any] = {
        "name": default_title(report),
        "notes": default_description(report),
        "case_contact": _reporter(report)[:250],
    }
    if owner is not None:
        initial["customer"] = owner
    else:
        initial["is_internal"] = True
    return initial


def case_of(report: Any) -> Project | None:
    """The service case made of the report, if there is one."""
    return Project.objects.filter(source_defect=report).order_by("pk").first()


@transaction.atomic
def create_from_defect(report: Any, *, user: Any = None, **fields: Any) -> Project:
    """Make a service case of a defect report – with its photo – and take its inquiry off the list.

    Args:
        report: The ``material.DefectReport``.
        user: Who makes it – ``None`` for an automation.
        **fields: The fields of the case (``service_cases.CASE_FIELDS``); left out: those of :func:`suggestions`.

    Raises:
        ValidationError: The report has a case already, or a value is invalid.
    """
    from rentalars.projects.files import add_file

    # The row of the report is locked until the case is made, so that two requests at
    # once – a form sent twice, two rules – make one case and an error, not two cases.
    type(report)._base_manager.select_for_update().filter(pk=report.pk).first()
    existing = case_of(report)
    if existing is not None:
        raise ValidationError(
            _("The service case %(number)s was made of this defect report already.") % {"number": existing.number}
        )
    values = {**suggestions(report), **fields}
    if values.get("customer") is not None:
        values["is_internal"] = False
    case = create_case(user=user, customer_required=True, **values)
    case.source_defect = report
    case.save(update_fields=["source_defect"])
    if report.photo:
        try:
            with report.photo.open("rb") as handle:
                content = ContentFile(handle.read(), name=report.photo.name.rsplit("/", 1)[-1])
            add_file(case, content, user=user, title=_("Photo of the defect report"))
        except (OSError, ValidationError):
            # The case counts more than the photo; the report keeps it on the item's page.
            pass
    inquiry = inquiry_of(report)
    if inquiry is not None and inquiry.resolved_at is None:
        inquiry.resolved_at = timezone.now()
        inquiry.save(update_fields=["resolved_at"])
    return case


def inquiry_of(report: Any) -> Any:
    """The entry of the report under Projekte → Anfragen (``mail.UnknownTagMail``), if there is one."""
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return report.inquiry
    except ObjectDoesNotExist:
        return None
