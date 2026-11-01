# SPDX-License-Identifier: GPL-3.0-or-later
"""Incoming invoices in Buchhaltung (DOK-023, DOK-024).

The requirement: management of incoming invoices in Buchhaltung, including AI recognition of invoice number, date,
supplier and price, and a note. An incoming invoice is uploaded as a PDF or a picture, read (number, date,
supplier, amounts, positions; the AI proposes, the user corrects everything), kept with a note and a status, and its
goods positions become items or quantities of bulk material, with the ancillary costs (freight, packaging, customs)
spread over the goods ("Anschaffungsnebenkosten"). Modules:

* :mod:`rentalars.incoming.models` – the invoice, its positions and the settings of the register;
* :mod:`rentalars.incoming.services` – upload, changing, positions, status, deleting;
* :mod:`rentalars.incoming.reading` – the text of the invoice and what is made of it (with and without AI);
* :mod:`rentalars.incoming.costing` – the acquisition cost of each goods position (ancillary costs spread);
* :mod:`rentalars.incoming.booking` – preview and booking in of the goods positions as items or quantities;
* :mod:`rentalars.incoming.access` – who may see and change the register.

Browser pages (``views``) and the API (``api``) both call these functions (API-002).
"""
