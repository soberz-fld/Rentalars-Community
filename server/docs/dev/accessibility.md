# Accessibility

Rentalars follows WCAG 2.1 level AA as far as a web application of this kind
can (NFA-025). This page says what is checked automatically, what was looked
at by hand, and what to keep in mind when adding a page.

## Checked automatically

**On every test run** – `tests/ui/test_accessibility.py` reads the HTML of
about forty main pages (lists, forms, details, planning, packing,
documents, administration, the login) with the demo data and fails if

- the page has no language (`<html lang>`),
- a field (`input`, `select`, `textarea`) has neither a `<label for>` nor
  an enclosing label, `aria-label`, `aria-labelledby` or `title`,
- a link or button has no text and no `aria-label` (an icon alone is not a
  name),
- an image has no `alt`,
- a progress bar has no name,
- an ID occurs twice on one page,
- the page has not exactly one main heading (`h1`).

**In a real browser** – `tests/browser/test_accessibility_in_browser.py`
runs axe-core with the rules of WCAG 2.0 and 2.1, levels A and AA, over
the same main pages, including colour contrast, and checks that the first
Tab leads past the navigation. axe-core is not part of Rentalars; the test
runs when it is at hand:

    npm pack axe-core@4.10.2 && tar xzf axe-core-4.10.2.tgz
    RENTALARS_AXE=$PWD/package/axe.min.js python manage.py test tests.browser.test_accessibility_in_browser

Result (12 October 2026): no finding on 31 pages after two
corrections – the progress bars of the packlist and of background tasks had
no name, and the block form of an item repeated the ID `id_reason` of the
status form.

## Looked at by hand

- **Keyboard:** every action is a link, a button or a form field; nothing
  needs a mouse. The lines of the planning, which are sorted by dragging,
  move with the arrow keys on their handle (a button); to another group
  through their edit form. `tests/browser/test_planning_in_browser.py`
  checks it. A skip link („Zum Inhalt springen“) is the first stop of
  the Tab key. The focus is always visible (`:focus-visible` with the
  accent colour). Dialogs are native `<dialog>` elements.
- **Order of reading:** one `h1` per page, sections below it as `h2`;
  lists are tables with column headings; on the phone the table rows become
  blocks whose cells carry their heading (`data-label`).
- **Colour is never the only sign:** statuses are badges with text, the
  tape on the packlist says "issued" or "missing", the timeline has a
  legend.
- **Language:** German throughout, plain words, no jargon beyond the
  trade's own.
- **Messages** that appear after a change in the background are in regions
  marked `aria-live`. The messages after a page load
  (`templates/core/_messages.html`) are a `<div role="status">` around
  `<ul class="messages">`, so the list keeps its role and its items stay
  list items.

## Project head and further measures

- **Head of a project** (PRJ-078): the status is a `<select>` with a
  visually hidden label ("Status ändern auf", `class="visually-hidden"`);
  the button "Status ändern" is disabled until a status is chosen, and
  "Storniert" asks first. The menus behind ▾ are `<details
  class="menu">`; they close on a click elsewhere or on Escape, and Escape
  puts the focus back on their `<summary>` when it was inside.
- **Type-ahead fields** (VFG-025) are comboboxes: `role`,
  `aria-autocomplete`, `aria-expanded`, `aria-controls`,
  `aria-activedescendant` and ids on the options, in `setUpTypeahead` – for
  every such field, not only the new search of the utilization.
- **Planning** (PRJ-082, PRJ-083): every line and every section has a
  labelled check box (also on phones); the button "optional" is a toggle
  with `aria-pressed`, not only an orange frame.
- **Mail** (EML-043): "Crew hinzufügen" and "Kunde hinzufügen" say in a
  `role="status"` line which addresses they added.
- **Week of the availability calendar** (PER-030): the heads of the days
  are the buttons for choosing days; colours are explained by a legend, as
  on the person's timeline.
- New browser tests run axe-core on the new or changed pages of mail,
  personnel, planning, lines and packing
  (`tests/browser/test_062_{mail,personnel,planning,lines,packing}_in_browser.py`);
  those of crew, documents and the project head check behaviour only. The
  former tab "Dateien" left the accessibility lists – it is the tab
  "Dokumente" now.

## Filters that fold away and further measures

