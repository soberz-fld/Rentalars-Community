# SPDX-License-Identifier: GPL-3.0-or-later
"""The price overview as PDF and as CSV (DOK-009, EML-025).

The same content as the page "Price overview": groups with their totals and a
short description of what they contain (PRJ-066), on request with all lines
(PRJ-036). Subgroups (PRJ-037) follow their parent, indented in the PDF and
named with their path in the CSV ("Licht › Front-Traverse"); the amount of
a parent includes them. The PDF is made with WeasyPrint like the packlist, from
``projects/price_overview_pdf.html``; the CSV is for a spreadsheet program,
with semicolons and decimal commas (IMP-005). Both are internal working
documents, marked as "not an invoice".

A whole project with subprojects (PRJ-046) shows its own groups first and
then every part that is not cancelled as a block of its own – a heading with
number, name and rental period, the part's groups, the part's subtotal – and
at the end the sum of everything (``projects.family_prices``). Given the
rights of a user, parts the user may not read are left out and the file says
how many. A part shows just itself.

PRJ-088: with ``crew_by_phase`` the personnel is broken down by phase and job
function – per phase its subtotal and one row per job function with places,
hours or days and amount, the lines without phase last. Costs never appear in
these files: the PDF goes to customers by mail (EML-025).
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.utils import timezone

from rentalars.core.models import CompanyProfile
from rentalars.core.money import format_decimal
from rentalars.packing.pdf import _font_url
from rentalars.projects.family_prices import FamilyPrices, family_prices
from rentalars.projects.models import Project


def render_price_overview_html(
    project: Project, *, with_lines: bool = False, rights: Any = None, user: Any = None, crew_by_phase: bool = False
) -> str:
    """The HTML document the PDF is made from."""
    overview = family_prices(project, rights=rights, user=user)
    return render_to_string(
        "projects/price_overview_pdf.html",
        {
            "project": project,
            "overview": overview,
            "planning": overview.own.planning,
            "with_lines": with_lines,
            "crew_by_phase": crew_by_phase,
            "company": CompanyProfile.load(),
            "printed_at": timezone.localtime(),
            "fonts": {
                "regular": _font_url("barlow-latin-400-normal.woff2"),
                "semibold": _font_url("barlow-latin-600-normal.woff2"),
                "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
            },
        },
    )


def render_price_overview_pdf(
    project: Project, *, with_lines: bool = False, rights: Any = None, user: Any = None, crew_by_phase: bool = False
) -> bytes:
    """The price overview of a project as PDF bytes; ``rights`` and ``user`` leave out parts they may not read."""
    from weasyprint import HTML

    html = render_price_overview_html(
        project, with_lines=with_lines, rights=rights, user=user, crew_by_phase=crew_by_phase
    )
    return HTML(string=html).write_pdf()


def render_price_overview_csv(
    project: Project, *, with_lines: bool = True, rights: Any = None, user: Any = None, crew_by_phase: bool = False
) -> str:
    """The price overview as CSV text: one row per line, or per group with ``with_lines=False``.

    PRJ-046: the rows of a part name it in front of their section ("2026-0042-1 › Licht"); a heading row opens
    the part and a row with its subtotal closes it. PRJ-088: ``crew_by_phase`` gives the personnel by phase
    and job function ("Personal › Aufbau") instead of line by line.
    """
    import csv
    import io

    from django.utils.translation import gettext as _
    from django.utils.translation import pgettext

    from rentalars.core.tables import BYTE_ORDER_MARK, csv_text

    overview = family_prices(project, rights=rights, user=user)
    text = io.StringIO()
    text.write(BYTE_ORDER_MARK)
    writer = csv.writer(text, delimiter=";")
    width = 10 if with_lines else 3
    if with_lines:
        writer.writerow(
            [
                pgettext("price overview", "Section"),
                _("Article no."),
                _("Name"),
                _("Quantity"),
                _("Unit"),
                _("Rental days"),
                _("factor"),
                _("Unit price"),
                _("Discount"),
                _("Amount"),
            ]
        )
    else:
        writer.writerow([pgettext("price overview", "Section"), _("Contents"), _("Amount")])

    def labelled(label: Any, amount: Any) -> None:
        writer.writerow([csv_text(label), *[""] * (width - 2), csv_text(amount)])

    for block in overview.blocks:
        if not overview.has_parts:
            _write_planning(writer, block.planning, with_lines=with_lines, crew_by_phase=crew_by_phase)
        elif block is overview.own:
            if not block.is_empty:
                labelled(block.shared_heading, "")
                _write_planning(writer, block.planning, with_lines=with_lines, crew_by_phase=crew_by_phase)
                labelled(_("Total of the shared lines"), block.prices.net_total)
        else:
            labelled(block.heading, "")
            _write_planning(
                writer,
                block.planning,
                with_lines=with_lines,
                prefix=f"{block.project.number} › ",
                crew_by_phase=crew_by_phase,
            )
            labelled(_("Total %(title)s") % {"title": block.title}, block.prices.net_total)

    totals = overview.totals
    for label, amount in [
        (_("Total net"), totals.net_total),
        *[(_("Tax %(name)s") % {"name": tax.tax_rate.name}, tax.tax) for tax in totals.tax_lines],
        (_("Total gross"), totals.gross_total),
        *([(_("Optional lines, not included"), totals.optional_lines_total)] if totals.optional_lines_total else []),
        *(
            [(_("Alternative lines, not included"), totals.alternative_lines_total)]
            if totals.alternative_lines_total
            else []
        ),
    ]:
        labelled(label, amount)
    for note in family_notes(overview):
        labelled(note, "")
    return text.getvalue()


def family_notes(overview: FamilyPrices) -> list[str]:
    """What a whole project's price overview leaves out, in words (PRJ-046, PRJ-049); empty if nothing."""
    from django.utils.translation import gettext as _
    from django.utils.translation import ngettext

    notes = []
    if overview.hidden:
        notes.append(
            ngettext(
                "%(count)s subproject is not included: you may not read it. The sums are without it.",
                "%(count)s subprojects are not included: you may not read them. The sums are without them.",
                overview.hidden,
            )
            % {"count": overview.hidden}
        )
    if overview.cancelled:
        label = _("Cancelled, therefore not included:")
        notes.append(" ".join([label, ", ".join(f"{part.number} {part.name}" for part in overview.cancelled)]))
    return notes


