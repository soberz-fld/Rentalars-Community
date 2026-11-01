# SPDX-License-Identifier: GPL-3.0-or-later
"""The invoice as ZUGFeRD / Factur-X PDF: a PDF/A-3b with the invoice data inside (DOK-049).

The PDF is made as every document PDF is (``documents.pdf``), once more as **PDF/A-3b** with WeasyPrint, with

* the Cross Industry Invoice (``documents.cii``) embedded as ``factur-x.xml``, relationship "Alternative" (PDF/A-3 keeps
  it in the ``/AF`` list of the catalog),
* the XMP metadata extended by the schema of Factur-X (``fx:DocumentType`` "INVOICE", ``fx:DocumentFileName``,
  ``fx:Version`` "1.0", ``fx:ConformanceLevel`` "EN 16931") and its declaration for PDF/A.

The result is one file: it opens in every PDF viewer and an invoice program reads the XML out of it. The document is
stored as this file, so the checksum of the document (DOK-007) is that of the hybrid.

Built after the specification of Factur-X 1.0 / ZUGFeRD 2.x and tested structurally (``tests/unit/test_112_zugferd``);
not validated with veraPDF, Mustang or the validator of a recipient.
"""

from __future__ import annotations

import io
from typing import Any

from django.conf import settings

from rentalars.documents.cii import CONFORMANCE_LEVEL, FILE_NAME
from rentalars.documents.content import DocumentContent

#: The namespace of the Factur-X properties in the XMP metadata.
FX_NAMESPACE = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"

XMP_BLOCK = f"""<rdf:Description rdf:about="" xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/" xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#" xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
<pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">
<pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
<pdfaSchema:namespaceURI>{FX_NAMESPACE}</pdfaSchema:namespaceURI>
<pdfaSchema:prefix>fx</pdfaSchema:prefix>
<pdfaSchema:property><rdf:Seq>
<rdf:li rdf:parseType="Resource"><pdfaProperty:name>DocumentFileName</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>name of the embedded XML invoice file</pdfaProperty:description></rdf:li>
<rdf:li rdf:parseType="Resource"><pdfaProperty:name>DocumentType</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>INVOICE</pdfaProperty:description></rdf:li>
<rdf:li rdf:parseType="Resource"><pdfaProperty:name>Version</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The actual version of the standard applying to the embedded XML document</pdfaProperty:description></rdf:li>
<rdf:li rdf:parseType="Resource"><pdfaProperty:name>ConformanceLevel</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The conformance level of the embedded XML document</pdfaProperty:description></rdf:li>
</rdf:Seq></pdfaSchema:property>
</rdf:li></rdf:Bag></pdfaExtension:schemas>
</rdf:Description>
<rdf:Description rdf:about="" xmlns:fx="{FX_NAMESPACE}">
<fx:DocumentType>INVOICE</fx:DocumentType>
<fx:DocumentFileName>{FILE_NAME}</fx:DocumentFileName>
<fx:Version>1.0</fx:Version>
<fx:ConformanceLevel>{CONFORMANCE_LEVEL}</fx:ConformanceLevel>
</rdf:Description>
"""


def _extend_xmp(_document: Any, pdf: Any) -> None:
    """Finisher of WeasyPrint: put the Factur-X schema and properties into the XMP stream of the PDF."""
    reference = pdf.catalog["Metadata"]
    if isinstance(reference, bytes):
        reference = reference.decode("ascii")
    stream = pdf.objects[int(str(reference).split()[0])]
    xmp = b"".join(stream.stream)
    marker = b"</rdf:RDF>"
    if xmp.count(marker) != 1:  # pragma: no cover - WeasyPrint writes exactly one
        raise ValueError("The XMP metadata has an unexpected shape.")
    stream.stream = [xmp.replace(marker, XMP_BLOCK.encode("utf-8") + marker)]
    # WeasyPrint lists a file twice in /AF (once as attachment, once as PDF/A-3 associated file); once is enough.
    associated = pdf.catalog.get("AF")
    if associated:
        unique = []
        for item in associated:
            if item not in unique:
                unique.append(item)
        associated[:] = unique


def render_hybrid(content: DocumentContent, template: Any, cii_xml: bytes) -> bytes:
    """The document as PDF/A-3b with the invoice (``cii_xml``) inside, as bytes."""
    from weasyprint import HTML, Attachment

    from rentalars.documents.pdf import render_html

    attachment = Attachment(
        file_obj=io.BytesIO(cii_xml),
        name=FILE_NAME,
        description="Factur-X Invoice",
        relationship="Alternative",
    )
    document = HTML(string=render_html(content, template, draft=False), base_url=str(settings.BASE_DIR)).render()
    return document.write_pdf(pdf_variant="pdf/a-3b", attachments=[attachment], finisher=_extend_xmp)