- **Filters that fold away** (UIX-030): the button "Filter" carries
  `aria-expanded` (set by the script; without scripts the button is hidden
  and every field shows), `aria-controls` naming the panel and
  `aria-describedby` naming the summary of the active filters. The count
  is part of the button's text ("Filter (2)"), so it is read out; the
  chevron is `aria-hidden`. A form with an error is never folded, and Enter
  in the search field still sends the form while its submit button is
  folded away. The chevron turns only with `prefers-reduced-motion:
  no-preference`.
- **A dialog over a dialog** (PRJ-094): "Neue Phase …" opens a native
  `<dialog id="phase-dialog">` with `aria-labelledby` on its heading,
  stacked over the dialog of the crew line. Its fields have the prefix
  `new-phase-`, so no ID occurs twice while both are open; the focus goes
  to the first field (or the first with an error). Its buttons and Escape
  close only this dialog, and the focus returns to the phase list it came
  from. Arrow or letter keys that land on the entry only select it – Enter
  or Space opens the dialog, and leaving the list puts the former phase
  back –, so a mere selection never opens a dialog (WCAG 3.2.2).
- **The pages without login** are centred in one column at every width,
  and the setup form fits at 320 px without scrolling sideways (WCAG
  1.4.10).
- **The company name** (UIX-032) at 480 px and below stands at the top of
  the opened menu; in the top bar it is then visually hidden, not removed,
  so screen readers still read it with the brand.
