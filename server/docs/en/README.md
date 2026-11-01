# Rentalars

Project, material and crew management for event technology companies.
Rentalars runs in the browser on a server of your own, is free software
(GPL-3.0-or-later) and costs nothing.

**Version 1.0.0.** The [requirements catalogue](../anforderungen/Rentalars_Anforderungskatalog.md) (German) describes 822
requirements; all MUSS and SOLL requirements (801) are built, the other 21 are noted as KANN. Which requirement is built and tested
where is shown in [requirement → code → test](../dev/traceability.md). What Rentalars cannot do is in chapter 17 of the user manual.

## What Rentalars does

- **Languages and accounts:** German and English – the interface per account, the documents for customers per company, the manual
  in both languages, also inside Rentalars. Roles and rights per module with separate rights for prices, purchase prices,
  personnel costs and availability, rights per project (the crew sees only the overview, packing list, chat and the open messages),
  accounts with an end date, two-factor login, optionally login with the account of the directory (LDAP, Active Directory),
  sessions and a security log.
- **Material:** models and items, built-in and loosely included parts, manufacturer, product and dealer, storage locations,
  labels with a QR code (printed from the browser to the label printer), scanning with the camera or a USB scanner, inspections
  with due dates and the electrical inspection after DGUV V3 with a protocol, audits, custom fields, photos, defect reports,
  purchase sets, bulk material, fixed assets with depreciation, "Enter a purchase" from an invoice, calendar links (.ics).
- **Vehicles and logistics:** vehicles and trailers as items with deadlines (HU, UVV), utilisation as a timeline, trips in the
  project billed by kilometres or flat, hints on double bookings, seats, driving licence and towing capacity, optionally
  kilometres from a routing service on your own server.
- **Products, customers, venues:** products with article numbers, sets, accessories and substitutes, consumables, incidental
  costs, service products; customers with contact persons and addresses; venues with access, power and plans; maps and routes
  only after a click.
- **Projects:** lines in nested groups, optional or alternative, sums, profit and price overview; scheduling with phases, a
  timeline and personnel per phase; subprojects; project templates; chat with photos and videos; billing by daily rental, flat
  rate, hours or effort with scales, surcharges and discounts; availability with traffic lights, buffer times and shortages;
  subrentals for missing quantities.
- **Service cases:** quick cases for a fault, a question or a repair, with correspondence, status, follow-up and participants,
  from a mail or a defect report, convertible into a project; a monthly invoice per customer.
- **Packing:** packing lists on screen and as PDF, issue and return per piece; the Rentalars app packs offline as well.
- **Documents and accounting:** quotation, order confirmation, delivery note, invoice (XRechnung, ZUGFeRD), credit note, crew
  disposition; advance, partial and final invoices; handover to Lexware Office or as a DATEV booking batch; accounting with open
  items, payments and the cash-basis profit statement; reading and booking incoming invoices; profitability reports.
- **Personnel and time:** job functions, qualifications with an expiry date, absences, "My area", requests with accept and decline
  (in the browser or by reply mail), price offers of freelancers, surcharges as rules per country, time tracking with a
  stopwatch and hints on rest periods, approval, timesheets, expenses and travel costs with a photo of the receipt.
- **Mail and AI:** several mailboxes, assignment to projects through the tag in the subject, replies from the project with
  documents attached, notes; summaries of the correspondence by a local AI (llama.cpp) on your own server or by a service you
  set up yourself; automations "If … then …" with a log.
- **Planning and overview:** calendar, timeline of all projects, personnel plan, a start page with what is due, notifications by
  category in the application, by mail and in the app.
- **Data in and out:** import from Excel lists with a preview (material, products, customers, personnel), export in the import
  format, CSV from every list, an API for all functions, webhooks.
