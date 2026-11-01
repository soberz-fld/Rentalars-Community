# Core flows

What happens inside the calculations that matter most, in words and with
numbers. Each section names the module to read next; the module's own
description goes into more detail.

1. [Availability](#1-availability) – what is free when? Also for material taken over between subprojects
2. [Price calculation](#2-price-calculation) – what does it cost? Also with nested groups and for a whole project; services and Nebenkosten
3. [Adding a line](#3-adding-a-line-to-a-project) – the two together, step by step; several lines at once, subrentals, alternatives, lighting plots, customer material; services only with the crew, the page per supplier
4. [Packing, issue and return](#4-packing-issue-and-return) – several packlists, issue per article, chosen items; the whole project and handovers; partial return, the bar, the app's offline packlists and sync; versions, change IDs, the clock rule, packlists on confirmation; packing with the role Crew, who may add material, reason codes
5. [Import](#5-import-of-lists) – material, products, customers, people; in the background; custom fields and storage paths in the material import, the export in the import format
6. [Crew: price, cost and warnings](#6-crew-price-cost-and-warnings) – rates, hours, per day, crew per phase, a new phase from the crew planning; requests after new times; the service product of a function, hour tiers per day, billing by effort; staffing a phase by job function and places, accepting marks "available"
7. [A time entry from recording to the project](#7-a-time-entry-from-recording-to-the-project) – service cases in the choices, a period in several job functions, pay and the clipboard; a job function choice that is never empty
8. [Assigning e-mails to projects](#8-assigning-e-mails-to-projects) – several mailboxes, inquiries, answers to deployment requests by mail, the footer of system mails; deleting a mailbox, mails of a supplier; further addresses (aliases), inquiries as projects, no mail server; untagged mails only from a point in time; messages with a lock
9. [Encrypting and moving the database](#9-encrypting-and-moving-the-database)
10. [Making an invoice](#10-making-an-invoice) – and the other documents; offers of groups only; a whole project with its parts
11. [Calendars of the people](#11-calendars-of-the-people) – busy times in, deployments out; the calendar links of products, models and items
12. [Webhooks](#12-webhooks) – recording, delivery, retries, switching off
13. [Handing invoices to the accounting](#13-handing-invoices-to-the-accounting) – Lexware Office and DATEV
14. [Timeline and personnel plan](#14-timeline-and-personnel-plan) – tabs and defaults, days or weeks (also the utilization), colours of deployments, bars at their real times, phases outside the rental period; framed bars, the timeline of one project, everybody in the personnel plan; hover times, conflicts filled red, dragging deployments, hourly lines, marking in the week, Planung → Wiedervorlagen; the project timeline like the personnel plan, changing the crew of a phase; phases and follow-ups in the calendar
15. [The head of a project and the tab "Dokumente"](#15-the-head-of-a-project-and-the-tab-dokumente) – actions, next document, documents and files; the tabs, the follow-up
16. [Project numbers](#16-project-numbers) – former numbers that keep working
17. [Filters, menu and the pages without login](#17-filters-menu-and-the-pages-without-login) – filters that fold away, the company name, the credit; impossible days in the address; grouping a table, no "Zurück" from the navigation; filters always folded, every column sorts, Meine Einsätze; entries per page per user and list
18. [Dates, periods and required fields](#18-dates-periods-and-required-fields) – the picker with clock face, hatched periods, a phase beyond the rental period, required fields
19. [New material: models, items, a product from a model](#19-new-material-models-items-a-product-from-a-model) – suggestions, the power, start ID and serial numbers, the default storage location
20. [Data steps: storage, material and mailboxes](#20-data-steps-storage-material-and-mailboxes) – what each migration does to existing data
21. [Subprojects afterwards, service cases, show files](#21-subprojects-afterwards-service-cases-show-files) – dividing a project, a case from an inquiry, the upload check; the customer required
22. [The chat of a project](#22-the-chat-of-a-project) – readers, mentions, unread through the change polling; read marks and change stamps; photos and videos made smaller on the server
23. [Automations](#23-automations) – events, runs after the commit, answers that cannot loop; the rules that came with Rentalars, "changed" and restoring them
24. [Route links, maps and trips](#24-route-links-maps-and-trips) – geocoding once per address, the lock, the content security policy, the trips of a project; routes from the current location, tiles with referrer, adjusted trips
25. [Surcharges for night, Sunday and holidays](#25-surcharges-for-night-sunday-and-holidays) – holidays, § 3b EStG, hours by plan and by effort, with hour tiers; rules, own holidays, the § 3b button
26. [Hints at times and expenses](#26-hints-at-times-and-expenses) – the working day, receipts, approval, costs; the hints switch, the way to work
27. [Moving appointments in the timeline; invoices switched off](#27-moving-appointments-in-the-timeline-invoices-switched-off) – the rolled-back preview; people dragged on Zeitplanung and what follows them
28. [The Raspberry Pi in the server scripts](#28-the-raspberry-pi-in-the-server-scripts) – detection and sizing in `deploy/lib.sh`
29. [Data steps: showfiles, maps and times](#29-data-steps-showfiles-maps-and-times) – what each migration does to existing data
30. [Data steps: surcharge rules, hints and aliases](#30-data-steps-surcharge-rules-hints-and-aliases) – what each migration does to existing data
31. [Data steps: packlist sync, mail cutoff and chat](#31-data-steps-packlist-sync-mail-cutoff-and-chat) – what each migration does to existing data
32. [Service case statuses with a follow-up](#32-service-case-statuses-with-a-follow-up) – waiting, waiting to close, backlog, the case triggers and action, the default rules
33. [Changing the server address](#33-changing-the-server-address) – prepared in the browser, applied by root
34. [Summarising the correspondence](#34-summarising-the-correspondence) – the short overview, the summary job, the local AI and interfaces; streaming, speeds, model choice, `ai refresh`
35. [Data steps: service-case rules and AI](#35-data-steps-service-case-rules-and-ai) – what each migration does to existing data
36. [The younger change wins: projects and own data from the app](#36-the-younger-change-wins-projects-and-own-data-from-the-app) – change times per field, the clock rule, 409, own data
37. [Shortage notifications on a schedule](#37-shortage-notifications-on-a-schedule) – the company setting, the minute timer, claiming a moment; known shortages as one reminder per project
38. [Data steps: accounts, labels and shortage notices](#38-data-steps-accounts-labels-and-shortage-notices) – what each migration does to existing data; the refresh timer
39. [Audits, to-dos and custom fields](#39-audits-to-dos-and-custom-fields) – due dates without a flood, the audit mode, values per item and their checks; the master data in the audit mode and the open points total
40. [Electrical inspections (DGUV V3)](#40-electrical-inspections-dguv-v3) – limits as data, the R_PE length rule, the suggestion, the live check, the test report
41. [Entering a purchase: amounts, totals and sums](#41-entering-a-purchase-amounts-totals-and-sums) – amounts as printed, the style of an invoice, totals, category and product, the sums
42. [Booking in an incoming invoice, with cost allocation](#42-booking-in-an-incoming-invoice-with-cost-allocation) – upload and reading, the correction, the split of ancillary costs to the cent, the plan and the booking
43. [Scanning a code](#43-scanning-a-code) – one resolver for page and API, packing and taking back by scan
44. [Login with a company directory (LDAP), and the role sync](#44-login-with-a-company-directory-ldap-and-the-role-sync) – the second backend, the plan, protection of the last administrator, the comparison
45. [The night's automatic AI summaries](#45-the-nights-automatic-ai-summaries) – the lock, the hash of the input, the brakes
46. [Importing old projects from their invoices](#46-importing-old-projects-from-their-invoices) – reading, preview, confirmation, quiet mode, undo
47. [Selling an item from the stock](#47-selling-an-item-from-the-stock) – the book value, the preview, the sale and its storno
48. [Negotiating a price offer for a deployment](#48-negotiating-a-price-offer-for-a-deployment) – offer, counter-offer, acceptance on one crew line

The migrations are squashed into one per module
(`<module>/migrations/0001_squashed_…`, two for `projects`); a database too old to update
is refused (`rentalars/core/checks.py`, `deploy/lib.sh` `OLDEST_UPDATABLE_VERSION`). The sections about data steps below
describe what updates of existing databases do to existing data. The squashed migrations keep only the data steps a new database needs
(number ranges, document templates and kinds, the rows of the mail, notification and label
settings, the default automations).

---

## 1. Availability

*Code: `rentalars/availability/engine.py`, `stock.py`. Catalogue: chapter 7.4,
VFG-001 to VFG-018, PRJ-047, PRJ-060. Tests:
`tests/unit/test_availability.py`, `tests/unit/test_060_subprojects.py`,
acceptance scenarios 2, 13, 14.*

### The rule (VFG-002)

```
free(product, period) = plannable stock
                      − highest quantity reserved at the same time within the period
```

The *highest quantity at the same time*, not the sum: two projects that use
the same six cables one after the other need six cables, not twelve.

**Example (acceptance scenario 2).** The stock of XLR cables is 9.

```
                 10.   11.   12.   13.
 P1  6 cables    ████████████
 P2  ? cables          ████████████
```

P1 is confirmed and has 6 cables from the 10th to the 12th. P2 asks for the
11th to the 13th. The busiest moment in P2's period has 6 cables out, so
3 are free. If P2 books 4, it is short of 1 – and the line is saved all the
same, marked red, until someone reduces it, moves it or subrents the missing
cable (PRJ-013).

`peak_quantity()` finds the busiest moment: every reservation becomes two
events, "+6 at the 10th, 08:00" and "−6 at the 12th, 18:00"; the events are
walked through in time order while a running total is kept. Times count, not
only dates (VFG-004): what comes back at 10:00 can go out again at 10:00.

### What the stock is (PRD-006, MAT-021, MAT-036)

A product has no stock field. `stock.py` counts material items:

| Figure | Counts |
|---|---|
| `total` | everything that is not retired, sold or lost |
| `operational` | of those: status available or in use |
| `plannable` | of those: not permanently installed in another item |

**Example (acceptance scenario 13).** Product T-050 "wireless receiver" has
the items 0310, 0311 and 0312. 0310 is screwed into rack 0500. Then total 3,
operational 3, plannable 2: the receiver in the rack only ever travels with
the rack.

### What reserves (PRJ-008, VFG-003)

| Line of a project that is … | reserves |
|---|---|
| confirmed or out | **firmly** |
| an option | **softly**: shown separately, takes nothing away |
| an inquiry, or finished | nothing |
| in an optional or alternative group | softly, whatever the project's status (PRJ-040) |
| an optional or alternative line | softly, like an option; it takes no stock from the lines that count (PRJ-075) |
| in a subgroup of an optional or alternative group | softly, as its group above (PRJ-037) |
| of a subproject | like a line of a project of its own: with the part's status and its own period (PRJ-047) |

The traffic light of a line follows from that: **free** – enough; **tight**
– enough, but an option of another project would collide if it became an
order; **short** – not enough.

A project is always judged *as if it were confirmed*: an inquiry for 12
cables with 9 in stock shows a shortage of 3, although the inquiry itself
reserves nothing. Otherwise the shortage would only appear at the moment of
confirming – too late.

### What else goes into a reservation

- **Buffer times** before and after (VFG-005): set for the whole system,
  overridden by a category, overridden by a product. The reservation is
  simply longer.
- **Kits** reserve their components (VFG-008). `flatten()` breaks a kit –
  also a kit of kits – down to real products. Five speaker sets of two
  speakers and one cable reserve ten speakers and five cables. A kit is as
  available as its scarcest component (acceptance scenario 14).
- **Containers** reserve their loose contents (VFG-016): whoever plans the
  cable case also occupies the twenty cables in it. If several cases of the
  same product hold different contents and none is chosen yet, the most
  extensive content is assumed (VFG-017).
- **Subrentals** take load off the own stock (VFG-018): a line of 4 cables,
  1 of them covered by a subrental, occupies 3.
- **Sales** occupy stock from their start without end, until the pieces
  have actually been booked out (PRD-013).
- **Overdue projects**: a project that is still "out" after its planned end
  keeps its material occupied up to this very moment.
- **Issued material** (PCK-025): a project whose material is
  partly issued keeps its status – "confirmed", or even an option – until
  everything is out (section 4). Its lines count as "out" all the same:
  firm, and still occupied when overdue. `_planned_from_database` and
  `projects_that_may_be_short` annotate the lines with
  `packing.models.material_out("project_id")` in the query they run anyway,
  so it costs no query. It counts only pieces out by the
  books: issued, neither taken back nor handed over, not sold.
- **Pieces taken back early** (PCK-028) are free again from
  the moment of their booking: of a line's demand, the taken-back pieces
  become a demand of their own that ends at `taken_back_at` (or the line's
  end, if earlier), the rest keeps the line's period. A packlist row taken
  back on the 11th at 18:00 of a line until the 13th frees its pieces for
  others from the 11th at 18:00. `_planned_from_database` reads
  `taken_back`, `taken_back_at` and `kit_taken_back` with the query it runs
  anyway (`packing.models.taken_back_of`); the components of kits taken
  back early cost one more query, only when there are any. Sold pieces
  never come back.
- **Blocked periods** of items (MAT-024): "in repair until
  15 November" is a firm demand of one piece of the item's product for that
  period, listed among the reservations with the item's ID and the reason.
  Only items that count towards the plannable stock are taken; blocking a
  defective item, or one screwed into a rack, does not take a second piece
  away.
- **Contents taken out** for a project (MAT-042): if a loose
  receiver is taken out of its rack for project P, the rack's reservation
  in P no longer occupies that receiver – it is free for others during P.
  The extraction counts for every container around the item, so a
  receiver taken out of a drawer is missing from the drawer and from the
  rack the drawer sits in.
- **Material taken over from another subproject** (PRJ-060):
  one reservation from the first stage straight to the next, without
  buffers in between – next section.
- **Customer material** (PRJ-096) is counted exactly like own
  material: its items are the stock, a defective item or a second gig of
  the same customer at the same time makes it short. Nothing in the engine
  knows the owner. Only the way out differs: a shortage gets no subrental
  suggestion (section 3, "Customer material in a project").

### Material taken over between subprojects (PRJ-060)

The same six spotlights serve the stage "Marktplatz" of a festival first
and then the stage "Schlosspark". The later part plans them as a
take-over: its line names the earlier line (`taken_over_from`). The
engine then counts the pieces as one reservation that goes from one
stage straight to the next – they never pass through the warehouse.

**Example.** Buffer times of 4 hours before and after; 10 spotlights in
stock. Line S of "Marktplatz" has 6 from the 10th, 08:00 to the 12th,
18:00; line T of "Schlosspark" has 6 from the 13th, 08:00 to the 15th,
18:00.

| | T planned on its own | T takes over from S |
|---|---|---|
| S occupies | 10th 04:00 – 12th 22:00 | 10th 04:00 – 12th 18:00: no buffer after, the pieces go on |
| T occupies | 13th 04:00 – 15th 22:00 | 12th 18:00 – 15th 22:00: from the end of S, no buffer before |
| the night in between | free for other projects | occupied – the pieces are on a truck |

The peak is 6 either way. Planned on its own, T would leave the six free
for another project in the night between the stages; taken over, they
stay with the production. If T began on the 12th at 12:00, before S
ends, its pieces would be occupied from 12:00 (`min(end of the source,
own start)`), and between 12:00 and 18:00 both lines count: 12 at the
peak, a shortage of 2. That is intended – the same pieces cannot stand on
two stages at once.

**Segments.** A line can receive and hand on at the same time. T with 8
pieces takes over 6 from S and hands 4 on to a later line U; `_segments`
cuts it into 4 pieces received and handed on (from the end of S to the
end of T, no buffer at all), 2 pieces only received (from the end of S to
the end of T plus the buffer after) and 2 pieces of its own (its period
with both buffers); a line that hands on more than it receives also has
pieces "only handed on". Each segment is a demand of its own, and their
verdicts are merged into one detail per product (`_merge_detail`), so the
planning shows one traffic light per line.

**Only lines that reserve are linked** (`_link_takeovers`). Whether S
hands pieces on is known only from the lines loaded: those of the judged
project and those of other projects that reserve in the window. A taking
line of an inquiry is not loaded, and S keeps its buffer after – rightly,
because the inquiry reserves nothing. The query of the other lines also
loads lines whose source ends inside the window; `_attach_sources` reads
end and quantity of the sources with one query, and only when a line
takes over at all. The generous first test of
`projects_that_may_be_short` (below) counts take-overs on the safe side.

### Shortages between subprojects (PRJ-047)

Parts reserve like projects of their own, so two stages of one festival
can be short of each other's material. A demand knows its whole project
(`root_project_id`), and the verdict for a line carries `family`: what
the other parts of the same whole project hold firmly at the busiest
moment of the line (`ProductShortage.family`). The tab "Teilprojekte"
lists the lines that are short while `family` is above zero
(`projects/family.py`); the page "Fehlbestände" says "davon belegt durch
andere Teilprojekte: N", the smaller of `family` and the missing count
(`OpenShortage.held_by_other_parts`).

### Nothing is stored

There is no table of reservations. Every answer is calculated from the
lines as they are now, so it cannot be out of step with them. The price is
computing time, and the engine is built for that: one `AvailabilityEngine`
object answers for a whole project with a fixed number of queries, whether
the project has 5 lines or 500.

### Three questions, three entry points

| Question | Method |
|---|---|
| How much of these products is free in this period? | `availability(product_ids, start, end)` – the product page, the API |
| How does every line of this project stand? | `project_availability(project, lines)` – the planning page |
| How does this one line stand? | `line_availability(line)` – after adding or changing a line; loads only the lines that compete for the same stock |

The third gives the same answer as the second for that line; a test compares
them for every line of the sample data.

### All shortages at once (PRJ-057)

The page "Fehlbestände" lists every open shortage of every running and
coming project. Judging a thousand projects exactly would take thousands of
queries. `projects_that_may_be_short()` asks a cheaper question first, for
all projects at once: *can* this project be short of anything? It compares,
per product, the stock with everything that could possibly be out at the
same time. Only the projects that fail this generous test are then judged
exactly. The test errs on the safe side, so no shortage is lost; with a
thousand projects and no shortage the page needs about two dozen queries.

**Open items** (PRJ-098): the page "Offene Punkte"
(`course_views.open_items_overview`) runs the same calculation once,
`open_shortages(projects=readable_projects(...))`, and adds each shortage
not resolved yet as a further bullet of its project ("Fehlbestand: 4 ×
LED-Scheinwerfer (2 zugemietet, 2 offen)"), linking to the project's
planning at `#line-<pk>`, where the row is highlighted. Projects that only
have shortages are fetched with one extra query and sorted in; the open
items are prefetched, which removed a query per row. Only projects whose
planning the user may read are listed. The API `/open-items` does not
include shortages yet.

### Two people, one last cable (VFG-007)

Two users add the last free cable to two projects at the same moment. Each
check, taken alone, would say "free". `projects/services.py` therefore locks
the rows of the affected products (`SELECT … FOR UPDATE`) before it saves a
line and calculates its availability: the second user waits a few
milliseconds and then sees the first booking. Products are always locked in
ascending order, so two requests cannot wait for each other in a circle.
`tests/unit/test_concurrency.py` does exactly this from two connections (on
MariaDB; SQLite cannot).

---

## 2. Price calculation

*Code: `rentalars/projects/pricing.py`; for a whole project
`projects/family_prices.py`. Catalogue: PRD-033 ff., PRJ-033 ff., PRJ-037, PRJ-046, PRJ-060. Tests: `tests/unit/test_pricing.py`,
`tests/unit/test_060_groups.py`, `tests/unit/test_060_documents_parts.py`,
acceptance scenarios 9, 16, 17.*

Nothing calculated is stored. Every amount, subtotal and total is derived
from the lines when it is needed.

### Step 1: the amount of a line (PRD-033)

| Billing mode | Amount |
|---|---|
| daily rental per piece | quantity × daily price × factor of the rental days |
| daily rental per kit | the same, the quantity being the number of kits |
| flat | quantity × price |
| by the hour | quantity × hours × price |
| by effort | quantity × price; the quantity is an estimate until the real effort is known |
| sale | quantity × sale price |

Then the line's own discount is deducted. A crew line has a
discount of its own too, and a job function may cap the discount of its
lines – crew lines, and material lines whose product is the job function's
service product (PER-026, `projects/discounts.py`): the line's own discount
plus its share of the group's discount, amount or flat price stays within
`max_discount_percent`. What a line may not take is not passed on to the
others; the group's discount shrinks, or its flat price rises. A product can carry the same cap (`Product.max_discount_percent`,
PRD-041): it limits the line's own discount, the customer's standard
discount and the line's share of the group's discount; where product and
job function both have one, the stricter counts, and the planning says
"(Produkt)" or "(Funktion)". It is read in `_price_single_line` from the
product that comes with the line – no extra query –, so duplicates and
templates follow it. Crew lines stay limited by their job function only.

**Services and Nebenkosten** (PRD-044, PRD-045). A service
is priced on its crew lines (section 6); a new material line of a service
is refused (section 3). Material lines of services planned earlier
stay and are priced as before – the maximum discount of their job
function included (`maximum_discounts_of_products` asks only when such a
line exists) – and carry the hint "Dienstleistung – unter Personal
planen". Nebenkosten (`incidental`) – transport, travel costs, fees – are
priced like any material line, by default flat: quantity × price.

**A line taken over from another subproject costs nothing** (PRJ-060,
): its amount is 0 and it is marked (`LinePrice.is_takeover`),
like a subrental that only covers a shortage. The pieces are charged
once, on the line they come from, which is priced as usual.

**Customer material costs nothing either** (PRJ-096): the
line's amount is 0 and it is marked (`LinePrice.is_customer_material`) –
`_price_single_line` returns before rental days, scale or discount are
looked at. It counts as a normal line, not as optional, but it is left out
of the group's sum (`own_lines_total`), of the shares of a group's
discount or flat price and of the split by tax rate; so it is part of no
sum, also not of "Material-Einnahme". The planning and the price overview
(page, PDF, CSV) show the badge and "nicht berechnet" instead of the price
columns; the API marks the line with `is_customer_material`. `add_line`
does not apply the customer's standard discount to it.

**Rental days and factor.** The most specific entry wins
(`resolve_rental_days_with_source`, PRJ-005, PRJ-062):

1. rental days typed in on the line;
2. the line's own period, if it differs from the project's – every started
   24 hours count as one day. Moving a line to other dates therefore changes
   its price without anyone having to remember the rental days;
3. rental days typed in on the group;
4. the rental days of the project.

The planning shows the number together with where it comes from, and days
and factor apart ("2 days", below it "factor 1.5") – never as "2 × 1.5",
which reads like a factor of three (PRJ-063).

The factor comes from the product's rental scale. The default scale
"Standardstaffel" of a new installation (ADM-011):

| Rental days | 1 | 2 | 3 | 4 | 5 | 6 | 7 | … |
|---|---|---|---|---|---|---|---|---|
| Factor | 1.0 | 1.5 | 1.75 | 2.0 | 2.4 | 2.75 | 3.5 | +0.3 per further day |

**Example (acceptance scenario 17).** 4 spotlights at 20.00 per day, 2
rental days: 4 × 20.00 × 1.5 = **120.00**.

A line remembers the *version* of the scale it was priced with (PRD-037).
When the table is edited later, existing lines keep their factor; the
planning page offers to switch them to the current table.

The same holds for the price itself (PRJ-010, PRJ-072): a line keeps the
price it took over, and remembers it as `list_price`. When the product's
price changes, the planning of an inquiry or an option says "3 lines have
an old price" and takes over the new ones on request – all lines whose
price was not set by hand (`unit_price` equal to `list_price`) at once,
those set by hand one by one (`projects/price_updates.py`). A confirmed
project keeps its prices.

### Step 2: groups (PRJ-039)

The amounts of a group's lines add up. Then either the group's discount (in
per cent or as an amount) is deducted, or a flat price replaces the sum.
Optional and alternative lines (PRJ-075) show their amount
but are left out of the sum and the discount – and of the totals, the
taxes, the invoice and the packlist.

**Nested groups** (PRJ-037) are summed from the bottom up. A
group's sum is its own lines plus the subtotals of its subgroups; then
its own discount or flat price applies – the subgroup's rule first, the
parent's on the result. A flat price of a parent replaces everything in
it. A subgroup that is optional or alternative itself is not part of its
parent's sum; a subgroup of an optional or alternative group counts as
such too, and is left out with it.

```
Group "Licht"           lighting desk                    450.00
  "Front truss"         3 lines                420.00
  "Rear truss"          2 lines      310.00
                        10 % discount −31.00   279.00
                                               ──────
                        subgroups together               699.00
                        together                        1149.00
                        5 % discount                    −57.45
Subtotal "Licht" with subgroups                         1091.55
```

The parent's reduction is spread over every line below it, in proportion
to what each line contributes at that point: the desk carries 22.50 of
the 57.45, the rear truss 13.95. That keeps a maximum discount of a job
function (PER-026) valid however many groups above a line give a
discount, and the net per tax rate exact (step 5). Rental days a subgroup
does not have come from the nearest group above (`effective_rental_days`).

### Step 3: percentage surcharges (PRD-039)

A percentage surcharge names what it refers to: single lines, groups, or the
whole project. Its amount is that percentage of the referred amounts *after*
discounts and *before* any other surcharge – surcharges are never charged
on surcharges.

### Step 4: the project total (PRJ-034)

Subtotals of the groups that count, lines without group, the crew
(section 6), project-wide surcharges. Optional and alternative groups are
shown with their subtotal but are not added (PRJ-040). The crew is priced
before the surcharges, so that a surcharge "on the whole project" includes
it.

### Step 5: tax (PRJ-024)

The net total is split by tax rate; tax is calculated per rate and added.

### All five steps in one example (acceptance scenarios 9 and 17)

```
Group "Front truss"     3 lines                        420.00
Group "Rear truss"      2 lines        310.00
                        10 % discount  −31.00          279.00
Without group           1 line                          50.00
Surcharge 10 % on both groups   (420.00 + 279.00) × 10 %  69.90
                                                       ──────
Net total                                              818.90
Tax 19 %                                               155.59
Gross total                                            974.49
```

### The sums of a whole project (PRJ-046)

A whole project with subprojects is priced project by project: every part
keeps its own calculation – groups, discounts, flat prices, percentage
surcharges, crew –, exactly as on its own planning page, and a surcharge
"on the whole project" set on the whole project refers to the whole
project's own lines. `family_prices()` puts the plannings side by side –
the whole project's own lines first, then every part that is not
cancelled, in the order of their numbers – and `sum_prices()` adds them:

1. the net amounts of all projects, **per tax rate**;
2. the tax, calculated once per rate on that sum (EN 16931 BR-CO-17);
3. gross = net + tax.

```
Shared lines of the whole project 2026-0042     net 1,200.00 (19 %)
Subproject 2026-0042-1 Bühne Marktplatz          net 3,334.40 (19 %)
Subproject 2026-0042-2 Bühne Schlosspark         net 2,101.50 (19 %)
                                                 ────────
Net total                                            6,635.90
Tax 19 % on 6,635.90                                 1,260.82
Gross total                                          7,896.72
```

Adding up the three gross totals one by one would give 7,896.73: the tax
of each is rounded on its own (633.54 and 399.29 instead of 633.536 and
399.285). The price overview and the documents use the sum
above; the sum row of the tab "Teilprojekte" adds the parts' figures and
may differ by a cent. For a project without parts, `sum_prices` gives
exactly its own figures. The price overview leaves out the parts the
viewer may not read and says how many (PRJ-049); a document always holds
every part that is not cancelled (section 10).

### Who sees it (AUT-019)

The calculation always runs. Whether its result is shown is decided at the
edge, from the special right "see prices": templates leave out the price
columns, the API leaves out the price fields. Purchase prices need a second
right on top, personnel costs a third; the profit of the project – net
total minus subrental cost minus personnel cost, "Gewinn aus dem Projekt"
(PRJ-087; the field is `contribution_margin`) – shows only to those who have all three. (The profit subtracts the approved expenses as well,
`ProjectPrices.expenses_cost`, section 26; the personnel cost includes the
surcharges of lines that have them, section 25.)

### Sums in the project list (PRJ-085)

The project list offers eight columns of sums – planned man-hours,
material and personnel revenue, net and gross, material and personnel
costs, profit –, off by default and not sortable (they are calculated, not
stored). `projects/list_sums.py` computes them only when one of them is
shown, for the rows of the page or the CSV (`with_sums`, in chunks of
200), from the same price calculation: material revenue is net minus
personnel revenue, material costs are the subrental costs. A whole project
shows its own sums plus those of its parts that are not cancelled and that
the user may read, taxed once per rate as in `sum_prices`; a part shows
its own. The rights are those of the planning page; rows whose planning
the user cannot read stay empty. `compute_project_prices(lookups=…)` with
one `PriceLookups` for all projects of the page keeps the number of
queries fixed, however many projects are listed.

---

## 3. Adding a line to a project

*Code: `projects/services.py` `add_line`, `projects/views.py` `line_add`,
`projects/planning.py`. This is the most frequent action in the program and
the one with a time limit: half a second including the availability check
(NFA-013).*

A user types "K-005" into the field below the group "Ton FOH", picks the
cable, enters 12 and presses Enter.

1. **The browser** posts the small form with htmx: product, quantity, group.
2. **`line_add`** (view) looks up product and group and calls the service.
3. **`add_line`** (service):
   1. Is the project still editable? Closed projects are not (PRJ-009).
   2. May this user set what was sent? Prices need the price right.
   3. Take title, unit, price, billing mode, tax rate and the current
      version of the rental scale from the product – only if
      it may be a material line at all: a service is refused with the
      name of its job function (`check_plannable_as_material`, PRD-044).
      (PRD-047) a product has one price, so the line sells
      exactly when the product is a sale product
      (`defaults_from_product`); `is_sale` for a rental product is
      refused, while lines that sold one before keep their price and may
      be turned back to rent.
   4. In one transaction: lock the product's rows (VFG-007), save the line,
      calculate its availability with `line_availability()`.
   5. Return line and verdict. A shortage does not prevent saving (PRJ-013).
4. **Back in the view**: if the line is short, add a warning message.
5. **`build_patch`** decides which parts of the page can look different
   now: the group of the new line, every group with a line that draws on the
   same stock (the same product, a kit that contains it), the surcharges and
   the totals. It loads all lines and calculates all prices – the totals
   need them – but judges the availability only of the lines in those parts
   and of the lines elsewhere that compete with them.
6. **The answer** is `_planning_patch.html`: those parts, each marked with
   `hx-swap-oob`. htmx puts each in the place of the element with the same
   id and leaves the rest of the page alone. The answer also carries the
   header `HX-Trigger: planningChanged`.
7. **The hints above the planning** ("3 pieces are missing") speak about
   all lines. Their block listens for `planningChanged` and then fetches
   its content from `planning_notes`, which builds the whole planning. The
   user already sees the new line with its traffic light while this second
   request runs. If another change is announced meanwhile, htmx queues one
   more fetch, so the hints end up with the latest state.

Why steps 5 to 7: in a project with 500 lines the whole planning is close
to a megabyte of HTML, and judging the availability of all its lines is the
most expensive part of building it. Doing both for every new line took
0.3 seconds on a small server and, when two users worked at once, sometimes
more than the half second allowed. The patch takes 0.2 seconds; the hints
follow about a quarter of a second later.

The danger of sending parts is a page that shows something outdated.
`tests/ui/test_project_pages.py` (`PlanningPatchTests`) therefore compares,
for every kind of change, the page after patch and hints with the page a
full reload gives: they must be equal, part by part. A second test compares
the verdict of every line shown in a patch with its verdict in the whole
planning. The same service is called
by `POST /api/v1/projects/{id}/material-lines`; the API simply returns the
line with its availability.

Changes to the structure – adding, copying, deleting groups, sorting by
dragging – send the whole planning block again. They are rare.

**Other ways in, the same service**. A project created from
a template (PRJ-076, `project_templates.apply_template`) gets its lines
through `add_line` and its crew places through `add_crew_lines`, so prices
are those of the day, the customer's standard discount applies and every
line is judged as if added by hand; only a group's own price rules and the
price of lines without product come from the template, and only for a user
who may see prices. Periods are wall-clock seconds from the new project's
start, from its end for an entry with `"anchor": "end"` – the
return and follow-up work of the template "Dry Hire" (PRJ-095) – and are
cut to the project's period (`_period`). A lighting plot (PRJ-077, `mvr.take_over`) adds one
line per chosen fixture type with the counted quantity, all in one
transaction. Duplicating a line (PRJ-075, `lines.duplicate_line`) puts the
copy directly below in the same group.

### Several lines at once (PRJ-082)

The planning has a box before every line and one per section ("choose all
of this section"); a bar below offers optional, no longer optional,
alternative, move, discount and delete. `lines.change_lines(project,
line_ids, action, rights=…, …)` – called by `line_views.lines_bulk` and
`POST /api/v1/projects/{id}/material-lines/bulk` (`line_api.BulkLinesView`)
– sends **every line through the single-line service, each in a step of
its own**. A line the action cannot be done with is skipped and named with
the reason (`BulkResult.skipped`, `SkippedLine`); the others are changed,
and each change is in the change log as if made by hand. The rules:

- optional or alternative: not a subrental that only covers a shortage,
  not a line with issued material, not a line other subprojects take over
  from (`services.check_may_become_variant` – the same refusals hold for
  the single line and the API);
- move: needs an explicit target ("Verschieben nach …" or "ohne
  Teilgruppe"); a covering subrental moves only with its line, a
  percentage surcharge stays where its targets are;
- discount: needs the price right; a percentage surcharge, a taken-over
  line and a covering subrental get none (they are not charged).

The answer refreshes only the touched groups, like adding a line (step 5).

### Subrentals as sub-rows (PRJ-084)

"X × … zumieten" at a short line opens a dialog (`views.subrental_accept`,
GET) asking for quantity, status, supplier and – with that right –
purchase price; `services.accept_subrental_suggestion(…, status=…)` makes
the line of the general subrental product that covers the shortage
(`covers_line`). It has no rental price: pricing already charged such a
line 0, the customer pays the covered line. The planning shows it as a
sub-row of the covered line (`PlannedLine.covering`, `is_sub_row`) in that
line's section, wherever the subrental itself stands, and it follows its
line on edit, move by selection and drag (`update_line`, `arrange_lines`).
Its edit dialog offers no group, price, discount, rental days or variant.
A direct POST without the dialog still works as before.

**Supplier and status** (PRJ-101). In both dialogs the
supplier is typed (`SupplierTypeahead`, suggestions from
`projects:supplier_suggest` over name, contact person and address); a
name not known yet offers "„…“ als neuen Lieferanten anlegen", whose form
(`projects:supplier_quick_create`) opens in a second dialog over the line
dialog and, saved, puts the new supplier into the field while the line
dialog keeps what was typed (`app.js`, block PRJ-101; accessibility.md).
The field "Status" starts at "offen" (`SubrentalStatus.OPEN`, also when
the API sends no status); "angefragt", "bestellt", "erhalten" and "zurück"
need a supplier – `MaterialLine.clean` refuses them without one, at the
status field, for page, service and API alike. Copies of a subrental
start "offen" again. The supplier's name in the planning links to the
page "Zumietung bei …" (below).

### Alternatives name what they replace (PRJ-083)

The buttons "optional" (a toggle, `aria-pressed`) and "Alternative" (a
dialog that requires a target) stand on every line and group
(`line_views.lines_alternative`, `group_views.group_kind`,
`group_alternative`). The planning and the price overview write
„Alternative zu „8 × LED-Scheinwerfer““ – they have no stable position
numbers, because a patch sends only the touched groups –; offer and order
confirmation write „Alternative zu Pos. 3“ with the number of the
document, worked out after numbering (`content.name_alternatives`, again
in `only_groups`), or quantity and title where the target is not listed.
Deleting the target makes the alternative optional. Copies – a duplicated
line, a copied group, a duplicated project, a template – name the copy of
the target, or within the same project the same target; copied into
another project without it, the copy becomes optional
(`services.relink_alternatives`, `project_templates._link_alternatives`).

### The MVR file is kept (PRJ-086)

"MVR-Datei importieren" keeps the uploaded file in the files of the
project (`mvr.keep_file`) under `mvr.kept_file_name`:
`yyyymmdd-hhmmss_<original name>` in local time, e.g.
`20261013-221530_Rig Stadtfest.mvr`, without document type and not
visible to the crew. In the browser it is kept when the file is read, and
"Andere Datei wählen" removes it again; through the API with the call that
adds the lines (`mapping`), which answers with `kept_file` – the first
call, which only lists the fixture types, still writes nothing. A file
above the upload limit of project files is not kept; the import goes on
with a warning. `.mvr` is an allowed upload type (`core/uploads.py`), so
it can also be uploaded by hand.

### Customer material in a project (PRJ-096, PRD-043)

A band stores its mixing desk in the warehouse; the provider takes it along
to the band's gigs. It is a product of category C "Fremdmaterial" with the
band as `Product.owner` (data-model, "Products"). In a project of the band
it is planned like any line, with these differences
(`projects/customer_material.py`):

1. **Finding it.** `/products/suggest/` offers customer material only with
   `?project=<key>` naming a project the user may see whose customer is the
   owner (`_owner_for_suggestions`; a part has the customer of its whole
   project), or with `?owner=` for the components of a kit of customer
   material; everywhere else only own material. The search of the planning
   and the addendum of the packlist pass the project; the hint says
   "Kundenmaterial". The MVR import never suggests customer material.
2. **Adding it.** `add_line` skips the customer's standard discount, and
   `MaterialLine.clean` → `clean_line` refuses the line in a project of
   another customer (`may_plan`) and refuses price, discount, sale and
   "optional"/"Alternative"; billing becomes "flat". The forms leave those
   fields out; `check_may_become_variant`, the selection of several lines
   (`lines._rule_against`: "is customer material and is taken along", "is
   not charged") and the API refuse the same.
3. **Pricing** – 0, in no sum (section 2).
4. **Availability** – as own material (section 1). A shortage offers no
   subrental: `accept_subrental_suggestion` refuses ("Customer material
   cannot be subrented …"), so the page, the API and the shortages page
   alike; the planning and "Fehlbestände" say "Kundenmaterial lässt sich
   nicht zumieten.", and `/projects/{id}/shortages` answers
   `suggestion: null`.
5. **The project keeps its customer.** `update_project` refuses another
   customer while the project or its family plans material of the current
   one (`_check_customer_material_stays`).
6. **Copies** go only where the owner is the customer: `copy_group`
   (`_copy_lines`) and duplicating a project (`duplicate._copy_material`)
   skip it, applying a template leaves it out with "Kundenmaterial eines
   anderen Kunden: …" (`project_templates`, `may_plan`).

Documents (section 10) and packlists (section 4) list it with a hint. The
labels of its items say "Eigentum von <Kunde>": on QR labels instead of the
company line, on barcode labels under the name (not on the small ones;
`material/labels.py`).

### Services only with the crew, Nebenkosten like material (PRD-044, PRD-045)

The requirement: service products are only linked 1:1 to functions and cannot be
chosen in planning outside the personnel planning. Every way a
material line can come in asks `services.plannable_as_material(product)`
(the kind is not in `CREW_ONLY_KINDS`):

| Way in | A service is … |
|---|---|
| the search below a group, the addendum of the packlist | not suggested (`exclude_kind=service`; the packlist also leaves out surcharges and Nebenkosten) |
| `add_line` – page and `POST …/material-lines` | refused: "D-003 Tontechniker ist die Dienstleistung der Funktion Tontechniker. Plane sie unter Personal: …" |
| duplicating a line (`lines.duplicate_line`) | refused |
| copying a group, duplicating a project | left out (`_copy_lines`, `duplicate._copy_material`) |
| applying a template | left out with a note ("eine Dienstleistung, die unter Personal geplant wird: …", `project_templates.apply_template`) |
| the lighting-plot import (`mvr`) | never offered, a remembered choice ignored; Nebenkosten are not offered either (`NOT_EQUIPMENT`) |
| a kit | refused as component (`KitComponent.clean`) |

Lines of services planned earlier stay, priced as before, with the hint
"Dienstleistung – unter Personal planen". Nebenkosten (`incidental`) go
every way material goes, with no stock to check (`tracks_stock` is false)
and no packlist row (section 4).

### One page per project and supplier (PRJ-106)

"Zumietung bei <Lieferant>" (`projects:subrental`,
`/projects/<number>/subrentals/<supplier>/`, `subrental_views.subrental_page`)
gathers what one supplier has to do with one project.
`subrentals.build_page` collects:

1. **The lines** – `subrental_lines(project, supplier)`: the project's
   lines of the kind subrental with that supplier, in the order of their
   period, with what each costs at purchase price, the sum of those that
   count, and how many stand at each status. Status and purchase price of
   all of them change in one form (`subrentals.update_lines`, view
   `subrental_lines`, edit access to a project that is not closed);
   purchase prices need their special right. Each line goes through
   `services.update_line`, so `clean()` and the change log apply as for
   one line. The form also has the column "Abholung" ("wird
   beim Lieferanten abgeholt", `picked_up_at_supplier`, PRJ-097; button
   "Status, Abholung und Preise speichern"), and the supplier's address
   carries a route link (section 24).
2. **The documents** – the project's files with this supplier
   (`ProjectFile.supplier`), uploaded with a kind (Angebot,
   Auftragsbestätigung, Lieferschein, Rechnung, Sonstiges) through
   `subrentals.add_document`, which calls `projects.files.add_file` – so
   they are on the tab "Dokumente" too, marked "Zumietung bei …", and
   never visible to the crew.
3. **The correspondence** – with the right to read correspondence,
   `mail.suppliers.mails_with(project, supplier)`: the mails linked to the
   supplier, and those from or to its address that are linked to nobody
   yet (section 8). "Mail schreiben" opens the project's compose form with
   `supplier=<id>`, so the mail is linked when it is sent.

`subrentals.suppliers_of(project)` names every supplier with subrentals,
documents or linked mails of a project. The ways in: the supplier's name on
a subrental line of the planning; the subrentals under Planung →
Fehlbestände, whose supplier names link to the page and which filter by
supplier (`?supplier=`, `availability.views`); and the supplier in the
master data ("Zumietungen bei diesem Lieferanten anzeigen",
`masterdata/admin.py`), which opens that filter. The API:
`GET /projects/{id}/subrentals` (per supplier the number of lines by
status, documents and mails), `GET` and
`PATCH /projects/{id}/subrentals/{supplier}` (`subrental_api`),
documents through the project's files with `supplier` and
`supplier_document_kind`.

---

## 4. Packing, issue and return

*Code: `rentalars/packing/services.py`, `pdf.py`; for subprojects
`subprojects.py`; for the app `offline.py`. Catalogue:
chapter 5.8, MAT-037, MAT-042, PRJ-048, PRJ-060, PCK-026 to PCK-030, AUT-021. Tests: `tests/unit/test_packing.py`,
`tests/unit/test_stage5_packing.py`, `tests/ui/test_packing_stage5_pages.py`,
`tests/api/test_packing_stage5_api.py`, `tests/unit/test_060_packing_parts.py`,
`tests/{unit,ui,api,browser}/test_070_packing*`, acceptance scenarios 7
and 21.*

The guiding rule is PCK-020: **packing works on product and quantity.**
Nobody has to scan anything or pick an individual item. Since 0.5 items
*can* be chosen where it matters (step 5), but nothing depends on it.

### Several packlists per project (PCK-008)

A project starts with one packlist, created when the packing page is first
opened (`get_packlist`). Further ones are added with a title – "Truck 2",
"Licht", "Donnerstag" – and lines are moved to them (`assign_lines`): a
moved line gets a `LineAssignment`; moving it back to the first, the
*main* packlist removes it. Every line without an assignment is on the
main packlist, so a new line of the planning always lands somewhere. Ticks
of a moved line on its old packlist are dropped; a line whose material was
issued on its packlist stays there. The main packlist cannot be deleted,
nor one with issued material; deleting another sends its lines back to the
main packlist.

Each packlist is packed, issued and returned on its own and has its own
status. Several are for projects whose material leaves in batches – two
trucks, sound and light from different halls, a first load days before
the rest; each has its title, loading time, state, PDF, issue and
delivery note.

**The project follows them** (`_project_after_packlists`,
PCK-025):

- **"out" only once everything is out**: material is out and no packlist
  with rows from the warehouse has anything left to issue
  (`_still_to_issue`: a partly issued packlist always waits; one not yet
  issued waits only if it has warehouse rows – an empty further packlist,
  or one that only takes over pieces of another part (PRJ-060), does not).
  Until then the project keeps its status; an "out" project stays "out"
  while a later addition waits.
- **"returned"** once nothing is out, something came back and nothing
  waits – also from "confirmed": a partial issue whose return was
  completed leaves the rest in the warehouse.
- **Nothing out but something waiting** (an issue taken back, or one
  packlist came back before the other went out): an "out" project is
  "confirmed" again.

The material issued meanwhile is out all the same (section 1,
`material_out`); the start page lists such a project under "Gerade
unterwegs" with the badge "teilweise ausgegeben". By hand, a partly issued
project can be set to "out" or between the two kinds of "confirmed", not
back to option or inquiry and not cancelled (`guard_project_status`); a
whole project cannot be cancelled while a part has material out.

### Step by step

1. **The rows** of a packlist are derived from its material lines when the
   page is opened (`build_overview`): one row per line and product, kits
   broken down into components ("4 × speaker, from 4 × speaker set"),
   services, surcharges and Nebenkosten left out (only
   `PACKABLE_KINDS` are packed), subrentals marked, the part of a line
   covered by a subrental left out, lines in optional or alternative groups
   left out. They are not stored, so the packlist cannot disagree with the
   planning. The rows can be ordered as planned, by category or by storage
   location – the way through the warehouse (PCK-004) –, carry weight and
   volume from the material models with sums at the bottom (PCK-006), and
   hints: items with an overdue inspection, loose pieces lying in
   containers, contents that stay behind (below). On request a row lists
   the contents of its containers (MAT-037).
2. **Packing starts** with the first tick, the first chosen item, the first
   addendum or the issue (`_start_packing`): every row's text and quantity
   is noted in its `PackEntry` (`title_snapshot`, `required_snapshot`) and
   `packing_started_at` is set.
3. **Ticking** a row stores the packed quantity for line and product. A row
   can be ticked completely with one tap or partly by typing a number. The
   packlist's status follows from the ticks: open → in progress → packed.
4. **Changes after packing started** (PCK-015) are compared with the
   snapshot whenever the list is built: a row whose quantity differs is
   *changed* (more or less, with the old quantity), a row without snapshot
   is *new*, an entry whose row disappeared is shown as *dropped*. They stay
   highlighted until somebody acknowledges them (`acknowledge_changes`):
   the snapshot is taken anew, packed quantities are cut down to what is
   now required (never below what was issued), and dropped rows are removed
   unless something of them went out.
5. **Choosing items** (PCK-022), where it matters – a certain rack, the
   tested cable drum: `item_choices` offers the items of the row's product
   that are fit for use and not fixed in a container, with notes ("with
   2027-0012", "in 0500", "inspection overdue", "came back from
   this project"). `choose_items` refuses items chosen for or out with
   another project, items that came back from this project
   (PCK-028), more items than the row needs, bulk material and subrentals,
   and warns about an overdue inspection. A
   chosen item is an `Allocation` with an empty `issued_at`; choosing again
   replaces the earlier choice.
6. **Adding material while packing** (PCK-013): `add_material` adds a line
   to the project through the same `add_line` as the planning (prices,
   availability, rights), marks it `is_addendum`, puts it on this packlist
   and ticks it as packed – the packer has it in hand. A shortage it causes
   is reported.
7. **Issue** (PCK-014, PCK-018; per article, PCK-025).
   **"Ausgeben"**, the main action, books only what is ticked, with the
   ticked quantities (`issue(only_packed=True)`); it is disabled until
   something new is ticked and says how many pieces go out. If anything is
   left, the packlist is *partly issued*: rows issued in full are grey and
   locked, partly issued rows say "4 von 6 ausgegeben" and can be ticked
   on, and the next "Ausgeben" books the rest that is ticked by then.
   **"Alles ausgeben"** (`only_packed=False`, with a confirmation; hidden
   when everything is ticked) books every row with its full quantity – for
   packing done on paper. The browser form treats a missing field as
   "ticked only", so an old page never issues everything by accident; the
   API's `only_packed` defaults to `true` and answers 400 with
   a hint when nothing is ticked; `services.issue()` keeps `False` as its
   default for callers in code. "Änderungen erledigt" after an issue
   settles the packlist both ways (`_settle_issue_status`): a rest no
   longer needed makes it "issued", a new line "partly issued" again. For
   every piece that goes out:
   - sold material leaves the stock for good (PRD-013); afterwards the
     minimum stock is checked (PRD-020);
   - chosen items go out first; then, where the system can tell which items
     it must be – the item the line wishes (PRJ-064, PCK-024), the only item
     of the product, or the whole stock – it writes an `Allocation`
     (PCK-021); otherwise it books the quantity and asks nobody. Allocated
     items are set to "in use";
   - the **contents** of an allocated container go with it (MAT-037): fixed
     contents always, loose contents unless they were taken out for this
     project – each content an allocation of its own, linked to the
     container's by `with_container`;
   - an item with an overdue inspection goes out with a warning (MAT-032).

   The project goes to "out" once everything is out (above); the webhook
   event `project.status_changed` → `out` comes with the last issue, and
   `packing.issued` names the project's status as it is.
8. **Return** (PCK-016, PCK-018; ticked and booked, PCK-028)
   works like packing and the issue, as soon as anything is out – also
   while the rest of the packlist is still packed and issued. Ticking a row
   as back (`set_returned`, "Alles ist zurück" = `return_all`) only stores
   `returned_quantity`; **"Rücknahme buchen"** (`take_back`) books what is
   ticked and not booked yet into `taken_back_quantity`, with the time.
   Details below ("Partial return per piece"). Sold rows are not returned.
   A row knows its state (`PackRow.return_state`, from the ticks): *out* –
   issued, nothing back yet, the normal case and shown plainly; *partial*
   – some pieces back, highlighted; *back*; *clarified*. "Out" is not
   "missing" (PCK-023): only when somebody tries to complete the return
   while rows are still open are those rows marked and the question "what
   happened?" asked. Once a row is completely **taken back** (not only
   ticked), its allocated items – contents included – are back and
   "available" again. A defect found on return can be reported for any
   item of a product on the packlist, with a photo (PCK-017, MAT-023): the
   item becomes "defective" and the warehouse is told.
9. **Completing the return** (PCK-019) is refused while a row is not back
   and nobody has written down what happened to the rest. It first books
   what is ticked (PCK-028), then closes every open allocation, drops items
   that were only chosen, sets the packlist to "returned" and, if no other
   packlist is out and none waits to be issued, the project too. After a
   partial issue, what never went out simply stays in the warehouse. A booking completes the return by itself when it leaves nothing
   out and nothing waiting (below); "Rücknahme abschließen" moved from the
   sticky bar into the list and is for clarified missing parts or a rest
   that will not go out.
10. **The PDF** is the same list for the clipboard, one per packlist,
    rendered from HTML by WeasyPrint (`packlist_pdf.html`), with tick boxes
    and fields for signature and date.

An issue booked by mistake can be taken back (`undo_issue`) as long as
nothing has been returned and no sold stock was removed – all issues of
the packlist at once, also after several partial ones; ticks and chosen
items stay. Every step is in the change log with user and time. While material
is out, the status of the project can only move on through the return:
`guard_project_status` keeps the project in step with all its packlists –
setting it to "returned" by hand completes the return of every packlist
that is out, provided nothing is missing, and books what is ticked as
back first.

### Partial return per piece (PCK-028)

Requirement: part of the material can be taken back, more issued, and the
rest taken back again. Decision (per piece): what came back cannot go out
again in this project; what was never issued still can.

- **Two tabs.** A partly issued packlist shows "Packen/Ausgabe" or
  "Rücknahme" (`views._mode`, `?mode=return`); an issued one only the
  return. After "Rücknahme buchen" on a partly issued packlist the page
  stays on "Rücknahme".
- **Four quantities**, each including the next: packed ≥ issued ≥ ticked
  back ≥ taken back (data-model, "Packing"). `return_limits(row)` keeps a
  tick between what is taken back already – a booked piece stays booked –
  and what was issued and not handed over to another part (PRJ-060).
- **Booking** (`take_back`, `_book_ticked_returns`, rows locked with
  `select_for_update`): per row it books `min(ticked, issued − handed
  over) − taken back`, sets `taken_back_at`, and frees the items of a row
  that is now completely taken back (`_close_allocations_if_back`). It
  refuses when nothing new is ticked. An event `packlist.taken_back` with
  the number of pieces goes into the history.
- **Example:** 10 planned, 6 issued, 4 ticked and booked back. Those 4 are
  done: `issued_quantity` (6) still counts them, so `to_issue` is 4 and
  the 4 never go out again; 2 are `still_out`. Packing and issuing the
  remaining 4 works as before.
- **Items.** An item that came back from the project is skipped by the
  automatic allocation and refused by "Exemplare wählen" (`_back_from`).
  With it out of the count, the one item left of a product counts as
  unambiguous. While only part of a row is back, its items stay "in use":
  nobody knows which of them came (PCK-020).
- **Auto-complete.** If a booking leaves the packlist "issued" with
  nothing still out (`still_out_total`), no handover awaited and no
  missing row, the return completes itself (`_finish_return`): packlist
  "returned", allocations closed, the project follows.
- **Project status.** The rules work on
  packlist status; `material_out()` now asks whether pieces are out by the
  books (section 1). The project becomes "returned" only through the
  completed return.
- **Webhooks and the API are compatible.** A tick that adds pieces fires
  `packing.returned` as before, and so does a booking that completes the
  return. `return-all` only ticks; an API client that calls `return-all`
  and then `complete-return` gets the same result as before, because
  `complete-return` books the ticks first. The new action `take-back`
  books without completing. Each packlist row in the API adds
  `taken_back`, `ready_to_take_back`, `still_out`, `packed_changed_at` and
  `returned_changed_at`; the packlist adds `ready_to_take_back`,
  `taken_back`, `still_out` and `bar` (below). All quantities are text with
  two decimals.
- **Not built:** choosing which items of a row came back. Items are freed
  only once their row is completely taken back.

### The bar and the sub-tabs (PCK-029, PCK-030)

**The bar** (`services.ProgressBar`, `PackRow.bar`, `PackOverview.bar`,
template `packing/_bar.html`) fills from the left in five states: `back`
(taken back, or handed over to another part – orange), `ticked_back`
(ticked as back, not booked – orange hatched), `out` (issued and still out,
sold pieces stay here – green), `packed` (ticked, not issued – green
hatched), `in_stock` (grey). Under it a list names each state with its
number ("4 zurückgenommen, 2 ausgegeben, 4 im Lager"), so it does not
depend on colour. A
takeover row counts only the pieces that arrived. The family view uses
the same bar per part; the
start page shows no packing progress.

**Sub-tabs** (`views.packlist_tabs`, `packing/_tabs.html`): a project on
its own has one tab per packlist, as before. In a family the tabs are, in
number order, the whole project and every part – the part being looked at
split into its packlists, the others one tab each –, then "Alle zusammen",
the packlist of the whole family (PRJ-048). Parts whose packlist the user
may not see are left out (`subprojects.packing_level_in`). The family page
has the same tabs; its old button in the head is gone.

### Packlists on the phone (PCK-026, PCK-027, APP-001 ff.,)

The Android app "Rentalars-App" (catalogue 5.16, not part of this
repository) loads packlists, ticks them without network and sends the
ticks later. The server side is built for what the app needs
from the server.

**What goes on the phone** (`GET /api/v1/offline/packlists`,
`offline.offline_projects`): the projects with status `confirmed_open`,
`confirmed` or `out` whose packlist the caller may open – the rule of
`packlist_project_for`, also for rights in assigned projects only (then
the project must be visible and assigned). Per project `id`, `number`,
`name`, `status`, `start`, `end`, `venue`, `customer` (the name; `null`
with the deployment view only, AUT-023), `can_write` and `packlists` as in
`/projects/{id}/packlists`; the rows come with `GET` of each packlist
(with `ETag`). **The `GET` writes nothing** (from a code review): the main packlist is
created where the data changes – the `post_save` signal
`offline.ensure_packlist_on_confirmation` (connected in `packing/apps.py`)
creates it when a project is created in, or moves into, `confirmed_open`,
`confirmed` or `out`, by every route (web, API, inquiry), logged like a
hand-made packlist; the migration `packing/0006_sync_082` created it for
the existing ones. A project that still has none is listed with
`packlists: []`. The packlist page and `GET /projects/{id}/packlists` still
create the main packlist on first open (PCK-001, unchanged). A handful of
queries, whatever the number of projects. `server_time` is in UTC ("Z"),
as in the sync.

**The sync** (`POST /api/v1/projects/{p}/packlists/{id}/sync`,
`offline.apply_changes`) takes `{"changes": [{line, product, field,
quantity, changed_at}]}`, `field` `packed` or `returned`, at most 1000
(`MAX_CHANGES`; the app sends at most 400).

1. **Input:** invalid input refuses the whole request with 400, never 500
   – also month 13, an offset of 25 hours, a moment without time zone
   (the phone keeps the server's time, APP-005) or before the year 2000
   (`ChangeMomentField`). Write access to the packlist is needed; a
   read-only token gets 403.
2. **Order:** the changes are taken in the order of their moments (a
   moment in the future counts as now), so that of several changes to one
   quantity the latest remains.
3. **Locking:** one transaction; the packlist and the entries of the
   touched lines are locked with `select_for_update` from the comparison
   until the end, so that no change in between is lost.
4. **Conflict rule:** a change counts only if its moment is **later** than
   the stored change time of that quantity (`packed_changed_at`,
   `returned_changed_at`); equal or older gives `older` – at the same
   moment the server wins. A change that counts stores the phone's moment
   as the change time, even if the quantity stays the same.
5. **Limits** as when ticking in the browser, **refused, not clamped**
   (`_refusal`): `packed` only while the packlist can be packed, not on a
   takeover row, not above what is needed, not below what is issued;
   `returned` only while material is out, not for sold rows, not below
   what is taken back, not above what was issued and not handed over. A
   row that is gone is refused too.
6. **Answer:** `results` in the order of the request (`line`, `product`,
   `field`, `outcome` = `applied` | `older` | `refused`, `message` – empty
   when applied), the whole `packlist` as `GET` delivers it, and
   `server_time`. Packing status follows applied `packed` changes;
   `packing.returned` goes to the webhooks when a `returned` change
   applied – only once per sync and only if some change
   **raised** a returned quantity, the browser's rule.

**Versions, change IDs and a
deterministic clock rule (PCK-027, from a code review).** Client timestamps alone were not a reliable
conflict rule: several future moments were all clamped to the same server
time, so the first could win and the truly later one be dropped.

- **Versions.** `PackEntry.version` rises by one on every change of the
  packed or returned quantity, by whatever route (`PackEntry.save`); rows
  of `GET …/packlists/{id}`, of the sync's packlist and of the family view
  carry `version`. A change may send **`base_version`**, compared with the
  row's version **at the start of the sync** (so changes within one sync do
  not conflict with each other). Equal → the change applies. Different →
  if the server already has the quantity the phone wants, `applied` with
  nothing written; otherwise **`conflict`**: the server's state stays and
  is returned in `server` (`quantity`, `changed_at`) with `version`, never
  silently lost.
- **Clock rule without `base_version`** (the app sends none):
  the server reads its clock only **after** locking the packlist; a future
  moment counts as now; changes are ordered by (clamped moment, original
  moment of the phone, request order), so clamped changes keep their order
  among themselves and within one sync the later change to the same
  quantity wins; against the server only a **strictly later** moment counts
  (equal → server); the stored moment never goes back.
  Two changes with equal moments in one sync both apply, the later in
  request order wins.
- **Change IDs.** A change may carry **`change_id`** (≤ 64 characters, e.g.
  a UUID). The judged outcome is stored as a `SyncReceipt` per user and
  ID; the same change sent again – the answer was lost – gets that outcome
  with `replayed: true` and is not judged again. The same ID for a
  different change is refused; the same ID twice in one request is judged
  once. Receipts older than `RECEIPT_DAYS` (30) are pruned by each sync.
- **Locks:** the packlist is locked before its entries, in the sync and in
  `services._LockedEntries` (`pack_all`, `acknowledge_changes`, `issue`);
  `_start_packing` and `resolve_missing` save only their own fields. Not
  proven by a test – SQLite shows no race.
- **What the app should adopt:** keep each row's `version`; send
  `base_version` and a `change_id` kept until a result arrives; handle
  `conflict` (show `server.quantity`, update the row, let the user tick
  again); treat `replayed` as the original outcome; show `packlists: []`
  as "keine Packliste"; ignore unknown keys.
- An open packlist page follows ticks of others and of the app through
  the change key `packing:<pk>` ([architecture.md](architecture.md),
  "Pages that follow changes").
- **Reason codes** (PCK-013): a packed quantity above the
  list is refused for everybody, as, now with `reason`
  `needs_project_write` (the caller may not add material; the message
  names who may) or `above_packing_list` (the caller could add material in
  the browser) – `offline._judge` asks `services.may_add_material` once per
  sync. The other changes of the sync still apply. The receipt stores the
  `reason` (`SyncReceipt.reason`), so a replay returns it too.
  `/offline/packlists` names `can_add_material` per project.

**Packing with the role Crew** (PCK-013, the user's rule:
everything that writing implies, but nothing with a financial effect).
`accounts/0007_crew_packing_084` gives "Crew" write on packing in its
assigned projects. Every packing step then needs write on packing only –
ticking and scanning, choosing items, issue and undo, take-back and
complete-return, missing parts (a note), defects, further packlists
(create, rename, delete: lines go back to the first), moving lines,
handovers (charged once at the source line), taking items out of
containers – because none of them changes a price or a cost; ticking is
capped at the list everywhere (`set_packed`, the sync). The one exception
is **adding material while packing** (`add_material`), which creates a
charged material line: `services.may_add_material(rights, user, project)`
is true for write on packing everywhere (`level_everywhere`, the
warehouse) or edit access to the project (`projects.access.access_level`,
the project manager); the view, the API (403 `needs_project_write`) and the
packlist template ask it, and the template shows the hint "Material
nachtragen dürfen nur Personen, die das Projekt ändern dürfen oder für alle
Projekte packen." in place of the field. `DELETE` on packing endpoints
needs write on packing (`PacklistView.action_levels`), not the level
"delete" other modules ask.

The sync never issues and never books a return – both stay steps in the
browser. Its route sits before `…/{action}` in `api/urls.py`, which would
otherwise take "sync" for a packing step. `api/docs` also answers without
the slash, because the app expects no redirects under `/api/v1`.

**Tokens of an app** (AUT-021, a security fix): the app logs in with
password (and code), then creates its own token limited to `packing`,
`projects` and `time_tracking` (also `email`, which opens
chat, mails, price overview and `/mail/unknown`). Such a token must not open more than it
has (`accounts.api.ApiTokenViewSet`): a token limited to modules creates no
tokens (403, "Create tokens in the browser") and under `/tokens` sees and
revokes only itself; a token with an expiry creates only tokens that
expire no later than itself, and must then give `expires_at` (400
otherwise); a read-only token still gets 400.

**Customer material** (PRJ-096) is a row like any other –
packed, issued and returned as usual, with weight, volume and storage
location in the sums for the transport. `PackRow.is_customer_material`
adds the hint "Kundenmaterial – wird mitgeführt" on the screen, the PDF
and the packlists of a whole project; the addendum's search passes the
project, so the owner's material can be added while packing.

### Taking contents out of a container (MAT-042)

A loose item can be taken out of its container for one project
(`extract`, from the item's page): the project must take the container
along and not be finished. The `Extraction` makes the item free for other
projects during that project (section 1), the container's packlist names it
as staying behind, and at the issue it does not go out with the container.
Cancelling the extraction puts it back into the plan.

### The packlist of a whole project (PRJ-048)

Every subproject is packed, issued and returned on its own packlists, and
its status follows them as above. `build_family_packlist` puts the
packlists of the whole project and of every part together, read-only, at
`/projects/<whole>/packlist/family/` (the same address of a part leads
there):

- **by subproject** – the whole project's own rows, then every part with
  its progress: pieces to pack and packed, issued, out and back, taken
  over from other parts and arrived, handed on to later parts;
- **summed up by article** – for the warehouse: per product, how many go
  out of the warehouse altogether ("Aus dem Lager", warehouse rows only),
  how many are taken over between parts ("Übernahme", apart), issued and
  back in the warehouse – warehouse movements only, so taken-over pieces
  are never counted twice.

Each part is shown only if the user may see its packlist (the rule of
`packlist_project_for`, `packing_level_in`); the page counts the parts it
leaves out. The PDF has both views, the API (`…/packlists/family`) returns
both at once.

### Handing over between subprojects (PRJ-060)

Line T of part B takes over 6 spotlights from line S of part A
(section 1). The pieces go from A's stage to B's on a truck, not through
the warehouse.

1. **Packing.** On A's packlist, S is an ordinary row; it says "6 gehen
   weiter an 2026-0042-2 …" and later how many were handed over. On B's
   packlist, T says "Übernahme aus 2026-0042-1 …, nicht aus dem Lager": it
   cannot be ticked, have items chosen or be issued, and it counts towards
   neither progress nor weight. Issuing B skips it, so no free item is
   allocated for it; B is "issued" as soon as its warehouse rows are out.
2. **A goes out** as usual. Only now can anything be handed over.
3. **The pieces arrive at B.** On B's packlist, "Übergabe buchen" at row T
   (`hand_over`), with a quantity – by default everything expected that
   is still out with A, at most that. It needs packing write access to the
   packlists of both parts. One `Handover` row is written: on A's entry the
   pieces count as handed over (`handed_over_quantity`), which for A is as
   good as back; on B's entry as issued. B's packlist becomes "partly
   issued" or "issued", and B's project "out". If the booking takes every
   piece still with A, A returned none of them and all of S's handovers go
   to this row, the item allocations move too: A's are closed – the items
   stay "in use" –, and new ones open at B, contents included, linked to
   the handover. The event `packing.handed_over` goes to the webhooks.
4. **B comes back** as usual: T's pieces are returned to the warehouse
   with B's other rows.
5. **A's return** counts handed-over pieces as back. Pieces still waiting
   for their handover count as missing: "Alles ist zurück" leaves them
   out, and completing A's return is refused, naming the part they wait
   for, until they are handed over, ticked as back after all, or
   clarified (PCK-019). After A is returned, nothing more can be handed
   over from A.

**Taking a handover back** (`undo_handover`) is possible for the latest
booking of a row, while neither A nor B is returned and none of its
pieces is back in the warehouse or gone on further. It reopens A's
allocations; if nothing of B is out any more, B goes back to its packing
status and B's project is no longer "out". Taking back A's issue is
refused while pieces have gone on; taking back B's keeps what arrived by
handover.

---

## 5. Import of lists

*Code: `rentalars/core/tabular.py`, `imports.py`, `import_views.py`,
`import_api.py`, `jobs.py`; `rentalars/material/importer.py`,
`products/importer.py`, `customers/importer.py`, `personnel/importer.py`.
Catalogue: IMP-001 to IMP-012, NFA-041. Tests: `tests/unit/test_importer.py`,
`tests/unit/test_stage5_imports.py`, `tests/ui/test_stage5_import_export_pages.py`,
`tests/api/test_imports_export_api.py`, acceptance scenarios 8 and 16.
Guide for operators: [docs/betrieb/import.md](../betrieb/import.md).*

Four lists can be imported: material, products, customers and people. They
share everything but the meaning of a row (see
[architecture.md](architecture.md), "Imports"):

1. **Read** the file (XLSX or CSV) into a plain `Table` (`read_table`).
2. **Map** columns to fields. Headings are recognised by the label and the
   aliases of each `ImportField`; every assignment can be overridden
   (IMP-003). The labels say "Beschreibung" and
   "Rechnungsdatum", and the former headings ("Spezifikation", "Tag des
   Kaufs") are still recognised; the product import knows the kind
   "Nebenkosten", and a service it creates brings its job function
   (PRD-044, `products/importer.py`).
3. **Check and write** – the importer of the module, in one transaction:
   every row is checked; a record that exists is found by its key and
   updated, never duplicated (IMP-004); if any row has an error, or for a
   dry run, the transaction is rolled back at the end (IMP-009).

| List | Key that finds an existing record | Needs, besides the module's write right |
|---|---|---|
| material | the ID of the item | – |
| products | the article number; its letters name the main category, which must exist | the price right for prices |
| customers | in this order: the customer number, the VAT ID, the e-mail address (of the customer or a contact), the name (without case, punctuation, legal form; umlauts spelt out) – see below; a row that finds nobody becomes a new customer, with the number of the file if it is free, else with the next number; a possible duplicate (similar name, same e-mail address) is a warning, not an error | the price right for the standard discount |
| people | the e-mail address, else first and last name (several of the same name without e-mail address is an error) | the right to see personnel costs for hourly rates |

Only the fields a column is assigned to are touched; everything else keeps
what is in the database. For customers, not even an empty cell
changes anything (IMP-013). The products, customers and people exported from
their lists as CSV with all columns come back under headings the import
recognises; an unchanged list imported again changes nothing
(`tests/ui/test_stage5_import_export_pages.py` checks this for all three).
A completed import is recorded as one event with its counts
(`import.material`, or `import.records` with the kind).

**Customers are merged, not duplicated** (IMP-013,
`customers/importer.py`). The contact export of a bookkeeping program
such as Lexware comes in as it is: its headings ("Firmenname", "Straße 1",
"Ansprechpartner 1 Vorname" …) are recognised, and a CSV file may be in
Windows-1252 – the encoding is detected in the order byte order mark,
UTF-8, Windows-1252, ISO-8859-1 (`core.tabular.decode_text`). Each row
looks for its customer step by step: number, VAT ID, e-mail address,
name. A step that finds several is narrowed down by the later ones; if
several remain, the row becomes a new customer and the dry run names those
that came into question. A customer is found by at most one row of a
file, a private person is never taken for a company with a legal form in
its name, and a number that matches while name, VAT ID and e-mail address
all disagree is a warning. A customer that is found is completed, never
emptied: empty cells keep what Rentalars has, names that differ only in
spelling keep the Rentalars version, a contact is added unless one with
the same name or e-mail address exists, a delivery address unless the
same one exists, and a main address in another street or city keeps the
old one as a further billing address. The report says for every row
whether it is new, merged with whom and found by what, or unchanged.

A person the people import creates gets an account like every new person
(AUT-026): a username from the name, no password, the role "Crew" or
"Freie Kraft".

### In the background (NFA-041)

In the browser a dry run and an import never run inside the request:

1. The uploaded file is stored under a random name in `DATA_DIR/imports`;
   the session remembers the name.
2. "Dry run" posts the mapping; `imports.start` stores a `BackgroundJob`
   of kind `import` with kind, file, mapping and `dry_run`, and starts it as
   a process of its own (`core/jobs.py`).
3. The task reads the file again, runs the importer with the rights of the
   user who started it and reports its progress every 50 rows; the report
   goes into `job.result["report"]`. While it runs, the page asks every two
   seconds; when it is done, the page shows the report and, after a dry run
   without errors, "Import now".
4. "Import now" starts a second task with the same mapping. After a
   successful import the file is deleted; a file left behind is removed by
   the daily maintenance after two days (only files with the random name of
   an upload).

If the process of a task dies – a restart of the server –,
`rentalars-jobs.timer` notices within a minute and runs the task once
more; an import writes all or nothing, so running it again is safe.

The API does the same with `background=true` (the answer is the task,
`/jobs/{id}` holds the report); without it the import runs inside the
request and refuses files of more than `MAX_IMPORT_ROWS_PER_REQUEST`
(5,000) rows, because a request is ended after two minutes. The commands
`import_material` and `import_data` run in the foreground without a limit.

### The material list

The existing Excel list has one row per item with 13 columns. The database
separates model and item and refers to categories, suppliers and other
items. The importer translates, in six steps:

1. **Read** the file (XLSX or CSV) into a plain table.
2. **Map** columns to fields. Headings are recognised by name ("ID",
   "Artikelname", "Kaufpreis" and common variants); every assignment can be
   overridden (IMP-003).
3. **Check** every row without touching the database: is the ID a number,
   the date a date, the price a price, does "installed in" name an ID that
   exists in the file or in the database?
4. **Write**, in one transaction: categories, suppliers and manufacturers
   that do not exist yet; one model per distinct article name (IMP-002);
   the items. An item whose ID already exists is updated, never duplicated
   (IMP-004) – the import can be repeated.
5. **Resolve "installed in"** in a second pass, because the column refers
   to rows of the same table (IMP-010). Circles are reported.
6. A **dry run** does all of this and rolls the transaction back at the end.
   It therefore reports exactly what the real import would do (IMP-009).

**All or nothing.** If a single row has an error, nothing is written. The
report names every problem with its row number and column, so the file can
be corrected in one go.

**Example.** Three rows

```
ID    Artikelname        Kategorie  Einsatz/Verbindung  Kaufpreis
0500  Funkrack 4 Kanal   Ton                            1.250,00
0310  EW 100 G4 Empf.    Ton        0500                  499,00
0311  EW 100 G4 Empf.    Ton                              499,00
```

become two models ("Funkrack 4 Kanal", "EW 100 G4 Empf.") and three items;
item 0310 is installed in item 0500. The report of the dry run counts what
would be created – 2 models, 3 items – and lists the category "Ton" if it
did not exist yet.

The command `import_material`, the import page in the browser and
`/api/v1/imports/material` all call the same function, `import_material()`
– the page and the API through the registered `ImportKind`.

The material import knows three more things:

- **Custom fields** (MAT-073, `customfields/importing.py`).
  `CustomColumns` takes every column whose folded heading is the name of a
  custom field and that is not mapped to a field of the import; a column
  of a sensitive field is left out with a warning for a user without the
  purchase-price right. After the writer saved an item (step 4) it calls
  `CustomColumns.apply`: each cell is cleaned by `CustomField.clean_value`
  (type, options, pattern), a field outside the fieldset of the item's
  model is an error unless the cell is empty or already equal, a unique
  value is checked against all other items, and `services.store_values`
  saves what changed – one change-log entry per value. Errors go to the
  report, so the transaction is rolled back as for any error; an empty
  cell empties the value; required values are not demanded. A row counted
  "unchanged" whose custom values change becomes "changed" in the preview
  (IMP-011), the change labelled "<field> (eigenes Feld)".
- **Storage locations by path** (IMP-017). `_Writer.storage_location` reads
  a cell with `>` as a path (`location_paths()`, case and spaces around
  `>` folded) before it falls back to the name; a path that does not exist
  becomes a new top-level location with the whole text as its name, as an
  unknown name always did.
- **The apostrophe of an export** (IMP-017). `core.tabular.cell_text`
  removes a leading `'` before `=`, `+`, `-` or `@` (and one of a doubled
  `''`), which `core.import_exports.cell` and the CSV of every list put in
  front of formula-like text; `choice_of` also accepts the German label of
  a choice in every language.

### The export in the import format (IMP-017)

*Code: `rentalars/core/import_exports.py`, `core/import_views.py`
(`import_format_export`), `core/import_api.py` (`ImportExportView`),
`material/import_export.py`, `products/import_export.py`,
`customers/import_export.py`, `personnel/import_export.py`,
`customfields` (`register_columns` in `apps.py`). Tests:
`tests/unit/test_092_exports.py`, `tests/browser/test_092_exports_in_browser.py`.*

The aim was a plain-text CSV, so that one could in theory go on working with
the CSV without Rentalars. The rule that makes that checkable: **the
file of each import, imported again, changes nothing** – the dry run calls
every row "unchanged" (`RoundTripTests`, per kind, also with custom
fields, sets, nested categories and paths).

1. **Columns.** `ImportFormatExport.columns_for(rights)` takes the fields of
   the import in their order, under their labels (German, as the import
   headings), then the columns other modules registered with a heading of
   their own (the custom fields, by name). A column whose `right` the user
   lacks is dropped – prices and maximum discount (`prices`), purchase
   prices and vehicle costs (`purchase_prices`), sensitive custom fields;
   the people's "Funktionen" stays but leaves out the rates without
   `personnel_costs`. Importing such a file leaves those values alone
   because an absent column touches nothing.
2. **Rows in chunks.** Each module's `chunks(rights)` yields lists of at
   most `CHUNK_ROWS` (2,000) rows read with `values()` and a fixed number of
   queries per chunk (the material: models, categories by path through
   `CategoryIndex`, storage locations by path, suppliers, products – five
   queries in all, one more per chunk for the custom values). Anonymised
   customers and people are left out (the import would refuse or recreate
   them).
3. **Cells** (`cell`): text trimmed, dates `31.12.2027`, numbers with a
   decimal comma and no grouping (`number`, `amount`), booleans "ja"/"nein",
   choices by their German label (`label`), all under
   `translation.override("de")`; text starting like a formula – not a
   plain number such as `-12,50` – gets a leading apostrophe, as does text
   that starts with an apostrophe before such a character.
4. **Streaming.** `stream()` writes the byte order mark and the heading row,
   then one piece per chunk; `response()` sends it as a
   `StreamingHttpResponse`, so 20,000 items leave in a few seconds without
   a background task. Read access to the module of the import is enough,
   as for the CSV of the list; the download is a CSV answer and counts as
   an export in the access log.

What the import has no column for – the item's own description and own
category values, a fourth contact, further addresses, project lines – is
not in the file; that is what the readable export of all data is for
(architecture, "The full export").

---

## 6. Crew: price, cost and warnings

*Code: `rentalars/projects/crew.py`, `hour_tiers.py`, `course.py`,
`rentalars/personnel/services.py`; `core/changes.py` (stamps). Catalogue:
PRJ-019 ff., PRJ-051, PRJ-052, PRJ-061, PRJ-073, PER-005 to PER-008,
PER-018, PER-029, PRJ-080, PRJ-088, PER-033,
PER-034, PRD-044, PER-035 to PER-037. Tests:
`tests/unit/test_crew.py`, `tests/unit/test_062_crew.py`,
`tests/unit/test_062_personnel.py`, `tests/{unit,ui,api,browser}/test_070_crew*`,
`tests/{unit,ui,api,browser}/test_071_services*`, acceptance scenarios 4
and 15.*

A crew line has two sides that never mix. (Both can carry
surcharges for night, Sunday and holidays – section 25.)

**The price for the customer** comes from the service product of the job
function (PER-008). `defaults_from_job_function` copies title, price,
tax rate and the way of billing onto a new line; from then on they are
the line's own. A service product billed as daily rental makes new lines
"per day", one billed flat a flat-rate line.

**One function, one service product** (PRD-044). Every job
function has exactly one service product and every service product one
function (data-model, "Personnel"), so adding crew needs nothing in the
material planning: the line names the product – its article number stands
on the line in the planning, the price overview and the documents
(`service_product_article_number` in the API) – and takes price, tax rate,
billing and the hour tiers from it (a crew line has no unit of its own:
hour, day or flat follows from its billing). A product without price yet
gives the line 0.00. Creating a function creates its product (`save_job_function`, with an
optional price per hour); creating a service product creates its function
(`products.services.save_product`).

**By effort by default** (PER-036). A product billed by the
hour makes a new line "nach Aufwand": the
customer pays the approved hours, and until there are any the planned
hours, marked as an estimate. New service products are billed by the hour
(`DEFAULT_BILLING_MODE`). Existing lines keep their
billing; the dialog and the API can still choose any.

| Billing | Amount | Example at 45.00 per hour |
|---|---|---|
| by plan | planned hours × price | 8 h → 360.00 |
| flat rate | the price itself | 300.00 |
| by effort | approved hours × price; until times are approved: planned hours × price, marked as an estimate (PRJ-061) | 9.5 h → 427.50 |
| per day (PER-029) | days × price, the price being per day | 2 days at 400.00 → 800.00 |

The days of a line per day are those typed into `days`, else the calendar
days its period touches (`calendar_days`, local time): Monday 08:00 to
Tuesday 20:00 is 2 days, Saturday 22:00 to Sunday 04:00 too, Monday 08:00
to Tuesday 00:00 is 1. Offer, order confirmation and invoice show the days
with the unit "Tag" (invoice code DAY).

The line's own discount (`discount_percent`) is deducted from
that amount, within the maximum of its job function (PER-026, section 2).
The customer's standard discount is not taken over: it stays for material
lines.

**The rates** (PER-029). A person's rows of a job function may
carry an hourly rate, a day rate, both or none, from a day on or – without
`valid_from` – always. `personnel.services.rate_for(person, job_function,
at)` reads them in one query and returns a `Rate`: the row that applies on
the day (`applicable_row`: the latest dated row not after the day, else the
undated row, else the earliest row), its own rates (`own_hourly`,
`own_daily`), and the rates to calculate with – the own one, else the guide
value of the job function (`guide_cost_rate`, `guide_daily_cost_rate`).
The row counts as a whole: an empty day rate in the row of 1 July means
the guide value from 1 July on, not the day rate of the row before.
`person=None` (an open place) gives the guide values. `RateBook(people)`
does the same for many people with one query; `rate_on` is only the
person's own hourly rate.

```
Anna, Tontechnik:   –/–  always;  35.00/280.00 from 1 July
Guide values:       30.00 an hour, 250.00 a day
rate_for(anna, tontechnik, 30 June)  → 30.00 / 250.00 (guide values)
rate_for(anna, tontechnik, 1 July)   → 35.00 / 280.00 (own)
```

**The cost for the company** comes from the person. When a person is put on
a line (`add_crew_lines`, `update_crew_line`), `rate_for` on the day the
line starts gives the person's **own** hourly and day rate, and both are
written onto the line (`hourly_rate`, `daily_rate`, PRJ-021); a guide value
is never copied there, so the deployment view never shows one as "my
rate". Changing person or job function fetches both again; removing the
person clears both. Later changes of the person's rates do not reach the
line. The cost (`price_crew_line`):

1. the flat amount agreed with the person (`cost_flat_rate`, PER-018),
   whatever the hours;
2. for a line per day: days × the line's day rate, else × the day guide
   value of the job function (`cost_per_day`);
3. otherwise – and per day when there is no day rate at all – planned
   hours × the line's hourly rate; without a person or without an own
   hourly rate, × the guide value (`cost_is_guide`, shown as "Richtwert").

**Hour tiers per day** (PER-035). The requirement: a higher
hourly rate above a limit of 10 hours, for price and costs,
counted per day. The service product carries `hours_limit` and
`price_above_limit`; a new line copies them (`hours_limit`,
`unit_price_above_limit`), and `hourly_rate_above_limit` comes with the
person like the hourly rate. They apply only to lines billed by the hour –
"nach Plan" and "nach Aufwand" (`CrewLine.has_hour_tiers`) –, never to a
flat rate or a line per day. `price_crew_line` counts **per calendar day
and per line** (`projects/hour_tiers.py`, plain arithmetic, no query):

- **by plan** – `planned_hours_per_day`: while the planned hours are the
  length of the period (the suggestion), each local calendar day gets the
  hours of the period that fall on it; hours typed by hand are spread
  evenly over the days the period touches; `split_at_limit` then splits
  each day at the limit;
- **by effort** – `approved_hours_per_day`: the approved entries, each on
  the local day it **starts** (a night shift belongs to the day it began).
  The entries come with their day and fixed rate in the one query of
  `approved_times`. Until something is approved the planned hours stand in,
  split as by plan.

```
Tontechniker: 45.00 an hour, from 10 h a day 55.00; Anna 35.00, from the limit 42.00
Planned Mon 08:00 – Tue 20:00 (36 h):  Mon 16 h = 10 + 6, Tue 20 h = 10 + 10
  price by plan  20 × 45.00 + 16 × 55.00 = 1,780.00
  cost           20 × 35.00 + 16 × 42.00 = 1,372.00
  20 h typed by hand instead: 10 + 10, nothing beyond the limit → 900.00
Approved Mon 08:00–20:30 (12.5 h), Tue 22:00 – Wed 03:00 (5 h, counts on Tuesday):
  price by effort  15 × 45.00 + 2.5 × 55.00 = 812.50
  actual cost      12.5 h on Monday: 10 × 35.00 + 2.5 × 42.00; Tuesday 5 × 35.00 = 630.00
```

The planned cost always uses the planned hours; what the approved times
actually cost (`actual_cost_with_limit`) takes the rate fixed on each entry
up to the limit of its day (ZEI-008) and the line's rate from the limit
beyond it. **The rate from the limit:** the person's own
(`hourly_rate_above_limit` on the line), else the person's hourly rate;
for an open place or a person without own hourly rate the guide value from
the limit of the function (`guide_cost_rate_above_limit`), else its guide
value per hour – the same order as `RateBook.rate` (`Rate.above_limit`).
`CrewPrice` carries the split – `hours_limit`, `hours_above_limit`,
`normal_hours`, `unit_price_above_limit`, `amount_above_limit`,
`cost_hours_above_limit`, `cost_rate_above_limit` –, shown in the planning
("davon 2 Std. über der Grenze"), the price overview and the documents
("davon 2 Std. über 10 Std. am Tag zu 55,00 €" in the details of the
position: the unit price is the one up to the limit, the amount the sum of
both, as the XRechnung states it), and in the API of the crew line (the
cost fields with the right for personnel costs). In the crew dialog limit
and price from the limit need the price right, the rate from the limit the
right for personnel costs; "Neue Preise übernehmen" (PRJ-072) brings the
product's limit along with its price. A changed limit alone is not pointed
out.

**Planned hours** are suggested from the period (`suggested_hours`) and
follow a changed period as long as nobody typed a number – the line's
hours count as a suggestion while they equal what the rule gives for its
period. (PRJ-073, decided: the whole period, e.g. 36 hours) the suggestion is always the whole length of the period, end minus
start in quarter hours, worked out in UTC (a night across the change to
summer time is an hour shorter): Monday 08:00 to Tuesday 20:00 is 36 hours,
Friday 10:00 to Sunday 18:00 56. Where nobody works through, the planner
types the real hours. A period over 16 hours is not read as
working days of its clock times; the migration
`projects/0009_crew_phases_and_days` recomputed the lines that still
carried its suggestion (a copy of the old rule is in the migration), except
in closed and cancelled projects.

**Crew per phase** (PRJ-080). A line can belong to a phase of
its project (`CrewLine.phase`). Planned for a phase – in the planning, or
with "+ Personal für diese Phase" on the tab "Zeitplanung"
(`crew_views.phase_crew_add`) – it takes the phase's period unless given
one of its own; without JavaScript the server takes the phase's period
when "Von"/"Bis" are empty or untouched, and the API does the same for a
new phase without start and end. `course.crew_by_phase` lists the lines
under their phases for the tab (one query), the lines without phase last.
When a phase moves, `course.update_phase(phase, move_crew=True, …)` – the
box "Personal dieser Phase mitverschieben" is ticked by default, the API
takes `move_crew` (default true) and answers with `moved_crew_lines` –
reads the stored old period and calls `crew.move_with_phase`:

- a line with exactly the phase's old period gets the new period, also when
  the phase only got longer or shorter;
- every other line moves by the change of the phase's start, wall-clock as
  in duplicating, and keeps its length – setup 08–20 with Anna at 14–18,
  moved to 10–22, puts Anna at 16–20; a phase that only changes its end
  leaves these lines alone; only inside the hour skipped by summer time
  could the end come before the start, and then the line keeps its length
  in hours;
- nothing is cut or refused (neither lines nor phases are bound to the
  project's period); suggested hours follow, typed hours, typed days and
  rates stay; the page reports how many lines moved and any double
  bookings at once.

Deleting a phase keeps its lines with their periods, without phase.
Duplicates and templates keep the phase of a line.

**A new phase from the crew planning** (PRJ-094). For
whoever may edit the project while it is not closed, `phase_field(…,
offer_new=True)` puts `data-new-phase-url` and `data-new-phase-label` on
the phase list of the crew form below the planning (`CrewAddForm`) and of
the dialog "Personalposition bearbeiten" (`CrewLineForm`); a project
without phases gets the list hidden. Someone who may plan crew but not
edit the project (role "Personaldisposition") gets neither entry nor
dialog. The rest is the script (`app.js`, block PRJ-094):

1. it appends "Neue Phase …" (value `new`, never sent) to every such list
   and shows a hidden one;
2. choosing it loads `projects:phase_dialog`
   (`/projects/<number>/phases/new/dialog/?start=&end=`, with the period
   typed in the crew form) into a `<dialog id="phase-dialog">` of its own,
   created on demand and stacked over the crew line's `#dialog`. The view
   (`course_views.phase_dialog`) requires edit access, answers a request
   without `HX-Request` with a redirect to "Neue Phase", starts the period
   as typed (else the project's), uses the field prefix `new-phase-` and
   leaves out the notes. (PRJ-116) the period comes from
   `course.first_guess`, in this dialog and on "Neue Phase" alike: the
   typed period only if it differs from the rental period, else from the
   end of the latest phase while that lies within the rental period, else
   from its start; a guess ending on a later day lasts one hour;
3. saved through `course.add_phase`, it answers **204** with
   `HX-Trigger: {"phaseCreated": {id, label, start, end}}` – not
   `objectCreated` with `closeDialog`, which would close the crew line's
   dialog too;
4. the script adds the phase to every phase list of the project in the
   order of time, chooses it in the list it came from and fires `change`,
   so the crew form takes over the period as with any phase; job function,
   person, places and note stay. The dialog's own buttons close only it;
   Escape closes it and the focus returns to the list.

Keyboard: arrow or letter keys that land on "Neue Phase …" only select it;
Enter or Space opens the dialog, and leaving the list puts the former phase
back (WCAG 3.2.2, no change of context on a mere selection). A fix in the
same release: choosing a phase that starts before the typed "Von" now also
moves the minimum of "Bis", which kept the browser from sending the form
(a planning meeting before the rental period always
hit it).

**Staffing a phase by job function** (PRJ-120,
`projects/staffing.py`, `staffing_forms.py`, `staffing_views.py`,
`staffing_api.py`). "Personal für diese Phase" asks for rows "job function
× places" first (at most `MAX_ROWS` = 10, places 1 to
`crew.MAX_LINES_PER_STEP` = 50), then for one person per place, as "Neue
Exemplare" asks for a serial number per item. The form starts with
`open_rows(phase)` – one row per job function with open places in the
phase – so places named when the phase was made are filled rather than
planned twice. `staff_phase(phase, rows, rights=…, firm=…)` runs inside
`crew_changes.one_notice_per_person()`:

1. per row it takes as many open places of that job function as the row
   has places (`open_places_of`, oldest first);
2. each person chosen fills one of them through `crew.update_crew_line`
   (person, and `firm` if ticked) – or, when they are used up, gets a new
   line through `crew.add_crew_lines` with the phase (and so its period);
3. places beyond people and existing open places become new open lines;
   open places the rows do not speak for stay as they are.

All rules of the crew lines hold (PER-006 job functions, PRJ-021 copied
rates, PER-041 firm planning – refused when nobody is chosen); any refusal
rolls back the whole step. The dialog's place fields are type-ahead fields
offering the people of the job function with `person_hints` – the PRJ-022
warnings of an unsaved probe line per person at the phase's period, in a
fixed number of queries; a change of the rows refreshes `#staffing-places`
only. Without the page script the same markup is a page of its own in two
steps ("Weiter zu den Personen"). A **new phase** names rows as well
(`FunctionRowsMixin`, "Personalplätze (optional)" on "Neue Phase" and in
the dialog "Neue Phase …"): `add_phase_with_places` saves the phase and
`staff_phase` with rows without people in one transaction, so that it
gets that many open places with its period; the dialog of the planning
answers with an out-of-band refresh of the crew block
(`_phase_places_oob.html`). API: `places` when a phase is created,
`POST /projects/{id}/phases/{phase}/staffing`.

**Asking the person** (PER-016) marks the line "requested" and tells the
person (`crew.request_deployment`). The request can go out as a
mail with the buttons "Zusagen" and "Absagen", answered by reply mail
(PER-032) – section 8.

**Asking again only for new times** (PER-033). The request
stores the period asked for (`requested_start`, `requested_end`). An
accepted or declined line whose `start` and `end` still equal it
(`times_changed_since_request` false) is not asked again: the service
refuses ("Anna Becker hat für diese Zeiten schon zugesagt …", 400 in the
API) and the page offers no "erneut anfragen", only the badge. A waiting
request may be sent again (e.g. after the address was corrected). Once the
times differ, the line says "Zeiten geändert seit der Zusage – angefragt
war: Mi 10.03. 08:00 – Mi 10.03. 18:00" (`crew.period_text`), offers
"erneut anfragen" – a waiting line also "eintragen" –, and a new request
names "Neue Zeiten: … (vorher: …)" (`new_times_text`) in the notification
and the mail, with its own subject, plus a history event
`crew_line.asked_again_new_times`. Only start and end count: hours, a
phase without new times, job function, meeting point and note do not. A
line asked for without a stored period counts as changed.

**A new request by itself** (PER-034).
`crew.ask_again_for_new_times(line)` runs whenever a service changes the
period of a line – `update_crew_line` (dialog and API) and
`move_with_phase` ("Personal dieser Phase mitverschieben") – and asks the
person again through `request_deployment` if the line was requested and
is still waiting, or accepted; its times differ from those asked for; the
project is not cancelled; the person is active; and
`SystemSettings.ask_again_on_new_times` is on (default; "Einstellungen →
Firmendaten und Grundeinstellungen"). Declined lines are not asked by
themselves – "erneut anfragen" is offered there. "Angefragt von" is
whoever changed the times (`_acting_user`, from the current actor of the
change log), in a command whoever asked before. The line carries
`asked_again` for the views; the crew dialog and saving a moved phase
(`course_views.phase_edit`, via `crew_views.tell_asked_again`) say who was
asked again.
The older request mail no longer counts: a reply to it gets "neuere
Anfrage" (`CrewRequestMail` with a higher key for the same line). A new
person still starts without request. Direct ORM updates of `start`/`end`
would bypass it; none exist.

**Planned firmly, and told instead of asked** (PER-041, PRJ-118). A planner may set a line with a person to `request_status`
`firm` – `firm=True` in `crew.add_crew_lines` (the add form, the phase
crew dialog, the API) or `update_crew_line` (the line dialog, "fest
einplanen" in the row, `crew_bulk` action `firm`); an accepted line stays
`accepted`, and unticking `firm` in the dialog makes it `""` again. `firm`
counts like `accepted` everywhere a line counts as the person's
(`CrewLine.is_confirmed`) and is left out of `ask_again_for_new_times`:
new times keep it firm. Instead every changing service takes a
`crew_changes.snapshot(line)` before and calls `note_update`,
`note_removed` or `note_firm` after; they compare times, meeting point,
note, phase, job function and vehicle (not hours, prices or rates) and
collect a notice – unless the line was just asked again (`asked_again`:
the new request names the changes) or the person declined, has no active
account, made the change, the deployment is over or the project
cancelled. Inside `crew_changes.one_notice_per_person()` – the bulk
service, `move_with_phase`, `schedule.moves.apply_move` – the notices are
held and sent at the end, one notification of kind `deployment_change`
per person naming all their lines, in the person's language.

**Accepting marks "available"** (PER-042). Every acceptance –
the browser, the reply mail (`mail/crew_answers.py`), the API and the app,
or a planner entering it – ends in `crew.answer_deployment`, which calls
`crew.mark_available_for(line)` when the answer is yes. That asks
`personnel.marks.mark_available_for_deployment(person, start, end, note)`:
only if `unavailable_in` finds an own mark "not available" overlapping the
line's period (and the period is at most `MAX_DAYS`), it colours exactly
that period "available" through `mark_period` – the same function as the
own calendar, which cuts back or splits overlapping own marks, also
occurrences of a series – with the note "Zugesagt: <number> <name> –
<job function>" in the person's language. Linked calendars are sources
and stay untouched; as the newer own statement the mark wins over their
busy times (PER-027). `line.marked_available` carries the new mark to the
confirmation (`crew.available_text`, to the person or – entered by a
planner – naming the person). Planning firmly (PER-041) marks nothing, and
removing the deployment later leaves the mark.

**Several lines at once** (PRJ-117). `crew_bulk.change_crew_lines`
checks the project is editable and the values once, then runs each chosen
line through the single-line service – `update_crew_line` with only the
fields that differ (`_edit_changes`), `request_deployment`,
`delete_crew_line` – inside `one_notice_per_person()`. A line the action
cannot be done with (an open place cannot be asked or planned firmly, a
firm line cannot be asked) or that is already as wanted is skipped and
named with the reason; one that a rule refuses is named with the
message. The job function is not among the values on purpose: it changes
price and rates line by line.

**Answers show at once** (PER-033, `core/changes.py`, UIX-020). The
problem was not the server: an answer – in the browser or by reply mail –
is stored and moves the project's change stamp. But the open planning
page took over the new stamp after the planner's own save (so as not to
reload for one's own change), and an answer that came in seconds before
was swallowed with it; the line stayed "angefragt" until a reload. The stamp of a project reads `<newest change>.<newest change by
somebody else>` (still one query: two `Max` aggregates, one filtered by
`actor_id`), e.g. `123.120`. After an own change the script compares only
the second part and reloads if it moved; at the regular question every
20 seconds it compares the whole stamp, so a change by the same user in
another tab or the app still reloads. While the planner types, only the
note "Auf dieser Seite gibt es etwas Neues" appears, as before.

**The price overview by phase** (PRJ-088). The switch "Personal je Phase
und Funktion" (`?crew=phases`, carried into the PDF and CSV links) shows
`crew.breakdown_by_phase`: per phase in the order of time one row per job
function with places, hours or days, amount – and, for those with the
right to see personnel costs, cost and "Gewinn" –, a subtotal per phase,
"Ohne Phase" last. PDF and CSV never show costs; the API gives
`personnel.by_phase` with costs only with `?crew=phases` and the right.

**Warnings** (`crew_warnings`, PRJ-022) – nothing is blocked:

- the person is planned somewhere else at the same time, in this or another
  project that is not cancelled;
- the period overlaps an absence;
- the job function is not among the person's own. Planning such a person is
  refused unless the planner has the special right for it (PER-006); with
  the right it is allowed and pointed out. The form offers only
  the people who have the chosen job function (PER-025), unless the planner
  has that right;
- (PER-021, PER-022): the person marked the period "not
  available", or is busy in the linked calendar; "available with limits"
  is a quieter hint.

They are found with four queries – one of them for the availability marks
 –, however many lines the project has. The marks are
resolved first (PER-027): where an own mark and a busy time of the linked
calendar meet, only the newer statement warns.

---

## 7. A time entry from recording to the project

*Code: `rentalars/timetracking/services.py`, `models.py`. Catalogue:
chapter 5.9. Tests: `tests/unit/test_timetracking.py`, acceptance scenarios
5 and 18. An entry also gets hints at conspicuous times, and
expenses go the same way as entries – section 26.*

1. **What can be booked** (`project_choices`, ZEI-006): first the project
   the person is planned in right now – a crew line whose period includes
   the moment, or ended within the last seven days, because Saturday's hours
   are written down on Monday – then other deployments, then internal
   projects, then running projects the user may see. The job function is
   prefilled from the crew line. Which functions can be chosen is
   `job_functions_for(person, project)` (ZEI-007), never empty: the person's own functions and those of their crew lines in the
   project first; then the functions of the project's other crew lines
   and open places (for a whole project its parts too, one query); only if
   that leaves nothing every active function, as on a service case.
   Without a project the person's own functions, or all active ones for a
   person with none. The form, the check when saving and
   `time-entries/choices` (which reads the active functions once for all
   projects) use the same rule.
2. **Recording** (`create_entry`): the person's row is locked, the entry is
   checked against the person's other entries (ZEI-009: no overlap; touching
   is fine; a running stopwatch blocks everything after its start) and
   against the clock (ZEI-022: neither begin nor end after now), and
   saved. The project may stay empty (ZEI-023) – then any of the person's
   own job functions can be chosen, and the entry counts nowhere until a
   project is assigned (`assign_project`, by the person while the entry is
   open or by whoever approves). The hourly rate of person and job function on that day is copied
   into the entry (ZEI-008); where the person has no own
   hourly rate, the rate fixed on the crew line, else the guide value of
   the job function (`_fixed_rate`, PER-029). Lock, check and save are one transaction, so a
   double tap on a phone cannot save the same hours twice.
3. **The stopwatch** (ZEI-005) is an entry without end. Only its start is
   stored; the page counts up from it. Stopping sets the end to now.
4. **Status** (ZEI-012): recorded → submitted → approved, or rejected with
   a reason. The quick entry submits at once unless the tick is removed.
   Approved entries are locked for everybody; somebody who may approve can
   take the approval back, which is logged.
5. **Approval** (`approve_entries`, ZEI-013) needs the special right and
   sight of the project. Many entries can be approved in one step. An entry
   without project cannot be approved; a batch containing one is refused as
   a whole, with the count. Entries without project are shown only to
   approvers whose right holds for all projects
   (`sees_entries_without_project`) – there is no project whose access
   could be checked. (ZEI-030) `correct_and_approve(entry,
   …)` changes a submitted entry – times, break, job function, project,
   note, through `update_entry` with its checks; the new project must be
   one the approver may approve for – and approves it in the same
   transaction; for a part of a divided period the period's fields change
   for all parts and the whole period is approved. The change log of the
   entry keeps every value before, and an event "corrected on approval"
   names them in one line. (ZEI-031) approving, correcting and
   sending back tell the person – one notification of kind
   `time_decision` per person and action, with the values before or the
   reason. And (ZEI-029) `timetracking.reminders` reminds the
   approvers once a day (`run_jobs`, at the time and after the days of
   Einstellungen → Benachrichtigungen) of what waits for them, as
   Personal → Freigeben would show it, never of their own; the state per
   approver is a `notifications.ApprovalNotice`, removed when nothing
   waits any more.
6. **Into the project** (ZEI-021): an entry is linked to the crew line of
   the same person and job function when it is recorded, or at approval if
   the line was planned later. Only *approved* hours count: next to the
   planned hours of the line, as the charged quantity of a line billed by
   effort, and as actual personnel cost. Approved entries without a matching
   line are listed in the project (`crew.unassigned_times`) and can be put
   on a line or become a line of their own.

Nothing of this is stored twice: the project asks for the approved hours
per line when it is priced (`approved_hours_by_line`, one query).

**The report** (`hours_report`, ZEI-015) adds entries up by person, project,
job function or day. Amounts appear only where the reader may see the rates.
A sum that would include a hidden amount is left out entirely rather than
shown too small.

### Service cases in the choices (ZEI-024)

`project_choices` adds a group "Servicefälle": every open service case
(`case_status` open or in progress), with every active job function
(an exception to ZEI-007). The cases the person takes part in
(`participations_of`, `ServiceCaseParticipant`) come after the planned
projects, with the participant's job function preselected; all other
open cases come last and are never the preselected guess. Only the time
form and `time-entries/choices` offer them; expenses and the approval's
project choices are unchanged. The API marks them `is_service_case` and
`takes_part`.

### A period in several job functions (ZEI-025)

A period (start, end, break) worked in more than one job function is
stored as **one `TimeEntry` per part**, linked by a common
`period_key` (a UUID) – the choice that lets every existing sum, report,
CSV, export, cost and hour tier count parts without a second code path.

1. **The form** (`timetracking/forms.py`) offers in the job function list
   first the person's crew lines in the project with job function, phase
   and the line's own times ("Licht – Aufbau, Mi 10.03. 08:00–12:00",
   value `line:<id>`), then the job functions. "Mehrere Funktionen in
   diesem Zeitraum" (folded) has rows of further function (or crew line)
   plus hours; the function at the top gets the hours that are left. The
   API takes the same as `parts` (and `crew_line`) on `time-entries`.
2. **Saving** (`timetracking.services`): one transaction; the period is
   checked once – against the clock, against the person's other entries
   (the overlap check skips the period's own parts) – then one row per
   part is written, each with the period's start, end, break and note,
   its own job function, crew line, rate (`_fixed_rate` as for any entry)
   and its share in `hours`. The shares add up to the worked hours of the
   period; `TimeEntry.save()` keeps a part's share instead of deriving
   `hours` from start and end.
3. **Changing one part** (API `PATCH` without `parts`): a new start, end,
   break, project or note goes to every part, and the shares are rescaled
   in proportion (rounding goes to the largest part); a new job function
   changes only that part.
4. **Once per period:** the hints merge the parts into one span, so the
   break counts once (`hints.py`); submitting, approving, rejecting,
   taking back an approval and deleting act on every part of the period;
   the approval page shows one tick at the first part. A running stopwatch
   cannot be divided – it is divided after it stops.
5. **Into the project:** each part is linked to its crew line and counts
   there with its hours and rate, like any entry (step 6 above).
   Surcharges (PER-009) need nothing new: `entry_pieces` already spreads an
   entry's hours proportionally over its time pieces, which is exactly the
   split by hours.
6. **Shown:** `timetracking/display.py` `mark_periods` marks the rows of a
   divided period ("Teil 1 von 2 eines Zeitraums von 8 Std.") in Meine
   Zeiten, the approval, the report and the deployment view.
7. **Dividing a project** (PRJ-050) moves time entries with their crew
   lines; `projects.split._keep_periods_together` refuses a split that
   would send the crew lines of one period to different projects, naming
   person, day, times and functions; a period whose lines move together
   moves whole.

An entry without parts has `period_key` empty and behaves exactly as
before, so the companion app keeps working unchanged.

### Meine Zeiten: pay and the clipboard (ZEI-026)

`display.attach_pay` gives each entry the shown pay: the hourly rate, or –
for an entry on a crew line billed per day that has the person's own day
rate – "Tagessatz" with that rate, its amount once per calendar day and
crew line, further entries of that day "im Tagessatz"; the week sum adds
what is shown. A guide value is never shown as pay; reports, exports and
costs keep hours × rate. `display.clipboard_text` builds, for an approved
period, one block per part: the service product's name (crew line's, else
the job function's, else the job function's name), a TAB, `Datum:` with
the start date as `yyyy.mm.dd`, `Projekt: <number> - <name>`,
`Aktivität:` with the crew line's phase. The browser copies it with
`navigator.clipboard.writeText`, or – on plain http, where that is
missing – a hidden textarea and `execCommand('copy')`, and announces
"Kopiert".

---

## 8. Assigning e-mails to projects

*Code: `rentalars/mail/mailboxes.py`, `fetching.py`, `tags.py`, `imap.py`,
`sending.py`, `backends.py`, `display.py`, `crew_answers.py`, `suppliers.py`. Catalogue: chapter 5.15, EML-001 to EML-032,
NFA-058, EML-041 to EML-043, PER-032, ADM-012,
EML-046, PRJ-106, ADM-015. Tests:
`tests/unit/test_mail.py`, `tests/unit/test_062_mail.py`,
`tests/unit/test_063_crewmail.py`, `tests/api/test_mail_api.py`,
`tests/{unit,ui,api,browser}/test_071_settings*`,
`tests/{unit,ui,api,browser}/test_071_subrentals*`, acceptance scenario 12.*

Rentalars works with any number of existing mailboxes
(`Mailbox`, EML-041). Each has roles (`mail/mailboxes.py`):

| Role | Lookup | What it does |
|---|---|---|
| correspondence (several) | `correspondence_mailboxes()` | fetched; mails go to projects by their tag |
| outgoing correspondence (exactly one of the active correspondence mailboxes) | `outgoing_mailbox()`, `can_send_correspondence()` | sends the mails written in projects, with its address as sender |
| system (at most one) | `system_mailbox()` – only if active and complete | sends invitations, password links, notifications; without it `[email]` of the configuration does, as before |

Rentalars fetches over IMAP and sends over SMTP, both always encrypted
(EML-002). `save_mailbox` keeps the rules: it stores new passwords only
when given, drops an SMTP login of its own with "same login"
(`smtp_same_login`), checks what an active mailbox needs for its roles,
takes "outgoing" or "system" from the mailbox that had it (with a note for
the page) and checks, in the same transaction, that exactly one active
correspondence mailbox sends. `delete_mailbox`
deletes every mailbox, handing the sending role to a successor ("Deleting
a mailbox", below). `check_connection` logs in to IMAP (opening the inbox) and SMTP without
changing or sending anything. `own_addresses()` are the addresses of all
mailboxes – never recipients of "reply to all". The settings page and
`/api/v1/mail/mailboxes` call the same functions; `/api/v1/mail/settings`
stays, its mailbox fields meaning the outgoing mailbox (`legacy_mailbox`).

### The tag (EML-009 to EML-011)

```
AW: Bühnenplan Stadtfest [RL#2027-0042]
                          ^^ ^^^^^^^^^
                      prefix  project number
```

`find_numbers()` finds it anywhere in the subject, whatever the case, with
spaces inside the brackets. The prefix is set in the system settings
(default `RL`). Every mail sent from a project carries the tag
(`subject_with_tag`, not twice), so the answer comes back by itself.

**Tags with a former number** (ADM-012, ADM-014).
Mails sent earlier carry `[RL#P-2027-0042]`. `find_numbers`
passes what it found through `projects.numbers.numbers_of_today`, which
replaces a former number by today's – one query for all tags of a
subject, case ignored, and none when no tag can be a former number
(`may_be_former`: letter-free, or "P-" plus letter-free) –, so the fetch,
the hand assignment and the API find the project unchanged. A tag that is
a project's number of today stays as it is. A tag naming no project, old
or new, waits as an unknown tag as before. Answering such a mail from
Rentalars replaces the old tag of the same project by today's instead of
adding a second (`subject_with_tag`).

### One fetch, step by step (`fetch_mail`)

The timer `rentalars-mail.timer` runs every minute. `fetch_mail` takes the
active correspondence mailboxes that can fetch (`can_fetch`), in name
order, and lets each through when `fetch_is_due(mailbox)` – the interval
of `MailSettings` (default 2 minutes) is over since **its own**
`last_fetch_at`. "Fetch now" passes `force=True` for all. A file lock in
the data folder lets only one fetch run at a time; a second returns at
once. The mailboxes are fetched one after the other (`_fetch_mailbox`,
which never raises): each keeps its own UIDs, success, error and
notification, and one that fails stops no other. `FetchResult` adds up the
mailboxes and keeps each one's result in `mailboxes`; the command prints
one line per mailbox and exits with 1 if one failed. Per mailbox:

1. **Headers only.** The mails after the mailbox's last seen UID are
   looked at with `BODY.PEEK` – their read state does not change
   (EML-005). If the mailbox's `UIDVALIDITY` changed, the fetch starts
   from the beginning; the Message-ID keeps it from storing anything
   twice.
   Every mail is first offered to
   `mail.crew_answers.take_answer` (PER-032), in every mailbox and whatever
   the mailbox does with mails without tag: an answer to a deployment
   request is dealt with there, counted (`FetchResult.crew_answers`) and
   filed away, and steps 2 to 5 are skipped (below, "Answers to deployment
   requests by mail").
2. **Where does it belong?** (`project_for_headers`)

   | The mail has … | Then |
   |---|---|
   | a tag naming a project | assigned by **tag** (EML-008) |
   | a tag naming no project | left in the inbox, put on the list under Projects → Inquiries with its tag (EML-014, EML-042) |
   | no tag, but `In-Reply-To` / `References` of a stored mail | assigned to that mail's project by **reference** (EML-012) |
   | nothing of that, sent to a listed further address | what the address says (`untagged`): `inquiry` as below, `service_case` a **service case at once**, `ignore` left alone (EML-047, "Further addresses" below) |
   | nothing of that, in a mailbox with `process_untagged` | an **inquiry**: left in the inbox, on the same list with an empty tag, logged as `inquiry` (EML-041) |
   | nothing of that, otherwise | left alone; it never shows up in Rentalars (EML-013) |

   **Untagged mails (EML-049):** the two "nothing of that" rows that take a
   mail in (inquiry or service case) first ask
   `aliases.untagged_skip(holder, received=…, seen=…)`, where `holder` is the listed
   address or the mailbox: the mail is **left in the inbox untouched**
   when it arrived before `holder.untagged_since`, or when
   `untagged_unread_only` is set and the mail carries `\Seen`. "Arrived"
   is the IMAP `INTERNALDATE`, else the `Date` header; a mail with neither
   is left while a moment is set. The values come with the header FETCH
   (`FLAGS INTERNALDATE`, `imap.HeaderInfo.seen`/`.received`,
   `parse_internaldate`) – no `SEARCH SINCE/UNSEEN`, because tagged mails
   must be looked at anyway, and no extra round trip; exact to the second.
   The mail log notes such a mail as `left` with `detail`
   `before_cutoff` or `read` (optionally `:<address>`), worded when shown
   (`LEFT_REASONS`). Tagged mails, replies by reference, answers to
   deployment requests and inquiries already taken in are not affected.
   `untagged_since` follows the switch in `mailboxes.save_mailbox` and
   `aliases.save_address` (`stamp_untagged_since`): switched on with the
   field empty → now; a given moment is kept; switched off → empty.

   With several tags the first counts. A mail already stored – the same
   mail in a second mailbox, or one whose filing failed last time – is
   only filed away. The list entry (`UnknownTagMail`) is keyed by the
   Message-ID, so a mail in two mailboxes is one entry.
3. **Take it over** (`import_mail`, one transaction): the whole mail is
   read, parsed and stored with its attachments. Attachments follow the
   rules for uploads (NFA-007): a forbidden type or one above the size limit
   is left out with a note on the mail. A mail above the limit is read only
   up to 512 KB – enough for its text – and its attachments stay in the
   mailbox, with a note. The stored mail is linked to the
   supplier whose address it names
   (`suppliers.supplier_for(mail_addresses(mail))`, below).
4. **Only then** does the mailbox file the mail away as it is set
   (`ImapMailbox.file_away`, `after_assignment`, EML-006, EML-041): mark as
   read and move into the folder for assigned mails, only mark
   as read (`read`), mark as read and
   delete, or – "keep" – change nothing at all; the fetch does not look at
   it again, because the last UID moves past it. If moving fails, the mail
   stays in the inbox; the next fetch recognises it by its Message-ID
   (EML-007) and only files it away. The last done UID is not advanced
   beyond a mail that failed, so nothing is skipped. The stored mail names
   its mailbox (`ProjectMail.mailbox`).
5. **Tell somebody** (`announce`, EML-023): the project's people get a
   notification. A mail for a finished or cancelled project is still
   stored, with a note saying so (EML-018).

A failed fetch (wrong password, server down) is recorded on its mailbox
with time and text (`_record_outcome`), reported to the operators **once**
per mailbox until its next success ("Mails von Projekte können nicht
abgerufen werden: …"), and shown on the settings page, the start page and
in the self-check, one line per mailbox (EML-032).

### Further addresses of a mailbox (`aliases.py`, EML-047)

One mailbox often receives for several addresses (`support@`, `projekt@`
as aliases of `info@`). For a mail **without** tag and without reference,
step 2 asks `mail.aliases.untagged_rule(mailbox, headers)`:

1. `recipient_addresses(headers)` collects the addresses of
   `Delivered-To`, `X-Original-To`, `To` and `Cc`, in that order (the
   fetch reads the two extra headers), lower case.
2. `alias_for` returns the **first listed** `MailboxAddress` of the
   mailbox found there. The mailbox's own address is checked **last**,
   because many servers write it into `Delivered-To` even for mail sent to
   an alias.
3. Found: its `untagged` decides – `ignore` (left alone), `inquiry`
   (waits under Anfragen, `UnknownTagMail.address` = the alias) or
   `service_case`. Not found: the mailbox's `process_untagged` decides as
   before – unless the own address is listed itself; then its entry
   decides for every mail that matches no other alias.
4. **Service case at once** (`service_case`): the case is made like
   "Als Servicefall anlegen" (PRJ-090: name and customer/contact guessed
   from the sender), with `case_manager` as responsible, and the mail is
   imported into it with `assigned_by` `new_case` – case and mail in one
   transaction; if anything fails, the mail stays an inquiry. The
   responsible person gets one `new_mail` notification.
5. **Automations:** `automations.engine.inquiry_arrived(project=,
   address=)` fires the trigger "mail without tag" (ADM-013) for an
   inquiry and for a mail that became a case (the case is the run's
   project); an automatic answer goes out with the alias as sender.

Tagged mails and replies are assigned by tag and reference whatever
address they went to. **Sending:** `aliases.sender_for(project)` gives a
service case the address with `for_service_cases` as sender – through the
alias's own mailbox if it can send, else through the outgoing mailbox –
and every other project the outgoing mailbox's address. Aliases count as
own addresses: "answer all" leaves them out, and automations never
answer them.

### Inquiries and unknown tags, by hand (`assign_unknown`)

Projects → Inquiries ("Anfragen", `/mail/`, EML-042) lists the waiting
mails – unknown tags and inquiries ("ohne Kennung"), with their mailbox
when there are several. It is a tab under "Projekte"; the
navigation entry "E-Mail" and its box "Abruf" are gone ("Fetch now" and the
state of the fetch are in the settings), and someone with only the module
E-mail reaches the page through "Projekte". A waiting mail is still in the
inbox of its mailbox. Assigning it opens **that** mailbox (else the
`legacy_mailbox`), searches the mail by Message-ID, takes it over like
step 3 and files it away like step 4 of that mailbox. If somebody removed
it from the inbox meanwhile, the error says to forward it with the right
tag instead. "Dismiss" only removes it from the list. The
project number typed for it may also be a former one
(`projects.numbers.project_by_number`, ADM-012).

(PRJ-107) the page is a `core.tables` table with its own row
template (tick boxes, actions) and the column "Empfangsadresse"
(`UnknownTagMail.address`). The number field is a type-ahead
(`data-typeahead-free`, `/mail/projects/?q=`: number or name, only
projects the user may see); without scripts the first word of the text
counts, and the old POST field `project_number` still works. "Als Projekt
anlegen" (untagged inquiries, write access to e-mail) opens the project
form with `?inquiry=` (`mail/inquiries.py`: `project_initial` guesses
subject, customer and contact like PRJ-090; `take_into` imports the mail
in the same transaction as the project – both or neither). The trash
can dismisses one mail without a question; "Ausgewählte von der Liste
nehmen" (and `POST /mail/unknown/dismiss` with `ids`) dismisses several
after a confirmation.

### Answers to deployment requests by mail (`crew_answers.py`, PER-032)

Requirement: crew can answer a deployment request without the
server being reachable from the internet. The link in a request leads to
Rentalars; a reply mail does not – it reaches a mailbox that Rentalars
fetches anyway, from the inside out.

**Sending the request.** `projects.crew.request_deployment` marks the line
"requested" and asks `crew_answers.mailbox_for_request(line)`. That gives a
mailbox when `MailSettings.crew_answers` is not `link`, `answer_mailbox()`
finds one (the system mailbox if it is a fetched correspondence mailbox
with an address, else the outgoing mailbox), the person is active and has
an address, and – for an active account – the mails of
`Kind.DEPLOYMENT_REQUEST` are not switched off. Then:

- the in-app notification still goes to an active account, but with
  `notify(…, email=False)`: the request mail **replaces** the plain
  notification mail;
- `send_request_mail` stores a `CrewRequestMail` with a new token and,
  after the commit, sends `request_message` the way of the system mails
  (system mailbox or `[email]`, logged in the mail log): text and HTML
  (`mail/email/crew_request.txt`, `.html`), `Reply-To` the answer mailbox,
  `Auto-Submitted: auto-generated`, the buttons as `mailto:` links (RFC
  6068: UTF-8, `%20`, `%0D%0A`) with subject
  `Zusage: Stadtfest, Mi 10.03. [RA-E-<token>-JA]` (or `Absage: …
  [RA-E-<token>-NEIN]`) and a body with "Anmerkung: " and a line of
  dashes; the link into Rentalars only with `both`;
- it also goes to a person who cannot log in – every person has an account
  (AUT-026), but one never invited cannot use the link. A failed send is
  logged, never raised: the request stands.

Without such a mailbox there is a notification with
its mail and the link. The tag does **not** use the configurable project
tag prefix; `RA-E` is fixed.

**Taking an answer** (`take_answer(box, uid, size, headers, mailbox)`,
from `fetching._handle` before the project tag):

1. `find_tag(subject)` – no `[RA-E-…-JA|NEIN]`, or a token without
   `CrewRequestMail`: a normal mail, back to the fetch.
2. A mail already logged as `crew_answer` with the same message key (a
   second mailbox, or filing failed last time) is only filed away.
3. The mail is read (at most 512 KB); an automatic reply or a bounce
   (`MailKind` not normal) is a normal mail – so an out-of-office reply
   that quotes the tag starts no loop.
4. In one transaction, with the crew line locked, `sender_reason` comes first (PER-046): the mail
   must come from `asked_address(request_mail)` – `CrewRequestMail.sent_to`, for older requests the
   person's current address – else the reason is `sender`; an `Authentication-Results` header
   with `dmarc=fail` gives `forged`. Either reason ends the check: nothing is recorded, `answered_at`
   stays empty, so the person can still answer from the right address. Then `refusal_reason` mirrors
   the browser answer: `withdrawn` (line deleted, another person planned,
   request taken back, person deactivated), `replaced` or `answered`
   (asked again since – `requested_at` differs or a newer
   `CrewRequestMail` exists), `cancelled` (project cancelled or closed –
   unlike the browser, a cancelled project is refused too), `answered`
   (not "requested" any more), `expired` (the line's end is past).
5. Nothing against it: `_record` calls `crew.answer_deployment` **acting as
   the person's account** (the token stands for the person), so the
   planners' notifications and the history are those of an answer in the
   browser; the note is the text after "Anmerkung:" (or "Note:") up to the
   dashes, quoted text and signature left out, at most 250 characters, from
   the HTML when there is no text part (`note_of`). The history gets
   `crew_line.answered_by_mail` (only from the address asked).
   `answered_at` is set.
6. Either way the person gets a reply (`reply_message`): a confirmation,
   or why nothing was taken over – always to the person's stored address,
   never to the sender, without tag, with `Auto-Submitted: auto-replied`
   and `In-Reply-To`; a person without address gets none. The mail log
   gets `crew_answer` with `detail` `accepted`, `declined` or
   `<answer>:<reason>`, linked to the project; then the mail is filed away
   as the mailbox does with assigned mails (move, delete, keep).

"Ja" or "Nein" written freely is **not** read: a reply quotes the request
with both words, and a wrong answer recorded is worse than none; such a
mail stays a normal mail and reaches the answer mailbox through
`Reply-To`. "Jetzt abrufen" and `fetch_mail` report the number of answers.
Where the answers go is shown with the choice itself:
"Antwort auf Einsatzanfragen" (ADM-015) is the field `crew_answers` of
`core.forms.SystemSettingsForm` on Einstellungen → Firmendaten und
Grundeinstellungen – still stored in `MailSettings.crew_answers`, and
changed there with write access to the settings –, and the mail settings
("Regeln für alle Postfächer") only
name the value with a link. `/api/v1/mail/settings` reads and writes it as
before.

### Reading a mail (`display.py`, EML-027, NFA-050)

The HTML of a mail was written by somebody outside. It is cleaned with
`nh3` (only formatting survives), external pictures are held back and
counted until the reader asks for them (they would tell the sender when the
mail was read), and the result is shown in a sandboxed `iframe` with a
content security policy of its own. Pictures inside the mail (`cid:`) are
served from its stored attachments.

### Sending (`sending.py`, EML-024, EML-025)

Write or answer from the project: the tag is added, an answer carries
`In-Reply-To` and `References`, attachments can be project files, the
packlists and the price overview made at that moment, the
"Einsatzübersicht" (PRJ-081, not ticked by default – the neutral view of
any colleague, `projects.deployment.neutral`, section 10),
the documents stored with the project (PDF and XRechnung, as they are –
DOK-008; a priced one only for those who may see prices) or uploads.
`send_project_mail` sends through the **outgoing mailbox** – refused with
"Sending is not set up" while there is none that can send – with its
address as sender, and stores the mail in the project like a received one,
naming the mailbox; a stored document that went along is marked as sent
(section 10). The stored mail gets a supplier of subrentals
(PRJ-106): the one named by the page "Zumietung bei …" (`?supplier=` on
the compose form), else that of the mail answered
(`suppliers.supplier_from`), else the one whose address is among To and
CC (`supplier_for`). Rentalars never replies to anything on its own (EML-030) –
with one exception: the confirmation of an answer to a
deployment request (above), which goes only to the person's own address.
(An automation may answer a mail without project tag,
ADM-013 – the second exception, protected against loops, section 23.)

**"Crew hinzufügen" and "Kunde hinzufügen"** (EML-043) stand
by the field "To". The addresses are rendered into the page as escaped
JSON; the script adds only those not yet in the field (case-insensitive)
and says in a `role="status"` line what it added; no button without
addresses. `addresses.crew_recipients` takes the crew lines with a person
whose request was not declined, who is active, not anonymised and has an
address, in the order of the plan, each address once – all addresses for
those who may edit the project or read personnel, otherwise only the
released ones (`share_email`, PER-019); a whole project adds the crew of
the parts the writer may read. `addresses.customer_recipient` is the
project's contact, else the whole project's contact (for a part), else the
customer's address.

(`signature.py`, `addresses.py`):

- **The signature** (EML-034) of the settings gets its placeholders –
  `{vorname}`, `{nachname}`, `{position}`, `{email}`, `{telefon}`, `{firma}`
  – filled with the writer's person and the company, escaped, and is
  cleaned once more. A mail with a signature goes out as text and HTML, the
  text derived from the HTML; one without stays text only. The writer can
  leave it off for one mail.
- **The sender** (EML-038) is "Vorname Nachname | Firma" with the address
  of the outgoing mailbox; the sender name of the mail settings only stands in when no
  writer is known.
- **The login** (EML-035): with `smtp_same_login`, the default, SMTP uses
  the user and password of IMAP.
- **CC and BCC** (EML-037): "Reply to all" fills To and CC from the mail
  answered, leaving out the addresses of all mailboxes; BCC
  goes into a `Bcc` header that `smtplib` removes before the mail is sent.
  Suggestions for the address fields come from customers, contacts and
  people the writer may read, from three characters on.

### The mail log (`log.py`, `backends.py`, EML-039)

Every mail that comes in or goes out leaves one `MailLogEntry` – the
envelope, never the text, and the mailbox: the fetch writes one
for each mail it looked at (assigned, unknown tag, inquiry, left in the
inbox), sending from a project one for "sent" or "failed" with the error of
the server, and every system mail Django sends – invitation, password
link, notification, test mail – passes through `LoggingEmailBackend`.
That backend sends through the **system mailbox** when there is
one (`system_mailbox()`, Django's SMTP backend with
`smtp_backend_options`), unless the caller passed a server of its own; a
mail from the default sender then goes out as the name of
`DEFAULT_FROM_EMAIL` with the mailbox's address (`system_sender`).
Without a system mailbox – or when the database cannot be reached – it
hands the mail to the backend configured before (`EMAIL_INNER_BACKEND`). It notes the result either way. Writing the log never stops a
mail. The daily maintenance removes entries after the retention of
the mails, or after 365 days if mails are kept for good. The
log also holds the answers to deployment requests (`crew_answer`, shown
yellow when not taken over), and its search finds a project by its former
number.

**Without a mail server** (EML-048, `mail/server.py`): when
there is no active, complete system mailbox and the inner backend only
writes a log (console, dummy or file – no `host` under `[email]`), the
backend still hands the mail over (developers see it in the log) but
records `not_sent` ("nicht versendet – kein Mailserver eingerichtet")
instead of `sent`, and returns 0 sent. Callers read that:
`notifications.services` leaves `Notification.emailed_at` empty; pages
that send (self-check test mail, invitation on create and resend, the
person form, the crew request) call `warn_without_server(request)`, which
adds the warning with a link to Einstellungen → Postfächer und Signatur;
the API answers with `mail_state()` (`{"sent": false, "reason": …}`); the
self-check names the missing server; the mail settings and the mail log
show a banner.

### The footer of system mails (`footer.py`, EML-045)

Requirement: every mail sent automatically says that Rentalars sent
it, with the company name and the address. Because every system mail
passes `LoggingEmailBackend` – notifications, invitation, password link
(Django's own reset included), deployment requests and the replies to
answers by mail, error reports, the self-check's test mail –, the backend
calls `footer.add_footer(message)` for each message just before sending:
"Diese Nachricht wurde automatisch von Rentalars für <Firmenname>
versendet: <Adresse>" (without a company name the sentence leaves it
out). The text part gets it after the signature separator `-- `
(RFC 3676, so mail programs fold it away when quoting); an HTML body or
alternative gets it as the last paragraph inside `<body>`, the address as
a link. A flag on the message adds it once even if the message is sent
twice. The company is `CompanyProfile.name` (no database: no company);
the address is `[rentalars] url` (`settings.RENTALARS_URL`); the language
is that of the mail, outside a request the installation's.
Correspondence written in a project goes out through `mail.sending` and
smtplib, not the backend, and gets no footer – it carries the writer's
signature. The request mail of PER-032 lost its own line "automatically
sent by Rentalars", which the footer now says.

### Deleting a mailbox (`mailboxes.delete_mailbox`, EML-046)

The requirement: mailboxes can be deleted; without one there is simply no usable mailbox, but the log keeps its entries.
Deleting works as follows:

1. **"Postfach löschen"** (`mail:mailbox_delete`, GET) shows a
   confirmation page built from `deletion_of(mailbox)` – a `Deletion` with
   the counts of mails, log entries and waiting mails, the roles, whether
   answers to deployment requests go there (`crew_answers.answer_mailbox`),
   the possible successors and, if deleting is impossible, why. It works
   without the page script, which is why it is a page and not a
   `data-confirm`.
2. **The sending role** (`_successors`): only an active mailbox that sends
   the correspondence needs a successor, and only while other active
   correspondence mailboxes remain – the rule "exactly one of them sends"
   holds after the deletion as before. With exactly one that can send
   (`can_send`), it takes over by itself; with several, the page asks which
   (field `successor`, API `?successor=`); with none that can send,
   deleting is refused with the reason (enter SMTP server and address of
   one, or switch them off). Without other correspondence mailboxes nobody
   sends any more, and a project can send no mail.
3. **Deleting** (POST): `_keep_name` writes the current name onto mails
   and log entries, the mailbox is deleted – `ProjectMail.mailbox` and
   `MailLogEntry.mailbox` become empty (`SET_NULL`), the waiting mails of
   Projekte → Anfragen go with it (`CASCADE`; on the server they stay) –,
   the successor gets "outgoing" through `save_mailbox`, so its data are
   checked as when set by hand, and `_check_roles` runs once more. The
   other roles simply go: without a system mailbox system mails go
   through `[email]` of the configuration again.
4. **Or only switch off** – "Nur ausschalten" on the same page
   (`switch_off_mailbox`), the box "aktiv" in the form, `PATCH is_active`.

The mail log lists, sorts and searches by the stored `mailbox_name` and
shows "Name (gelöscht)" for a deleted mailbox (`mailbox_label`); a rename
of a living mailbox is carried onto its rows in `save_mailbox`. The API's
`DELETE /mail/mailboxes/{id}` answers 204; a log entry has `mailbox_name` and
`mailbox_deleted`.

### Mails of a supplier (`suppliers.py`, PRJ-106)

A mail of a project belongs to the subrentals of a supplier when it was
written with that supplier. `ProjectMail.supplier` keeps the link:

- **Automatically** when a mail is stored – fetched (`import_mail`) or
  sent (`send_project_mail`): `supplier_for(addresses)` compares the
  addresses of sender, To and CC (not BCC; for a sent mail To and CC)
  with `Supplier.email`, exactly and ignoring case, and links the mail if
  exactly **one** supplier matches. A mail written from the page
  "Zumietung bei …" names its supplier itself, an answer takes that of the
  mail answered (`supplier_from`).
- **By hand** on the page of the mail ("Gehört zu einer Zumietung?",
  `projects:mail_supplier`, the project's suppliers to choose from) and
  through `POST /projects/{id}/mails/{mail}/supplier`; `set_supplier`
  saves, so the change log has it. `None` removes the link.
- **Shown** on the page of the subrental (`mails_with`): the linked mails
  plus mails of the project from or to the supplier's address that are
  linked to nobody yet – the address may have been entered after the mail
  came. Addresses are compared exactly (`max@verleih.example` is not
  `x@verleih.example`): the database narrows with `icontains`, Python checks the
  parsed addresses.

The tag still decides the project (EML-008); the supplier is an additional
link inside it. The API lists mails and files of one supplier with
`?supplier=`.

### Messages with a lock (`locks.py`, EML-055)

*Code: `rentalars/mail/locks.py`, `templatetags/mail_locks.py`,
`mail/views.py` (`mail_lock`), `mail/api.py`, `mail/notes.py`,
`mail/fetching.py`, `mail/forms.py`; templates `mail/_lock*.html`.
`mail/history.py` (the project history), `automations/signals.py`,
`automations/engine.py` (`_communication_text`).
Tests: `tests/unit/test_092_lock.py`, `tests/unit/test_092_review_mail.py`,
`tests/browser/test_092_lock_in_browser.py`, `tests/api/test_mail_api.py`.*

Every `ProjectMail` – mail or note – is `locked` or open. One function
decides what a user may do with the correspondence of a project:
`correspondence_for(rights, user, project)` → `Correspondence(reach, basis,
may_write, may_lock)`; `correspondence_of(request, project)` keeps it on the
project for the request.

1. **The basis** is read access to the project and
   the special right `correspondence_read`, or working on the service case
   (`works_on_case`, AUT-033). With it the reach is `ALL` with the price
   right (`SpecialRight.PRICES`), else `OPEN`; `may_write`
   (`correspondence_write`, or changing the case one works on); `may_lock`
   = `may_write` and the price right.
2. **Without the basis**, a user who reaches the project at least with the
   deployment view and whose person has a **confirmed** crew line there –
   accepted or planned firmly (`CONFIRMED_REQUESTS`, `planned_in`) – gets
   `OPEN`, read only. A line not asked, waiting or declined opens the
   deployment view as before but not the correspondence.
3. **Filtering.** `Correspondence.readable(queryset)` (lists, the thread,
   the search, the subrental page, the summary input) and `may_read(mail)`
   (a single message, its attachments, answering, moving, notes) – a
   message the user may not read answers 404 everywhere, the API included.
   The tab "Korrespondenz" shows when `reads_any`; the AI summary and the
   reply draft only when `reads_all`, since they read every message.
4. **New messages.** `default_lock(project)` reads
   `MailSettings.lock_new_in_projects` / `lock_new_in_cases` for every way a
   message comes in: fetched (`fetching.import_mail`), written
   (`views.compose`), noted (`notes.add_note`), an inquiry taken over, a
   case made from a mail. `answer_lock(answer_to, project)` starts an
   answer to a locked message locked – it quotes it: the initial of the
   tick in `views.compose`, and in the API (`api._wanted_lock`) the value
   when `locked` is left out of `POST …/mails` with `answer_to`
   (`locked: false` takes it off); `answers_locked` (in
   `fetching.import_mail`, or-ed with the default) stores an incoming mail
   locked when its In-Reply-To or References name a locked message of the
   same project. `Correspondence.new_lock(wanted,
   project)` applies the writer's tick ("Mit Schloss", initial = the
   default) – and makes the message open for a writer without the price
   right, who could not read it otherwise. Moving a mail keeps its state.
5. **Setting and taking away** (`POST /projects/<p>/mails/<m>/lock/`,
   `PATCH /api/v1/projects/{id}/mails/{mail}/lock`): only with `may_lock`;
   `set_lock` saves the field (change log of the project) and, when the
   lock goes, `tell_crew` notifies the confirmed crew (`crew_of`) who could
   not read it before – once per message and person (a `NEW_MAIL`
   notification with the same link exists already), in their language.
6. **Notifications** of a new mail go through `readers(mail, users)`, so
   nobody is told of a message they cannot open. **Automations** of
   service cases (`automations.signals` → `engine.case_communication(…,
   locked=True)`) never take the subject of a locked mail into the run:
   `data["text"]` stays empty, `data["locked"]` is set, and
   `_communication_text` writes "Mail von <sender> (mit Schloss)" or
   "Mail gesendet (mit Schloss)" – the value of `{kommunikation}` in the
   texts of notifications and open items, and the title of a notification
   without a title of its own (`case_event_text`).
7. **The project history** (`mail/history.py`, `hide_unreadable`, called
   by `projects.views.project_history` and `GET /projects/{id}/history`):
   the change-log entries of a `ProjectMail` carry its subject as the
   record's name, the events `mail.note_added`, `mail.deleted` and
   `mail.reassigned` in their details. Applied when shown, so older
   entries are covered: who `reads_all` sees everything; otherwise an
   entry about a message still in the project keeps its subject only if
   `may_read(mail)`, one about a message removed or moved away never.
   Everybody else gets `neutral_name` / `neutral_event` – "Nachricht,
   eingegangen am …", "Nachricht, gesendet am …", "Notiz vom …", "Notiz in
   der Korrespondenz vom …", "Nachricht vom … aus der Korrespondenz
   entfernt", "Nachricht von … nach … verschoben" – and the field
   `subject` is dropped from the changes. At most two queries per page:
   the messages named, and for older "note added" events
   (without the note's ID) the notes of the project at the times named.
   The system-wide change log (administration) is not filtered.

The migration `mail 0014_locked_092` added the column with default true
and set the messages of service cases open: nobody reads anything new, and
the case workers keep reading their cases. With the start roles
everybody with "read correspondence" also sees prices; a custom role
without the price right loses the old project messages until they are
opened.

---

## 9. Encrypting and moving the database

*Code: `deploy/encryption.sh`, `deploy/move-database.sh`, `deploy/lib.sh`,
`rentalars/core/management/commands/database_fingerprint.py`. Catalogue:
NFA-066 to NFA-068. For operators: `docs/betrieb/verschluesselung.md`,
`betrieb.md` ("Die Datenbank umziehen").*

Both run as root on the server, not inside the application. Django does
not know whether its tables are encrypted.

### One secret: the recovery key (NFA-067)

```
recovery key  ──┬── encrypts the backups        (*.enc, openssl, AES-256, PBKDF2)
/etc/rentalars/ │
recovery-key    └── = filekey of MariaDB ── unlocks keys.enc ── the key MariaDB
                    /etc/mysql/rentalars-encryption/              encrypts its files with
```

MariaDB's own data-at-rest encryption (`file_key_management`) encrypts
tables, redo log and temporary files. Its key file `keys.enc` is locked
with the recovery key, which is shown once at installation and is to be
kept outside the server. Whoever is root on the server reads the data as
before – MariaDB decrypts transparently – and `openssl` alone decrypts a
backup, so an emergency needs no Rentalars. What the encryption protects
against is a stolen disk, a copied data folder or a backup in wrong hands.

One exception: a backup made in the browser (ADM-010,
`core/backup.py`) is written by the application, which may not read the
recovery key. With encryption switched on it gets a key of its own, in the
same form and the same `openssl` format; that key is shown only to the
person who made the backup, and `rentalars restore … --key-file` or
`openssl` with that key opens it.

### Switching it on afterwards (`rentalars encryption enable`)

MariaDB encrypts existing tables in the background, page by page, under the
same crash-safe bookkeeping as any other change. So the data stays in its
database; what makes it safe is the comparison:

1. A backup of the present state is written and kept.
2. Rentalars stops; `manage database_fingerprint` writes, per table, the
   number of rows and a checksum over all values.
3. MariaDB gets its key and restarts. If it does not come up with it, the
   settings are removed again and everything runs as before.
4. The script waits until `information_schema` reports every table
   encrypted, takes the fingerprint again and compares. Rentalars starts
   only if not one value differs; otherwise it stays stopped and the
   message names the backup of step 1.
5. Existing backups are encrypted, and all future ones.

With a database on another server, encrypting its files is that server's
matter: `enable` encrypts only the backups and reports what it finds there.

### Moving the database (`rentalars move-database`, NFA-068)

The way to move consistently – new database, check, then switch – is the
move to another database, for example an existing MariaDB server with
encrypted storage, or back onto this server:

1. The target is checked before anything changes: reachable, empty, its
   user has all rights on it and **no others**. `root`, and any user with
   rights on the whole server or on a further database, is refused – the
   same check as at installation (NFA-066).
2. A backup is written. Rentalars stops; the data is copied.
3. Fingerprints of old and new database are compared. Only if they are
   equal is the configuration switched (the old one is kept as
   `rentalars.conf.before-move-…`) and Rentalars started.
4. On any failure Rentalars starts again on the old database. The old
   database is never deleted by the script.

---

## 10. Making an invoice

*Code: `rentalars/documents/services.py`, `content.py`, `pdf.py`,
`xrechnung.py`; for a whole project `projects/family_prices.py`.
Catalogue: chapter 5.10, DOK-003 to DOK-008, PRJ-045,
PRJ-046, PRJ-096. Tests: `tests/unit/test_stage5_documents.py`,
`tests/ui/test_document_pages.py`, `tests/api/test_documents_api.py`,
`tests/unit/test_060_documents_parts.py`.*

An invoice is the strictest of the documents: once made it must never
change (DOK-007), its number must come without gaps, and it comes with a
structured electronic invoice (DOK-006) – German businesses have to be able
to receive those since 2025. The
other kinds – order confirmation, delivery note, crew disposition – go the
same way without the parts marked *invoice only*. (Invoices and
cancellations can be switched off altogether – section 27.)

A user on the tab "Documents" of a project chooses "invoice", ticks text
blocks such as the terms of rental, and presses "Make document". The view
checks edit access to the project and – for a priced kind – the right to
see prices, then calls `create_document`, which runs in **one
transaction**:

1. **Can it be made?** (`check_can_make`) An invoice needs a customer, and
   no other invoice of the project that is still valid – one invoice per
   project; a wrong one is cancelled first.
2. **The content** (`build_content`, `content.py`): company data, the
   billing address (the project's chosen one, else the customer's own),
   every group and its lines with quantity, unit, rental days, discount and
   amount, the crew, the surcharges, the totals per tax rate – all from the
   price calculation of section 2, so the invoice says what the planning
   says. *Invoice only:* optional and alternative groups are left out (an
   order confirmation shows them without adding them up). A subrental that
   only covers a shortage is left out, because the customer pays the line
   it covers. The service period is the reservation period of the project.
   Of the ticked text blocks, only those meant for this kind are printed. *Invoice
   only:* the payment terms (the customer's, else those of the company
   profile) and the due date. The texts of the template get their
   placeholders filled (`{project}`, `{due_date}` …).
3. **Can the electronic invoice be made?** *Invoice only:*
   `xrechnung.missing_data` checks the content for what EN 16931 requires –
   company name, address, e-mail address, VAT ID or tax number, the
   customer's billing address. Anything missing stops the invoice here,
   with a message naming it, before a number is taken.
4. **The number** (`NumberRange.allocate("invoice")`, `RE-2027-0001`) is
   taken with a row lock *inside* the transaction. If anything after this
   fails, the counter goes back with everything else: no gap, and two
   users making invoices at the same moment wait for each other. (The
   other kinds have ranges of their own: `AB-`, `LS-`, `CD-`.)
5. **The files.** The content is rendered to a PDF by WeasyPrint
   (`pdf.py`) and its SHA-256 is computed; *invoice only:* the same content
   is written as XRechnung 3.0 in UBL syntax (`xrechnung.build_xml`), with
   the customer's Leitweg-ID or buyer reference as `BuyerReference` (BT-10)
   – a public authority routes the invoice by it –, else the project
   number.
   Positions carry their price for the whole quantity, so rental days and
   scale factors need no rounding; group discounts and flat prices become
   allowances or charges per tax rate.
6. **Store** the `Document` with number, date, totals, due date, the
   content as JSON, both files and the checksum, and write the event
   "document.created" into the project's history. Storing it
   also records the webhook event `document.created` (section 12), and an
   invoice or cancellation starts its hand-over to Lexware Office when the
   settings say so (section 13) – after the transaction, as a task in the
   background; nothing there can stop the invoice.

**A preview** (`services.preview`) runs steps 2 and 5 with "DRAFT" instead
of a number and stores nothing; it counts no number.

**Customer material** (PRJ-096) in step 2: a line marked
`LinePrice.is_customer_material` becomes a `Position` with
`customer_material=True` – quantity, unit, title, the note "Kundeneigenes
Material – wird mitgeführt, ohne Berechnung" (`customer_material_note`),
no unit price and no amount. `Position.counts` is false for it, so it is in
no sum, no tax and no XRechnung. Offer and order confirmation list it where
it stands; an offer of groups only (below) keeps it listed under its group,
so the customer sees that the gear comes along. *Invoice only:* it is left
out (`priced_sections(with_customer_material=False)`). The delivery note
lists it with "Kundeneigenes Material – wird mitgeführt"
(`SimpleRow.customer_material`).

**Cancelling** (`cancel_invoice`, again one transaction): the invoice is
locked; its *stored* content is read back (`content.from_json`), every
quantity and amount negated (`content.negated`), the cancellation gets the
next number of the same range and is stored like any document – the
XRechnung as type 384 referring to the invoice. Then the cancellation's
`cancels` and the invoice's `cancelled_by` are set – besides the note
about sending, the only fields of a stored document that ever change. The
project can then get a new invoice.

**Sending** (DOK-008) goes through the mail of the project (section 8):
the stored PDF and XRechnung are attached as they are, never made anew.
After the mail went out, `mail.sending.note_documents_sent` – called by the
page and the API alike – notes `sent_at` and `sent_to` on every stored
document that was attached (`documents.services.mark_sent`).

**Verifying:** `services.verify(document)` compares the SHA-256 of the
stored PDF with the checksum written when it was made.

### The offer: groups only, validity in days (DOK-013)

The form of an offer has two more fields, and `build_content`, `preview`
and `create_document` take them:

- **"Umfang"** (`detail`): "mit Positionen" (`lines`, as before) or "nur
  Teilgruppen" (`groups`). With `groups`, `content.only_groups()` turns
  every group and subgroup into one row – title, description, discount or
  flat-price note, sum; a group with subgroups keeps a heading "mit
  Untergruppen", the subgroups and "Zwischensumme … mit Untergruppen".
  Lines outside groups, the personnel and the surcharges stay listed, and
  so do optional and alternative lines inside a group – they are not part
  of its sum. The remaining positions are numbered from 1 again and
  alternatives named anew (`name_alternatives`). Totals and taxes are
  computed on the full offer **before**, so they are the same in both
  modes. The stored content is what the PDF shows, and the document
  stores `detail`; the list of documents notes "nur Teilgruppen". Any
  other kind refuses `groups` (`check_detail`; 400 in the API).
- **Validity** as a date (`valid_until`), in days (`validity_days`, 0 to
  3,650, counted from today, the offer's date) or both:
  `offer_valid_until(issued_on, valid_until, validity_days)` accepts
  either, and both only if they name the same day – otherwise the error
  names both dates. The proposal is `default_validity_days()`, the
  `validity_days` of the offer's template (Settings → Dokumentvorlagen →
  Angebot). The browser keeps date and days in step
  with a few lines of script; without script, the field the user changed
  counts (`changed_data`). Offer texts can use `{validity_days}`.

### The deployment view as PDF (PRJ-081)

"Drucken / PDF" on the tab "Überblick" (PRJ-104)
makes the "Einsatzübersicht"
(`documents.deployment`, route `documents:deployment_pdf`, API
`/projects/{id}/deployment/pdf`) with the letterhead and fonts of the
documents and the logo and additional footer of the crew disposition's
template. It is **not** a document: no number, not stored, it shows
"Stand" with date and time; file name `Einsatzuebersicht-<number>.pdf`.
The data come from `projects/deployment.py`, shared with the tab: from the
tab it is exactly the viewer's view (planners see every contact; never a
rate, a price or the customer); attached to a mail it is
`deployment.neutral()` – no "Mein Einsatz", no own times, contact data
only as released (PER-019), because the mail leaves the house.

### A whole project with its parts (PRJ-045, PRJ-046)

Billing happens at the whole project: the customer gets one offer, one
order confirmation and one invoice for the whole festival. The steps
above change in three places.

- **Step 1** – on a part, offer, order confirmation and invoice are
  refused (`part_problem`): "Angebot, Auftragsbestätigung und Rechnung
  entstehen am Gesamtprojekt 2026-0042 – mit allen Teilprojekten." A part
  makes delivery notes (to its own delivery address, with its own
  material) and crew dispositions. On the whole project an invoice is
  also refused while a part still has a valid invoice from before it
  became a part (it would be charged twice). And a priced document of a
  whole project is refused to a user who may not read every part that is
  not cancelled (`check_parts_readable`, PRJ-049; the view and the API
  pass the user's rights); the message names those parts. A preview is
  refused the same way.
- **Step 2** – `build_priced` takes the plannings from
  `family_prices()` (section 2, "The sums of a whole project"): the whole
  project's own positions first, without a heading; then every part that
  is not cancelled and has something to charge, as a block – an opening
  section with "Teilprojekt 2026-0042-1 Bühne Marktplatz,
  10.03.–12.03.2027" and, if set, "Veranstaltungsort: …", the part's
  groups, a closing section with the part's net total. The positions are
  numbered straight through the document; the block subtotals, like the
  group subtotals, are never added up. Lines taken over from another
  part are not charged and so not listed. Net, tax per rate and gross are
  those of `sum_prices`; the service period runs from the first start to
  the last end of all included projects.
- **Step 5** – the XRechnung lists every position flat, as always, with
  the allowances of each group per tax rate, and its totals are the sums
  of step 2, so `LineExtensionAmount`, `TaxExclusiveAmount` and the tax
  per rate agree with the PDF (EN 16931 BR-CO-17). Tested with part
  blocks, discounts in several parts and the cancellation; the KoSIT
  validator 1.5.0 with the XRechnung 3.0 rules accepts both.

A cancellation is built from the stored content as before, blocks
included. The delivery note of a part marks taken-over rows "Übernahme
aus 2026-0042-1 Bühne Marktplatz".

---

## 11. Calendars of the people

*Code: `rentalars/personnel/marks.py`, `calendars.py`, `calendar_client.py`,
`calendar_views.py`, `calendar_api.py`, `availability.py`,
`availability_week.py`; `core/management/commands/run_jobs.py`. Catalogue:
PER-021 to PER-023, PER-030 and PER-031.*

People keep calendars anyway. Rentalars takes their busy times in and puts
their deployments out, without anybody having to type anything twice.

**Painting the own availability** (PER-021). On "Meine Personaldaten" a
person colours days or periods green (available), yellow (with limits,
with a note) or red (not available). `marks.mark_period` works like a
brush: a new colour replaces what was in the period – an older mark is cut
back, split in two or removed –, and the same colour with the same note
next to a mark joins it. Personnel planning sees the colours in "who is free" and
the personnel plan; red, and busy times from a linked calendar, make a
warning at the crew line (section 6).

**Month or week** (PER-030). The availability calendar – "Mein
Bereich → Verfügbarkeit" and the tab "Verfügbarkeit" of a person – shows a
month or a week; the choice is kept in the session (`calendar_views.Place`,
`calendar_place`). `availability_week.week_calendar` lays out the week
like the planning's week grid (opens at 06:00, a line for now): the
availability that counts as bands over its hours, busy times hatched, and
the person's deployments as blocks on the right, framed red where they lie
in a red period; projects the reader may not open show as "Funktion ·
eingeplant". Two queries, whatever is entered. The heads of the days carry
the colour of the month cell and are the buttons for choosing days.

**Reading the linked calendars** (PER-022; several, PER-031). A
person – or personnel planning for them – links up to ten ICS calendars,
each with an optional name (`calendars.add_feed`; `remove_feed` removes
one with its busy times). `run_due` reads every calendar that was not read
for 30 minutes, each on its own (`read_calendar`); "Jetzt lesen" reads all
of a person's (`read_feeds(force=True)`). One reading:

1. The address – usually the private ICS link of a Google, Outlook or
   iCloud calendar – is fetched by `calendar_client.fetch_calendar`: only
   http or https, 15 seconds without an answer at most, 5 MB at most.
   `_claim_feed` marks it as being read, so two runs never read the same
   calendar at once. (NFA-071, NFA-072, from a code review)
   every request goes through `core.network.open_url`: the host is
   resolved and checked, internal targets are refused unless `[network]
   allow_internal` allows them, the connection goes to the checked address;
   redirects are followed by hand (`_KeepRedirects`, at most five), each
   target checked again; credentials (CalDAV) go only to exactly the same
   scheme, host and port, except iCloud's partition hosts
   (`CREDENTIAL_PARTNERS`); an address on another host named in a server's
   answer is not contacted, and the calendar found is checked before it is
   stored ([architecture.md](architecture.md), "Outbound connections to
   user-entered addresses").
2. `busy_periods` reads the appointments of the past month and the coming
   half year, unfolds repeating ones and keeps the busy ones: free and
   cancelled appointments are left out, and so are all titles.
3. The marks **of this calendar** (`AvailabilityMark.feed`) are replaced as
   a whole by the new ones (at most 3,000), with the calendar's row locked;
   `feed_uid` is prefixed with the calendar's ID, because a UID is unique
   only within its calendar. The busy times of all calendars together are
   one layer, the union of each calendar's last good reading: a failure
   keeps that calendar's old marks, notes the error and counts the
   failures on the calendar, and leaves the others alone. After six
   failures in a row the person is told once, with the calendar's name
   (`calendar_problem`). Others see a calendar's name and server, never its
   address.

**Writing the deployments** (PER-023) – the crew lines of the person from
60 days ago on, not in cancelled projects and not declined
(`deployment_lines`), with what the person sees of them anyway (AUT-023): job
function, project number and name, place, meeting point, times, note for
the crew; no customer, no prices.

- As a file and as a **subscription link** `/calendar-feed/<pk>/<token>.ics`
  that calendar programs read without a login; the token is compared in
  constant time, too many wrong links from one client (by its
  real address, `feed_failures_key`) and too many readings of one link
  wait (429), an unchanged calendar is answered with 304.
- Into a **CalDAV calendar**, for servers that phones cannot reach. A change
  of a crew line marks its people (`caldav_dirty`, through a signal); the
  next run of the minute timer compares, per person, the events that should
  be there with what `CalendarPush` says the server has: a new one is
  `PUT` with `If-None-Match: *`, a changed one with `If-Match`, a gone one
  is deleted. On the first contact `find_collection` finds the calendar
  "Rentalars" of the account, or creates it.

**When it runs.** `run_jobs`, started every minute by
`rentalars-jobs.timer`, calls `run_due()` after the waiting tasks: each
linked calendar not read for 30 minutes, CalDAV calendars that are marked or
were not compared for 30 minutes; after 40 seconds it starts nothing new,
and the rest is due the next minute. `run_due` never raises. By hand:
`manage.py sync_calendars` for what is due, `--person ID` for one person
at once; on "Meine Personaldaten", "Jetzt lesen" does the same for the
own calendars. The feed names its refresh interval
`X-PUBLISHED-TTL` as a duration (`PT30M`; a bare `timedelta` was written
`0:30:00`, which calendar programs ignored).

### Calendar links of products, models and items (VFG-040)

*Code: `rentalars/schedule/models.py` (`CalendarLink`),
`calendar_links.py`, `calendar_link_views.py`, `calendar_link_api.py`,
`templatetags/calendar_links.py`, `timelines.py` (`item_events`). Tests:
`tests/unit/test_093_calendar_links.py`,
`tests/browser/test_093_calendar_links_in_browser.py`.*

The same idea as the subscription link of a person, for the bookings of
material.

1. **Who.** `may_see(rights, kind)`: read access to the module of the
   record (`products` for a product, `material` for a model or an item),
   the special right `availability` (AUT-032) and read access to *every*
   project (`level_everywhere(PROJECTS) >= READ`, AUT-016) – the feed names
   projects to anyone with the address, so it must not show a reader more
   than his pages would. `may_manage` adds write access to the module. The
   box (`calendar_link_box`) shows only for `may_see`, its buttons only for
   `may_manage`; the API checks the same per method (GET read, POST and
   DELETE write). The **address** itself (box and API `url`) only for
   `may_manage`: it works without login, and a reader who
   copied it could not end it; a reader sees that a link is active, when
   and by whom it was created and what it shows.
2. **Create, renew, deactivate.** `create_link` refuses a deactivated
   product, a product without stock of its own (`tracks_stock`) and an
   archived item (`unavailable_reason`); it locks the record's row
   (`select_for_update().get_or_create`), sets a new
   `secrets.token_urlsafe(32)` – the old address dies at once – and
   records the event `calendar_link.created` or `.renewed` on the record.
   `deactivate_link` empties the token (the row stays) and records
   `.deactivated`. A second "create" from a stale page keeps the address
   ("A calendar link is already active").
3. **Ends with the record.** A `post_save` signal on `Product` and
   `MaterialItem` (`subject_archived`, connected in `schedule/apps.py`)
   empties the token when the product is deactivated or the item retired,
   sold or lost, with the event `calendar_link.ended`; `link_of` and
   `link_for_token` refuse such a record anyway. Reactivating needs a new
   link. Deleting the record deletes the row (`CASCADE`).
4. **Reading** `GET /calendar-feed/<kind>/<pk>/<token>.ics`
   (`calendar_link_feed`, public, `require_safe`): a client with too many
   failures waits (429, `FEED_FAILURES_PER_ADDRESS`, counted together with
   the person feeds under `personnel.calendar_views.feed_failures_key` –
   the client address as the login reads it, `X-Forwarded-For` behind
   NGINX, nothing counted without one); `link_for_token` loads the link of the
   record and compares the token with `hmac.compare_digest` also when there
   is none, so the time tells nothing; a link read more often than
   `FEED_READINGS_PER_LINK` per window waits too.
5. **The appointments** (`appointments_of`), from 90 days ago
   (`FEED_PAST`) to 730 days ahead (`FEED_FUTURE`), in a fixed number of
   queries:
   - product and model: `AvailabilityEngine.collect_demands` for the
     product (a model: its default product and the products of its items'
     overrides, not archived) – lines of projects with an option or a
     confirmation, also through kits and containers, their periods with
     the buffers, and the blocked items; a soft demand is `TENTATIVE`; a
     sale (end `FAR_FUTURE`) is one day at its start and is left out if it
     began before the window;
   - item: `timelines.item_events` – the events of its timeline
     (allocation issued or chosen, wish on a line, travelling with its
     container, taken out, blocked) with their exact periods, and its due
     inspections (an overdue one today).
   A period from local midnight to midnight becomes whole days. Each event
   has the UID `rentalars-<kind><pk>-<key>@<host>`, the key naming the
   record behind it (`line-<id>-<product>-<via>`, `allocation-<id>` …), so
   a calendar program updates instead of duplicating; segments of one line
   count up. Summary and description name the project
   (`family_labels.project_label`), status and quantity, with a link to
   the project page – never prices, customers, contacts or places.
6. **The answer** (`calendar_of`) is written in the installation's
   language (`translation.override(settings.LANGUAGE_CODE)`), with
   `REFRESH-INTERVAL` and `X-PUBLISHED-TTL` of 30 minutes. The ETag is a
   hash of the calendar and its events *without* `DTSTAMP`, so an
   unchanged calendar answers 304; `Cache-Control: private, max-age=900`,
   `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`.

The token is in `core.export.SECRET_FIELDS` and never in the change log
(`CalendarLink` is no `AuditedModel`); the events on the record say who
created, renewed or deactivated it.

---

## 12. Webhooks

*Code: `rentalars/api/webhooks.py`, `webhook_events.py`, `webhook_api.py`,
`webhook_views.py`; `core/management/commands/run_jobs.py`. Catalogue:
API-012. Tests: `tests/unit/test_060_webhooks.py`,
`tests/ui/test_060_webhooks_pages.py`, `tests/api/test_060_webhooks_api.py`.*

A webhook is the address of another system – an ERP, a chat, an
automation tool such as n8n – and a list of events. When one of them
happens in Rentalars, that system gets a signed `POST` at once and never
has to ask again and again.

**Recording** – in the transaction of the change:

1. **The event is noticed.** Creating a project and changing its status
   are heard through `post_save` on `Project` – also the automatic "out"
   and "returned" that packing sets; the status before the save is read
   from the change log's snapshot (`_audit_before`). Storing a document is
   heard through `post_save` on `Document`. Packing (issue, issue taken
   back, material back, handover between subprojects) and time tracking
   (approval, approval taken back) call `record` in their services.
2. **`record`** looks for the active webhooks that want the event, builds
   the event's `data` once (`webhook_events.build` – a compact subset of
   the API representation, never prices, costs or rates) and writes one
   `WebhookDelivery` per webhook: waiting, next attempt now. The insert
   runs in a savepoint of the change's own transaction. A change that is
   rolled back leaves no delivery; a delivery is never lost because the
   process ended right after the commit; and an error while recording is
   logged and lets the change go on.

**Delivering** – `run_jobs`, started every minute by
`rentalars-jobs.timer`, calls `run_due()` after the tasks and the
calendars:

1. It takes the deliveries that are due – waiting, next attempt passed,
   webhook switched on –, the oldest first, at most 200, and starts nothing
   new after 30 seconds.
2. Each is **claimed** first: its next attempt moves ten minutes ahead,
   with a condition on the old value. A second run at the same time finds
   it taken; a run that dies while sending leaves it to be tried again in
   ten minutes.
3. The body is the envelope `{"version": 1, "id", "event", "timestamp",
   "data"}`, serialised once; the signature is the HMAC-SHA256 of exactly
   these bytes with the webhook's secret:

   ```
   POST /hooks/rentalars HTTP/1.1
   Content-Type: application/json
   User-Agent: Rentalars/1.0.0 (webhook)
   X-Rentalars-Event: project.status_changed
   X-Rentalars-Delivery: 3f2b8f4e-…            the same on every attempt
   X-Rentalars-Signature: sha256=9c1e…

   {"version":1,"id":"3f2b8f4e-…","event":"project.status_changed",
    "timestamp":"2027-03-01T08:00:00+01:00","data":{"project":{…},
    "old_status":"confirmed","new_status":"out"}}
   ```

   The receiver computes the HMAC itself, compares in constant time, and
   takes a delivery ID it has seen once.
4. **Sending** (`post`): 10 seconds per step, 20 in all; redirects are
   not followed; at most 64 KB of the answer are read, the first 1,000
   characters kept with status code and duration. The proxy of the
   environment is used, except for addresses on the machine itself.
   (NFA-071) the request goes through `core.network.open_url`
   with `_NoRedirects`: an internal receiver is reached only with
   `[network] allow_internal`, otherwise the delivery fails with "Die
   Adresse führt in ein internes Netz …" and counts as a failure like any
   other (ten in a row switch the webhook off); `validate_webhook_url`
   refuses an internal IP address or `localhost` already when entered.
5. **The outcome.** A 2xx answer: delivered, and the webhook's count of
   failures is set back to 0. Anything else: tried again after 1 minute,
   5 minutes, 30 minutes, 2 hours and 12 hours – six attempts within
   about 15 hours –, then failed for good. While one delivery of a
   webhook fails, its other deliveries wait for the next run, so one dead
   receiver cannot use up the run.
6. **Switching off.** Every delivery that failed for good counts;
   at ten in a row the webhook is switched off – in the change log by
   `system:jobs` – and everybody with write access to the settings is
   notified ("Webhook abgeschaltet: …", kind "error of the application").
   Its waiting deliveries stay and go out once somebody switches it on
   again; switching it on sets the count back. While it is off, nothing
   new is recorded for it.

`run_due` never raises: a failure of the webhooks stops neither the tasks
in the background nor the calendars.

**By hand.** "Test senden" sends a `ping` at once and shows the answer;
"Erneut senden" sends a failed delivery once more, with its ID. Both try
once, inside the request, do not count towards switching off and work on
a switched-off webhook too; an answer 2xx sets the count back.

**Keeping.** The daily maintenance deletes deliveries older than 30 days
(`delete_old_deliveries`).

---

## 13. Handing invoices to the accounting

*Code: `rentalars/documents/lexware.py`, `datev.py`, `accounting_views.py`,
`accounting_forms.py`, `accounting_api.py`, `models.py`
(`AccountingSettings`, `LexwareTransfer`). Catalogue: DOK-011, DOK-012
. Tests: `tests/unit/test_060_accounting.py`,
`tests/ui/test_060_accounting_pages.py`,
`tests/api/test_060_accounting_api.py`; `tests/lexware_fake.py` plays
Lexware Office.*

An invoice made in Rentalars already has its number, its PDF and its
XRechnung (section 10). The bookkeeping gets it in one of two ways – or
both: one by one into Lexware Office, or the invoices of a period as a
file for the tax adviser's DATEV. (Both are hidden and
refused while "Rentalars als Buchhaltungsprogramm verwenden" is off; hand-overs
already queued still finish – section 27.)

### Lexware Office (DOK-011)

**Starting.** By hand, "An Lexware Office übergeben" at an invoice or
cancellation on the tab "Dokumente" (`request_transfer`) – for whoever
may make it, or may change the settings, and sees prices. Or by itself:
with "sofort übergeben" switched on, `create_document` and the
cancellation call `transfer_automatically` right after the document is
stored; a problem there is logged and never stops the invoice. Either
way a `LexwareTransfer` row is taken or made for the document (refused if
it is in Lexware Office already, or on the way and not older than 15
minutes) and a task in the background of kind `lexware` is started.

**The task** (`run_transfer_job` → `perform_transfer`), with the API key
decrypted from the settings:

1. **Claim** the transfer (waiting or failed, or running for more than 15
   minutes); one attempt per document at a time.
2. **Is the voucher there already?** Unless the transfer knows its ID
   from an earlier attempt, `GET /v1/voucherlist` is asked for the
   document number. A voucher found with the same amount is taken; one
   with another amount stops the transfer (error code
   `voucher_conflict`: "Rentalars legt keinen zweiten an").
3. **The contact**, when a voucher is to be made. With "auf den
   Sammelkunden buchen" none: `useCollectiveContact`. Otherwise the
   contact ID kept on the customer (`lexware_contact_id`), else `GET
   /v1/contacts?number=…&customer=true` with the customer number; a
   contact found is taken only if its name matches the customer's. If it
   does not, the transfer stops with the error code `contact_conflict`,
   and the document offers "Als neuen Kontakt übergeben". If none is
   found – or a new one was asked for – `POST /v1/contacts` creates one
   with name, billing address, e-mail address, phone, VAT ID and tax
   number; Lexware Office gives it a number of its own. The ID is kept on
   the customer.
4. **The voucher**: `POST /v1/vouchers`, type `salesinvoice` (a
   cancellation `salescreditnote`, amounts positive), the number and date
   of Rentalars, the end of the service period as `shippingDate`, the due
   date, `taxType` `net` with one item per tax rate – net, tax, rate and
   posting category from the stored document's amounts per tax rate, the
   same as in the PDF and the XRechnung. The voucher ID is stored at
   once.
5. **The PDF**: `POST /v1/vouchers/{id}/files`, unless it was uploaded
   before.
6. **Done**: state "handed over", time noted; the event
   `document.transferred` in the project's history.

Every request goes to `https://api.lexware.io` with `Authorization:
Bearer …`, at most two per second; after a 429 it is asked again after 1,
2 and 4 seconds. Redirects are not followed, 20 seconds is the timeout.
An error marks the transfer as failed with a text and an error code
(`auth`, `rate_limit`, `rejected`, `unreachable`, `server`, …). Whoever
started a transfer by hand is told the result like any task in the
background; an automatic one tells the maker of the document only if it
fails. Failed transfers are listed on the page Settings → Accounting with
"Erneut übergeben"; an attempt after an error only does what is missing.

"Verbindung prüfen" asks `/v1/profile` and `/v1/posting-categories` and
keeps the name of the organisation and the income categories for the
choice of a category per tax rate.

### DATEV (DOK-012)

On the page Settings → Accounting a period is chosen – the last month by
default –, and two downloads are offered:

1. **Buchungsstapel** (`datev.bookings_file`). Every invoice and
   cancellation dated in the period, read from its stored content; a
   cancelled invoice and its cancellation are two documents, each in the
   period of its date. The period must lie within one fiscal year. Per
   document and revenue account one line: the gross amount of its tax
   rate, "S" (debit on the debitor) for an invoice, "H" for a
   cancellation; account = the debitor, contra account = the revenue
   account of the rate; Belegdatum `TTMM`, Belegfeld 1 the document
   number, the booking text title, number and recipient. No tax key: the
   revenue accounts of SKR 03/04 for 19 % and 7 % are automatic accounts.
   A 0 % booking to a customer with an EU VAT ID fills "EU-Land u.
   UStID".
2. **Debitoren** (`datev.debitors_file`) – the customers of those
   invoices as debitor accounts, with name, address, VAT ID, e-mail
   address, phone, customer number and payment terms as they are now in
   Rentalars. With one collective debitor account there is nothing to
   export, and the page says so.

Both files have the header line "EXTF" (version 700) with consultant and
client number, the start of the fiscal year, the length of the general
ledger accounts and the period, then the column names and the rows, in
Windows-1252 with CRLF and `;`; neither is locked (Festschreibung 0).

The export stops with a message, before anything is written, when the
consultant or client number is missing, a tax rate has no revenue
account, a customer number is not made of digits (with debitor accounts
per customer), or a debitor account would fall outside the range DATEV
takes as debitors (10000 to 69999 with accounts of four digits). The
download needs read access to the settings and the price right, and it
is noted in the access log like every CSV file.

---

## 14. Timeline and personnel plan

*Code: `rentalars/schedule/services.py`, `views.py`, `timelines.py`,
`course_timeline.py`; `availability/services.py`
(`utilization_in_periods`); templates `schedule/_zoom.html`, `_tabs.html`,
`timeline.html`, `products.html`, `personnel.html`, `_course_timeline.html`.
Catalogue: VFG-012 ff., VFG-022, VFG-023, VFG-024, VFG-025, PRJ-092, VFG-027 to VFG-029, VFG-030,
PRJ-103 and a fix of VFG-023. Tests: `tests/unit/test_062_planning.py`,
`tests/ui/test_062_planning_pages.py`, `tests/unit/test_063_phases.py`,
`tests/{unit,ui,api,browser}/test_070_planning*`,
`tests/{unit,ui,api,browser}/test_071_planning*`. The bars of
the view "Tage" and of the project's timeline can be dragged (VFG-026,
section 27); service cases are in no timeline (PRJ-090, section 21).*

**Tabs and defaults** (VFG-028). The tabs of "Planung" are, in
this order, Kalender, Zeitstrahl, Materialauslastung, Personalplan, Fehlbestände (`schedule/_tabs.html`). The
calendar opens on the week (`views.DEFAULT_CALENDAR_VIEW`), "Woche" comes
before "Monat", and the choice is kept in the session (`calendar_view`);
an address with `?month=` or `?week=` but no `view` shows what it names,
so old links keep working. Zeitstrahl, Materialauslastung and Personalplan
share one span (`views._scale`): an address without `days` and `weeks`
shows days in hours – as many as chosen last in the session
(`schedule_days`), else `DEFAULT_DAYS` (4, was 3) –, unless the session
says weeks (`schedule_span`, "days" or "weeks"). `_remember` writes the
session only when a choice changes. The link "Wochen" carries `weeks`
explicitly. The API defaults are unchanged.

**Days or weeks** (VFG-024,; the utilization too).
The project timeline, the personnel plan and, (VFG-029), the
Materialauslastung show either "Wochen" (one column per day, 1 to 12
weeks, as before) or "Tage": 1 to 10 days (`MIN_DAYS`, `MAX_DAYS`) with
columns of hours. `hours_per_column(days)` takes the finest of
`HOUR_STEPS` (1, 2, 3, 6 hours) that keeps at most 40 columns in view
(`MAX_VISIBLE_COLUMNS`):

| Days | 1 | 2–3 | 4–5 | 6–10 |
|---|---|---|---|---|
| Hours per column | 1 | 2 | 3 | 6 |

`scale_from_request` reads `days=1..10`; `views._scale` remembers the last
number in the session (`schedule_days`) and offers it when switching to
days, otherwise `DEFAULT_DAYS` (4); other values
of `days` mean weeks, so old addresses with `?days=1|2|3` keep working. The
API keeps its own range (`days` 1 to 84 on `/calendar`, `/utilization`,
`/personnel-plan`). The timelines of a product, model, item or person keep
weeks only.

**The utilization in hours** (VFG-029).
`availability.services.utilization_in_periods(product_ids, periods)` gives
the peak of the firm reservations (and what options add) per hour column,
with the same queries as per day (`utilization`), whatever the number of
columns. `schedule.services.utilization_rows` joins neighbouring columns
with equal figures into one `LoadRun` cell (`grid-column`, the period as
its title), so ten days in six-hour columns stay a small page. The search
forms sit outside the region that reloads while moving sideways, so the
type-ahead keeps working; their hidden span fields come along through
`form=`.

**Colours of deployments** (VFG-027). The personnel plan had
no visible colours: bars showed their status only as a 3 px left edge on a
background almost that of the panel, and a project in status "Anfrage" had
no edge colour at all. `services.crew_bar_css(line)` now gives a
deployment bar `crew status-<project status>` (plus `requested` while the
person has not answered): firm (orange) from "confirmed" on – also out,
returned and closed –, option yellow, inquiry grey (a new legend entry),
"angefragt" a paler fill with a dashed band. It is used in the personnel
plan and on the person's timeline; the API row `kind` of the person
timeline starts with `crew ` as well. Every status bar of a timeline gets a
30 % tint and a 6 px band (special bars such as containers and takeovers
keep their look), the text stays in the normal text colour (contrast 5:1
or better in both themes); availability and absence bars got stronger
tints and hatching; bars and legend are taller. The project timeline keeps
the calendar's project colours, now filled.

**Bars that end visibly** (VFG-030). The requirement: in the
timelines the grey areas of projects must visibly end against the grey
background, and text must not run over them. The tint of an inquiry (grey), or of "out" in the light theme,
hardly differs from the panel, so every bar of a project status or a deployment has
a 1 px frame in the colour of its band (`--status-edge`); grey takes the
stronger `--ink-soft` and yellow `--yellow-ink`, so every frame reaches
3:1 against the panel in both themes (WCAG 1.4.11 – the browser test
measures it). A requested deployment keeps a dashed band and a solid
frame. Phases, absences, blocks and availability are framed too. A
cancelled bar is not half-transparent (the frame would lose its
contrast) but pale and struck through. Labels end with "…" at the end of
their bar (`.tl-bar { overflow: clip; text-overflow: ellipsis }`, not
`hidden`, so the bar does not become a scroll container and the text of a
bar that began left of the view still sticks next to the names); every
bar's `title` holds the whole text. The block for planning in
`app.css` adds no colour token.

**Bars at their real times** (the phase bug). A bar once
filled every column it touched: a setup from 14:00 to 20:00 filled the
whole day, 22:00 to 02:00 two days, 07:30 to 08:15 the two-hour columns
06–10. `Scale.bar` gives each `Bar` its columns plus `lead` and `trail` –
the parts of the first and last column before the start and after the end,
as fractions of the bar's columns – and `Bar.style` turns them into
percentage margins (`--fill` lets the style sheet shrink the padding of a
short bar). A phase from 14:00 to 20:00 in a day column has a lead of
14/24 and a trail of 4/24. This holds for every bar of the project
timeline and the personnel plan, in days and in weeks; whole-day periods
look as before. The hour step only sets headings and grid lines.

**Phases outside the rental period** (PRJ-092). A phase may lie
outside its project's period – "Planungen und Besprechungen" weeks before,
"Nachbereitung" after the material is back. The month and week calendars
showed such phases already; the project timeline and the API `/calendar`
listed a project only when its own period touched the span, so its
meeting was missing there. Both now select with
`services.projects_or_phases_in(projects, start, end)`: the period touches
the span, or an `Exists` over the project's phases does – one subquery, no
further query. The phase is drawn in its project's row.

**The person's timeline** (PER-020) has the rows Einsätze, Verfügbarkeit,
Qualifikationen. The row "availability" reads
`effective_periods` (PER-027) plus absences, like the personnel plan. The API row `kind` is `"availability"` instead of `"absence"`.

**Utilization** (VFG-025): the search field suggests products
while typing (`/products/suggest/?exclude_kind=…` with every kind without
stock – kit, service, subrental, surcharge and, incidental);
a chosen suggestion sends `product=<id>` and shows exactly that product,
typed text with Enter searches. Category and search are separate
forms, so choosing a category afterwards shows the whole category again.
Every type-ahead field carries the combobox roles (`setUpTypeahead`).

**Everybody in the personnel plan** (VFG-023). The requirement: with the tick "Only people with deployments or absences" off, every person is shown. `services.people_in_plan(people, start, end, busy_only=…)` returns every
active person given when the box is unticked, and with it only those with
a deployment or absence in the span (`busy_people_filter`); the view and
`GET /api/v1/personnel-plan` (`busy=1`) call it alike. The person field of
the crew forms and "Wer ist frei?" keep offering only people with the job
function (PER-025).

**Further changes** (VFG-031 to VFG-034, PER-039; tests
`tests/{unit,ui,api,browser}/test_081_plan*`, `test_081_notify*`):

- **Exact times on hover** (VFG-032): every availability, absence and
  deployment bar of the personnel plan has a `title` and a hidden text
  with its times ("Mi 10.03., 9:00 Uhr bis 13:30 Uhr", "… bis 24:00 Uhr",
  "Mi 10.03., ganztägig").
- **Conflicts filled red** (VFG-032, VFG-023): `services` marks a
  deployment that overlaps another, an absence or "nicht verfügbar" with
  `is-conflict`, and the style sheet fills it red – no other kind is
  filled red; the band at its start keeps the status colour. Availability
  and absence bars are not filled; their "!" and hover name the conflict.
  All availability kinds are hatched. The same marking in the week of the
  availability calendar and, new, on the person's timeline
  (`timelines.py`; the API `kind` carries `is-conflict`). Planung →
  Zeitstrahl and the project timeline show no conflicts (they never did;
  it would cost queries).
- **Dragging deployments** (VFG-031): a fourth kind of move, `crew`, in
  `schedule/moves.py`, reusing the drag code, keyboard handling, dialog
  and API of VFG-026 (section 27): `what=crew` with `crew_line` on
  `reschedule/preview` and `reschedule`. Saving goes through
  `crew.update_crew_line`, like the crew dialog – the planned hours follow
  the period when they were the suggested ones, a line asked or accepted
  is asked again (PER-034); the answer names `planned_hours_before` and
  `planned_hours_after`, the dialog the warnings at the new times. Only
  the deployment moves; its phase and project keep their times. Same
  rights as VFG-026, only in "Tage"; not onto another person.
- **Wider scroll range** (VFG-033): the hour views (Zeitstrahl,
  Personalplan, Materialauslastung, the project timeline) load two spans
  before and two after the chosen one; the week
  views and the day-column timelines of a product or person are
  unchanged.
- **Hourly lines** (VFG-033): a container query on the panel draws a line
  per hour where an hour is at least 8 px wide – up to 7 days at 1920 px
  of window, 4 days at 1280 px – also inside columns of 2, 3 or 6 hours
  (`_scale_panel_attrs.html`).
- **Marking in the availability week** (PER-039, `static/js/app.js`
  block "PER-039", `_availability_week.html`): pointer drag in 15-minute
  steps (on a touch screen tap start, then end, in 30-minute steps), over
  several days with the same hours each day; the range is written into
  the existing form (days, "Nur zu bestimmten Uhrzeiten", from, until), a
  live line states it in words, and the colour buttons save as before. No
  new data; a night across midnight is typed into the form.
- **Planung → Wiedervorlagen** (VFG-034, `schedule/follow_ups.py`): the
  last tab; a `core.tables` table over projects and service cases with a
  follow-up – Tag, Uhrzeit, Für, Notiz, Projekt, Art, Status (Kunde,
  Zuständig optional), filters Für (alle/für mich), Nur fällige, Von/Bis.
  Who sees what: with the customer right (AUT-023) every follow-up of the
  visible projects, else only one's own. "Verschieben" opens the
  project's follow-up dialog with `next` back to the table; "Erledigt" is
  a button of one shared form. Both only with edit access. In
  `core.trail.START_PAGES`.

### The timeline of one project (`course_timeline.py`, PRJ-103)

The requirement: the tab "Zeitplanung" also shows a timeline like the menu entry "Planung", with the phases and the assignment of personnel. The tab "Zeitplanung" (`course_views.course_page`)
shows, below the open items and above the phases,
`templates/schedule/_course_timeline.html` with one row per thing
(`CourseRow`, `course_rows`):

| Row (`kind`) | Bars |
|---|---|
| `period` | the rental period, in the colour of the project status |
| `event` | the event period, if the project has one |
| `phase` | each phase in a row of its own, with its times on the bar |
| `person` | one row per planned person: a bar per crew line, labelled with the job function, coloured as in the personnel plan (`crew_bar_css`: firm, option, inquiry; requested paler with a dashed band); a declined request red, hatched and struck through (new) |
| `open` | one row per job function with open places, yellow and hatched |

The first row of the phases and of the crew starts a group (a line above
it). A row whose period lies outside the shown days stays, without a bar.
Tooltips name person, function, period and request status (`_crew_title`);
names link to the person only for users who may read personnel.
`crew_legend` explains the crew colours.

**The columns** are those of Planung → Zeitstrahl (`services.Scale`,
`scale_from_request`, `_zoom.html`): 1 to 10 days in hour columns or 1 to
12 weeks of days, with "Tage", "Wochen", "früher", "später", "Von" and the
loading of further days while scrolling sideways. Without `from`, `days`
and `weeks` in the address the timeline opens on the rental period
(`default_span`): up to ten days in hour columns, a longer project in
weeks from its first day; an address with `from` only keeps that kind of
columns (`course_scale`). Unlike the planning pages nothing is kept in the
session – the project decides what is worth seeing.

**No query of its own:** `course_rows` builds everything from the phases
and crew lines the page loads anyway (PRJ-080, `crew_by_phase`); a UI test
holds the query count of the page fixed whatever the number of phases and
crew lines. (Three more queries for the checks below.)

**Crew like the personnel plan (VFG-035).** The crew rows use
the personnel plan's bars (`templates/schedule/_course_bars.html`, the
same CSS): firm, option, inquiry in their colours, requested dashed;
**conflicts filled red** – overlap with another line of the person, also
in other projects, an absence, or "nicht verfügbar" – with "!" before the
name and the reason as hidden text; these checks cost **3 queries whatever
the crew size** (tested). Conflicts are shown to everyone who can open the
page, because the planning shows these warnings anyway. With the right to
read personnel, a hatched availability row stands above each person's
deployments, as in the personnel plan. Hovering a crew bar names the exact
times; the legend is the personnel plan's plus "abgesagt" and "offen".

**Changing the crew of a phase (PRJ-110).** On the phases
(`_phase_crew_list.html`), whoever may plan crew gets per line a pencil
that opens the planning's crew dialog (`projects:crew_edit` with
`?from=course`, a page of its own without the page script) – fill an open
place with a person, change person, job function or times – plus
"anfragen"/"erneut anfragen", "eintragen: zugesagt"/"abgesagt" and the bin,
all the existing views of `crew_views.py`. `crew_warnings` (overlap,
absence, availability, PRJ-022) show at every line and again as messages
after saving. After a change the response carries `HX-Refresh`, so the
page reloads in place; a redirect to `…#phases` on the same page would
only jump to the anchor.

### Phases and follow-ups in the calendar (VFG-039)

`schedule.views.calendar_options(request)` decides two switches: the
address (`?phases=0|1`, `?follow_ups=0|1`; the form sends a hidden `0`
before each tick box, so the last value counts), else what the user chose
last (the session, like the calendar view), else `CALENDAR_OPTIONS` –
phases on, follow-ups off. A choice in the address is remembered.
`week_grid` and `month_weeks` take `phases` and `follow_ups` – the
queryset of `follow_ups.visible_follow_ups(rights, user)`, the same as the
tab "Wiedervorlagen": every follow-up of the visible projects for whoever
may know whose projects they are (AUT-023), else only one's own. A
follow-up with a time stands in the hour grid of the week, one without in
the all-day strip, in the month below its day (`follow_ups_of`), with
number and note, linking to the project or case; the legend names it only
when it is shown.

---

## 15. The head of a project and the tab "Dokumente"

*Code: `rentalars/projects/templatetags/project_actions.py`,
`templates/projects/_head.html`, `_head_actions.html`;
`rentalars/documents/views.py` (`render_document_list`),
`projects/course_views.py` (`files_page`), `projects/follow_up.py`,
`follow_up_views.py`, `templates/projects/_follow_up.html`. Catalogue:
PRJ-078, PRJ-079, PRJ-102, PRJ-104, PRJ-105.
Tests: `tests/ui/test_062_project_pages.py`,
`tests/browser/test_062_project_in_browser.py`,
`tests/{unit,ui,api,browser}/test_071_settings*` (follow-up).*

**The tabs** (`_head.html`; PRJ-104): Planung, Teilprojekte
(in a family), Preisübersicht, Dokumente, Zeitplanung, Packliste,
Korrespondenz, Überblick, Zugriff, Verlauf – "Packliste" moved before
"Korrespondenz", and the deployment view is called "Überblick" (msgid
"Overview", context "project tab"). Its address
(`projects:deployment`) and the PDF "Einsatzübersicht" did not change. The
Zeitplanung lost the box "Veranstaltungsort" (PRJ-102): the venue with its
notes is in the head and on the Überblick. "Chat" stands
between Korrespondenz and Überblick, with the count of unread messages
(UIX-010, section 22), and a service case has the tabs Servicefall,
Dokumente, Korrespondenz, Chat, Zugriff, Verlauf (PRJ-090, section 21).

**The head** (PRJ-078). Every tab of a project renders
`{% load project_actions %}{% project_actions project %}`, an inclusion tag
that shows, always in this order: "Projekt bearbeiten" · the status as a
drop-down list with "Status ändern" · "<Dokument> erstellen" with the other
kinds behind ▾ · "Duplizieren" · "Als Vorlage speichern" · "Teilprojekt
anlegen". The rights are those of before: editing with edit access while
the project is not closed, statuses with edit access, reopening a closed
project only with the special right. **The tag costs no query**: the head
is on every tab, and the planning page has a tight limit (scenario 11); it
works from the project, the request's rights and what the view loaded
anyway.

- **Status:** the list offers only the statuses reachable from the current
  one; the button stays disabled until one is chosen, and "Storniert" asks
  first (`static/js/app.js`). `views.project_set_status` follows a safe
  POST `next` (same host; https if the request was), so the user stays on
  the tab – except "Bestätigt – Einzelheiten offen" without open items, which
  still leads to the Zeitplanung (PRJ-059).
- **Next document:** `NEXT_DOCUMENT` maps the status to the usual kind –
  inquiry and option → offer; confirmed (both kinds) → order confirmation;
  out → delivery note; returned and closed → invoice; cancelled → none.
  `suggested_document(status, kinds)` takes it if the user may make that
  kind here; otherwise a confirmed or running project suggests the
  delivery note (a part makes priced documents at its whole project;
  without the price right there are none), and else nothing is suggested
  and all kinds are in the list. The button only **leads** to the tab
  "Dokumente" with `?kind=` chosen in "Dokument erstellen"; the document is
  checked as a draft and made there – nothing is made by one click in the
  head. No invoice is suggested or listed while invoices are
  switched off (DOK-014, section 27).
- **"Teilprojekt anlegen"** has an arrow with "In Teilprojekte
  gliedern" – on a whole project "Teilgruppen in Teilprojekte umwandeln"
  (PRJ-050, section 21).
- The small menus (`<details class="menu">`) close on a click elsewhere or
  Escape.

**Documents and files on one tab** (PRJ-079). The tab "Dateien" is gone; the
tab "Dokumente" (`documents:list`) shows the documents, the box "Dokument
erstellen" (`id="make-document"`) and below them the files with the upload
form (`templates/projects/_files.html`, `id="files"`).
`documents.views.render_document_list(request, project, file_form=None)`
builds the page; `?kind=` preselects the kind (`MAKEABLE`, now in
`documents/models.py`). `projects.course_views.files_page` keeps the old
address: GET redirects to `documents:list#files`, POST uploads and
redirects there on success, or renders the merged page with the bound form
on an error; editing and deleting a file lead back to `#files`. The
"Back" of the top bar treats all tabs of a project as one place
(`core/trail.py`, `TAB_GROUPS` – also `projects:family`,
`projects:course`, `documents:list`, `mail:project_mails` and
`packing:family`).

**The follow-up** (PRJ-105). The requirement: (open) projects
can be put on follow-up. A project of any status gets a day, a note
and the user it is for (`Project.follow_up_*`, data-model):

1. **Setting it.** "Wiedervorlage" in the head opens a dialog
   (`follow_up_views.follow_up_edit`, `projects:follow_up`; a page of its
   own without the script) with day, note and person – preselected the
   user who sets it. `follow_up.set_follow_up` needs edit access to the
   project but no open project: a follow-up does not change the planning,
   so a closed project can have one. The person must be active and able to
   open the project (`may_be_for`). A new day or another person empties
   `follow_up_notified_at`, so the notification comes again; a new note
   alone does not. The API: `PUT` and `DELETE /projects/{id}/follow-up`;
   the fields are read-only in the project document and not part of
   `PATCH /projects/{id}` or the project form.
2. **The notification.** The minute timer of the tasks (`run_jobs`,
   `_notify_due_follow_ups`, which never stops the other tasks) calls
   `notify_due_follow_ups(now)`: every project whose day has come
   (`follow_up_on` up to today from 06:00 local time, `NOTIFY_FROM_HOUR`,
   else up to yesterday – nobody is woken at night, and a missed day comes
   at once) and that was not notified yet, at most 500 per run.
   `notify(…, Kind.FOLLOW_UP, …)` tells the person – the project manager if
   the person is gone or deactivated – in the application and by e-mail as
   the person's notification settings say (by mail unless switched off);
   the note is the text. `follow_up_notified_at` is then set with a plain
   `update`: bookkeeping, not a change of the project, so no change-log
   entry and no new stamp.
3. **Seeing it.** The head shows the follow-up to everybody who reads the
   planning – "fällig" from its day on – with "Ändern" and "Erledigt" for
   those who may edit; `project_for` loads the person in its query, so the
   head costs nothing more. The start page lists "Deine Wiedervorlagen"
   from their day on, oldest first, at most eight (`due_for`). The project
   list filters by "Wiedervorlage" – "fällig", "für mich", "alle mit
   Wiedervorlage" (`filter_projects`, across every status, like a search;
   the API `?follow_up=due|mine|any`) – and shows the note under the name
   and an optional column "Wiedervorlage"; filter, note and column only
   for users who may see customers, so the crew sees none of it.
4. **Done.** "Erledigt" (`follow_up_done`) or `DELETE` empties all four
   fields (`clear_follow_up`); the history keeps who set which day for
   whom.

---

## 16. Project numbers

*Code: `rentalars/projects/services.py` (`create_project`,
`_next_free_number`, `_next_subproject_number`), `projects/numbers.py`,
`core/converters.py`, `core/middleware.py` (`FormerNumberRedirectMiddleware`),
`mail/tags.py`. Catalogue: PRJ-003, ADM-003, ADM-012, ADM-014. Tests:
`tests/unit/test_070_numbers.py`,
`tests/ui/test_070_numbers_pages.py`, `tests/api/test_070_numbers_api.py`.*

In short: a number reads `2026-0042` (ADM-014); the number with "P-" in
front (`P-2026-0042`, ADM-012) is kept as the former number, for new and
existing projects.

**Allocation.** `create_project` takes `_next_free_number()`:
`NumberRange.allocate("project")` with a row lock, repeated while the
number is some project's number **or former number** – after an
administrator set the counter back, or changed the prefix, an old number
on a document must still mean the project it was printed for. A part is
numbered after its whole project (`_next_subproject_number`:
`2026-0042-1`, `-2`, …). The prefix of a new installation is `{year}-`
(`core/defaults.py`, `PROJECT_PREFIX`), four digits at least, counted from 1 every year:
`2026-0042`.

**The renaming to "P-"** (`projects/0012_numbers_063`). Decision:
switch completely – new installations, new projects and the
existing ones. The migration adds `Project.former_number` and then:

1. **The prefix.** A prefix without letters apart from `{year}` follows the
   default scheme and gets "P-" in front: `{year}-` → `P-{year}-`,
   `{year}/` → `P-{year}/`, an empty prefix → `P-`. A prefix that starts
   with "P-" already stays. Any other prefix with letters (`PRJ-{year}-`)
   is the administrator's own scheme: then **nothing** is changed, neither
   the prefix nor a number – no "P-PRJ-…".
2. **The numbers.** Every number without letters gets "P-" in front, parts
   included (`2026-0042-1` → `P-2026-0042-1`); the old one goes into
   `former_number`. A number with letters is never touched – which makes
   the step idempotent, since a converted number has one. A target that is
   taken (compared case-insensitively, as MariaDB compares the unique
   column) or longer than 30 characters is skipped: that project keeps its
   number, which keeps working. A new number always starts with "P-" and an
   old one being renamed never has a letter, so a renamed number can never
   meet one still to be renamed.
3. **Templates.** `ProjectTemplate.source_number` follows the new number.
4. **The change log** gets one entry per change with the actor
   "Aktualisierung" – the range's prefix, each project (`number`,
   `former_number`), each template.

On a database just being created – no project range yet – the data step
does nothing; the start data bring the new prefix. Documents are not
touched: what was sent stays as sent; documents made
from now on show the new number. The reverse step does nothing – going
back keeps the new numbers. Webhooks, exports, packlist and price PDFs and
their file names read the live number; calendar UIDs are built from the
crew line's key, so subscribed calendars only see a new summary at the next
push. The migration depends on `core/0007_noon_to_noon`, not on
`core/0008_numbers_063`, which only changes a help text.

**The renaming back** (`projects/0014_numbers_070`, ADM-014). The
requirement: project numbers do not all start with "P-" any more, for future and existing projects. The
migration changes the help text of `former_number` (state only) and runs
one data step, `take_p_away`:

1. **The prefix.** "P-" followed by no further letters apart from
   `{year}` loses it: `P-{year}-` → `{year}-`, `P-{year}/` → `{year}/`,
   `P-` → empty. The counter goes on: after P-2026-0057 comes 2026-0058.
   `PRJ-{year}-` or `P-X-{year}-` is an administrator's own scheme and
   stays.
2. **The numbers.** Every number "P-" plus letter-free loses "P-", parts
   included (`P-2026-0042-1` → `2026-0042-1`) – those renamed earlier and
   those created since. The number with "P-" becomes `former_number`: it
   is printed on earlier documents and in the subjects of their
   mails. The former number is the number of today again, so
   nothing is lost. A project keeps both numbers if the target is taken
   (case ignored) or if its former number is something other than the
   target (only a change by hand outside Rentalars can do that). Renaming
   in order is safe on MariaDB: a target never contains a letter, so it
   never meets a number with "P-" still to be renamed. A second run
   changes nothing.
3. **Templates** follow the new number; **the change log** gets one entry
   per change with the actor "Aktualisierung".
4. **An older installation.** Then 0012 and 0014 run in the same
   `migrate`: 0012 gives "P-" and 0014 takes it away a moment later.
   Nobody ever saw such a number, so it is not kept: the project ends up
   exactly as before, with an empty former number. A migration does not
   know which other migrations its `migrate` applies, so
   `ProjectsConfig.ready` connects `note_migration_plan` to the
   `pre_migrate` signal, which receives the whole plan before anything
   runs; it leaves the set of migrations to apply on the database
   connection (`rentalars_migration_plan`), and 0014 checked whether
   `projects 0012_numbers_063` was in it (`p_given_just_now`; handler and
   migrations gone). A project
   that had "P-" set by hand before the renaming was not renamed by 0012 and
   still keeps its P- number as the former number. `deploy/update.sh` and
   `deploy/restore.sh` run a single `migrate`, so this holds for updates
   and restores; 0014 run without the signal (no plan on the connection)
   keeps the P- numbers as former numbers – the safe side.

The migration depends on `projects/0013`, `core/0008` and
`contenttypes/0002`; going back does nothing (0.6.x finds a project by
either number). The help text of `SystemSettings.mail_tag_prefix` follows
in `core/0009_crew_requests_070`. Documents are not touched.

**Former numbers keep working** – the number of today always wins: if a
project has as its number what is another project's former number, that
project is meant. `projects/numbers.py` holds the lookups:
`project_by_number` (one query; today's number case-insensitively sorted
before a former one), `numbers_of_today` (a list of numbers, former ones
replaced, one query, case ignored), `matching` (a `Q` over `number` and
`former_number`) and `may_be_former` (not empty, and no letter apart from
a leading "P-" – `2026-0042` and `P-2026-0042` can be former numbers,
`PRJ-2026-0042` cannot and costs no query). The address converter looks
for a former number only when today's number is not found, and no list or
search page makes a query per row.

| Where | How |
|---|---|
| Addresses | `ProjectNumberConverter.to_python` tries today's number, then – before the bare key, since `0042` of an empty prefix is a number – a former one, and notes it for the request (`former_numbers_in_address`). `FormerNumberRedirectMiddleware.process_view` then answers a GET or HEAD with **301** to the same path with today's number, query string kept. POST and the like are served at the old address (a redirect would turn them into a GET). It sits after the login and two-factor middleware, so a visitor who is not logged in goes to the login first and learns no number; and before `TrailMiddleware`, which then only sees today's address. |
| Mail tags | `find_numbers`, `subject_with_tag` (section 8) |
| Search | the global search (`core/search.py`), `?q=` of the project list, `q` of `/api/v1/projects` – all with `matching` –, and the search of the mail log (`mail/log.py`, `project__former_number`) |
| Forms and API that take a number | copying a group into another project, assigning a waiting mail by hand (page and `project_number` in the API), the API filter `?number=` (`project_by_number`) |
| The project | its head shows "(früher P-2026-0042)"; the API gives `former_number`, read-only, and `?number=P-2026-0042` still finds it |

---

## 17. Filters, menu and the pages without login

*Code: `rentalars/core/templatetags/rentalars.py` (`filterpanel`),
`templates/core/_filter_panel.html`, `_credit.html`, `templates/base.html`,
`base_public.html`, `core/context_processors.py`, `accounts/backends.py`,
`static/js/app.js` and `static/css/app.css` (blocks UIX-030 to UIX-032);
`core/listing.py` (`query_date`). Catalogue:
UIX-030 to UIX-032, UIX-038, UIX-004. Tests:
`tests/unit/test_063_ui.py`, `tests/ui/test_063_ui_pages.py`,
`tests/browser/test_063_ui_in_browser.py`, `tests/ui/test_071_lead_pages.py`.*

**Filters that fold away** (UIX-030; folded on every width,
UIX-038). On a phone the filters above a list took half the screen; the
requirement is that they fold away on every width, not only on the phone.
Every list with a filter bar wraps its filters – not
the search field, which stays in front – in a block tag:

```django
<form method="get" class="filters">
  <div class="field grow">… search …</div>
  {% filterpanel "projects" %}
    <div class="field">… status …</div>
    <button class="btn secondary" type="submit">…</button>
  {% endfilterpanel %}
</form>
```

`FilterPanelNode` renders `core/_filter_panel.html`: a button "Filter"
(`data-filter-toggle`, `aria-controls="filter-panel-<key>"`,
`aria-describedby="filter-summary-<key>"`), a summary
(`filter-summary-<key>`, hidden while empty) and the panel holding the
fields. Then:

1. **Before any script**, the CSS hides the button; with
   `@media (scripting: enabled)` it shows, and the panel is folded until
   the script has looked – so nothing jumps. That
   holds on every width. An open panel is `display: contents`, so on a
   wide screen its fields stand in the one row of before. Without
   JavaScript every field shows and there is no button.
2. **The script** (`app.js`, block UIX-030) sets `aria-expanded`: a form
   with an error is always open; else folded. **Nothing is remembered**
   (UIX-038, line 13 of the user's message:
   "immer eingeklappt") – the stored value is
   ignored, and a click only toggles.
3. **Active filters** are counted from the values the page was **loaded**
   with (`defaultSelected`, `defaultValue`, `defaultChecked` – the server
   filtered by those, not by what was typed since): a field counts when it
   is not on its first option or not empty, or not on its
   `data-filter-default` (the days of the inspection list). The button says
   "Filter (2)", "Filter (2 aktiv)" (the text comes translated
   from the page, `data-filter-active`); while folded, chips like "Status:
   Bestätigt" stand in the summary. The Materialverwaltung lists already
   used this panel – only the remembered state had kept them open. The
   Django master-data admin folds its filters too
   (`templates/admin/filter.html`: `<details>` with `data-list-filter`
   instead of `data-filter-title`, so `admin/js/filters.js` reopens
   nothing; the folded heading names the choice, "Nach Aktiv: Ja").
4. Enter in the search field still sends the form while the submit button
   is folded away.

Sixteen lists use it (projects, items, models, inspections, products,
customers, venues, people, time approval and report, shortages, mail log,
change log, access log, security log, a webhook's deliveries). Left out:
the user list (search only), the bars of the timeline, utilization and
personnel plan (navigation, not filters), "Wer ist frei?" (the form is the
question) and the inquiries (no filter bar).

**An impossible day in the address** (UIX-004). Filters live
in the address, so people edit links by hand. `?since=2027-02-30` is well
formed but no real day, and Django's `parse_date` raises `ValueError` for
it – the project list answered with a server error. `core.listing.query_date`
returns `None` for a missing or impossible day, `query_datetime` the same
for a moment (`2027-03-01T25:00`); such a filter is then simply not
applied. They read the dates of the project list (`since`, `until`), the
planning pages (`from`, the calendar's `week`), the times (`week`), the
change log (`since`, `until`) and the availability check of a line
(`start`, `end`). A new page that takes a date from the address uses them
instead of `parse_date`.

**The company name in the menu** (UIX-032). The context processor
`core.context_processors.application` gives every page `company_name`.
It must cost no query: the menu is on every page, and the planning page has
a tight query limit (scenario 11). `EmailOrUsernameBackend.get_user`
therefore loads the session user with a scalar subquery
(`Subquery(CompanyProfile.objects.filter(pk=1).values("name")[:1])`,
annotated as `menu_company_name`) in the query that already brings the
person – always current, no cache. A cache was tried and rejected: the
default cache lives per process, so with several gunicorn workers a changed
name would stay old in the others. A user object that did not come from
`get_user` – the one `authenticate` returned in the request of the login,
for instance – gets a lazy `CompanyProfile.load()`, read only when the
menu is rendered. Where it shows: in the sidebar under
"Rentalars"; in the phone top bar from 481 to 900 px, cut with "…"; at
480 px and below at the top of the opened menu (`p.sidebar-company`), while
the top bar keeps it visually hidden for screen readers. Not on public
pages.

**The credit** (UIX-031). `rentalars/__init__.py` holds `CREDIT_NAME`
("fld-vt.de") and `CREDIT_URL` next to `__version__`; the context
processor passes them as `rentalars_credit`, also to visitors not logged
in. `core/_credit.html` writes "von fld-vt.de" (new tab, `rel="noopener"`)
under the version in the sidebar and in the footer of the public pages
("Rentalars <version> · von fld-vt.de").

**The pages without login** (`base_public.html`: login, login code, new
password, password reset, setup). Logo, box and footer now share one
full-width column (`div.public-column`) and are each centred in it. Before,
the grid item was as wide as its longest text and the 440 px box stood at
its left edge – 106 px off centre at 1366 px and wider. The setup form also
fits at 320 px now (`minmax(min(220px, 100%), 1fr)`). In the same release
the phone layout got `align-content: start` on the page grid: on short
pages the rows had shared out the height, and the top bar stood about
220 px high.

**Small things.** The links to the API documentation (settings,
webhooks) open in a new tab (`target="_blank" rel="noopener"`, UIX-037);
there is no "opens in a new tab" hint, as the project has no such
convention. On the mail settings the buttons "Verbindung prüfen" and
"Bearbeiten" of a mailbox stand in one flex row (`.cell-buttons`), also
on a phone.

**Grouping a table** (UIX-040, `core/tables.py`,
`templates/core/_table.html`, `_table_tools.html`). Every list page is a
`TableDefinition`; a column that may group declares `group`. A request
flows like this:

1. `TableDefinition.state(request)` reads `?group=<key>` (with the
   table's prefix, `param("group")`) next to `cols` and `sort`; a key the
   user cannot see, or of a column without `group`, is ignored.
2. `TableState.order(queryset)` sorts by the group first – a field
   with choices in the order of its choices ("offen, in Arbeit, erledigt",
   `_choice_order`), a link by the name the column sorts by – and then by
   the chosen column, so each group stands together on every page. A table
   over computed rows (`_order_list`) does the same in Python, with
   `group_key`.
3. The rows of the page are fetched as always; one aggregate query
   (`Count` per group value) counts each group in the **whole** filtered
   list.
4. `TableState.rows` puts a `GroupHeading` (value via `group_value` /
   `group_label`, count) on the first row of each group and on the first
   row of a page whose group began on the previous page; `_table.html`
   writes it as a header row spanning all columns ("(ohne Angabe)" for an
   empty value).
5. The choice "Gruppieren nach" in `_table_tools.html` is a GET form next
   to "Spalten" that repeats the page address as hidden fields, so
   filters, sorting and page size survive.
6. CSV (`?format=csv`) ignores the group and leaves out columns with
   `export=False`.

**No "Zurück" from the navigation** (UIX-041). The trail
(`core/trail.py`) shows no back link on a page in `START_PAGES`; the three
pages that had one again (Servicefälle, Spesen, Meine Spesen) were
missing there. `tests/ui/test_back_and_page_size.py`
(`NoBackFromTheNavigationTests`) now walks every navigation entry, the
links at the sidebar foot and every tab found on those pages, so a new
tab without an entry fails the test.

**Every column sorts** (UIX-015, UIX-040, line 21 of the
user's message; `core/tables.py`, tests `tests/unit/test_082_cleanup.py`,
`tests/ui/test_082_cleanup_pages.py`). A click on any heading sorts, also
columns added under "Spalten":

1. A column whose `sort` names model fields or lookups sorts in the
   database, as before.
2. A multi-valued column (job functions, qualifications, roles, categories
   of a scale) sorts by its alphabetically first value
   (`first_value(queryset, field)` → a `Subquery`).
3. A computed value the database can express sorts by an expression or an
   annotation – volume L×W×H, a notification's category, two-factor login,
   a venue's hall plan, an item's effective product; `Column.sort_prepare`
   adds what the sort needs. The admin "path" of master data sorts by the
   tree (`admin_tables.tree_path_order`, exact up to 6 levels).
4. A value that only exists in Python – the 8 project sums, rental days,
   stock / total stock / below minimum, the category-specific value, a
   scale's factors, a template's content, a webhook's events, "my part"
   and note in my service cases – sorts in Python
   (`TableState._order_in_python`) **if the filtered list has at most
   `PYTHON_SORT_MAX_ROWS` (2,000) rows**; a longer list keeps the table's
   default order and sets `sort_notice` ("Zum Sortieren nach „…“ darf die
   Liste höchstens 2.000 Zeilen haben …"), shown by `core/_table.html`. The count is one extra
   query; the rows are loaded once for the page anyway.
5. Text with numbers sorts naturally (`natural_key`: "5 m" before "10 m").
6. Only button and tick-box columns are unsortable, each naming its reason
   in `Column.unsortable`; a test walks every `TableDefinition` and fails
   on a column that neither sorts nor gives a reason. The CSV follows the
   chosen sort (also the material CSV of an already sorted list).

**Meine Einsätze** (UIX-043, `projects/my_deployments.py`,
`templates/projects/my_deployments.html`, `personnel/_my_tabs.html`): the
crew lines of the user's own person as a `core.tables` table at
`/me/deployments/`, the first tab of Mein Bereich, which the navigation
opens (`core/navigation.py`, `core/trail.py`). Filters: period
(`coming` by default, with 12 hours' grace like the start page; `past`;
`all`; plus `since`/`until`), state (firm/option/inquiry), request status
(asked, accepted, declined, not asked), project. Cancelled projects are
left out; no module right is needed. Every column sorts; "Stand" sorts by
the view's annotation `deployment_state` and cannot be grouped
(`core.tables` groups only by a model field). The start page block stays;
its button "Alle meine Einsätze" leads here.

**Entries per page per user and list** (UIX-050). Every list
paged by `core.listing.paginate` or `TableState.paginate` offers 25, 50,
100, 200 and a typed number from 5 to 1,000; `page_size_choice` takes the
address, then `TablePreference.page_size` under `list_key` (the URL name
of the page plus the table prefix), then the default, and remembers a
number accepted from a `GET`. Details in [architecture.md](architecture.md),
"Lists as tables". **Required fields everywhere** (UIX-051): forms written
by hand mark a field with `core/_required_star.html` and put the note with
`_required_note.html` and `always=True`; `tests/unit/test_092_ui.py`
(`RequiredMarksTests`) crawls the pages and dialogs of an administrator
and fails on a `required` input without the star.

---

## 18. Dates, periods and required fields

*Code: `static/js/app.js` (block "UIX-036 … PRJ-099" at the end, and the
UIX-025 range picker), `static/css/app.css`, `templates/base.html`
(`data-text-*`), `rentalars/projects/templatetags/period_marks.py`,
`projects/course.py`, `course_views.py`, `course_api.py`;
`core/templatetags/rentalars.py` (`required_condition`, `condition_holds`,
`marks_required`), `core/forms.py` (`mark_required`),
`templates/core/_required_mark.html`, `_required_note.html`. Catalogue:
UIX-035, UIX-036, PRJ-099, PRJ-100. Tests:
`tests/{unit,ui,api,browser}/test_070_pickers*`, `test_070_planning*`.*

**One picker for every date and time field** (UIX-036). Requirement: every
date field offers the calendar of "Zeitraum im Kalender wählen", and every
time field a time choice; decision: a clock face. The
script wraps every `<input type="date">`, `datetime-local` and `time` in
`.dt-wrap` and puts its own button where the browser's calendar symbol
was (that one is hidden with `::-webkit-calendar-picker-indicator`). **The
fields keep their native type and value format** (`2027-03-10T08:00`), so
typing, the server's parsing, form checks, the API and every `.fill()` in
the tests stay as they were; without JavaScript the browser's own picker
remains. Alt+↓ and F4 open the dialog; a click on the field does not
(`preventDefault`), but on a touch screen (`pointer: coarse`) a tap on the
field opens it, since the browser would show its own picker over the page.

- **Calendar:** a date alone is taken with the tap on the day; date and
  time need "Übernehmen". "Heute"/"Jetzt" fill in now, "Leeren" appears
  only on optional fields. `min`/`max` are respected – days outside are
  marked (`aria-disabled`) but stay focusable. A field paired with a
  partner (`…start`/`…end`, `partnerOf`) outlines the partner's day and
  tints the days between. Keys: arrows by day and week, Page↑/↓ by month,
  Home/End, Enter or Space; this navigation works in every calendar of
  these dialogs, the range picker included.
- **Clock face** as in Android's 24-hour mode: outer ring 12, 1–11, inner
  ring 00, 13–23; after the hour it switches to the minutes, shown in steps
  of five – a tap snaps to five, dragging or typing gives any minute. Hour
  and minute are also two text fields; two digits move on. The face is a
  `role="slider"`; see [accessibility.md](accessibility.md).
- **Phone** (below 640 px): date and time take turns through two buttons
  at the top; after the day the clock gets the focus. Focus always returns
  to whatever opened the picker; Escape closes without change.
- **Shared code:** `window.Rentalars.calendar` (`marks`, `markDay`,
  `legend`) and `window.Rentalars.enhancePickers` let the UIX-025 range
  picker use the same marks and give its two time fields the clock. The
  texts come from `data-text-*` on `<body>` (pick-date, hour, minute,
  clock-hint, today, now, clear, …), translated by the template.

**Hatched periods** (PRJ-099). An element with `data-calendar-marks`
around the fields lists periods to hatch in these calendars: the rental
period (grey) and the event period (green), lines in opposite directions,
with a legend naming the times. `{% project_period_marks project %}` gives
the saved periods – for the phase forms ("Neue Phase", phase edit and the
dialog over the crew planning); `{% form_period_marks %}` names the fields
of the project form, so the calendar of one period shows the other live,
as typed. A period whose fields are the ones being chosen is left out.
Each marked day's label adds the period's name for screen readers. The
crew forms get the picker but no hatching.

**The project form** (PRJ-099): the boxes "Mietzeitraum: Material außer
Haus" and "Veranstaltung" are laid out alike (`.period-fields`): Von, Bis,
and the button "Zeitraum im Kalender wählen" in a `[data-range-slot]` as
tall as the fields in the same row, the rental days in a second row; below
1000 px the button goes under the two fields, below 640 px everything
stacks. Before, the event box's button was out of place.

**A phase beyond the rental period** (PRJ-100). Decision: ask first
("Erst nachfragen"). The phase is always saved first; then
`course.rental_period_suggestion(phase)` returns a
`RentalPeriodSuggestion` – the present rental period widened just enough
to cover the phase – or `None` (inside the period, or a phase of a kind
in `KINDS_WITHOUT_EXTENSION`: `planning` never asks, so a site visit
weeks before blocks no material). `blocked_by` names the whole project of
a subproject whose period would not cover it; then there is no
"Erweitern", only a note to extend the whole project first.

1. Saved on a page, `phase_edit` redirects to the Zeitplanung with
   `?extend=<phase id>`; `course_page` shows the question box
   (`_rental_period_question.html`) with the focus on "Erweitern". From
   the dialog over the crew planning (PRJ-094) the answer `phaseCreated`
   carries `keepDialog`, and the dialog shows the question in place of its
   content (`_phase_extend_question.html`).
2. "Erweitern" posts to `projects/<pk>/phases/<phase_pk>/extend-period/`
   (`phase_extend_period`, edit access): `course.extend_rental_period`
   goes through `services.update_project`, the path of the project form –
   a closed project refuses, a part stays inside its whole project
   (PRJ-045), parts stay inside the whole project, material lines that had
   the old period follow, the change log records it –, then
   `project_changed` tells the people of the project. A warning appears
   only if the longer period leaves more pieces missing than before
   (`build_planning(...).shortage_total` before and after).
3. In the dialog the result stays in the dialog
   (`_phase_extend_done.html`) and the response triggers
   `rentalPeriodChanged`: the page shows "Es gibt Neues auf dieser Seite"
   instead of reloading, so the crew form keeps what was typed.
   "Nicht erweitern" leaves everything as it is.

The API only tells: `outside_rental_period` and `rental_period_suggestion`
on every phase (list, create, update; no extra query per phase); a client
extends with `PATCH /projects/{id}`.

**Required fields** (UIX-035). Required fields have to be marked
(e.g. the price of a new product). The asterisk comes from one filter,
`required_condition(field)`: `"always"` if the form field is required or
`core.forms.mark_required(field)` set `aria-required` (a field the model
requires although the form field is optional), else the condition of
`mark_required(field, when="kind=rental|kit")` (`data-require-if`), else
nothing. `core/_required_mark.html` draws the asterisk (`aria-hidden`); a
conditional one carries the same condition as `data-show-if`, so the page
script shows it while the condition holds, and `applyConditions` sets the
field's `required` with it. Conditions understand `&` (both) and `;` (one
of them, binding weaker) in Python (`condition_holds`) and in the script
(`conditionHolds`). `_form_errors.html` adds the note "* Pflichtfeld"
(`aria-hidden`) once per form whose fields mark anything
(`marks_required`). Validation is unchanged – the model still decides.
Marked under conditions: the product's price for every kind but sale,
the sale price, percentage, owner and custom scale; the project's
customer unless internal; the mailbox's IMAP server, user and password,
SMTP server, address and done folder. Hand-written forms (members, lines,
items, people, availability, time entry, documents, import …) use the
same include. Not marked: GET filter forms, radio groups that always have
a choice, the SMTP password (its condition "field filled" cannot be
expressed); required selects without an empty option keep their asterisk
but get no `aria-required`.

---

## 19. New material: models, items, a product from a model

*Code: `rentalars/material/services.py` (`create_items`,
`following_free_numbers`, `check_serial_numbers`, `manufacturer_named`,
`supplier_named`, `create_product_from_model`, `assign_model_to_product`),
`material/forms.py` (`MaterialModelForm`, `ItemCreateForm`,
`MaterialItemForm`), `material/views.py`, `material/api.py`;
`masterdata/models.py` (`StorageLocation`, `is_power_field`);
`products/services.py` (`presets_for_kind`); `static/js/app.js` (block
"Material"). Catalogue: MAT-048 to MAT-052, PRD-046.
Tests: `tests/{unit,ui,api,browser}/test_071_material*`.*

The requirements for the forms "Neues Materialmodell" and "Neue
Exemplare", with what happens behind them.

**Manufacturer, product and "Gekauft bei"** (MAT-048, MAT-050). The three
fields are text fields with suggestions (template
`material/_name_typeahead.html`; endpoints `material:manufacturer_suggest`,
`material:product_suggest`, `material:supplier_suggest`). For manufacturer
and supplier **the typed name is the value** (`manufacturer_name`,
`supplier_name`): saving the form calls `manufacturer_named(name)` or
`supplier_named(name)`, which return the record of that name – case
ignored, an inactive one too – or create it; empty means none. So the form
works without JavaScript, and nothing is created by merely typing; the last
suggestion only says "neuer Hersteller" or "neuer Händler". (The supplier
of a subrental is created in a dialog instead, because it gets contact
data there – section 3.) The product field offers rental and sale
products by article number or name; the separate endpoint keeps it apart
from `products:suggest`.

**The power** (MAT-049) is `MaterialModel.power_w`, in the box "Gewicht,
Maße und Leistung" with weight and dimensions; the volume is still
calculated from the dimensions. A category field for it is refused
(`CategoryField.clean` with `is_power_field`: type number, label
"Leistung" or "Power", unit W or Watt), so the value has one place.

**"Neue Exemplare"** (`material:item_create`, `ItemCreateForm`,
`create_items(model, count, inventory_number=…, serial_numbers=…, …)`):

1. **Start-ID.** Empty: every item gets the next free ID of the number
   range, as before (MAT-003). Given: the first item gets it – refused if
   taken –, each further one the next free ID after the one before
   (`following_free_numbers` reads the taken IDs in windows, not one query
   per number: start 42 for three items with 43 taken gives 42, 44, 45),
   and `NumberRange.ensure_next_is_above` moves the counter behind the last.
   The rule of 0.5 "a specific ID only for a single item" is gone.
2. **Serial numbers.** One per item, in the order of the IDs; an empty one
   leaves that item without. `check_serial_numbers` refuses more than there
   are items and the same one twice in the batch; a serial number the model
   has already only warns (MAT-004, `serial_number_warnings`). On the page
   the script turns the textarea `serial_numbers` (one per line – what a
   browser without script gets) into one field per item, as many as
   "Anzahl der Exemplare" says (at most 500); Enter jumps to the next field,
   because a scanner ends every code with Enter, and lines pasted into one
   field fill the following ones and raise the count if needed.
3. **Purchase data.** "Gekauft bei" (a supplier, created if new),
   "Rechnungsnummer" (`invoice_number`) and "Rechnungsdatum" (the field
   `purchase_date`); the edit form of an item
   has the same fields.
4. **Storage location** (MAT-052): preselected with
   `StorageLocation.get_default()` – the active location marked "Standard
   für neue Exemplare", in a new installation "Hauptlager". The import and
   `POST /material-models/{id}/items` take no default; they name a location
   or none. The API takes `start_number` (the start ID) and
   `serial_numbers` (a list).

**"Als Produkt anlegen"** (MAT-051, `material:model_create_product`,
`POST /material-models/{id}/create-product`). A model without product gets
a product of the same name: `create_product_from_model` takes the
category's presets (`presets_for_category`), makes a sale product if the
category presets sale and a rental product otherwise, sets the price (for
a sale product the sale price) to 0, takes the next free article number
and assigns the model
(`default_product`). It needs write access to products; afterwards the
product form opens for users with the price right – the price is still 0
–, the product page for the others. For customer material the button is a
link to the product form instead, because the owner must be chosen.

**The product form asks the kind first** (PRD-046). The field "Produktart"
comes before "Kategorie"; on a new product choosing either reloads the
form with `?kind=…&category=…` (`data-reload-fields`), so the server can
prefill the rest: categories whose preset kind matches the chosen kind
come first, in a group of their own (`category_groups`), and
`presets_for_kind` keeps the chosen kind against the category's preset –
the billing mode follows the kind unless the category presets that same
kind with a billing mode of its own; customer material stays flat. Text
typed before the reload is lost, as with the category before.

**"Vorhandenes Modell zuordnen"** (PRD-046) under "Zugeordnetes Material"
of a product: a type-ahead over models without product
(`material:model_suggest`) posts to `material:model_assign`;
`assign_model_to_product` refuses a model that has a product and a product
of a kind without stock, and returns the hint of PRD-032 when the model is
in another main category than the product. It needs write access to
material.

**The default storage location** (MAT-052) is chosen in Einstellungen →
Stammdaten → Lagerorte with "Standard für neue Exemplare"; saving one takes the mark
from the others (`StorageLocation.save`), a deactivated location cannot
have it (`clean`), and the administration page names the current default
("Kein Standard-Lagerort für neue Exemplare" without one).

---

## 20. Data steps: storage, material and mailboxes

*Code: the migrations named below. Tests: `tests/unit/test_071_*.py` call
each data step on data shaped like an older installation's, and a second time to see that
nothing changes.*

What `rentalars update` (one `migrate`, after the backup) does to the data
of an existing installation, in the order the dependencies allow. Every
data step was run on a copy of an earlier database and a second time without
change; every change of business data is in the change log with the actor
"Aktualisierung" (the pattern of `projects/0014_numbers_070`,
section 16), the changes of lines, mails and files also in the history of
their project. A fresh database skips the data steps that need start
data (`SystemSettings.defaults_installed` is false) – the start data
bring N, the eight job functions and "Hauptlager" after `migrate`.
Going back runs no data step (`RunPython.noop`); the way back is
the backup.

| Migration | Schema | Data |
|---|---|---|
| `products/0006_services_071` | `Product.kind` offers `incidental`; `hours_limit`, `price_above_limit` | – |
| `masterdata/0006_incidental_071` | `Category.default_product_kind` offers `incidental` | adds the main category N "Nebenkosten" (no stock, kind Nebenkosten, unit "Pauschal" where it exists) unless a main category has the code N or the name (case ignored) |
| `personnel/0010_services_071` | `JobFunction.guide_cost_rate_above_limit`, `PersonJobFunction.hourly_rate_above_limit`; after the data step `JobFunction.service_product` becomes a required `OneToOneField` | 1. a product shared by several functions stays with the function of its name (or whose name it starts with), else the oldest; the others get copies with the next free article number of the category, the same prices, billing, tax rate, unit, maximum discount and hour tiers, named after the function; 2. a function without product gets one in the category of services (D first; D "Dienstleistung" or "DL" created if there is none), by the hour, priced like the newest crew line of the function billed by plan or effort above 0, else 0; 3. services without function become Nebenkosten; 4. a main category presetting services whose products – at least one – are all Nebenkosten now presets Nebenkosten; 5. an installation without any job function gets the eight of the start data, without price. On a fresh database it removes the unused suggestions of `0002_suggested_job_functions` instead. |
| `projects/0016_crew_071` | `CrewLine.hours_limit`, `unit_price_above_limit`, `hourly_rate_above_limit` (empty: every hour the same) | every crew line whose `service_product` is not that of its function now names the function's product; title, prices, billing and discount stay. Billings are not changed (PER-036 is for new lines). |
| `masterdata/0007_suppliers_071` | `Supplier.email`, `Supplier.phone`; `contact` is the contact person | moves the first valid e-mail address and the first phone number (at least six digits, with the label before it, not after "Nr."/"Nummer") out of `contact`, where the new fields are still empty |
| `projects/0017_subrentals_071` | `subrental_status` offers `open` first; `ProjectFile.supplier`, `supplier_document_kind` | subrentals without supplier and a status other than "offen" – as a rule "angefragt", the former default – and subrental lines without any status become "offen" |
| `mail/0006_subrentals_071` | `ProjectMail.supplier` | links each stored mail whose sender, To or CC names the address of exactly one supplier (in chunks of 50 addresses, SQLite's limit of terms) |
| `masterdata/0008_storage_071` | `StorageLocation.is_default` | does nothing if a default exists; else an active top-level "Hauptlager" (case ignored) becomes the default, or – without any location – "Hauptlager" is created as the default; otherwise none until one is chosen |
| `material/0004_items_071` | `MaterialModel.power_w`, `MaterialItem.invoice_number`; labels "Beschreibung", "eigene Beschreibung", "Rechnungsdatum" | every category field of type number labelled "Leistung"/"Power" in W/Watt: the model values move to `power_w` (a power already there wins), an item's own value becomes a line "Leistung: 600 W" of its own description, the field is deleted. JSON values are compared in Python, not by a database lookup, because SQLite and MariaDB store them differently. |
| `mail/0007_mailboxes_071` | `ProjectMail.mailbox_name`, `MailLogEntry.mailbox_name`; both `mailbox` keys `SET_NULL` (were `PROTECT`) | copies each mailbox's name onto its mails and log entries, one statement per mailbox and table; no business data change, so **no** change-log entry. Mailboxes that were switched off stay switched off and can be deleted now. |
| `projects/0018_follow_up_071` | `Project.follow_up_on`, `follow_up_note`, `follow_up_user`, `follow_up_notified_at` | – (no project has a follow-up) |
| `notifications/0004_follow_up_071` | `Notification.kind` and `Preference.kind` offer `follow_up` | – (who chose nothing gets follow-ups in the application and by e-mail) |

Not a migration, but part of the same update: "Antwort auf Einsatzanfragen"
keeps its value (ADM-015 moved only the field on the pages), and the
follow-ups are notified by the minute timer that already runs
(`rentalars-jobs.timer`).

---

## 21. Subprojects afterwards, service cases, show files

*Code: `rentalars/projects/split.py`, `split_views.py`; `service_cases.py`,
`case_views.py`, `case_forms.py`, `case_api.py`; `showfiles.py`, `files.py`;
`rentalars/core/showfiles.py`, `core/uploads.py`. Catalogue:
PRJ-050, PRJ-090, PRJ-089. Tests: `tests/{unit,ui,api,browser}/test_080_projects*`.*

### Dividing a project afterwards (PRJ-050)

"Stadtfest" was planned in one piece, with the top-level groups "Bühne
Marktplatz" and "Bühne Schlosspark"; now each stage needs its own period,
packlist and status. The arrow next to "Teilprojekt anlegen" offers "In
Teilprojekte gliedern" (`projects:split`; on a whole project
"Teilgruppen in Teilprojekte umwandeln").

1. **The plan** (`split_plan`, a handful of queries): the page – and
   `GET /projects/{id}/split` – lists every top-level group with its lines
   (subgroups included, and the subrentals that cover their shortages,
   PRJ-054), whether it can become a part and why not, whether it stays as
   a group in the part (`kept_because`), the crew lines, and warnings. It
   refuses the whole project (`_refusal`) for a service case, a part (one
   level, PRJ-044) and a status other than inquiry, option, confirmed
   (both) – `SPLITTABLE_STATUSES` –, and a project without groups. A group
   cannot go when material of it is packed, issued, ticked back or
   allocated (any `PackEntry` with progress), when it or one of its lines
   is an alternative across its boundary, or when a surcharge refers across
   it (`_surcharge_crosses`). A surcharge on "the whole project" or
   "personnel" is a warning only: it stays and counts what stays.
2. **Choosing:** the groups that become parts, and for each crew line
   "bleibt am Gesamtprojekt" or one of the chosen groups. Lines outside
   every group always stay.
3. **Doing it** (`split_into_subprojects`, one transaction, the project row
   locked): for each chosen group in the order of the groups,
   `services.create_subproject` makes the part – name of the group, the
   project's periods, rental days and status, the usual presets –; packing
   records without progress and packlist assignments of its lines are
   deleted (they belong to the packlists of the whole project); groups and
   lines move with `update()`. A group that is kept moves as the part's one
   group; otherwise its subgroups become top-level groups of the part, its
   own lines lose their group, and the empty group is deleted (the change
   log shows it as deleted). Covering subrentals stand with their line. The
   chosen crew lines move with their time entries; a phase of theirs is
   copied into the part (`_move_crew`). Events: `project.split_part` at
   each part, `project.split` ("In Teilprojekte gegliedert: …") at the
   whole project.
4. **Afterwards** everything of PRJ-044 to PRJ-049 holds: the whole
   project bills all parts (section 10), its packlist shows them (section
   4), memberships of the whole project hold in the parts.

### A service case (PRJ-090)

A flickering spotlight, a question about a manual: no planning, but a
number, a correspondence and somebody responsible.

1. **Creating** (`service_cases.create_case`): Projekte → Servicefälle →
   "Neuer Servicefall", or "Als Servicefall anlegen" at an inquiry without tag
   under Projekte → Anfragen (`projects:case_create?inquiry=<id>`, needs
   write access to e-mail). Fields: name, customer (**required**, PRJ-090 – `create_case(customer_required=True)`
   from the form, the API and the inquiry flow, and `update_case` on every
   edit, both through `require_customer`; the status can change without
   one; a case the mail fetch creates itself, EML-047, passes no
   `customer_required` and shows "Kunde fehlt" with "Kunden wählen" for
   editors), contact, "Gemeldet von", description (`notes`, optional),
   "Zuständig" (`manager`, preset: who creates it). The case gets the next project number
   (`_next_free_number`), `kind=service_case`, `case_status=open`, the
   project status "inquiry" and a one-hour stand-in period. From an
   inquiry the subject (without "AW:", "Re:" …) is the name, and a sender
   whose address is that of a contact brings customer and contact, else
   lands in "Gemeldet von" (`suggestions_from_inquiry`); `create_from_inquiry`
   creates the case and takes the mail in (`mail.fetching.assign_unknown`)
   in one transaction – if the mailbox cannot be reached, there is no case.
   A role limited to assigned projects gets a membership, so the creator
   can open the case.
2. **Working on it:** the tab "Servicefall" (`case_detail`) shows status,
   responsible, contact and description; the status changes in any order
   (`set_case_status`, logged); a newly responsible person is told
   (`project_change`). Mails with its tag land in it like in any project
   (EML-009).
3. **Where it is not:** `services.ensure_plannable` refuses material and
   crew lines and parts; `change_status` refuses project statuses. The
   calendar, the timelines, the calendar API (`schedule/views.py`,
   `schedule/api.py`), the project list, `/api/v1/projects` without `?kind=`
   and the coming projects of the start page leave cases out. The list of
   cases (`case_list`) filters by status (default open and in progress),
   "mine" and text, and counts mails in the same query.
4. **Converting** (`convert_to_project`): the project form asks for
   customer and periods; `kind` becomes `project`, the case status is
   emptied, the status is "inquiry", and `services.update_project` saves
   with all its checks. Number, mails, files, open items, follow-up and
   history stay.

### Show files (PRJ-089)

1. **The upload check** (`core.uploads.validate_document_upload`) lets a
   file through when its ending is a document ending (NFA-007) or a show
   file ending (`core.showfiles.is_showfile_name`). Compound endings
   (`.show.gz`) are found by the end of the name, the others by the last
   suffix. The refusal lists both sets. The size limit is
   `SystemSettings.max_upload_mb`.
2. **Type and console** (`projects.showfiles.prepare_upload`, called by
   `files.add_file` and when a mail attachment is taken over): a show file
   without document type gets the active type with `is_showfile`; the
   console follows from the ending where it is unambiguous
   (`guess_system`: `.esf3d` is Eos, `.dm7f` a DM7; `.shw` may be Hog 4,
   MagicQ or X32/M32 and stays empty; `.avc` is taken as Resolume Arena).
   The browser does the same while the file is chosen (`app.js`, block
   PRJ-089, `data-show-endings`) and shows the fields of a show file only
   for such a type.
3. **The current show:** a new show file of a console is the current one;
   `mark_current` takes the mark from the others of the same project and
   console (name compared without case), one save each. Editing a file can
   move the mark back. A file of another type keeps no show fields
   (`clean_show_fields`).
4. **The crew** sees show files on the Überblick: the type "Showfile" is
   visible to the crew (PRJ-007); the deployment API gives the show fields
   with the files. Files other than PDF, pictures and text are always
   downloaded (`document_response`), never opened in the browser.

---

## 22. The chat of a project

*Code: `rentalars/chat/` (`models.py`, `services.py`, `views.py`, `api.py`,
`templatetags/chat_tags.py`); `core/changes.py` (`_chat_stamp`);
`static/js/app.js` (block UIX-010). Catalogue: UIX-010.
Tests: `tests/{unit,ui,api,browser}/test_080_communication*`.*

1. **Who reads** (`readers_of`): every active user who can open the
   project – a role for all projects, or for assigned ones a membership
   (of a part its own, else the whole project's, PRJ-049) or a crew line
   (the deployment view, AUT-018). The same rules as `access_level`, for
   all users at once in four queries. The page lists them under "… Personen
   lesen mit", crew marked, and says that the crew reads along.
2. **Writing** (`post_message`): the text is trimmed and checked (not
   empty, at most 4,000 characters); the message stores the author's name
   as it is now. `mentioned_in` finds `@Name` or `@username` among the
   readers, longest names first, each found name blanked so that
   `@Anna Becker` does not also mention a user `anna`, and an `@` inside a
   word (an e-mail address) mentions nobody. The mentioned are stored and
   notified (`chat_mention`, link to `#m<id>`), the author's own read mark
   moves to the message. The view answers with the message list
   (`hx-target="#chat-messages"`) and the event `chatSent`, which empties
   the field.
3. **Changing and deleting** (`edit_message`, `delete_message`): only the
   author, within 15 minutes (`can_change`); a changed message gets
   `edited_at` ("geändert"), and only people mentioned anew are notified.
4. **Unread** (`ChatReadMark`): opening the chat moves the mark to the
   newest message (`mark_read`); messages of others after it are unread.
   (UIX-010) `POST …/chat/read` with
   `up_to` cannot mark future messages read: `mark_read` lowers
   `up_to` to the newest message **of that chat** not after it, the mark
   only moves forward (a guarded update, so two requests at once cannot
   move it back), and a value that is not a whole number ≥ 0 is 400
   (`ChatReadSerializer`).
5. **Following new messages without websockets** (UIX-020). Every project
   page watches `project:<pk>` and `chat:<pk>`
   (`changes.watch_keys`). The stamp of `chat:<pk>` is
   `<newest>-<count>-<last edit>~<unread>` (`chat.services.stamp`, one
   aggregate query; empty for a user who cannot open the project). The third part is the sum of `ChatMessage.revision`; the
   newest edit time in whole seconds (`int(timestamp())`) would miss a
   second edit within the same second and an edit of an older message;
   `edit_message` raises `revision` with an `F()` update. The
   script of every project page puts the unread part into the badge of the
   tab "Chat" and ignores `chat:` keys when it decides about reloading – a
   message is no change of the project. On the chat page itself a changed
   content part fetches `chat:messages` and replaces the list in place,
   unless a message is being changed (an open `details.chat-edit`); what is
   being typed stays, and the list stays at its end if it was there. The
   question is the one every page asks anyway every 20 seconds, so the chat
   costs no further polling.
6. **API** (`chat/api.py`): `GET`/`POST /projects/{id}/chat` (`?before=`,
   `?limit=` up to 500), `GET`/`PUT`/`PATCH`/`DELETE …/chat/{message}`,
   `GET`/`POST …/chat/read`, `GET …/chat/readers`. Writing needs read
   access to the module projects – the crew writes too; a read-only token
   only reads.

### Photos and videos (`media.py`, UIX-049, NFA-076)

*Code: `rentalars/chat/media.py`, `models.py` (`ChatAttachment`),
`services.py` (`post_message`), `views.py` (`media_file`), `api.py`;
`core/selfcheck.py` (`_ffmpeg`, `_nginx_body_size`); `deploy/lib.sh`
(`added_packages`, `install_added_packages`), `deploy/ai.sh`
(`refresh_packages`); `core/jobs.py` (the gate). Tests:
`tests/unit/test_092_chat_media.py`, `tests/unit/test_092_review_media.py`,
`tests/browser/test_092_chat_media_in_browser.py`, `tests/deploy/test_system.sh`.*

Decision: shrink on the server ("Auf dem Server verkleinern"); only the
small version is kept.

1. **Checking, in the request** (`prepare_files`, called by `post_message`
   before the message is saved): at most `MAX_FILES` (10) files and
   `MAX_MESSAGE_BYTES` (500 MB) together. Each file by its content, not its
   name. A **photo** (`_prepare_photo`): first its size in
   bytes (`MAX_PHOTO_BYTES`, 25 MB), then `Image.open` reads only the
   header – format and pixel count are checked by `_too_many_pixels`
   before `verify()` or any decoding: JPEG – MPO of a phone included – at
   most `MAX_JPEG_PIXELS` (150 megapixels, decoded with `draft`), PNG, GIF
   and WebP at most `MAX_PHOTO_PIXELS` (16 megapixels – they are decoded
   whole, 64 MB as RGBA; a 6 KB PNG of 7070 × 7070 pixels took 593 MB with
   the 50 megapixels allowed before), with a message to send larger ones
   as JPEG; Pillow's own `DecompressionBombError` stays as a net. HEIC and
   AVIF (an ISO brand in the first bytes) are refused with a message. A
   **video** must carry a known container signature in its first bytes
   (MP4/QuickTime, Matroska/WebM, AVI) and pass `ffprobe` with exactly
   that demuxer (`-f`) and `-protocol_whitelist file` – a playlist that
   would make ffmpeg read other files never gets that far –, at most
   200 MB and 20 minutes, where the length is the longest of the
   container's, the stream's and a Matroska stream tag's `DURATION`
   (`_duration`: the container alone could claim seconds for an hour).
   `stream_problem` (NFA-076) then refuses a picture above
   `MAX_VIDEO_SIDE` (4096) on either side, above `MAX_VIDEO_FPS` (240) or
   above `MAX_VIDEO_FRAMES` (72,000 – 20 minutes at 60 fps) frames,
   counted as the larger of `nb_frames` and rate × length. Without ffmpeg
   (`videos_possible`) a video is refused with a message; photos still
   work. Any refusal discards what was prepared.
2. **Photos** are made smaller at once (`shrink_photo`, which checks the
   pixels once more before decoding): a JPEG is decoded with `draft`,
   reduced as far as the scales 1/2, 1/4, 1/8 allow while its long side
   keeps at least `PHOTO_LONGEST_SIDE` (`draft_size` asks for the long side
   2048 and the short side in proportion – a panorama too), turned upright
   (`exif_transpose`), reduced to `PHOTO_LONGEST_SIDE` (2048) and a preview
   of 640, written as JPEG with the place (GPS) and the colour profile (at most 128 KB) as the only metadata; the
   preview has the profile only.
3. **Videos** are copied to `DATA_DIR/chat-videos/` under a random name
   (`_keep_upload`, which first removes leftovers older than
   `PENDING_DAYS` – two days – that no attachment waits for;
   `delete_old_sources`, also called by
   `run_daily_maintenance`).
4. **Storing** (`attach`, inside the transaction of the new message): one
   `ChatAttachment` per file – a photo `ready` with `file` and `thumbnail`
   below `MEDIA_ROOT/chat/<project>/`, a video `processing` with `source`;
   then `_start_conversion` starts a background job `chat_video` without a
   user, so nobody gets a "ready" notification. The message may have no
   text when it carries files.
5. **Converting** (`run_job` → `convert`): `nice -n 10 ffmpeg -nostdin`
   with a list of arguments (no shell), the same demuxer and protocol
   whitelist, the first video and audio stream, `-map_metadata -1`, scaled
   into 1280 × 720 (720 × 1280 upright, never larger), at most 30 fps,
   libx264 `veryfast` CRF 26 with `-maxrate 3M`, AAC 128k, `-t 1200`
   (never more than `MAX_VIDEO_SECONDS`, whatever the file claimed),
   `+faststart`, into a `.mp4.part` in the pending folder, at most
   `CONVERT_TIMEOUT` (one hour); then a poster frame (`_poster`), and
   `_store` moves the result into the media folder (no copy) and deletes
   the original. Each change raises the message's `revision`, so open
   chats refetch it (UIX-020).
   **One at a time** (NFA-076): the kind is registered with
   a gate, `register("chat_video", …, gate="rentalars.chat.media:conversion_slot")`.
   `core.jobs.run_job` claims the job and calls `_run_gated`:
   `conversion_slot` takes `fcntl.flock(LOCK_EX | LOCK_NB)` on
   `DATA_DIR/chat-videos.lock` (next to the pending folder, whose clean-up
   removes unknown files). Without the lock the job is put back to
   `queued` and the process ends; with it, the process runs the job and
   then claims the oldest waiting `chat_video` jobs one by one
   (`_claim_next`) before it lets go, and tries once more after letting go
   for a job queued in that moment. The kernel releases the lock when the
   process dies, so a crash leaves the waiting jobs to the minute timer
   (`run_waiting_jobs`). Every conversion takes one or two cores and a lot
   of memory for up to an hour; a memory limit for ffmpeg was left out
   (decisions.md).
6. **Failing** (`_fail`): a conversion error, the time limit or a missing
   ffmpeg sets `failed` with its reason, deletes the original and tells the
   author (`JOB_FINISHED`, "Video für den Chat von … fehlgeschlagen"); the
   job itself does not fail – only a disk that cannot be written is an
   error for the operators. A video still `processing` after `STUCK_AFTER`
   (three hours) lost its job (a restart) and is failed quietly when the
   chat is read (`expire_stuck`) – unless `_in_line` finds its job still
   `queued` or `running` (it waits for others), then only after
   `STUCK_IN_LINE_AFTER` (24 hours).
7. **Delivering** (`media_file` → `file_response`): only after the chat's
   read check of the project; through NGINX (`X-Accel-Redirect`, which
   also answers the range requests of a video player), inline, with
   `Content-Security-Policy: sandbox`, cacheable privately for a day.
   Deleting a message – or the project – deletes the files after the
   commit (`files_deleted`).

**Getting ffmpeg onto the servers** (NFA-076). `ffmpeg` is in
`system_packages` (installed by `install.sh`) and in `added_packages`, the
packages a version added. The update runs the *old* `update.sh`, which
only knows its own list; but it calls `ai.sh refresh` of the new release
after switching, and `refresh_packages` installs what the new `lib.sh`
names and the server lacks (`missing_added_packages`, `dpkg-query`),
with `apt-get -o DPkg::Lock::Timeout=120` – it waits up to two minutes
for a running package manager and only warns when it fails.
`update.sh` itself calls `install_added_packages` with the new version's
list (step 3). Nothing missing, nothing is done – also at every boot,
when `rentalars-ai-refresh.timer` runs `refresh`. The self-check warns
when ffmpeg is missing and when `client_max_body_size` of the NGINX site
is below a video plus 1 MB (the template has 510 MB).

---

## 23. Automations

*Code: `rentalars/automations/` (`models.py`, `engine.py`, `signals.py`,
`forms.py`, `views.py`, `api.py`); `mail/parsing.py`
(`automatic_reason`), `mail/fetching.py`, `projects/follow_up.py`,
`core/management/commands/run_jobs.py`, `run_daily_maintenance.py`.
Catalogue: ADM-013 (and the exception to EML-030). Tests:
`tests/{unit,ui,api,browser}/test_080_communication*`.*

**A rule** (Einstellungen → Automationen, `automations:list`) is one
trigger with its condition and one action. The form shows only the parts
that fit (`app.js`, `data-show-when`, `data-actions-of`,
`data-recipients-of`); without the script every part shows and
`Automation.problems` – which the API calls as well – says what does not
fit. `normalise()` drops what does not belong to the chosen trigger and
action before saving.

**1. The event.** Four places hand an `Event` to `engine.fire`:

| Trigger | Where | Event key |
|---|---|---|
| `inquiry` – a mail without project tag | `mail.fetching`, right after the mail was noted as an inquiry (`inquiry_arrived`) | `mail:<hash of the Message-ID>` – the same mail in two mailboxes is one event |
| `project_status` | `post_save` of `Project` (`automations.signals`): created with a status, or saved with another one; the former value from the change log's snapshot (`_audit_before`), so every path counts – form, API, packing, a reply mail | `status:<project>:<status>:<time>:<random>` – every change is an event |
| `crew_answer` | `post_save` of `CrewLine` when `request_status` became accepted or declined | `answer:<line>:<answer>:<time of the answer>` |
| `follow_up` | `follow_up.notify_due_follow_ups` (minute timer), once with the notification | `follow_up:<project>:<day>:<user>` |

Each first asks whether an active rule of its trigger exists (one cheap
query) and does nothing otherwise. The values of the placeholders are
taken in one language (`translation.override`) and stored with the run –
the language of the company's documents
(`engine._language`), because automations write to customers. There are also the triggers of service cases (section 32).

**2. Recording** (`fire`): for every active rule of the trigger whose
condition holds (`_matches`: the mailbox, the status, the answer) an
`AutomationRun` is saved in a savepoint – the unique constraint
(`automation`, `event_key`) refuses a second run of the same rule for the
same event, which is skipped. This happens **inside the transaction of the
change**: a change that is rolled back runs nothing. `fire` never raises;
a problem is logged and the change goes on.

**3. Running after the commit:** `transaction.on_commit(run_pending(ids))`
carries the runs out at once. `run_pending` claims each run with a
conditional `update` (`pending` → `running`); a run another process
claimed is left alone. The minute timer (`run_jobs`,
`_run_pending_automations`) carries out what is still waiting, e.g. after
a restart. A run left "running" for 10 minutes (`STALE_AFTER`) was
interrupted: it is marked failed – "Unterbrochen. Nicht wiederholt, damit
nichts doppelt hinausgeht." – and never repeated. The action runs as the actor
"Automation „<Name>“" (`acting_as`), so the change log names the rule.
Every run ends `done`, `skipped` (with the reason) or `failed` (with the
error); the list under Einstellungen → Automationen shows them, and the
daily maintenance deletes runs older than 365 days.

**4. The actions:**

- **Answer the mail** (`_reply`, only for `inquiry`). First
  `no_answer_reason`: a mail marked automatic (`headers.automatic`, from
  `mail.parsing.automatic_reason` – `Auto-Submitted` other than "no",
  `Precedence` bulk/junk/list/auto_reply, `List-Id`, `List-Unsubscribe`,
  `X-Autoreply`, `X-Autorespond`, `X-Auto-Response-Suppress` with all/oof/
  autoreply, an empty `Return-Path`, `multipart/report`; an unreadable
  header counts as automatic); a sender or `Reply-To` whose local part is
  mailer-daemon, postmaster, no-reply, do-not-reply, bounce, daemon,
  listserv or majordomo; an own address (`own_addresses`: the mailboxes,
  `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, the company's address); no address
  to answer. Then `answered_today`: a done answer of this rule to this
  address since local midnight. The answer goes through the mailbox the
  mail came into if it can send, else the one that sends the
  correspondence (`_sending_mailbox`); to `Reply-To`, else the sender;
  subject from the rule, else "AW: <subject>"; with
  `Auto-Submitted: auto-replied` and `X-Auto-Response-Suppress: All`
  (RFC 3834), `In-Reply-To` and `References`, and the footer of EML-045.
  It is noted in the mail log as kind `automatic`.
- **Notify a person** (`_notify`): the chosen user, the project manager,
  whoever asked for the deployment (`requested_by`) or the user of the
  follow-up – active users only – with the kind `automation`, the rule's
  subject (else the event) and text, a link to the project or to Projekte
  → Anfragen.
- **Note an open item** (`_open_item`): `course.add_open_items` with the
  filled text (at most 250 characters).

**Placeholders** (`PLACEHOLDERS`, listed in the form): for every rule
`{firma}`, `{datum}`; for an inquiry `{name}`, `{absender}`, `{betreff}`,
`{postfach}`; for project triggers `{projekt}`, `{projektnummer}`,
`{projektname}`, `{status}`, `{projektleitung}`, `{link}`; for an answer
`{person}`, `{antwort}`, `{funktion}`, `{einsatz}`, `{anmerkung}`; for a
follow-up `{wiedervorlage}`, `{notiz}`, `{fuer}`. An unknown placeholder
stays as typed.

**Deleting a mailbox** switches its rules off first (`pre_delete`), so a
rule "only this mailbox" never answers all of them (EML-046).

### The rules that came with Rentalars (ADM-019)

*Code: `rentalars/automations/defaults.py`, `models.py`
(`default_key`, `is_default`, `default_changed`), `views.py`
(`automation_restore_defaults`), `api.py` (`restore_defaults`),
`list_tables.py`, `migrations/0004_default_keys_093.py`. Tests:
`tests/unit/test_093_automations.py`,
`tests/browser/test_093_automations_in_browser.py`.*

Four rules come with Rentalars: the three of the service cases (section
32) and "Defektmeldung → Servicefall" (MAT-057). They are edited,
switched and deleted like any rule, with the same checks and the change
log.

1. **Known by a key, not by name.** `Automation.default_key`
   (`case_closing_due`, `case_closing_communication`, `case_backlog_due`,
   `defect_case`; unique, null for own rules). Names are translated and
   editable, so they cannot identify a default. The update gave the keys
   to existing rules without a creator, by German or English name first,
   then by trigger, condition and action; it created nothing.
2. **"geändert".** `defaults.is_changed(rule)` compares the stored values
   (`DefaultAutomation.values()`: trigger, mailbox, status, answer,
   communication, action, recipient, user, new case status, subject,
   text) with how the rule came; the name counts as unchanged in German or
   English, and switching off is no change. The list shows "Standard" and
   "geändert" and the column "Herkunft"; the form a note; the API
   `default_key` and `default_changed` (read-only).
3. **Restoring.** `defaults.missing()` lists the keys not present;
   `restore(user)` creates each as it came – active, named in the
   installation's language, `created_by` the user – each in its own
   savepoint, so two people restoring at once make each rule once (the
   unique key refuses the second, which is skipped). Rules that are there,
   changed or not, stay as they are; an own rule with a default's name is
   no default. Browser: `POST /administration/automations/restore-defaults/`
   (shown with a question naming the rules only while one is missing);
   API: `POST /automations/restore-defaults` (201 with the created rules,
   200 with an empty list). Both need write access to the settings.
4. **Nothing else creates or overwrites them**: the squashed migration
   that brought them to a new database ran once, the start data
   (`core.defaults.install_defaults`) and a start do not touch
   automations. A later version that ships a different default must give
   it a new key, so that `is_changed` keeps telling changed rules from
   shipped ones.

---

## 24. Route links, maps and trips

*Code: `rentalars/core/maps.py`, `geocoding.py`, `map_views.py`,
`map_api.py`, `templatetags/maps.py`, `middleware.py`
(`ContentSecurityPolicyMiddleware`), `config.py` (`[maps]`);
`rentalars/projects/trips.py`, `trip_api.py`, `templatetags/trips.py`;
templates `core/_map_box.html`, `core/_map.html`, `projects/_trips.html`;
`static/js/app.js` (block UIX-034, PRJ-097); `static/vendor/leaflet/`.
Catalogue: UIX-033, UIX-034, PRJ-097, NFA-050. Tests:
`tests/{unit,ui,api,browser}/test_080_maps*`; `tests/geocoder_fake.py`
stands in for Nominatim.*

**A route link** (UIX-033, `maps.route_url(destination, *,
waypoints=())`, tag `{% route_link destination label %}`):
`https://www.google.com/maps/dir/?api=1&destination=…&waypoints=…`, at
most nine stops (`MAX_WAYPOINTS`), opened in a new tab with
`rel="noopener noreferrer"`. It is a plain link: the address leaves
Rentalars only with the click. **No link names a start** – Google Maps
then starts where the viewer is. The `origin` parameter of `route_url` and
of `Place` is removed, not ignored, and the tag `warehouse_address` is
gone; web, API (`route_url` fields), admin and trips alike.

**A map** (UIX-034) belongs to a target – `venue`, `customer` (with its
further addresses), `supplier`, `company` (with the warehouse), `project`
(the places of its trips) – and is shown in four steps:

1. **The box** (`{% map_box target pk %}`): empty when `[maps] tile_url`
   is empty. Otherwise it adds the origin of the tile server to
   `request.csp_image_sources` – `ContentSecurityPolicyMiddleware` then
   allows images from it on this page, and only on pages with a map
   (`tile_origin`; `{s}` becomes a wildcard for sub-domains) – and renders
   the button "Karte anzeigen" with the hint that only the click sends the
   address to OpenStreetMap. With "Karten sofort laden" the box fetches the
   map at once (`hx-trigger="load"`).
2. **The click** fetches `core:map` (`map_views.map_part`): `map_for`
   checks the right to see the target (venues and customers need read
   access to customers; a supplier to projects, material or settings; the
   company to settings; a project the deployment view) and collects its
   `Place`s; `locate` fills in the positions.
3. **Positions, once per address** (`locate`): `attach_positions` reads
   the kept rows of every address of the map in one query (key: SHA-256 of
   the address with spaces and case normalised). For addresses without a
   row the server asks the geocoder (`geocoding.look_up`) – at most 5 per
   opening (`LOOKUPS_PER_REQUEST`) and 15 seconds (`LOOKUP_BUDGET_SECONDS`);
   the rest is asked at the next opening, which the map says. Each answer
   is stored, "not found" too, so no address is asked twice; a network
   error, a 429 or a broken answer is shown on the map and stores nothing.
   Without `geocoder_url` positions are set by hand only.
4. **Drawing:** `core/_map.html` lists every place with its route link and
   the source of its position; `data-map` carries the places, the tile
   template, attribution, maximum zoom and where Leaflet lies. The script
   loads `static/vendor/leaflet/leaflet.js` and `.css` from this server the
   first time a map is shown, then the browser fetches the tiles. The wheel
   zooms only while the map has the focus. (UIX-034, line 9 of
   the user's message: "Access blocked 403 … tile usage policy") the tile
   layer is created with `referrerPolicy` from `data-map`
   (`map_data["referrerPolicy"]` = `TILE_REFERRER_POLICY`,
   `"strict-origin-when-cross-origin"`; the same value is the fallback in
   `app.js`): the page's `Referrer-Policy: same-origin` had left the tile
   requests without a Referer, which the OSM policy requires. The tile
   server now learns the installation's origin – only after "Karte
   anzeigen". A browser test checks the Referer the tile request carries
   (empty with `same-origin`).

**The geocoder's rules** (Nominatim usage policy, `geocoding.py`): one
request per second for the whole installation – `_wait_turn` keeps the
time of the last request in `DATA_DIR/geocoder.lock`, locked with `flock`
while it is read and written, because the gunicorn workers are separate
processes (without a writable data directory a thread lock of the process
remains) –; a User-Agent `Rentalars/<version> (maps)`,
`Rentalars/<version> (maps; +<scheme>://<host>)` from `[rentalars] url`
(`user_agent()`; never a path or credentials; without a usable URL the
short form); no redirects followed; at most 256 KB of answer and 10
seconds; no search while typing. The rest of the OSM policy was checked:
attribution linking to /copyright, tiles only after the click,
no bulk or prefetch, normal browser caching (no service worker, no
no-cache headers).
`_send` is the only place that touches the network; tests replace it.

**Correcting a position** ("Position korrigieren", `map_position`,
`PUT /maps/{target}/{id}/positions/{key}`): latitude and longitude typed,
or set by a click into the map or by dragging the marker, which fill the
same fields; decimal comma accepted, ranges ±90/±180. `set_position` needs
`can_correct` – write access to customers for a venue or a customer (not
an anonymised one), the right to create suppliers for a supplier
(`may_create_supplier`), write access to settings for the company, edit
access for a project –, replaces what was found with `manual`, and records
the event "Position auf der Karte von Hand gesetzt: …" at the record. "Neu
suchen lassen" (`forget_position`, `DELETE`) deletes the row, so the next
opening asks again. The position holds for every record with the same
address text.

**Clean-up:** anonymising a customer deletes the positions of its
addresses at once (`forget_addresses`); the daily maintenance deletes the
rows of addresses no venue, customer, address, supplier, company,
warehouse, project or phase uses any more (`delete_unused_positions`).

### The trips of a project (PRJ-097)

`trips.trips_of(project)` works the trips out from the phases (nothing is
stored), in the order of time:

| Phase | Trips |
|---|---|
| Aufbau, Abbau | warehouse → venue at the phase's start, venue → warehouse at its end |
| Packen (the first) | warehouse → every supplier of subrentals "wird beim Lieferanten abgeholt" → warehouse |
| Nachbereitung (the first) | the same round trip, to bring the material back |
| no Packen / no Nachbereitung | the pickup at the earliest start, the return at the latest end of those subrentals |

The suppliers are those of normal subrental lines with
`picked_up_at_supplier` and a supplier (`_pickups`; optional and
alternative lines are left out). The venue of a phase is, in this order,
the venue of the phase, the venue of the project, the place typed into the
phase, the venue typed into the project, the delivery address
(`_venue_of`). Each trip has a route link with stops and destination
(without start – `Trip.origin` stays for display, API and
map), and `problems` naming what is missing (the warehouse address, a
supplier without address, a venue). No distance is computed. The
Zeitplanung shows the trips with the problems and a map of the project's
places (`places_of`: each address once); the Überblick shows them to the
crew without the problems. `GET /projects/{id}/trips` needs the
deployment view.

**Adjusting trips (PRJ-111,;** `trip_changes.py`,
`trip_forms.py`, `trip_views.py`, `trip_api.py`, `_trip_form.html`). The
computed trips stay the default; `TripAdjustment` rows override them per
project (data-model). `trips_of` applies them after computing – one more
query, bounded (`test_080_maps.TripTests.test_bounded_queries`: 3 → 4):

1. Each computed trip has a `key` (`to_venue-<phase>`, `from_venue-<phase>`,
   `pickup`, `return`); an adjustment with that `trip_key` replaces the
   fields it fills (`title`, `start`, `origin`, `stops`, `destination`,
   `note`) and marks the trip `is_changed`; with `is_removed` the trip is
   left out (listed under "Entfernte Fahrten" for editors,
   `?removed=true` in the API). An adjustment whose trip no longer exists
   (its phase was removed) changes nothing. Adjustments with an empty key
   are own trips (`is_own`, kind `own`, key `own-<id>`).
2. `change_trip` stores only what differs from the computed trip, so
   untouched values keep following the phases; a change that ends equal
   deletes the adjustment. `remove_trip` sets `is_removed` (an own trip is
   deleted); `reset_trip` deletes the adjustment, bringing a removed trip
   back; `add_trip` needs departure, start and destination.
3. Every function first calls `_lock`: `ensure_editable` (a closed project
   refuses, PRJ-009) and `select_for_update` of the project row, so two
   planners cannot adjust the same trip at once. At most 9 stops. The views
   need edit access to the project; the API needs write access (removing
   too, not delete). The route link follows the adjustment.
4. Adjustments are audited in the project's history; they are not copied
   when a project is duplicated or divided.

---

## 25. Surcharges for night, Sunday and holidays

*Code: `rentalars/projects/time_surcharges.py`, `crew.py`
(`price_crew_line`, `defaults_from_job_function`, `surcharge_rules_for`),
`pricing.py`, `hour_tiers.py` (`local_days`, `planned_hours_per_day`);
`rentalars/core/holidays.py`, `surcharges.py`, `surcharge_presets.py`,
`surcharge_views.py`, `surcharge_api.py`, `models.py`
(`TimeSurchargeSettings`, `TimeSurchargeRule`, `OwnHoliday`);
`documents/content.py`; templates `core/time_surcharges.html`,
`core/_surcharge_rule.html`, `core/_own_holiday.html`,
`projects/_time_surcharges.html`. Catalogue: PER-009, PER-040. Tests: `tests/{unit,ui,api,browser}/test_080_surcharges*`,
`test_081_surcharges*`.*

The fixed kinds (night, night after midnight,
Sunday, holiday, high holiday) are **rules** from a list that works in any
country; the rules of § 3b EStG are one preset of that list and give
exactly the surcharges of the fixed kinds. The fixed
kinds are the `code` of the preset rules.

**Which lines.** A crew line gets surcharges on the price when
`time_surcharges_on_price` is set, on the costs when
`time_surcharges_on_cost` is set – and only when it is billed by plan or
by effort (`by_hour`); the costs not when the person has a flat rate.
`defaults_from_job_function` sets both switches of a new line from the
settings (`on_price`, `on_costs`) and the service product
(`Product.time_surcharges`); afterwards only the dialog changes them.

**The rules** (`SurchargeRules`, built by `SurchargeRules.from_rows` from
the settings row, the `TimeSurchargeRule` rows in their order and the
`OwnHoliday` rows; `current_rules` reads them through
`core.surcharges.load_rule_set` – at most three queries, once per request,
and only when a line needs them via `surcharge_rules_for(lines)`). The
first use installs the § 3b preset (`ensure_rules`, under a row lock), so
a new installation has it; afterwards an empty list means no surcharges.
Each `Rule` has a kind – `time` (a window `time_from`–`time_until`, over
midnight when it ends earlier; optionally `begun_before_midnight`),
`weekday` (ISO digits), `holiday` or `date` (day and month) – the day
kinds with an optional "from" time; a `price_percent`, a `cost_percent`
and its position. `next_day_until` (04:00 after § 3b, empty: never) says
until when a day rule of the previous day still holds for work begun
before midnight.

**Holidays** (`core.holidays.holidays_of(year, state)`, computed and kept
per year and state – no network): fixed days, the days that move with
Easter (Easter Sunday by the Gregorian computus), Repentance Day, and the
changes of the laws (Reformation Day in the north since 2018, Women's Day
in Berlin since 2019 and Mecklenburg-Western Pomerania since 2023, World
Children's Day in Thuringia since 2019 …). `calendar_of(year, state, german_holidays, own)` adds the own holidays –
yearly on a day, once on a date, or a number of days from Easter Sunday –
and leaves out the statutory ones when `german_holidays` is off.
`GET /holidays?year=&state=` and the settings page show them
(`holiday_rows`).

**Cutting a period into pieces** (`time_pieces`). The period is cut at
every local midnight, 04:00, 14:00 and every time of day a rule names
(`SurchargeRules.clocks`, `_boundaries`; both readings of a clock time the
change from summer time repeats). Each piece asks
`SurchargeRules.applying_at(day, clock, began_before_midnight)` at its
middle: the `time` rules whose window holds (a `begun_before_midnight`
rule only for work begun before that day's midnight – and if one holds,
it replaces the other time rules: 40 % instead of 25 %), and the day rules
that hold on the day from their "from" time – plus, for work begun before
midnight and before `next_day_until`, the day rules that held at the end
of the previous day (a Sunday reaches until 04:00 on Monday). The hours of
a piece are the hours that really pass. Example with the preset: Saturday
18:00 to Sunday 03:00 → Saturday 18–20 nothing, 20–24 Nacht, Sunday 0–3
Sonntag and Nacht 0–4 Uhr.

**Which percentages count** (`applying(rules, side)`, per side – price
and costs choose separately): the highest of the time rules adds to the
highest of the day rules; with equal percentages the rule further down the
list wins (`Rule.order`); 0 is none. Sunday 22:00 on a holiday: 25 % +
125 %.

**Hours by plan** (`planned_pieces`, for "nach Plan" and for "nach
Aufwand" while no time is approved): the planned hours per calendar day
are those of the hour tiers (`planned_hours_per_day`: the length of the
period on each day, or hand-typed hours spread evenly); within a day the
pieces share them in proportion to their length. Monday 08:00 to Tuesday
20:00 with 20 planned hours: 10 a day; Monday's 16 hours of period hold 4
night hours, so 2.5 of the 10 are night hours.

**Hours by effort** (`entry_pieces`): each approved time entry with its own
period, its hours (break taken off) spread over its pieces in proportion,
each piece with the rate fixed on the entry. The entry counts on the day
it starts, as the hour tiers count (PER-035).

**With hour tiers** (`_split_at_limit`): the hours of a day beyond the
limit are its last ones; a piece that crosses the limit is split. The
surcharge of an hour is a percentage of the rate of that hour – the price
up to the limit, the price from the limit beyond it; for planned cost the
person's rate or rate from the limit (guide values for an open place);
for actual cost the rate fixed on the entry, or the rate from the limit
beyond it.

**Adding up** (`surcharge_parts`): per kind the hours and hours × rate ×
percent / 100, rounded to cents per kind; `total_of` is their sum. A kind
(`SurchargePart`) is the rule's name and percentage – rules
with the same name and percentage are one part, so "Feiertag" (holidays
and 31 December from 14:00) and "Weihnachten und 1. Mai" (four date
rules) stay one line each; the API part carries
`rule`, `label` (the name) and `kind` (the fixed kind for preset rules,
`custom` otherwise). In
`price_crew_line` the price surcharges go into `base_amount` before the
line discount (the discount applies to them too), the planned cost
surcharges into `cost`, the actual ones into `actual_cost`. `CrewPrice`
keeps `time_surcharges`, `cost_time_surcharges` and
`actual_cost_time_surcharges` (lists of `SurchargePart`);
`ProjectPrices.personnel_time_surcharges` sums the price surcharges. The
planning shows "inkl. Zuschläge …" under amount and cost, the price
overview and its CSV likewise, a document in the details of the position
("inkl. Zuschläge 126,00 €: Nacht 25 % auf 4 Std. 45,00 €, …"), the API
`time_surcharges` per crew line and `totals.personnel_time_surcharges`.

**Live, not frozen:** the rules, the percentages, the holidays and the
state apply at once to every line that has surcharges, closed projects
included; a stored document stays as it was made (DOK-007).

**The § 3b button and the update**. "Nach § 3b EStG
einstellen" (`core.surcharges.set_section_3b`, `POST
settings/surcharges/section-3b`) replaces every rule by
`core.surcharge_presets.section_3b` and sets `next_day_until` 04:00;
state, own holidays and switches stay; each deleted and created rule is in
the change log. The update (`core/0015_surcharges_081`) turned the earlier
settings into the same rules with a frozen copy of the preset. A unit test
compares the rules against a frozen copy of the earlier calculation over
nine settings variants and fifteen periods (summer time, Christmas, New
Year, Easter, Corpus Christi, ties).

**The settings page** (`surcharge_views.py`): a formset of rule cards
(name, kind, both percentages, order, delete; the fields of the chosen
kind shown by `data-show-if`) and one of own holidays. One empty row works
without JavaScript; with it "Regel hinzufügen" clones a template row and
↑/↓ renumber `position` and announce the new place. The API takes `rules`
and `own_holidays` as lists that replace the stored ones (with `id`
updated, without created, missing deleted, order = rule order; errors as
`rules.N.field`).

---

## 26. Hints at times and expenses

*Code: `rentalars/timetracking/hints.py`; `expenses.py`, `expense_views.py`,
`expense_api.py`, `models.py` (`Expense`), `forms.py` (`ExpenseForm`),
`views.py` (approval, report), `export.py`, `pdf.py`; `projects/pricing.py`
(`expenses_cost`), `list_sums.py`. Catalogue: ZEI-018,
ZEI-019. Tests: `tests/{unit,ui,api,browser}/test_080_times*`.*

### Hints at conspicuous times (ZEI-018)

`hints_for(entries)` reads, in one query, the finished and not rejected
entries of the same people from two days before the earliest to two days
after the latest asked entry (`CONTEXT`), so that a working day and the
rest before it are complete whatever part of them the page shows. Per
person:

1. **Working days** (`working_days`): the entries in the order of their
   start; the next entry joins the current working day unless the gap
   before it is at least the rest limit (11 h), or at least 3 h
   (`NIGHT_GAP`) and it starts on another calendar day than the working day
   began. A night shift 22:00–06:00 is one day; 18:00–23:00 and
   00:30–03:00 are one day; the next morning is a new one.
2. **Hours and break** of a working day: the hours of its entries (the
   break already taken off); the break minutes of the entries plus every
   gap of at least 15 minutes between them (`SHORTEST_BREAK`, ArbZG § 4).
3. **Hints** (`hints_of_days`): "Langer Arbeitstag" above
   `time_hint_day_hours`; "Kurze Pause" when the hours exceed
   `time_hint_break_hours` (`…_long_break_hours`) and the break is shorter
   than `time_hint_break_minutes` (`…_long_break_minutes`) – both at every
   entry of the day; "Kurze Ruhezeit" at the first entry of a working day
   that starts less than `time_hint_rest_hours` after the previous one
   ended. A limit of 0 switches its hint off; with all off nothing is read.

The hints are attached (`attach_hints`) to the confirmation of the quick
entry, "Meine Zeiten", the approval and the report (filter "Nur Einträge
mit Hinweisen"), and go into the hours CSV (last column "Hinweise"), the
timesheet PDF and the API (`hints` with `kind` and `message`). Entries of
projects the reader cannot see count, but the hint names hours, never a
project. Nothing is blocked.

The parts of a divided period (section 7) are merged into one
span before step 1, so the break counts once. `SystemSettings.time_hints_enabled`
off (ZEI-018) switches everything off: nothing is read, the filter "Nur
Einträge mit Hinweisen" is gone, the CSV column stays empty and the API
answers `hints: []`; the limits are kept.

### Expenses (ZEI-019)

1. **Recording** (`create_expense`; "Spesen erfassen" under Mein Bereich →
   "Meine Spesen", after a recorded time, on the Überblick, or
   `POST /expenses`): the caller may record for the person
   (`may_record_for`: oneself, others with "approve times"); the person is
   active; the project is one the person may book on
   (`timetracking.services._may_book_on`, as for times) and neither closed
   nor cancelled; the date is not in the future. For a trip with
   kilometres `km_rate` is copied from the settings and `apply_kind` sets
   the amount; a trip without kilometres and every other kind need an
   amount. "Gleich zur Freigabe einreichen" (ticked by default) submits it
   at once.
2. **The receipt** (`prepare_receipt`): at most the upload limit; a file
   starting with `%PDF-` is stored as it came (`beleg.pdf`); otherwise
   Pillow must recognise a JPEG, PNG or MPO, which is turned upright by its
   EXIF orientation, reduced to 2,000 px on the long side and saved as JPEG
   by `render_photo_upload` (`beleg.jpg`; the place stays, the device and time go). Stored below `receipts/<person>/` under a random
   name; a replaced or removed receipt is deleted after the commit
   (`_remove_file_later`). On a phone the file field offers the camera
   (`accept="image/jpeg,image/png,application/pdf"`).
3. **Approval** – on the existing page "Freigeben", per project, next to
   the times and with the same buttons (`approve_expenses`,
   `reject_expenses` with a reason, `take_back_approval`), with "approve
   times" and sight of the project. Approved expenses are locked. Changing
   a sent-back expense makes it "recorded" again.
4. **Reimbursement** (`mark_reimbursed`, on Personal → "Spesen" or
   `POST /expenses/reimburse`): approved and not yet reimbursed expenses
   get `reimbursed_on` (today or a given past day) and `reimbursed_by`; a
   mistaken mark is taken back with `take_back_reimbursement`. Sent back
   and reimbursed expenses are told to the person (kind `expense`).
5. **Report** (`expense_report`, `/times/report/expenses/`, CSV): sums per
   month and person, "zu erstatten" (approved, not reimbursed); the tab
   "Spesen" under Personal for approvers, "Meine Spesen" for everyone.
6. **Costs of the project:** only approved expenses
   (`approved_expense_sums`, one query for many projects;
   `approved_expenses_total` as an annotation of the planning page's
   project query). `ProjectPrices.expenses_cost` reads them – or takes
   what the caller loaded – and `contribution_margin` subtracts them; the
   cost line in the planning totals and `totals.expenses_cost` in the API
   need the right for personnel costs.
7. **The way to work** (ZEI-027, `expenses.commute_deduction`): when a trip
   with kilometres is recorded or its project, kind, day or kilometres
   change, and `SystemSettings.expense_deduct_commute` is on and the
   person has `commute_km`, the allowance for that person, project and day
   is twice `commute_km` minus what the other trips of that day and
   project (in the order they were recorded) already deducted. The trip
   deducts up to its kilometres, stores it in `Expense.commute_km` and
   pays `(kilometres − commute_km) × km_rate`, possibly 0.00 €. Other trips
   are not recalculated when one is deleted (only ever in the person's
   favour). The rows show `distance_label` ("42 km − 28 km Arbeitsweg =
   14 km"); the CSV and the API carry `commute_km`.
8. **Lists**: Personal → Spesen and Meine Spesen are
   `core.tables` tables over computed rows
   (`timetracking/expense_list_tables.py`, sorted and grouped in Python);
   "CSV mit allen Spalten" on Personal → Spesen gives the columns of the
   former file, sorted by day, as `spesen-<date>.csv`.

---

## 27. Moving appointments in the timeline; invoices switched off

*Code: `rentalars/schedule/moves.py`, `move_views.py`, `move_api.py`,
`services.py` (`Bar.move`, `project_timeline(movable=…)`),
`course_timeline.py`; templates `schedule/_move_*.html`, `move.html`;
`static/js/app.js` (block VFG-026); `rentalars/documents/services.py`
(`invoices_enabled`, `check_invoices_enabled`, `makeable_kinds`),
`views.py`, `api.py`, `lexware.py`, `datev.py`, `accounting_views.py`,
`projects/templatetags/project_actions.py`. Catalogue:
VFG-026, DOK-014. Tests: `tests/{unit,ui,api,browser}/test_080_planning*`.*

### Dragging and its dialog (VFG-026)

1. **Which bars move** (`movable_project_ids`, `movable`): in hour columns
   only, the rental period, the event (Zeitplanung) and the phases of
   projects the user may edit and that are not closed – no query for a
   role on all projects, one for a role on assigned projects. Such a bar
   carries `data-tl-move` with its key, name and times (wall clock), and
   grips at its ends when they are in view.
2. **In the browser** (`app.js`): a mouse or pen drags the middle (move) or
   a grip (start or end), snapping to 15 minutes (`STEP`); a dashed frame
   with the new times follows. A finger scrolls. With the keyboard ←/→
   move a chosen bar by 15 minutes, with Shift only its end; the new times
   go to a live region (`data-tl-announce`); Enter opens the dialog,
   Escape takes the move back. Dropping opens the dialog `schedule:move`
   (`/schedule/move/<project>/?what=…&phase=…&start=…&end=…`); in the
   Zeitplanung a click on a bar opens it as well, with the times to type
   in.
3. **The preview** (`preview_move`): `check_move` (project not closed,
   end after start, the phase of this project, an event to move); then
   `_trial` runs `apply_move` – the real move with the real services – in
   `transaction.atomic()` and leaves it with an exception that carries the
   outcome out, so the transaction is rolled back. The trial moves the
   crew along, the schedule along and – where a phase would leave the
   rental period and the extension is possible – extends it, so that the
   dialog can offer each box with its consequences. Nothing leaves the
   database: notifications and mails are sent `on_commit`; webhooks and
   change log are rows of the same transaction. Around the trial the
   missing material (PRJ-012) of the project – and of the parts a whole
   project takes along – is counted before and after (`_shortage`, the
   planning's own calculation).
4. **The dialog** (`_move_dialog.html`, `_move_consequences.html`): old and
   new times of everything that moves (`PeriodChange`), the crew lines that
   move with who is asked again (PER-034) and their warnings (PRJ-022), the
   material lines with the old period that follow, the parts that move, the
   material missing before and after. Boxes: "Personal dieser Phase
   mitverschieben" for a phase (PRJ-080), "Veranstaltung, Phasen und
   Personal mitverschieben" for a rental period moved as a whole
   (`offers_schedule`: as long as before on the wall clock), both ticked,
   and the unticked "Mietzeitraum erweitern" for a phase beyond the rental
   period (PRJ-100; never for "Planungen und Besprechungen"). If the
   extension cannot be made, the dialog says why and shows the move
   without it.
5. **Saving** (`perform_move`, "Verschieben" or
   `POST /projects/{id}/reschedule`): `apply_move` in one transaction –
   a phase through `course.update_phase` (with `move_with_phase`), the
   rental period through `services.update_project` (lines with the old
   period follow; a whole project's parts move along when it moves as a
   whole, else must stay inside; a part stays within its whole project);
   with the schedule ticked, `_shift_schedule` moves event, phases with
   their crew and the crew without phase by the same wall-clock shift,
   also in the parts that moved; the event period alone through
   `update_project`. A new rental period tells the people of the project
   (`project_changed`, crew included). (PRJ-118) `apply_move`
   runs inside `crew_changes.one_notice_per_person()`: every planned
   person whose lines moved gets one "Änderung meines Einsatzes" naming
   all of them, and `project_changed(…, crew_told=…)` leaves those people
   out of the crew told "neuer Zeitraum …", so nobody gets both. The
   dialog's close reloads the page, and the focus returns to the bar.

### People dragged on Zeitplanung (PRJ-121)

*Code: `schedule/course_timeline.py`, `moves.py` (`followers_of`,
`Followers`, `followed_phase_times`, `_move_crew_line`, `_phase_follows`,
`_suggestion_for_follower`), `move_views.py`, `move_api.py`; templates
`schedule/_move_consequences.html`, `_move_extension.html`. Tests:
`tests/unit/test_092_projects.py`, `tests/browser/test_092_timeline_in_browser.py`.*

Every crew bar – a person or an open
place – carries `data-tl-move` like the phases (`moves.movable(…, CREW,
crew_line=…, origin="course")`), for whoever may edit the project; the
dialog posts `from=course`, and only then does the move offer `follow`
(the personnel plan sends nothing, so nothing follows there).

1. **What would follow** (`followers_of(line)`, two queries at most):
   nothing for an open place; **the phase**, when the line has a person
   and no other line of its phase has one (open places do not count);
   otherwise **the open places** of the same job function in the same
   phase – or, for a line without phase, among those without phase – with
   exactly the same start and end, provided no other line among those has
   a person. `Followers.label` and `reason` give the box and its "why"
   ("Die Phase „Aufbau“ wird mitverschoben, weil Anna Becker die einzige
   Person darin ist.").
2. **The phase follows** (`_phase_follows`) through `course.update_phase`
   with `move_crew=True`, so its open places and vehicle bookings move as
   if the phase had been dragged (`outcome.vehicle_lines`). The new times
   come from `followed_phase_times`: a line with exactly the phase's period
   gives the phase the new period; a line with times of its own moves the
   phase by the wall-clock shift of its start – a changed end alone leaves
   the phase. A phase that then leaves the rental period gets the box
   "Mietzeitraum erweitern" of PRJ-100 (`_suggestion_for_follower` in the
   trial, `_extend_for` on saving), never for "Planungen und
   Besprechungen".
3. **The open places follow** through `crew.update_crew_line` with the new
   times of the line.
4. **The line itself** goes through `update_crew_line` as in the personnel
   plan (hours, asking again, warnings). All of it runs in the rolled-back
   trial for the dialog first (`preview.followers`, `offers_follow`; the
   box is ticked), then for real inside `one_notice_per_person()`, so each
   person gets one message (PRJ-118). The API takes `follow` in
   `POST /projects/{id}/reschedule` for a crew line; without it nothing
   follows.

### Invoices switched off (DOK-014)

`documents.services.invoices_enabled()` reads
`SystemSettings.invoices_enabled` (cached per request). Off:

- `makeable_kinds()` drops invoice and cancellation: the tab "Dokumente"
  offers neither; `check_can_make` and the draft refuse them with
  `invoices_off_message()`; the view checks the posted kind first, so the
  message is that, not "not a valid choice"; the API answers 400.
- `cancel_invoice` refuses a cancellation as well (12.2 number 24 i).
- The head of a project (`project_actions`) neither suggests nor lists an
  invoice – also not for a returned or closed project.
- The page Einstellungen → Buchhaltung hides the hand-over to Lexware
  Office and the DATEV export; `lexware.request_transfer` and the DATEV
  export refuse (`check_invoices_enabled`, 400 in the API). A hand-over
  queued before still runs.
- Invoices made before stay readable, downloadable and sendable with
  their state in Lexware Office. Closing a project never needed an
  invoice.
- (DOK-055) the bookkeeping is hidden as a whole.
  `documents/bookkeeping.py` lists the page names (`PAGES`) and API names
  (`API`) that are bookkeeping – incoming documents, payments, open items,
  bank, EÜR, archive, asset register, sales from stock, import of old
  projects. `bookkeeping_on()` (= `invoices_enabled()`) drives: the
  navigation (`Section.bookkeeping`, `entries_for(bookkeeping=…)` from the
  context processor), the tabs (`outgoing.tabs`), the template variable
  `bookkeeping_on` for the links elsewhere, and `BookkeepingMiddleware`
  (`process_view`): a listed address answers with a redirect to the start page
  and a message, or with 400 `accounting_disabled` in the API – except for
  a caller who is not logged in. The test `test_115_bookkeeping` fails for any
  page under `accounting/` that is neither listed nor on its list of what stays.

---

## 28. The Raspberry Pi in the server scripts

*Code: `deploy/lib.sh` (section "The system and the device"),
`install.sh`, `update.sh`, `deploy/rentalars` (`status`),
`move-database.sh`; `rentalars/core/selfcheck.py`. Catalogue:
NFA-070 (with NFA-063, NFA-042). Tests: `tests/deploy/test_system.sh`
(66 cases with made-up files), run by `tests/unit/test_080_pi.py` and
`scripts/check.sh`. Operators' guide: `docs/betrieb/installation.md`,
section "Raspberry Pi".*

Every function takes the files it reads as arguments, so the test hands
it made-up `/etc/os-release`, `/proc/device-tree/model`, `/proc/meminfo`
and `/sys/dev/block`.

1. **Check before anything changes** – `install.sh` calls
   `check_system OS_RELEASE MODEL "$(dpkg --print-architecture)"` before
   `apt-get update`. The architecture is that of the installed packages: a
   32-bit system (armhf, armel, i386) is refused everywhere, on a Pi with
   the advice to install "Raspberry Pi OS Lite (64-bit)" or Ubuntu Server.
   `ID=ubuntu` from 24.04 on (a newer untried version gets a note, as); `ID=debian` or `raspbian` only when the model file starts with
   "Raspberry Pi" (`is_raspberry_pi`), from Debian 13 on (12 refused for its
   Python 3.11; 14 or testing noted as untried); anything else refused. A
   Pi other than 4, 5, 400, 500, CM4, CM5 (`is_intended_raspberry_pi`)
   gets "nicht erprobt" and goes on. The result is in `SYSTEM_ID`,
   `SYSTEM_VERSION`, `SYSTEM_NAME`, `SYSTEM_ARCHITECTURE`, `SYSTEM_MODEL`,
   `SYSTEM_NOTE`.
2. **What the installer says on a Pi:** a line "Gerät: <model>, <memory>
   Arbeitsspeicher, <architecture>", a warning below 4 GB (MemTotal under
   3,500 MB, `FOUR_GB_IN_MB` – a "4 GB" Pi shows about 3.7 GB) and a warning
   when the database (if local), the data folder or the backups would lie
   on the SD card – both before the confirmation question.
3. **Packages** (`system_packages SYSTEM_ID LOCAL_DATABASE TLS_MODE
   DNS_PLUGIN`): one list for Ubuntu and Debian 13 – the names are the same
   –, with `mariadb-server` for a local database, `certbot` for Let's
   Encrypt or DNS, and the DNS plugin.
4. **Sizing** (NFA-042, only on a Pi, `sizing_for_memory`): from 3,500 MB
   nothing changes (5 workers, `innodb_buffer_pool_size` 1G); 1,500 to
   3,500 MB "3 512M"; below "2 256M". `adapt_workers` sets `--workers`
   with `sed` on the installed `rentalars.service` at every
   `install_units` (install, update, rollback);
   `write_database_memory_settings` writes
   `/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf` (read after
   `60-rentalars.cnf`) or removes it from 4 GB on – at installation before
   MariaDB starts, at every `refresh_server_configuration`, and when
   `move-database.sh` sets up a local MariaDB. It takes effect at the next
   start of MariaDB.
5. **SD card** (`storage_devices`, `places_on_sd_card`): `findmnt` gives
   the device number of the folder's file system; `/sys/dev/block/MAJ:MIN`
   leads to the device, its `slaves` through LUKS and LVM; any `mmcblk*`
   counts (the eMMC of a Compute Module too). `installation_places_on_sd_card`
   checks the database (if local), the data folder and the backups – only
   on a Pi. `update.sh` notes it, `rentalars status` shows the rows "Gerät"
   and "auf der SD-Karte", the self-check (`selfcheck._raspberry_pi`,
   `_sd_card`) a device line in "Server" (a NOTE below 4 GB) and a NOTE in
   "Speicherplatz".
6. **Python libraries** come from PyPI as aarch64 wheels; `mysqlclient` is
   built against `libmariadb-dev`, which the package list brings on every
   system.

---

## 29. Data steps: showfiles, maps and times

*Code: the migrations named below. Tests: `tests/unit/test_080_projects.py`
calls the data step of `masterdata/0009_showfiles_080` on data shaped like
an older installation's and a second time; `tests/unit/test_080_surcharges.py`
(`MigrationTests`) migrates an older database forward and back.*

What `rentalars update` (one `migrate`, after the backup) does to the data
of an existing installation, in the order the dependencies allow. Only one
migration changes business data – `masterdata/0009_showfiles_080`, logged
with the actor "Aktualisierung" (the pattern of section 20); every
other one adds tables, columns or choices with defaults that change
nothing until somebody switches them on: surcharges, maps at once, the
pickup at a supplier are off, invoices on. Every migration was run on a
copy of an older SQLite database; MariaDB was not tried. Going back runs
no data step (`RunPython.noop`); the way back is the backup.

| Migration | Schema | Data |
|---|---|---|
| `mail/0008_automations_080` | `MailLogEntry.kind` offers `automatic` ("automatische Antwort") | – |
| `automations/0001_initial` | tables `Automation`, `AutomationRun` (constraint `automation_run_once`, index `automation_run_status_idx`) | – |
| `chat/0001_initial` | tables `ChatMessage` (with its table of mentions), `ChatReadMark` (constraint `chat_read_once`) | – |
| `core/0010_maps_080` | table `AddressPosition`; `CompanyProfile.warehouse_address` (empty: the company's address); `SystemSettings.maps_load_at_once` (off) | – (no address is asked for until a map is opened) |
| `core/0011_surcharges_080` | table `TimeSurchargeSettings` with the § 3b defaults; both switches off | – (the row is created on first use) |
| `core/0012_invoices_080` | `SystemSettings.invoices_enabled` (on) | – |
| `core/0013_times_080` | `SystemSettings.time_hint_day_hours` 10, `time_hint_break_hours` 6, `time_hint_break_minutes` 30, `time_hint_long_break_hours` 9, `time_hint_long_break_minutes` 45, `time_hint_rest_hours` 11, `expense_km_rate` 0.30 | – |
| `customers/0007_maps_080` | none – an empty step, so that the numbering is the same everywhere | – |
| `masterdata/0009_showfiles_080` | `DocumentType.is_showfile` | a type named "Showfile", "Showfiles", "Show-Datei" or "Show-Dateien" (case ignored, the oldest) is marked; otherwise "Showfile" is created – visible to the crew, active, with the position of "Sonstiges" (so it sorts right before it) or after the last. Logged as "Aktualisierung" where start data were installed; a second run finds the mark and does nothing. |
| `masterdata/0010_maps_080` | `Supplier.street`, `postal_code`, `city`, `country` (empty) | – (addresses in "Kontakt" or "Notiz" stay there) |
| `notifications/0005_chat_080` | `Notification.kind`, `Preference.kind` offer `chat_mention`, `automation` | – (who chose nothing gets both in the application and by e-mail) |
| `notifications/0006_expenses_080` | … and `expense` | – |
| `products/0007_surcharges_080` | `Product.time_surcharges` (on) | – (every product allows surcharges; none are switched on) |
| `projects/0019_service_cases_080` | `Project.kind` (`project`), `case_status`, `case_contact`, index `project_kind_case_status_idx`; `ProjectFile.show_system`, `show_version`, `is_current_show` | – (every project stays a project) |
| `projects/0020_trips_080` | `MaterialLine.picked_up_at_supplier` (off: the supplier delivers) | – |
| `projects/0021_surcharges_080` | `CrewLine.time_surcharges_on_price`, `time_surcharges_on_cost` (off) | – (no existing line gets surcharges; prices and costs stay to the cent) |
| `timetracking/0003_expenses_080` | table `Expense` (indexes `expense_person_date_idx`, `expense_project_status_idx`) | – |

Not a migration, but part of the same update: the automations run from
the minute timer that already runs (`rentalars-jobs.timer`), the daily
maintenance deletes old runs and unused positions, and on a Raspberry Pi
the update script of the *installed* release runs – an installation tried
on a Pi with less than 4 GB gets its sizing with a second
`rentalars update` from the same package (section 28).

---

## 30. Data steps: surcharge rules, hints and aliases

*Code: the migrations named below. Tests: `tests/unit/test_081_surcharges.py`
(the conversion against the preset, a migration on older data there and
back, and a frozen copy of the earlier calculation);
`tests/unit/test_081_notify.py` (the default "In der App").*

What `rentalars update` does to the data of an existing
installation. Only `core/0015_surcharges_081` changes business data –
logged as "Aktualisierung", with no reference logged as text (ADM-005);
`notifications/0007_categories_081`
changes user settings (not logged). Everything else adds tables or
columns that change nothing. No price, cost or sum of a project changes.
The migrations were run on copies of an older SQLite development
database (for the surcharges also comparing the personnel sums of every
project before and after); MariaDB was not tried.

| Migration | Schema | Data |
|---|---|---|
| `core/0014_hints_081` | `SystemSettings.time_hints_enabled`, `expense_deduct_commute` (both on) | – |
| `core/0015_surcharges_081` | tables `TimeSurchargeRule`, `OwnHoliday`; `TimeSurchargeSettings.german_holidays`, `next_day_until`, `rules_set_up`; the earlier fields `night_*`, `started_before_midnight`, `price_*`, `cost_*` removed | an existing settings row becomes rules with the same values (frozen copy of the § 3b preset: nine rules for the defaults, "Nacht 0–4 Uhr" only where `started_before_midnight` was on), `next_day_until` 04:00 or empty, `german_holidays` on; one settings entry and one per rule in the change log where `defaults_installed`; no row: nothing; idempotent; reversible from the rules' `code` |
| `core/0016_tables_081` | none – an empty step (grouping stores nothing) | – |
| `mail/0009_aliases_081` | table `MailboxAddress` (constraint `mail_alias_unique_address`); `UnknownTagMail.address`; choices `after_assignment` `read`, `MailLogEntry.result` `not_sent`, `ProjectMail.assigned_by` `new_case`; help text of `process_untagged` | – |
| `notifications/0007_categories_081` | `Preference.companion`, `Notification.companion` | stored preferences of `deployment_request`, `chat_mention`, `follow_up` get `companion` on unless that kind was switched off completely (frozen `COMPANION_KINDS`); existing notifications off |
| `personnel/0011_commute_081` | `Person.commute_km` (empty) | – |
| `personnel/0012_availability_081` | none – an empty step (PER-039 stores nothing) | – |
| `projects/0022_followups_081` | `Project.follow_up_at` (empty) | – (follow-ups remind in the morning as before) |
| `projects/0023_participants_081` | table `ServiceCaseParticipant` (constraint `service_case_participant_unique`) | – |
| `timetracking/0004_expenses_081` | `Expense.commute_km` (empty); the amount validator allows 0 | – (no amount changes) |
| `timetracking/0005_shares_081` | `TimeEntry.period_key` (empty) | – (hours unchanged) |

No new timer: the reminder of a follow-up with a time is sent by the
minute timer that already runs (`rentalars-jobs.timer`).

---

## 31. Data steps: packlist sync, mail cutoff and chat

*Code: the migrations named below. Tests: `tests/unit/test_082_sync.py`
(the packlists made for confirmed projects, in a `TransactionTestCase`),
`tests/unit/test_082_mail_maps.py` (the cutoff), `tests/unit/test_082_security.py`,
`tests/unit/test_082_project.py`.*

What `rentalars update` does to the data of an existing
installation. Business data change in `packing/0006_sync_082` (main
packlists created) and `mail/0010_cutoff_082` (the cutoff set) – both
logged as "Aktualisierung" with IDs, never texts; `chat/0002_reads_082`
changes read marks (not logged, chat is not business data). Everything else
adds tables or columns. No price, cost or sum of a project changes. A
second run changes nothing. The migrations were run on copies of an older
SQLite development database (forward, back, forward for the mail step);
MariaDB was not tried.

| Migration | Schema | Data |
|---|---|---|
| `api/0003_safeguards_082` | table `api_writelock` (`WriteLock`); help text of `Webhook.url` | – (older stored idempotent answers are keyed differently, never matched again, and expire with the daily maintenance) |
| `chat/0002_reads_082` | `ChatMessage.revision` (0) | messages with `edited_at` get `revision` 1; read marks beyond the newest message of their chat are lowered to it (0 for an empty chat); not reversed going back |
| `mail/0010_cutoff_082` | `Mailbox.untagged_since`, `untagged_unread_only`; the same on `MailboxAddress` | `untagged_since` = the moment of the update for every mailbox with `process_untagged` and every address whose `untagged` is not `ignore`; "only unread" off; one change-log entry each (`untagged_since: [null, iso]`, an address with its mailbox as parent); going back drops the fields |
| `packing/0006_sync_082` | `PackEntry.version` (0); table `SyncReceipt` (constraint `sync_receipt_once`); added dependencies on projects 0023, core 0016, contenttypes and the user model | every `confirmed_open`, `confirmed` or `out` project without a packlist gets an empty, open main packlist, logged as "Aktualisierung" (`project`, `status`, the project as parent); idempotent |
| `projects/0024_trips_082` | table `TripAdjustment` | – (service cases without customer stay valid) |

In the configuration file, both optional: `allow_http` under `[rentalars]` and the section
`[network]` with `allow_internal` (`deploy/rentalars.conf.example`); a
production configuration with an `http://` URL and without `allow_http =
yes` stops the start – and so the update, which rolls back. Settings that
point into the internal network are kept; the self-check names them.

---

## 32. Service case statuses with a follow-up

*Code: `rentalars/projects/service_cases.py` (`set_case_status`,
`FOLLOW_UP_STATUSES`, `ACTIVE_STATUSES`, `off_dashboards`),
`projects/follow_up.py` (`notify_due_follow_ups`, `_closing_rule_active`,
`clear_follow_up`), `projects/case_views.py`, `projects/case_api.py`,
`templates/projects/_case_status_form.html`; `automations/engine.py`
(`case_follow_up_due`, `case_communication`, `_case_status`,
`case_event_text`), `automations/signals.py`. Catalogue: PRJ-112, ADM-013,
PRJ-109. Tests: `tests/{unit,ui,api,browser}/test_083_cases*`.*

**The statuses.** `CaseStatus` is `open`, `in_progress`, `waiting`,
`closing`, `backlog`, `done`. The three in the middle need a follow-up:

| Status | Follow-up needs | `case_waiting_for` | Shown as |
|---|---|---|---|
| `waiting` | `follow_up_on` (time optional) | `reply`, `action` or `delivery` – required | "wartet auf Rückmeldung" / "Waiting for a reply" … |
| `closing` | `follow_up_on` and `follow_up_at` | – | "wartet auf Schließen" |
| `backlog` | `follow_up_on` (time optional) | – | "Rückstand" |

**Setting one** (`set_case_status(case, status, follow_up=…, waiting_for=…)`)
checks the follow-up first and raises a `ValidationError` per field, then
saves follow-up and status in one transaction; `case_waiting_for` is kept
only with `waiting`. In the browser, choosing one of the three in the
status list posts in the background; the server answers with the follow-up
dialog carrying the chosen status as a hidden field, and only sending the
dialog saves both (without the script: a page of its own); "Abbrechen"
puts the select back to the saved status. In the API, `PATCH
/service-cases/{id}` does the same in one call and answers 400 without the
follow-up. Moving the follow-up of a `closing` case keeps the time
required. "Erledigt" on the follow-up of a case in one of the three sets
it back to `open` with a message.

**Off the dashboards.** `off_dashboards()` is
`kind=service_case, case_status=backlog` and *not* `due_condition(now)` –
the same test that makes a follow-up due (6:00 of the day, or its time).
The start page (open items, "Meine Servicefälle"), Mein Bereich →
Servicefälle and Planung → Wiedervorlagen exclude it unless their filter
"(A|a)uch Rückstand" is ticked; Projekte → Servicefälle and
`GET /service-cases` default to `ACTIVE_STATUSES` (all but `done`) and
show it.

**The due follow-up** (minute timer, `notify_due_follow_ups`): a service
case's due follow-up is processed once (`follow_up_notified_at`) even when
nobody is to be notified; it fires `follow_up_due` (trigger `follow_up`)
and `case_follow_up_due` (trigger `case_follow_up`, event key
`case_follow_up:<case>:<day>:<user>[:<time>]`, data: status, waiting-for,
day and time). The notification is skipped when there is nobody – and for
a `closing` case while `_closing_rule_active()` (one query per run: an
active rule `case_follow_up` / `closing` / `case_status` / `done`).

**New communication** (`automations.signals`): `post_save` of a
`ProjectMail` in a service case – created, or moved into the case by hand
(the `project` changed) – with no `kind` (automatic replies and delivery
failures have one) fires `case_communication` with kind `mail_in` or
`mail_out`, key `case_communication:<case>:mail:<id>`; a created
`ChatMessage` fires it with kind `chat` (an edit does not). Nothing fires
while a rule is being carried out (`automation_running`), so a rule's own
mail or status change is never "communication". (EML-055) a
locked mail fires it with `locked=True` and without its subject: the run
keeps only the sender, and its texts say "Mail von … (mit Schloss)"
(section 8, "Messages with a lock").

**The action `case_status`** (`_case_status`) re-reads the case when the
run is carried out: another status than the event saw, or – for
`case_follow_up` – another follow-up day or time, makes the run `skipped`
with the reason; the same status is skipped too. Otherwise it calls
`set_case_status(case, new_case_status)` (only `open`, `in_progress`,
`done`) and, when a due follow-up closed the case, `clear_follow_up`.
Setting the status fires no event, so rules cannot set each other off. A
notification from a case rule without a title of its own is written per
recipient (`case_event_text` with `LocalText`); the run texts and the
placeholder values are written in the document language
(`engine._language`), like every automation.

**Example.** Case 2026-0057 is set to "wartet auf Schließen" with the
follow-up Fri 23.10.2026 16:00. Thu 15:12 the customer answers by mail:
rule 2 ("bei neuer Kommunikation wieder öffnen") sets the case to `open`;
the follow-up stays. Fri 16:00 the follow-up is due: the case is `open`,
not `closing`, so rule 1 has no matching run, and the follow-up person
gets the ordinary reminder. Had nobody written, Fri 16:00 rule 1 would
have closed the case (`done`), removed the follow-up and sent no reminder.

**Default rules** (`RULES` of `automations/0002_cases_083`, of
`automations/0001_squashed_0003_defects_085`, also for new installations): (1) `case_follow_up` + `closing` → `done`;
(2) `case_communication` + `closing` → `open`; (3) `case_follow_up` +
`backlog` → `open`. Active, named in the installation's language,
editable.

---

## 33. Changing the server address

*Code: `rentalars/core/server_address.py`, `address_models.py`,
`address_views.py`, `address_api.py`,
`core/management/commands/address_change.py`, `deploy/address.py`,
`deploy/rentalars` (`address`). Catalogue: ADM-016. Tests:
`tests/{unit,ui,api,browser}/test_083_address*`,
`tests/address_certificates.py`.*

1. **The page reads the present state** (`current_state`): `url` from the
   configuration, `server_name` and certificate paths from the NGINX site
   (`read_site`, readable by the service user), the certificate NGINX
   presents from a TLS handshake with 127.0.0.1:443
   (`presented_certificate` – the files are root-only).
2. **Prepare** (`prepare`, delete right on the Administration module):
   `normalise_host`; for an own certificate `check_certificate` (key
   matches, chain, names incl. one-label wildcards, expiry); `run_checks`
   – does the name resolve to an address of this server or the current
   name's (says when it cannot tell behind NAT), do ports 80/443 answer.
   An `AddressChange` with a random hex `token` is stored, uploaded files
   go to `<data_dir>/address/<token>/` (key Fernet-encrypted), an older open
   change becomes `superseded` and loses its files. The page shows
   `sudo rentalars address apply <token>` and `steps()`; `blocking_errors`
   are shown before anyone runs it.
3. **Apply** (operator, root): `deploy/address.py` runs
   `runuser -u rentalars -- … manage.py address_change export <token>`
   and reads JSON from its stdout only; it checks everything again, backs
   up to `/etc/rentalars/address-backup/<time>-<token>/`, gets the
   certificate (certbot webroot `--cert-name <host>`, openssl self-signed
   825 days, or the uploaded files) into `/etc/rentalars/tls/<host>/`,
   edits only the old name's `server_name` lines and the certificate lines
   of the site and `url`, adds or rewrites the redirect section for old
   names, `nginx -t`, `systemctl reload-or-restart nginx`,
   `systemctl restart rentalars`, waits for the socket, and fetches
   `https://<new host>/login/` through 127.0.0.1 with SNI, checking the
   presented certificate is the new one. Any failure: restore every file
   from the backup, reload, restart.
4. **Record:** `manage.py address_change record <token> --applied|--failed
   --by $SUDO_USER [--message …]`; the uploaded files are deleted after
   success. `--dry-run` prints the plan and the diff and records nothing.

---

## 34. Summarising the correspondence

*Code: `rentalars/ai/` (`overview.py`, `correspondence.py`, `summary.py`,
`client.py`, `local.py`, `drafts.py`, `views.py`, `api.py`,
`signals.py`), `templates/ai/`, `deploy/ai.sh`,
`deploy/systemd/rentalars-ai.service`. Catalogue: EML-040, EML-044,
ADM-017. Tests: `tests/{unit,ui,api,browser}/test_083_ai*`,
`tests/ai_fake.py`.*

**The short overview** (always): `overview.py` reads the project's mails
(a whole project: its parts the reader may see) and computes participants,
received/sent counts, first and last date, the last writer ("noch nicht
beantwortet" when the newest mail came in), dates in German, British, ISO
and month-name forms and euro amounts in the newest 200 mails, sentences
ending in "?" in the newest 3, and attachments.

**Which model answers** (`AISettings.summary_source`): `off` – the block
says who can switch it on; `local` – the address from
`/etc/rentalars/ai-local.conf` (loopback only; missing file: "not
installed"); `provider` – an `AIProvider`, called through
`core.network.open_url`.

**The job** (`ai_summary`): `correspondence.py` cuts every mail to its new
text (quotes and signature removed) and to 6,000 characters; the mails,
oldest first (and the chat, if included), are packed into parts that fit
the model's context (the provider's `context_tokens`, the local AI's
8,192, minus room for the prompt and the answer); each part is summarised,
then the summaries are packed and summarised again – up to 6 levels –
until one text remains. The prompt asks for the starter's interface
language. The result replaces the project's `AISummary` with the mail
count, newest mail id and date, `include_chat`, newest chat id, covered
parts, the number of parts and the duration. Each model call writes one
`AICall`.

**"veraltet"** is computed on display: mail count or newest mail id
differ, or – with the chat – a newer chat message exists. Deleting a
covered mail deletes the summary (`ai.signals`, also by retention and
anonymisation).

**The reply draft** (`ai_draft`, ADM-017): the thread of the mail being
answered, cut the same way, with a prompt to answer in that mail's
language and to write only the body; the result lands in the job's
`result.text` for its starter.

**The local AI** is the operator's: `deploy/ai.sh install` chooses the
model by memory (`choose_model`: below 1,500 MB none, below 6,000 MB
Qwen2.5 1.5B, else Qwen3 4B), threads = cores − 1 (1 to 8), `MemoryMax` 2G
or 5G, writes `ai-local.env` and `ai-local.conf`, enables the service and
sends a test prompt. "Geschwindigkeit messen" (`POST /ai/local/speed-test`)
stores tokens per second and seconds in `AISettings`.

**Details (EML-040, ADM-017):**

- **Model and threads:** `choose_model MEMORY CORES FAST` – below 1,500 MB
  none; Qwen3 4B only with ≥ 6,000 MB, ≥ 4 physical cores and `FAST` (x86-64
  with AVX2 and FMA, or a 64-bit ARM server that is not a Raspberry Pi);
  otherwise Qwen3 1.7B (`MemoryMax` 3G). Threads = physical cores (1 to
  16). `--model` switches, `--keep-model` keeps the old file, a built
  llama-server is kept unless `--rebuild`.
- **The job streams** (`client.chat(stream=True)`): server-sent events are
  read as they come; `Progress` turns llama-server's `prompt_progress`
  (`total`, `processed`) into "reads the mails … N %" and the written words
  into "writes … N words", written to the job at most every 2 s. A silence
  of 180 s (local) or the provider's `timeout_seconds` ends the call;
  before the first token the limit is `first_token_seconds` from the
  estimate. Thinking is switched off three ways (server flag, request
  fields, "/no_think") and stripped from the text.
- **Estimate and limit** (`ai/speed.py`): prompt tokens ≈ characters / 3;
  reading time from the measured reading speed, writing time from the
  writing speed and `max_tokens`; the block shows the estimate (a warning
  above 5 minutes) and the job's limit is 3 × the upper estimate (at least
  10 minutes; 3 hours without a measurement).
- **Speeds** are measured by the speed test (~400 prompt tokens,
  `cache_prompt: false`) and updated by every local call from `timings`
  (`prompt_per_second`, `predicted_per_second`), stored per call in
  `AICall` and as the latest in `AISettings`.
- **`ai refresh`** keeps an installation in step with the version
  ([architecture.md](architecture.md), "Commands that need root"): run by
  `update.sh` and by `rentalars-ai-refresh.timer` after boot and after an
  update enables the timers.

---

## 35. Data steps: service-case rules and AI

*Code: the migrations named below. Tests: `tests/unit/test_083_cases.py`
(the default rules, forward, back and again), `tests/unit/test_083_i18n.py`,
`tests/unit/test_083_address.py`, `tests/unit/test_083_ai.py`.*

What `rentalars update` does to the data of an existing
installation. Business data change only in `automations/0002_cases_083`
(three rules created, each logged "Aktualisierung" with its ID);
everything else adds tables or columns. No price, cost or sum of a
project changes; no status or name changes; a second run changes nothing.
The migrations were run on copies of an earlier SQLite development
database; MariaDB was not tried.

| Migration | Schema | Data |
|---|---|---|
| `accounts/0006_language_083` | `User.language` (`""`, also `db_default`) | – |
| `core/0017_language_083` | `CompanyProfile.document_language` | set to the installation's language (`de` unless `language = en`); not logged |
| `core/0018_address_083` | table `AddressChange` | – |
| `core/0019_ai_083` | – (empty on purpose) | – |
| `projects/0025_case_status_083` | `Project.case_waiting_for`; choices of `case_status` | – (no status changes) |
| `automations/0002_cases_083` | `Automation.communication`, `Automation.new_case_status`; added dependencies on core 0001 and contenttypes | three active rules (`RULES`), named in the installation's language; not added if a rule with the same trigger, status, action and new status exists; logged "Aktualisierung" (`name`, `is_active`, `trigger`, `status`, `action`, `new_case_status`) on an installation with `defaults_installed`; going back removes them if unchanged in name |
| `ai/0001_initial` | tables `AISettings`, `AIProvider`, `AISummary`, `AICall`; depends on `projects/0024_trips_082` | – (every use off) |

The package contains the Python library Markdown, `deploy/address.py`, `deploy/ai.sh`
and `deploy/systemd/rentalars-ai.service` (installed by `install_units`,
started only after `rentalars ai install`). The update itself runs the
installed updater, so its output is still German; the scripts of
the new version follow the operator's locale.

---

## 36. The younger change wins: projects and own data from the app

*Code: `rentalars/projects/field_changes.py`, `projects/models.py`
(`Project.save`, `refresh_from_db`), `projects/api.py`,
`projects/case_api.py`, `personnel/own_api.py`, `personnel/models.py`
(`Person.save`). Catalogue: PRJ-113, PRJ-114, API-015, API-016.
Tests: `tests/{unit,api}/test_084_companion*`,
`tests/ui/test_084_companion_pages.py`.*

The companion app changes projects, service cases and the own contact data
without network and sends them later; the customer's rule is "the younger
change wins", per field.

1. **Stamp on every save.** `Project.save()` calls
   `field_changes.stamp(project, update_fields)`: it takes the values as
   loaded (the audit module's load snapshot, refreshed by
   `refresh_from_db`) or as last saved – for a project built by hand its
   database row –, compares them with the values being written (only
   `update_fields` when given; moments as instants), and writes "now" (or
   the moment a call set with `changes_at`) for every key with a changed
   field into `field_changed_at`, starting from the moments stored now, so
   a moment set meanwhile by another change is kept. Keys: the API names;
   `follow_up` covers the four follow-up fields, `case_status` the status
   with `case_waiting_for`. Every route goes through `save()`: forms, API,
   automations, imports, status actions, the follow-up dialog, packing
   setting "out"/"returned", converting a case.
2. **A change with a moment** (`PATCH /projects/{id}` etc. with
   `changed_at`): `field_changes.locked(project)` takes the API-010 lock row
   `record:projects.project:<pk>` and the project row (`SELECT … FOR
   UPDATE`), then reads the clock; `parse_moment` reads the sent ISO 8601
   (with zone; a future moment becomes now); `judge` keeps the sent keys
   whose moment is later than the stored one (equal → server); the kept
   fields are validated and saved like a normal PATCH; `note` stores the
   sent moment for every kept key, also where the value did not change, so
   that a third device's later change still counts from it. The answer is
   the project as stored now with `applied` (the kept keys, in `TRACKED`
   order).
3. **Status and follow-up.** `POST /projects/{id}/status` with `changed_at`
   applies only if later; a transition no longer allowed when it arrives
   (the project was cancelled meanwhile) gives 409 `status_not_allowed`
   with the project and `applied: []`. `PUT`/`DELETE …/follow-up` judge the
   key `follow_up` (DELETE reads `changed_at` from the query or the body).
4. **Service cases** (`PATCH /service-cases/{id}`): `case_status_changed_at`
   judges status, `case_waiting_for` and the follow-up sent with it as one
   unit (a status that needs a follow-up never half-applies), `changed_at`
   judges each other field; no 409 – any status order is allowed.
5. **Own contact data** (`PATCH /people/me/profile`, API-015): the same rule
   for `phone`, `email`, `share_phone`, `share_email`, with the moments in
   `Person.*_changed_at` (set by `Person.save` for fields that really
   changed); `changed_at` is one moment or one per field; the person row is
   locked with the API-010 lock; validation is `OwnProfileForm`, as in the
   browser. Absences (`/people/me/absences`, 30 days back, with
   `Idempotency-Key`) and deployments (`/people/me/deployments`, the rows of
   "Meine Einsätze" from `projects/my_deployments.py`, `venue_of` as there)
   need no module right.

Without `changed_at` every route behaves as before (If-Match,
no `applied`). The new fields make every stored `ETag` stale once.

---

## 37. Shortage notifications on a schedule

*Code: `rentalars/core/notification_settings.py`,
`rentalars/notifications/schedule.py`, `notifications/services.py`
(`run_due_shortage_check`), `notifications/views.py`, `forms.py`, `api.py`,
`core/management/commands/run_jobs.py`. Catalogue: VFG-036.
Tests: `tests/{unit,ui,api,browser}/test_084_shortages*`.*

1. **The setting.** `NotificationSettings` (one row): interval
   (`daily`, `workdays`, `weekly` with `shortage_weekday`, `off`), time of
   day, lead weeks (1–26), `shortage_repeat`. Einstellungen →
   Benachrichtigungen and `GET`/`PATCH /settings/notifications` edit it;
   changing time, interval or weekday (`SCHEDULE_FIELDS`) calls
   `schedule_changed()`, which sets `shortage_last_run` to now, so the
   schedule starts from the next moment and a time already past today is
   not made up.
2. **When due.** `schedule.latest_slot(settings, now)` is the latest
   scheduled moment at or before now (working days skip Saturday, Sunday
   and the holidays of `TimeSurchargeSettings`/`OwnHoliday`, read through
   `holiday_test` without creating that row). A check is due when that
   moment is later than `shortage_last_run`; a moment missed while the
   server was off is made up once at the next run.
3. **Who runs it.** `run_jobs` (every minute, `rentalars-jobs.timer`)
   calls `run_due_shortage_check()`. A quiet minute costs one query. A due
   run claims the moment with a conditional `UPDATE … SET
   shortage_last_run = now WHERE shortage_last_run < <slot>` – only one of
   two overlapping runs wins. Interval "off" returns at once.
   On the first run `shortage_last_run` is empty: the run
   only notes now, so the first check is the next 4:15.
4. **The check.** Projects beginning within the lead time; every shortage
   not yet in `ShortageNotice` (or grown, or back after being resolved) is
   reported to the project manager and the members with edit access (none:
   everybody who may change projects); with `shortage_repeat` every open
   shortage again ("Still a shortage in …"). (VFG-036)
   `shortage_repeat` is on by default and the known shortages are
   collected per project during the check (`reminders`) and sent after it
   as **one** notification per project (`_remind_of_shortages`: one
   shortage keeps its own title; several get the title "Still
   shortages in …: 7 products" and the list in the text, one line per
   shortage in the order found, each written in the recipient's language –
   in the title a long list is cut at 250 characters; the period from the
   earliest start); new and
   grown shortages are sent one by one (`_report_shortage`, the same
   recipients). Each shortage still updates its `ShortageNotice` and counts
   in `shortage_reported`. Notices are forgotten only for
   projects that were looked at. `shortage_checked_at` and
   `shortage_reported` feed the page's "Letzte Prüfung"; `next_run` its
   "Nächste Prüfung".

`run_daily_maintenance` (4:15) does not check shortages.

---

## 38. Data steps: accounts, labels and shortage notices

*Code: the migrations named below, `deploy/update.sh`, `deploy/ai.sh`,
`deploy/systemd/rentalars-ai-refresh.{service,timer}`. Tests:
`tests/unit/test_084_*.py` (each migration forward, back and again on an
older copy; `RefreshTests`).*

What `rentalars update` does to the data of an existing
installation. Business data change only in `accounts/0007` and
`masterdata/0011` (logged "Aktualisierung"); everything else adds
tables or columns or fills bookkeeping. No price, cost, sum or status of a
project changes; a second run changes nothing. The migrations were run on
copies of an earlier SQLite development database; MariaDB was not tried.

| Migration | Schema | Data |
|---|---|---|
| `projects/0026_field_changes_084` | `Project.field_changed_at` | every key from the last change-log entry that really changed it, else `created_at`; not logged |
| `personnel/0013_profile_084` | `Person.phone_changed_at`, `email_changed_at`, `share_phone_changed_at`, `share_email_changed_at` | from the change log, else the person's creation; not logged |
| `accounts/0007_crew_packing_084` | help text of the project scope | "Crew" packing read → write where still read, with its start description; English start descriptions "packlist(s)" → "packing list(s)" where unchanged; logged with the levels before and after; other roles with packing write in assigned projects only and no project write noted as `role.no_material_while_packing`; reversible |
| `packing/0007_labels_084` | labels; `SyncReceipt.reason` | – |
| `documents/0005_labels_084` | labels and help texts of the DATEV settings | – |
| `masterdata/0011_labels_084` | – | an English § 3b rule `night_after_midnight` named exactly "Night 0–4 o'clock" → "Night 0–4", logged |
| `core/0020_shortages_084` | table `NotificationSettings`; help text of `TimeSurchargeRule.begun_before_midnight` | one row (daily 4:15, 4 weeks, once) |
| `ai/0002_speed_084` | `AISettings.local_test_prompt_per_second`, `AICall.prompt_per_second`, `generation_per_second`; help text of `AIProvider.timeout_seconds` | – |

The package contains `deploy/systemd/rentalars-ai-refresh.service` and
`.timer` (installed by `install_units`, enabled by `enable_timers` with
the other timers), `ai.sh refresh`, `install --rebuild` and
`--keep-model`. The timer calls `ai refresh` about
a minute after the updater enables it; `update.sh` calls it
itself after a successful update. Going back to an earlier release removes the refresh
units (`install_units` deletes units the active release does not ship).

---

## 39. Audits, to-dos and custom fields

*Code: `rentalars/material/audit_models.py`, `audits.py`, `audit_views.py`,
`audit_tables.py`, `audit_api.py`; the app `rentalars/customfields/`.
Catalogue: MAT-067 to MAT-073. Tests:
`tests/unit/test_092_audits.py`, `tests/unit/test_092_customfields.py`,
`tests/unit/test_092_review_media.py` (the review fixes),
`tests/browser/test_092_audits_in_browser.py`.*

### When an audit is due (MAT-067)

Nothing about due dates is stored; `audits.py` computes them on demand.

- **Due date** = the day of the last audit + `AuditSettings.interval_months`
  (24 unless set; `add_months` as for inspections, so 31 January + 1 month
  is 28 February) – whatever the audit found: its to-dos are followed up
  as to-dos, not by auditing again.
- **Never audited** – the reference is `MaterialItem.created_at`, the day
  the item was entered in Rentalars. "Last audit + interval" alone would
  make every item of an existing installation due on the day of the
  update; this way imported stock comes due one interval after its import,
  the oldest first, and a fresh installation is not flooded. Unlike an
  electrical test (`material.inspections`, where never inspected means
  overdue), "not looked at yet" is not dangerous.
- **Never due:** archived items (`ARCHIVED_STATUSES`: retired, sold, lost)
  and bulk material (`TrackingMode.BULK`, one row for a quantity); both can
  still be audited and get to-dos. An interval of 0 switches due dates off
  altogether.

The lists work on querysets: `with_audit_fields` annotates
`last_audit_at` (a grouped `Max` subquery – no `LIMIT`, which MariaDB
refuses inside `IN`), `open_todo_count` and `audit_reference` (last audit,
else creation); `due_items()` filters `audit_reference` before
`due_before(interval)` – the first moment not due today, worked out with
the same `add_months` so that the list and the item page always agree –
and orders oldest first. `audit_fields(item)` gives the API its
`last_audit`, `next_audit`, `audit_due`, `open_todos` from those
annotations, or with two small queries for a single item.

### Recording (MAT-068, MAT-069)

- **The audit mode** (`audit_views.audit_page`, `material:audit`, write
  access to material): `?id=` is read by `parse_scanned_id` – `0427`,
  `427`, `#0427` as the ID field (MAT-063), or the address a
  scanner reads from the QR code (the last part of the path). Two plain
  forms: "In Ordnung" with the field "In Ordnung – nächste ID" inside it,
  so Enter there records `ok` and redirects to the next ID; and "Audit
  speichern" with quick picks, free text, a note and the open to-dos to
  tick done. The round ("In dieser Runde geprüft", at most 200) lives in
  the session. No script is needed.
- **`record_audit(item, todos=…, done=…, note=…, user=…)`** in one
  transaction: texts tidied and de-duplicated, the result `todos` if at
  least one is left, else `ok`; each text through `add_todo` with the
  audit; ticked open to-dos done. The moment may be given through the API
  (an audit from paper records) but not in the future.
- **`add_todo`**: an open to-do of the item with the same text (any case)
  is returned instead of a second one; noted again after it was done, it
  is a new one. `complete_todos` ticks several at once ("Gewählte To-Dos
  erledigt" under Offene Punkte → Material mit To-Do, `todos_done`;
  also `POST /api/v1/material-todos/done` with
  `{"todos": [ids]}`, `audit_api.TodosDoneView`, write access to material:
  1 to 2,000 integer IDs, else 400; answers `done` – open ones done now –,
  `already_done` and `not_found`, the IDs of no to-do; MAT-070, API-002).
  To-dos are never deleted by the application.
- **History:** `ItemAudit` and `ItemTodo` are audited models with the item
  as `audit_parent`; `audits.history_summary` turns their change-log
  entries into "Audit: in Ordnung", "To-Do notiert: …", "To-Do erledigt:
  …".
- **Offene Punkte** (`open_without_product`, `open_todos`, `open_audits`;
  the counts of the sub-tabs from `open_point_counts`, three counts): the
  to-dos as `TODO_TABLE` (one row per open to-do of an item not archived,
  grouped by text, the bulk bar for whoever may write), the due audits as
  `AUDIT_DUE_TABLE` with a button into the audit mode per row. The item
  head (`head_badges`) shows "Audit fällig" and "N To-Dos" on every tab.
  (MAT-070) the tab itself carries the sum of the three
  counts on every tab of the material management
  (`material_tags.open_points_total`: the counts the view already has, else
  `open_point_counts` once per request – not one query per item).
- **The master data in the audit mode** (MAT-079):
  `audits.master_data(item, rights)` lists ID, model, manufacturer,
  category, serial number, invoice date, supplier, the purchase price
  (only with the right `purchase_prices`; "im Preis von 0851 enthalten"
  for a set), storage location (with "in 0500" for an installed item),
  status, the protection class, every category field (own values marked)
  and the custom fields the reader may see (`value_rows`, required ones
  without value flagged) – every row, empty ones as a red "–" with the
  hidden text "nicht erfasst". `audit_item` loads the item with its
  category fields, so the overview takes a fixed number of queries. "Exemplar
  bearbeiten" opens `material:item_edit` with `?next=` the audit of the
  item; `item_edit` follows it only to an address on this server
  (`item_views.safe_next`).

### Custom fields: definitions, values, checks (MAT-071 to MAT-073)

1. **A value is stored as text in a canonical form** – a number `12.5`,
   a date `2027-03-01`, yes/no `yes`/`no`, a choice as its option –
   by `CustomField.clean_value(raw)`, which accepts what people and files
   write (`12,5`, `1.234,5`, `01.03.2027`, `ja`) and checks type, options,
   length and the pattern; `typed_value` and `display_value` turn it back
   (`12,5 m`). The value of a sensitive field goes into `protected_value`,
   which the change log hides from readers without the purchase-price right
   (`audit_sensitive`) and the search never reads; the field's
   `visible_to(rights)` decides showing, setting, exporting and the API.
   A field marked sensitive *after* items had values: the
   log noted those values in the open column `value`, so what decides is
   the field's mark now, not the column an entry names – in the item
   history (`customfields.history.value_rows`, `hide_all`) and in the
   system-wide change log (`CustomFieldValue.audit_hidden`, asked by
   `core.history.visible_changes`, the answer kept per request under
   `SENSITIVE_CACHE_KEY`). A value whose field is gone counts as sensitive
   if the log ever kept it in `protected_value` (`ever_protected`); the
   entries that only moved a value between the columns are shown to nobody
   (`is_column_move`).
   **Showing** (`tables.value_html`, item page and list column): a web
   address becomes a link only with the scheme `http` or `https` and a
   host (`LINK_SCHEMES`, read with `urlsplit` as a browser would –
   `java\tscript:` is no link), an e-mail address a `mailto:` link only
   when `EmailValidator` accepts it; anything else – a value stored before
   the checks, or by hand – is plain text.
2. **Forms** (`CustomValuesForm`, prefix `cf`, inside the item forms): the
   entries of the model's fieldset the user sees, in order. A required
   field is required when one item is created or edited; with several new
   items (`several`) it may stay empty and a unique field is left out –
   the typed value would apply to every piece. A duplicate (`copy_of`)
   starts with the original's values, unique ones left out. "Kauf
   einpflegen" asks for none and names the new items lacking a required
   value afterwards (`items_missing_required`).
3. **Storing** (`services.store_values`): each changed value saved on its
   own row (`CustomFieldValue`, unique per item and field), so each change
   has its change-log entry with the item as parent; an emptied value keeps
   its row. `check_unique` compares case-insensitively with every other
   item. Values of fields outside the model's fieldset are kept and shown
   apart; changing the fieldset of a model deletes nothing.
4. **Definitions follow the data**: `CustomField.clean` refuses a new type,
   other options, a pattern or "unique" that a stored value would break,
   naming examples (the first value whose check takes too long ends the
   check with that error under "pattern", not one per value);
   `services.delete_field(field, with_values=…)` deletes a
   field with values only after the tick, its values one by one so the
   history of each item keeps them; a fieldset a model has is protected
   (`ModelFieldset.fieldset` is `PROTECT`).
5. **Lists and search**: fields marked "in lists" become columns of the
   item list through `TableDefinition.add_column_source` (sorting by a cast
   of the value: numbers as numbers, dates as dates), filters `?cf<id>=`,
   and the CSV; `filters.search_condition` adds `value__icontains` to the
   item search (list, API, global search, suggestions) – never
   `protected_value`.
6. **Import and export**: section 5 (`CustomColumns`) and "The export in
   the import format" (a column per field, registered with
   `register_columns`). API: `/custom-fields`, `/custom-fieldsets`,
   `fieldset` on material models, `custom_fields` (name → typed value or
   `null`) on items, checked by `services.check_values` like the form.
7. **Check patterns without catastrophic backtracking** (`patterns.py`,
   MAT-071: ReDoS). A pattern applies to text, long text,
   number, URL and e-mail (`PATTERN_TYPES`); Python's `re` backtracks –
   `(a+)+` against 30 characters took a minute – and the `regex` module
   with its time limit is not used (no new libraries). Three layers:
   - `pattern_problems(pattern)`, called by `CustomField.clean` after
     `re.compile`, walks the tree of Python's own parser (`re._parser`)
     and refuses nested repetitions whose count can vary where the outer
     or the inner one is open-ended (`(a+)+`, `(.*,){5}`), bounded nested
     ones with more than `MAX_NESTED_WAYS` (100,000) ways to split a value
     (`(a?){30}`; `([0-9]{1,3}\.){3}` has 27 and passes), alternatives inside an
     open-ended repetition (`(ab|a)+`; the parser turns `(a|b)` into a
     class, which passes), back-references (`\1`, `(?P=name)`, conditional
     groups) and patterns longer than `MAX_PATTERN_LENGTH` (200). A fixed
     count inside (`(:[0-9A-F]{2}){5}`) has nothing to try twice.
   - `full_match(pattern, text)` never matches a text longer than
     `MAX_VALUE_LENGTH` (4000, the longest long text); `_matches` refuses
     such a value as too long first.
   - `full_match` stops after `TIME_LIMIT` (0.5 s) with `SIGALRM`
     (`setitimer`, a previous timer put back) – only in the main thread,
     where gunicorn's sync workers answer requests and `run_jobs` runs the
     import; in other threads (`runserver`) it matches unguarded.
     `PatternTooSlowError` becomes `PatternTooComplexError` (a
     `ValidationError`, code `pattern_too_complex`): "Prüfmuster zu
     aufwendig: …" in the form, the API and the import.
   A pattern stored before these checks keeps working until its field is
   edited; the second and third layer apply to it all the same.

---

## 40. Electrical inspections (DGUV V3)

*Code: `rentalars/material/dguv.py`, `forms.py` (`InspectionForm`),
`services.py` (`record_inspection`), `item_views.py` (`item_inspections`,
`inspection_check`, `inspection_report`), `item_api.py`,
`inspection_report.py`; templates `material/_dguv_*.html`,
`material/inspection_report_pdf.html`. Catalogue: MAT-077, MAT-078,
extending MAT-030, MAT-031. Tests: `tests/unit/test_093_dguv.py`,
`tests/browser/test_093_dguv_in_browser.py`.*

An inspection type with `is_electrical` asks for what DIN VDE 0701-0702
checks, in its order. Rentalars suggests a result; the inspector decides.

1. **The limits are data** (`dguv.LIMITS`, with the sections of DIN VDE
   0701-0702:2008-06 as comments) – the only place a limit is written:
   R_PE 0.3 Ω for a cord up to 5 m, +0.1 Ω for every further 7.5 m
   *begun*, at most 1 Ω (`pe_resistance_limit`: 10 m and 12.5 m → 0.4 Ω,
   12.6 m → 0.5 Ω, 50 m → 0.9 Ω, 60 m → 1 Ω; no length → the short-cord
   limit); R_ISO at least 1 / 2 / 0.25 MΩ for class I / II / III; I_PE at
   most 3.5 mA; I_B at most 0.5 mA. `MEASUREMENTS` says which value
   applies to which class: R_PE and I_PE class I, R_ISO all, I_B classes I
   (at conductive parts without protective conductor) and II; `REQUIRED`
   (also data, with its source) which of them a class needs (step 3).
2. **The starting values** (`InspectionForm.__init__`): the protection
   class of the item (`effective_protection_class`), the cord length from
   `cord_length_of(item)` – the category field labelled
   "Länge"/"Length"/"Kabellänge"/"Leitungslänge"/"cable length"/"cord
   length" of type number with unit m, cm or mm, the item's own value
   first –, and the test device the same user recorded last. Without an
   electrical type among the item's types the form has none of these
   fields; with one they show only while such a type is chosen
   (`data-show-if`) and count only for it (`clean`).
3. **Judging** (`evaluate` → `Evaluation`): each value against its limit
   (`ValueCheck.verdict`: `ok`, `exceeded`, `missing` – applies, not
   measured – or `not_applicable`); `reasons` names a visual inspection not
   recorded or not passed, every value outside its limit, every need of the
   class that was not measured (`REQUIRED`: class I R_PE and
   one of R_ISO, I_PE, I_B – the alternative methods of the standard –,
   class II R_ISO or I_B, class III nothing; `missing_requirements`,
   `ValueCheck.required_missing`, `required_missing` in the API) and a
   failed function test; `suggested_result` is `passed` without reasons,
   `failed` with, empty while no class is known. A value that applies but
   is not needed may stay empty; the function test may be null
   ("entfällt"). Text like "NaN" or "Infinity" is no number (`_decimal`).
4. **While typing** the fieldset posts to `inspection_check` (htmx, input
   delayed 400 ms, `hx-sync` replace): the same form, judged as sent (a
   field that is not a number counts as not measured), answers the
   suggestion and, out of band, the limit and verdict next to every value
   (`_dguv_limit.html`, `aria-describedby` of the field). Nothing is
   stored; without scripts the page shows the same after sending. No new
   JavaScript.
5. **Recording** (`services.record_inspection(…, electrical=…)` →
   `dguv.clean_values`): class and visual inspection required, a value
   only where it applies to the class, numbers never negative and never
   beyond what the column holds (a cord length taken from the category may
   exceed 9,999.99 m); "passed" while the values speak for "failed" – also
   for a missing need – needs a note. Another type with
   values is refused. A failed inspection sets the item "defective" as
   before; without a note its reason names the findings. The stored row
   keeps only the values – `Inspection.evaluation` judges them again with
   the limits of the code whenever it is shown.
6. **Showing and printing.** The list of the item's inspections gets the
   column "Messwerte" only if one inspection is electrical
   (`_dguv_values.html`, folded, with the count outside the limit) and the
   link to `inspection_report` (`/material/inspection-records/<pk>/report/`,
   read access to material): `inspection_report.render_report_pdf` – an
   HTML template made into a PDF by WeasyPrint, in the documents' language,
   with the next due date when passed and lines to sign.
7. **API** (API-002): `is_electrical` on inspection types; `POST
   /material-items/{id}/inspections` takes the values
   (`ElectricalValuesSerializer`; class and cord length from the item when
   left out, `null` for not measured); `POST
   /material-items/{id}/inspections/check` answers `Evaluation.as_dict()`
   (values with `limit`, `limit_kind`, `applies`, `within_limit`, the
   suggestion and its reasons; 400 without a class); every inspection
   carries the values, `evaluation` and `report_url`; `GET
   /inspections/{id}/report` the PDF (404 for one that is not electrical).

---

## 41. Entering a purchase: amounts, totals and sums

*Code: `rentalars/material/purchases.py` (`parse_amount`,
`invoice_numbers`, `InvoiceNumbers`, `totals_in_text`, `match_category`,
`match_product`, `build_proposal`), `purchase_forms.py` (`AmountField`,
`purchase_sums`, `rows_from_proposal`), `purchase_views.py`,
`ai/invoices.py` (`catalogue`, `parse_answer`), `static/js/app.js`
("purchase sums"). Catalogue: MAT-074 to MAT-076, extending
MAT-061, MAT-062. Tests: `tests/unit/test_093_purchase.py`,
`tests/browser/test_093_purchase_in_browser.py`.*

The model copies amounts **as printed**, and Rentalars reads them.

1. **One amount** (`parse_amount(value, decimal_comma=…)`): currency signs
   and codes, spaces and apostrophes and a closing ",-" are removed. Both
   marks present: the last one is the decimal mark, the other must group
   thousands correctly (`1.072,50`, `1,072.50`). One mark: three or more
   groups are thousands (`1.072.500`; `1.072.50` – a point put for the
   comma – reads 1072.50); a single mark followed by exactly three digits
   and preceded by one to three is **ambiguous** (`1.072`): with
   `decimal_comma` it groups thousands (1072), else it is a decimal mark
   (1.072); anything else is a decimal mark. Not rounded here.
2. **The style of an invoice** (`invoice_numbers(text, currency=…,
   samples=…)`): the amounts the answer wrote as text vote (`99,00` German,
   `1,072.50` English; JSON numbers, read as `NumberLiteral`, say
   nothing); without a vote the amounts of the invoice text, then the
   currency (EUR German; USD, GBP, CHF English), then the language of the
   text (German and English invoice words), else German.
   `InvoiceNumbers.amounts` are the amounts with cents in the text, read in
   the text's own style.
3. **Checking against the text** (`InvoiceNumbers.amount`): an amount that
   is on the invoice is taken; otherwise an ambiguous one is tried both
   ways and as the thousands of an amount of the text ("1.072" for
   "1.072,50"), an inexact one by its digits ("1.0725" for "1.072,50");
   exactly one candidate on the invoice wins, else the reading stands.
   `ai.invoices._price` then requires 0 ≤ amount < 100 million and rounds
   to cents.
4. **Totals without AI** (`totals_in_text`): a line with a net label
   ("Netto", "Zwischensumme", "Subtotal" …) or a gross one ("Gesamtbetrag",
   "zu zahlen", "Total" …), its last amount or one alone on the next line;
   the largest of several; an amount to pay below the net total is none.
   `head_from_text` returns them with the currency, so reading without AI
   finds them too.
5. **Positions** (`parse_answer`, `build_proposal`): serial numbers must
   stand in the invoice text (spaces and case aside), others are dropped
   and counted (`serials_left_out` → a hint); for a model that is not a
   certain match the proposed category and product are taken only when
   `match_category` (path, main-category code, or a name only one category
   has, among `purchase_categories` – active, own stock, no customer
   material) or `match_product` (article number alone or in front of the
   name, or a name only one product has, among `purchase_products` –
   active rental, sale and vehicle products of the company, never customer
   material) finds exactly one; else `hints` explain
   (`ambiguous`/`unknown`). A certain model brings its own category and
   product. The same two lists, at most 150 categories and 40 products,
   go to the model in a data block of the prompt (`ai.invoices.catalogue`,
   at most a third of the room; a cut invoice text is reported with
   `purchases.end_not_read_note`). A customer's product typed into a
   row is refused (`purchases.customer_product_error`).
6. **The form.** One empty row (`EMPTY_ROWS`), "Weitere Position" adds one
   (`action=more`, or the script without a request); a proposal replaces
   empty rows with one row per position. Prices typed by people go through
   `AmountField` (the interface language's style). The invoice totals of
   the last reading travel in two hidden fields (`invoice_total_net`,
   `invoice_total_gross`, `1072.50`; removed with the invoice, and absent
   without the purchase-price right).
7. **The sums** (`purchase_sums(head, formset)`, `None` without the
   purchase-price right): each non-empty row adds price × pieces, a set
   price once, a row without a valid price counts 0 and is counted. Gross
   entry: the gross sum adds the typed prices, the net sum adds
   `services.net_from_gross` per piece (what is stored, cents). Net entry:
   gross = net × (1 + rate), rounded once. The rate is the purchase's,
   else the default tax rate. `compared` is gross when the invoice's gross
   and a gross sum exist, else net; `difference` = sum − invoice total.
   `_purchase_sum.html` renders it on every step; `app.js` recomputes it
   while typing from the same data attributes (`data-rate`,
   `data-invoice-net`, `data-invoice-gross`, the texts for unpriced rows).

---

## 42. Booking in an incoming invoice, with cost allocation

*Code: `rentalars/incoming/` (`services.py`, `reading.py`, `costing.py`
with `costing_of`, `spread`, `even_slice_cents`; `booking.py` with `plan` and
`book`; `views.invoice_book`), `material/purchases.py` (`create_purchase`,
`check_positions`), `material/assets.py`, `ai/invoices.py`
(`register_proposal`, `run_register_job`). Catalogue: DOK-023, DOK-024,
MAT-086, MAT-088 (extending MAT-061, MAT-062). Tests:
`tests/unit/test_100_incoming.py`,
`tests/browser/test_100_incoming_in_browser.py`.*

An example: an invoice with 4 mixing-desk faders at 100,00 € net, 3 cables at
50,00 € net and 21,00 € freight, spread by value.

1. **Upload** (`services.create_from_upload`). `validate_invoice_file` checks
   extension (PDF, PNG, JPEG, WEBP), size and, for pictures, the real format
   by content. The file goes to `incoming/<year>/<random>`, its SHA-256 into
   `content_hash`. The same hash, or the same supplier and number, is shown
   as a warning on the invoice (`services.duplicates`) – it is not refused.
2. **Reading** (`start_reading`). `reading.text_of` takes the text of a PDF
   with a text layer (first pages, as in "Kauf einpflegen"); a scan or picture
   has none: `reading_state` becomes `failed`, the page says "enter by hand".
   `proposal_from_text` finds number, date, due date, a **known** supplier
   and the totals by patterns, and `apply_proposal` writes them into the
   **empty** head fields only. If the AI is on for invoices, `reading_state` is
   `running` and the job `ai_incoming_invoice` finds the positions too (the
   page polls `incoming:reading` every 2 s until it is finished); an unknown
   supplier is only proposed. Reading again never overwrites typed values and
   never touches a position that is booked in.
3. **Correction.** Every field of head and position can be changed
   (`update_head`, `update_position`; at most 100 positions). Freight,
   packaging and customs are marked "Nebenkosten" (a discount is a negative
   amount); the key (value, quantity, weight) is chosen once for the whole
   invoice. Changing the key asks `incoming:costing` and shows the new split
   at once; nothing is saved.
4. **Costing** (`costing_of`). Per goods position the amount in euros
   (`line_net × rate`), the weight of all pieces if known, and – after
   `spread` – its share. Example by value: the goods are 400,00 + 150,00 =
   550,00 €; the shares of 21,00 € are 21 × 400/550 = 15,2727 → 15,27 and 21
   × 150/550 = 5,7273 → 5,73; floors 15,27 and 5,72 add up to 20,99, the one
   remaining cent goes to the largest remainder (5,7273 → 5,73), so 15,27 +
   5,73 = 21,00. The share of the fader position (15,27 €) is then spread over
   its 4 pieces: `15.27 // 4` = 3,81 € each, and the first `15.27 % 4` = 3
   pieces get one cent more: 3,82 / 3,82 / 3,82 / 3,81 (the sum is 15,27). The
   acquisition cost of a fader is 100,00 + 3,82 = 103,82 €. The kind of each
   position (`assets.kind_for`, on the **cost per piece**, up to the limit
   inclusive a GWG, above it a fixed asset, unless chosen) and its useful
   life (`assets.life_for`) are filled in.
5. **The booking page** (`incoming:book`, GET): one row per goods position
   with model (or name and category of a new model), number of pieces
   (default: what is left), storage location, serial numbers, kind, useful
   life, and "book again". A POST without confirmation shows the **plan**.
6. **The plan** (`booking.plan`, nothing written). Problems stop it: foreign
   currency without a rate, costing problems (no goods, no weight when spreading
   by weight, nothing to spread over), a position not of this invoice or twice,
   no model, customer material (`purchases.is_customer_model`), pieces < 1 or
   more than a step allows, a position booked in already without "book
   again", a fixed asset without a useful life, serial numbers not matching;
   then the rules of "Kauf einpflegen" (`purchases.check_positions`: the price
   right, the most items of a step). Warnings only inform ("more pieces than
   are left: the extra ones get the average cost"). The page shows per row
   price, share, total, per piece, kind and life, and wants the tick "Ja, genau
   so einpflegen".
7. **Booking** (`booking.book`, one transaction). The invoice row is locked
   (`select_for_update`), the plan is made **again** (a double click or a second
   user cannot book twice), and `purchases.create_purchase` makes the items
   with consecutive IDs, supplier, invoice number and date as `purchase_date`,
   the invoice file attached to each item. Every item gets
   `purchase_price`, `ancillary_cost_net`, `acquisition_cost_net`,
   `asset_kind`, `useful_life_months` and `source_position` from
   `_item_values`; a bulk row gets the sum of its slice. Afterwards the
   position remembers its model, the invoice its supplier, and
   `mark_booked_in_when_complete` sets the status "eingepflegt" when every goods
   position is in. An event `incoming_invoice.booked` with the IDs goes to the
   history.
8. **Afterwards.** A position that is booked in cannot be removed; the invoice
   cannot be deleted. A later change of the key does not rewrite items. The
   book value of the new items is computed from section 47's rules
   (`material/depreciation.py`).

## 43. Scanning a code

*Code: `rentalars/material/scan.py` (`resolve`, `clean_code`),
`scan_views.py`, `scan_api.py`; `packing/scan.py` (`scan_pack`,
`scan_return`); `static/js/scan.js`; `templates/material/_scan.html`.
Catalogue: MAT-027, UIX-006, PCK-010, PCK-011, PCK-016, PCK-022. Tests:
`tests/unit/test_100_scan.py`, `tests/browser/test_100_stock_in_browser.py`.*

1. **The code arrives as text** from one of three sources: the camera dialog
   (`scan.js`: `BarcodeDetector` polls the video every 220 ms; the same code
   in front of the camera is read once per 2.5 s; the picture never leaves the
   browser), a USB scanner typing into the field "ID scannen oder eintippen"
   (it ends with Enter), or a person typing.
2. **Cleaning** (`clean_code`): control characters at the end, an AIM prefix
   (`]Q1`, `]C0`) and spaces removed; cut at 300 characters.
3. **Resolving** (`resolve`, in this order):
   a. a QR address of a label becomes its ID (the pattern in Einstellungen →
      Etiketten with `{id}`, else the last path part);
   b. a number of 8, 12, 13 or 14 digits (with leading zeros equivalent) is
      looked up as **GTIN of a product** first – IDs are short;
   c. an inventory number (`0042`, `42`, `#0042`) or a serial number
      (case-insensitive) finds an **item**; an item that holds items or
      built-in quantity material is a case (`is_case`);
   d. `01-A-1` is a **storage spot** (when items lie there);
   e. the name of a **storage location**;
   f. otherwise `none` with "Nothing is known under …".
   Each step first asks the reader's right (`allowed`): a code that leads to
   something the reader may not read answers exactly like a code nobody
   knows. Nothing is created or changed.
4. **Pages and API.** `material:scan_resolve` and `GET /scan/resolve?code=`
   return `result_document` (kind, title, detail, url, `is_case`,
   `plan_token`/`plan_label`, item and product). The material list jumps to
   the item; the planning (mode "plan") adds the product with the item as a
   wish (`plan_token` `12:i56`).
5. **Packing** (`packing/scan.scan_pack`, from the packing list's field or
   dialog, which stays open for the next code – `continuous`). The item is read; the checks come
   in this order and each refusal has its own message and status: packing is
   still open; the item has a product; a fixed content of a case goes out with
   the case (INFO if the case is on the list, else refused); bulk material only
   points to its row; the product has a row on the list; the item is
   operational (not defective/blocked); it is not chosen for or out with another
   project (`_busy_with`). Then the row is found – the one that has the item
   chosen already, else the first with free pieces – and if all pieces are
   chosen, `FULL`. A new item is chosen with `services.choose_items`
   (overdue inspection only warns), `Allocation.packed_scan_at` is set, and
   the row's tick is raised to the pieces scanned (`scanned // pieces per
   unit`, never lowered). The message says "4 von 6" (per piece for a row of
   several pieces). The same code twice answers `DUPLICATE` and counts
   nothing. At the issue, scanned items go out first.
6. **Taking back** (`scan_return`): the item must have gone out with this
   packing list; `returned_scan_at` is set once; the row's "returned" tick is
   raised; booking the return stays its own step (PCK-028).

## 44. Login with a company directory (LDAP), and the role sync

*Code: `rentalars/accounts/ldap_backend.py` (`LdapBackend`), `ldap_sync.py`
(`sign_in`, `plan_for`, `apply_plan`, `compare_accounts`, `sync_nightly`),
`ldap_client.py`, `backends.py`, `models.py` (`LdapSettings`,
`LdapGroupMapping`, `LdapRoleAssignment`), `management/commands/ldap_sync.py`.
Catalogue: AUT-029. Tests: `tests/unit/test_100_ldap.py` (mock directory),
`test_100_ldap_pages.py`, `test_100_ldap_slapd.py` (opt-in).*

1. **Local first.** `AUTHENTICATION_BACKENDS` = the local backend, then
   `LdapBackend`. The local backend refuses any account but a local
   (emergency) one when the directory is on and "allow local login" is off; so
   with local passwords on, a user with a Rentalars password logs in as ever,
   and the directory is asked only when the local check said no.
2. **Is the directory asked at all?** `LdapBackend.authenticate` answers
   `None` ("not me") when the settings are not ready, the name or password is
   empty, or the account is a **local account or a superuser** – those log in
   with their own password only.
3. **Service bind and search** (`ldap_sync.sign_in`). The typed name is
   normalised (Unicode NFC; empty, over 256 characters or with control
   characters: refused); a connection is opened
   to the servers in turn (each checked by the address guard `core.network`;
   `ldaps://` or StartTLS; the certificate against the **name** of the server);
   bound with the search account; `find_user` searches the base with the filter
   in which `{username}` is replaced in one pass by the **escaped** name (more
   than one hit: `ambiguous`). An unknown name ends here.
4. **The user's own bind.** `check_password` binds as the entry's DN with the
   typed password – an **empty password is never sent**. Wrong: the security log
   gets "wrong password", the user a general text.
5. **Groups** (`groups_of`): `memberOf` of the entry, or a search with
   `{user_dn}`/`{username}` in the group filter. A failure at any step that is
   the directory's (unreachable, TLS, service bind) returns `unavailable`: the
   login page then says the directory could not be reached.
6. **The plan** (`plan_for`, pure; the dry run "Anmeldung testen" and the
   nightly comparison call it too). `decide_roles` takes the mappings whose
   group is among the user's groups, in order of priority – roles are united, a
   mapping with "last match" ends the list. Then the account: found by DN, else
   by username; a protected account (local, superuser, or one that belongs to
   another entry) is not taken over. No account: created only if `auto_create_users`
   is on **and** the user has at least one role. An account of the directory
   that now has no role is to be deactivated – unless an administrator
   deactivated it (stays so) or it is the **last administrator** (never).
7. **Applying** (`apply_plan`, in a transaction). Everything is attributed to
   `system:ldap` in the change log. Username, name, e-mail from the mapped
   attributes (a new account goes through `full_clean`; unusable data refuse the
   login as "data not usable"); `ldap_dn`, `ldap_synced_at`;
   `set_unusable_password` for a new account; `_apply_roles` writes the roles
   and the `LdapRoleAssignment` rows (`also_manual` where an administrator had
   given the role first); a user back in a mapped group is activated again if
   `ldap_deactivated_at` says the directory had deactivated them. Security
   events `ldap_account` / `ldap_roles` are written; a refusal is `ldap_refused`
   with its reason (`in no group with a role`, …).
8. **Then as usual.** The login view continues: lockout counting, 2FA (the
   code is asked after the LDAP password), session. Page and API change only the
   roles that are not the directory's (`services.set_user_roles` keeps them).
9. **The comparison** (`compare_accounts`, `manage.py ldap_sync`, the buttons
   "Unterschiede anzeigen"/"Diese Änderungen anwenden", and the nightly
   `sync_nightly` when `sync_daily` is on): for every directory account the same
   `plan_for`; a dry run only reports. It **stops** when more than 3 and more
   than half of the accounts would be deactivated, unless `--force`. The result
   goes to `last_sync_summary` and the security log (`ldap_sync`).

## 45. The night's automatic AI summaries

*Code: `rentalars/ai/auto.py` (`run_due`, `run`, `_loop`, `judge`,
`_summarise_one`), `ai/summary.py`, `ai/privacy.py`,
`core/management/commands/run_jobs.py`, `ai/management/commands/ai_summaries.py`.
Catalogue: EML-056, NFA-079. Tests: `tests/unit/test_100_ai_summaries.py`,
`tests/api/test_100_ai_summaries_api.py`.*

1. **The trigger.** Every minute `run_jobs` calls `auto.run_due()`. Outside the
   window, with the feature off, or if the night has been done
   (`auto_last_night`), it costs one query. Inside the window it starts the task
   `ai_auto_summaries` as a process of its own (so hours of a slow model do not
   hold up the other tasks) – or `manage.py ai_summaries` runs it by hand.
2. **Gates** (`run`). Switched on, else no run is made at all; the lock is
   acquired (`_acquire`: a row of `AutoSummaryRun` with `lock = 1`, unique – a
   run that stopped beating for two hours counts as dead; if another run holds
   it, nothing is done); the opt-in holds for the server the summaries go to now
   (`consent_holds`), else the run is recorded as stopped with the reason
   `consent`; an unusable provider ends it as failed with the reason
   `provider`.
3. **Candidates** (`eligible_projects`): projects and service cases in the chosen
   statuses that have correspondence (their own or their parts'), not excluded
   (`AutoSummaryExclusion` for the project or its customer), not of an
   anonymised customer, **newest mail first**. A whole project is summarised
   with its parts (`project_ids_of`): the job has no user whose rights would pick
   some.
4. **For each candidate** (`judge`), cheapest check first: fewer readable mails
   than `auto_min_mails` → skip; no summary yet → summarise; marks (mail count,
   newest mail, with chat also the newest chat id) equal to the stored
   summary's → "unchanged"; the stored one is younger than
   `auto_min_interval_hours` → "recent". Only then are the texts built.
5. **Building and hashing** (`summary.prepare_texts` with the **automatic scope**:
   mails and notes of the project and its parts, locked mails by default, chat
   only if allowed; `privacy.prepare` removes the classes of data; delimiters are
   neutralised; the text is cut at `max_input_chars`, oldest first). The SHA-256
   of that input is `input_hash`. **Equal to the stored hash → the marks are
   updated and the model is not called** (counted "unchanged").
6. **Asking the model** through the same `summarise` as the button, as the
   principal `system:ai-summaries`; the answer goes through `clean_output`.
   `store_summary` keeps time, model, provider, hash, `is_automatic`; the earlier
   text becomes an `AISummaryVersion` (up to `auto_keep_versions`). A manual
   summary is never overwritten without being marked.
7. **Brakes.** After every project: the count of the night
   (`auto_max_per_run`, reason `limit`), the end of the window (no new project is
   started after it, reason `window`), the token budget (`tokens_after` sums the
   `AICall`s since the run began, reason `budget`), the heartbeat of the lock. Three failures in a row end the
   run with reason `provider`. A failing project is noted in `details` (error, no
   mail content) and is a candidate again next night; a run that could not reach
   the provider is tried again up to three times.
8. **Seeing it.** Administrators see the runs and their counters
   (`AutoSummaryRun.details`, `/ai/auto-summaries/runs`), no notification is sent.
   On the project page `shown_summary` offers the summary (for who reads all
   messages) with "automatisch erstellt", a hint when newer mails exist and
   "Erneut zusammenfassen".

## 46. Importing old projects from their invoices

*Code: `rentalars/projects/legacy_import.py` (`add_files`, `start_reading`,
`check`, `summary`, `confirm`, `undo`), `legacy_draft.py`, `legacy_text.py`,
`legacy_quiet.py`, `legacy_views.py`, `ai/legacy_invoices.py`
(`parse_answer`, `run_job`). Catalogue: PRJ-130, extending DOK-005, MAT-062.
Tests: `tests/unit/test_100_legacy_import.py`,
`tests/browser/test_100_legacy_import_in_browser.py`.*

1. **Upload** (`add_files`). At most 30 files of 10 MB and 120 MB per batch;
   each is checked as a PDF, kept under `DATA_DIR/legacy-invoices/<random>`
   and fingerprinted. A file imported before, or twice in the upload, becomes a
   record "duplicate" and is never read. First, `delete_old_files` drops what
   was uploaded 14 days ago and not taken over.
2. **Reading** (the task `legacy_invoices`). For each invoice
   `purchases.invoice_text` gets the text (PDFs with a text layer only); with AI
   on for reading invoices **only that text** goes to the provider; `parse_answer`
   reads the JSON strictly (expected keys and types, lengths cut, numbers parsed
   by Rentalars, at most `MAX_LINES` lines); without AI or on failure
   `legacy_text` finds the same things by patterns. `prepare` matches the customer
   and, optionally, products against the master data – **it only proposes**.
   The result is stored in `LegacyImportItem.proposal`; the page of the batch
   shows progress.
3. **Preview and checks** (`check`). The user edits the draft (customer: match,
   new or none; number, date, totals, positions, paid or not). Warnings: the sum
   of the positions against the totals (tolerance by number of lines), tax, the
   printed amounts against quantity × price. Errors, which block: no number, a
   number that exists, a number **inside the running sequence** of the live
   invoice range (`range_collision` – it would collide later), an unknown tax
   rate. "Zu einem Projekt zusammenfassen" joins invoices (`merge_into`);
   "Überspringen" ends one.
4. **The confirmation page** (`summary`) lists exactly what will be created per
   project: customer (new or existing), project number, name, period, lines,
   historic invoice. Nothing is created before the user confirms; a batch may
   be confirmed in part.
5. **Taking over** (`confirm` → `_take_over`, per project in one transaction,
   inside `legacy_quiet.quiet()`). The customer is created only now if "new" was
   chosen; the project gets the next number `ALT-<year>-<nnnn>`
   (`_next_project_number`) and the status **closed**; lines are free lines or
   mapped products; a `Document` of kind invoice is built from the content with
   the original number, date, totals and the original PDF attached, and the
   record is linked to it (`LegacyImportItem.document` – this link is what
   `Document.is_historic` reads). The project's notes and history say
   "Importiert aus Rechnung … am … von …". The live number sequences are not
   touched; no mail, task, notification, reservation, automation or webhook.
6. **Undo** (`undo_problems`, `undo`): within 7 days, by who imported or an
   administrator, only if nothing was changed since (no change-log entry after
   `audit_mark`, no document, mail, file, time … added; invoices not sent,
   cancelled or handed on; a customer made by the import has no other project).
   The projects, historic invoices and customers of the batch are removed; the
   records go to `undone`.
7. **Later.** Historic invoices are listed like other documents, but cannot be
   booked or cancelled, are not in the Lexware error list, and are in the DATEV
   export only with "historische Belege einschließen".

## 47. Selling an item from the stock

*Code: `rentalars/material/sales.py` (`preview`, `sell`, `cancel`),
`sale_models.py`, `book_values.py`, `depreciation.py`, `asset_views.py`,
`asset_api.py`. Catalogue: MAT-087, MAT-086. Tests:
`tests/unit/test_100_depreciation.py`.*

1. **The book value** (`book_values` → `depreciation`, computed on every call).
   A fixed asset of 1.000,00 € over 60 months bought in March 2024: on 15 June
   2026 the months counted are 28 (March 2024 to June 2026, the month of
   acquisition and the month asked for in full); written off
   `round(1000 × 28 / 60)` = 466,67 €; book value 533,33 €. A GWG of 600,00 €
   bought in 2026: the full cost until 30 December, 0 from 31 December 2026.
   Merchandise stays at cost.
2. **Preview** (`sales.preview`; the page `material:item_sell`, the API
   `sale-preview`). It works out the book value on the day of the sale, gain or
   loss (net price minus book value) and the three lists: problems, warnings,
   notes (section "Used sale" in decisions). An item that is no asset in the
   books gets book value 0 € and the note says so.
3. **Selling** (`sales.sell`, one transaction). The item row is locked; the
   preview is made again; problems raise a `ValidationError`; warnings need
   `accept_warnings` (error code `needs_confirmation`, which the page turns
   into a tick). The record `SaleFromStock` is filled with the books as they
   were. A whole item: `set_status(… SOLD, reason="Sold on … to …")` – the
   existing mechanics, so the archive rules hold. A part of a bulk row:
   `_reduce_row` takes the pieces off the row's quantity and the share off its
   three cost columns and keeps the parts in `price_part` / `ancillary_part`. An
   event `item.sold_from_stock` (buyer, date, quantity – no amount) goes to the
   history.
4. **Storno** (`sales.cancel`, with a reason, while the item is still sold): the
   former status is restored (or the part is put back with exactly the parts
   kept), the record gets `cancelled_at`/`by`/`reason` and stays in the list.
5. **Invoice for the buyer.** In the list, "Rechnung dazu erstellen" creates a
   free outgoing document draft for a buyer who is a customer – the
   draft is not linked to the sale.
6. **Registers.** `/accounting/assets/` (items with cost, depreciation and
   book value at a date or balance year; filters; totals; CSV) and
   `/accounting/assets/sales/` (sales with gain/loss per year) read the same
   functions; neither has a DATEV export.

## 48. Negotiating a price offer for a deployment

*Code: `rentalars/personnel/offers.py` (`make_offer`, `accept_offer`,
`counter_offer`, `reject_offer`, `withdraw_offer`, `apply_offer`,
`release_offer`, `after_line_update`, `on_new_request`), `offer_models.py`,
`offer_views.py`, `offer_api.py`, `projects/crew.py`. Catalogue: PER-038,
extending PER-016. Tests: `tests/unit/test_100_price_offers.py`,
`tests/browser/test_100_price_offers_in_browser.py`.*

1. **Switch and request.** `OfferSettings.enabled` (default off). The request
   mail (`projects/crew.request_deployment`) then has the line "Du möchtest deinen
   eigenen Preis nennen?". A new request starts a new negotiation
   (`on_new_request` lets earlier open offers lapse; an applied total ends when
   new times are asked for).
2. **The freelancer's offer** (`make_offer`). The person of the line makes it
   themself, or a planner with the personnel-cost right enters one made by phone
   (`Acting.allowed`). `blocker` names what stands in the way: the person is not
   a freelancer (temporary staff only if `also_temporary`) or not active; the
   request is not waiting for an answer (`request_status` `requested`); the
   project is closed or cancelled; the rounds are used up. The line is locked
   (`_lock`), and an offer that waits already stops a second one. `_new_proposal`
   checks the unit (`hour`; `day` only for lines billed per day; `total`), the
   amount against the limits in percent of the stored rate
   (`reference_amount`; two decimals, EUR, at most 99 999 999,99), and
   `_check_actions_per_hour` allows 30 proposals per user and hour. A row
   `PriceOffer` (round = rounds used + 1, side `freelancer`) is written with the
   rate at that time as `reference_amount`; the company is told.
3. **The company.** The planning shows a badge, the amount and "hinterlegt: …"
   (the stored rate) to who has the personnel-cost right and reads the project;
   without that right nothing of offers shows. The company user (`Acting`:
   someone who plans the crew and sees personnel costs) can **accept**, **reject**
   or **counter**: a counter makes the first offer `countered` and writes round 2
   with side `company`; the freelancer answers a counter the same way or
   **withdraws**. At the last round only accept or reject is left.
4. **Accepting** (`accept_offer`, one transaction). The proposal is `accepted`
   and every other open proposal of the negotiation `lapsed`. `apply_offer`
   writes the amount into **that crew line**: per hour `hourly_rate` (and the
   rate above the hour limit and the flat cost are emptied – the offered rate
   holds for every hour), per day `daily_rate` (flat cost emptied), in total
   `cost_flat_rate`. The values replaced are kept on the offer
   (`previous_*`), an earlier applied offer of the line is taken back first
   (`revoked`), the line is saved through the normal path (so the change log has
   it, the rates only for who sees personnel costs) and the event
   `crew_line.offer_applied` names no amount. Then the request is answered
   "zugesagt" through `projects.crew.answer_deployment` with the note "Accepted
   after a price offer." – the note is shown to everybody who sees the planning
   and so does not name the price – and the other side is told. The **customer
   price is not touched.**
5. **Letting go** (`after_line_update`, `on_new_request`). The cost rate edited by
   hand (or a unit that no longer fits the line): `release_reason` `manual`; the
   person or job function changed: `person`; in both cases the line **keeps the
   rates it has** (`restore=False`). New times requested: an applied **total**
   is released with `times` and the former values **come back** (`restore=True`);
   a rate per hour or day stays after new times – it is the person's price for the
   line. A new request lets waiting proposals lapse. The event
   `crew_line.offer_released` is logged.
6. **Notification.** Offers notify (`_tell_company`) only users with the
   personnel-cost right who can read the project (kind `price_offer`); answers
   notify the freelancer (`price_offer_answer`). The companion-app default is
   unchanged.
7. **Seeing it.** Personal → Preisangebote lists offers for the company; the
   freelancer sees only his own (`/people/me/offers`). Amounts are shown
   to others only with the right; the change log belongs to the person.
