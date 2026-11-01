# SPDX-License-Identifier: GPL-3.0-or-later
"""The procedure documentation (Verfahrensdokumentation) for the accounting, filled with the facts of this installation (DOK-046).

The GoBD ask a company to describe how its vouchers arise, are kept and are protected. Rentalars writes the part that it
knows – the system and its settings – and leaves a section for what only the company can say (who does what, which
processes run outside). **It is a draft to complete and to check with the tax adviser, no certificate.** The page and the PDF
are made from the same sections.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars import __version__
from rentalars.core.i18n import local_pattern
from rentalars.documents import archive
from rentalars.documents.content import company_data
from rentalars.documents.models import AccountingSettings


@dataclass
class Section:
    """One chapter: a heading, paragraphs and facts as name/value pairs."""

    heading: str
    paragraphs: list[str] = field(default_factory=list)
    facts: list[tuple[str, str]] = field(default_factory=list)


def sections() -> list[Section]:
    """The chapters, in the order the GoBD name them (general description, user, system, operation)."""
    accounting = AccountingSettings.load()
    company = company_data()
    info = archive.summary()
    yes, no = str(_("yes")), str(_("no"))
    formats = {"xrechnung": "XRechnung (UBL/XML)", "zugferd": "ZUGFeRD / Factur-X (PDF/A-3 + CII)"}
    return [
        Section(
            _("1. General description"),
            [
                _(
                    "Rentalars is the software of this company for event technology rental: offers, order confirmations, "
                    "delivery notes and invoices are made from projects; incoming invoices are captured, checked and booked."
                ),
            ],
            [
                (_("Company"), company["name"] or "–"),
                (
                    _("Tax number / VAT ID"),
                    " / ".join(x for x in (company["tax_number"], company["vat_id"]) if x) or "–",
                ),
                (_("Software version"), __version__),
                (_("Date of this description"), timezone.localdate().strftime(local_pattern("%d.%m.%Y"))),
            ],
        ),
        Section(
            _("2. Documentation for users"),
            [
                _(
                    "Outgoing documents are made from a project with the numbering of the installation. An issued document is "
                    "stored as PDF (with XML for an e-invoice) and cannot be changed or deleted afterwards. A mistake is "
                    "corrected by a cancellation or a credit note; the original stays."
                ),
                _(
                    "Incoming invoices are uploaded as PDF, picture or e-invoice (XML), read, checked by a person and, "
                    "where they contain goods, booked into the stock. Payments are entered by hand with their day and "
                    "amount; a wrong payment is voided with a reason, never changed or deleted."
                ),
            ],
            [
                (_("Format of new invoices"), formats.get(accounting.invoice_format, accounting.invoice_format)),
                (_("Invoices with errors are refused"), yes if accounting.einvoice_blocks else no),
                (_("Small business (§ 19 UStG)"), yes if accounting.small_business else no),
            ],
        ),
        Section(
            _("3. Technical system documentation"),
            [
                _(
                    "Data and files are kept on the server of this installation. Every change is logged with the user and "
                    "the time (change log). Issued documents carry a SHA-256 checksum; the archive records the checksum of "
                    "every file of every voucher."
                ),
                _(
                    "The income and expense statement (EÜR) is worked out from the payments, not from the invoices, on the "
                    "cash basis. Assets are depreciated by the month principle; low-value assets are written off in the year "
                    "of acquisition. The figures are a preparation for the tax adviser."
                ),
            ],
            [
                (_("Database"), settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]),
                (_("Vouchers in the archive"), str(info["total"])),
                (_("Outgoing documents / incoming invoices"), f"{info['documents']} / {info['incoming']}"),
            ],
        ),
        Section(
            _("4. Operation and retention"),
            [
                _(
                    "Every night the archive registers new vouchers and checks a part of the files against their checksums, so "
                    "that every file is checked within the period below. A changed or missing file turns the self-check red and "
                    "reaches the operators. An archived incoming invoice cannot be deleted before its retention period "
                    "ended; an issued outgoing document is never deleted."
                ),
                _(
                    "The retention period ends with the calendar year in which the voucher was made, plus the years below. "
                    "The backup of the installation is made every night (see the self-check)."
                ),
            ],
            [
                (_("Retention of invoices and vouchers"), f"{accounting.retention_invoice_years} " + str(_("years"))),
                (_("Retention of business letters"), f"{accounting.retention_letter_years} " + str(_("years"))),
                (_("Every file checked within"), f"{accounting.archive_check_days} " + str(_("days"))),
                (_("Files found changed or missing"), str(info["changed"] + info["missing"])),
            ],
        ),
        Section(
            _("5. To be completed by the company"),
            [
                _("Who captures, checks and approves vouchers, and who may enter payments?"),
                _(
                    "Which vouchers arise outside Rentalars (cash book, bank statements, payroll) and where are they kept?"
                ),
                _("How is the data handed to the tax adviser, and how are tax audits supported (data access)?"),
                _(
                    "This text is a draft made from the settings of the installation. It does not replace the review by the "
                    "tax adviser, and Rentalars is not certified."
                ),
            ],
        ),
    ]


def as_markdown() -> str:
    """The same chapters as Markdown."""
    lines = [f"# {_('Procedure documentation')}", ""]
    for section in sections():
        lines += [f"## {section.heading}", ""]
        lines += [paragraph + "\n" for paragraph in section.paragraphs]
        lines += [f"- **{name}:** {value}" for name, value in section.facts]
        lines.append("")
    return "\n".join(lines)


def render_html() -> str:
    """The chapters as a page of their own, for the PDF."""
    from django.template.loader import render_to_string

    return render_to_string(
        "documents/procedure_pdf.html",
        {
            "sections": sections(),
            "title": _("Procedure documentation"),
            "company": company_data(),
            "version": __version__,
        },
    )


def render_pdf() -> bytes:
    """The PDF of the procedure documentation."""
    from weasyprint import HTML

    return HTML(string=render_html(), base_url=str(settings.BASE_DIR)).write_pdf()
