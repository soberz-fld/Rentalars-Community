# SPDX-License-Identifier: GPL-3.0-or-later
"""What the check with the official schemas found in the files Rentalars writes (DOK-042).

``scripts/external_validation.py`` checked the XML of every kind of invoice against the XSD and the Schematron of EN 16931.
UBL had no finding; the CII had one error, which these tests keep from coming back: the date of a referenced invoice
(``FormattedIssueDateTime``) is a qualified date (``qdt``), not an unqualified one.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rentalars.documents import services
from rentalars.documents.models import AccountingSettings, InvoiceFormat
from tests.unit.test_060_accounting import AccountingCase

QDT = "{urn:un:unece:uncefact:data:standard:QualifiedDataType:100}DateTimeString"
UDT = "{urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100}DateTimeString"
RAM = "{urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100}"


class CiiDatesTests(AccountingCase):
    def test_the_date_of_a_referenced_invoice_is_a_qualified_date(self) -> None:
        row = AccountingSettings.load()
        row.invoice_format = InvoiceFormat.ZUGFERD
        row.save()
        cancellation = services.cancel_invoice(self.invoice())
        root = ET.fromstring(cancellation.xml_file.read())
        referenced = root.findall(f".//{RAM}InvoiceReferencedDocument/{RAM}FormattedIssueDateTime")
        self.assertTrue(referenced)
        for element in referenced:
            self.assertEqual([child.tag for child in element], [QDT])
        # every other date stays unqualified
        issue = root.find(f".//{RAM}IssueDateTime")
        assert issue is not None
        self.assertEqual([child.tag for child in issue], [UDT])


class SpecificationIdentifierTests(AccountingCase):
    """BR-DE-21: the specification identifier of an XRechnung has the form of the XRechnung."""

    OWN = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"

    def setUp(self) -> None:
        super().setUp()
        self.xml = self.invoice().xml_file.read().decode("utf-8")

    def rules_for(self, identifier: str) -> set[str]:
        from rentalars.documents import einvoice_rules

        xml = self.xml
        assert self.OWN in xml
        report = einvoice_rules.check(xml.replace(self.OWN, identifier, 1).encode("utf-8"))
        return {finding.rule for finding in report.findings}

    def test_our_own_identifier_and_the_other_forms_pass(self) -> None:
        for identifier in (
            self.OWN,
            "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.1",
            "urn:cen.eu:en16931:2017#compliant#urn:xoev-de:kosit:standard:xrechnung_2.3",
            self.OWN + "#conformant#urn:xeinkauf.de:kosit:extension:xrechnung_3.0",
            "urn:cen.eu:en16931:2017#conformant#urn:xeinkauf.de:kosit:extension:xrechnung_3.0",
        ):
            self.assertNotIn("BR-DE-21", self.rules_for(identifier), identifier)

    def test_a_malformed_identifier_is_refused(self) -> None:
        for identifier in (
            "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3",
            "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung",
            "urn:cen.eu:en16931:2017#xrechnung_3.0",
            "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:extension:xrechnung_3.0",
            "xrechnung 3.0",
        ):
            self.assertIn("BR-DE-21", self.rules_for(identifier), identifier)