- **Operation:** scripts to install, update and back up, backup from the browser too, the database on this or an existing
  server, encrypted on request; runs on a Raspberry Pi 4 or 5 as well; address and certificate in the settings; the
  [Rentalars Gateway](operations/gateway.md), through which apps reach the server from the internet, is paired in the settings;
  self-check; HTTPS only; Rentalars itself never gets root rights.

Rentalars is free of charge for every company and can be installed by
anyone. Each company runs its own instance with its own database. Rentalars
sends no data to third parties of its own accord: no fonts, scripts or
statistics from other servers, no check for new versions. An address only
goes to OpenStreetMap or Google Maps when someone opens its map or route;
the maps can be switched off entirely. The local AI runs on your own
server; mails only go to an AI service outside if an administrator
explicitly sets up an interface to it and assigns it to a use.

## Installing

On a freshly installed Ubuntu Server 24.04 LTS or 26.04 LTS – or on a
Raspberry Pi 4 or 5 with Ubuntu Server or Raspberry Pi OS based on
Debian 13 –, as a user with `sudo`:

```sh
tar -xzf rentalars-1.0.0.tar.gz
cd rentalars-1.0.0
sudo ./deploy/install.sh
```

The script asks for the name of the server, the kind of certificate, where
the database is to live and whether it is encrypted, sets everything up –
including the system packages needed – and at the end names the address for the first-run setup in the
browser. It speaks English, or German if the locale of the server is German
(`RENTALARS_LANG=en` forces English). In the first-run setup, choose
"English" for English documents and start data. The full guide:
[operations/installation.md](operations/installation.md); for updates see
[operations/updating.md](operations/updating.md).

## Manuals

| Topic | File |
|-------|------|
| User manual: working with Rentalars | [user-manual.md](user-manual.md) |
| Installation, HTTPS, system requirements | [operations/installation.md](operations/installation.md) |
| Daily operation, settings, troubleshooting | [operations/operation.md](operations/operation.md) |
| Updating and going back | [operations/updating.md](operations/updating.md) |
| Backup and restore | [operations/backup.md](operations/backup.md) |
| Reaching the apps from the internet through the Rentalars Gateway | [operations/gateway.md](operations/gateway.md) |
| Encryption of database and backups | [operations/encryption.md](operations/encryption.md) |
| Import: Excel list, products, customers, personnel | [operations/import.md](operations/import.md) |

The German originals are in [docs/handbuch](../handbuch/benutzerhandbuch.md)
and [docs/betrieb](../betrieb/). The changes of each version are in
[CHANGELOG.md](../../CHANGELOG.md) (in German).

## For developers

Code, comments and developer documentation are in English:
[getting started](../dev/getting-started.md),
[architecture](../dev/architecture.md),
[data model](../dev/data-model.md),
[core flows](../dev/core-flows.md),
[accessibility](../dev/accessibility.md),
[decisions](../dev/decisions.md) and
[requirement → code → test](../dev/traceability.md).

## Licence

Rentalars is licensed under the GNU General Public License, version 3 or
later (GPL-3.0-or-later); the text is in [LICENSE](../../LICENSE). A term
under section 7 b of the GPL applies as well:
whoever conveys Rentalars must keep the author attribution "by fld-vt.de" in
the interface ([ADDITIONAL-TERMS.md](../../ADDITIONAL-TERMS.md)). Bundled
fonts and the libraries used, with their licences, are listed in
[THIRD-PARTY.md](../../THIRD-PARTY.md).

Copyright © 2026 Lars Wilting, fld-vt.de.

**Made with AI.** Large parts of Rentalars – code, tests and documentation – were written with the help of AI assistants, mainly
Claude (Anthropic, through Claude Code). The requirements, the decisions and the acceptance lie with Lars Wilting. Commits in
which an AI assistant took part name it with a line `Co-Authored-By: Claude <noreply@anthropic.com>` (with the name of the model),
so that GitHub shows Claude as a co-author of the commit. Whether and how far copyright exists in such code is not settled in law;
the licence above applies to everything in it that is protected.