def _write_planning(
    writer: Any, planning: Any, *, with_lines: bool, prefix: str = "", crew_by_phase: bool = False
) -> None:
    """The rows of one project's groups, lines without group, personnel and surcharges.

    ``prefix`` names the part in front of every section of a part's block (PRJ-046). ``crew_by_phase``
    writes the personnel by phase and job function (PRJ-088). PER-009: a crew line names its surcharges for
    night, Sunday and holidays in its name.
    """
    from django.utils.translation import gettext as _

    from rentalars.core.money import format_money
    from rentalars.core.tables import csv_text

    prices = planning.prices

    def lines(block: str, planned_lines: list[Any]) -> None:
        for planned in planned_lines:
            line, price = planned.line, planned.price
            if line.is_covering_subrental:
                continue
            title = line.title
            if line.is_text:
                # A text line is a row of text, without quantity and amount.
                text = f"{title}: {line.note}" if line.note else title
                writer.writerow([csv_text(block), "", csv_text(text), "", "", "", "", "", "", ""])
                continue
            if line.variant:
                # PRJ-075: an optional or alternative line says so; it is not part of the subtotal.
                # PRJ-083: an alternative names the line it could replace.
                label = getattr(planned, "alternative_label", "")
                label = _("alternative to “%(line)s”") % {"line": label} if label else line.get_variant_display()
                title = f"{title} ({label})"
            elif line.taken_over_from_id:
                # PRJ-060: charged once, on the line the pieces come from.
                source = _("Taken over from %(part)s") % {"part": line.taken_over_from.project.number}
                title = f"{title} ({source})"
            if price.is_customer_material:
                # PRJ-096: the customer's own material, taken along without charge – no price.
                title = f"{title} ({_('customer material – taken along')})"
            writer.writerow(
                [
                    csv_text(block),
                    csv_text(line.product.article_number if line.product_id else ""),
                    csv_text(title),
                    csv_text(line.quantity),
                    csv_text(line.unit.abbreviation if line.unit_id else ""),
                    csv_text(price.rental_days),
                    csv_text(price.scale_factor),
                    csv_text(None if price.is_customer_material else line.unit_price),
                    csv_text(price.discount_percent or None),  # PER-026: as it applies
                    csv_text(None if price.is_customer_material else price.amount),
                ]
            )

    def block(name: str, summary: str, amount: Any, planned_lines: list[Any] | None = None) -> None:
        name = prefix + name
        if with_lines:
            if planned_lines is not None:
                lines(name, planned_lines)
            writer.writerow([csv_text(name), "", csv_text(_("Subtotal")), "", "", "", "", "", "", csv_text(amount)])
        else:
            writer.writerow([csv_text(name), csv_text(summary), csv_text(amount)])

    def group_block(group: Any) -> None:
        """PRJ-037: a group named with its path ("Licht › Front-Traverse"), followed by its subgroups.

        A parent's amount includes its subgroups. With lines, its subtotal
        row therefore comes after them; without lines, the parent's row
        comes first and its subgroups follow as the breakdown.
        """
        path = prefix + group.path
        name = path if group.prices.counts_toward_total else f"{path} ({_('optional')})"
        if not with_lines:
            writer.writerow([csv_text(name), csv_text(group.summary), csv_text(group.prices.subtotal)])
            for child in group.children:
                group_block(child)
            return
        lines(name, group.lines)
        for child in group.children:
            group_block(child)
        label = _("Subtotal with subgroups") if group.children else _("Subtotal")
        writer.writerow([csv_text(name), "", csv_text(label), "", "", "", "", "", "", csv_text(group.prices.subtotal)])

    for group in planning.root_groups:
        group_block(group)
    if planning.ungrouped:
        block(str(_("Without group")), planning.ungrouped_summary, prices.ungrouped_total, planning.ungrouped)
    if prices.crew:
        if crew_by_phase:
            _write_crew_by_phase(writer, planning, with_lines=with_lines, prefix=prefix)
        elif with_lines:
            for crew_price in prices.crew:
                crew_line = crew_price.line
                title = crew_line.title
                if crew_price.has_time_surcharges:
                    # PER-009: the surcharges for night, Sunday and holidays are part of the amount.
                    included = _("incl. surcharges %(amount)s") % {
                        "amount": format_money(crew_price.time_surcharge_amount)
                    }
                    title = f"{title} ({included})"
                writer.writerow(
                    [
                        csv_text(prefix + _("Personnel")),
                        csv_text(crew_line.service_product.article_number if crew_line.service_product_id else ""),
                        csv_text(title),
                        csv_text(crew_price.quantity),
                        csv_text(_crew_unit(crew_price)),
                        "",
                        "",
                        csv_text(crew_line.unit_price),
                        csv_text(crew_price.discount_percent or None),
                        csv_text(crew_price.amount),
                    ]
                )
        block(str(_("Personnel")), planning.crew_summary, prices.personnel_total)
    if prices.logistics:
        # LOG-009: the vehicles and trailers, a block of their own.
        if with_lines:
            units = {"day": _("day"), "km": "km", "flat": _("flat"), "mixed": _("flat")}
            for vehicle_price in prices.logistics:
                writer.writerow(
                    [
                        csv_text(prefix + _("Logistics")),
                        csv_text(vehicle_price.line.product.article_number),
                        csv_text(vehicle_price.line.label),
                        csv_text(vehicle_price.quantity),
                        csv_text(units[vehicle_price.unit_kind]),
                        csv_text(vehicle_price.days),
                        csv_text(vehicle_price.scale_factor),
                        csv_text(vehicle_price.unit_price),
                        csv_text(vehicle_price.discount_percent or None),
                        csv_text(vehicle_price.amount),
                    ]
                )
        block(str(_("Logistics")), planning.logistics_summary, prices.logistics_total)
    if planning.surcharges:
        block(str(_("Surcharges")), planning.surcharges_summary, prices.surcharges_total, planning.surcharges)
    if prices.overall_discount:
        # PRJ-123: the overall discount, as a negative amount.
        percent = prices.project.overall_discount_percent
        name = str(_("Overall discount")) + (
            f" {format_decimal(percent, max_places=6)} %" if percent else ""
        )  # R3-3: as stored
        block(name, "", -prices.overall_discount)


