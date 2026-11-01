# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the business rules in detail.

NFA-019 asks for automatic tests of the core logic. They are here, one file
per topic:

==========================  ===================================================
``test_availability.py``    what is free when (VFG): peaks, status, buffers, kits,
                            containers, subrental, the overview of all shortages
``test_pricing.py``         amounts, rental scales, discounts, surcharges, tax (PRD, PRJ)
``test_foundation.py``      rights (AUT), numbers, change log, configuration
``test_project_services.py``  rules of projects, groups and lines (PRJ)
``test_packing.py``         packing, issue, return (PCK)
``test_importer.py``        the import of the material list (IMP)
``test_concurrency.py``     two bookings at the same moment (VFG-007); MariaDB only
``test_translations.py``    every text of the interface has a German translation (NFA-026)
``test_templates.py``       mistakes in pages that only a browser would show
==========================  ===================================================

The check of article numbers (PRD-007 ff.) is tested where it is used: in
``tests/api/test_products_api.py`` and ``tests/ui/test_product_pages.py``.
Hourly rates belong to stage 3 and have no code yet.
"""
