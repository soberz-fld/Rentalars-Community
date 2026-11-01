# Glossary of the interface (UIX-063)

One word for one thing. This is the list the texts of the interface follow – in the code (English message
IDs), in the German translation and in the manuals. It came out of a review (B5, B6), which found the
same thing under several names. When a text needs a new word, look here first; when you add one, add it here.

The German column is the word of the user interface (`locale/de`), the English column the message ID.

## Material

| English | German | Means | Not used for |
|---|---|---|---|
| item | Exemplar | one physical piece, with its own ID on the label | – |
| model | Materialmodell | a type of article as in the maker's catalogue | – |
| product | Produkt | what is planned, offered and charged | – |
| container | Behälter | a case, rack or road case that holds other items (“Case”, “Rack” are kinds of it) | “Gerät” |
| device | Gerät | only an electrical device or fixture (the unit of an electrical inspection, a fixture in an MVR file, a device that logs in) | a case or rack |
| contents | Inhalt | what is in a container; “fest verbaut” or “lose enthalten” | – |
| photo | Foto | a picture a person took, made anew on upload with its place only (NFA-084); the kind “picture” of a file of the material reads “Foto” | “Bild” (a logo, a map image) |

## People

| English | German | Means | Not used for |
|---|---|---|---|
| crew | Crew | the people planned on a project (“Crew und Fahrzeuge”, “Crew dieser Phase”) | the module or the cost type |
| contact person | Ansprechpartner | a person of a customer (“Neuer Ansprechpartner”) | “Kontakt” alone |
| personnel | Personal | the module (“Personal”), and the cost type (“Personalkosten”, “Personaleinnahmen” – one word, no hyphen) | the people of one project |
| freelancer | Freie Kraft | the role; always written with a capital letter (`capfirst`, never `capitalize()`) | – |

## Requests and orders

| English | German | Means | Not used for |
|---|---|---|---|
| inquiry | Anfrage | the status of a project, and a request that arrived by mail or by telephone | – |
| crew request | Einsatzanfrage | the request to a person to take a place on a project | “Anfrage” alone |
| request refused (error 400) | Aufruf abgewiesen | the title of the error page for a bad request | “Anfrage abgewiesen” |
| order | Auftrag | what a customer gives (“Auftragsbestätigung”) | a job in the background |
| job | Aufgabe | something that runs in the background (backup, export, the summaries of the night) | an order of a customer |

## Statuses

| English | German | Why this word |
|---|---|---|
| packing list: returned | zurückgenommen | “zurück” would read like the Back button |
| service case: backlog | zurückgestellt | “Rückstand” sounds like arrears of payment |
| project: confirmed – details open | Bestätigt – Preise und Einzelheiten offen | the status counts as firm, but prices can still change; the name says so |
| material that was issued | unterwegs | where the material is (“5 von 9 Stück sind unterwegs”, project head, lists); “außer Haus” is the label of the rental period, “draußen” is not used |
| packing list: issued | ausgegeben, teilweise ausgegeben | the status of the packing list names the act, and it is “zurückgenommen” when the material is taken back by us |
| subrental: returned | zurückgegeben | the same English word as the packing list's “returned”, the other direction: it goes back to the supplier (`pgettext`, context “subrental status”) |

## Writing

* The interface says **du**. Texts to customers (documents, mails in the name of the firm) say **Sie**. A text that is
  both is written for the one who reads it.
* A number with a noun is written with `ngettext` or `{% blocktranslate count %}` – never “Position(en)”, never “1 Tage”.
  `plural_of` gives the number that decides between the two forms when the value is a `Decimal` or a text.
* A word that means two things in two places gets a context (`pgettext`): `group` of a directory is “Gruppe”, `Message` of
  the chat is “Nachricht”, “Apply” of a filter is “Anwenden” and not “Übernehmen” (which is “take over”).
* The first letter of a text is made capital with `capfirst`. `str.capitalize()` makes the rest small
  (“Freie kraft”) and is not used.
* A date has a four-digit year (`d.m.Y`, `D d.m.Y`), written by `local_pattern` or the filter `date`, so that the English
  reader gets `dd/mm/yyyy`. A fixed `strftime("%d.%m.%Y")` is only for files with a format of their own (DATEV, exports).
  Numbers that are shown go through `format_decimal` or `number`, so that the decimal comma follows the language.
* A selection without a choice reads “– bitte wählen –” (`core/choices.py` replaces Django's `---------` once, at the
  start).