def _crew_unit(crew_price: Any) -> str:
    """The unit of a crew line on paper: hours, days (PER-029) or a flat rate."""
    from django.utils.translation import gettext as _

    return {"hour": _("h"), "day": _("day"), "flat": _("flat")}[crew_price.unit_kind]


def _write_crew_by_phase(writer: Any, planning: Any, *, with_lines: bool, prefix: str) -> None:
    """The personnel by phase and job function (PRJ-088): per phase its rows and a subtotal row.

    With lines, a row per job function names places and function, and gives hours or days with their unit
    where the function is charged by one of them; without lines, one row per function with the same in
    words. The total of the personnel follows as in every other overview.
    """
    from django.utils.translation import gettext as _

    from rentalars.core.tables import csv_text

    for share in planning.crew_by_phase:
        section = f"{prefix}{_('Personnel')} › {share.label}"
        for row in share.functions:
            name = f"{row.places} × {row.job_function.name}"
            if with_lines:
                single = [kind for kind in (row.hours, row.days, row.flat) if kind]
                quantity, unit = ("", row.scope)
                if len(single) == 1 and row.hours:
                    quantity, unit = csv_text(row.hours), _("h")
                elif len(single) == 1 and row.days:
                    quantity, unit = csv_text(row.days), _("day")
                writer.writerow(
                    [
                        csv_text(section),
                        "",
                        csv_text(name),
                        quantity,
                        csv_text(unit),
                        "",
                        "",
                        "",
                        "",
                        csv_text(row.amount),
                    ]
                )
            else:
                writer.writerow([csv_text(section), csv_text(f"{name}, {row.scope}"), csv_text(row.amount)])
        if with_lines:
            writer.writerow(
                [csv_text(section), "", csv_text(_("Subtotal")), "", "", "", "", "", "", csv_text(share.amount)]
            )
        else:
            writer.writerow([csv_text(section), csv_text(_("Subtotal")), csv_text(share.amount)])
