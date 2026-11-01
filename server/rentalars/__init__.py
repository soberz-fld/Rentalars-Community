# SPDX-License-Identifier: GPL-3.0-or-later
"""Rentalars – project, material and crew management for event technology.

The package is split into one sub-package per business module (NFA-021):

==============  ===========================================================
``core``        audit log, number ranges, company and system settings
``accounts``    users, roles, rights, API tokens, login protection
``masterdata``  categories, units, tax rates, manufacturers, suppliers
``material``    material models and material items ("what do we have?")
``products``    products, kits and rental scales ("what do we plan with?")
``customers``   customers and their contacts
``projects``    projects, groups, material lines and price calculation
``availability``the availability calculation ("what is free when?")
``packing``     packlists, issue and return
``api``         the shared plumbing of the HTTP API under ``/api/v1``
==============  ===========================================================

The German terms of the requirements catalogue are translated with the fixed
list in section 2.1 of ``docs/anforderungen/Rentalars_Anforderungskatalog.md``.
"""

__version__ = "1.0.0"

#: UIX-031: who made Rentalars – shown under the version in the menu and in the footer of the login page.
#: Kept here, next to the version, so that it is found at once. An author attribution under section 7 b of
#: the GPL that has to be kept when Rentalars is conveyed: see ADDITIONAL-TERMS.md (NFA-075).
CREDIT_NAME = "fld-vt.de"
CREDIT_URL = "https://fld-vt.de"

#: UIX-062: the holder of the copyright, named on the page "About Rentalars" and in the README.
#: The name is entered; a fork that replaces it also replaces the line in README.md.
COPYRIGHT_YEAR = "2026"
#: What stood here while nobody had entered a name; ``about.py`` still shows it in the language of the page
#: if a fork sets ``COPYRIGHT_HOLDER`` back to it.
PLACEHOLDER_HOLDER = "die Autorinnen und Autoren von Rentalars"
COPYRIGHT_HOLDER = "Lars Wilting, fld-vt.de"
