# Import: material, products, customers, personnel

Four lists can be taken over into Rentalars from an Excel or CSV file
(IMP-001): the existing **material list** – one row per item –,
**products**, **customers** and **personnel**. All four imports are built so
that you can try them out safely and repeat them as often as you like:

- **A dry run first.** It checks the whole file and says exactly what the
  import would do. Nothing is written.
- **All or nothing.** If even one row has an error, nothing is imported.
  There is no half-imported stock.
- **Repeatable.** What already exists is recognised and updated, never
  created twice: an item by its ID, a product by its article number, a
  customer by customer number, VAT ID, e-mail address or name – there empty
  cells change nothing (below "Customers") –, a person by their
  e-mail address or their name. So you can correct the list and load it
  again.

There are three ways that do the same: in the browser (the more convenient
one for most people), via the API and on the command line of the server.

Each import also has its way back: the **export in the import
format** – a CSV file with exactly the columns of the import, in plain text
(below, "Export in the import format").

## The file

An Excel file (`.xlsx`) or a CSV file, at most 25 MB in size, with a heading
row and **one row per record**. Empty rows do no harm. With CSV, the
separator (semicolon, comma, tab) and the character set are recognised; for
the character set the import tries, in turn, byte order mark, UTF-8,
Windows-1252 (as often with exports from Lexware) and ISO-8859-1, so umlauts
arrive correctly even from older programs. With Excel files with several
sheets the first sheet counts; another one can be chosen via the API and on
the command line.

Please save old Excel files (`.xls`) as `.xlsx` in Excel.

The columns are recognised by their headings. Upper and lower case, line
breaks in the heading and the order of the columns do not matter. If a
column is called something else in your file, that is no problem: you assign
it during the import (see below). Which headings are recognised is listed in
the tables of the following sections, in the browser under "Which columns
are recognised?" and via the API (`GET /api/v1/imports/{kind}`).

**For all lists:**

- Numbers: `1.250,00`, `1250`, `1250.50`, `499,00 €`, `19 %`. If there is a
  comma in the number, it is the decimal sign and a dot separates thousands.
- Yes/no columns ("Aktiv") understand `ja`/`nein`, `1`/`0`, `x`,
  `aktiv`/`inaktiv`. An empty cell changes nothing there.
- **A list exported from Rentalars can be read in again.** In the "CSV with
  all columns" of the lists of products, customers and personnel the data is
  under headings that the import recognises (columns such as "Projects" or
  "Contact" that it does not know are simply ignored). So many records can be
  changed in a spreadsheet and loaded back; an unchanged list changes nothing
  when it is read in. The export in the import format is made for exactly
  this, also for material (below).
- **Apostrophe in front of a formula**: if a cell starts with
  an apostrophe followed by `=`, `+`, `-` or `@` – this is how the exports
  of Rentalars write text that a spreadsheet would otherwise run as a
  formula, e.g. `'=Summe` or `'- defekt` –, the import takes the apostrophe
  away. Any other apostrophe at the start stays.

## Material

### The columns

The 13 columns of the existing list are recognised by their headings:

