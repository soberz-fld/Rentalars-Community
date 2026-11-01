#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check e-invoice files with the official XSD and Schematron rules of EN 16931 (DOK-042) – a developer's tool.

Rentalars checks its e-invoices itself (``documents/einvoice_rules.py``). This script checks files with the rules other
people wrote: the XML schemas (UBL 2.1 and Factur-X / ZUGFeRD EN 16931) and the compiled Schematron of the European
standard (CEN, as the ``factur-x`` package carries it). It is **not** part of Rentalars and its packages are not
requirements: they are installed in a separate environment, only to run it::

    python3 -m venv /tmp/ext && /tmp/ext/bin/pip install saxonche lxml factur-x
    /tmp/ext/bin/pip install --no-deps odoo-addon-base_ubl
    /tmp/ext/bin/python scripts/external_validation.py DIRECTORY_WITH_XML_FILES

It does **not** run the Schematron of the XRechnung (BR-DE rules of the KoSIT), nor does it check PDF/A: those come from the
KoSIT validator and veraPDF, which need Java and a download from GitHub / Maven Central. Exit code 1: a file broke a rule (a warning of the Schematron does not count).
"""

from __future__ import annotations

import sys
from pathlib import Path


def package_dir(name: str) -> Path:
    """The directory of an installed package, found without importing it (``odoo`` has no importable top level)."""
    import importlib.util
    import sysconfig

    spec = importlib.util.find_spec(name)
    if spec is not None and spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations)))
    return Path(sysconfig.get_paths()["purelib"]) / name


def main(argv: list[str]) -> int:
    """Check every ``*.xml`` file of the directory; print the findings; 0 if none broke a rule."""
    from lxml import etree
    from saxonche import PySaxonProcessor

    if len(argv) != 2:
        print(__doc__)
        return 2
    facturx = package_dir("facturx") / "xsd_and_schematron"
    ubl_xsd = package_dir("odoo") / "addons" / "base_ubl" / "data" / "xsd-2.1" / "maindoc"
    schemas = {
        "ubl-invoice": etree.XMLSchema(etree.parse(str(ubl_xsd / "UBL-Invoice-2.1.xsd"))),
        "ubl-credit": etree.XMLSchema(etree.parse(str(ubl_xsd / "UBL-CreditNote-2.1.xsd"))),
        "cii": etree.XMLSchema(etree.parse(str(facturx / "facturx-en16931" / "Factur-X_EN16931.xsd"))),
    }
    rules = {
        "ubl-invoice": facturx / "ubl-2.1" / "EN16931-UBL-validation.xslt",
        "ubl-credit": facturx / "ubl-2.1" / "EN16931-UBL-validation.xslt",
        "cii": facturx / "facturx-en16931" / "FACTUR-X_EN16931.xslt",
    }
    broken = 0
    with PySaxonProcessor(license=False) as processor:
        xslt = processor.new_xslt30_processor()
        compiled = {name: xslt.compile_stylesheet(stylesheet_file=str(path)) for name, path in rules.items()}
        for path in sorted(Path(argv[1]).glob("*.xml")):
            root = etree.parse(str(path)).getroot()
            tag = etree.QName(root).localname
            kind = {"Invoice": "ubl-invoice", "CreditNote": "ubl-credit", "CrossIndustryInvoice": "cii"}.get(tag)
            if kind is None:
                print(f"{path.name}: unknown document {tag}")
                broken += 1
                continue
            schemas[kind].validate(etree.parse(str(path)))
            problems = [f"XSD: {error.message}" for error in schemas[kind].error_log]
            warnings = []
            report = compiled[kind].transform_to_string(source_file=str(path))
            svrl = etree.fromstring(report.encode())
            for failed in svrl.iter("{http://purl.oclc.org/dsdl/svrl}failed-assert"):
                text = " ".join("".join(failed.itertext()).split())
                line = f"{failed.get('id')} ({failed.get('flag')}): {text}"
                (warnings if failed.get("flag") == "warning" else problems).append(line)
            state = "OK" if not (problems or warnings) else f"{len(problems)} error(s), {len(warnings)} warning(s)"
            print(f"{path.name}: {state}")
            for line in problems + warnings:
                print(f"    {line}")
            broken += bool(problems)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