- **Customer material** is a badge with text ("Kundenmaterial – wird
  mitgeführt"), never a colour alone.
- Browser tests with axe-core: `tests/browser/test_063_{ui,phases,crewmail,ownmaterial}_in_browser.py`
  (every list with filters, folded and open; the pages without login; the
  stacked dialog with the keyboard; the mail settings at phone width; the
  product form and the pages with customer material).

## Date and time picker and further measures

- **The date and time picker** (UIX-036). The fields keep their native
  type, so typing stays possible and a screen reader still hears a date
  field. The added button (`.dt-btn`, `aria-haspopup="dialog"`) is a real
  button named after its field ("Datum wählen: Von", "Datum und Uhrzeit
  wählen: …", "Uhrzeit wählen: …") – one more Tab stop per field. It opens
  a native `<dialog>` labelled by its heading; the focus returns to
  what opened it, Escape closes without change. In the calendar the days
  are buttons in a table with a caption; only one day is in the Tab order
  (roving `tabindex`), the arrows move by day and week, Page↑/↓ by month,
  Home/End to the start and end of the week, Enter or Space pick. Days
  outside `min`/`max` carry `aria-disabled="true"` but stay focusable, so
  the keyboard can pass them. The month name is `aria-live="polite"`.
- **The clock face is a `role="slider"`** with `tabindex="0"`,
  `aria-label` "Stunde" or "Minute", `aria-valuemin` 0,
  `aria-valuemax` 23 or 59, `aria-valuenow` and `aria-valuetext` with the
  whole time ("08:30"). Arrows change the value by one, Page↑/↓ by three
  hours or five minutes, Home/End go to the first and last value, digits
  go into the hour or minute field, Enter goes from the hour to the minute
  and then takes the time. The SVG drawing is `aria-hidden`; hour and minute are
  also two labelled text fields (`inputmode="numeric"`), so nobody has to
  aim at the dial. On a phone date and time take turns; after the day the
  focus moves to the clock.
- **Hatched periods** (PRJ-099). The rental and the event period are told
  apart by two hatchings in opposite directions plus colour, never colour
  alone; a legend under the calendar names each period with its times, and
  the label of every marked day adds the period's name ("… – Mietzeitraum,
  Veranstaltung"). The legend's swatches are `aria-hidden`.
- **Required fields** (UIX-035). The asterisk is `aria-hidden`; the field
  itself says it is required – `required`, or `aria-required="true"` for a
  field the model requires (`mark_required`). A field required only under
  a condition gets `required` from the script while the condition holds,
  and its asterisk shows and hides with it. The note "* Pflichtfeld" at the
  top of a form is `aria-hidden` too (it explains a visual sign).
  Required selects without an empty option keep their asterisk but get no
  `aria-required`, as they always have a value.
- **The packlist bar** (PCK-029) is `aria-hidden`; what it shows stands
  under it as a list with a name ("Wo die Stücke sind"), each state in
  words and numbers ("4 zurückgenommen, 2 ausgegeben, 4 im Lager"). The
  hatchings of "packed" and "ticked as back" set them apart from "issued"
  and "taken back" without colour.
- **Sub-tabs of the packlist** (PCK-030) are a `<nav>` with a name
  ("Packlisten des Gesamtprojekts und seiner Teile" in a family) and
  `aria-current="page"` on the tab shown; the status of each packlist is a
  badge with text.
- **Personnel plan colours** (VFG-027): bar text stays in the normal text
  colour on a 30 % tint (5:1 or better in both themes); "angefragt" is a
  dashed band, not only a paler fill; the legend lists every state,
  "Projekt-Anfrage" included.
- **The phase question** (PRJ-100) on the Zeitplanung gets the focus on
  "Erweitern"; in the dialog it replaces the content, and the note "Es gibt
  Neues auf dieser Seite" uses the region of UIX-020 instead of reloading
  under the user.
- The links to the API documentation open in a new tab without a hint;
  the project has no convention for that yet (UIX-037).
- Browser tests with axe-core: `tests/browser/test_070_{pickers,planning,packing,crew}_in_browser.py`
  (the picker with keyboard and at phone width, the hatched periods, the
  required marks, the personnel plan and its legend, the packlist with
  bar, legend and sub-tabs at 1360 and 390 px without sideways scrolling,
  the crew answers). Not tried: a real screen reader; Firefox and Safari
  (Chromium only).

## Dialogs over dialogs and further measures

- **A dialog over a dialog from a type-ahead** (PRJ-101). "„…“ als neuen
  Lieferanten anlegen" in the supplier field of the subrental dialog opens
  a native `<dialog id="create-dialog">` on top of the line dialog
  (`app.js`, block PRJ-101), named by its heading (`aria-labelledby`). The
  focus goes to its first field, or the first with an error; its buttons
  (`data-close-dialog`) and Escape close only this dialog, and the focus
  returns to the type-ahead field with the caret at the end – a moment
  later, because Chrome ignores typing that comes right after a dialog
  closed. Everything typed in the line dialog stays. The field keeps the
  combobox roles of VFG-025; the last option says what it does ("… als
  neuen Lieferanten anlegen").
- **Bars that can be told from the background** (VFG-030). Every bar of a
  project status or a deployment has a 1 px frame in its colour, at least
  3:1 against the panel in the dark and the light theme (WCAG 1.4.11 –
  `tests/browser/test_071_planning_in_browser.py` measures the frames of
  grey and yellow bars); phases, absences, blocks and availability are
  framed too. States never rest on colour alone: "angefragt" is a dashed
  band, a cancelled project or a declined request is struck through (the
  latter also hatched red), open places are hatched with a dashed frame,
  and the legends name every state. Labels do not run over other bars:
  they end with "…", and each bar's `title` holds the whole text.
- **The timeline on the Zeitplanung** (PRJ-103) is built like Planung →
  Zeitstrahl – a label per row, the same navigation buttons, a legend of
  the crew colours; names are links only for those who may open the
  person. It sits below the open items, which keep their place at the top.
- **Filters folded on every width** (UIX-038): the markup of UIX-030 applies – `aria-expanded`, `aria-controls`, the counted
  "Filter (2)" –; a filter with an error is never folded, and
  without scripts every field shows.
- **One serial number field per item** (MAT-050). The script replaces the
  labelled textarea by a `<fieldset>` whose `<legend>` is the textarea's
  label, with one labelled field per item ("Exemplar 1", "Exemplar 2" …)
  in a list; the help text is tied to the group with `aria-describedby`.
  Enter moves to the next field instead of sending the form (a scanner ends
  every code with Enter). Without the script the textarea takes one serial
  number per line.
- **Text fields with suggestions for manufacturer, product and "Gekauft
  bei"** (MAT-048, MAT-050) are plain text fields with the combobox roles:
  the typed name is the value, so they work without the script and
  without choosing a suggestion.
- **Kind before category** (PRD-046): choosing kind or category of a new
  product reloads the form (`data-reload-fields`), as choosing the
  category did before; the lead text asks for the kind first ("Wähle
  zuerst die Produktart, dann die Kategorie …") but does not announce the
  reload. In a browser that fires `change` while the arrow keys walk
  through a closed list, the form reloads at the first step (WCAG 3.2.2) –
  a known point, unchanged since the category did the same.
- **Deleting a mailbox** (EML-046) is a page, not a script dialog: it lists
  what follows in a plain list, offers the successor as a labelled `select`
  with a help text tied by `aria-describedby` (or names the one successor
  in a note), has "Nur ausschalten" as a second button, and works without
  scripts.
- **The follow-up** (PRJ-105) is a dialog with labelled fields (a page of
  its own without scripts); in the head of the project it is text with a
  badge "fällig", not a colour alone.
- Browser tests with axe-core: `tests/browser/test_071_{services,subrentals,material,planning,settings}_in_browser.py`
  (the product form with the hour tiers, function and product linked, the
  crew planning with the hours beyond the limit at phone width; a new
  supplier in the dialog over the subrental dialog, the page "Zumietung
  bei …"; the serial number fields, the suggestions for manufacturer and
  product, the product form, assigning a model and "Als Produkt anlegen";
  the bars and their frames, the timelines in hours and weeks, the
  Zeitplanung, phone width, filters folded on a wide screen; the follow-up
  dialog, the start page and the project list with follow-ups, the
  mailbox confirmation at phone width). Not tried: a real screen reader;
  Firefox and Safari (Chromium only).

## Keyboard dragging and further measures

- **Dragging has a keyboard way** (VFG-026). A bar that can be moved is a
  link (in Planung → Zeitstrahl to the project, in the Zeitplanung to the
  dialog of the move, with a visually hidden "… verschieben:" before its
  label) and carries `aria-describedby="tl-move-hint"`, the visible text
  that names the keys. On a focused bar ← and → move it by 15 minutes,
  with Shift only its end; the new times go to a visually hidden
  `aria-live="polite"` region (`data-tl-announce`); Enter opens the dialog
  with the consequences, Escape puts the bar back. The grips at the ends,
  the dashed frame and its tooltip are `aria-hidden`. The dialog is a
  native `<dialog>` named by its heading (`aria-labelledby="move-title"`),
  its times are the picker fields of UIX-036, so the times can always be
  typed instead of dragged; without scripts it is a page of its own. After
  saving, the page reloads and the focus returns to the moved bar. A finger
  does not drag (the timeline scrolls), and nothing needs a drag (WCAG
  2.5.7).
- **The map is an extra, the list is the content** (UIX-034). Before the
  click there is only a button "Karte anzeigen" with a sentence saying what
  the click sends. The map is a `role="group"` named "Karte: …"; under it
  an ordered list names every place with its address, the source of its
  position in words ("Position von OpenStreetMap", "Position von Hand
  gesetzt", "Auf der Karte nicht gefunden.") and its route link – the numbers on the
  markers are `aria-hidden` and repeat the list's order. Problems are
  `role="status"`, errors `role="alert"`. **"Position korrigieren"** is a
  `<details>` with two labelled text fields (`inputmode="decimal"`) for
  latitude and longitude: the keyboard way to what the mouse does by
  clicking or dragging the marker, which fill the same fields. The zoom
  buttons of Leaflet carry German names ("Vergrößern", "Verkleinern"); the
  wheel zooms only while the map has the focus, so scrolling the page does
  not zoom by accident. The attribution "© OpenStreetMap-Mitwirkende" is a
  link, opening in a new tab.
- **Route links** say that they open Google Maps in a new tab (a visually
  hidden "(öffnet Google Maps in einem neuen Tab)"); the icon is
  decorative.
- **The chat** (UIX-010) is a tab like the others (`aria-current`); the
  unread count in it has a visually hidden "ungelesen". The messages are
  an ordered list named "Nachrichten", focusable (`tabindex="0"`) so it
  scrolls with the keyboard; each message is an `<article>` with the
  author as text and a `<time>`; "geändert" is a word, own messages are
  set apart by position and by their buttons, not by colour alone. The
  page says in text that the crew reads along, and "… Personen lesen mit"
  is a `<details>` with the names – each a button "… erwähnen", the crew
  marked with a badge. The field is labelled "Nachricht" with its help
  ("Mit @ und einem Namen erwähnst du jemanden … Strg+Enter sendet.") tied
  by `aria-describedby`.
  New messages of others replace the list in place; the list itself is
  not live (it would read everything again), but a separate
  `aria-live="polite"` paragraph (`[data-chat-announce]`) names the newest
  one: "Neue Nachricht von Ben Weber: …". The field keeps its content and
  focus.
- **The list of names after "@"** is a `role="listbox"` named "Erwähnen"
  under the field (`aria-autocomplete="list"`, `aria-controls`); the
  options are `role="option"` with `aria-selected`, the active one named
  by `aria-activedescendant` on the field, which keeps the focus. ↑/↓
  choose, Enter or Tab take the name, Escape closes the list without
  closing anything else; Ctrl+Enter still sends. Mouse users can click an
  option.
- **Recording expenses on the phone** (ZEI-019) is the dialog of the
  quick entry: one labelled field per row, kind and day side by side even
  at 375 px, the kilometres shown only for a trip and the amount's
  asterisk only where it is required (`data-show-if`, `mark_required`
  with a condition, UIX-035); the amount and the kilometres are text
  fields with `inputmode="decimal"` and a decimal comma, so phones offer
  the number pad. The receipt is a labelled file
  field (`accept` photo or PDF), for which phones offer the camera; its
  help says so. Statuses of expenses ("eingereicht", "erstattet" …) are
  badges with text. Icon-only buttons in the lists ("Spesen bearbeiten",
  "Spesen löschen") have names.
- **Hints at times** (ZEI-018) are text with an icon and a visually hidden
  "Hinweis:" – the colour only repeats what the text says –, and they block
  nothing.
- **Surcharges** (PER-009) are listed in words under amount and cost
  ("inkl. Zuschläge … Nacht 25 % auf 4 Std.") with visually hidden
  separators for screen readers; the settings page has one labelled field
  per percentage and the holidays as a table.
- **Service cases, dividing, show files** (PRJ-090, PRJ-050, PRJ-089): the
  status of a case is a badge with text; the page "In Teilprojekte
  gliedern" is a form with a labelled check box per group and a choice per
  crew line, labelled (visually hidden) "Wohin „…“ geht", and says in text
  why a group cannot go; the fields of a show
  file appear only for the type "Showfile" and are all visible without
  scripts.
- Browser tests with axe-core: `tests/browser/test_080_{projects,communication,maps,surcharges,times,planning}_in_browser.py`
  (the show-file upload, dividing, the pages of the service cases; the
  chat with a mention by keyboard and from the readers, messages in place,
  the unread badge, the automation form at phone width; the map of a venue
  with the policy of the page, correcting by click and by typing, the
  trips; the surcharge settings, the planning, the crew dialog and the
  price overview with surcharges; expenses by kilometre and with a photo,
  the hints in the confirmation, the approval and the report, at 375 px;
  dragging with the mouse and the keyboard, the dialog to type the times,
  the timeline on a phone, the documents without invoices). Not tried: a
  real screen reader; Firefox and Safari (Chromium only).

## Trash-can button and further measures

- **The trash-can button** (PRJ-107) on Projekte → Anfragen and in the
  list of a mailbox's further addresses is an icon button whose name is a
  visually hidden text ("von der Liste nehmen"; on a service case
  "Vom Servicefall nehmen", with the person's name in the `aria-label`); the
  mouse gets the same as `title`, and with keyboard focus
  (`:focus-visible`) the text becomes visible next to the icon. The tick
  boxes for removing several have names ("„…“ auswählen", "Alle auf
  dieser Seite wählen"), and "Ausgewählte von der Liste nehmen" asks in
  the Rentalars dialog first. The project number field is a type-ahead
  with the combobox roles of `setUpTypeahead`.
- **"In Zwischenablage kopieren"** (ZEI-026) is a named icon button; the
  result – "Kopiert" or "Kopieren hat nicht geklappt." – goes to a
  visually hidden `role="status"` `aria-live="polite"` paragraph
  (`data-copy-status`). The text uses a real TAB character. Where
  `navigator.clipboard` is missing (plain http) a hidden textarea with
  `execCommand('copy')` does it, and the focus returns to the button.
- **The dismissible hint** in Meine Zeiten (ZEI-024) has a named close
  button ("Diesen Hinweis ausblenden") and a link to Mein Konto →
  API-Token (`#tokens`).
- **Dragging has an alternative everywhere it is new.** Deployments in
  the personnel plan (VFG-031) use the keyboard way of VFG-026 unchanged:
  a focusable bar, ← and → (Shift for the end), the new times announced in
  the `aria-live` paragraph `data-tl-announce`, Enter for the dialog with
  typed times, Escape to put it back. Marking a range in the availability
  week (PER-039) is pointer or tap only; the keyboard way is the form
  below the week, which the marking only fills in – nothing needs a drag
  (WCAG 2.5.7).
- **The marked range in words** (PER-039): a paragraph above the colour
  buttons (`data-avail-selection`, `aria-live="polite"`) says what was
  marked, e.g. which days and from when to when, so the result of a drag
  is read out and visible as text.
- **Exact times without hovering** (VFG-032): every bar of the personnel
  plan has its times as `title` *and* as visually hidden text ("Mi
  10.03., 9:00 Uhr bis 13:30 Uhr"), so screen readers and keyboard users
  get what the mouse sees. A conflict is filled red, but the colour is
  never alone: the "!" before the name carries a visually hidden
  "Warnung: …", the legend says in words that conflicting deployments are
  filled red and that availability is hatched (hatching, not colour,
  tells availability from deployments).
- **Reordering surcharge rules** (PER-040): ↑ and ↓ on a rule card are
  named buttons ("Regel nach oben", "Regel nach unten"); after a move a
  visually hidden `aria-live="polite"` paragraph says the rule's new place
  ("Die Regel steht jetzt an Stelle 3.").
  Every rule card is a `<fieldset>` with a (hidden) legend "Regel 3" or
  "Neue Regel"; the fields of the other kinds are hidden with
  `data-show-if` and present without scripts; the cells align at the
  bottom, so label and field stay together at 375, 1280 and 1920 px.
- **Grouped tables** (UIX-040): the heading of a group is a `<th
  scope="colgroup">` spanning the row, with the count as text ("12
  Einträge"); "Gruppieren nach" is a labelled `<select>` in a GET form
  that also works without scripts. The notification settings group their
  rows under `<th scope="rowgroup">` per category (UIX-039), and the new
  column "In der App" has its own header.
- **Date and time fields** (UIX-042) keep one button with a name
  ("Datum und Uhrzeit wählen") and stay typeable; the browser's own
  indicator, which has no name of Rentalars', is hidden (Chromium) or
  covered (Firefox).
- **No "Zurück" on start pages** (UIX-041) – the navigation and tabs keep
  `aria-current="page"`; a test walks them.
- Browser tests with axe-core: `tests/browser/test_081_{mail,notify,service,times,plan,ui,surcharges}_in_browser.py`
  (wide and at 375 px; the surcharge settings also at 1280 and 1920 px).
  Not tried: a real screen reader; Firefox and Safari (Chromium only –
  the Firefox cover of the picker indicator is untested), dragging on a
  real phone.

## Filters always folded and further measures

- **Filters always folded** (UIX-038): the toggle keeps `aria-expanded`,
  `aria-controls` and `aria-describedby` (the summary of active filters);
  folded, its name includes the count ("Filter (2 aktiv)", translated text
  from `data-filter-active`) and the chips say in words what is filtered,
  so a filtered list is never only a visual state. A filter with an error
  still opens. The folded master-data filters of the Django admin are
  `<details>`/`<summary>` (keyboard and screen readers handle them
  natively) and name the chosen value in the summary ("Nach Aktiv: Ja").
- **Every column sorts** (UIX-015): the sort links are the headings as
  before; when a computed column cannot be sorted because the list is too
  long, the reason is a message with `role="status"` above the table
  (`table.sort_notice`), not a silently ignored click.
- **The project timeline like the personnel plan** (VFG-035): crew bars
  carry their exact times as `title` *and* visually hidden text; a
  conflict is filled red and, never by colour alone, marked with "!"
  before the name with a visually hidden "Warnung: …"; the legend says in
  words what red filling and hatching mean.
- **Changing the crew of a phase** (PRJ-110): the pencil and the bin at
  each crew line are icon buttons with names that say what and whom
  ("Licht – Max Muster ändern", "Offenen Platz Licht besetzen",
  "Personalposition Licht entfernen") and a `title` for the mouse; "anfragen"
  and "eintragen: zugesagt" are text buttons; warnings stand as text at
  the line.
- **Trips** (PRJ-111): "Fahrt anpassen" and "Fahrt entfernen" name the
  trip in their `aria-label`; "Zurücksetzen", "Zurückholen" and "Fahrt
  hinzufügen" are text buttons; removing asks in the Rentalars dialog; the
  dialog form uses `core/_field.html` (stops: one address per line in a
  labelled textarea). Changed and own trips have a text badge
  ("angepasst", "eigene Fahrt"), not a colour only. The route link keeps
  its visually hidden "(öffnet Google Maps in einem neuen Tab)".
- **Meine Einsätze** (UIX-043) is a `core.tables` table like every list
  (labelled filters, sort links, "Gruppieren nach", CSV) and the first tab
  of Mein Bereich with `aria-current="page"`.
- **"Kunde fehlt"** (PRJ-090) is a text badge with a text link "Kunden
  wählen"; the required customer field is marked like every required
  field.
- **Mailbox settings** (EML-049): "übernehmen ab" is a labelled
  date-and-time field with the picker of UIX-036, "nur ungelesene Mails" a
  labelled tick box; the line in the list states both as text.
- **Maps** (UIX-034): nothing changed for users – the tile requests only
  gained a Referer.
- Browser tests with axe-core:
  `tests/browser/test_082_{security,sync,cleanup,project,mail_maps}_in_browser.py`
  (wide and at 375 px). Not tried: a real screen reader; Firefox and
  Safari (Chromium only); a real phone.

## Two languages and further measures

- **Two languages** (UIX-029): `<html lang>` is `de` or `en-GB` for the
  language of the request, so screen readers pronounce the page in the
  right language; responses carry `Content-Language`. The note on the
  manual page that the English manual is missing is `role="note"` with
  `lang="en-GB"` around German content. Texts that JavaScript writes
  ("Copied", date chips, the timeline) come from `data-text-*` attributes
  and follow the language. The date picker names days in words with the
  date in the language's format ("Wed, 10/03/2027"), not by position.
  Number fields accept the format they show.
- **The manual** (`/manual/`): the table of contents is a `<nav>` with
  `aria-label` "Contents of the manual" ("Inhalt des Handbuchs") holding
  an open `<details>` that can be folded; headings keep their levels and
  anchors;
  the sanitised Markdown keeps tables with header cells.
- **Server address** (ADM-016): every block is a `<section>` with
  `aria-labelledby`; the command is a `<code>` block with a text button
  "Copy" (`aria-describedby` to the command) and a `role="status"` line
  for "Copied"; results ("Applied on …", the failure) are `role="status"`
  notes and badges with words, not colours only; the check results say
  "error:", "warning:", "note:" in text. The certificate choice is a
  labelled radio group (`core/_field.html`).
- **AI** (EML-040, ADM-017): the "Overview" block and the settings page
  use `aria-labelledby` sections; a running summary is a `progressbar`
  with `aria-valuenow` inside an `aria-live="polite"` region, so progress
  and the finished summary are announced; the polling elements target
  themselves (`hx-target="this"`). "made by AI" and "out of date" are
  text, the cloud warning is text ("cloud – data leaves the company"),
  not a colour alone. The draft box is `aria-live="polite"`; "Take it over
  into the text" names the body field it fills (`aria-controls`).
- **Service case statuses** (PRJ-112): the status select opens the
  existing follow-up dialog (focus moves into it, Escape and "Cancel"
  close it and put the select back to the saved status, so the visible
  state never lies); without script the dialog is a page of its own. The
  dialog explains each status in a sentence; required day and time are
  marked like every required field. The three new badges carry their name
  ("wartet auf Rückmeldung", "Rückstand"), their colours are only a second
  cue. The filters "auch Rückstand"/"Auch Rückstand" are labelled tick
  boxes.
- **Grouping** (UIX-044): "Gruppieren nach" stays a labelled select; when
  a list is too long to group by a computed column, the reason is the
  `role="status"` message above the table (`sort_notice`), as for sorting.
- Browser tests with axe-core:
  `tests/browser/test_083_{address,i18n,ai,cases,tables}_in_browser.py`
  (wide and at 375 px; the address tests at 1360 px too, the cases tests
  in both themes). Not tried: a real screen reader; Firefox and Safari
  (Chromium only); a real phone.

## Menu as a drawer and further measures

- **The menu as a drawer** (UIX-045, up to 900 px): the menu button has
  `aria-controls="sidebar"` and `aria-expanded`, set to "true" while the
  drawer is open; the drawer's head has a close button with the label
  "Close menu" ("Menü schließen"). While open, everything outside the
  drawer is `inert`, so neither Tab nor a screen reader's virtual cursor
  leaves it; Tab wraps round inside; focus moves to the close button and
  back to the button that opened it. Escape, the close button, a tap on
  the backdrop and the browser's Back close it (a history entry, so Back
  never leaves the page by surprise). With `prefers-reduced-motion` it
  appears without sliding. The swipe is an addition – every way to open
  and close it also works with keys or a single tap. Above 900 px nothing
  changes; growing past it closes an open drawer and restores the layout.
- **Hour lines** (VFG-033): purely visual (background gradients and an
  `::after` layer without content); the hour labels stay text above them.
- **Service case tab and summary box** (PRJ-090, EML-050): the first tab is
  "Overview" ("Überblick", `aria-current="page"` as before); the
  correspondence box is a section labelled "Summary"; the AI part has a
  visually hidden heading "Summary by AI" next to the visible badge "made
  by AI", so the visible word is not read twice; the short overview is a
  `<details>` closed on load that keeps the reader's choice while the
  block refreshes. The estimate before "Summarise" is text, the long one a
  `note`; the progress text ("writes … 120 words") sits in the existing
  `aria-live="polite"` region.
- **Einstellungen → Benachrichtigungen** (VFG-036): fields through
  `core/_field.html`; the weekday field is shown only for "Once a week"
  (`data-show-if`, hidden otherwise, so it is not read); last and next
  check are a `<dl>` with words, not icons.
- **Packing with Crew** (PCK-013): where someone may not add material the
  field is replaced by a plain sentence saying who may, not a disabled
  control without explanation.
- **Settings → AI** (EML-040, ADM-017): processor, speed and the
  recommendation are text in a `note`; the recommended command is a
  `<code class="command copy">` like the install command.
- Browser tests with axe-core:
  `tests/browser/test_084_{ui,fixes,shortages,ai}_in_browser.py` (the
  drawer at phone width with emulated touch, in both themes; the hour
  lines measured at 1236–1920 px). Not tried: a real phone, iOS Safari,
  Firefox, a real screen reader.

## Scan dialog and further measures

- **The scan dialog** (`static/js/scan.js`, `templates/material/_scan.html`,
  MAT-027, UIX-006): a native `<dialog>` with `aria-labelledby` on its title,
  closed by Escape and by a close button with the label "Close";
  the focus moves into the dialog – to the **field for typing the code**, which
  is always there and is the way for keyboard, switch and screen reader users
  and for hand scanners – and back to the button that opened it. The camera is
  an addition, never the only way: the status line is an `aria-live="polite"`
  region that says "Hold the code in front of the camera", "The camera needs
  a secure connection …" or "This browser cannot read codes …" in words; the
  video is `aria-hidden` (it has no meaning for a screen reader); the torch
  button is a toggle with `aria-pressed`. The camera stops when the dialog
  closes, the page is left or the tab is hidden.
- **Packing by scan** (PCK-010, PCK-011): the server announces what a scan
  did ("4 von 6", or the reason for a refusal) in a trigger of the answer; the
  dialog says it in its `aria-live` status line, and with a short vibration
  where the phone has one, because the packing list below the dialog cannot be
  seen. The colour (green, yellow, red) is never the only cue – every message
  is a sentence.
- **The planning follows the stock** (UIX-056): the availability column,
  the wish hints and the hints above the lines are replaced in place; the swap
  keeps typed text, the scroll position and dialogs, and the planning block
  keeps the open or closed state of every `<details>` when a group is saved.
  Saving a group does not throw the page to the
  bottom (scroll anchoring in `app.js`).
- **The manual in chapters** (UIX-057): `/manual/` has a search form with
  `role="search"` and a label; the chapter page has a `nav` "Chapters of the
  manual" with `aria-current="page"` on the chapter shown, and a `nav`
  "Previous and next chapter"; the arrows are `aria-hidden`.
- **Pages built from the usual parts** (`core/_field.html`, labelled
  tables, `role="status"` messages): the register of incoming invoices and its
  booking page (the reading status is an `aria-live="polite"` region while it
  polls), the asset card, the asset register, the sale from stock, the LDAP
  settings and "Anmeldung testen", the price-offer dialogs, the import of old
  projects and the settings of the automatic summaries. The crawl of the "required" marks
  (`RequiredMarksTests` in `tests/unit/test_092_ui.py`) reaches these forms
  through the menu and the tabs of Buchhaltung.
- **Phone width:** the API token table of "Mein Konto" turns into cards at
  360 px; the tables are wrapped like the others.
- Browser tests with axe-core:
  `tests/browser/test_100_{incoming,depreciation,stock,ldap,price_offers,legacy_import,manual,products_planning,account}_in_browser.py`
  (at 1360 and 390 or 360 px). Not tried: a real screen reader, a real phone
  camera, Firefox and Safari (where the camera dialog shows the typing field
  only).

## When adding a page

- Render fields with `core/_field.html`, which writes label, help text and
  error in the right relation.
- Give an icon-only button an `aria-label`.
- Use `aria-current="page"` for the tab or navigation entry that is shown.
- Run `tests/ui/test_accessibility.py` after adding the page to its list.