| Column | Required | Recognised headings | Becomes |
|---|---|---|---|
| ID | yes | ID, Inventarnummer, Inventar-Nr, Nr, Nummer | ID of the item |
| Artikelname (article name) | yes | Artikelname, Artikelname (evtl. gekürzt), Artikel, Name | material model |
| Kategorie (category) | yes | Kategorie | category of the model |
| Beschreibung (description) | | Spezifikation, Spec, Beschreibung | on the model |
| Kategoriespezifische Angabe (category-specific detail) | | Kategoriespezifische Angabe, Kategoriespezifisch, Kat.-spez. Angabe | on the model, e.g. "5 m" |
| Einsatz/Verbindung (use/connection) | | Einsatz/Verbindung, Einsatz, Verbindung, Verbaut in | "installed in" – the ID of another item |
| Seriennummer (serial number) | | Seriennummer, Serien-Nr, SN, S/N | on the item |
| Notiz (note) | | Notiz, Notizen, Bemerkung | on the item |
| Rechnungsdatum (invoice date) | | Tag des Kaufs, Kaufdatum, Gekauft am, Rechnungsdatum | on the item |
| Kaufnotiz (purchase note) | | Kaufnotiz | on the item |
| Kaufpreis (purchase price) | | Kaufpreis, Preis, EK | on the item |
| Gekauft (Händler) (bought from supplier) | | Gekauft (Händler), Gekauft, Händler | supplier; created if missing |
| Artikelnummer beim Händler (supplier's article number) | | Artikelnummer beim Händler, Händler-Artikelnummer, Bestellnummer | on the item |

Plus nine columns that the old list does not have, but that you can add if
you know the data anyway:

| Column | Recognised headings | Meaning |
|---|---|---|
| Hersteller (manufacturer) | Hersteller | on the model; created if missing |
| Kurzname (short name) | Kurzname | on the model |
| Menge (quantity) | Menge, Anzahl, Stückzahl | for bulk material: one row with a number of pieces instead of many rows |
| Status | Status, Zustand | available, defective, in repair, blocked, retired, sold, lost; without a value new items are available |
| Lagerort (storage location) | Lagerort, Lager | the name of a storage location or, its path, e.g. `Halle 1 > Regal A` – this is how the export in the import format writes it, because two shelves may have the same name; a name that does not exist yet is created as a top-level storage location |
| Produkt (product) | Produkt, Artikelnummer | article number of an existing product, e.g. `K-005`; assigns the model to this product |
| Rechnungsnummer (invoice number) | Rechnungsnummer, Rechnungs-Nr, Re-Nr, Rechnung | on the item |
| Leistung (W) (power) | Leistung, Leistung in W, Watt | on the model, in watts |
| Schutzklasse (protection class) | Schutzklasse, Schutzkl., SK, Protection class | the protection class of the item, `I`, `II` or `III` (below); on the model only if it has none yet and all its rows agree |

> **Note.** The recognised headings follow the description in the
> requirements catalogue and common spellings. A column whose heading is not
> recognised is assigned by hand in the preview.

### How the data is read

- **ID:** a number; leading zeros are allowed (`0042` and `42` mean the same
  item). Each ID may occur only once in the file.
- **Artikelname:** rows with the same article name become *one* material
  model with several items. So watch out for consistent spelling –
  "XLR Kabel 5m" and "XLR-Kabel 5 m" would be two models. (They can only be
  merged by hand later.)
- **Kategorie:** the name or the code of an existing category ("Sound" or
  "T"; on an installation in German "Ton"). You write a subcategory as
  `Sound > Microphones` (or `Sound / Microphones`).
  Categories that do not exist yet are created; a new main category gets a
  code from its initial letters. The report names all newly created ones –
  check the codes before you assign article numbers. A new
  installation comes with the main categories Sound (T), Lighting (L),
  Video/media (M), Rigging/truss (R), Cables (K), Sale (V), Material
  subrented from others (E) and Event technology services (D),
  also Customer material (C) for the material of customers,
  Incidental costs (N) – on an installation in German Ton, Licht,
  Video/Medien, Rigging/Traverse, Kabel, Verkauf, Extern zugemietetes
  Material, Veranstaltungstechnik-Dienstleistung, Fremdmaterial and
  Nebenkosten. A slash that belongs to the name of an existing main
  category stays part of the name: "Video/media" is the category
  Video/media, "Video/media/Projectors" its subcategory Projectors.
  `Video/media > Projectors` or the code `M` is always unambiguous.
- **Einsatz/Verbindung:** the ID of the item this one is in. The ID must
  occur in the file or already in Rentalars. Every such entry is taken over
  as **"permanently installed"**. Whatever only lies loose in a case you
  switch to "loosely contained" on the item afterwards; the report lists all
  links for this. A cell with **exactly one** ID (`500`,
  `#0500`, `500.0`) is the connection. If it holds several IDs
  (`#0123, #1234`), **no** connection is made – an item can be installed in
  only one other item, and which one is meant cannot be guessed. The same
  goes for free text (`Rack`, `Stage left`). In both cases it is no error:
  the text of the cell is taken over into the note of the item
  (`Einsatz/Verbindung: #0123, #1234`, after a note from the file) and the
  report names the row as a note. You make the connection on the item
  afterwards. The same line is in the note only once, even if you read the
  file again; if the text in the cell changes, the new line is added and an
  earlier one is not removed. A number such as `1,5` is no list of IDs;
  very long runs of digits (more than nine) are no ID and count as text.
**Further rules**:

- **Status "import error".** An entry Rentalars cannot read or accept – a
  purchase price like "neun", an invoice date like `32.13.2019`, a protection
  class that is none, a status that does not exist, a quantity that is not a
  whole number, an installed-in ID that does not exist, a reference to a set
  that points nowhere – **does not stop the import**. The item is taken over
  without that entry (an existing one keeps its old value), gets the status
  **"import error"** ("Fehler Import" in German), and its note names each entry
  in a line: the heading of the column in the file and the content of the cell
  ("Kaufpreis: neun"). An item with this status is **not fit for rental** until
  you fill in the fields by hand and choose another status; you cannot set this
  status yourself, only the import does. The report and the dry run count the
  items ("3 items get the status "import error""), and every row is in the list
  with its note. If you read the same file again later without the problem, the
  item is free again: it takes the status from the file, else "available"; the
  lines in the note stay only once. **Exception:** an item that is not fit for rental anyway (sold, retired, lost, blocked, defective, in repair) keeps its status and the reason for it; the note names the entries all the same, and a later clean import does not make it available again. **Errors remain** errors where there is no
  substitute: a missing or doubled ID, a missing article name or category, an
  item outside the file that forbids a set inside a set – Rentalars then writes
  nothing (all or nothing).
- **Quantity of individual items.** If you set "Menge (bulk material)" to
  "– do not import –" and an item still has a quantity from earlier times (it
  was bulk material), the message "individual items always have the quantity 1"
  is gone: the quantity is set to 1, the old value is in the note, and the report
  names it as a hint.

- **Rechnungsdatum:** a date from Excel, or as text `12.03.2021`,
  `12.03.21`, `2021-03-12`, `12/03/2021`, even just `03/2021` or `2021`.
  The day or month of an old item may be unknown: `00.00.2015`
  (year only), `00.05.2015` (month and year), also `05.2015`, `2015-05-00`
  and `2015-00-00`. Rentalars stores the first day of the known period (for
  the depreciation) and remembers how exact the date is; it is shown as
  `2015`, `05.2015` (`05/2015` in the English interface) or the full date. The export file in the import format
  writes these dates the same way, so an export and a new import lose
  nothing. A number such as `215` or `20150` is reported as an error.
- **Kaufpreis:** `1.250,00`, `1250`, `499,00 €`. Net.
- **Lagerort** (also as a path): if there is a `>` in the cell,
  the import looks for the storage location with exactly this path (case
  and the spaces around `>` do not matter). If the path does not exist, it
  creates – as for an unknown name – a storage location **at the top
  level** that carries the whole text as its name (`Halle 1 > Regal B`),
  instead of hall and shelf separately. So create new storage locations
  beforehand under Settings → Storage locations.
- **Schutzklasse** (protection class; MAT-077, for the
  electrical inspection after DGUV V3; [user manual](../user-manual.md), section 4,
  "Protection class"): `I`, `II` or `III`, likewise `1`, `2`, `3` (also
  `2.0` from a number cell) and with a word in front such as `SK II`,
  `Schutzkl. 2`, `Schutzklasse III`, `Klasse 1` or `Protection class 2`;
  case does not matter. Anything else is an error of the row. The cell is
  the class of the **item**:
  - A material model **without** a protection class gets the class all its
    rows of the file name – only if all name the same (none empty) and
    none of its items in Rentalars has a class of its own. Then it applies
    to the whole model, and a file from the export in the import format
    comes back unchanged.
  - Otherwise every item whose cell differs from its model's class gets a
    class **of its own**; the same class as the model, or an empty cell,
    means "as the model" and takes an item's own class away.
  - The import never changes the protection class of a model that has one
    – do that on the model's page.

### Custom fields

(MAT-073) items have **custom fields**, grouped in one
fieldset per material model ([user manual](../user-manual.md), section 4,
"Custom fields"). The material import reads them as well:

- **Column = name of the field.** A column headed with the name of a
  custom field (case does not matter) fills that field – without an
  assignment in the step "Assign the columns". A column assigned there to one of
  the usual fields stays that field. Which names exist is shown in the
  browser under "Which columns are recognised?". The CSV file of the item
  list and the export in the import format write the fields under exactly
  these headings.
- **Errors per row.** Every value is checked against the fieldset of the
  material model of its row, like a value in the form: type (number, date
  `01.03.2027`, "ja"/"nein", option …), check pattern and "unique". If the
  fieldset does not have the field ("The material model “…” has no custom
  field “…” in its fieldset."), the value does not fit or another item
  already has the same unique value, that is an error of this row – and as
  with every error, nothing is imported.
- **An empty cell empties the value** – the file counts, as for the serial
  number or the note. For a field that is not part of the model's
  fieldset, an empty cell is skipped.
- **Required fields are not demanded.** The import may create items
  without their required values, like creating several items at once; the
  item's page names what is missing.
- **Confidential fields** ("only with the right to see purchase prices"):
  without this right the import skips the column with the note "The column
  is not imported: the values of this field need the right to see purchase
  prices."

In the dry run a change appears as "Name (custom field)" with before and
new, like the other fields; a confidential value without the right as "not
visible".

Whoever may edit material may import.

## Products

One row per product. Whoever may edit products may import.

| Column | Required | Recognised headings | Meaning |
|---|---|---|---|
| Art.-Nr. (article number) | yes | Art.-Nr., Artikelnummer, Art.-Nr, Art-Nr, Artikel-Nr., Article no. | article number such as `K-005`; recognises existing products |
| Name | yes | Name, Artikelname, Bezeichnung, Produkt | |
| Kategorie (category) | | Kategorie, Unterkategorie, Category | a subcategory of the main category, see below |
| Art (kind) | | Art, Produktart, Kind | rental product, sale or consumable, service, kit, surcharge, subrental, incidental costs |
| Preis (price) | | Preis, Mietpreis, Preis (netto), Tagespreis, Price | net |
| Verkaufspreis (sale price) | | Verkaufspreis, Verkaufspreis (netto), VK, Sale price | net |
| Höchstrabatt (maximum discount) | | Höchstrabatt, Höchster Rabatt, Höchster Rabatt in Prozent, Max. Rabatt, Maximaler Rabatt, Maximum discount | in per cent, 0 to 100; empty: no limit, 0: no discount allowed |
| Einheit (unit) | | Einheit, Unit | name or abbreviation of an existing unit, also without the part in brackets ("Piece" for "Piece (rental)"), see below |
| Steuerart (tax rate) | | Steuerart, Steuersatz, MwSt, USt, Tax rate | name of an existing tax rate or its rate, e.g. `19` |
| Abrechnungsart (billing mode) | | Abrechnungsart, Abrechnung, Billing mode | daily rental per piece, daily rental per kit, flat, by the hour, by effort |
| GTIN/EAN | | GTIN/EAN, GTIN, EAN, Barcode | |
| Beschreibung (description) | | Beschreibung, Description | |
| Interne Notiz (internal note) | | Interne Notiz, Notiz, Bemerkung, Note | |
| Mindestbestand (minimum stock) | | Mindestbestand, Minimum stock | whole number; empty or 0: no warning |
| Eigentümer (owner) | | Eigentümer, Eigentum, Eigentümerin, Kunde, Owner | only for customer material: customer number or name of the customer the product belongs to; empty: own material |
| Aktiv (active) | | Aktiv, Active | yes/no |

- **The article number decides.** If there is a product with this number, it
  is updated, otherwise created. Lower case and spaces do no harm (`k-005` is
  `K-005`). The letters before the hyphen name the **main category**; a
  category with this code must exist – the product import does not create
  categories.
- **Kategorie:** name or path (`Sound > Microphones`) of a subcategory of this
  main category. If the cell is empty, the main category applies.
- **Art and Abrechnungsart** understand the names from Rentalars and common
  words (Miete, Verkauf, Verbrauch, Verbrauchsmaterial, Zuschlag; pro Tag,
  täglich, Pauschale, pro Stunde, stündlich). Whatever a **new** product does
  not have in the file – kind, unit, tax rate, billing mode – comes from the
  defaults of its category, as with a product created in the browser. Every **service** belongs to exactly one job function of the
  personnel: a new one creates its job function with the same name; a name
  that a job function already has is reported as an error by the dry run.
  You import transport and travel costs as "incidental costs".
- **Einheit:** a new installation comes with the units Piece
  (rental), Piece (sale), Kit (rental), Kit (sale), Hour, Day, Kilometre,
  Flat rate, Litre or part of one, Metre or part of one and Kilogram or
  part of one – on an installation in German Stück (Miete), Stück
  (Verkauf), Set (Miete), Set (Verkauf), Stunde, Tag, Kilometer, Pauschal,
  Angefangener Liter, Angefangener Meter and Angefangenes Kilogramm. An
  exactly matching name always counts. If the text matches several units –
  a name without its part in brackets such as "Piece" or "Kit" ("Stück",
  "Set"), or an abbreviation that several share, such as "pcs." ("Stk.") –,
  the import takes the unit the category of the product prescribes: in
  Sound "Piece (rental)", in Sale "Piece (sale)". If the category
  prescribes none of them, the first by name counts. If a unit "Stück"
  exists, the import takes that one for "Stück".
- **Prices** are imported only by someone who may see prices – the same
  goes for the **maximum discount**. If a column is assigned to "Price",
  "Sale price" or "Maximum discount" and the right is missing, the import
  stops with "Importing prices needs the right to see prices." – then set
  these columns to "do not import".
- **Eigentümer**: material that customers store with you – a
  band's mixing desk – is **customer material** in a category marked for it,
  such as C "Customer material" ("Fremdmaterial")
  ([user manual](../user-manual.md), "Customer material"). The column names
  the customer by their **customer number** or their **name** (with the name,
  upper and lower case do not count); if several customers have the same
  name, the import requires the customer number. The customer must exist –
  the product import does not create customers. A product of a category for
  customer material needs an owner, is a rental product or kit and must have
  no price and no sale price (a maximum discount is discarded); a product of
  another category must have no owner. Otherwise the dry run reports the row
  as an error. If the product is already planned in a project, its owner can
  no longer be changed. The exported product list ("Columns" → "Owner" or
  "CSV with all columns") contains the name of the customer.

## Customers

One row per customer. Whoever may edit customers may import. The **contact export of Lexware** (CSV) can also be read in unchanged
(IMP-013): its columns – "Firmenname", "Straße 1", "PLZ 1",
"Ansprechpartner 1 Vorname" and so on – are in the table, and the import
recognises its character set (above, "The file").

| Column | Required | Recognised headings | Meaning |
|---|---|---|---|
| Nummer (number) | | Nummer, Kundennummer, Kunden-Nr., Kd.-Nr., Number | recognises existing customers, see below |
| Name | (*) | Name, Firmenname, Firma, Kunde, Name oder Firma | |
| Vorname (first name) | (*) | Vorname, First name | without a company name: first and last name are the name of a private person |
| Nachname (last name) | (*) | Nachname, Familienname, Last name | |
| Anrede (salutation) | | Anrede, Salutation | stored only for contact persons, not for the customer |
| Art (kind) | | Art, Kundenart, Kind | company or organisation (also Firma, Unternehmen, Organisation), private person (also Privat) |
| Zusatz (addition) | | Zusatz, Adresszusatz 1, Adresszusatz, Namenszusatz, Abteilung | |
| Straße (street) | | Straße, Straße 1, Strasse 1, Strasse, Straße und Hausnummer, Anschrift, Street | |
| Postleitzahl (postal code) | | Postleitzahl, PLZ 1, PLZ, Postal code | |
| Ort (city) | | Ort, Ort 1, Stadt, City | |
| Land (country) | | Land, Land 1, Country | |
| Lieferadresse Zusatz, Straße, Postleitzahl, Ort, Land (delivery address) | | Lieferadresse Zusatz, Adresszusatz 2; Lieferadresse Straße, Straße 2, Strasse 2; Lieferadresse Postleitzahl, PLZ 2, Lieferadresse PLZ; Lieferadresse Ort, Ort 2; Lieferadresse Land, Land 2 | a delivery address of the customer |
| E-Mail | | E-Mail, E-Mail 1, Email 1, E-Mail-Adresse, Mail, Email | |
| E-Mail 2 | | E-Mail 2, Email 2 | goes into the note |
| Telefon (phone) | | Telefon, Telefon 1, Tel., Telefonnummer, Phone | |
| Telefon 2 (phone 2) | | Telefon 2, Tel. 2 | goes into the note |
| USt-IdNr. (VAT ID) | | USt-IdNr., USt-ID, UStID, Umsatzsteuer-ID, Umsatzsteuer ID, VAT ID | e.g. `DE123456789` |
| Steuernummer (tax number) | | Steuernummer, Steuer-Nr., St.-Nr., Tax number | |
| Zahlungsziel (Tage) (payment terms in days) | | Zahlungsziel (Tage), Zahlungsziel, Payment terms (days) | empty: as in the company data |
| Standardrabatt % (default discount) | | Standardrabatt %, Rabatt, Standardrabatt | |
| Notiz (note) | | Notiz, Bemerkung, Note | |
| Ansprechperson (contact person) | | Ansprechperson, Kontakt, Ansprechpartner, Ansprechpartnerin, Kontaktperson | name of the contact person |
| E-Mail der Ansprechperson (contact person's e-mail) | | E-Mail der Ansprechperson, E-Mail Ansprechpartner | |
| Telefon der Ansprechperson (contact person's phone) | | Telefon der Ansprechperson, Telefon Ansprechpartner | |
| Ansprechpartner 1 und 2 (contacts 1 and 2) | | Ansprechpartner 1, Ansprechpartner 1 Anrede, … Vorname, … Nachname, … E-Mail, … Telefon; likewise with 2 | two further contact persons, as in the contact export of Lexware |
| Aktiv (active) | | Aktiv, Active | yes/no |

(*) A column must be assigned to "Name" or to "Vorname" or "Nachname".

The import does not take over the column "Lieferantennummer" (supplier
number) of the Lexware export; the report says so. It recognises the column
"Contact" of the customer list exported from Rentalars (e-mail and phone) as
such and leaves it out, so that the list comes back unchanged.

**Who is who.** The import looks for the matching customer for
every row, in this order

1. by the **customer number**,
2. by the **VAT ID**,
3. by the **e-mail address** – of the customer or one of their contact
   persons –,
4. by the **name**, regardless of upper and lower case, punctuation and
   legal form, with umlauts written out: "Müller GmbH" is "MUELLER gmbh".

If a step finds several, the following ones decide. If several remain, the
row becomes a new customer, and the dry run names who came into question
("Several customers fit (…), so a new customer is created.") – then enter
the customer number in the file. The import is careful here:

- A customer is found by at most one row of a file; a second row that looks
  just the same becomes a new customer with a note (if it carries the same
  customer number, it is an error).
- A private person is never matched to a company with a legal form in its
  name, and only by their own e-mail address, not by that of a contact
  person.
- If only the number fits, but neither name nor VAT ID nor e-mail address,
  the dry run warns. Lexware also counts from 10001; its numbers may
  therefore hit entirely different customers. If the numbers in the file
  come from another program, set the column "Customer number" to "– do not
  import –"; then the import recognises the customers by VAT ID, e-mail
  address and name.

A customer that is found is **completed, never emptied**:

- **Empty cells change nothing** – in every column, with every customer
  import. So a field can no longer be emptied via the import; that is done
  in the browser.
- A name that differs only in spelling stays as it is in Rentalars.
- If the file names **a different street or a different city**, that
  becomes the address of the customer, and the previous one is kept as a
  further billing address. The import also recognises the same address when
  it says "Str." once and "Straße" once, or the postal code is missing.
- A **delivery address** is added, unless the customer already has one with
  the same street, postal code and city.
- A **contact person** is added, unless there already is one with the same
  name or the same e-mail address; that one is completed. The first contact
  person of a customer becomes their main contact person.
- "E-Mail 2" and "Telefon 2" go into the note once.
- If the customer was found by VAT ID, e-mail address or name and the file
  names a different number, they keep their number in Rentalars ("The file
  has the number …; the customer keeps its number …").

If the import finds no customer, it creates a new one – with the number from
the file if Rentalars does not know it yet; so customers keep their number
from the previous program. Otherwise, or without a number, they get the next
number of the number range. If a new customer looks similar to an existing
one – similar name or same e-mail address –, the dry run mentions that as a
note ("May be the same as 10003 …"); the note does not stop the import. An
anonymised customer is not changed.

The **report** names for every row whether the customer is new, whom they
are merged with and by what they were recognised, or whether they stay
unchanged.

- **Default discount** is imported only by someone who may see prices;
  otherwise the import stops ("Importing discounts needs the right to see
  prices.").

## Personnel

One row per person. Whoever may edit the personnel may import. Every person is an account (AUT-026): a newly created person gets an account
with a user name from their name, without a password and with the role Crew,
a freelancer with the role Freelancer (in German: Freie Kraft). They can
only log in once they are invited under Settings → Users or get a one-time
password.

| Column | Required | Recognised headings | Meaning |
|---|---|---|---|
| Name | (*) | Name, "Name, Vorname", "Nachname, Vorname", Person | "Last name, First name" as in the exported list, or "First name Last name" |
| Vorname (first name) | | Vorname, First name | |
| Nachname (last name) | (*) | Nachname, Familienname, Last name | |
| Art (kind) | | Art, Beschäftigung, Anstellung, Kind | permanent employee (also fest, festangestellt, angestellt, Mitarbeiter), temporary staff (also Minijob), freelancer (also frei, Freelancer, freiberuflich) |
| Funktionen (job functions) | | Funktionen, Funktion, Job functions, Tätigkeiten | see below |
| E-Mail | | E-Mail, E-Mail-Adresse, Mail, Email | recognises existing people |
| Telefon (phone) | | Telefon, Tel., Mobil, Handy, Phone | |
| Firma (company) | | Firma, Company | |
| Straße (street) | | Straße, Strasse, Anschrift, Street | |
| Postleitzahl (postal code) | | Postleitzahl, PLZ, Postal code | |
| Ort (city) | | Ort, Stadt, Wohnort, City | |
| Steuernummer (tax number) | | Steuernummer, St.-Nr., Tax number | |
| USt-IdNr. (VAT ID) | | USt-IdNr., USt-ID, VAT ID | |
| Notiz (note) | | Notiz, Bemerkung, Note | |
| Aktiv (active) | | Aktiv, Active | yes/no |

(*) A column must be assigned to "Name" or "Nachname".

- **Who is who:** a person is recognised by their e-mail address, otherwise
  by first and last name. If there are several people of the same name and
  no e-mail address that tells them apart, the dry run reports an error.
  Whoever is not found is created. An e-mail address belongs to exactly one
  account; if the file names the address of another account for a person,
  that is an error ("This e-mail address is already used by another
  user.").
- **Funktionen** are in one cell, separated by commas or semicolons:
  `Tontechnik, Licht`. Each must already exist in Rentalars. Rates of their own go after a colon, the **hourly rate** and, after a
  slash, the **day rate**:

  | Cell | means |
  |---|---|
  | `Tontechnik: 35,00/280,00` | Tontechnik with €35.00 per hour and €280.00 per day |
  | `Tontechnik: 35,00` | only an hourly rate of its own |
  | `Licht: /250` | only a day rate of its own |
  | `Rigging` | without rates of its own – the guide values of the job function apply |

  Several together: `Tontechnik: 35,00/280,00, Licht: /250, Rigging`. A
  comma in a rate (`35,00`) does not separate job functions. A **new** job
  function gets the rates of the row without "Valid from", that is from the
  start – or none of its own; the import does not copy a guide
  value in as a rate of its own, and a job function without a guide value needs no
  rate. If the person already has the job function, it keeps
  its rates unless the row names others; those then apply from the day of
  the import, and a rate the row does not name is taken over from the
  previous ones. The import never takes a job function away. The list of
  people exported from Rentalars names only the job functions, without
  rates; read in, it changes nothing about the rates.
- **Hourly and day rates** are personnel costs: they are imported only by
  someone who may see personnel costs ("Importing hourly rates needs the
  right to see personnel costs."). Job functions without rates can be
  assigned by anybody who may edit the personnel.

## In the browser

The imports are where the lists are, and collected under
**Settings → Import and export**:

| List | Where | Right |
|---|---|---|
| Material | Material management → Import, tab "Material items" | edit material |
| Products | Material management → Import, tab "Products" | edit products |
| Customers | Customers → "Import" | edit customers |
| Personnel | Personnel → "Import" | edit personnel |

1. **Choose the file** and upload it.
2. **Assign the columns.** For every field Rentalars shows which column it
   has recognised, and the first values from it. If something is wrong,
   choose the right column – or "– do not import –". Then **"Dry run: check
   without writing"**.
3. The report shows what would happen, or the errors with row and column.
   Without errors, **"Import now"** appears.

**Dry run and import run as a task in the background** (NFA-041). The page
shows the progress and, as soon as the task is finished, the report. You can
keep working in the meantime; when it is finished you get a notification,
and you find it again under My account → Tasks in the background. There is
no upper limit for the number of rows in the browser. (For comparison: checking and importing 1,650 rows of material took about a quarter of
a minute.)

The uploaded file stays on the server between the steps
(`/var/lib/rentalars/imports/`, under a random name). It is deleted after
the import, with "Use a different file" or after two days at the latest.

The link **"Export in the import format"** is at the top of
every import page and next to every import under Settings → Import and
export (below).

## Via the API

```
GET  /api/v1/imports/{kind}          which fields, which headings are recognised
POST /api/v1/imports/{kind}          dry run or import
GET  /api/v1/imports/{kind}/export   the export in the import format (below)
```

`{art}` is `material`, `products`, `customers` or `people`. The same rights
apply as in the browser. `POST` takes the file as `file` (multipart) and
these parameters:

| Parameter | Meaning |
|---|---|
| `dry_run` | `true` (default): only check; `false`: import |
| `mapping` | assign columns by hand, as JSON: `{"name": "Gerät"}`; the value is the heading, the number of the column (from 0) or empty for "do not import" |
| `sheet` | for Excel files with several sheets: which sheet (otherwise the first) |
| `background` | `true`: as a task in the background |

**Without `background`** the import runs in the request itself, and a file
may have at most **5,000 rows** – a request to Rentalars may take at most two
minutes. The response is the report (status 200, with errors 400), plus,
under `mapping`, which heading filled which field. Every error names `row`,
`column`, `message` and, as `text`, everything in one sentence.

**With `background=true`** there is no upper limit. The response (status
202) is the task; `GET /api/v1/jobs/{id}` says how far it has got and
contains, once it is finished, the report under `result.report`:

```sh
curl -H "Authorization: Bearer rl_…" \
     -F file=@kunden.xlsx -F dry_run=false -F background=true \
     https://rentalars.example.de/api/v1/imports/customers
```

## On the command line

If you prefer to work on the server. The commands have no upper limit.

The file must be readable for the service account of Rentalars. The easiest
is to put it into the directory intended for this:

```sh
sudo cp bestand.xlsx /var/lib/rentalars/imports/
sudo chmod 644 /var/lib/rentalars/imports/bestand.xlsx
```

The browser uses the same directory for its uploaded files. The daily
maintenance, however, deletes only those there – they carry a random name of
32 characters – when they are older than two days. What you put in yourself
stays; delete it after the import.

### Material: `import_material`

**Dry run** – that is the normal case, without any further option:

```sh
sudo rentalars import_material /var/lib/rentalars/imports/bestand.xlsx
```

```
File: /var/lib/rentalars/imports/bestand.xlsx, 5 rows
Column mapping:
  inventory_number         ID *                             “ID”
  name                     Artikelname *                    “Artikelname (evtl. gekürzt)”
  category                 Kategorie *                      “Kategorie”
  …
  manufacturer             Hersteller                       –

Material models: 3 new, 0 changed
Items: 5 new, 0 changed, 0 unchanged
2 item(s) linked as “permanently installed” (switch single ones to “loosely contained” where needed):
  0310 → 0500
  0311 → 0500
Highest ID: 0743, next new ID: 0744
Dry run without errors. Use --commit to import.
```

A dash in the column mapping means: no column was found for this field.

**With errors** the end looks like this – all errors of the file at once, so
that you can fix them in one go:

```
Error: Row 6, Artikelname: The article name is missing.
Error: Row 7, Kategorie: The category is missing.
Error: Row 9, ID: The ID 0500 already occurs in row 4.
CommandError: 3 error(s). Nothing was imported.
```

An entry that cannot be read (purchase price "neun", invoice date "32.13.2019",
Einsatz/Verbindung pointing at an ID that does not exist) is **no error** any
more: the report names it as a note, the item gets the status
"import error" (above), and it is imported all the same.

The row number is the one from Excel.

**Actually importing:**

```sh
sudo rentalars import_material /var/lib/rentalars/imports/bestand.xlsx --commit
```

### Products, customers, personnel: `import_data`

The same, with the kind of list in front – `products`, `customers` or
`people`:

```sh
sudo rentalars import_data customers /var/lib/rentalars/imports/kunden.xlsx            # dry run
sudo rentalars import_data customers /var/lib/rentalars/imports/kunden.xlsx --commit   # import
```

```
File: /var/lib/rentalars/imports/kunden.xlsx, 3 rows
Column mapping:
  number                     Nummer                           “Kundennummer”
  name                       Name *                           “Firma”
  …
  active                     Aktiv                            –

Note: Row 4: May be the same as 10003 Kulturverein Musterstadt (similar name).
Records: 2 new, 1 changed, 0 unchanged
Dry run without errors. Use --commit to import.
```

On the server all rights apply: prices, discounts, hourly and day rates are
taken over without further ado. `import_data material` exists as well and
names the number of items ("Items: … new, … changed, … unchanged"); for the
material list, however, `import_material` is more talkative (models, links,
next ID).

**Further options** (both commands):

| Option | Purpose |
|---|---|
| `--show-mapping` | only show the recognised column mapping |
| `--map "FIELD=COLUMN"` | assign a column by hand, e.g. `--map "inventory_number=Inv.-Nr." --map "name=Gerät"`; can be used several times. `FIELD` is the name on the far left in the column mapping, `COLUMN` the column. `--map "note="` leaves a field out. |
| `--sheet NAME` | for Excel files with several sheets: which sheet (otherwise the first) |

## After the import

**Material:**

1. **Number range.** The next new material ID now comes after the highest
   one imported. To look and change: "Settings → Number ranges".
2. **Check new categories** ("Settings → Categories and codes"): are
   the codes right? As long as no product carries an article number with the
   code, it can be changed.
3. **Switch loose contents.** Everything from "Einsatz/Verbindung" counts as
   permanently installed after the import. Cables in the case, microphones in
   the box: set them to "loosely contained" on the item, so that they can
   also be planned on their own.
4. **Assign products.** Material can only be planned once it is assigned to
   a product. "Material management → Open points → Material without
   product" shows what is still missing.
   Create the products – that can be done with an import, too, see above –
   and enter them on the model; that then applies to all items of
   the model. How this works is in the [user manual](../user-manual.md),
   "Assigning material to a product".

**Customers:** customers with a number taken over do not move the number
range; new customers get the next free number, numbers already given are
skipped.

Every import is in the change log with time, user and figures; every record
created or changed has its own entry.

## Importing again

You have kept working on the list or corrected errors? Just load it again.

- What already exists (same ID, article number, e-mail address or same name
  of a person; for customers see above, "Who is who") is **updated** with the
  data of the file. The dry run shows how many would change.
- Fields for which the file has **no column** – or whose column you set to
  "do not import" – stay untouched. So whatever you have maintained in
  Rentalars in the meantime is not lost.
- Records that are **missing** from the file stay as they are. The import
  never deletes anything.

**Empty cells** work differently depending on the column:

- **Material:** for **Seriennummer, Notiz, Rechnungsdatum,
  Rechnungsnummer, Kaufnotiz, Kaufpreis, Händler, Artikelnummer beim
  Händler** and **Einsatz/Verbindung** the file counts – also where its cell
  is empty: an empty cell empties the value in Rentalars or removes the link.
  **Beschreibung, Kategoriespezifische Angabe, Leistung, Hersteller,
  Kurzname, Produkt, Menge, Status** and **Lagerort** are only set where the
  file contains something. A link that already exists stays as it is – even
  if you have switched it to "loosely contained" in the meantime. In a
  column of a **custom field** the file counts as well: an
  empty cell empties the value (above, "Custom fields"). Likewise for the
  **protection class** of an item: an empty cell takes its
  own class away; the class of a model that has one stays (above, "How the
  data is read").
- **Products, personnel:** for the text, price and number columns the file
  counts; an empty cell empties the value (for the minimum stock: no
  warning). An empty name of a product and a missing last name of a person
  are errors. An empty "Kategorie" sets a product to its main category.
  **Art, Abrechnungsart, Einheit, Steuerart** and **Aktiv** stay as they are
  with an empty cell; so do the job functions of a person.
- **Customers:** an empty cell never changes anything (above,
  "Customers"). A row without any name – neither name nor first or last
  name – is an error.

As soon as you work with Rentalars, Rentalars is the truth. The repeated
import is meant for the transition period and for changes to many records at
once (export, change in the spreadsheet, read in again), not as a permanent
synchronisation with an Excel list.

## Export in the import format

(IMP-017) each of the four imports has an export in exactly the
format of the import – so that a list can be used further without
Rentalars, edited in a spreadsheet and read in again. In the browser under
**Settings → Import and export** next to each import and at the top of the
import page ("Export in the import format"), through the API with
`GET /api/v1/imports/{kind}/export` (`material`, `products`, `customers`,
`people`).

**The file:**

- **Exactly the columns of the import**, under the same headings and in the
  same order as in the tables above; for material, after them one column
  per custom field, headed with the name of the field.
- **Plain text instead of internal IDs:** the ID of an item with leading
  zeros, "Einsatz/Verbindung" as the ID of the device, category and storage
  location as a path (`Ton > Mikrofone`, `Halle 1 > Regal A`), supplier,
  manufacturer, unit and tax rate by their names, the product of a model
  and the owner of customer material by article or customer number, the job
  functions of a person with the rates that apply today
  (`Licht: 28,00/250,00, Tontechnik: /280,00, Rigging`), an item bought as
  part of a set with `#0851` in the purchase price column, in
  the column "Schutzklasse" the class that applies to the item – its own,
  else its model's – as `I`, `II` or `III`.
- **Written as the import reads it:** UTF-8 with byte order mark,
  semicolon, numbers with a decimal comma and no thousands separator
  (`1234,50`), dates as `31.12.2027`, "ja"/"nein", choices by their German
  names – always in German like the headings, whatever language the user
  works in. Text a spreadsheet would run as a formula gets an apostrophe in
  front; the import takes it away again (above, "The file").

**Rights.** Whoever may read the list (read access to the module of the
import) may download it. Columns with prices, the maximum discount and the
rates of vehicles need the right "See prices and calculation", purchase
prices and the internal costs of vehicles "See purchase prices", and so do
confidential custom fields; without the right **the column is missing**.
For people the column "Funktionen" stays, but without the right "See
hourly rates and personnel costs" it names only the job functions.
Importing such a file again leaves these values as they are – for the
missing columns, what is said above under "Importing again" applies.

**There and back changes nothing.** Imported again, the dry run calls every
row "unchanged"; edited in a spreadsheet, the file changes exactly what was
edited. This is tested.

**What is not in it:** what the import does not know – for material the
item's own description and own category-specific values, for customers a
fourth contact person, further billing and delivery addresses and the
position of the first contact, and of course projects and their lines.
Anonymised customers and people are left out: the import would refuse the
customers and create the people anew. For all data at once there is the
readable export under Settings → Backup ([operation.md](operation.md),
"Full data export"; [backup.md](backup.md), "The readable export is not a
backup").

**Large stocks.** The file is written while it is sent, in chunks of 2,000
records and with a fixed number of database queries per chunk; 20,000
items take a few seconds. There is no background task and no upper limit.

## If it does not work

| Message | Remedy |
|---|---|
| "Only XLSX and CSV files can be imported." / "The file is not a readable XLSX file." | The file has a different format (even if it is called `.xlsx`). Open it in Excel and save it again as `.xlsx`. |
| "The file is too large (at most 25 MB)." | Split the file or save it as CSV (smaller). |
| "No column of the file is assigned to this required field." | The heading of a required field (material: ID, Artikelname, Kategorie; products: Art.-Nr., Name; customers: Name or Vorname or Nachname) is called something else in your file. Assign it in the browser or use `--map`. |
| "“…” already has the category … from row …; this row differs." (note) | Same article name, different categories. The first one counts; make the list consistent. |
| "The ID … already occurs in row …" / "The article number … already occurs in row …" | Duplicate key in the file; correct one of the two rows. |
| "The ID … does not exist." (Einsatz/Verbindung, a note) | The item named is neither in the file nor in Rentalars. A typo? The item is taken over without the connection and has the status "import error"; the note names the cell. |
| "… names several items … taken over into the note" / "… is not the ID of an item – taken over into the note" (note, Einsatz/Verbindung) | The cell held several IDs or free text. No connection was made; the text is in the note of the item. If a connection was meant: enter only one ID in the file or make it on the item. |
| "The material model “…” has no custom field “…” in its fieldset." (material) | The row has a value in the column of a custom field that is not part of its model's fieldset. Empty the cell or give the model the right fieldset. |
| "“…” is not a protection class. Write I, II or III." (material) | The column "Schutzklasse" holds something other than I, II, III, 1, 2 or 3 (with or without "SK", "Schutzklasse" in front). Correct it or empty the cell. |
| "The column is not imported: the values of this field need the right to see purchase prices." (note) | A confidential custom field; let someone with the right "See purchase prices" do the import. |
| "There is no category with the code …" (products) | The letters of the article number match no main category. Create the category or correct the article number. |
| "Importing prices needs the right to see prices." (likewise maximum discount, discounts, hourly and day rates) | Set the column to "do not import" or have someone with the right do the import. |
| "There is no job function “…”." (personnel) | Create the job function under Personnel → Job functions or adjust the name in the file. |
| "There are several people named …" (personnel) | Add a column with the e-mail address. |
| "The file has … rows. In one request at most 5000 rows can be imported." (API) | Send it with `background=true` or import on the server. |
| "Permission denied" / file not found (command line) | The service account cannot read the file. Put it into `/var/lib/rentalars/imports/` (see above). |
