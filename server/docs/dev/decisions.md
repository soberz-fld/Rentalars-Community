# Decisions

What was decided, why, and what was rejected (NFA-059). Part 1 holds the
decisions taken with the requirements catalogue, which shaped the project
before the first line of code; the later parts the decisions taken while
building, one part per round of work.

A decision marked **[assumption]** or *Assumption* fills a gap the catalogue
leaves open. It is the reading that seemed most useful; it is cheap to
change now and gets more expensive with every installation. If it is
wrong, say so.

New decisions are added as a new part at the end.

---

## Part 1: Decided with the requirements catalogue

These are the entries of catalogue chapter 12.1 that concern the stages built
so far. The catalogue itself gives the full list and the history; here is how
each one shows in the code.

### Foundations

| Decision | Why | Rejected | In the code |
|---|---|---|---|
| Own development, not a fork (chapter 9) | The data model – model/item/product, kits, availability over periods – is the core and does not fit an inventory tool | Building on an existing inventory tool: its model is "one asset, one checkout"; and a licence like the AGPL would bind every user to further conditions (NFA-053) | – |
| Python with Django behind NGINX, MariaDB | Mature, long-term versions, one process and one database are enough for a small business | A JavaScript front end with a separate back end: two code bases, a build chain, more to install | `requirements.txt`, `deploy/` |
| Pages rendered by the server; the API of equal rank next to them (API-002, UIX-009) | Little script, fast on a phone, nothing to build; and every function reachable by other programs | A single-page application talking only to the API | "One logic, two doors" in [architecture.md](architecture.md) |
| Code must explain what happens and why (NFA-055 ff.) | The people who maintain it later are not the ones who wrote it | – | docstrings everywhere; `ruff` rule set `D` fails the check where one is missing |
| Everything in the code is English, with a fixed translation list (NFA-061, catalogue 2.1) | One thing has one name everywhere; English is the language of the tools | German identifiers | names of classes and fields; `tests/acceptance/test_scenario_19_…` checks the list |
| Prices and customer correspondence are always separate rights (AUT-019) | Warehouse and crew work with projects without seeing what they cost | Tying prices to the write level of the module | `SpecialRight` in `accounts/rights.py` |
| GPL, version 3 or later (NFA-052) | Free for every business; changes stay free | – | `LICENSE`, `scripts/check_licenses.py` |
| One installation per business, free, self-installable (NFA-045, NFA-046) | No operator in the middle who sees the data of several businesses | Several businesses ("tenants") in one installation | no tenant column anywhere; one `CompanyProfile` row |
| Only Ubuntu Server with NGINX; an installation script is mandatory (NFA-027, NFA-031); on a Raspberry Pi also Raspberry Pi OS (Debian 13, NFA-070; see Part 16) | One tested path instead of several half-tested ones | Containers as the main path (possible later, NFA-016) | `deploy/install.sh` |
| Own server with certificate; only reachable by VPN during the test phase (NFA-035, NFA-048) | Must be safe on the open internet from day one | Relying on the VPN for security | HTTPS only, strict headers, login lockout; certificate also obtainable by DNS without being reachable |
| Sized for 100 accounts, more than 10,000 items, several hundred projects (catalogue 3.2) | – | – | `create_load_test_data`, acceptance scenario 11 |

### Material and products

| Decision | In the code |
|---|---|
| "Installed in" always names the ID of another item (MAT-033) | `MaterialItem.installed_in` |
| Two kinds of connection: permanently installed and loosely contained (MAT-036) | `ConnectionType`; decides the plannable stock in `availability/stock.py` |
| Loose contents are planned along with their case (MAT-036, MAT-042) | `container_index` in the availability engine |
| On import, every row with "installed in" becomes "permanently installed" (IMP-010) | `material/importer.py` |
| Fields are split between model and item as in MAT-011 | `MaterialModel`, `MaterialItem` |
| One category-specific value per category, extensible (MAT-009, MAT-010) | `CategoryField`, `MaterialModel.field_values` |
| Bulk material exists (MAT-005) | `TrackingMode.BULK`, `MaterialItem.quantity` |
| An item belongs to one product, and can also be part of kits (PRD-004, PRD-022) | `default_product` / `product_override`; `KitComponent` |
| One common tree of categories for material and products (PRD-009) | `masterdata.Category` |
| Article number: code of the category, then digits with a minimum length (PRD-007, PRD-027) | `products/services.py`, `suggest_article_number` |
| Existing IDs are four-digit and consecutive; after 9999 counting goes on with five digits (MAT-003) | `material/numbering.py` |

### Prices

| Decision | In the code |
|---|---|
| The rental price is a price per day; the billing mode is chosen per product (PRD-013, PRD-014) | `Product.billing_mode`, copied to the line |
| Rental scale: adjustable, also per category; part of the line's price (PRD-015, PRD-034) | `RentalScale`, `Category.rental_scale`, `Product.rental_scale_mode` |
| Start values 1 day = 1.0, 2 days = 1.5 (PRD-015, PRD-038) | `masterdata/defaults.py` |
| Surcharges as fixed amount and as percentage; a percentage names what it refers to (PRD-031) | `SurchargeTarget` |
| Rental and sale price on the same product (PRD-017) | `Product.price`, `Product.sale_price`, `MaterialLine.is_sale` |
| Tax 19 % by default, or tax-free (PRD-016) | `TaxRate` |

### Projects and planning

| Decision | In the code |
|---|---|
| Eight statuses; "confirmed" in two flavours (PRJ-008, PRJ-059) | `ProjectStatus`, `ALLOWED_TRANSITIONS` |
| Overbooking only warns; planning stays possible (PRJ-013) | `add_line` saves and returns the shortage |
| Subrental through category E, suggested where something is short (PRJ-018, PRJ-054) | `accept_subrental_suggestion`, product `E-001` |
| A covered shortage does not burden the own stock (VFG-018) | `covers_line`, `covers_product` |
| Buffer times exist; default 0 hours (VFG-005) | `SystemSettings`, `Category`, `Product` |
| Packing: ticking is enough; scanning later and never mandatory (PCK-009, PCK-020) | `packing/services.py` |
| Groups: discount, flat price, optional/alternative; nesting later (PRJ-037 to PRJ-040) | `Group`; `Group.parent`, used for nesting (Part 10) |

### Assumptions the catalogue names itself (chapter 12.2)

1. Both "confirmed" statuses reserve firmly, "option" reserves softly,
   "inquiry" not at all (PRJ-008). → `firmness_of()`.
2. Percentage surcharges are taken from the amounts after discount and never
   from other surcharges (PRD-039). → `pricing.py`, step 3.
3. If several cases of the same product have different contents, the
   availability reckons with the most extensive content until an item is
   assigned (VFG-017). → `_contents_for()`.

---

## Part 2: Decided while building

### Business rules

**A product has no stock field; nothing calculated is stored.**
Stock, free quantities, amounts, subtotals and totals are derived when
needed. *Why:* a stored figure can disagree with the records it was derived
from, and then nobody knows which is right. *Rejected:* a reservation table
kept up to date by triggers or signals – faster to read, but every path
that changes a line, a status, an item or a kit would have to keep it right.
*Price:* computing time; see "Performance" below.

**Shortages are shown at every project that competes, not only at the one
that came last.** Two confirmed projects need 6 and 4 of 9 cables at the
same time: both show the shortage. *Why:* which of the two has to give way
is a decision for a person; the program should not suggest that the earlier
entry is in the right. *Rejected:* "first come, first served".

**A project is judged as if it were confirmed.** An inquiry shows its
shortages although it reserves nothing. *Why:* otherwise the shortage
appears only at the moment of confirming. **[assumption]**

**"Tight" means: enough, but it collides with an option of another
project.** (PRJ-012 names three colours without defining the middle one.)
**[assumption]**

**Default rental scale: 1 day = 1.0, 2 days = 1.5, each further day +0.5.**
The first two values are given (PRD-015); the rule for longer periods is
"confirmed" in the catalogue without numbers. The increment is a field of
the scale and can be changed in the browser. **[assumption]**

**"Daily rental per kit" is calculated like "per piece"**, the quantity
being the number of kits. The two modes differ in what the quantity means,
not in the formula. **[assumption]**

**A flat price of a group replaces everything in it**, including surcharges
inside the group; surcharges that refer to the group from outside are then
taken from the flat price. **[assumption]**

**Project-wide percentage surcharges ignore optional and alternative
groups**, because those are not part of the total (PRJ-040). **[assumption]**

**Rental days are suggested when nobody entered them.** If neither line,
group nor project name rental days, they are derived from the event period –
every started 24 hours count as one day – and without an event period from
the reservation period. *Why:* a new project should show prices at once
instead of zeros. **[assumption]**

**Material IDs have no prefix**; they are plain numbers shown with four
digits, as on the existing labels (MAT-003).

**An extra module for rights: "Packing and issue".** The catalogue's list
of modules (AUT-014) has none. *Why:* warehouse staff must work through
packlists without the right to edit projects, and crew may read a packlist
without ticking anything. *Rejected:* tying packing to the write level of
"projects".

**The role "Lager" (warehouse) sees purchase prices** but not rental
prices: whoever maintains material enters what it cost. **[assumption]**

**Roles limited to "assigned projects only" give no access to projects and
packing until stage 3.** The assignment of people to projects arrives with
personnel planning. Until then "only assigned" cannot be evaluated, and the
safe reading is "none". *Rejected:* treating it as "all" for now – a crew
account would see every project and lose that with the update to stage 3.
The role form says so.

**Archiving is refused while something is inside.** A rack with receivers
in it cannot be set to retired, sold or lost; the contents have to be taken
out first (MAT-022). The rule is in `MaterialItem.clean()` and therefore
holds for every way of changing the status.

### Import

**The import is a dry run unless told otherwise.** `import_material FILE`
only reports; `--commit` writes. In the browser the "import" button appears
after a dry run without errors. *Why:* the first import of 1,650 rows
should not be the first time anybody sees what the file does.

**All or nothing.** One faulty row stops the whole import (IMP-009).
*Rejected:* importing the good rows – it leaves a database that matches
neither the file nor the state before.

**The column defaults follow the 13 fields of MAT-011 and common
spellings.** They have been tried on constructed files, not on the real
list. Every assignment can be corrected (in the browser, or with `--map`);
once the real heading row is known, its spellings should be added to
`IMPORT_FIELDS` in `material/importer.py`. **[open point]**

### Technology

**No `__date` lookups on date-time columns.** `filter(start__date=day)` makes
MariaDB convert time zones in SQL, which needs time zone tables that a fresh
MariaDB does not have; the query then silently finds nothing. Day limits
are computed in Python instead (`start_of_day`, `end_of_day` in
`core/listing.py`). SQLite does not show the problem, which is why the full
test run also runs on MariaDB in the continuous integration.

**Templates write numbers plainly; grouping is asked for by a filter.**
Django can put dots between the thousands of every number a template
prints (`USE_THOUSAND_SEPARATOR`). That is switched off. *Why:* a template
also prints record IDs – into hidden fields, options, `data-` attributes –
and with the automatic separator the ID 1234 was written as "1.234"; every
form sending it back failed from the thousandth record on. No test noticed,
because test databases start counting at 1; the browser tests on MariaDB,
where the counters are not reset between tests, did. Amounts are grouped by
the filter `money`, counts by `thousands`. `tests/ui/test_large_ids.py` works
with IDs above 1000 throughout.

**Amounts and quantities travel through the API as strings**, `"12.50"`.
*Why:* JSON numbers become floating point numbers in most clients.

**The API token is shown once and stored as a hash** (AUT-021), like a
password.

**Rules of a single record live in `clean()`; `save()` does not validate.**
Services, forms and API serializers call `full_clean()` before saving.
*Rejected:* validating inside `save()` – Django's own tools (migrations,
fixtures, `bulk_create`) save without expecting validation errors.

**Releases side by side with a symlink.** An update installs the new
version in its own folder with its own Python libraries and then switches
`/opt/rentalars/app` and `/opt/rentalars/venv`. *Why:* the old version is
complete and untouched until the switch, and going back is switching the
links again (NFA-034). *Rejected:* updating in place with `pip install -U`.

**A backup is one file**: database dump, uploaded files, configuration,
version. *Why:* one thing to copy away, and a new server can be set up from
it alone. It holds the database password and the secret key, so it is
readable by root only.

**The sample page tests read HTML; a second, small set drives a real
browser.** *Why:* the page tests do not run scripts. A dialog that replaced
itself with the answer of its own availability check went unnoticed by 480
tests and was found by the first click in a browser (`tests/browser`).
They are optional, because they need a browser on the machine.

**Tests take place on a fixed day** (1 March 2027). The examples use fixed
dates, and the application compares dates with today in a few places;
without a fixed "today" the same test passes this year and fails the next.

**Type hints everywhere, but the type checker is not yet a gate.** Every
function is annotated. `mypy` with the Django plug-in still reports about a
hundred findings, most of them in the loosely typed parts of the frameworks
(request data, generic serializers). It is in `requirements-dev.txt` and
configured in `pyproject.toml`, but not part of `scripts/check.sh`. Making it
one is worth doing before the code grows much further. **[open point]**

### Performance (NFA-012 to NFA-014)

Deriving everything on demand only works if deriving is fast. What was
done, each found by measuring the full amount of data of acceptance
scenario 11 (see [docs/betrieb/betrieb.md](../betrieb/betrieb.md)):

**After a change of one line the page gets a patch, not the whole
planning.** Opening a project with 500 lines takes about half a second;
re-sending all of it for every new line broke the limit of half a second
for adding one. The server now sends the groups that can look different
and the totals. *Rejected:* giving up server-rendered pages for this one
page; and caching the rendered planning, which would have to be thrown away
on almost every change anyway. *Risk:* a part that should have been sent
and was not. `PlanningPatchTests` compares every patch with a full reload.

**The hints about the whole project follow in a second request.** "3
pieces are missing" needs the availability of every line – in a project
with 500 lines about 120 of the 300 milliseconds an answer took. With
everything in one answer, the half second for adding a line was kept on
average, but not for every answer: on a server with two cores the slowest
answer of a run was above it in 17 of 38 runs (up to 0.7 seconds). The
patch therefore judges only the lines it shows and those that compete with
them, and the block with the hints fetches itself when the answer
announces `planningChanged`. Measured afterwards on the same server: 0.2
seconds on average, the slowest answer under half a second in all 18 runs.
*Price:* each change of a line now costs the server two requests and about
half as much work again; when two users click without any pause on two
cores, opening the large project is slowed by this (once 1.04 seconds
instead of under one). With half a second between clicks nothing of that
remains. *Rejected:* leaving the hints out of date until the next page
load; and keeping the number of missing pieces in the database, against
the rule above that such figures are derived when needed. *Guard:* a
planning built for a patch refuses questions about all lines
(`Planning.partial`), and a test compares the verdict of every line in a
patch with the whole planning.

**The stock is counted in a form the indexes can answer.** "The product of
an item is the one named on it, otherwise that of its model" is one line as
a computed column – and reads every item for every question. Asked as
"items of the models that lead to the product, plus items that name it",
the stock of one product is an index lookup.

**List pages find their rows first and load the details second**
(`LeanPaginator`). The list of 20,000 items with product, model, category,
supplier and location went from 400 ms to about 100 ms.

**The overview of all shortages screens before it calculates.** Judging a
thousand projects one by one took over twenty seconds. A cheap test over all
projects at once now sorts out those that cannot be short; the exact
calculation runs for the rest. The screening is deliberately generous, so
it can only cost time, never hide a shortage; a test compares its result
with judging every project.

**"No end" is the year 9000, not the last day a date can hold.** Sold
material never comes back. Adding a buffer of a day to the last possible
date raised an error; a project with a sale line and a buffer of 24 hours
could not be opened.

**What was loaded at start is set aside from the garbage collector**
(`core/warmup.py`, `gc.freeze()`). Python searches all objects in memory
for garbage that refers to itself, every few requests. With the
application loaded that is about 110,000 objects that will never be
garbage. One such search took 90 to 230 milliseconds – inside whatever
request was running. Measured in one process: "add a line" took 175 to 250
milliseconds, and 467 when a search fell into it. After setting the
start-up objects aside the searches are short; the slowest of five runs of
"add a line" went from 391–451 to 206–240 milliseconds. Garbage that
requests produce is found as before. This was found last, and it explains
most of the "slowest answers" recorded before it.

**The application is loaded once, before the server splits into workers**
(`--preload`, `core/warmup.py`). URL table, language file and the 76
templates are read at that moment; the first request of a fresh worker
took 1.1 seconds for the large project without it and about half a second,
like any other, with it. Workers are replaced after 2,000 requests, so "first requests"
happen every day. *Condition:* nothing may open a database connection
before the split; a test checks that the warm-up makes no query.

**The application server answers one request per process – no threads.**
gunicorn first ran three processes with two threads each. Two requests that
landed in the same process then took turns at Python's interpreter lock,
although a second core was idle. Measured with two users working at the
same moment through NGINX (two cores, six runs of 15 rounds each): the
slowest "add a line" took 442 to 762 ms with threads and was over the
limit of 500 ms in five of six runs; with five single-request processes it
took 355 to 446 ms and was under the limit in all six. The medians moved
from about 330 to about 285 ms. The price is memory, about 90 MB for each
process. *Consequence:* a request that runs longer than the two minutes of
`--timeout` is now really ended (its process is replaced, the database
transaction is undone); with threads it kept running after NGINX had given
up on it, and its result arrived unseen. Tried with the limit set to eight
seconds and an import of 5,000 rows: the caller got an error after eight
seconds, no row was written, no transaction stayed open. NGINX waits ten
seconds longer than the application, so that the application always gives
up first.

**The browser and the API import at most 5,000 rows in one request**
(`MAX_IMPORT_ROWS_PER_REQUEST`). An import of 20,000 rows takes about
2:20 minutes on two cores, longer than a request may run; 5,000 rows take
about 35 seconds, the 1,650 rows of the present list about 15. Longer
files get a message that names the command on the server, which has no
limit (IMP-007). *Rejected for now:* running the import in the background
with a progress display – it needs a job queue, and the first stage that
needs one anyway is stage 4 (e-mail retrieval).


## Part 3: Ubuntu Server 26.04 LTS

The requirement: the scripts run on Ubuntu 26 as well as on Ubuntu
24 (NFA-063). What that turned out to mean, and what was decided:

**Two versions are named, and both are tried – not "24.04 or newer".** The
scripts list the Ubuntu versions they were run on
(`TESTED_UBUNTU_VERSIONS` in `deploy/lib.sh`). An older Ubuntu is refused
before anything changes, because its Python is too old. A newer one that is
not on the list is *not* refused: the installation says that it is untried
and goes on. *Why:* refusing would lock people out of an interim release
that most likely works; saying nothing would promise more than was checked.
*Consequence:* a new LTS version means running the scripts on it, recording
the result in `docs/betrieb/installation.md` and adding the version to the
list and to NFA-063.

**The scripts decide by what is installed, not by the Ubuntu version.**
There is no `if Ubuntu 26` anywhere. HTTP/2 is written into the NGINX site
in the form the installed NGINX understands (`adapt_nginx_site` asks NGINX
for its version; the directive `http2 on;` exists from 1.25.1). *Why:*
the same Ubuntu can carry another NGINX – from a newer package source, or
after an upgrade of Ubuntu under an existing installation – and it is NGINX
that reads the file. The function works in both directions and changes
nothing when the form is already right, so it can run with every update.

**What the scripts do on Ubuntu 26.04:** they run through.
Everything below was found by looking closer, not by a failure.

- NGINX 1.28 warns at every start that "listen … http2" is deprecated.
- MariaDB 11.8 warns that `innodb_file_per_table` is deprecated and will
  be removed. A database server that no longer knows a setting in its
  configuration does not start, so this one would have become an outage
  with some later Ubuntu. The configuration does not contain the line; it
  is the default anyway.
- WeasyPrint warns that it will require the library HarfBuzz-Subset.
  It is installed.
- `/tmp` is kept in memory since Ubuntu 24.10. Restore would unpack the backup
  there and the update the package; both unpack on disk, next to the data
  and next to the program.
- The Rust replacements of the basic commands (`install`, `ln`, `mktemp`,
  `date` and others come from uutils on 26.04) and sudo-rs made no
  difference: owners and rights of everything the scripts create (27
  files, folders and links) were compared with those on 24.04 and are the
  same.

**An update refreshes what Rentalars keeps in the configuration of NGINX and
MariaDB** (`refresh_server_configuration`): the proxy snippet, the form of
the site, the one deprecated MariaDB line, and the link
`/usr/local/bin/rentalars`. NGINX is reloaded only if `nginx -t` accepts
the result; otherwise the files are put back and a note is printed. *Not
touched:* everything else in the MariaDB file, which the operations guide
tells administrators to tune. *Limit:* an update is carried out by the
update script of the version that is installed; the new package is unpacked
and switched to, but its own scripts do not run during that update. What
a new version adds to the update therefore takes effect from the next update on.

**After Ubuntu was upgraded under an installation, the update is the
repair – and says that there is no way back.** The libraries of a release
are installed for the Python that was present when it was built. After the
change from 24.04 to 26.04 the installed release cannot start, and neither
can it be gone back to. The update notices (`release_runs`), says so before
it starts, and if it fails puts program and data back as they were and
leaves Rentalars stopped, which is what it was before. `rollback` refuses
with an explanation instead of switching to a program that cannot run.
*Rejected:* building the libraries of the previous release again for the
new Python during a rollback – its pinned versions may not exist for a
Python they were never released for. *Tried:* by taking the libraries away
from a release on 26.04 and putting the NGINX site back into the old form;
not with a real `do-release-upgrade`.

**The oldest supported Python stays 3.12.** Ubuntu 24.04 brings 3.12,
Ubuntu 26.04 brings 3.14. All pinned libraries install on both, and the
tests run on both – in the automatic checks against MariaDB 10.11 with 3.12
and against MariaDB 11.8 with 3.14, the pairs the two Ubuntu versions have.
Nothing newer than 3.12 may be used in the code until 24.04 is dropped.

## Part 4: Getting around

Three wishes from the first use of the program; requirements UIX-011 to
UIX-013 in the catalogue cover them.

**"Back" is kept by the application, not left to the browser**
(`core/trail.py`, UIX-011). The link in the top left corner leads to the
view the user came from, as it was – the list with filter, sort order, page
and page length. *Rejected:* `history.back()`. After "open, edit, save" the
browser's history leads into the form that was just saved, and after three
changes of a filter it needs three steps; it also needs a script, and a link
that only works with one. *Rejected:* a fixed link to the list of the
section (the breadcrumb already is one); it forgets filter and page, which
was the complaint. *How:* a short list of addresses, the trail. A start
page begins it, a new page is added, a page that is already on it cuts it
back to itself (so a circle "product, model, product" does not lose the way
out), the tabs of a project share one place, and a form that was sent and
led on is taken off. *Assumptions, marked [A] in the catalogue:* after
saving, "Back" leads past the form; the tabs of a project count as one
page; without a way behind, "Back" leads to the start of the section.

**The trail lives in a signed cookie, not in the session.** The session is
a row in the database; writing it for every page a user opens would add a
write (and with it a wait for the disk) to requests that otherwise only
read. *Consequence:* one trail per browser, shared by its tabs. A link is
fixed when its page is delivered, so it stays right whatever another tab
does; only the next page opened is added to a trail that both tabs wrote.
The cookie is signed and its addresses are checked to be paths of this
site, because they end up in a link. It ends with the browser session and
is deleted on logout.

**Entries per page: four fixed choices, remembered per browser**
(`core/listing.py`, UIX-012). 25, 50, 100, 200; any other number in the
address is ignored, so nobody can ask for a list of everything on one page.
The choice is part of the address like filter and sort order (UIX-004) and
is also kept in a cookie for a year, so that the next list opens with it.
*Rejected:* storing it at the user account – it would need a change of the
database for a preference that differs between phone and desk anyway. The
API keeps its own parameter (`page_size`, up to 500).

**"Material" opens the models** (UIX-013). The tab "Models" now comes
before "Items", and the navigation leads to the first tab. The addresses
are unchanged (`/material/` are the items, `/material/models/` the
models), so bookmarks and the links in the search keep working.

Products and material now share one entry of
the navigation, and it opens the products – see part 5.

## Part 5: Wishes from practice

The catalogue holds the requirements NFA-064, NFA-065, PRJ-062 to PRJ-065,
PCK-023, PCK-024, MAT-044 to MAT-046, UIX-014, UIX-008 and UIX-013 for
them.

**The setup page is closed unless a key exists and matches** (NFA-064,
`core/setup.py`). Before, a missing key file meant "no key needed", and the
installation script started the web server before it created the key: for a
moment anybody who reached the server could have created the first
administrator. Now a missing key closes the page (fail closed), and the
script creates the key before NGINX delivers the application. *Kept:* a
development environment may open the page without key, but only if the
setting says so explicitly (`SETUP_OPEN_WITHOUT_TOKEN`), which the
configuration of a server never does.

**Static files carry a fingerprint of their content in the address**
(NFA-065, `core/staticfiles.py`): `app.css?v=308a9f0eba`. The reported
"broken" page-size chooser was yesterday's stylesheet from the browser's
cache. *Rejected:* Django's `ManifestStaticFilesStorage`, which renames
the files – it needs `collectstatic` to run before anything works, also in
development and in tests, and rewrites references inside the stylesheet in
ways that break on a font address with a query string. A query parameter
computed from the file's content does the one thing needed.

**Dark by default, colours as tokens** (UIX-008). All colours are custom
properties in two tables at the top of `app.css`; `data-theme` on `<html>`
chooses. The house orange #EE591F is the colour of buttons and marks, with
dark text on it (white on this orange reaches only 3.5 to 1; dark text reaches 5.3). As a *text*
colour on the dark surfaces it would reach 4.3 to 1 on the raised ones, so
links and coloured text use a slightly lighter orange (#F47B4A).
#727272 is used for lines and borders, not for text: as text on the dark
background it reaches 3.8 to 1. *Left for later:* the switch to the light
theme; its table is complete and tested for contrast, print already uses
it.

**One navigation entry for products and material** (UIX-013,
`core/navigation.py`). An entry now covers several *sections*, each with
its module and address; it leads to the first section the user may read,
and each tab shows only with the right for its module. The addresses did
not change.

**A wish for a model or item is a hint, not a reservation** (PRJ-064,
`projects/wishes.py`). The availability of a product counts pieces, and the
whole point of products is that the pieces are interchangeable. Reserving a
named item would create a second, competing stock ledger. So the wish only
warns – item not usable, built into something, wished twice – and is served
first when items are allocated at issue (PCK-024).

**Rental days from a line's own period** (PRJ-062). Typed days still win;
the period comes second, before group and project. *Rejected:* writing the
counted days into the field when the period changes – it could not be told
apart from days somebody typed, and would stop following the next change.
The source is shown next to the number instead.

**After issue a row is "out", not "missing"** (PCK-023). The colour red
means one thing only: this row stands in the way of completing the return.
That state is not stored; it is requested with the page (`?open=1`) after a
refused attempt to complete.

**From "defective" only three ways** (MAT-045): in repair, retired, sold.
The rule lives in the model (`MaterialItem._clean_status_change`), so the
form, the API and the import obey it alike. *Assumption:* "lost" is not a
way out of "defective" – an item cannot be both in the workshop and gone.

**"Contains" is the same link as "installed in"** (MAT-046). There is one
field, `installed_in`; the page of the container only offers a second place
to set it. `add_content` refuses an item that is already installed elsewhere
instead of moving it silently: taking a receiver out of rack A by typing
its number at rack B would be a surprise in the wrong warehouse.

## Part 6: Personnel and time (stage 3)

### Business rules

**One crew line is one person or one open place.** "2 × stagehand" creates
two lines. *Rejected:* a line with a quantity. As soon as the first of the
two places is filled the line would have to be split anyway, and rate,
warnings and worked hours all belong to one person.

**Personnel is planned and charged in hours.** The catalogue allows "hours
or days" (PRJ-051) and puts day rates into stage 6 (PER-009). A service
product billed "flat" gives a flat customer price; that covers the day rate
on the customer's side today.

**Suggested hours** (PRJ-023): up to 16 hours the length of the period,
beyond that 8 hours per started day. A crew line that covers a three-day
project should not start with 58 planned hours and a cost to match. The
planner's own number always wins and is never overwritten.

**The rate is fixed twice** – on the crew line when the person is assigned
(PRJ-021) and on the time entry when it is recorded (ZEI-008) – each time
with the rate valid on the day of the work, not on the day of typing.

**Rights for one project are a second question, asked in one place**
(`projects/access.py`). *Rejected:* a filter in every view. Thirty views
and twenty API operations each remembering a filter is thirty-one chances
to forget one; a test that walks all addresses now proves that none did.
*Decided:* an invisible project answers 404, not 403, so that a restricted
user cannot find out which numbers exist. A membership never raises the
level above the role's (AUT-025). With the deployment view alone, the
customer of a project stays hidden as well – in lists, search, filters,
packlist and API (AUT-023).

**Personnel planning plans crew in projects it only reads.** The role of
chapter 4 reads projects and maintains personnel. `may_plan_crew` therefore
accepts "edit the project" *or* "read it and write personnel".

**Approving is a special right, not a module level** (ZEI-013). The level
"write" on time tracking is what everybody needs to record their own hours;
approving and recording for others is something else and is granted
separately (`APPROVE_TIMES`).

**The quick entry hands in at once** (ZEI-003, ZEI-012). Acceptance
scenario 18 expects recorded times to be "submitted" until approved; a
second step "hand in" after every entry would be the opposite of quick.
The tick can be removed for those who want to collect first.

**Internal projects have no customer and are open to everybody for
booking** (ZEI-010). *Rejected:* a pseudo-customer "internal" – it would
show up in every customer list and export.

**Anonymising a person reaches the account and the change log**
(NFA-009). The log stores related records by ID and resolves names when
shown, so most of it follows by itself; the free texts and two events that
carry a name are scrubbed explicitly. A superuser account is only unlinked.

### Technology

**`projects` does not import `timetracking`.** Time entries point to
projects, and the project needs approved hours per crew line. The one
function that needs them looks the model up by name
(`apps.get_model`), which keeps the dependency pointing one way.

**No database constraint against overlapping entries.** MariaDB has no
exclusion constraint for ranges. The check runs inside the transaction that
saves the entry, with the person's row locked;
`tests/unit/test_concurrency.py` races two identical entries against each
other on MariaDB.

**The existing API-coverage check became stricter.** The test runner
(`rentalars/testing.py`) now counts an operation as tested only if a test
reached it *successfully*. With rights per project there are many tests
that only prove a refusal, and those alone should not make an operation
count as covered.

**Ten people at once is measured against the running server** (NFA-051,
`manage.py measure_concurrency`): real requests through NGINX, with test
accounts the command creates and removes. "Usable" is taken to mean that
every answer arrives within two seconds – the catalogue gives no number.

**The load-test data includes stage 3.** `create_load_test_data` also
creates a person for each of the 100 accounts, three crew lines per project
(20 in the big one) and 20,000 time entries – about a year of 100 people –
and `measure_performance` times the pages of personnel and time entry as
well, some of them as one of the generated people. Measuring this found two
problems before the release:

* *The CSV and PDF of the unfiltered report held every entry.* The page
  shows the current month when no filter is set, but the file links carry
  `format=…`, which counted as a filter. With a year of data the CSV took
  three seconds and held 20,000 rows instead of the 700 on screen. Now
  `format`, `page` and `per_page` do not count as filters.
* *The report listed every entry on one page.* A month of 100 people –
  2,200 entries – made a page of 2 MB that took over a second. The sums
  still cover everything; the list of entries below them is paged like any
  other list (UIX-012). Now 140 kB and 0.4 to 0.5 seconds.

**A timesheet holds at most 3,000 entries.** WeasyPrint needs about
0.2 seconds per page of the timesheet; a month of 100 people (2,200 entries,
78 pages) took 15 to 20 seconds on the 2-core test machine, almost all of it
in the page layout – `border-collapse`, `break-inside` and a fixed table
layout made no difference. A year of everybody would run past the 120
seconds the server allows a request and end in an error page. Above the
limit the page says so and asks to narrow the selection; the API answers
400 with the same text. The CSV file has no limit (a year, 20,000 rows: about
three seconds).

## Part 7: Correspondence and planning (stage 4)

### Business rules

**One shared project mailbox, fetched – no mail server of our own**
(EML-001 ff.). Rentalars reads an existing mailbox over IMAP and sends
through its SMTP server, the way a ticket system does it.
*Rejected:* receiving mail directly (an MX record, spam filtering, a server
that must never be down) and one mailbox per user (the project, not the
person, is what the mail belongs to).

**Only assigned mails are touched** (EML-006, EML-013). The fetch reads
headers with `BODY.PEEK`; a mail without a tag and without a reference stays
in the inbox, unread, as if Rentalars did not exist. A mail with a tag for
which there is no project stays there too and is listed for assignment by
hand. Only an assigned mail is taken over completely and then moved – never
before it is stored.

**Mails are kept until somebody removes them** (EML-031). A period in days
can be set; 0, the default, keeps them. Removing a mail from Rentalars
leaves the copy in the mailbox folder alone.

**External pictures are loaded per mail, on request** (EML-027). *Rejected:*
"always load from this sender" – a list that grows quietly and that nobody
looks at again.

**Deployment requests for people without an account are entered by the
planner** (PER-016). Freelancers are often asked by phone. The request
status on the crew line is the same either way; whoever has an account may
answer in Rentalars.

**Notifications by mail are on, except for changes of a project** (UIX-005).
Changes happen many times a day; the bell is enough for them unless
somebody asks for more. Shortages of the coming four weeks are checked
every night and reported once per line (`ShortageNotice`), not every night
again.

**One start page for everybody**, filled by rights and the linked person,
not by the name of a role (UIX-003). Roles are renamed and combined; rights
are what the code knows.

**A duplicated project starts as an inquiry, with open places instead of
people** (PRJ-029). The copy is a new job; the old crew has not been asked.
Times keep their clock time across a change of daylight saving time: a
setup at 08:00 in March stays at 08:00 when copied to November
(`projects.services.wall_clock_shift`, `moved`). *Rejected:* shifting by a
fixed number of hours, which would turn 08:00 into 07:00 or 09:00.

**The crew sees project files by document type, or one by one** (PRJ-007,
AUT-023). Stage plan, rider, schedule and hall plan are meant for the crew;
contracts and orders are not. `DocumentType.visible_to_crew` sets the
default, `ProjectFile.visible_to_crew` the exception.

**An error of the application is reported once, and again after 24 hours
if it continues** (NFA-018). `ErrorRecord` counts it. A thousand mails about
the same broken disk help nobody.

**The price overview names what a group contains** (PRJ-066). A group shown with its total only gets one line such as "8 ×
LED-Scheinwerfer RGBW, 6 × Traverse 4-Punkt 2 m": lines of the same product
added up, kits as kits, subrentals that only cover a shortage left out, and
at most six things named, the most valuable, followed by "and 12 more"
(`projects/summary.py`). The summary is meant as an approximation.

### Time tracking (requirements from use)

**No time in the future** (ZEI-022). Neither begin nor end may lie after
the moment of saving – in the quick entry, the form, the API and on change.
Hours are written down after they were worked. The stopwatch begins now and
is therefore never in the future. *Assumption:* there is no tolerance; a
clock on the phone a minute ahead of the server's is the case in question.

**Time without a project** (ZEI-023). An entry may be saved without project,
with one of the person's own job functions. It counts nowhere – not on a
crew line, not in a project's costs – and cannot be approved until a project
is assigned: by the person while the entry is open, or by whoever approves.
A batch approval that contains such an entry is refused as a whole and says
how many lack a project. Entries without project are visible to approvers
whose right holds for all projects only; a crew chief limited to assigned
projects has no project through which to see them.

### Login and sessions

**Two-factor login is TOTP by RFC 6238, written in a few dozen lines
rather than taken from a library** (AUT-006). Six digits, 30 seconds, one step either
side for clocks that drift, a code accepted only once (`totp_last_step`).
Any authenticator app works. Ten recovery codes, stored as hashes. An
administrator can reset the second factor of somebody who lost the phone;
if the administrator is the one who lost it, `manage.py reset_two_factor`
on the server does the same. *Rejected:* `pyotp` and `django-otp` – the
algorithm is short and stable, and every library is one more thing to keep
up to date. The QR code is drawn as SVG by `segno` on the server; no
script is needed.

**API tokens are a key of their own and need no code.** They are created
only by somebody fully logged in, can be narrowed and revoked. The API
login with password does take the code in the same request.

**Logout after 240 minutes without activity** (AUT-008), set in the system
settings. A working day on the warehouse floor has long pauses; four hours
cover a lunch break without letting a forgotten browser stay open
overnight. The security log is kept for a year (AUT-022).

### Operation (requirements from use)

**An existing database server – but never with `root`** (NFA-066). The requirement:
rule out `root` explicitly. The name is refused, and beyond the
name the rights are checked: the account must have every right on its
database and **no right on anything else**, including rights it gets
through roles (`core/database_account.py`, from `SHOW GRANTS`). A name
alone proves nothing; an administrator account can be called anything. The
check runs before the installation writes anything, again at `move-database`,
and in the self-check of the running application. The connection is
encrypted by default.

**Encryption is MariaDB's own, with one recovery key** (NFA-067). The requirement:
encryption that authenticated people can still undo easily in an
emergency. MariaDB's data-at-rest encryption is transparent for whoever can
log in to the database, so nothing changes for root on the server; its key
file is locked with a recovery key that also encrypts the backups. With that
key and `openssl` alone a backup can be decrypted on any machine – no
Rentalars needed. The key is shown once at installation, to be kept outside
the server. *Rejected:* encrypting fields in the application. Search,
sorting and the database's own checks would stop working, and the key would
still have to live on the same server as the data. With a database on
another server, Rentalars encrypts only its backups; the files are that
server's matter.

**Switching it on afterwards: in place, with a proof** (NFA-067). The
open question was how consistency could be kept; the proposal was a new database, a
check, then the switch. For encryption on the same MariaDB that detour is
not needed: MariaDB encrypts table files in the background under its own
crash-safe bookkeeping, the same as any other write. What the proposal
asked for – proof that nothing changed – is kept: Rentalars is
stopped, every table is fingerprinted (rows and a SHA-256 over all values),
MariaDB encrypts, the fingerprint is taken again, and Rentalars starts only
if not one value differs. A backup from just before is kept either way.

**The procedure is `rentalars move-database`** (NFA-068): a new,
empty database with its own account – on another server or this one – is
checked like at installation, filled, fingerprinted against the old one,
and only then connected. The old database is left untouched as a way back.
It covers moving to an encrypted database server, to a central company
server, and back.

### Technology

**`nh3` cleans the HTML of mails; a sandboxed frame shows it** (EML-027,
NFA-050). Two walls: if the cleaning missed something, the frame runs no
script and loads nothing from outside unless the reader asked for the
pictures. `tests/browser/test_stage4_in_browser.py` checks in a real
browser that a script in a mail does not run and a tracking pixel is not
requested.

**IMAP with `imaplib` from the standard library; servers without `MOVE` or
`UIDPLUS` are not supported.** Without them, removing one mail means
`EXPUNGE`, which also removes every mail somebody else marked as deleted.

**The mail timer fires every minute; the interval is a setting in the
database.** The operator changes the interval in the browser without
touching systemd. A lock file keeps the timer and "fetch now" from fetching
at the same moment. `rentalars.service` has `Wants=rentalars-mail.timer`,
so the timer also starts after an update by the 0.3 update script, which
does not know it.

**Secrets in the database are encrypted with a key derived from the secret
key of the configuration file** (`core/crypto.py`, `cryptography`'s
Fernet): mail passwords and TOTP secrets. A copy of the database alone
opens no mailbox. Consequence, written in `sicherung.md`: a restore needs the
configuration file with the same secret key, or the mail passwords must be
entered again and the second factor set up again.

**Problems of the self-check are logged every night** (NFA-037). The daily
maintenance runs the self-check at 04:15 and logs its errors – and backup
warnings – through the logger `rentalars.selfcheck`, so that they reach the
operators like errors of the application. A backup counts as current for 25
hours: the backup runs at 02:30 with up to ten minutes of random delay, so
24 hours would warn every other morning.

**An update never rewrites the NGINX site; `rentalars nginx-site` does, on
request.** The administrator may have changed the file (another
certificate, an extra location), and a web server that stops answering
after an update is worse than one that lacks a new hardening. The update
only adapts what the installed NGINX demands; the self-check names
settings of the template that are missing; `nginx-site` shows the
difference, asks, keeps the old file and reloads only if `nginx -t`
accepts the new one. Found when updating in the test
environment: the new blocks for foreign host names did not arrive.

**The installation writes the first backup at once.** Until the first night,
the self-check would otherwise report "no backup" on a fresh installation,
and an operator who deletes the database in the first hour has nothing.

---

## Part 8: Warehouse and documents (stage 5)

### Lists, calendar, timelines (requirements from use)

**One table definition per list, rendered on the server** (UIX-015,
IMP-005). `core/tables.py` describes the columns of a list once – label,
cell, text for CSV, sort fields, default on or off, visible only with a
right. The page, the column chooser and the CSV export all read it, so a
column that is shown can always be exported and sorted. The choice of
columns is stored per user and list (`TablePreference`) and follows the
person to another computer. Sorting is a link on the heading that keeps
filters and page size. *Rejected:* a script that sorts the table in the
browser – it sorts one page of fifty rows, not the list, and knows nothing
of the CSV.

**The calendar remembers month or week for the session** (PRJ-067). A
planner who looks at weeks keeps looking at weeks; a new login starts with
the month again. *Assumption.*

**Every product, model, item and person has a timeline of 1 to 12 weeks**
(VFG-019, PER-020). The item's timeline also shows the demand of its
product, so that "is this exact piece free?" and "is the product short?"
are answered on one page. The person's timeline marks the day a
qualification expires. The planning page that was called "Zeitleiste" is
now "Zeitstrahl", as the catalogue always called it.

### Material

**Due dates of inspections are calculated, never stored** (MAT-030,
MAT-031, MAT-032). An inspection type applies to the models of its categories
(subcategories included) and to models named directly. Due = last passed
inspection + interval; a failed inspection makes the item due at once.
**[assumption]** An item that was never inspected is overdue: "we don't
know" is not "fine" for an electrical test. The last inspection from the
paper records can be entered. Each item, type and due date is reported to
the warehouse once (`DueNotice`).

**A product's weight on the packlist is that of its heaviest model**
(PCK-006). **[assumption]** A product can be served by models of different
weight; the truck must carry the heavier. Rows without a weight are counted
and named, so that a sum is never silently too low.

### Packing

**Several packlists; the first one is the main one** (PCK-008). Lines that
are not assigned to another packlist belong to the first (`LineAssignment`
only records the exceptions), so a project that never uses a second
packlist works as before. Material that went out on a packlist stays there;
it cannot be moved to another.

**Changes after packing started are shown against a snapshot** (PCK-015).
When the first row is ticked, the required quantities are recorded; later
changes of the planning appear as "more", "less", "new", "dropped" until
the warehouse acknowledges them.

**Choosing items stays voluntary** (PCK-022). Whoever ticks packs as
before; a chosen item enables what needs a specific piece: its contents go
out and come back with it (MAT-037), and an overdue inspection warns at the
issue (MAT-032).

### Customers

**Default addresses are taken by the service, not only by the form**
(KND-005). `create_project` fills billing and delivery address from the
customer's defaults when the caller chose none – the form, the API, a
duplicate. When the customer of a project changes, addresses of the former
customer give way to the new one's defaults. The project form sends back
whose addresses it offered (`addresses_for`), so that a customer picked in
the same form still gets its defaults. Found while writing the manual.

**The standard discount goes into each new material line** (KND-006), where
it can be changed; percentage surcharges do not get it, they already follow
the discounted amounts.

### Documents

**A document is a snapshot** (DOK-007). Its content is assembled once
(`documents/content.py`), stored as JSON, rendered to PDF, and the PDF is
stored with its SHA-256. The model refuses changes and deletion; only "sent
at/to" and "cancelled by" can be set. Later changes of prices, addresses or
texts never reach a document that exists.

**One valid invoice per project; a wrong one is cancelled** (DOK-006). The
cancellation is an invoice with negated amounts (type 384) that names the
invoice it cancels, and it draws its number from the invoice range, so
invoice numbers have no gaps (§ 14 UStG). Then a new invoice can be made.
*Rejected:* editing or deleting a draft invoice that already has a number.

**Every invoice comes with an XRechnung** (DOK-006): EN 16931 with the
German specification XRechnung 3.0 in UBL 2.1, written with the standard
library's `ElementTree` from the stored content. What it needs and the
company data lack is named before the invoice is made. The buyer reference
is the customer's Leitweg-ID, else the project number – public authorities
require their Leitweg-ID (found while writing the manual). Checked with
the KoSIT validator 1.5.0 and its XRechnung 3.0.2 configuration of
31 January 2026: invoices and cancellations with group discounts, flat
prices, a percentage surcharge, crew lines and two tax rates (19 % and
exempt) pass schema and schematron without a warning. The check found two
things: the seller's telephone number is required (BR-DE-6), and a
cancellation must name the company as it is on the day of the
cancellation, not as the invoice did. *Rejected:*
ZUGFeRD (CII embedded in a PDF/A-3) – another syntax and a stricter PDF
for no gain over sending the XML along.

**The period of service is the reservation period** (DOK-006). The rental
days are counted over it; the placeholder `{period}` of the texts says the
same.

**Optional groups are on the order confirmation, not on the invoice.** The
customer may still choose them while confirming; the invoice is what is
owed.

**Every kind of document counts on its own**: AB-, LS-, RE- and CD-year-
number. The general range "document" of stage 1 stays in the database but
is not used and not shown.

**Documents stay when a customer or person is anonymised** (NFA-009).
**[assumption]** Invoices and what they rest on must be kept for years
(§ 147 AO, § 257 HGB); erasure gives way to that duty (Art. 17 (3) b
GDPR). The crew disposition contains only contact data the person released
for colleagues.

**Text blocks are offered per kind of document** (DOK-005). The form shows
a block only while a kind it fits is chosen, and the service drops a block
that does not fit. Cancellations take over their invoice and get none.

### Import, export, background

**One import machinery for four lists** (IMP-001). `core/tabular.py` reads
files and maps columns, `core/imports.py` keeps a registry of
`ImportKind`s – material, products, customers, people – that the modules
register in `AppConfig.ready()`. Page, API and the command `import_data`
share it. Every import writes all or nothing and has a dry run. The
headings of the exported lists are recognised, so a list exported with all
columns comes back unchanged (tested for products, customers, people).
Records are found by article number, customer number and e-mail address
or name. **[assumption]** A customer number the database does not know is
taken over, so numbers of an earlier program survive.

**Dry run and import run in the background in the browser** (NFA-041).
That ends the limit of 5,000 rows per request in the browser (Part 2). The
API keeps the limit inside one request and offers `background`.

**A task in the background is a process of its own, with a timer of its
own** (NFA-041, NFA-028). No queue and no broker: `start_job` stores the
task and starts `manage.py run_jobs --job N` when the transaction is
committed. `rentalars-jobs.timer` runs, every minute, what could not be
started and starts again – once – a task whose process is gone; the task
records host and PID. The timer was first part of the mail fetch; a long
export would have held up the mail and run into its ten-minute limit.
*Rejected:* Celery or RQ – a second service and a broker for a handful of
tasks a day.

**Only the one who started a task sees it and its result.** The full
export holds the data of everybody; another administrator starts an export
of his own, which is recorded in the change log. Found while writing the
operations guide.

**The full export is open formats, not a backup** (IMP-006): every table
as Django JSON and as CSV, all stored files, a text that explains it.
Password hashes, two-factor secrets, token hashes, mail passwords and the
setup token stay out. Loading it into a freshly installed Rentalars of the
same version with `loaddata` was tried with the demo data (70 tables, 544
rows, no error). Backups stay the way to restore an installation.

### API

**The rate limit counts in the database** (API-011): one row per token and
minute, counted up with an `UPDATE`. The application runs as several
processes; a counter in the memory of one process would allow several
times the limit. 600 calls per minute is the default, changeable, 0 off.
Calls from a browser session are not counted.

**Idempotency-Key and ETag are middleware** (API-010), so that every
endpoint has them without being written for it. The answer to a changing
call with a key is stored for a day, per token; an answer with a server
error is not stored, so the client can try again. The ETag is a hash of the
JSON delivered; `If-Match` is checked by asking the view for the current
representation first. *Rejected:* a version column on every model – forty
models to change, and it would miss changes of related data that the
representation shows.

### Operation and quality

**Retention periods are settings, the change log is kept by default**
(NFA-011): security log 365 days, notifications 180, results of tasks 7.
The daily maintenance applies them. Mail keeps its own period (Part 7).

**Accessibility is checked twice** (NFA-025): with axe-core against WCAG
2.1 A and AA in a real browser (`tests/browser/test_accessibility_in_browser`,
run when `RENTALARS_AXE` names `axe.min.js`), and on every test run by a
small checker of what the HTML alone shows (`tests/ui/test_accessibility`).
axe-core is not shipped; its licence (MPL 2.0) is not the point, a test tool
the users never run is. There is a skip link for the keyboard. See
[accessibility.md](accessibility.md).

**One command measures the own hardware** (NFA-044):
`measure_performance --create-test-data` fills a test installation with the
amounts of the catalogue if needed and measures, now including the pages of
this stage. It refuses to run before the first setup in the browser:
without a company and an administrator every page answers with a redirect
to the setup, and the times measured would be those of the redirect.

**The packlist reads plain values, not objects** (NFA-014). Loading every
material item of the products on the list as an object, with its model and
location, for the hints (inspections due, items in repair, the storage
location as walking order) took 1.3 to 1.5 seconds for the packlist of the
500-line project on the reference amounts. The hints read only the IDs and dates they need
(`values_list`), the path of every storage location is built once from one
query, the inspection rule runs on plain values (`InspectionPlan.overdue_ids`,
the same rule as `dues_for`, which a test holds together), and only items
installed in a device are loaded as objects, because their device decides
where they lie. Measurements: see the operation guide.

**The load test data has the things of stage 5** (NFA-044).
`create_load_test_data` puts every item into one
of 200 compartments of a storage tree (two halls, ten shelves each, ten
compartments each) and gives the items of two main categories an
inspection every twelve months, recorded on some day of the last 14 months
– about a fifth of them overdue. With that data two pages asked per row: the material list asked for the parents of
every item's place (three levels: 860 queries for one page), and so did the
list of storage locations in its filter and its forms. **Paths of storage
locations come from one query** (`masterdata.models.location_paths`,
`remember_location_paths`); a table definition has a `prepare` hook that
loads what the cells of a page need before they are written, for the page
and, in parts of 2,000 rows, for the CSV file. The timeline of an item works out its product's demands once
(`utilization_with_demands`), and the page shares one
inspection plan. And the overview of due inspections loaded all 8,000
inspected items as objects to show the first 500 (850 to 900 ms on the
reference amounts): `InspectionPlan.due_rows` now works out the dues on
plain values, and only the rows shown become objects (`with_items`). The
due date of an item comes from one function, `_due_date`, which the item
page, the overview, the packlist and the timeline all use.

**A CSV cell is the text of the HTML cell, unescaped.** Without a `text`
function a column's CSV value is its HTML without tags; "&" stayed
"&amp;" and ">" stayed "&gt;" – a customer "Müller & Söhne" came back from
its own export as "Müller &amp; Söhne". Found by the test above; the round
trip tests now carry names with "&" and quotes.

**The migrations of stage 5 are one per app.**

---

## Part 9: Requirements from practice

About 55 requirements from the use of the application, delivered as a release of their own
before stage 6 (catalogue: 45 new requirements in stage 5, chapter
12.1 "Weitere Anforderungen", chapter 12.2 number 17). The
catalogue decided the order – first the wishes, then stage 6 (chapter 10)
– and moved two further wishes into a stage 7 of their own: a summary of
the correspondence by an AI (EML-040), only running locally and only once
that is stable and fast, and login through LDAP (AUT-029).

### People and accounts

**Every person is an account, every account a person** (AUT-026). *Rejected:* personnel without
login – decided: every person signs in (catalogue 12.1). `Person.user` is therefore a OneToOne field that is never
empty, `PROTECT`, and not editable in forms. `User.save` creates or updates
the person, `Person.save` creates or updates the account; first name, last
name, e-mail address and "active" are the same on both. `User.save` passes
on only the fields that were saved (`update_fields`): a login saves only
`last_login`, and an account object loaded before somebody changed the
person must not write its stale name back. `Person.save` writes the four
shared fields onto the account with one `UPDATE`, so that the two saves
never call each other in a circle.

**A new account gets a name, no password and the role of the crew**
(AUT-026, catalogue 12.2, 17 a). The username is made from the name –
`anna.becker`, then `anna.becker2`, umlauts written out (`joerg.mueller`)
–, the password is unusable until the person is invited or gets a
one-time password, and the role is "Crew", or "Freie Kraft" for a
freelancer. Further roles are given under Settings → Users. `User.email`
is optional now (NULL instead of an empty text) and unique: an address
belongs to one person (`Person.clean` checks it).

**Deleting and erasing keep the company able to log in** (AUT-026,
catalogue 12.2, 17 b). A person whose account never logged in can be
deleted, and the account goes with it. A person who has logged in cannot
be deleted – deactivated or anonymised instead –, nor can the last account
with access to the settings. Anonymising closes and anonymises the account
as well; an account with all rights is refused until that right is taken
away, so that erasing the personnel data of the boss cannot lock the
company out of its own system.

**The data migration links what exists**
(`personnel/0004_every_person_an_account`). Every person without account
gets one as above; an anonymised person gets an inactive account named
`anonym-p<pk>`. An e-mail address that another account already uses is left
off the new account and moves from the person into the person's note
("E-Mail-Adresse vorher: …"): person and account share one address from
now on, and an address belongs to one account, so the person could
otherwise not be saved again. Every account without person becomes a person – the
administrator of the first-run setup included. Pairs already linked
take the person's names and the account's address, the one it logs in with.
The migration cannot be reversed; the way back is the backup the
update writes.

**Who is offered for planning is who has the job function** (PER-025).
`people_choices()` in `projects/forms.py` builds the options of the person
field; each carries `data-functions` with the IDs of the person's job
functions, and the page script narrows the list to the function chosen in
the same form. Planners with the special right to plan outside job
functions (PER-006) get `data-any`: they see everybody, also people
without any function. The personnel plan lists active people with at
least one job function, plus anybody deployed in the span shown
(`schedule.services.plannable_people`) – somebody planned outside his
functions is never hidden. Pure office accounts, which AUT-026 brought
into the personnel, stay out of both. Without "Nur
Personen mit Einsätzen oder Abwesenheiten" the personnel plan shows every
active person, office accounts included; `plannable_people` became
`people_in_plan` (VFG-023, Part 15). The person field keeps the rule.

**A person has a position in the company** (PER-024), `Person.position`,
e.g. "Leitung Licht"; the signature shows it as `{position}`.

### Login

**A one-time password for people without e-mail** (AUT-027). Four groups
of four characters from an alphabet without look-alikes (no `i`, `l`, `o`,
`0`, `1`), shown once to the administrator who set it; recorded in the
security log. `User.must_change_password` is set with it.
`PasswordChangeRequiredMiddleware` (after the login check, before the
two-factor one) then sends every page to `/account/new-password/` and
answers the API with 403 `password_change_required`, so the password that
was handed over is good for nothing but choosing an own one.

**"Forgot password" reaches invited accounts** (AUT-027). Django sends the
link only to accounts with a usable password; an invited user who lost the
invitation has none and got nothing. `ResetPasswordForm.get_users` sends it
to every active account with that address. This was the bug reported
for resetting the password of new users.

### Calendars of the people (PER-021 to PER-023)

**The own availability is painted, not listed** (PER-021,
`personnel/marks.py`). A person colours periods green, yellow (with a
note) or red. A new colour replaces whatever the person had in that period
– an older mark is cut back, split or removed –, the same colour with the
same note next to a mark joins it, "clear" removes the own marks. Red warns
when the person is planned (PRJ-022) and counts as absent in "who is free";
yellow is a hint; green puts the person first among the free ones. Marks
read from a linked calendar are never touched by the brush.

**A linked calendar is read; its titles are not** (PER-022,
`personnel/calendars.py`). The private ICS link of a Google, Outlook or
iCloud calendar is enough. It is read every 30 minutes for the past month
and the coming half year (catalogue 12.2, 17 c); busy appointments become
red marks, repeating ones unfolded, free and cancelled ones left out, at
most 3,000. Planning learns *that* the person is busy, not *why*. A
successful reading replaces the marks of the one before; a failed one keeps
them and notes the problem at the person. After six failures in a row –
about three hours – the person is told once, with the new notification
kind `calendar_problem` (migration `notifications/0003_calendar_problem`),
by e-mail unless switched off.

**Deployments go out two ways, because the server is often not on the
internet** (PER-023, catalogue 12.1). One is an `.ics` file and a
subscription link `/calendar-feed/<pk>/<token>.ics` that calendar programs
read without a login. The token is 256 random bits, compared in constant
time; a new one ends the old link. The file holds what the person sees of a
deployment anyway (AUT-023) – no customer, no prices. Rentalars slows down
guessing (20 wrong links per address in ten minutes) and readers that ask
far more often than a calendar program (60 readings of one link in ten
minutes), and answers an unchanged calendar with 304.
`deploy/nginx/rentalars.conf` limits `/calendar-feed/` like the login; an
existing server gets that only with `rentalars nginx-site` (Part 7: an
update never rewrites the site). The other way is for servers that phones
cannot reach: Rentalars writes into a CalDAV calendar on the internet
(Nextcloud, iCloud, mailbox.org, Posteo …), one event per crew line with a
stable UID – `PUT` with `If-None-Match: *` for a new one, with `If-Match`
for a change, `DELETE` for what is gone. `CalendarPush` remembers digest and
ETag of each, so only changes are written. Rentalars owns these events: if
somebody changed one on the phone (412), Rentalars' version is written over
it. The address may be just the server; discovery (RFC 6764, RFC 4791) finds
the calendar "Rentalars" of the account or creates it. *Rejected:* writing
into Google Calendar – its CalDAV access needs OAuth (catalogue 12.1);
Google reads the subscription link instead.

**The calendars ride on the minute timer of the background tasks.**
`run_jobs` calls `personnel.calendars.run_due()` after the waiting tasks:
linked calendars not read for 30 minutes, CalDAV calendars marked due by a
changed crew line – within a minute – and every 30 minutes anyway. A crew
line marks its people through a `pre_save`/`post_delete` signal connected
by the model's name, so `personnel` imports nothing of `projects`. A run
starts nothing new after 40 seconds and takes at most 200 people per kind;
the rest is due the next minute. It never raises: one broken calendar must
stop neither the others nor the tasks. `manage.py sync_calendars` does the
same by hand, `--person ID` for one person at once. No new timer and no
new unit: an update has nothing to switch on.

**Addresses that people type in are not trusted**
(`personnel/calendar_client.py`). Only the standard library (`urllib`); only
`http` and `https`, also after a redirect, `webcal://` read as `https://`;
15 seconds without an answer end a request, twice that in total; an answer
above 5 MB is refused. What a server answers is never shown, and an error
names the kind of problem, never the address, which may be a secret link.
Credentials go only to the site they were entered for: a redirect to another
site, or from https to http, loses them (`p52-caldav.icloud.com` counts as
`caldav.icloud.com`). Internal addresses are allowed on purpose: the
company's own Nextcloud may be one. The CalDAV password is encrypted like
the mail passwords (`core/crypto.py`).

**The person decides about the own calendars.** On "Meine Personaldaten"
(`/me/`) a person paints, links a calendar, downloads or subscribes to the
deployments and sets up CalDAV, without any right on the personnel module.
Personnel planning sees the calendar with read access and, with write
access, paints it and links or removes a calendar for the person; the
CalDAV settings and the subscription link stay the person's own business.

### Projects

**Templates keep the structure, not the prices** (PRJ-076, which carries
out PRJ-030; `projects/project_templates.py`). `ProjectTemplate` has a
name – unique without regard to case, checked by the service –, a
description, `content` as JSON with `version: 1`, the number of the source
project and who made it. The content keeps groups, lines (product key,
quantity, sale or rental, note, model wish, variant; lines without product
with title and, for whoever may see prices, price), crew places without
people, phases and open items. Times are kept as wall-clock seconds from
the project start, so a template saved in summer lands on the same clock
times in winter; periods of their own are cut to the new project.
Applying goes through `services.add_line` and `add_crew_lines`, so the
prices are those of the day and the customer's discount applies, as if the
lines were added by hand (catalogue 12.2, 17 d); a group's own price rules
are kept only for whoever may see prices. Products and job functions that
are gone or deactivated by then are left out and named. API:
`/api/v1/project-templates`, and `template` when a project is created.

**Old prices are offered, not forced** (PRJ-072,
`projects/price_updates.py`). Material and crew lines store `list_price`,
the product's price when they took it over; a line whose unit price differs
from it was set by hand. The data migration filled `list_price` only where
the unit price still equalled the product's price; the other old lines count
as set by hand. The hint appears only for an inquiry or an option – a
confirmed project keeps what was quoted; the API lists old prices for every
status. "Take over all" changes only lines not set by hand; those set by
hand are taken over or kept line by line, and "keep" records the new price
as seen. The line's discount stays. Found on the way: after "Auf aktuelle
Staffel umstellen" the hints alone replaced the planning, because the form
sat inside `#planning-notes` and inherited its `hx-select`. Fixed twice:
`hx-disinherit="hx-select hx-target hx-swap"` on the hints and
`HX-Reselect: #planning` on every answer that carries the whole planning;
the browser test fails if both are removed.

**Optional and alternative lines show their price and count nowhere**
(PRJ-075). `MaterialLine.variant` is empty, `optional` or `alternative`.
Such a line is priced where it stands, but left out of its group's sum and
discount, the totals, taxes and costs, the invoice and the packlist. It
reserves softly, like an option, and takes no stock from lines that count
(catalogue 12.2, 17 l); a percentage surcharge includes it only if the
surcharge is optional too; group summaries leave it out. **Duplicating**
puts the copy right below, in the same group, with prices, discount,
`list_price`, variant, surcharge targets and model wish – not the wish for
a specific item. A covering subrental cannot be duplicated. No price right
is needed.

**The offer is a document of its own** (DOK-010). First in
`DocumentKind`, its own range `AN-{year}-` (`core/0005_offer_number_range`),
`valid_until` (14 days unless changed, placeholder `{valid_until}`), no
XRechnung. It is priced like the order confirmation, with optional groups
and lines marked. Any number of offers per project.

**A job function can cap the discount** (PER-026, `projects/discounts.py`).
`JobFunction.max_discount_percent`: empty no limit, 0 never discounted. It
applies to crew lines, which have a discount of their own
(`CrewLine.discount_percent`), and to material lines whose product is the
service product of a job function – the strictest maximum if several share
it (a service product belongs to exactly one function and is
not planned as material – PRD-044,
Part 15). It caps a line's own discount plus its share of the group's discount,
amount or flat price. What a line may not take is not passed on to other
lines (catalogue 12.2, 17 k): the group discount shrinks, or the flat price
rises. Stored values stay as typed. The customer's standard discount stays
for material lines only, so new crew lines start at 0 %.

**Projects run from noon to noon** (PRJ-068). The defaults are 12:00 to
12:00 of the next day; migration `core/0007_noon_to_noon` changes only
installations that still had the old defaults 08:00 to 20:00 – an own
choice stays. **Crew hours read the clock** (PRJ-073, `suggested_hours`):
a period up to 16 hours is taken as worked through; a longer one is read
with its clock times per day when the daily span is between 1 and 16 hours
– 08:00 to 20:00 over three days is 36 hours, not 24 (catalogue 12.2,
17 e) –; otherwise 8 hours per started day, as before.

**Customer and venue are typed into the project form** (PRJ-070). Both are
type-ahead fields (`templates/core/_typeahead_field.html`) with a hidden
value. For users who may write customers the suggestions end with a
"create" entry carrying a `create_url`; the quick-create views open in the
dialog and answer 204 with `HX-Trigger` `closeDialog` and `objectCreated`
{field, id, label}, which the field takes over. The same duplicate check as
on the customer page (KND-008). The fields of the customer form became one
include, `customers/_form_fields.html`; that fixed a bug: editing
a customer in the browser cleared the buyer reference (Leitweg-ID), and the
tax number was missing.

**A lighting plot is counted, matched and remembered** (PRJ-077,
`projects/mvr.py`). Fixtures, trusses, supports, video screens, projectors
and scene objects that name a GDTF file are counted, also inside nested
groups; objects without one are reported as not counted, vendor data is
ignored. A type is GDTF file plus mode; its readable name comes from the
GDTF file in the archive if possible, else from the file name.
Suggestions: a remembered choice first (`FixtureTypeMapping`: same mode,
else the latest choice for another mode); otherwise a score of shared
words, letter similarity and how many of the type's words the product
contains – manufacturer words only add or subtract a bonus, conflicting
numbers (S30 against S60) cost 30 points. From 60 % a product is
preselected, from 35 % offered, at most four per type; services,
surcharges and subrentals never. All lines go in through the normal
services in one transaction, all or nothing, so availability, prices and
shortages work as usual; the plot read is kept in the session, the MVR
file is not stored. **An archive is not trusted:** at most 200 MB upload,
5,000 files, 2 GB declared unpacked, 20 MB scene description, 50 MB per
GDTF file and 200 MB for all, 10 MB per GDTF description; reads are
capped; XML with `<!DOCTYPE` or `<!ENTITY` is refused before parsing, XML
that is not UTF-8 too, and the parser stops at any document type
declaration. `defusedxml` is not a dependency of Rentalars; these checks
stand in for it.

Smaller ones: the phase "Reinigung" at the end (PRJ-071); the tab
"Dokumente" right after the price overview (PRJ-074).

### Planning views (VFG-020 to VFG-023)

**The month draws bars** (VFG-020, `schedule/calendars.py`). The server
splits each project into one piece per week row and stacks the pieces in
lanes – the lowest free lane, longer bars first. At most five lanes show;
the rest is counted per day as "+n", which links to the week. A bar that
continues gets an arrow at its edge. The status colour is one CSS property
`--status`, drawn as a wide edge and a light tint; the status is also in
hidden text, so colour is never the only sign.

**The week is a grid of hours** (VFG-021). Whatever lasts 24 hours or more,
or exactly whole days, goes into the all-day strip; everything shorter is
a block placed by its hours and split at midnight; phases are blocks of
their own, framed in dashes. A day with overlapping blocks gets a wider
column instead of thin blocks; the all-day strip uses CSS `subgrid` to stay
aligned. Day heads, strip and hours stay put while the grid scrolls. The
page opens at 06:00, or at the earliest start that day (not counting what
continues from the night), and scrolls sideways to today only when today
is cut off. The server places the line of the current time; the script
only moves it on by the time passed, so it does not depend on the time
zone of the browser.

**Hours in the timeline and the personnel plan** (VFG-022). The parameter
`days=1|2|3` gives columns of one or two hours. Hour columns follow the wall clock:
every day has 24, also when the clocks change. The page renders one span
before and one after the chosen one; scrolling to an end loads the next
span in the background, keeps the view where it was, updates the address
and tells screen readers the new range. Without script, "früher" and
"später" do the same with a page load.

**Warnings of the personnel plan look at real times** (VFG-023). Double
booking, absence, "not available": three warnings, checked against the
times, not the day columns – a morning and an evening job on the same day
are not a false alarm. "With limits" is shown, but no warning. The
badge is filled red with dark text and a ring and has a text alternative;
the bars concerned get a red frame. The API gives `days` (1–84) on
`/calendar`, `/utilization` and `/personnel-plan`; the plan also returns
the availability entries and a `warnings` list, and `conflict` follows
from those, so two overlapping absences do not count. Month and week
take two queries each, the rows of the personnel plan four, whatever the
amount of data.

### E-mail (EML-034 to EML-039)

**One signature for everybody, written once** (EML-034,
`mail/signature.py`). `MailSettings.signature_html`, editable with write
access to the settings. The placeholders are fixed German words –
`{vorname}`, `{nachname}`, `{position}`, `{email}`, `{telefon}`, `{firma}` –
filled with the data of the person who writes. The HTML is cleaned with
`nh3` when stored and again after the placeholders are filled, with the
values escaped. The text part is derived from the HTML; a signature without
tags keeps its line breaks. Mails with a signature go out as text and
HTML, without one as text only; it can be left off per mail (`signature:
false` in the API).

**Sending uses the login of the fetch unless told otherwise** (EML-035).
`MailSettings.smtp_same_login`, on by default; while it is on, a stored
SMTP user and password are deleted. The migration switches it off where an
SMTP user or password was stored, so nothing changes for those. Off with
an empty SMTP user means "send without logging in". The mailbox settings
moved to `/administration/mail/` (the old address redirects) and show each
user only the part he may change: the mailbox with write access to E-mail,
the signature with write access to the settings.

**Compact mails and a conversation** (EML-036). The headers fold into one
`<details>` line. The height of the frame with the HTML is estimated from
the length of the text, because a sandboxed frame cannot be measured. The
conversation view ("Mailverlauf", because the project already has a tab
"Verlauf") trims quotes and signatures; list or conversation is kept for
the session.

**Addresses, CC and BCC** (EML-037, `mail/addresses.py`). Names are no
longer stored RFC 2047-encoded in To and CC (umlauts were stored as
`=?utf-8?…`), and names with a comma are quoted. BCC is a `Bcc` header that
`smtplib` strips before sending; a test with a recording SMTP server shows
it is not transmitted. Suggestions start at three characters and are
filtered by the rights to read customers and personnel; the endpoint
itself needs the right to write mails.

**The sender is the person and the company** (EML-038): "Vorname Nachname
| Firma", with the address of the mailbox. The `sender_name` of the mailbox
is only a fallback for mails without a known writer; it left the form and
stays in the API.

**The mail log keeps the envelope, never the text** (EML-039,
`mail/log.py`). `MailLogEntry`: time, direction, addresses, subject,
project, result. Project mails are recorded where they are fetched and
sent; system mails by `mail.backends.LoggingEmailBackend`, which wraps
`EMAIL_INNER_BACKEND`. Writing an entry never stops a mail; an incoming
mail is recorded once per mail and result. Kept as long as the mails, or a
year if mails are kept for good (catalogue 12.2, 17 i); anonymising a
customer deletes the entries of the customer's addresses. Found on the way:
the self-check asked `EMAIL_BACKEND` whether an SMTP server is set, which
is now always the wrapper, and reported "no mail server"; it asks
`EMAIL_INNER_BACKEND` now.

### Customers and import (IMP-013)

**A customer import merges** (`customers/importer.py`). Each row looks for
its customer by number, then VAT ID, then e-mail address (of the customer
or a contact), then name – compared without case, punctuation, legal form
and with umlauts spelt out (catalogue 12.2, 17 h). If a step finds several,
the later ones narrow them down; if several remain, the row becomes a new
customer with a warning that names them. Conservative on purpose: a
customer is matched by at most one row of a file; a private person is
never matched to a company with a legal form in its name, and only by the
customer's own e-mail address, not a contact's; a number that matches
while nothing else (name, VAT ID, e-mail) agrees gives a warning in the
dry run – Lexware also counts from 10001, so its numbers can hit unrelated
customers of Rentalars.

**Empty cells never erase anything, in every customer import.** A
field cannot be emptied through an
import (catalogue 12.2, 17 h). Names that differ only in
spelling keep the version of Rentalars. A move to another street or city
keeps the old address as a further billing address; addresses are compared
despite "Str."/"Straße" and a missing postal code. Customers have
`tax_number`, contacts `salutation`.

**The Lexware contact export is read as it is.** Address 1 is the main
address, address 2 a delivery address; "E-Mail 2" and "Telefon 2" go into
the note once; a salutation is kept on contacts only; "Lieferantennummer"
is skipped and the report says so. "Name" is not a required mapping –
first and last name are enough. The encoding of a CSV file is detected in
the order byte order mark, UTF-8, Windows-1252, ISO-8859-1
(`core.tabular.decode_text`). The column "Kontakt" of the own list export
(e-mail and phone) is told apart from Lexware's contact person, so the
round trip of the export stays unchanged.

### Settings, backup and logs

**The server is read from `/proc`** (ADM-008, `core/resources.py`): no
library, no command started, and a line is simply left out where `/proc`
lacks it. The memory of Rentalars is the PSS of the gunicorn master and its
workers, so shared pages count once. The load warning uses the
five-minute value (above twice the cores); one PDF drives the one-minute
value up for a moment.

**Encryption is switched on at the server, never by a button** (ADM-009,
catalogue 12.1). Switching it on changes MariaDB, restarts it and writes a
key only root may read, and the application runs without root rights on
purpose. Settings → "Sicherung und Verschlüsselung" shows the state –
database, new backups, the last nightly backup, the recovery key – and
explains `sudo rentalars encryption enable`.

**A backup from the browser is the nightly backup's file** (ADM-010,
`core/backup.py`). It reproduces the format of `backup.sh` in Python, so
that `rentalars restore` takes it: `mariadb-dump` with the same options
plus `--no-tablespaces`, with an option file of mode 600 that is removed at
once – never a password on the command line; on SQLite the backup API. It
runs as a task in the background (kind `backup`); the archive is written
outside `media`, read back completely, then moved into
`media/jobs/backups/`, delivered only to whoever made it and deleted with
the results of tasks. `deploy/backup.sh` leaves that folder out: backups in
backups would double the size of every night (catalogue 12.2, 17 j).

**An encrypted web backup gets a key of its own** (ADM-010, catalogue
12.1). The recovery key is root's, and the service runs with
`NoNewPrivileges`, so the application can never encrypt with it. Instead of
refusing, each backup gets a new key in the form of a recovery key and is
encrypted exactly like `backup.sh` does (`openssl enc -aes-256-cbc -pbkdf2
-iter 200000 -md sha256`, `.tar.gz.enc`). The key is shown only to the
person who made it, on the page and in the API answer, stored encrypted
with the task and deleted with it, and never put into the notification.
Restore with `rentalars restore FILE --key-file KEYFILE`, or type the key
when asked. This adds a second kind of key next to "one secret opens
everything" (Part 7). *Rejected:* refusing a backup in the browser while
backups are encrypted.

**The access log is one middleware** (AUT-028, `core/access_log.py`). It
looks at every successful `GET` after the view answered, at the name of
the address and its arguments – `<project:pk>` for projects, a table of
names for the rest; any CSV answer counts as a list export. htmx requests,
failed requests, lists without export and a person's own data are not
logged (catalogue 12.2, 17 g). The same user reading the same record the
same way within five minutes is one entry; the first read costs one query,
which names the record and looks for a recent entry at once, and one
insert; a repeat costs nothing thanks to a small cache in the process,
keyed by session or token. Mails, attachments, files and documents carry
their project as parent, so the filter by project finds them.
Anonymising a customer or person rewrites the labels and the reader's name
in the log. Kept 180 days by default (`retention_access_log_days`, at
least 30).

### Interface (UIX-016 to UIX-025)

**"Verwaltung" is "Einstellungen"** (UIX-023) – only the German labels; the
addresses stay `/administration/`, the module stays `ADMINISTRATION`.
Texts of the interface do not name requirement IDs. The logo comes as
PNG in 64, 128 and 256 pixels, `favicon-32.png` and `apple-touch-icon.png`;
`favicon.svg` embeds the 64-pixel PNG (UIX-016). The start page shows all
open shortages (UIX-021). The tabs
of "Planung" – calendar, timeline, utilization, personnel plan – are start
pages without "Back" (UIX-022, `START_PAGES` in `core/trail.py`).

**Readable addresses, keys inside** (UIX-024, catalogue 12.1,
`core/converters.py`). The path converters `<project:pk>` and `<product:pk>`
put the project number or article number into the address, whether `reverse`
gets the object, its key or the number; views keep receiving primary keys.
Old numeric addresses still resolve (a number wins over a key of the same
digits). Per request the numbers found are kept, and after three single
lookups all are read at once, so a list of fifty projects does not cost
fifty queries (NFA-012). A number with characters that are not safe in a
path falls back to the key. The API is unchanged.

**Pages follow changes** (UIX-020, `core/changes.py`). `GET
/changes/?keys=` answers a stamp per key: `project:<pk>` – the newest
change-log entry of the project or with the project as parent, which every
line, mail, file and document writes –, `mail:unknown`, and
`notifications`, whose answer also carries the unread count for the bell.
The page asks every 20 seconds and when it becomes visible again
(catalogue 12.2, 17 f). It reloads keeping the scroll position, unless the
user typed in the last 15 seconds, has a dialog or the menu open, or
selected text – then only a note offers it. The page's own changing htmx
requests are adopted as the new state, so one's own saving never reloads
the page. The question costs one or two indexed queries per open page,
whatever the amount of data.

**Questions in a dialog of the page** (UIX-018). `data-confirm` and
htmx's `hx-confirm` open a `<dialog>` of the page instead of the grey box
of the browser. A question about deleting gets a red button, labelled like
the button that asked or "Ja, löschen". `alert` gave way to a short message
that disappears by itself.

**Periods move together** (UIX-025). Every pair of fields `…start` and
`…end` of the same type in one form is a period: the end's `min` follows
the start, and moving the start moves the end, keeping the length counted
in wall-clock time – noon to noon stays noon to noon across a change of
daylight saving time. "Zeitraum im Kalender wählen" opens a calendar: first
and last day, then the times. An end not after the start on the same day
goes to the next day.

**Styles and scripts written in files of their own while building were
merged** into `static/css/app.css` and `static/js/app.js`; no page loads an
extra file. (See Part 16: a map loads the bundled Leaflet
from `static/vendor/leaflet/` the first time it is shown.)

Smaller ones: the search on every page, "/" on the keyboard (UIX-019); on
the phone the menu below the header bar and tabs without a scroll bar, on
wide screens the full width (UIX-017); the two periods of a project
explained in the form (PRJ-069); on the page of an item "change status"
next to "installed in / contains", installing on the page and the history
folded (MAT-047).

### Performance

**The project page needs about 45 queries on its first read** (NFA-012,
scenario 11: the limit went from under 44 to under 46). New are one lookup
for the number in the address, one for the availability marks of the crew,
and the lookup and insert of the access log on the first read of a record;
reading it again within five minutes costs nothing. The crew warnings and
the availability of people need one query more, for the availability
marks. The number does not grow with the lines.

**The start page keeps its shortages until the next change** (UIX-021).
Showing every open shortage instead of those of two weeks made the start
page about as expensive as the list of shortages: on the full amount of
data of scenario 11 it took about twice as long as before. The result
(the first six and the count) is kept in the cache under the newest entry
of the change log – every change of a line, a project or an item writes
one – and for five minutes at most, for what changes without an entry
(time passing, imports in bulk). Only users who may read every project see
the box, so they share one result. *Rejected:* keeping the two weeks (the
wish was "all open shortages"); counting without judging every project.
*Price:* after a change without log entry the box can be up to five
minutes old; the list of shortages itself is always computed fresh.

**Browser tests answer the pages' question about changes themselves.**
Every page asks `/changes/` when it loads (UIX-020). The test server
shares one SQLite connection between its threads, and a question running
alongside the test's own request once made a row come back with an empty
field. The browser tests therefore answer `/changes/` without the server,
except those about following changes (`watch_changes`). A real server has
one database connection per process and does not share it.

---

## Part 10: Stage 6: subprojects, nested groups, webhooks, accounting

Stage 6 of the catalogue (chapter 10,
chapter 12.1 "Stufe 6 ", chapter 12.2 number 18). A big
production is planned as a whole project with subprojects, material goes
from one stage straight to the next, groups nest, other systems hear what
happens, and invoices reach the bookkeeping. What the customer still has
to confirm is collected at the end, under "Assumptions to confirm".

### Scope: what was decided first

Four answers came before the first line of this stage (catalogue 12.1).

**Only the SOLL requirements of stage 6** (chapter 10).
Twelve requirements: subprojects (PRJ-031, PRJ-044 to PRJ-049), material
that moves on from one part to the next (PRJ-060), nested groups
(PRJ-037), webhooks (API-012) and the two new requirements of the
accounting (DOK-011, DOK-012). The 26 KANN requirements that stood in
stage 6 belong to stage 7, "Weitere Erweiterungen",
and come one by one, as needed – among them scanning while packing
(MAT-027, PCK-010, PCK-011, UIX-006), day rates and qualifications as a
prerequisite (PER-009, PER-015), further mailboxes (EML-003), customer
prices (PRD-018), calendar feeds of projects (API-013) and dividing an
existing project into parts afterwards (PRJ-050). *Rejected:* all 38
requirements of the stage in one release. (See Part 16:
surcharges, PER-009, and dividing afterwards, PRJ-050, are built; the rest
is stage 9.)

**Accounting: both Lexware Office and DATEV.** The catalogue
had promised a hand-over of the invoice data to a bookkeeping system
(DOK-006) without naming one. Now invoices and cancellations go to
Lexware Office as vouchers (DOK-011), and the invoices of a period go to
the tax adviser as a DATEV Buchungsstapel (DOK-012) – two new SOLL
requirements of stage 6. *Rejected:* only one of the two.

**No external login in this stage.** Login through an
identity provider with OIDC or SAML (AUT-007) is KANN and moved to
stage 7, where it comes together with LDAP (AUT-029).

**The project mailbox stays with an own or other provider.** It is fetched and sent through IMAP and SMTP with user
and password, as (EML-002); signing in with OAuth 2 at
Microsoft 365 or Google (EML-004) is not needed and moved to stage 7 with
the other mail wishes.

### Subprojects (PRJ-031, PRJ-044 to PRJ-046, PRJ-049)

**A subproject is a project with a parent, one level deep** (PRJ-031,
PRJ-044). `Project.parent` was in the data model from stage 1 (catalogue
chapter 10) and unused; now it is set. A part is a project in every other
respect – number, name, venue, manager, status, rental period and rental
days, groups, material and crew lines –, so planning, availability,
packing, documents and the API treat it like any project, and the rules
of the whole are in one place (`projects/family.py`). `Project.clean`
keeps the tree flat: a part cannot have parts, and a project that has
parts cannot become a part. `Project.parent` is `PROTECT`, and
`delete_project` refuses a project with parts. Making an existing project
into parts afterwards (PRJ-050) is KANN and stage 7; the API refuses a
change of `parent` after creation (400). (See Part 16:
"In Teilprojekte gliedern" divides a project afterwards; `PATCH` still
refuses a new `parent`.)

**A part is numbered after its whole project**: `2026-0042-1`,
`2026-0042-2`, the first free counter (`_next_subproject_number`). The
numbers stay unique under the existing constraint and work in addresses
(`<project:pk>`, UIX-024) and in the mail tag `[RL#2026-0042-1]`
(EML-009).

**Customer, internal flag and billing address always come from the whole
project** (PRJ-045, `INHERITED_FIELDS`). The form of a part does not show
them, `update_project` silently ignores changes of them on a part, and
the API takes them from the whole project. When the whole project gets
another customer or billing address, every part follows; a contact or
delivery address of the former customer is replaced by the whole
project's. **Contact, delivery address, venue, project manager and rental
period are presets** (`PRESET_FIELDS`): taken over when the part is made,
unless given, and changeable on the part.

**The whole project is the frame in time** (PRJ-044). A part lies within
the rental period of its whole project; `Project.clean` files the error
under `start`. Moving the whole period by the same amount at both ends
moves every part along – with those of its lines that had the part's
period, and with its event period. Any other change must leave every
part inside, else it is refused as a whole (`_update_subprojects`, one
transaction).

**Every part has a status of its own**, with three rules between whole
and parts (PRJ-044, `_check_family_status`): cancelling a whole project
cancels its parts that are not finished, and is refused while a part is
out; a whole project is closed only after all its parts are closed or
cancelled; a part of a cancelled whole project cannot be taken up on its
own. `change_family_status` moves the whole project and then each part
where the step is allowed; the others keep their status and are named.
In the browser the checkbox "Teilprojekte auch" next to the status
buttons is ticked by default; in the API it is `with_subprojects`.

**A new part starts in a status that fits its whole project**
(`_STATUS_OF_NEW_PART`): a part of an inquiry is an inquiry, of an option
an option; a part of a project that is confirmed, out or returned starts
as "confirmed – details open" – a new stage is rarely complete when it is
added. Cancelled and closed whole projects get no new parts.
**[assumption]** (catalogue 12.2, 18 a).

**Rights flow from the whole project; a part can replace them** (PRJ-049,
`projects/access.py`). A membership of the whole project holds in each
part. A membership of a part replaces it there, for more or for less –
down to the new level "no access" (`ProjectAccessLevel.NONE`), which is
offered only on parts; the API refuses it on a whole project. A
membership of a part alone opens neither the whole project nor the other
parts. A crew line counts in its own project only and always gives the
deployment view there, even against "no access". Roles for all projects
are not touched. `assigned_filter` and `readable_projects` express this
with subqueries, so lists still ask nothing per row; `access_of_many`
needs one query more, for the parents. Whoever sees a part also sees
number and name of its whole project ("Teil von …"), an external stage
manager included **[assumption]** (catalogue 12.2, 18 b).

**The tab "Teilprojekte" shows the family side by side** (PRJ-046,
PRJ-047, `family.build_family`). It appears on whole projects with parts
and on parts, right after "Planung": one row for the whole project's own
lines – the shared ones, central power supply or production office – and
one per part, with lines, pieces (stock products and kits), crew lines,
open places, planned hours, net (with the price right) and shortage, and
the sum of all; below them the shortages between the parts (next
section). Parts the viewer may not read are left out of rows and sum, and
counted. One availability engine serves all parts; each part costs one
build of its planning. Above the planning, a strip leads to the whole
project and to every part.

### Material taken over and its availability (PRJ-060, PRJ-047)

**A take-over is a line that names its source** (PRJ-060,
`MaterialLine.taken_over_from`, `_clean_takeover`). The source is a line
of another project of the same family – another part or the whole project
itself – with the same product, not a sale, that starts earlier. All
lines taking over from one line together take at most its quantity, and
the source cannot be reduced below what others take from it. Deleting the
source turns the taking line into a normal one (`SET_NULL`). In the
planning, "Aus anderem Teilprojekt übernehmen" opens a dialog with the
lines of the other parts that start earlier and still have pieces left
(`family.takeover_sources`, `services.take_over_line`); the line dialog
has the field "Übernahme aus" – only in families, only lines of the same
product that start earlier.

**Taken-over pieces are one continuous reservation** (PRJ-060,
`availability/engine.py`). They are occupied from `min(source end, own
start)`, without the buffer before: the gap between the stages counts as
occupied, because the pieces stay with the production. The pieces a later
line takes over end without the buffer after. A line can therefore fall
into up to four segments – taken over and handed on, only taken over,
only handed on, neither –, each judged with its own span, and their
verdicts are merged into one detail per product (`_merge_detail`). Where
the periods overlap, the pieces count twice and show as a shortage: the
same pieces cannot stand on two stages at once. Linking happens only
among the lines that are loaded and reserve, plus the judged project's
own (`_link_takeovers`): a source whose taker does not reserve – its
project is an inquiry – keeps its buffer after. The query of the other
lines also loads lines whose source ends inside the window, and
`projects_that_may_be_short` counts take-overs on the safe side.

**Shortages between parts are shown, not prevented** (PRJ-047). Parts
reserve like separate projects with their own periods.
`ProductShortage.family` is what the other parts of the same whole
project hold firmly at the busiest moment of a line (`Demand.root_project_id`
tells them apart). The tab "Teilprojekte" lists the lines that are short
while `family` is above zero, and the page "Fehlbestände" says "davon
belegt durch andere Teilprojekte: N" (`OpenShortage.held_by_other_parts`,
the smaller of `family` and the missing count) with a link to the tab.

**A take-over is charged once, on the line it comes from** (PRJ-060,
catalogue 12.2 number 3). The taking line has the amount 0
(`LinePrice.is_takeover`), like a subrental that covers a shortage; the
source line is charged as usual. The planning shows both ends: at the
taking line "übernommen", "kommt von …" and "nicht berechnet / berechnet
in …", at the source "N gehen weiter an …" (`PlannedLine.handed_to`).

### Packing (PRJ-048, PRJ-060)

**Every part is packed on its own; the whole project gets a combined
view** (PRJ-048, `packing/subprojects.py`). The packlist of the whole
project, `/projects/<whole>/packlist/family/`, is read-only: packing,
issue, handover and return stay with the packlist of each part; the same
address of a part leads to its whole project's. Two views – "Nach
Teilprojekt", with the progress of each part (packed, issued, back), and
"Nach Artikel zusammengefasst" for the warehouse –, the choice kept for
the session; the PDF has both, the API returns both at once. It needs the
packlist right on the whole project; each part is filtered with the same
rule, and the page says how many parts it leaves out. Every packlist of
the family links to it for whoever may see the whole project's packlist.
In the article view "Aus dem Lager" counts warehouse rows only and
"Übernahme" is shown apart; "Ausgegeben" and "Zurück im Lager" count
warehouse movements only, so taken-over pieces are never counted twice.

**A take-over row is not packed from the warehouse.** Line T of part B
takes over from line S of part A. On B's packlist T cannot be packed,
have items chosen or be issued; `issue` skips it, so no free item is
allocated for it. It counts towards neither the packing progress nor the
weight, and it does not keep B "partly issued": B is "issued" once its
warehouse rows are out. A packlist with take-over rows only cannot be
issued; the handover issues it. A's row S lists every later line taking
it over, with planned and handed-over pieces (kits per component); for
projects outside a family this costs no query.

**The handover is booked where the pieces arrive** (PRJ-060,
`hand_over`): on B's packlist, "Übergabe buchen", in parts if need be;
the default quantity is everything expected that is still out with A.
A's packlist must be out, and booking needs packing write access in both
parts **[assumption]** (catalogue 12.2, 18 d). One `Handover` per
booking. On A's row the pieces count as back
(`PackEntry.handed_over_quantity`), kept apart from "returned to the
warehouse"; on B's row they count as issued. B's packlist becomes
"partly issued" or "issued", B's project "out".

**Item allocations move only when it is beyond doubt** which items went
(PCK-020, PCK-021): when the booking takes every piece still with A, A
returned none of them, and all of S's handovers went to this one row.
Then A's allocation is closed – the item stays "in use" – and a new one
is opened at B, contents included, pointing to the handover
(`Allocation.handover`), so the history of the item shows both parts
(MAT-025). Otherwise nothing moves, as everywhere in packing.

**A handover can be taken back** (`undo_handover`): the latest booking of
a row first, and not once A or B is returned, or once pieces of it are
back in the warehouse or have gone on further. It reopens A's
allocations; if nothing of B is out any more, B's packlist goes back to
its packing status and B's project is no longer "out".

**Pieces still waiting for their handover are missing for A**
**[assumption]** (catalogue 12.2, 18 d). Handed-over pieces count as back
for A, so `complete_return` and `guard_project_status` pass. Pieces still
waiting count as missing until they are handed over, ticked as back after
all, or clarified (PCK-019); "Alles ist zurück" leaves them out, and the
refusal names the part they wait for. After A is returned, nothing more
can be handed over from A. *Rejected:* counting them as back
automatically. Returning B works as usual. Taking back an issue is
refused on A while pieces have gone on; on B it keeps what arrived by
handover, and B stays "partly issued". Deleting T or clearing its source
makes the normal rules apply again; bookings made before stay.
**Subrented pieces do not move on** (catalogue 12.2, 18 d): if S is
partly covered by a subrental, only the pieces from A's own stock that
are out can be handed over.

**One webhook event, `packing.handed_over`**, on booking (`undone:
false`) and on taking back (`undone: true`); `counts.outstanding` of a
packlist subtracts the pieces handed over to another part (API-012,
below). The history of both projects names the handover
(`packlist.handed_over`, `packlist.handed_on`, `packlist.handover_undone`).

### Prices and documents (PRJ-045, PRJ-046, PRJ-060)

**Billing happens at the whole project** (PRJ-045, PRJ-046,
`projects/family_prices.py`, `documents/content.py`). Offer, order
confirmation and invoice of a whole project hold its own positions first,
without a heading, then every part that is not cancelled as a block: a
section that opens it ("Teilprojekt 2026-0042-1 Bühne Marktplatz,
10.03.–12.03.2027", below it "Veranstaltungsort: …" if a venue is set),
the part's groups, and a section that closes it with the part's net
total (`Section.subproject_block`, `part="opens"` and `"closes"`). Every
section of a block carries the part's number in `subproject`. Like group
subtotals, block subtotals are never added up; the positions are numbered
straight through the document. A part with nothing to charge is left out
**[assumption]** (catalogue 12.2, 18 c).

**Each project keeps its own calculation; the sum adds net per tax rate**
(`family_prices.sum_prices`). Groups, discounts, flat prices and
percentage surcharges work inside the project they belong to, exactly as
on its planning page – so a percentage surcharge "on the whole project"
set on the whole project counts the whole project's own lines only
**[assumption]** (catalogue 12.2, 18 c). The net amounts of all included
projects are added per tax rate, and the tax is calculated once per rate
on that sum (EN 16931 BR-CO-17); gross is net plus tax. For a project
without parts this gives exactly the old figures. Adding up the gross
totals of the parts one by one can differ by a cent; the sum row of the
tab "Teilprojekte" does that (`Family.total`), the price overview and the
documents do not. **The service period** runs from the first start to
the last end of all included projects.

**A part makes delivery notes and crew dispositions, nothing priced.**
`check_can_make` and `preview` refuse offer, order confirmation and
invoice on a part: "Angebot, Auftragsbestätigung und Rechnung entstehen
am Gesamtprojekt … – mit allen Teilprojekten." The part's tab "Dokumente"
says so and links to the whole project's, for whoever may read it.
Delivery notes and crew dispositions are made per part, with the part's
delivery address and crew; the delivery note of the whole project holds
its own material only. There is no combined delivery note for all parts
**[assumption]** (catalogue 12.2, 18 c).

**Taken-over lines are left out of offer, order confirmation and
invoice** (PRJ-060). They stay on the taking part's delivery note, marked
"Übernahme aus 2026-0042-1 Bühne Marktplatz" (`SimpleRow.taken_over_from`),
and the price overview shows them as "übernommen" and "nicht berechnet /
berechnet in …".

**One valid invoice, for the whole family.** A valid invoice of the whole
project blocks a second one, as before (DOK-006). New: a valid invoice
that a part still has from before it became a part also blocks the whole
project's invoice – otherwise that part would be charged twice.

**Priced documents need sight of every part** (PRJ-049,
`check_parts_readable`). Whoever may not read every part that is not
cancelled cannot make or preview the whole project's offer, order
confirmation or invoice; the message names those parts **[assumption]**
(catalogue 12.2, 18 c). A document once made shows every part to whoever
may open the documents of the whole project and see prices.

**The price overview leaves out what the viewer may not read** – page,
PDF, CSV and API – and says how many parts are missing; it also names the
cancelled parts it leaves out. The price overview of a part shows only
the part, with "Teil von …; Summe aller Teile im Gesamtprojekt" and a
link to the whole project's. The API `price-overview` keeps the project's
own figures at the top level, so existing clients keep working, and adds
`parts`, `family_totals` (net, tax per rate, gross), `hidden_parts`,
`cancelled_parts` and `part_of`; each line has `taken_over_from`. The
price overview a mail attaches is made without the sender's rights
(`mail/sending.py`) and so holds every part that is not cancelled, like a
priced document.

**XRechnung, Lexware Office and DATEV needed no change**: they read the
stored content and its amounts per tax rate. Tests check the XML totals
with part blocks, discounts in several parts and the cancellation – the
KoSIT validator 1.5.0 with the XRechnung 3.0 rules accepts both –, the
Lexware voucher and the DATEV rows of such an invoice.

Fixed on the way: the tax row of the price overview's CSV said "Tax 19
%", because the text sat in an f-string the translation tool cannot read;
it says "Steuer 19 %" now.

### Subprojects elsewhere (PRJ-029, PRJ-047, PRJ-048, PRJ-076)

**A part is named one way everywhere** (`projects/family_labels.py`, the
filters `part_of` and `project_label` of `{% load subprojects %}`), in
three forms: "Teil von 2026-0042 Stadtfest" as a second line or tooltip;
"2026-0042-1 Bühne Marktplatz (Stadtfest)" in selection lists and the
deployment calendar; "Bühne Marktplatz (Stadtfest)" on calendar bars.
Callers load `select_related("parent")`, so no page asks once per row
(month and week still two queries, the personnel plan four). In the
project timeline the parts follow their whole project, indented; month
and week keep their lanes in the order of time and change only their
labels. *Rejected:* grouping the lanes of the calendar by whole project –
it breaks the layout of the bars. The search finds parts by the name of
their whole project, the customer page lists parts right after their
whole project, and the API gives calendar entries a `parent`. The
breadcrumb links to the whole project's overview only for users who may
read the planning; crew with the deployment view alone got a 404 there
before.

**Duplicating a whole project takes its parts along** (PRJ-029,
`projects/duplicate.py`, `with_subprojects`, on by default). Each part
moves by the whole project's wall-clock shift (`shifted_period`); if the
new period is shorter, a part is cut to it, like lines, rather than
refused. Presets come from the copy of the whole project, but a part
keeps what it set itself – its own manager, delivery address, contact,
venue. A part cancelled on its own is not copied; of a cancelled whole
project all parts are. Take-over links are mapped to the copies
(`copy_group(line_copies=…)`); a link that fails `MaterialLine.clean`
becomes a normal line, and the page says how many **[assumption]**
(catalogue 12.2, 18 a).

**Duplicating a part makes a new part of the same whole project** by
default (`as_subproject`); its period must lie within the whole's, and it
starts in the status a new part gets there – "Bestätigt – Einzelheiten offen"
for a confirmed whole project, not "Anfrage" as other copies
**[assumption]** (catalogue 12.2, 18 a). It needs the right to edit the
whole project: the browser hides the option without it and says so, the
API answers 400 on `as_subproject`. Links to sources outside the copy are
kept where still valid. Copied as a project of its own, every take-over
becomes a normal, charged line.

**A template holds one project** (PRJ-076). The save dialog of a whole
project with parts says that parts are saved one by one. Take-over links
were never part of a template, so a template line is a normal line;
applying a template to a part works as on any project.

**The timeline of a product draws taken-over pieces as a bar of their
own**, from the end of the source line, "6× übernommen", titled
"übernommen von 2026-0042-1" – one query, and only when a part is among
the demands.

**The correspondence of a whole project includes its parts'** (EML-019,
EML-029, PRJ-049): its tab "Korrespondenz" also lists the mails of the
parts the user may read, each with a badge of the part's number, opening
in the part. Mails tagged with a part's number land in the part
(EML-008). **Time tracking and deployments** belong to the part
(PRJ-048); the project choice of the quick entry and of the approval
says "2026-0042-1 Bühne Marktplatz (Stadtfest)", and the deployment view
and the calendar entry of a deployment name the whole project.

**Not yet.** The time-tracking report, "Meine Zeiten", the timesheet PDF
and the pages of a product and of an item show a part by number and name
only – the suffix "-1" marks it; naming the whole project in the report
would need further joins. `GET /shortages` carries neither
`held_by_other_parts` nor `parent`, and the mail list of the API shows a
project's own mails only.

### Nested groups (PRJ-037)

**Groups nest up to three levels** (`projects/grouptree.py`,
`MAX_DEPTH`): Licht › Front-Traverse › Traverse 1. `Group.parent` was in
the data model from stage 1, so no migration was needed. `Group.clean`
refuses a cycle and a place that would make the tree deeper, with the
error under `parent`. `GroupTree` builds the tree from the groups already
loaded – order, depth, paths, ancestors, allowed parents – without a
query, and puts each parent into Django's cache, so walking up from a
group asks nothing either (NFA-014).

**The order is a table of contents.** `position` counts among siblings;
the project's order is a group, its subgroups, then the next group, and
it holds everywhere, also for the order in which availability is judged
(PRJ-042). A parent group may have lines of its own; they come first,
then its subgroups.

**Sums go from the bottom up** (`projects/pricing.py`, PRJ-039). A
parent's sum is its own lines plus the subtotals of its subgroups; the
subgroup's rule applies first, then the parent's on the result, and a
parent's flat price replaces everything below it. Surcharges inside a
subgroup are part of its subtotal, so a parent's discount applies to
them; a group's own discount still does not touch the surcharges in that
same group. The base of a percentage surcharge (PRD-039) is a target's
amount after its own rules, not after the rules of the groups above it –
the amount the planning shows next to the target.

**A reduction is spread down to every line below**, in proportion to
what the line contributes at that point. That keeps the maximum discount
of a job function (PER-026) valid across all levels and the net per tax
rate exact for the invoice.

**Optional and alternative are inherited** (PRJ-040,
`Group.effective_kind`). A subgroup of an optional or alternative group
counts as such too: outside the total, reserving softly – also checked
two levels up –, not packed, not invoiced. A subgroup that is optional
itself stays outside its parent's sum, like an optional line. "Optionale
Teilgruppen, nicht enthalten" adds up every group whose own kind is
optional or alternative, without counting twice. **Rental days are
inherited** as well: a subgroup without its own takes them from the
nearest group above (`effective_rental_days`, PRJ-062).

**Deleting moves the contents up one level.** By default the lines go to
the parent group – or to "without group" for a top-level group – and the
subgroups take the deleted group's place; with `?lines=delete` the whole
subtree goes, lines included. The question before deleting says which of
the two happens. **Copying** copies the whole subtree, surcharge targets
included: in the same project to the end of the same parent, in another
project to the top level; duplicating a project copies the top-level
groups with their subtrees. **Templates** have content version 2 with a
`"parent"` key, parents first; templates of version 1 load with every
group at the top level, without conversion.

**Moving: dragging, arrow keys or a field.** A group is dragged by its
handle into another group, out of it or to another place (SortableJS, as
the lines); with the keyboard, ↑ and ↓ change the order, → moves it into
the group above, ← one level up. The group dialog has "Übergeordnete
Teilgruppe", and a new group can be added "in" another. All of it ends in
`services.move_group`. The API: `parent` is writable and moves the group
to the end of the new parent's subgroups, `POST …/groups/{id}/move` takes
`{parent, position}`, the group list comes in tree order, totals and the
price overview carry `parent`, `depth` and `path`; `reorder` still
changes the order only, never the parent.

**A planning patch re-sends the groups above a change** (NFA-013). After
a line changes, the patch also carries the subtotal of every group above
the changed group. If that group or one above it has a discount or flat
price and a line with a maximum discount (PER-026) sits underneath, the
whole family of groups is sent.

### Webhooks (API-012)

**Deliveries are written in the transaction of the change**
(`api/webhooks.py`). `record` writes one `WebhookDelivery` per active
webhook that wants the event, in a savepoint; the timer only ever sees
committed rows. A change that is rolled back leaves nothing to send, and
nothing is lost if the process ends right after the commit. An error
while recording is logged and never stops the business change.
*Rejected:* `transaction.on_commit` – the event would be lost if the
process ended between the commit and the callback.

**Project and document events come from signals; packing and time from
the services.** `project.created` and `project.status_changed` come from
`post_save` on `Project`, connected by the model's name; the old status
is read from the change log's snapshot (`_audit_before`, as
`personnel/calendars.py` does), so the automatic "out" and "returned" of
packing are caught too. `document.created` comes from `post_save` on
`Document`, so the document services stayed untouched. Packing and time
tracking call `record` themselves (`issue`, `undo_issue`,
`set_returned`, `return_all`, `complete_return`; `approve_entries`,
`take_back_approval`); `set_returned` and `take_back_approval` became
`@transaction.atomic` for it.

**The events**: the four the catalogue names – `project.status_changed`,
`packing.issued`, `packing.returned`, `time_entry.approved` – and
`project.created`, `packing.issue_undone`, `packing.handed_over`
(PRJ-060), `time_entry.approval_withdrawn` and `document.created` (every
kind; a cancellation carries `cancels`). `ping` is the test and cannot be
chosen. `packing.returned` fires on every booking that brings material
back – a row tick that raises the quantity, "Alles ist zurück" when
something changed, completing the return –; `complete` is true only for
the last. Corrections downwards send nothing. `api/webhook_events.py`
documents each event with an example, and a test checks that every
example has exactly the keys that are sent.

**A payload never holds prices.** The envelope is `{version: 1, id,
event, timestamp, data}`; `data` is a compact subset of the API
representation plus `api_url`. No prices, costs or rates – a test checks
it over all events; personal data only for time entries (person ID and
name); quantities and hours as text with two decimals (NFA-003);
`parent_project` from `Project.parent`.

**Delivery** is a `POST` with `X-Rentalars-Event`,
`X-Rentalars-Delivery` (the same ID on every attempt) and
`X-Rentalars-Signature: sha256=<hmac>`, the HMAC-SHA256 of the raw body
with the webhook's secret, as GitHub does it. 10 seconds per step, 20 in
total; at most 64 KB of the answer are read and its first 1,000
characters kept. Redirects are never followed: a 3xx is a failure. Only
`http` and `https`; credentials in the address are refused. Internal
addresses and host names without a dot are allowed on purpose – an ERP
or n8n in the company network is a usual receiver –, which makes webhooks
a deliberate way into the internal network, open only to whoever may
change the settings. The proxy of the environment is used, except for
addresses on the machine itself.

**Retries** after 1 minute, 5 minutes, 30 minutes, 2 hours and 12 hours:
six attempts within about 15 hours; only a 2xx answer is success.

**The minute timer delivers** (`run_jobs`, after the calendars; Part 8,
Part 9). A run stops after 30 seconds or 200 deliveries and never raises.
When a receiver fails, its other deliveries wait for the next run, so one
dead receiver cannot use up the run. A delivery is claimed before it is
sent – its next attempt moves ten minutes ahead –, so two runs never send
it twice.

**A webhook that keeps failing switches itself off.** After ten
deliveries in a row that failed after all their attempts, it is switched
off, the switch-off is in the change log (actor `system:jobs`), and
everybody with write access to the settings is notified with the kind
"error of the application" (`SYSTEM_ERROR`) **[assumption]** (catalogue
12.2, 18 e). Its waiting deliveries are paused, not dropped, and go out
once it is switched on again; switching it on resets the count. While it
is off, no events are recorded for it. *Rejected:* a notification kind of
its own – it would change the choices of `notifications` and need a
migration there.

**Sending by hand** – "Test senden" (a `ping`) and "Erneut senden" (a
failed delivery, with its delivery ID) – happens in the request, once,
with the answer shown at once; it does not count towards the switch-off
and works on a switched-off webhook too. Only failed deliveries can be
sent again.

**The secret** is 32 random bytes, stored with `encrypt_secret` like the
mail passwords, never in the change log (only `secret_created_at` shows a
renewal), shown once after creation and later through "Geheimnis
anzeigen" to whoever may change webhooks (API: `GET
/webhooks/{id}/secret`). "Geheimnis neu erzeugen" replaces it at once. A
secret that can no longer be decrypted – `secret_key` changed – makes a
delivery fail with a hint to create a new one, and the API answers 409.

**Rights and keeping.** Reading the settings shows the webhooks and their
deliveries, answers included; writing changes, tests, sends again and
shows the secret; deleting deletes. Deliveries are kept 30 days, fixed
(catalogue 12.2, 18 e), and deleted by the daily maintenance.
*Rejected:* a setting for it – it would need a migration in `core`.
Webhooks and deliveries are not in the full export: an address may itself
be a secret link. The delivery log holds the names of people (from time
entries) for those 30 days; anonymising a person does not remove them
there.

### Accounting (DOK-011, DOK-012)

**An invoice becomes a voucher in Lexware Office, not an invoice of
Lexware Office** (DOK-011, `documents/lexware.py`): `POST /v1/vouchers`,
type `salesinvoice`, a cancellation `salescreditnote` with positive
amounts. *Rejected:* creating an invoice in Lexware Office – it would get
a second number and a second PDF. `taxType` is `net`, one item per tax
rate, taken from the stored amounts per tax rate of the document – the
same as in the PDF and the XRechnung; a test compares them with the
XRechnung's tax subtotals. Then the PDF goes to the voucher (`POST
/v1/vouchers/{id}/files`, field `file`).

**Talking to Lexware Office.** `https://api.lexware.io` with
`Authorization: Bearer <key>`, the standard library only, 20 seconds
timeout. Redirects are not followed, so the key cannot go anywhere else.
At most two requests per second: 0.5 seconds between requests, and after
a 429 again after 1, 2 and 4 seconds – Lexware sends no `Retry-After`.

**The customer is found by its number, and only if the name agrees.**
`GET /v1/contacts?number=…&customer=true`: customers imported from a
Lexware contact export (IMP-013) carry Lexware's numbers. A contact found
by number is taken only if its name matches; otherwise the hand-over
stops with an error and offers "Als neuen Kontakt übergeben" – Lexware
numbers its contacts itself, and a number of Rentalars may belong to
another customer there. If none is found, a contact is created (`POST
/v1/contacts`); Lexware gives it a number of its own, which cannot be
set, so a new contact's number in Lexware may differ from the one in
Rentalars. The contact ID is kept on the customer
(`Customer.lexware_contact_id`). With "auf den Sammelkunden buchen" no
contact is looked for.

**Nothing twice.** One `LexwareTransfer` per document; only one attempt
runs at a time. Before a voucher is created, `GET /v1/voucherlist` is
asked for the number; an existing voucher is taken only if its amount
matches. The voucher ID is stored as soon as it is known, so a retry
after an error only uploads the PDF.

**Posting categories** per tax rate, by default "Einnahmen"
(`8f8664a1-…`, the same in every account). "Verbindung prüfen" loads
`/v1/profile` and the income categories (`/v1/posting-categories`) for
the choice.

**Handing over is a task in the background** (kind `lexware`, NFA-041).
By hand – on the tab "Dokumente", or again from the page Accounting – the
user is told when it is done; automatically, right after an invoice or
cancellation is made, it is silent on success and tells the maker on
failure. It never stops the invoice from being made.

**The API key** is stored with `encrypt_secret`; only its last four
characters are shown, the API field is write-only, and the key stays out
of the change log and of the full export (`SECRET_FIELDS`).

**The formats are built from published descriptions**, not tried against
Lexware Office or DATEV. The official pages could not be opened while
building; the formats come from sources that reproduce them, and a fake
server in the tests (`tests/lexware_fake.py`) refuses bodies that do not
match the published format. The first real hand-over and the first DATEV
import are to be checked with the customer **[assumption]** (catalogue
12.2, 18 f).

**DATEV: the invoices of a period as a Buchungsstapel** (DOK-012,
`documents/datev.py`). Header "EXTF", version 700; Buchungsstapel data
category 21, format version 13 with 125 columns; Debitoren/Kreditoren
category 16, version 5 with 254 columns; Windows-1252, CRLF, `;`, texts
in quotes, amounts without sign and with decimal comma, Belegdatum
`TTMM`. Festschreibung 0: the tax adviser checks before locking.

**One booking per invoice and tax rate**: the gross amount, debit on the
debitor, credit on the revenue account. No tax key, because 8400/8300 and
4400/4300 are automatic accounts. A cancellation is booked the reverse
way ("H"). *Rejected:* the Generalumkehr flag. Default revenue accounts:
SKR 03 8400 (19 %), 8300 (7 %), 8336 (0 %); SKR 04 4400, 4300, 4336 – all
editable, filled up with zeros for longer accounts; a tax rate without
account stops the export with a message. For a 0 % booking to a customer
with an EU VAT ID, column 40 ("EU-Land u. UStID") is filled.

**The debitor account is the customer number plus an offset** (default 0,
since customer numbers start at 10001), which must lie between 10000 and
69999 for four-digit accounts – or one collective account for all.
Customer numbers with letters are refused with a message. The period
must lie within one fiscal year, whose first month is a setting. The
Debitoren file uses the customer data as they are now in Rentalars, not
the snapshot on the invoice.

**Rights.** The page Settings → Accounting and the DATEV export need read
access to the settings and the price right (AUT-019); changing the
settings, checking the connection and handing over again from that page
need write access to the settings. Handing over one invoice needs the
price right and write access to the project or to the settings. The
supplied role "Nur-Lesen", described as for bookkeeping, has the price
right but no access to the settings, so it cannot open the page
**[assumption]** (catalogue 12.2, 18 f): give it read access to the
settings, or make a role "Buchhaltung". The CSV downloads land in the
access log by themselves (AUT-028).

### Performance

**The planning page of scenario 11 needs 44 queries on its first read**
(NFA-012, NFA-014; the limit stays under 46). Subprojects added three
questions to it – has this project parts, does a line hand pieces on,
which line does it take from –, and none of them costs a query of its
own: the parts flag comes with the project in `project_for` (an `Exists`
annotation, `with_parts_flag`), the lines query annotates per row whether
a line hands pieces on (`EXISTS`) and prefetches
`taken_over_from__project`, and `handed_on()` asks only for lines that
do. `build_planning` does not grow, and the group tree needs no query:
20 groups, five of them parents, cost what 20 groups at the top level
cost. During the building of this stage the page was at 47 to 48 queries
for a while; these annotations brought it back.

The same `Exists` keeps the packlist of 500 lines within its limit. The
tab "Teilprojekte" builds one planning per part with one shared
availability engine; `access_of_many` needs four queries instead of
three; parts are named with `select_related("parent")`.

The load-test data (`create_load_test_data`) has no whole project with
parts yet, so the measurement does not cover the pages of a family.
Measured times: see the operation guide.

### Assumptions to confirm (catalogue 12.2, number 18)

The catalogue asks the customer to confirm these readings; each is cheap
to change now.

a) A new part of a confirmed whole project starts as "confirmed – details
   open", one of an inquiry or an option with that status; a copied part
   likewise. A whole project duplicated into a shorter period cuts its
   parts to it; parts cancelled on their own are not copied (PRJ-044,
   PRJ-029).
b) Whoever sees a part sees number and name of its whole project ("Teil
   von …") – also an external stage manager who may work on that part
   only –, and the search finds parts by the whole project's name
   (PRJ-049).
c) Billing at the whole project: parts with nothing to charge are left
   out of offer and invoice; a percentage surcharge "on the whole
   project" set on the whole project counts only its own lines; there is
   no combined delivery note; whoever may not read a part cannot make
   the whole project's invoice (PRJ-045, PRJ-046).
d) Taken-over material: the handover is booked by whoever may work on
   both packlists; pieces still waiting for it are missing for the
   earlier part until they are handed over, returned or clarified;
   subrented pieces do not move on (PRJ-060).
e) A webhook is switched off after ten deliveries in a row that failed
   for good; the administration hears of it as an error of the
   application; deliveries are kept 30 days (API-012).
f) The role "Nur-Lesen" needs read access to the settings to open the
   page Accounting; the formats of Lexware Office and DATEV are still to
   be checked against the real systems (DOK-011, DOK-012).

Further questions from building, not yet in the catalogue:

- The earlier part's packlist names the part its pieces go to ("6 gehen
  weiter an … Bühne Schlosspark") also to a user who may not see that
  part, as the planning does. Or should it say "an ein anderes
  Teilprojekt"?
- Someone restricted on one part who may read the whole project can open
  an existing invoice of the whole project, which shows every part. Is
  that acceptable?
- The price overview attached to a mail holds every part that is not
  cancelled, whatever the sender may read – as a priced document does.
  Should it leave out the parts the sender may not read?

## Part 11: Requirements from practice

A bug fix and the requirements from the use of the application (catalogue:
PER-027, PER-028, UIX-026, UIX-027; chapter 12.1 "Weitere Wünsche"; chapter 12.2 number 19). Four questions were
answered before building; the decisions are noted where they mattered.

### The bug: customers from the dialog were deactivated

The dialog "… als neuen Kunden anlegen" of the project form (PRJ-070)
rendered the shared customer fields, which leave out the box "active" –
the customer management renders it separately. A box that is not sent
counts as unticked, so every customer made there was created deactivated
and could not be chosen. `customer_quick_create` now drops the field from
the form, and the model default (active) holds. The venue dialog renders
all of its fields and was not affected.

Migration `customers/0006_reactivate_quick_created` repairs the data: a
customer is reactivated when its change log says it was created
deactivated (`{"is_active": [None, False]}`) and no later entry touches
"active". A customer deactivated on purpose either was created active or
had the box changed later, so it stays. The repair writes its own log
entry ("Aktualisierung"). *Rejected:* reactivating every
deactivated customer without projects – customers deactivated on purpose
before their first project would come back.

### One availability at any moment (PER-027)

Availabilities of one person must not run in parallel, and at the same
time the busy times of the linked calendar are to stay a layer of their
own, so that the `.ics` can always be replaced as a whole. Both hold:

- **Two layers in storage, one in every view.** Own entries (`source =
  own`) never overlap each other – painting already cut what lay under a
  new colour. The busy times (`source = feed`) stay a layer of their own,
  replaced as a whole with every reading. `marks.resolve()` turns both
  into `AvailabilityPeriod`s that never overlap; every consumer – month
  calendar, "who is free" (`people_availability`), crew warnings, the
  personnel plan and its API, `/people/availability` – reads
  `effective_periods()` (one query for any number of people) instead of
  the rows.
- **The newer statement counts** – decided: the newer statement wins, the
  stricter one if they cannot be compared. Every row has `entered_at`:
  an own entry when it was entered (older rows: when they were
  created), a busy time when the appointment was last changed in the
  calendar – `LAST-MODIFIED`, else `CREATED`. `DTSTAMP` does not count:
  Google and others set it to the moment the file is generated, which
  would make every appointment the newest statement. A date in the future
  counts as now. Per elementary segment, the own entry wins if it is at
  least as new as every busy time there; if a time is missing, the
  stricter wins – the busy time, unless the own entry is red as well, which
  keeps its note.
- **Busy times are blocks.** Overlapping and touching busy times join;
  neighbouring own segments with the same colour, note and source join for
  display.
- **No joining in storage.** Painting the same colour next
  to an entry does not merge the two rows. Each entry keeps its own
  `entered_at`, so that a later change of a calendar appointment between
  them is judged against the right moment; a piece left over from cutting
  keeps the moment (and series) of the entry it comes from. The calendar
  shows neighbours as one period, so nothing changes for the person.
- **Periods are not cut at the edges of a query.** Only rows overlapping
  the window are read, so a period reaching out of it may be judged
  without a busy time lying outside; the part inside is always right.
  Periods entirely outside the window are dropped.

### Series (PER-028)

An entry repeats daily, weekly on chosen weekdays, every n
weeks or monthly, until a date or n times. `AvailabilitySeries` holds the
rule; its occurrences are **materialised** as ordinary own entries with a
`series` link, up to 366 days after the first day. That keeps every
consumer unchanged and makes an occurrence behave like any entry: it
replaces what was entered for its time, and what is entered later replaces
it. *Rejected:* computing occurrences on the fly (every consumer would need
the rule; painting over one occurrence would need exceptions) and series
without end (the requirement is at most one year ahead).

- **Monthly** means the same day of the month; months without that day are
  skipped, as calendar programs do.
- **Changing** works like "this and the following" in a calendar program:
  from a day (default today) the occurrences are removed and painted anew
  after the changed rule; what lies before stays. The count of a series
  counts from its first day, also after a change.
- **Removing** takes all occurrences, or those from a day on – the series
  then ends the day before. A series without any occurrence left before
  that day goes completely.
- **Changing one occurrence** (`change_mark`) takes it out of the series:
  it is a statement of its own now.
- Painting many periods at once (`marks._paint`) cuts once and creates the
  entries with `bulk_create`; a year of evenings is a few hundred rows and
  well under a second.

### "My area" and the tabs of "Personnel" (UIX-026)

The requirement: a navigation entry "Mein Bereich" holds the availability
and "Meine Zeiten" (so far in "Zeiterfassung"); the tabs "Freigeben" and
"Auswertung" of "Zeiterfassung" fit better into "Personal".

- **My area** has the tabs Availability (`/me/availability/`, new as a page;
  `POST` there still colours days), My times (`/times/`) and Personnel data
  (`/me/`). The navigation entry needs an account that is a person; the
  person now comes with the user in the same query
  (`EmailOrUsernameBackend.get_user` with `select_related("person")`), so
  asking for it on every page costs nothing.
- **Approve and Report** are tabs of Personnel. `navigation.Section` learned
  `special` (a special right) and `needs_write`, so that "Personnel" shows
  for someone who may approve times without reading the personnel module.
  The report of the own hours stays reachable for everybody else as a tab
  of My area – the same page, with the tabs of the area the user sees it
  in.
- The navigation entry "Zeiterfassung" is gone; "Zeit erfassen" stays.

### Uniform tabs (UIX-027)

The requirement: no "Back" on tab pages, as in the planning – tab pages are
start pages, "Zurück" only on pages below them; on the phone the "Back"
button at the top is useful everywhere. Explanations such as the one under
Planung → Fehlbestände must not shift the formatting; they belong inside
the tab.

- **Start pages:** every tab under a navigation entry is in
  `trail.START_PAGES` – newly the venues, the inspections, the open items
  and the tabs of My area. The notification settings are a page below the
  notifications (a button, not a tab) and keep their "Back".
- **Tabs of a record** count as one place on the trail, like a project's
: a person, a product, a material model and a material item.
- **On the phone** the top bar always has "Back" at the left (not on the
  home page): the trail's `back_url` where there is one, else the browser
  history if the user came from a page of this application, else the home
  page. The link above the page is hidden there; it would say the same
  again.
- **Same height:** `.page-head` has the height of a row of buttons, so the
  tabs sit at the same place with and without buttons. Explanations of a
  tab stand under the tab bar (`.tab-lead`), the lead of shortages
  included.
- **Venue:** "Hallenplan" is "Lageplan/Hallenplan" – only the German text;
  the document type "Hallenplan" of project files stays.

### Not built

- **A chat inside the project** (UIX-010) – is KANN and stays in
  stage 7; pulling it forward was considered. (See Part 16: built as the tab "Chat".)

### Assumptions to confirm

The catalogue lists them under 12.2, number 19:

a) The change date of an appointment is `LAST-MODIFIED`, else `CREATED`,
   never `DTSTAMP`; a future date counts as now; older own entries
   count as entered when created (PER-027).
b) Neighbouring own entries of the same colour stay separate rows and are
   shown as one (PER-027).
c) A series reaches at most 366 days beyond its first day; monthly skips
   months without the day; a change counts from a day on, today by
   default; a changed occurrence leaves the series (PER-028).
d) The report is a tab of Personnel for everybody who may approve times,
   and of My area for everybody else (UIX-026).
e) Customers created deactivated by the dialog are reactivated by
   the update if "active" was never changed since.

## Part 12: Requirements from practice

The requirements from the use of the application (catalogue: VFG-024,
VFG-025, PRJ-078 to PRJ-088, DOK-013, PCK-025, EML-041 to EML-043, PRD-041,
PER-029 to PER-031, ADM-011, NFA-069; changed PRJ-073; EML-003 and PER-009
now partly fulfilled; chapter 12.1 "Weitere Anforderungen";
chapter 12.2 number 20). Four questions were answered before building; the
decisions are noted where they mattered.

### Several mailboxes (EML-041 to EML-043)

- **A table of its own.** `Mailbox` holds access, folders and the state of
  the fetch; these fields left `MailSettings`, which keeps what holds for
  all: signature, sender name, interval, size limit, retention. The
  interval stays global ("Regeln für alle Postfächer"); the time of the
  last fetch is kept per mailbox, so each is due on its own. The passwords
  moved with them, so the full export's `SECRET_FIELDS` names
  `mail.mailbox` now; a test checks that no field that looks like a secret
  of any model reaches the export.
- **Roles are three flags**, `for_correspondence`, `is_outgoing`,
  `for_system`. At most one mailbox sends the correspondence and at most
  one the system mails; giving one of these roles to a mailbox takes it
  from the one that had it, with a note on the page, instead of refusing.
  "Exactly one active correspondence mailbox sends" is a validation error
  checked inside the transaction of `save_mailbox`. There are no
  conditional unique indexes: MariaDB ignores them. A check constraint
  allows "sends" only on a correspondence mailbox.
- **Per mailbox for incoming mails:** `process_untagged`, off by default, and
  `after_assignment` move (default),
  delete or keep. "Keep" leaves the mail completely untouched, not even
  marked as read; the fetch does not look at it again because its UID is
  passed.
- **The update** turns a filled-in settings row into the mailbox
  "Projekte" with correspondence and outgoing, active if "fetch and send"
  was on, `delete` if "delete instead of moving" was on, else `move`. All
  secrets and the fetch state (UIDVALIDITY, last UID) are kept, so the
  first fetch continues where it stopped; mails, waiting mails and project
  entries of the mail log are linked to it. A row never filled in gives no
  mailbox. Going back copies the outgoing mailbox into the settings row;
  further mailboxes are lost.
- **Delete or switch off:** a mailbox through which mails came in or went
  out is switched off (the foreign keys are `PROTECT`, so mails and log
  keep naming it); a never-used one is deleted. Deleting needs delete
  access to the module E-mail, by default only the Administrator's.
  Every mailbox can be deleted; mails and log keep
  its name (EML-046, Part 15).
- **The system mailbox** is used only when active and complete. Only mails
  from the default sender get a new From – the name of
  `DEFAULT_FROM_EMAIL` (else "Rentalars") with the mailbox's address; a
  caller that names a server of its own keeps it. Without a system
  mailbox, or when the database cannot be reached, `[email]` of the
  configuration sends as before – a report of a database problem still
  goes out. The mail log names the mailbox.
- **Inquiries** are `UnknownTagMail` rows with an empty tag, envelope
  only. "Übernehmen" fetches the mail from its own mailbox. A mail in two
  mailboxes is one entry (the Message-ID is the key) and is stored once.
  *Not built:* making a project from an inquiry, a preview of its text.
- **API:** `/mail/mailboxes` and `/mail/mailboxes/{id}/check`; listing and
  reading need write access, as `/mail/settings` did. `DELETE` answers 204
  when deleted, 200 with the switched-off mailbox. `/mail/settings` stays;
  its mailbox fields now mean the outgoing mailbox (else the first of the
  correspondence), and changing them with no mailbox at all creates
  "Projekte". New fields on `/mail/fetch`, `/mail/unknown`, `/mail/log`.
- **Where things are** (EML-042): "Anfragen" is a tab under "Projekte",
  shown by rights; someone with only the module E-mail reaches `/mail/`
  through "Projekte". The navigation entry "E-Mail" and the box "Abruf" are
  gone; "Jetzt abrufen" and the state are in the settings. Mailbox URLs
  use `mailbox_pk`, because below the mail module `pk` always names a
  project (`NoPageForgetsToAskTests`).
- **"Crew hinzufügen"** (EML-043) takes crew lines with a person whose
  request was not declined, who is active, not anonymised and has an
  address, in plan order, each address once. Privacy as in the deployment
  view (PER-019): with edit access to the project or read access to
  personnel all addresses, otherwise the released ones. A whole project
  adds the crew of the parts the writer may read; a part only its own.
- **"Kunde hinzufügen"**: the project's contact, else the whole project's
  contact (for a part), else the customer's address. The addresses are in
  the page as escaped JSON; the script adds only what is not yet in "An"
  (case-insensitive) and says in a `role="status"` line what it added. No
  button without addresses.
- **Self-check:** it names the system mailbox and gives one line per
  correspondence mailbox ("Postfach „Name“").

### Rates without obligation, day rates (PER-029)

Decided on the day rate: a day rate
as a field of person and job function, and the billing "je Tag" for crew
lines (below, "Crew per phase").

- **Which row applies on a day:** the latest row with a date not after
  that day; else the row without a date ("immer"); else the earliest row.
  The row counts as a whole: an empty rate in it
  means "no own rate", so the guide value counts, not the previous row's
  rate. Only one undated row per person and function, checked in `clean()`
  and `set_rate` – MariaDB has no conditional unique constraint.
- **`rate_on` is the person's own hourly rate only; `rate_for`** falls back
  to the guide values, also for open places, and says which rate is own
  and which a guide value. `RateBook` is meant for pricing many lines at
  once.
- **Existing callers made safe for "no rate":** a crew line keeps
  `hourly_rate` empty where the person has no own rate, so the deployment
  view never shows a guide value as "Mein Stundensatz hier"; its cost uses
  the guide value and is labelled "Richtwert". A planned person without an
  own rate costs the guide value, not 0 – also outside the own functions.
  Time entries take the own rate, then the crew line's, then the guide
  value.
- **Day rates are personnel costs:** the same right as hourly rates. The
  own profile lists the functions always, the own rates only where
  allowed, never guide values.
- **Assigning needs no cost right:** a function needs no rate, so whoever
  may edit personnel assigns functions – without the
  cost right the form has only the function, and `assign_job_function`
  never touches rates the person already has (assigning again is a no-op).
  Taking a function away deletes its rates, so without the cost right only
  a function without own rates can be removed (`has_own_rates`). The same
  in `POST/DELETE /people/{id}/job-functions`; the import behaves the same.
- **An empty "valid from" means "always"**, in the form and the API.
- **Import:** a function without a rate gets no guide value
  copied in as the person's own rate; a rate the row does not name is
  carried over; a changed rate of an existing function becomes a row from
  today (`Tontechnik: 35,00/280,00`, hourly/day).
- The rows are "Funktion und Sätze" (verbose name "job function and
  rates"): a row may hold a day rate only, or no rate.

### Several linked calendars, the week (PER-030, PER-031)

- **Each busy time belongs to its calendar**, and a successful reading
  replaces only that calendar's busy times. The layer is therefore always
  the union of each calendar's last good reading; a failing calendar keeps
  its busy times and its own error count, and its one-time notice names
  it. At most 10 per person, the same address once. Others see the name
  and the server, never the address; "Jetzt lesen" reads all of a person's
  calendars.
- **`availability_feed_url` is refused:** `PATCH calendars` with
  `availability_feed_url` answers 400 with a hint instead of being ignored
  silently.
- **The week** reuses the planning week's grid (opens at 06:00, today in
  view, the line for now), without the all-day strip. Day heads carry the
  month cell's colour and are the tap targets for choosing days.
  Availability shows as full-width bands with a label that stays visible
  while scrolling; deployments take the right 72 %, framed red where they
  meet a red period. In the week the panel takes the full page width. On
  the planning tab, projects the reader may not open show as "Funktion ·
  eingeplant" (AUT-016).
- **The person's timeline** has the rows Einsätze, Verfügbarkeit,
  Qualifikationen. `person_timeline` reads `effective_periods`, so own
  availability, busy times and "one availability at a time" (PER-027)
  count there as in the personnel plan, "who is free" and the warnings:
  someone "nicht verfügbar" does not look free in the person's timeline or
  in `/people/{id}/timeline`; the API row is `availability`
  instead of `absence`.

### Crew per phase, continuous hours, billing per day (PRJ-080, PRJ-073, PRJ-088)

Decided: a crew line can belong to a phase, its time follows the phase, the
Zeitplanung shows the crew of each phase; and the hours are counted
continuously – Monday 08:00 to Tuesday 20:00 counts 36 hours. The tab "Ablauf" is called "Zeitplanung".

- **Hours are the whole span** (`suggested_hours`): end minus start in
  quarter hours, in UTC, so a summer-time night is an hour shorter. This
  replaces the earlier rule (Part 9, catalogue 12.2 number 17 e) that read
  a period over 16 hours as working days of its clock times.
- **The migration recomputes** only lines whose hours equal what the old
  rule suggested for their period and differ from the new one – in
  practice lines over 16 hours, e.g. 24 → 36. Typed hours stay, closed and
  cancelled projects are skipped, issued documents keep their content. The
  old rule is copied into the migration. A line's hours still count as
  suggested while they equal the suggestion for its period.
- **Moving a phase** (box "Personal dieser Phase mitverschieben", ticked;
  API `move_crew`, default true): a line with exactly the phase's old
  period gets the new period; every other line moves by the change of the
  phase start (wall-clock, as in duplicating) and keeps its length, so a
  phase that only changes its end leaves those lines alone. Only inside
  the skipped summer-time hour could a line end before it starts; it then
  keeps its length in hours. Nothing is cut or refused: neither crew lines
  nor phases were ever bound to the project's period (PRJ-044 concerns
  subprojects). Suggested hours follow; typed hours, typed days and rates
  stay. Removing a phase keeps its lines without a phase.
- **A phase without JavaScript:** if "Von"/"Bis" are empty or untouched,
  the server takes the phase's period; in the API a new phase without
  start and end does the same.
- **Days** are the calendar days the period touches; a period ending
  exactly at midnight does not count the next day; typed days win. A
  service product billed as daily rental makes new crew lines "je Tag".
- **Day cost:** the line's fixed own day rate, else the function's day
  guide value, else hours × hourly rate. Changing person or function
  fetches both rates again; removing the person clears both.
- **Price overview:** a separate switch "Personal je Phase und Funktion"
  (`crew=phases`) next to the detail switch, carried into the PDF and CSV
  links. With the right to see personnel costs, the browser view shows
  cost and "Gewinn" per row; the default view, PDF and CSV never show
  costs – the PDF is mailed to customers –, and the API gives them only
  with `?crew=phases` and the right. *Open:* this is a change to acceptance
  scenario 15 ("no hourly rate in the price overview"); rates themselves
  still never appear.

### Issue per article (PCK-025)

Decided: issue per article – "Ausgeben" books only what is
ticked; partly issued, packing goes on; the project becomes "Unterwegs"
only when everything is out.

- **API:** `only_packed` stays; its default is now `true`, `false` issues
  everything; JSON booleans and form strings ("0", "false", "no", "off")
  are accepted. *Rejected:* a second parameter `all` – two parameters
  could contradict each other. Clients that sent `only_packed` behave as
  before; clients that sent nothing get a 400 with a hint when nothing is
  ticked.
- **In code** `services.issue()` keeps `only_packed=False` (about 50 test
  call sites and scripts); the view and the API always pass it. In the
  browser form a missing field means "ticked only", so an old page never
  issues everything by accident.
- **When the project is "out":** when material is out and no packlist with
  warehouse rows has something left to issue. A partly issued packlist
  always waits; an unissued one only if it has warehouse rows, so an empty
  packlist or one with takeover rows only (PRJ-060) holds nothing back.
  While something waits the project keeps its status; an "out" project
  stays "out" while a later addition waits or one of several issues is
  taken back.
- **Returns and undo:** "returned" when nothing is out, something came back
  and nothing waits – also from "confirmed" after a partial issue whose
  return was completed (the rest stays in the warehouse). Nothing out but
  something waiting: an "out" project goes back to "confirmed".
- **Status by hand while partly out:** "out" and either kind of
  "confirmed" are allowed; option, inquiry and cancelling are refused. A
  whole project cannot be cancelled while a part has material out –
  checked in the packing guard with the existing message, not in
  `projects/services.py`.
- **"Änderungen erledigt"** after an issue settles the status both ways:
  the rest no longer needed → "issued"; a new line → "partly issued", so
  it can be packed and issued.
- **Issued material is out whatever the status:** an option or inquiry
  that is partly out reserves firmly, an overdue partly-out project keeps
  its stock occupied (`material_out` inside the existing query). The start
  page lists such projects under "Gerade unterwegs" with a yellow
  "teilweise ausgegeben" and "Heute zurückerwartet", not under
  "Steht an", but still under "Heute und morgen zu packen".
- *Not built:* a note on the planning page or in the project head; the
  calendar and the project list still colour and filter by status.

### Planning: several lines, alternatives, subrentals, MVR (PRJ-082 to PRJ-084, PRJ-086, PRJ-087)

- **The alternative's reference** (PRJ-083): a line to a line, a group to a
  group, not across. Allowed targets: same project; not itself; not a
  covering subrental; not an alternative itself; for groups not a group
  above or below. Deleting the target, or copying into another project
  without it, makes the alternative **optional**, saved one by one so the
  history shows it. Copies (line, group, project, templates) name the copy
  of the target, or the same target within the same project. The dialogs
  require a target; the API accepts `variant=alternative` without one, so
  existing clients keep working; older alternatives keep their
  mark without a target, and editing one asks for it.
- **"Alternative zu Pos. X"** appears only in offer and order confirmation,
  with the document's number (worked out again for an offer of groups
  only); a target that is not listed is named by quantity and title. The
  planning and the price overview have no stable position numbers – after
  a change only the touched groups are sent – and say „Alternative zu „8 ×
  LED-Scheinwerfer““.
- **Optional:** a covering subrental, a line with issued material and a
  line other subprojects take over from cannot become optional or an
  alternative – for the selection, the single dialog and the API alike.
- **Selection** (PRJ-082): each line goes through the single-line service
  in its own step; lines the action cannot be done with are named with the
  reason, the others are changed. A covering subrental moves only with its
  line, a percentage surcharge stays with its targets; a surcharge, a
  taken-over line and a covering subrental get no discount. Only the
  touched groups are refreshed. "Move" needs an explicit choice
  ("Verschieben nach …" is disabled, "ohne Teilgruppe" is a choice).
- **Subrental** (PRJ-084): shown in its line's section as a sub-row,
  wherever the subrental stands, and following its line on edit, move and
  drag. The dialog asks quantity, status, supplier and purchase price (the
  last with that right); the edit dialog keeps title, quantity, period,
  supplier, status, purchase price and note. Pricing already charged it 0.
- **MVR file** (PRJ-086): kept when read in the browser ("Andere Datei
  wählen" removes it), through the API with the call that adds the lines –
  the first call still writes nothing. Name `yyyymmdd-hhmmss_<name>.mvr`
  in local time; no document type, not visible to crew; above the upload
  limit of project files not kept, with a warning.
- **Below the groups:** one framed row directly under "Ohne Teilgruppe"
  and above "Personal" – new group, line without product (and, in a
  family, take over from another part), "MVR-Datei importieren". The
  placeholder is "Neue Teilgruppe"; "Teilgruppe hinzufügen" was kept.
  Line buttons in the order optional, alternative, edit, copy, delete.
- **"Gewinn aus dem Projekt"** (PRJ-087) replaces the one label
  "Deckungsbeitrag" (planning totals); per row, in the list and the price
  overview, it is "Gewinn".

### Offers, project list, deployment PDF (DOK-013, PRJ-085, PRJ-081)

- **"nur Teilgruppen" hides only positions inside groups.** Each group and
  subgroup becomes one row with title, description, discount or flat-price
  note and sum; a group with subgroups keeps both halves ("mit
  Untergruppen", the subgroups, "Zwischensumme … mit Untergruppen"). Lines
  outside groups, personnel and surcharges stay listed – a single sum row
  would hide what they are –, and so do optional and alternative lines in
  a group, which are not part of its sum. Positions are renumbered from 1;
  totals and taxes are computed on the full offer first and are the same
  in both modes; the stored content is what the PDF shows (DOK-007).
- **Only offers can be "groups"**; for any other kind it is refused (400),
  not ignored. Offers have no XRechnung, so nothing else follows.
- **Validity as a date, in days or both**; both must name the same day,
  otherwise the error names both dates. Days count from today (the
  offer's date), 0 to 3,650. The default lives in the offer's document
  template; the migration sets 14 days. New placeholder `{validity_days}`.
- **Sum columns** (PRJ-085): material revenue = net minus personnel
  revenue; material costs = subrental costs, the only material cost the
  calculation knows; profit = `contribution_margin` (see Part 16: minus the approved expenses as well). A whole project shows
  its own sums plus its non-cancelled parts the user may read, gross taxed
  once per rate; each part shows its own – summing a column with both
  counts a part twice. Rights as on the planning page (profit needs all
  three cost and price rights; hours none); rows whose planning the user
  cannot read stay empty. Not sortable: the sums are calculated, not
  stored. A fixed number of queries per page, which needed the `lookups`
  parameter of `compute_project_prices`.
- **The deployment PDF** lives in `documents`, with the documents'
  letterhead and fonts and the crew disposition's logo and footer. It is
  not stored and has no number; it shows "Stand" with date and time. From
  the tab it is exactly the viewer's view; as a mail attachment the
  neutral view of any colleague – no "Mein Einsatz", no own times, contact
  data only as released, because a planner sees unreleased numbers that
  must not leave the house (PER-019). Offered for every project, not
  ticked by default; one button "Drucken / PDF", and the page prints
  cleanly through print CSS.

### Timeline, utilization, product discount, start data (VFG-024, VFG-025, PRD-041, ADM-011)

- **Hour steps:** the finest of 1, 2, 3 or 6 hours that keeps at most 40
  columns in view – 1 day 1 h, 2–3 days 2 h, 4–5 days 3 h, 6–10 days 6 h.
  Bars are exact to the minute, so the step only sets headings and grid
  lines. The control is "Tage" (1 to 10) or "Wochen"; switching to days
  offers the number chosen last in the session (as PRJ-067), else 3; the
  group label is "Zeitraum" (was "Zoom"); `?days=1|2|3` keeps working.
- **API:** `days` 1 to 84 on `/calendar`, `/utilization`,
  `/personnel-plan` stays. The product, model, item and person timelines
  keep weeks only – their per-day free counts are not the same control.
- **Exact bars for every bar** of the project timeline and the personnel
  plan in all views – one rule, consistent with the real-time warnings of
  VFG-023. Product, item and person timelines keep whole-day bars.
- **Utilization suggestions** come from `/products/suggest/` without kits,
  services, subrentals and surcharges; a chosen one shows exactly that
  product, typed text plus Enter searches; category and search
  are separate forms. The combobox roles apply to every type-ahead field,
  following the address fields (EML-037).
- **Maximum discount per product** is read at pricing time, so duplicates
  and templates follow it (there is no product copy). Crew lines stay
  limited by the job function only (PER-026); with both limits the
  stricter counts. Import column "Höchstrabatt" with aliases ("Höchster
  Rabatt", "Max. Rabatt", "Maximum discount", …).
- **Start data:** all unit abbreviations map to e-invoice unit codes; the
  customer's "Angefangener Kilogramm" is "Angefangenes Kilogramm". "Stück
  (Miete)" is created first, as the fallback unit of categories without a
  preset. Categories T, L, M, R, K (own stock, rental, "Stück (Miete)"), V
  (sale, "Stück (Verkauf)"), E (subrental, no stock; E-001 "Zumietung"
  stays) and D (service, "Stunde"); the fields K "Länge (m)" and L
  "Leistung (W)" stay; new installations do not get S, A, F (the demo
  data creates them). The power is a field of every
  material model and L has no such field (MAT-049); N "Nebenkosten" exists,
  and the demo's F "Fahrt/Transport" presets Nebenkosten instead of
  services (PRD-045, Part 15). The scale "Standardstaffel": 1.0, 1.5, 1.75, 2.0,
  2.4, 2.75, 3.5, then +0.3 per day.
- **The migration** runs only where start data was installed
  (`SystemSettings.defaults_installed`) and only adds: units by name (case
  ignored), the scale if no scale has that name (default only if none
  is), a main category if neither code nor name exists. It never renames,
  changes or deletes; an existing "Standardstaffel" keeps 1.0/1.5/+0.5.
- **Import units:** a name without its bracket part, or a shared
  abbreviation ("Stück", "Stk."), resolves to the unit the product's
  category presets if it is one of the matches; an exact name wins.

### The head of a project, documents and files (PRJ-078, PRJ-079)

- **Order of the head:** "Projekt bearbeiten" · status list + "Status
  ändern" · "<Dokument> erstellen" ▾ · "Duplizieren" · "Als Vorlage
  speichern" · "Teilprojekt anlegen"; the rights as before. The tag runs
  no query – it is on every tab.
- **Next document:** inquiry/option → offer; confirmed (open)/confirmed →
  order confirmation; out → delivery note; returned/closed → invoice;
  cancelled → none. Where the usual one is not possible (a part makes
  priced documents at the whole project; no price right) a confirmed or
  running project suggests the delivery note, otherwise nothing, and all
  kinds stay in the list. The button leads to the tab "Dokumente" with
  the kind chosen; the document is checked as draft and made there –
  nothing is made by one click in the head.
- **A status change keeps the tab**, except "Bestätigt – Einzelheiten offen"
  without open items, which still leads to the Zeitplanung (PRJ-059).
- **Files** are on the tab "Dokumente" below the documents and "Dokument
  erstellen", with the upload form inside the files panel; the old
  address of "Dateien" redirects there.

### Installing and updating (NFA-069)

The cause on an installed server: the installed scripts had no execute
bit, and `/usr/local/bin/rentalars` was missing. `install_cli` therefore
writes the command as a small wrapper script (`exec /bin/bash
/opt/rentalars/app/deploy/rentalars "$@"`) on every install, update and
rollback instead of relying on a symlink; every script calls the others
with `bash script`, the backup unit runs `/bin/bash …/backup.sh`, and
`make_scripts_executable` sets mode 755 on the scripts of the new release,
of the running release before an update and of the previous release
before a rollback switches it on – after a rollback the old release's own
updater runs again, and it calls the scripts directly. *Rejected:* relying
on the execute bit alone – a package unpacked elsewhere or copied through a
share loses it.

### Not built

- The later notes are recorded as stage 7, KANN, nothing
  built: PRD-042 (job functions with the products; products and services
  apart – function and service product are one-to-one,
  PRD-044, Part 15), UIX-028 (notice of open shortages or items x days before the
  start), DOK-014 (invoices can be switched off), VFG-026 (dragging
  appointments in the days view), PRJ-089 (uploading show files – EOS,
  Hog, ChamSys, Resolume, …), UIX-029 (switching between German and English), PRJ-090
  (dummy projects as tickets for service cases), EML-044 (AI summary of a
  correspondence), PRJ-091 (AI suggestions for project templates).
  (See Part 16: DOK-014, VFG-026, PRJ-089 and PRJ-090 –
  as service cases – are built; the others are stage 9.)
- Making a project from an inquiry; a preview of an inquiry's text.
- A note on the planning page that material is partly out.

### Assumptions to confirm

For the catalogue, chapter 12.2 number 20:

a) Mails without tag are left alone unless a mailbox is set to take them
   in; "unverändert lassen" does not even mark them read; a mailbox with
   mails is switched off instead of deleted (see Part 15,
   EML-046); the old mailbox becomes "Projekte" (EML-041).
b) A rate row without "gültig ab" counts from always; a row counts as a
   whole, so an empty rate in a newer row means the guide value; the
   import never copies guide values as own rates (PER-029).
c) "Je Tag" counts the calendar days a period touches; an end at midnight
   does not count the next day (PER-029).
d) Moving a phase moves its crew as described above; nothing is cut to
   the project's period (PRJ-080).
e) While material is only partly out the project keeps its status, but
   the material counts as out – an option partly out reserves firmly
   (PCK-025).
f) With the right to see personnel costs, the price overview by phase
   shows costs and profit in the browser, never in PDF or CSV (PRJ-088).
g) The deployment PDF attached to a mail shows contact data only as
   released, also when a planner sends it (PRJ-081).
h) Existing installations keep their "Standardstaffel" and their units
   and categories; only what is missing is added (ADM-011).

## Part 13: Requirements from practice

The requirements from the use of the application (catalogue: PRJ-092 to
PRJ-096, PRD-043, ADM-012, PER-032, UIX-030 to UIX-032; changed PRJ-006,
PRJ-008, PRJ-071, PRJ-076, ADM-003, PER-016; chapter 12.1 "Weitere Wünsche"; chapter 12.2 number 21). Four questions were
answered before building – the name of the status, crew answers by mail,
customer material, the project numbers –; the decisions are noted where
they mattered. Two further questions were answered by what was
built: dry hire by a template (PRJ-095), the credit by UIX-031.

### Phases, status, the template "Dry Hire" (PRJ-092, PRJ-093, PRJ-095)

The requirement: phase kinds "Planungen und Besprechungen", "Packen" instead of
"Verladen", a phase for unpacking and checking after the return, and a
status name that is not mistaken for a back button. Decided on the
status: "Wieder im Lager".

- **Names change, stored values stay.** "Packen" keeps the value `loading`;
  "Wieder im Lager" is the status `returned` – a translation, no data
  migration. *Consequence:* existing phases, API clients and webhooks see
  the same values; `projects/0011_phases_063` only changes the choices. The
  loading time of a packlist (`Packlist.loading_at`) keeps "Verladen".
- **Order:** `planning` first, `aftercare` ("Nachbereitung") right after
  `return`, then `cleaning`, `other` last. *Consequence:* cleaning is not
  the last kind (PRJ-071).
- **Phases outside the rental period show everywhere.** A planning meeting
  lies weeks before the rental. The month and week calendars show it;
  the timeline and the API `/calendar` list a project when one
  of its phases touches the span (`projects_or_phases_in`, one `Exists`).
- **Dry hire is a template, not a project type.** The requirement: a
  template without crew or phases, created by the installation script as a
  default. Built: a template without crew and lines, but
  **with** the phases of a rental at the warehouse, each at "Lager" with a
  short note – Packen, "Übergabe an den Kunden (Abholung)" (kind `other`),
  "Rücknahme" (kind `return`), Nachbereitung – the course of such a rental
  as `projects/defaults.py` describes it. *Consequence:* the
  project has no field for "the customer picks up"; the
  template's note says it in the project notes.
- **`"anchor": "end"`** lets the last two phases follow the end of the
  rental, so the template fits any length; a very short rental cuts them to
  its period. The content stays version 2; "Als Vorlage speichern" never
  writes the key.
- **Created by the first-run setup, not with the start data.**
  `install_defaults` runs after every `migrate`, test databases included;
  the template belongs to an installation that is set up. The migration
  `projects/0013` adds it where setup is completed and no template of that
  name exists (case ignored). *Consequence:* both run once, so a template
  the company renamed, replaced or deleted is never created again.
- **Demo data:** the festival has six phases, from a site visit a week
  before to the follow-up work.

### A new phase from the crew planning (PRJ-094)

The requirement: a "new phase" entry in the phase list of the crew planning,
opening as a pop-up dialog like "new customer" in the project.

- **Only with JavaScript, only for editors.** The script adds "Neue Phase
  …" from data attributes; the dialog's address without htmx redirects to
  the page "Neue Phase". It is offered with edit access to a project that is
  not closed – a "Personaldisposition" who may plan crew but not edit the
  project gets neither entry nor dialog.
- **A dialog of its own, stacked.** The crew line's form already lives in
  `#dialog`; the phase opens in `#phase-dialog` over it, its buttons close
  only it. Saving answers 204 with the event `phaseCreated`. *Rejected:*
  `objectCreated` with `closeDialog`, which would close the crew line's
  dialog and lose what was typed.
- **After saving** the phase is in every phase list of the project, in time
  order, and chosen in the one it came from; the crew form keeps function,
  person, places and note and takes the phase's period as with any phase.
  The dialog asks kind, label, period, venue and place – no notes – and
  starts with the period typed in the crew form.
- **Keyboard:** reaching the entry with arrow or letter keys only selects
  it; Enter or Space opens the dialog, leaving the list restores the former
  phase (WCAG 3.2.2). Escape closes the dialog and returns the focus.
- **Bug fixed:** a phase starting before the typed "Von" left
  "Bis" with the old minimum, and the browser refused the form – every
  time for a planning meeting before the rental period.

### Project numbers with "P-" (ADM-012, ADM-003)

Decided: convert completely – for new installations, and for existing
installations for new and for existing projects.

- **The old number is a field** (`Project.former_number`, indexed, not
  editable), not a table of aliases: only this migration ever renames, so
  one former number per project is enough, and searches need no join.
- **Only the default scheme is converted** – a prefix or number without
  letters apart from `{year}`: `{year}-`, `{year}/` and an empty prefix get
  "P-", and so does every number without letters, parts included. A prefix
  that starts with "P-" stays, but older numbers still get "P-". Any other
  prefix with letters (`PRJ-{year}-`) is the administrator's own scheme:
  nothing changes, no "P-PRJ-…". Numbers with letters are never touched.
  *Consequence:* the step is idempotent, and a former number never has a
  letter – which is what spares a query for every number of today.
- **Safe on MariaDB**, which compares the unique number without case: a new
  number starts with "P-", one being renamed has no letter, so they cannot
  meet. A target already taken (case ignored) or over 30 characters is
  skipped; that project keeps its number, which keeps working. Tested on
  MariaDB with `2026-0003` next to `p-2026-0003`.
- **Traces:** change-log entries with the actor "Aktualisierung" for
  the prefix, every project and every template whose `source_number`
  followed. Documents are not touched – what was sent stays as sent. The
  reverse step does nothing.
- **Today's number always wins** over a former one – in addresses, mail
  tags, the API and the forms. A newly allocated number that equals a
  former one is skipped (`_next_free_number`), should the prefix ever be set
  back to `{year}-`.
- **Old addresses** answer 301 to today's address, query string kept, for
  GET and HEAD only; a POST is served at the old address (a redirect would
  turn it into a GET). The middleware comes after the login, so a visitor
  who is not logged in learns no number.
- **Mail:** a reply carrying an old tag lands in its project; answering such
  a mail from Rentalars replaces the old tag of the same project instead of
  adding a second one. ICS and CalDAV UIDs are built from the crew line's
  key, so subscribed calendars see only a new summary; webhooks, exports,
  PDFs and their file names read the live number.
- **The dependency on `core/0007`**, not `core/0008` (which only changes a
  help text): the development database had recorded the empty placeholder
  of `projects/0012` as applied, and a dependency on a newer core migration
  would have made its history inconsistent.

### Crew requests answered by reply mail (PER-032, PER-016)

The requirement: requests can run by mail with `mailto:` links, so that
the server need not be reachable from the internet; decided: build it now. Rentalars fetches the answer itself over IMAP – the
connection goes from the inside out.

- **A new token per request mail:** 120 random bits as 24 characters (a–z,
  2–7) in `CrewRequestMail`, in the subject as `[RA-E-<token>-JA]` or
  `[RA-E-<token>-NEIN]`. There was no link token to reuse – the link of a
  request only leads to the start page behind the login. The tag has a
  fixed prefix, not the configurable project tag prefix. The token is the
  proof, not the sender: a foreign sender is noted in the history, and the
  person is told.
- **Default "beides".** Without a fetched mailbox it behaves exactly like
  "link only"; adding one later switches the buttons on by itself.
  *Consequence:* existing installations with a fetched mailbox send
  buttons from the update on.
- **The answer mailbox:** the system mailbox if it is also a fetched
  correspondence mailbox with an address, else the outgoing correspondence
  mailbox; it is the request's `Reply-To`, so a free-text reply reaches a
  mailbox somebody reads.
- **The request mail replaces the plain notification mail**; the in-app
  notification stays. Whoever switched off mails for deployment requests
  gets none. It also goes to people who cannot log in – every person has an
  account (AUT-026), but one never invited cannot use the link. "Per
  Antwort-Mail" leaves the link out.
- **No reading of "Ja" or "Nein".** A reply quotes the request with both
  words, and signatures vary; a wrongly recorded answer is worse than none.
  *Rejected:* parsing the text. The note is what stands after "Anmerkung:"
  up to the dashes, at most 250 characters, also from an HTML-only mail.
- **The same rights as in the browser:** the answer is recorded through
  `answer_deployment`, acting as the person's account, so the planners'
  notifications and the history are the same. Refused with nothing changed
  and a friendly mail: line deleted or another person planned, asked again,
  answered already, project cancelled or closed, deployment over, person
  deactivated. Unlike the browser, a cancelled project is refused.
- **No loops, no strangers:** confirmations and refusals go only to the
  person's stored address, carry no tag and are marked `Auto-Submitted`; an
  automatic reply or bounce that quotes a tag is a normal mail. This is the
  one automatic reply to incoming mail, a stated exception to EML-030.
  (See Part 16: the answer of an automation, ADM-013, is
  the second.)
- **Handled once:** a mail already logged as an answer (second mailbox,
  failed filing) is only filed away. The mail log stores `accepted`,
  `declined` or `<answer>:<reason>` ("Absage – nicht übernommen: schon
  beantwortet", yellow); the history says "Antwort von X kam per
  Antwort-Mail", naming a foreign sender.
- Notification titles of requests and answers name the weekday in German
  ("Mi", not "Wed").

### Customer material (PRD-043, PRJ-096)

A rental company stores a customer's gear and takes it to that customer's
events. The requirement: customer material in the warehouse is handled like
own material, with model, weight, volume and storage place, but belongs to
the customer: never rentable to others, without price; in a project it is
added as carried along; in the material management it is a product of the
category "Fremdmaterial C", with the customer as owner and a model as usual,
as bulk material without item IDs or with IDs and labels, plannable only in
projects of this customer, never with a price.

- **A mark on the category, an owner on the product.**
  `Category.is_customer_material` on main categories with own stock only
  (subcategories follow); it cannot be switched while the category has
  products. C "Fremdmaterial" is in the start data and added by
  `masterdata/0005` under the rule for the start data: only if neither
  code C nor the name exists – a C used otherwise is not marked.
  `Product.owner` → `Customer`, `PROTECT`. *Consequence:* a customer whose
  material is stored can be deactivated, not deleted.
- **Rules of the product:** an owner exactly in a marked category; only
  rental or kit (a kit holds only the same owner's material, and customer
  material is never in a kit of one's own); no price, sale price or
  surcharge; billed flat without scale or maximum discount; the owner fixed
  once the product is planned.
- **No migration of `projects`.** A line is customer material when its
  product has an owner; the rules run in `MaterialLine.clean` – the owner's
  projects only (parts share the customer), price 0, no discount, not
  optional or alternative, no sale, billed flat. *Consequence:* one check
  for page, API, copies, templates and the MVR import; the customer's
  standard discount does not apply.
- **Price 0 with a flag, the same everywhere.** `LinePrice.is_customer_material`:
  a normal line, but outside the group sum, the share of a group's flat
  price and the tax split; "nicht berechnet" on the planning, the price
  overview, its PDF and CSV; not part of "Material-Einnahme".
- **Documents:** offer and order confirmation show quantity, no price, no
  amount, and "Kundeneigenes Material – wird mitgeführt, ohne Berechnung" –
  also an offer of groups only, under its group, so the customer is sure
  the gear will be there. The invoice and the XRechnung leave it out; the
  delivery note adds "Kundeneigenes Material – wird mitgeführt"; the
  packlist shows it with weight, volume, storage location and a hint.
- **Availability as own material, no subrental.** A defective item or a
  second gig at the same time makes it short; nobody else can supply it, so
  `accept_subrental_suggestion` refuses (also through the API), API
  shortages have `suggestion: null`, and the planning says
  "Kundenmaterial lässt sich nicht zumieten."
- **Where it can be found:** the product search offers it only for a
  project of the owner (`?project=`) or a kit of the owner (`?owner=`); the
  MVR import never suggests it. A project (or its family) planning the
  customer's material cannot change customer; copied groups and duplicated
  projects skip foreign customer material, templates leave it out with a
  message.
- **Product form:** the existing show-if mechanism switches between owner
  and prices by category – no new script; values hidden by the switch are
  dropped. The owner is typed with the customer suggestions, which can
  create a customer. Labels print "Eigentum von <Kunde>" instead of the
  company line (QR) or under the name (barcode, not on small labels).

### Lists, menu and the pages without login (UIX-030 to UIX-032)

- **One pattern for every filter bar** (UIX-030): `{% filterpanel %}` with
  a "Filter" button, the summary and the panel; the search stays in front.
  Folded at 900 px and below – where the phone layout starts –, open above,
  set by CSS before the script runs so nothing jumps; without JavaScript no
  button and every field. Folded, the button counts the active filters and
  chips name them. *Rejected:* keeping the panel open while a filter is
  set. The choice is remembered per list in
  `localStorage`, not with the account; it wins over the width, and a form
  with an error is never folded. Left out: the user list, the timeline,
  utilization and personnel-plan bars, "Wer ist frei?", the inquiries.
  Nothing is remembered; folded on every page load
  (UIX-038, Part 18).
- **The credit** (UIX-031): "von fld-vt.de" rather than "by" – the
  interface is German –, under the version and below the login, the
  constants next to `__version__`. The GPL-3.0 allows such a notice but does
  not protect it: whoever passes Rentalars on may remove it unless an
  additional term under section 7 b) keeps it. Whether there should be one
  is a decision for the project owner; `LICENSE` is unchanged. There is no about or
  licence page to put it on.
- **The company name without a cache** (UIX-032): a scalar subquery with
  the session user, in the query that brings the person – always current,
  no query of its own. *Rejected:* a cache invalidated on save: the default
  cache is per process, so with five gunicorn workers the others would keep
  the old name, and the first page after a clear cost a query (four
  query-count tests failed). Not on the public pages.
- **Login centring** (bug fix): the grid item was as wide as its widest
  text, so the 440 px box sat at its left edge while logo and footer were
  centred – 106 px off at 1366 px and wider. A full-width centred column
  fixes all pages of `base_public.html`; the setup form also fits at
  320 px. Found while testing: on phones the page grid shared out the
  height of short pages, so the top bar stood about 220 px high
  (`align-content: start`).

### Not built

- The notes recorded as stage 7, KANN, nothing built:
  UIX-033 (a link from an address into the route planning of Google Maps;
  the address leaves Rentalars only with the click), UIX-034 (an
  interactive, zoomable map at addresses – its tiles, from Google Maps or
  OpenStreetMap, load from outside and tell the provider which places are
  looked at; whether and how that fits NFA-050 is decided before building),
  PRJ-097 (travel distances of a project worked out automatically: for
  "Packen" the distance to the warehouse – a fixed setting – plus trips to
  suppliers of subrented material marked "wird beim Lieferanten abgeholt",
  for "Aufbau" and "Abbau" warehouse to venue and back, for "Nachbereitung"
  as for "Packen"; it needs an outside routing service, decided together
  with UIX-033 and UIX-034), ADM-013 (automations with triggers defined in
  the browser, e.g. an acknowledgement for mails without project tag in a
  mailbox that takes such mails – a deliberate exception to EML-030 that
  needs a guard against automatic replies answering each other). (See
  Part 16: all four are built; the map is OpenStreetMap after
  a click, and PRJ-097 gives trips with route links instead of distances.)
- Removing old `CrewRequestMail` rows; marking answers by mail on the
  planning page (only history and mail log show them).
- Customer material in the demo data; an owner column in the lists of
  models and items; a choice limited by owner in the material model form,
  whose default product is a plain list of all products with stock (the
  validation refuses wrong combinations).
- A credit on an about or licence page; a GPL section 7 b) term.

### Assumptions to confirm

For the catalogue, chapter 12.2 number 21:

a) "Packen" keeps the stored value of "Verladen"; existing phases do not
   change. The timeline and the calendar API show a project when only a
   phase of it lies in the span (PRJ-092).
b) "Neue Phase …" exists only with JavaScript and only for those who may
   edit the project; the dialog does not ask for notes (PRJ-094).
c) Dry Hire: the template has phases at the warehouse, although the
   question suggested none; the hand-over has the kind "Sonstiges", the
   return the kind "Rückfahrt"; "the customer picks up" stands in the
   project notes; a very short rental cuts the phases; the template is
   created only in a set-up installation without a template of that name
   (PRJ-095).
d) Only prefixes and numbers without letters were renamed; a number whose
   target was taken (case ignored) or too long keeps its old number; old
   addresses redirect on reading, after the login; replying to an older
   mail replaces the old tag; going back does not restore the old numbers
   (ADM-012).
e) "Beides" is the default and acts like "link" without a fetched mailbox;
   the request mail replaces the notification mail and also reaches people
   who cannot log in; the code counts, not the sender; unlike the browser, an
   answer to a cancelled project or from a deactivated person is not taken
   over; requests sent by mail are never cleaned up (PER-032).
f) The mark "customer material" sits only on main categories with own
   stock and stays while there are products; C is created only where neither
   code nor name exists; customer material is never in a kit of one's own,
   is billed flat without scale or maximum discount, keeps its owner once
   planned; an anonymised customer keeps its products (PRD-043).
g) In a project, customer material gets no standard discount and no
   subrental suggestion, also through the API; copied groups and templates
   leave foreign customer material out with a note; the MVR import never
   suggests it (PRJ-096).
h) Filters are folded on every width and on every page load, not remembered;
   a form with errors stays open (UIX-030, UIX-038).
i) The credit reads "von fld-vt.de"; whether a GPL section 7 b) term should
   protect it is open (UIX-031, NFA-052).
j) The company name comes with the login, without a cache, and is not shown
   on the pages without login (UIX-032).

## Part 14: Stage 7

The changes asked for, the server side of the Android
app, and a security fix (catalogue, stage 7
"Ausbaustufe 7": PCK-026 to PCK-030, AUT-021, ADM-014, UIX-035 to
UIX-037, EML-045, PRJ-098 to PRJ-100, PER-033, PER-034, VFG-027 to
VFG-029; NFA-070 in stage 8; chapter 12.1; chapter 12.2 number 22).
The requirements and the answers to four questions before building –
the Raspberry Pi, the partial return, the phase beyond the rental period,
the time picker – are noted where they decided something. The
decisions below are those of the build, checked against the code.

### Scope: stage 7 is this delivery, the rest moves to stage 8

- **Items of stage 7 that were not named move to stage 8.** Stage 7
  is now exactly what the release contains: the requested items, the
  app requirements APP-001 to APP-006 with PCK-026 and PCK-027, and the
  fix of AUT-021. What is built is SOLL. Every other requirement of the
  former stage 7 – the KANN items moved there from stage 6, the
  notes (UIX-033, UIX-034, PRJ-097, ADM-013), EML-040,
  AUT-007, AUT-029 – moves as KANN to a new stage 8 "Weitere
  Erweiterungen". (See Part 16: stage 8 is built; what was not built moved on to stage 9.)
- **The app is not in this repository.** The server part is built from
  the app's server requirements (sections A to D: unchanged calls, change
  times, the two new endpoints, the token fix). APK and app source are not
  part of the package.
- **Raspberry Pi** (question: can the application be installed on one?): only recorded, as NFA-070 [KANN, stage 8] – a Raspberry
  Pi 4 or 5 (64 bit, at least 4 GB) with Ubuntu Server 24.04/26.04 for the
  Pi, Raspberry Pi OS (Debian 13) as an option. Notes for later: the
  install script checks for Ubuntu; the Python libraries come from PyPI
  (arm64 wheels exist; `mysqlclient` is built against `libmariadb-dev` as
  on x86); the number of worker processes should follow the memory. It
  cannot be tested in the build environment. Nothing changed in `deploy/`.
  (See Part 16: built, SOLL in stage 8.)

### The app's server side (PCK-026, PCK-027, AUT-021)

- **Change times on the entry, noted by `save()`.** `PackEntry` got
  `packed_changed_at` and `returned_changed_at`; `save()` compares with the
  quantities as loaded and notes now – or the phone's moment
  (`change_time`) – only for a quantity that changed. So every path –
  ticking, "alle packen", issuing everything, "Alles ist zurück", a
  handover, "Änderungen übernehmen", the sync – is covered without a call
  in each service. A queryset `update()` would bypass it; no service uses
  one on these quantities.
- **Robust against the side version.** Installations that ran the side version have
  the two columns under a migration unknown here. `packing/0004` adds each
  column only if the table lacks it (asking the database) and fills
  `updated_at` in only where a quantity is above zero and no time is
  stored. Tested with the columns present and an unknown migration record.
- **Sync rule** (requirement of the mobile app): changes in the order of their
  moments; a moment in the future counts as now; only a moment *later*
  than the stored one counts, equal goes to the server (`older`); a later
  moment is stored even when the quantity stays the same. One transaction
  with the packlist and the touched rows locked from comparison to
  writing. **Limits are refused, not clamped**: the phone learns that its
  tick did not hold, with the reason; the browser's tick, in contrast,
  holds a quantity within its limits. Invalid input fails the whole
  request with 400, never 500 – also month 13, an offset of 25 hours, a
  moment without time zone or before 2000 – and nothing is applied. Seven
  ways of being refused are tested.
- **The sync never issues and never books a return.** Both stay steps in
  the browser, with their checks and messages. Applied `returned` changes
  fire `packing.returned`, as a tick in the browser does.
- **The list for the phone** takes the rule of opening a packlist, also
  for rights in assigned projects only; `customer` is the customer's name,
  `null` with the deployment view only (AUT-023); `server_time` is UTC
  ("Z"). Rows are not inlined: the app fetches each packlist with `GET`
  and `ETag`. A project whose packlist nobody opened gets its main
  packlist there, as on opening it – all of them in one `bulk_create`
  with their change-log entries (`core.audit.create_in_bulk`,
  `packing.services.ensure_main_packlists`). The measurement found the
  first version, one `get_packlist` per project, at 171 queries for the
  100 projects of scenario 11; now the count does not grow with the
  projects, and the list is part of the measured pages.
- **Route order:** `…/sync` is registered before `…/<slug:action>`, which
  would take "sync" for a packing step. `api/docs` also answers without
  the slash, because the app expects no redirects under `/api/v1`.
- **`Date` header:** left to gunicorn in production. *Rejected:* adding it
  in the application – gunicorn would send a second one.
- **What the app does alone.** APP-002 (screen lock, encrypted storage, no
  screenshots), APP-003 (sync in the background and on request) and
  APP-006 (signed APK, built from Ubuntu packages) are met by the app and
  need nothing new here. The server's part of APP-001 (login with code,
  a token of its own), APP-004/ZEI-020 (time entries sent once – the
  `Idempotency-Key` answer is kept a day, and a later repetition is
  refused as an overlap by ZEI-009) and APP-005 (the server's time in
  `Date` and `server_time`) is what was already offered; the tests of
  section A in `tests/api/test_070_packing_api.py` pin it, so it keeps
  working.
- **AUT-021, a gap since stage 1:** a token limited to modules could
  create an unlimited one. Now such a token gets 403 on creating tokens
  and sees and revokes only itself under `/tokens`, so an app's token on a
  phone cannot reach the user's other tokens; a token with an expiry must
  give `expires_at` no later than its own (400 otherwise); the read-only
  case keeps its 400.

### Partial return per piece, the bar, sub-tabs (PCK-028 to PCK-030)

The requirement: return in parts like the issue, also when only a part of the
material is issued; a position once taken back cannot be issued again; the
tab is to be called "Packen/Ausgabe". Decided on how to read "Position":
**per piece** – what
came back cannot go out again in this project; what was not issued yet
still can (10 planned, 6 out, 4 back → those 4 are done, 4 can still be
issued).

- **The return works like the issue.** `returned_quantity` stays the tick
  "back"; the new `taken_back_quantity` with `taken_back_at` is what
  "Rücknahme buchen" books. Each quantity includes the next: packed ≥
  issued ≥ returned ≥ taken back. `packing/0005` books every earlier tick
  as taken back, because earlier the tick was the booking.
- **Per piece.** A piece taken back cannot be unticked; `issued` keeps
  counting it, so it is never issued again here. Items that came back are
  skipped by the automatic allocation and refused by "Exemplare wählen" in
  the same project; when the other items of a product came back, the one
  item left counts as unambiguous.
- **Items of a row in part:** while only part of a row is back, its items
  stay "in use" – nobody knows which came (PCK-020). They are freed once
  the row is completely taken back.
- **Auto-complete.** A booking that leaves nothing out and nothing waiting
  (packlist "ausgegeben", no handover still expected, no missing row)
  completes the return. "Rücknahme abschließen" moved out of the sticky
  bar into the list; it is for clarified missing parts or a rest that
  will not go out.
- **Project status:** the existing rules stay and work on packlist status.
  `material_out()` (availability, start page) now asks whether pieces are
  out by the books: issued, not taken back, not handed over, sales
  excluded.
- **Availability:** taken-back pieces count as occupied only until their
  booking; the kit components cost one extra query, only when there are
  any.
- **Compatible API and webhooks:** a tick still fires `packing.returned`,
  and so does a booking that completes the return; `return-all` only
  ticks; `complete-return` books the ticks first, so a client calling
  `return-all` then `complete-return` behaves as before. The new action is
  `take-back`. All row quantities in the API are now text with two
  decimals (before, some were unrounded or "0").
- **The bar** (the requirement: ticked green hatched, issued green, ticked back
  orange hatched, back orange): one bar filling from the left – orange,
  orange hatched, green, green hatched, grey – with a legend in words and
  numbers under it. The family view uses the same bar per part instead of
  three green meters. The start page shows no packing progress, so it is
  unchanged.
- **Sub-tabs** (the requirement: see the subprojects as sub-tabs of the
  packlist): in a family, in number order, the whole project and the
  parts – the current part split into its packlists –, then "Alle
  zusammen". Parts the user may not see are left out. The family page has
  the same tabs; its old button in the head is gone.

### Project numbers without "P-" again (ADM-014)

The requirement: revert the "P-" prefix on all project numbers, for future
and for existing projects.

- **One former number is enough.** An older project is called
  `2026-0042` again, which its old documents show; its former number
  becomes `P-2026-0042`, which older documents and mails show.
  A project created with a P- number gets its `P-…` as former number. The earlier scheme
  always set number = "P-" + former number, so nothing is lost.
- **What is converted** mirrors the earlier scheme: only "P-" followed by no further
  letters (`P-{year}-`, `P-{year}/`, `P-`; `P-2026-0042`). `PRJ-{year}-`
  and `P-MS-{year}-` are an administrator's own scheme and stay. A second
  run changes nothing.
- **Both numbers stay** where renaming would lose one: the target is taken
  (case ignored, as MariaDB compares), or the project's former number is
  not the target (only a change by hand can do that). A target never has
  a letter, so renaming in order never meets a P- number.
- **The jump from an older version** runs 0012 and 0014 in one `migrate`:
  the P- number existed only for a moment and is not kept. A migration
  cannot see the plan of its `migrate`, so `ProjectsConfig.ready` connects
  a `pre_migrate` handler (`note_migration_plan`), which receives the
  whole plan and leaves it on the database connection for 0014. The data
  alone cannot tell: after an update in two runs a project looks the same.
  `deploy/update.sh` and `restore.sh` run one `migrate`. A project that
  had "P-" set by hand keeps its P- number as former number.
  The migration tests run `migrate` back to projects 0011 and forward,
  once in two runs and once in one.
- **Lookups** stay cheap: a former number is letter-free or "P-" plus
  letter-free, anything else (`PRJ-…`) costs no query; `project_by_number`
  is one query with today's number sorted first; `numbers_of_today` one
  query for all tags of a subject, case ignored; the converter asks for a
  former number only when today's is not found. No list or search page
  makes a query per row (tested with 5 against 15 renamed projects).
- **Traces:** "Aktualisierung" in the change log for the range, each
  project and each template. The help text of
  `SystemSettings.mail_tag_prefix` shows `[RL#2026-0042]`. Going back does
  nothing; a rollback is done with
  the backup, and the older version then finds replies to such mails
  (`[RL#2026-0042]`) only for older projects.

### Pickers, hatched periods, a phase beyond the rental period (UIX-036, PRJ-099, PRJ-100)

The requirement: the calendar of "Zeitraum wählen" in every date field, and
the time ideally also selectable in a view like the one of a common
calendar app. Decided: a clock face – first the hour,
then the minute on a round clock face, as in the Android app.

- **The fields keep their native type** (`datetime-local`, `date`,
  `time`): value format, parsing, form checks, the API and every test that
  fills a field stay unchanged, and without JavaScript the browser's own
  picker is there. The script puts its button where the browser's symbol
  was (hidden with `::-webkit-calendar-picker-indicator`).
- **When it opens:** the button, Alt+↓ or F4. A click into the field
  places the cursor for typing; only on a touch screen (`pointer:
  coarse`), where the browser would cover the page with its own picker, a
  tap opens ours.
- **Clock face** as in Android's 24-hour mode (outer ring 12, 1–11, inner
  00, 13–23); minutes shown in steps of five, a tap snaps to five,
  dragging or typing gives any minute; a `role="slider"` for the keyboard.
- **Calendar:** a date alone is taken with the tap on the day; date and
  time need "Übernehmen"; "Leeren" only on optional fields; `min`/`max`
  days marked but focusable; the partner field's day outlined. On a phone
  date and time take turns.
- **Hatching** (the requirement: the other period lightly hatched in "Zeitraum im
  Kalender wählen", and both when creating phases): rental period grey,
  event green, lines in opposite directions, a legend with the times. The
  project form reads the other period live from its fields, the phase
  forms the saved periods. The single-field picker shows the same marks as
  the range picker.
- **Project form:** the event box is laid out like the rental box – Von,
  Bis and the button in one row, rental days in a second row – which also
  puts the button that was out of place where it belongs. The field labels
  stayed.
- **A phase beyond the rental period.** Decided: ask first –
  Rentalars suggests extending the rental period ("Material außer
  Haus") and changes it only after the user agrees. The phase is always
  saved first; the suggestion is the old period widened just enough.
  "Erweitern" goes through `services.update_project`, the path of the
  project form (closed project refused, subproject within its whole
  project, lines with the old period follow, change log,
  `project_changed`). A warning only if the longer period makes more
  pieces missing than before. A subproject whose whole project does not
  cover the new period gets no button, only the note. In the dialog over
  the crew planning the question stays in the dialog and the page offers
  to show the change instead of reloading, so the crew form keeps what
  was typed.
- **Phases of the kind "Planungen und Besprechungen" never ask** – by decision: a site visit weeks before would block material for all
  that time.
- **The API only reports** (`outside_rental_period`,
  `rental_period_suggestion`, read-only, no extra query); a client extends
  with `PATCH /projects/{id}`. No new operation.

### Crew requests and the footer of mails (PER-033, PER-034, EML-045)

The requirement: after an answer (e.g. by mail) the planning still showed
"angefragt" until the notification was opened; "erneut anfragen" only
after changed times; every change of times of a requested or accepted
line should ask again, switchable in the settings; automatic mails should
name Rentalars, the company and the address.

- **The cause was the browser script, not the server.** The answer was
  stored and moved the project's stamp; but when the planner saved
  something before the next 20-second check, the script took over the new
  stamp as its own and swallowed the answer. The stamp is now
  `<newest change>.<newest change by somebody else>`, still one query;
  after an own change only the second part is compared, so own changes
  stay silent; a change by the same user in another tab or the app still
  reloads at the next check. Reproduced in the browser; the new test fails
  without the fix.
- **What counts as changed:** only start and end. Hours, a phase without
  new times, job function, meeting point and note do not.
- **"Erneut anfragen" only after new times.** Accepted or declined lines
  with unchanged times show only the badge, and the service refuses (400
  in the API). A waiting request may be sent again (a corrected address).
  The line names the times asked for. Lines asked earlier got their
  current period by the migration; a line without one counts as changed.
- **The automatic request** (setting "Bei geänderten Zeiten neu anfragen",
  on by default): only for requested or accepted lines, not for declined
  lines, cancelled projects or deactivated people; through the same path
  as a manual request, naming new and old times; "angefragt von" is who
  changed the times, in a command who asked before. The older request
  mail no longer counts ("neuere Anfrage"). A new person still resets the
  request. It runs in `update_crew_line` (dialog and API) and
  `move_with_phase`, the services that change the period of an existing
  line; a direct ORM update would bypass it, and none exists.
- **The footer is added in the mail backend**, the one place every system
  mail passes – also Django's password reset. Text part after `-- `, HTML
  as the last paragraph inside `<body>`, once per message, also without a
  company name; company name of the profile and `[rentalars] url`.
  Correspondence goes out through `mail.sending` and keeps the writer's
  signature without a footer. The request mail lost its own "sent
  automatically by Rentalars" line.

### Planning and forms (VFG-027 to VFG-029, PRJ-098, UIX-035, UIX-037)

- **Colours of the personnel plan** (VFG-027): a status shown only as a
  3 px edge on a background almost that of the panel can hardly be seen,
  and a one-day deployment in two weeks is about 25 px wide. Deployments are
  coloured **by commitment** (`crew_bar_css`): "fest" (orange) from
  confirmed on, out, returned and closed included; option yellow; inquiry
  grey; "angefragt" paler with a dashed band. The
  project timeline keeps the calendar's status colours, filled.
- **Larger markings:** a 30 % tint and a 6 px band on every status bar,
  text in the normal text colour (5:1 or better); stronger tints and
  hatching for availability and absence; taller bars and legend.
- **Defaults** (the requirements: "Woche" before "Monat" and chosen; timeline
  and personnel plan on 4 days; tab order Kalender, Zeitstrahl,
  Materialauslastung, Personalplan, Fehlbestände): `DEFAULT_DAYS` 4; the
  session also remembers days or weeks (`schedule_span`), shared by the
  three views, written only on change; `?month=`/`?week=` without `view`
  show what they name.
- **Materialauslastung like the timeline** (VFG-029): 1 to 10 days in hour
  columns or 1 to 12 weeks; the peak per column with the queries of the
  day view; equal neighbouring columns joined into one cell to keep the
  page small; the search forms outside the region that reloads, so the
  type-ahead keeps working.
- **Shortages among the open items** (the requirement: listed as bullets
  like the other open items): one bullet per
  shortage not resolved yet, from the same calculation as the page
  "Fehlbestände", run once; projects with only shortages are listed too;
  each bullet links to its line, which is highlighted. Only projects whose
  planning the user may read.
- **Required fields** (the requirement: mark required fields that were not
  marked, e.g. the price in "Neues Produkt"): one filter decides
  (`required_condition`) – required form field, `mark_required()` for a
  field the model requires, or a condition (`data-require-if`) that also
  shows and hides the asterisk; the note "* Pflichtfeld" once per form.
  Validation is unchanged: the model still decides. Marked under
  conditions: the product's price for every kind but sale, sale price,
  percentage, owner, custom scale; the project's customer unless
  internal; a mailbox's IMAP and SMTP data, address and done folder.
- **Small things:** the mailbox buttons "Verbindung prüfen" and
  "Bearbeiten" in one flex row, both with an icon; the API documentation
  opens in a new tab (`target="_blank" rel="noopener"`) without a hint,
  as the project has no convention for one.

### Not built

- **NFA-070** (installation on a Raspberry Pi), recorded for stage 8.
  (See Part 16: built.)
- **Checked against the real app:** the server part was tested against
  the agreed interface, not against the app or its JSON; whether
  the key `projects` and `customer` as a name match is unconfirmed.
- **Choosing the items of a partial return;** items are freed only when
  their row is completely taken back.
- **Shortages in the API `/open-items`.** The "Neue Packliste" form has its
  asterisk but no "* Pflichtfeld" note; GET filter forms, radio groups
  that always have a choice and the SMTP password (condition "field
  filled") are not marked.
- **Crew:** there is no button to record
  "abgesagt" on an accepted line for the same times (the API `answer`
  still works); the person's deployment page shows no former times;
  declined requests still look like normal bars in the personnel plan.
- **Pickers:** the crew forms get the picker but no hatching; not checked
  in Firefox (its own symbol may show next to ours), iOS Safari (the native
  picker may flash) or Android Chrome, nor with a real screen reader.
- **The light theme** was checked for the planning colours by forcing
  `data-theme="light"`; it is still not offered in the interface.

### Assumptions to confirm

For the catalogue, chapter 12.2 number 22:

a) Partial return: a piece taken back is never issued again in its
   project; items become free only when their row is completely taken
   back; a booking that leaves nothing out and nothing waiting completes
   the return; "Rücknahme abschließen" is for missing parts or a rest that
   will not go out (PCK-028).
b) The bar fills from the left in the order taken back, ticked back,
   issued, packed, in the warehouse; pieces handed over to another part
   count as taken back; the family view uses the same bar (PCK-029).
c) Sub-tabs list the whole project and its parts in number order, then
   "Alle zusammen"; parts one may not see are left out (PCK-030).
d) The phone gets the projects "Bestätigt – Details offen", "Bestätigt"
   and "Unterwegs"; `customer` is the name, empty with the deployment view
   only; a change without time zone or before 2000 makes the whole request
   invalid; changes beyond the limits are refused, not clamped; at the same
   moment the server wins; the sync never issues or books a return
   (PCK-026, PCK-027).
e) A token limited to modules creates no tokens and sees only itself; a
   token with an expiry must name an expiry no later than its own
   (AUT-021).
f) Project numbers: only "P-" with no further letters is removed; own
   schemes with letters stay; a project whose target number is taken keeps
   both numbers; an update straight from an older version leaves no former
   number; going back only with the backup (ADM-014).
g) The fields keep their native type; a tap into the field opens the
   picker only on touch screens; the clock face shows five-minute steps;
   "Leeren" only on optional fields (UIX-036).
h) Rental period hatched grey, event green; the phase forms show the saved
   periods, the project form the typed ones; the crew forms show none
   (PRJ-099).
i) A phase is always saved first; the suggestion widens the rental period
   only as far as the phase needs; "Planungen und Besprechungen" never
   asks; a subproject must first have its whole project extended; the API
   only reports (PRJ-100).
j) Only start and end count as changed times; declined lines are not
   asked again by themselves; older lines count as changed;
   automatic requests are on by default and name who changed the times;
   an answer to an older request mail is not taken over (PER-033, PER-034).
k) The footer goes on every system mail, after the signature separator,
   never on correspondence (EML-045).
l) Deployments coloured by commitment – firm from "confirmed" on, also out,
   returned and closed; inquiry grey; 4 days and the week are the
   defaults; the session remembers days or weeks until logout; the API
   defaults are unchanged (VFG-027 to VFG-029).
m) Open items show shortages only for projects whose planning one may
   read; the API `/open-items` does not include them yet (PRJ-098).
n) Required fields are marked, not newly enforced; GET filter forms,
   radio groups with a fixed choice and the SMTP password are not marked
   (UIX-035).
o) The API documentation opens in a new tab without a hint (UIX-037).

## Part 15: Requirements from practice

The requirements noted while using the application (catalogue,
stage 7 "Weitere Anforderungen": PRD-044 to PRD-046,
PER-035 to PER-037, PRJ-101 to PRJ-106, MAT-048 to MAT-052, VFG-030,
UIX-038, ADM-015, EML-046, and a fix recorded under VFG-023; PER-038 and
ADM-016 in stage 8; chapter 12.1; chapter 12.2 number 23). The
requirements and the answers to four questions are noted where they
decided something. The decisions below are those of the build, checked against the code.

### Scope: the built wishes are SOLL in stage 7, two notes go to stage 8

- **Service products stay, linked one-to-one to job functions and not
  selectable in the planning outside the crew planning.** Decided on the
  open note about removing service products and steering the personnel
  costs purely through the job functions: service products stay, as the
  price of exactly one job function (PRD-044).
- **Stage 7** gets every built wish as SOLL, in a block "Ausbaustufe 7:
  Weitere Anforderungen " at the end of each
  chapter of the catalogue, origin V.
- **Two notes are only recorded, as KANN in stage 9** (see Part 16), both decided as
  "only record": **ADM-016**, changing the address of the
  installation and renewing its certificate from the browser, and
  **PER-038**, freelancers quoting their own price in a request (the question was
  whether that is wiser for tax reasons; the catalogue records that
  an own price instead of a preset rate is one sign of self-employment,
  explicitly not as a legal assessment).
- **The answers that shaped the build:** a higher rate from a limit for
  "Preis und Kosten", counted **per day** (PER-035); services without crew
  such as a transport – which is an incidental cost, not a service, so
  products must stay – get a product kind
  of their own (PRD-045).
- **Decisions:** the tab and
  the title of the deployment view are **"Überblick"**; the PDF is named
  "Einsatzübersicht" (PRJ-104). The product form asks the **kind first**,
  then the category (PRD-046). The eight default job functions come with
  new installations and, on update, only to an installation without any
  job function (PER-037).

### Service products belong to their job function (PRD-044, PRD-045, PER-037)

- **One-to-one, never empty.** `JobFunction.service_product` is a
  `OneToOneField` (`PROTECT`, related name `job_function`).
  `JobFunction.save()` creates a missing product
  (`personnel.services.create_service_product`: the same name; main
  category D, or the first active main category presetting services – an
  installation with neither gets D "Dienstleistung", or "DL" with D taken;
  the next free article number; unit "Stunde"; by the hour; no price). The
  other way, `products.services.save_product` gives a new service its
  function (`check_service_function`, `link_service_function`), also in the
  import; a name a function already has, or one longer than 80 characters
  (the length of a function's name), is refused. Plain ORM code can still
  create a service without a function; the update turns such ones into
  Nebenkosten.
- **The two follow each other.** A rename carries over while both have the
  same name. Deleting a function deletes its product
  (`delete_job_function`); if either is in use, deleting is refused with
  the advice to deactivate the function. The product of a function cannot be
  deleted on its own (page and API) and cannot change its kind
  (`Product._check_service_kept`). The function form and the product page
  link to each other, and the list of functions links the product (PER-037).
- **No price yet is allowed** for a service product (the start data has
  none): its crew lines cost the customer 0, and the list of functions says
  "noch kein Preis".
- **Planned only with the crew.** `projects.services.check_plannable_as_material`
  refuses a service as a material line and names its function – on the
  page, through the API, in templates, the MVR import and when a line is
  duplicated; the product search of the planning leaves services out
  (`exclude_kind=service`), and a kit cannot contain one
  (`KitComponent.clean`). Material lines with a service
  keep their price (the maximum discount of the function included),
  and carry the hint "Dienstleistung – unter Personal planen"; copying a
  project or a group leaves them out, and applying a template leaves them
  out with a note. The lighting-plot import offers neither services nor
  Nebenkosten and ignores a remembered service.
- **The crew line shows its product.** It takes price, tax rate, billing
  and the hour tiers from the service product of its function
  (`crew.defaults_from_job_function`; the unit of a crew line follows from
  its billing: hour, day or flat) and shows its article
  number in the planning, the price overview, the documents and the API
  (`service_product_article_number`).
- **Nebenkosten** (`ProductKind.INCIDENTAL`, value `incidental`, PRD-045):
  no stock, never packed (not in `PACKABLE_KINDS`), never suggested by the
  MVR import (`NOT_EQUIPMENT`), planned like material, flat by default
  (`DEFAULT_BILLING_MODE`) – wherever material lines treat services
  specially, Nebenkosten are treated so too. The start data brings the main
  category N "Nebenkosten" (no stock, kind Nebenkosten, unit "Pauschal");
  a migration adds it unless a main category has the code N or that name
  (`masterdata/0006_incidental_071`). In the demo data F-001 "Transport
  Sprinter" is Nebenkosten, and the demo category F "Fahrt/Transport"
  presets them.
- **The migration** (`personnel/0010_services_071`): a shared product stays
  with the function of its name (or whose name it starts with,
  "Tontechnik" for "Tontechnik, Stunde"), else with the oldest function;
  every other function gets a copy with prices, billing, tax rate and
  maximum discount, named after the function. A function without product
  gets one, priced like the newest crew line of the function billed by the
  hour above 0, else 0. A service without function becomes Nebenkosten,
  and a main category presetting services whose products – at least one –
  are all Nebenkosten presets Nebenkosten. An installation without any job function gets the
  eight of the start data. `projects/0016_crew_071` then points every crew
  line to the product of its function; title, prices, billing and discount
  stay. On a fresh database the unused suggestions of
  `0002_suggested_job_functions` are removed and the start data creates
  the eight after `migrate`. Everything is in the change log as
  "Aktualisierung"; a second run changes nothing.
- **Start data** (PER-037, `personnel/defaults.py`, run by
  `install_defaults` after categories and tax rates): Techniker,
  Lichttechniker, Tontechniker, Medientechniker, Stagehand, Lager,
  Projektplanung, Sonstiges, each with its product in D, unit "Stunde",
  without price. The demo data uses these functions (Tontechniker with a
  limit of 10 hours, 55.00 from the limit and a guide value of 38.00 from
  the limit). Its check "the installation has data of its own" ignores
  service products – the eight of the start data would otherwise keep the
  demo data from loading.

### Hour tiers per day, billed by effort (PER-035, PER-036)

The requirement: a higher hourly rate above a limit (e.g. 10 hours); decided:
for price and costs, counted per day.

- **The limit is stored once, on the service product** (`hours_limit`,
  0.25 to 23.75 hours a day, and `price_above_limit`; both or none, and
  only for a service billed by the hour – `Product._check_hour_tiers`). A
  crew line copies both (`hours_limit`, `unit_price_above_limit`) as it
  copies its price (PRJ-015), and "Neue Preise übernehmen" takes over the
  limit too. In the crew dialog the two need the price right, the rate from
  the limit the right for personnel costs (`PRICE_FIELDS`, `COST_FIELDS`).
- **The cost of an hour beyond the limit:** the person's own rate from the
  limit (`PersonJobFunction.hourly_rate_above_limit`, fixed on the line as
  `CrewLine.hourly_rate_above_limit` when the person is assigned); else the
  person's own hourly rate; for an open place or a person without own
  hourly rate the guide value from the limit of the function
  (`guide_cost_rate_above_limit`), else its guide value per hour
  (`RateBook.rate`, `crew.price_crew_line`).
- **Counted per calendar day and per line**, never across a person's lines
  (`projects/hour_tiers.py`): by plan, the planned hours as they fall on
  each day while they are the length of the period (Monday 08:00 to Tuesday
  20:00: 16 and 20 hours) and hand-typed hours spread evenly over the days
  the period touches; by effort, the approved entries on the day they start
  (a night shift belongs to the day it began), the planned hours until
  then. Flat and per-day billing ignore the limit. Limit 10, 45.00 and
  55.00 from the limit, 12 hours on a day: 10 × 45.00 + 2 × 55.00 = 560.00.
- **No query more:** the tiers are arithmetic on what is loaded; the
  approved entries come with their day in the one query of
  `crew.approved_times`, also for the sum columns of the project list.
- **Shown everywhere a crew line is priced:** the planning ("davon 2 Std.
  über der Grenze"), the price overview and the documents ("davon 2 Std.
  über 10 Std. am Tag zu 55,00 €" in the details – the unit price is that
  up to the limit, the amount the sum of both, as the electronic invoice
  states it), and the API: on a crew line `hours_limit`,
  `unit_price_above_limit`, `normal_hours`, `hours_above_limit`, with the
  right for personnel costs `hourly_rate_above_limit`,
  `cost_hours_above_limit`, `cost_rate_above_limit`; on a product
  `hours_limit`, `price_above_limit` (price right) and `job_function`; on a
  job function `guide_cost_rate_above_limit`, `price` only when creating,
  `service_product` read-only (another value gives 400); on the rates of a
  person `hourly_rate_above_limit`.
- **By effort by default** (PER-036): a new service product is billed by
  the hour, and a new crew line of a product billed by
  the hour is billed "nach Aufwand" – the
  approved hours, until then the planned ones marked as an estimate. Flat
  stays flat, daily rental gives "je Tag". Lines created through the API follow the same default.

### Subrentals: the supplier, the status "offen", one page per supplier (PRJ-101, PRJ-106)

The requirements: the supplier as a text field with suggestions and the
option to create new ones, again by pop-up (the combination "angefragt" and
"no supplier" was possible and illogical); and correspondence and documents
must be storable for subrentals as well.

- **"offen" first and by default** (`SubrentalStatus.OPEN`): for a new
  subrental, in the dialog and in the API when no status is sent – also
  with a supplier. "Status beim Lieferanten" is called "Status". Every
  other status needs a supplier; the rule sits in `MaterialLine.clean`, so
  it holds for form, service and API alike, with the error at the status
  field. Copies – a duplicated line, a copied group, a duplicated project –
  start "offen" again. `projects/0017_subrentals_071`
  sets lines without supplier and another status, and subrental lines
  without any status, to "offen", in the history of their project.
- **The supplier field** is a reusable widget, `SupplierTypeahead`
  (`projects/subrental_forms.py`), over `projects:supplier_suggest`; its last
  suggestion "„…“ als neuen Lieferanten anlegen" opens
  `projects:supplier_quick_create`. Suggestions need read access to
  Projekte, Material or Einstellungen, creating write access to one of
  them (`may_create_supplier`). Supplier names are unique regardless of
  case.
- **A dialog over a dialog.** A type-ahead inside a dialog opens its
  "create" form in a second `<dialog id="create-dialog">` on top (`app.js`,
  block PRJ-101, event `typeaheadCreate`); saving closes only that one, and
  the line dialog keeps everything typed. The focus returns to the field a
  moment later, because Chrome otherwise ignores typing right after a
  dialog closes.
- **The supplier's address** (master data): `email` and `phone` are fields
  of their own; `contact` stays and names the contact person
  ("Ansprechpartner"); the API keeps `contact` and adds both.
  `masterdata/0007_suppliers_071` moves the first e-mail address and the
  first phone number (at least six digits, not after "Nr." or "Nummer") out
  of `contact`.
- **Documents of a supplier are project files** (`ProjectFile.supplier`,
  `PROTECT`, with `supplier_document_kind`: Angebot, Auftragsbestätigung,
  Lieferschein, Rechnung, Sonstiges) – also on the tab "Dokumente"; uploaded
  from the page they are not visible to the crew; a supplier's file without
  kind becomes "Sonstiges". A supplier with documents can only be
  deactivated, as one with subrental lines.
- **Mails of a supplier** (`ProjectMail.supplier`, `SET_NULL`,
  `mail/suppliers.py`): linked when a mail is fetched or sent and exactly
  one supplier's address stands in sender, To or CC (exact match; BCC does
  not count); a mail written from the page, or the answer to a linked
  mail, names its supplier directly; changed by hand on the mail's page
  ("Gehört zu einer Zumietung?") and through the API. The page also lists
  mails of the project from or to the supplier's address that are linked
  to nobody, in case the address was entered later. `mail/0006_subrentals_071`
  links the stored mails the same way. The mails stay in their project by
  its tag (EML-008).
- **The page "Zumietung bei …"** (`projects:subrental`,
  `projects/subrentals.py`, `subrental_views.py`) belongs to the tab
  Planung: the supplier's lines of the project with status and purchase
  prices, changed at once; the documents; the correspondence. Reading needs
  read access to the project, changing edit access to a project that is
  not closed; purchase prices, the mails and writing a mail each need their
  own special right (AUT-019, EML-029). It is reached from the subrental
  line in the planning, from Planung → Fehlbestände (supplier names are
  links; the new filter "Lieferant", `?supplier=`) and from the supplier's
  master data ("Zumietungen bei diesem Lieferanten anzeigen", which leads
  to that filter). There is no page of a supplier across projects.
- **API:** `GET /projects/{id}/subrentals`, `GET` and
  `PATCH /projects/{id}/subrentals/{supplier}`,
  `POST /projects/{id}/mails/{mail}/supplier`; `?supplier=` on mails and
  files; `supplier` and `supplier_document_kind` on files; `supplier` when
  sending a mail; `email` and `phone` on `/suppliers`.

### Material: suggestions, power, new items, a product from a model, Hauptlager (MAT-048 to MAT-052, PRD-046)

- **Manufacturer, "Gekauft bei", product** (MAT-048, MAT-050): text fields
  with suggestions (`material:manufacturer_suggest`, `supplier_suggest`,
  `product_suggest`, template `material/_name_typeahead.html`). The typed
  name is the value, so the field works without JavaScript; a new name is
  created when the form is saved – no dialog, unlike the supplier of a
  subrental –, and the last suggestion marks it "neuer Hersteller" or
  "neuer Händler". An existing record of that name is reused regardless of
  case, even an inactive one (`material.services.manufacturer_named`,
  `supplier_named`). The product field offers rental and sale products
  from an endpoint of its own, apart from `products:suggest`. The item's edit form has the
  supplier field and the invoice number as well.
- **The power in one place** (MAT-049): `MaterialModel.power_w` (W) on
  every model, next to weight and dimensions. Creating a category field of
  the type number labelled "Leistung" or "Power" in W or Watt is refused
  (`masterdata.models.is_power_field`, `CategoryField.clean`). The
  start data gives L "Licht" no field "Leistung".
- **Labels, not fields:** "Spezifikation" is "Beschreibung" and "Tag des
  Kaufs" is "Rechnungsdatum" wherever shown, list columns and import labels
  included; the fields and API names `specification` and `purchase_date`
  stay, and the import also knows the old column headings.
- **New items** (MAT-050, `material.services.create_items`): "Start-ID" –
  a start ID that is taken is refused, not skipped; the following items get
  the next free IDs after it (`following_free_numbers`), and the counter
  moves behind the last one used. One serial number per item: more
  serial numbers than items, or the same one twice in the batch, is
  refused; one the model has already only warns (MAT-004). The
  API takes `start_number` and `serial_numbers` on
  `POST /material-models/{id}/items` and has `invoice_number` on items.
- **"Als Produkt anlegen"** (MAT-051, `create_product_from_model`, view
  `material:model_create_product`, `POST /material-models/{id}/create-product`):
  a sale product if the category presets sale, else a rental product, at
  price 0, with the category's presets and the model assigned. It needs
  write access to products and then opens the product form for users with
  the price right, otherwise the product page. Customer material gets a
  link to the product form instead, which asks for the owner.
- **Kind before category** (PRD-046): choosing the kind reloads the form of
  a new product (`?kind=`); choosing the category keeps kind and owner.
  Categories whose preset kind matches come first, in a group of their
  own; the chosen kind beats the category's preset, and the billing mode
  follows the kind unless the category presets that same kind
  (`products.services.presets_for_kind`). "Vorhandenes Modell zuordnen"
  (`material.services.assign_model_to_product`) offers only models without
  product, needs write access to material, refuses a model that has a
  product and a product of a kind without stock, and shows the hint of
  PRD-032 for a model of another main category.
- **The default storage location** (MAT-052, `StorageLocation.is_default`):
  at most one (`save()` takes the mark from the others), never a
  deactivated one (`clean()`). A new installation gets "Hauptlager" only if
  there is no storage location at all. The form "Neue Exemplare" preselects
  it; import and API do not. It is chosen with "Standard für neue
  Exemplare" in the storage-location settings, and the administration page
  names it. `masterdata/0008_storage_071` makes an active top-level
  "Hauptlager" (case ignored) the default, creates "Hauptlager" where there
  is no location at all, and otherwise leaves the choice to the user.
- **A bug fixed on the way:** the edit pages of a model and an
  item did not show weight, dimensions, further category fields, the
  item's own description or its own category values, so saving them in the
  browser emptied those values.

### Zeitplanung, tabs, timelines, personnel plan, filters (PRJ-102 to PRJ-104, VFG-030, VFG-023, UIX-038)

- **Zeitplanung without the box "Veranstaltungsort"** (PRJ-102): the venue
  with its notes stays in the head of the project, its form and the
  Überblick.
- **A timeline of the project on the Zeitplanung** (PRJ-103,
  `schedule/course_timeline.py`, `templates/schedule/_course_timeline.html`):
  the rental period in its status colour, the event, one row per phase,
  one row per person (the bar names the job function; colours of the
  personnel plan, `crew_bar_css`), one row per job function for open
  places (yellow, hatched). It reuses the columns, the navigation and the
  loading while scrolling of Planung → Zeitstrahl, and builds its rows from
  the phases and crew lines the page loads anyway – no query of its own.
  Without an address it opens on the rental period: up to 10 days in hour
  columns, a longer project in weeks (at most 12); a link with `from` only
  keeps that kind of columns. Nothing goes into the session, unlike the
  planning pages: the project decides what is worth seeing. Requested
  crew: a dashed band, as in the personnel plan; declined (new): red
  hatched and struck through. Tooltips name person, function, period and
  request status; names link to the person only for users who may read
  Personal. The open items stay on top (`id="open-items"`), because many
  links lead there; the timeline follows, then the phases.
- **Tabs** (PRJ-104): Planung, (Teilprojekte), Preisübersicht, Dokumente,
  Zeitplanung, Packliste, Korrespondenz, Überblick, Zugriff, Verlauf. The
  tab is the msgid "Overview" with the context "project tab". The address (`projects:deployment`) and the PDF
  "Einsatzübersicht" stay, so bookmarks keep working.
- **Bars that end visibly** (VFG-030): every bar of a project status or a
  deployment has a 1 px frame in its colour – grey in `--ink-soft`, yellow
  in `--yellow-ink` –, at least 3:1 against the panel in both themes (WCAG
  1.4.11, measured in `tests/browser/test_071_planning_in_browser.py`);
  phases, absences, blocks and availability are framed too. Cancelled bars
  are pale and struck through. Labels end
  with "…" (`overflow: clip`, not `hidden`: the bar does not become a
  scroll container, so the text of a bar that began left of the view still
  sticks next to the names); the tooltip holds the whole text. No new
  colour tokens.
- **The personnel plan shows everybody** (VFG-023;
  PER-025 mentions it): with "Nur Personen mit Einsätzen oder Abwesenheiten"
  unticked every active person is in the plan, office accounts without job
  function included, and `GET /personnel-plan` does the same (API-002).
  The people come from `schedule.services.people_in_plan`.
  The choice lists of the crew forms and "Wer ist frei?" keep PER-025.
- **Filters folded on every width** (UIX-038): the CSS folds the panel
  before the script looks, at any width; a filter with an error is never
  folded.

### Settings, mailboxes, follow-up (ADM-015, EML-046, PRJ-105)

- **"Antwort auf Einsatzanfragen"** (ADM-015) is the field `crew_answers` of
  `core.forms.SystemSettingsForm` on Einstellungen → Firmendaten und
  Grundeinstellungen, read from and saved to `MailSettings.crew_answers`,
  where it stays; the page names the mailbox the answers go to;
  Einstellungen → E-Mail only shows the value with a link there. Changing
  it needs write access to the settings, like everything on that page. `/mail/settings` in the API is
  unchanged and still needs write access to E-Mail.
- **Every mailbox can be deleted** (EML-046, `mail.mailboxes.delete_mailbox`).
  Mails and mail log store the mailbox's name (`mailbox_name`): it follows a
  rename while the mailbox exists – sorting and searching the log need no
  join – and stays when the mailbox is deleted; the foreign keys are
  `SET_NULL`, and the log then shows "Name
  (gelöscht)" (`mailbox_label`). Waiting mails (`UnknownTagMail`) stay
  `CASCADE`: they cannot be fetched from a deleted mailbox, so they leave
  Projekte → Anfragen and stay on the server. `mail/0007_mailboxes_071`
  copies the names onto the stored rows; it changes no business data and
  writes no change-log entry.
- **The sending role:** "exactly one active correspondence mailbox sends"
  stays. If only one other mailbox can send, it takes over by itself and
  the page says so; with several, the confirmation asks which one
  (`?successor=` in the API); if none can, deleting is refused with the
  reason. The other roles simply go – system mails then use the
  configuration file.
- **A confirmation page** (`deletion_of`, `templates/mail/mailbox_delete.html`)
  instead of the script's `data-confirm`: it lists the facts – mails, log
  entries, waiting mails, roles, the answers to requests – and works
  without the page script. Switching off stays: "Nur ausschalten" on that
  page, the checkbox in the form, `PATCH is_active`
  (`switch_off_mailbox`). `DELETE` answers 204; a log entry in the API has `mailbox_name` and
  `mailbox_deleted`.
- **"Wiedervorlage"** (PRJ-105, `projects/follow_up.py`,
  `follow_up_views.py`): four fields on `Project` – `follow_up_on`,
  `follow_up_note`, `follow_up_user`, `follow_up_notified_at` –, not
  editable through the project form or `PATCH /projects/{id}`; set through
  the dialog or `PUT /projects/{id}/follow-up`, removed by "Erledigt" or
  `DELETE` (not a deletion of anything), with edit access, in every status –
  a closed project too, since it does not change the planning. The person
  must be active and able to open the project; by default it is whoever
  sets it. The changes are in the history; `follow_up_notified_at` is
  bookkeeping and stays out of the change log.
- **Notified once:** the minute timer (`run_jobs`,
  `follow_up.notify_due_follow_ups`) tells the person from 06:00 local time
  on the day, a missed day at once. A new day or another person notifies
  again; a new note does not. When the person is deactivated, the project
  manager is told. The new kind "Wiedervorlage eines Projekts"
  (`follow_up`) goes by e-mail by default.
- **Who sees it:** the head of the project shows it to everyone who reads
  the planning (`project_for` loads the person in the same query). The
  filter of the project list – "fällig", "für mich", "alle mit
  Wiedervorlage", across every status like a search –, the note under the
  name and the column "Wiedervorlage" show only to users who may see
  customers, so the crew sees nothing. The start page lists the user's own
  follow-ups from their day on ("Deine Wiedervorlagen", at most 8);
  "Erledigt" only with edit access.

### An impossible day in the address (UIX-004)

Added after the independent check. `/projects/?since=2027-02-30` – well formed, but no
real day – ended in a server error: Django's `parse_date` raises
`ValueError` for such a day. `core.listing.query_date`, and
`query_datetime` for a moment, give `None` instead, so a hand-edited link
filters nothing rather than failing. They are used by the project list
(`since`, `until`), the planning pages (`from`, `week`), the times
(`week`), the change log (`since`, `until`) and the availability check of a
line (`start`, `end`); `tests/ui/test_071_lead_pages.py` opens each.

### Not built

- **PER-038 and ADM-016**, recorded for stage 8 (stage 9 since catalogue
  0.21, see Part 16).
- **Services:** the CSV of the price overview has no split of the hours;
  the hint of PRJ-072 points out a changed price, not a changed limit or
  price from the limit; the column "Ab der Grenze" on the page of a person
  shows for every function; a database that had job functions without
  product outside the migration was not tried.
- **Subrentals:** a subrental line with a supplier but without status keeps
  the empty status (the page shows "–"). A customer or venue type-ahead
  moved into a dialog would open its "create" form on top as well, but its
  form would need `hx-target="this"`. No page of a supplier across
  projects.
- **Material:** no power per item; choosing kind or category reloads the
  form of a new product, so text typed before is lost (as with the
  category before).
- **Planning:** a very short bar shows only "0…" or "2026-…"; the whole
  text is in its tooltip.
- **Settings:** no follow-up in the demo data and no time of day for a
  follow-up; the page of a mail still does not name its mailbox.

### Assumptions to confirm

For the catalogue, chapter 12.2 number 23:

a) Existing material lines with a service stay, with their
   documents, and carry a hint; a shared service product stays with the
   function of its name, else the oldest; the copies are named after their
   function; everything the update creates, copies or turns into
   Nebenkosten is in the change log (PRD-044).
b) A category presets Nebenkosten when all its products became Nebenkosten
   in the update; N is added only where neither the code N nor the name
   "Nebenkosten" exists (PRD-045).
c) "Vorhandenes Modell zuordnen" offers only models without product; a
   model of another product is not moved there (PRD-046).
d) The limit counts per calendar day and line, not per deployment, and
   only for "nach Plan" and "nach Aufwand". An hour beyond it costs the
   person's own rate from the limit, else the person's own hourly rate;
   without own hourly rate the function's guide value from the limit,
   else its guide value per hour (PER-035).
e) "Nach Aufwand" is the default of new crew lines, also through the API;
   existing lines keep their billing (PER-036).
f) The eight functions come with new installations and, on update, only
   without any job function; their products have no price yet (PER-037).
g) "Offen" means not yet asked; the update sets subrentals without
   supplier to "offen"; the supplier of a line whose status is not "offen"
   cannot be removed without setting the status back (PRJ-101).
h) Purchase prices and correspondence show on the subrental page only with
   their rights; mails appear there by the supplier's address and stay in
   their project by its tag (PRJ-106).
i) The venue stays in the head and the form; the address of the Überblick
   is that of the former tab "Einsatz" (PRJ-102 to PRJ-104).
j) A follow-up is notified once, on its day; "Erledigt" removes day, note
   and person together (PRJ-105).
k) The bars were checked with screenshots in the dark and the light theme
   (VFG-030).
l) Unticked, the personnel plan shows every active person, office accounts
   included; choice lists and "Wer ist frei?" keep PER-025 (VFG-023).
m) The choice remembered per list and device wins; a list with an error in
   its filter is open; without JavaScript every filter shows (UIX-038).
   (See Part 18: nothing is remembered any more.)
n) Without a start ID new items get the next free IDs; a serial number the
   model has already only warns; a supplier typed under "Gekauft bei" is
   created with its name alone; "Als Produkt anlegen" makes a sale product
   where the category presets sale, else a rental product (MAT-048 to
   MAT-051).
o) The update makes a top-level "Hauptlager" the default, creates one only
   where there is no location at all, and otherwise leaves the choice open;
   existing items keep their location (MAT-052).
p) "Antwort auf Einsatzanfragen" is stored where it was; `/mail/settings`
   reads and changes it as before (ADM-015).
q) Mails and mail log keep the name of a deleted mailbox, their link to it
   becomes empty; without a system mailbox system mails go through the
   configuration (EML-041); without a sending mailbox no mail can be sent
   from a project (EML-046).

## Part 16: Stage 8

The extension requested after a review of the open items of stage
8 (catalogue, stage 8 "Service, Karten, Zuschläge":
PRJ-050, PRJ-089, PRJ-090, UIX-010, VFG-026, UIX-033, UIX-034, PRJ-097,
ADM-013, DOK-014, NFA-070, PER-009, ZEI-018, ZEI-019; chapter 12.1
"Ausbaustufe 8 "; chapter 12.2 number 24). The
requirements and the answers to four questions are noted where they decided
something. The decisions below are those of the build, checked against
the code.

### Scope: stage 8 is these 14, the rest moves to stage 9

- **The requirements:** projects – divide a project into subprojects afterwards,
  dummy projects as a ticket system, common show files as project files,
  a chat in the project; planning – drag appointments in the timeline;
  maps – route link to Google Maps, a zoomable map, automatic trip routes;
  automations with triggers, e.g. an acknowledgement of receipt; invoices
  that can be switched off; operation – Raspberry Pi; personnel –
  surcharges (night, Sunday and holiday), expenses and hints for
  conspicuous times.
- **Stage 8 has exactly these 14 requirements,** each
  SOLL and rewritten where it stands, its origin letter kept. The other 29
  requirements of the former stage 8 – 20 KANN items of the old stage 6
  (AUT-007 among them), the two (EML-040, AUT-029), five
  notes and the two (PER-038, ADM-016) – move as KANN to
  a new stage 9 "Weitere Erweiterungen". The statements of Parts 14 and 15
  that name "stage 8" for KANN items mean this stage 9 now).
- **The four answers:**
  - Maps: OpenStreetMap, and a link to Google Maps for routes – a
    zoomable OpenStreetMap map; a route is a link into Google Maps. No
    routing service, no distances: PRJ-097 (determining trip routes
    automatically) became the trips of a project, each with a route link.
  - Surcharges for night, Sunday and holidays: for **price and costs**,
    like the hour tiers (PER-035).
  - Raspberry Pi: **Ubuntu Server for the Pi and also Raspberry Pi OS**
    (Debian 13).
- **Decisions:**
  - A map loads only after a click ("Karte anzeigen"), so that no address
    and no tile request leaves before (NFA-050); a setting ("Karten sofort
    laden") makes maps load at once. Coordinates come from Nominatim,
    asked by the server once per address and stored; tiles come from the
    OpenStreetMap tile server in the browser. Both addresses are settings
    of the configuration file, so an own server can be used; attribution
    "© OpenStreetMap-Mitwirkende".
  - Chat: one per project, read and written by everybody who can open the
    project – the crew with the deployment view included; the chat says
    so.
  - Dummy projects as a ticket system become **Servicefälle**: a kind of
    project for service cases.
  - Surcharges: defaults after the tax-free rates of § 3b EStG, every value
    changeable.
- **A correction to the requirement:** the first draft had 24 December from
  14:00 at 125 %. § 3b (1) Nr. 4 EStG gives it 150 %, like 25 and 26 December and
  1 May; 31 December from 14:00 has 125 % like a holiday (Nr. 3). The code,
  the catalogue (PER-009, 12.2 number 24 j) and the manual use the law.

### Subprojects afterwards, service cases, show files (PRJ-050, PRJ-090, PRJ-089)

- **One step for both cases** (PRJ-050). "In Teilprojekte gliedern" (a
  project without parts) and "Teilgruppen in Teilprojekte umwandeln" (a
  whole project) are the same page, `projects:split`
  (`/projects/<number>/split/`), behind the arrow next to "Teilprojekt
  anlegen" in the head; the API is `GET`/`POST /projects/{id}/split`. The
  service is `projects.split.split_into_subprojects`, the plan the page
  and the API show `split_plan`. This differs from Part 10, which
  had PRJ-050 as KANN: a project can be divided afterwards; `parent` still
  cannot be changed through `PATCH /projects/{id}`.
- **What a new part gets:** each chosen top-level group becomes a part
  numbered `…-1`, `…-2` (PRJ-044), named like the group, with the
  project's rental period, event period, rental days and status (an
  inquiry stays an inquiry), and the presets of a new part (contact,
  venue, project manager – `services.create_subproject`).
- **The group dissolves – or stays.** Normally its lines stand without a
  group in the part, its subgroups become the part's groups. It stays as
  the one group of the part if it has a discount or flat price, own rental
  days, "optional"/"alternative", a description, or a surcharge refers to
  it – so no price changes. Subrentals that cover a shortage go with the
  line they cover (PRJ-054); packing records without progress and packlist
  assignments of moved lines are deleted.
- **Crew:** crew lines are in no group (PRJ-038), so the page asks per
  line: stays at the whole project or goes with a chosen group. A line
  that goes takes its time entries along, and its phase – which stays at
  the whole project – is copied into the part. Documents, mails, files,
  phases, open items and the follow-up stay at the whole project.
- **Refused:** for a part or a service case; in the statuses out,
  returned, closed and cancelled (`SPLITTABLE_STATUSES`); for a group with
  packed, issued or allocated material; for alternatives or surcharges
  that would point across the new boundary (PRJ-083, PRJ-058). A
  surcharge on "the whole project" or "personnel" is only a warning: it
  stays at the whole project and from then on counts less.
- **The trace:** the moves are bulk updates with the project row locked
  (`select_for_update`); the change log has the event "In Teilprojekte
  gegliedert: …" at the whole project, an event per part
  (`project.split_part`), the parts as created and a dissolved group as
  deleted. *Rejected:* one save per line – the history of a 500-line
  project would drown in it.
- **A service case is a project with `kind=service_case`** (PRJ-090,
  `projects/service_cases.py`). It takes the next project number, has the
  mail tag and the correspondence of a project, files, open items, a
  follow-up, access and history. *Rejected:* a model of its own – it
  would need its own number range, tag, correspondence and rights.
  - Its statuses are `case_status` open, in progress, done, in any order;
    `Project.status` stays "inquiry" and `change_status` refuses cases.
  - The person responsible is `manager`; a newly responsible person is
    told in the application with the existing kind "Änderung eines
    Projekts" (`project_change`).
  - The customer is optional; "Gemeldet von" (`case_contact`) covers
    people who are no customers. The rental period, which a project must
    have, is a hidden one-hour stand-in (`stand_in_period`).
- **Where a case appears:** it can have no material lines, crew lines or
  parts (`services.ensure_plannable`). It is left out of the calendar,
  the timelines, the calendar API, the project list, `/api/v1/projects`
  (unless `?kind=` is given) and "coming projects" on the start page; it
  is in the search ("Servicefall"), the open items, the follow-ups and its
  own list Projekte → Servicefälle (filters status, mine, text). The start
  page shows "Meine Servicefälle". Its tabs are Servicefall, Dokumente,
  Korrespondenz, Chat, Zugriff, Verlauf.
- **From an inquiry:** "Als Servicefall anlegen" on Projekte → Anfragen,
  only for mails without tag and with the right to write e-mail. The case
  is created and the mail taken in, or nothing happens
  (`create_from_inquiry`: one transaction around `create_case` and
  `assign_unknown`). The subject becomes the name; a sender known as a
  contact brings customer and contact.
- **Conversion:** "In Projekt umwandeln" uses the project form – customer
  and rental period are required now; number, mails, files and history
  stay; the project starts as an inquiry (`convert_to_project`, event
  `service_case.converted`). The API is `/service-cases` with `convert`;
  webhook payloads of projects carry `kind`.
- **Show files pass by their ending** (PRJ-089, `core/showfiles.py`,
  `core.uploads.document_type_allowed`), compound endings like `.show.gz`
  included. Endings confirmed in manufacturer documentation: ETC (`.esf`,
  `.esf2`, `.esf3d`, `.csf`, `.lsf`, `.asc`), Hog 4 `.shw`, MagicQ
  `.shw`/`.sbk`/`.xhw`/`.mpr`, DM7 `.dm7f`, LA Network Manager
  `.preset`/`.system`; the others are from practice (grandMA3 `.show`,
  grandMA2 `.show.gz`, Titan `.avo`, Resolume `.avc`, WATCHOUT `.watch`,
  QLab `.qlab4`/`.qlab5`, Millumin, DM3 `.dm3f`, CL/QL `.clf`, TF `.tff`,
  X32/M32, DiGiCo `.ses`, d&b R1 `.dbpr`). Shows that are folders go up as
  ZIP. Nothing executable is accepted, and every project file except PDF,
  pictures and text is handed out as a download. *Rejected:* checking the
  content – the formats are closed and differ by version.
- **The document type "Showfile"** (`DocumentType.is_showfile`,
  `masterdata/0009_showfiles_080`) is visible to the crew; a show file
  notes "Pult oder Software", the version and "aktuelle Show". A new
  upload of a console becomes its current show (`showfiles.mark_current`,
  one save per file, so the change log has each). Type and console are
  filled from the ending on the server and in the browser; `.shw` is
  ambiguous and chosen by hand.
- **The size limit is unchanged:** "Größte Datei zum Hochladen" (default
  50 MB, at most 500; NGINX allows 510 MB). The upload form names it. A
  show with media goes up as ZIP within that limit.

### The chat of a project (UIX-010)

- **A tab, not a panel.** "Chat" sits between "Korrespondenz" and
  "Überblick", for everyone with at least the deployment view – the crew
  included (AUT-018, AUT-025). Each subproject has its own chat. Writing
  is allowed in every project status. The page says who reads along
  ("… Personen lesen mit", `chat.services.readers_of`, which applies the
  rules of `projects.access` to all users at once in four queries).
- **No websockets** (NFA-029: no further service). The unread badge comes
  from the change polling of UIX-020: every project page also watches
  `chat:<pk>`, whose stamp is `<content>~<unread>` (`chat.services.stamp`,
  one query). The chat page fetches its messages in place when the
  content part moves (every 20 s, no faster), keeps what is being typed
  and leaves a message alone while it is being changed. *Rejected:* a
  faster poll of the chat page – 20 s is what every page already costs.
- **Messages are not business data:** not in the change log, and a new
  message never reloads the other project pages – `chat:` keys are left
  out of the reload check in `app.js`.
- **Changing:** the author may change or delete a message for 15 minutes
  (`EDIT_MINUTES`); a changed message says "geändert".
- **Mentions:** `@Vorname Nachname` or `@username`; the longest name wins
  and blocks its place, and only people who can read the chat can be
  mentioned (`mentioned_in`). A changed message notifies only the newly
  mentioned. The kind `chat_mention` goes in the application and by
  e-mail by default, switchable per user.
- **API rights:** writing needs only read access to projects – the crew
  writes too; a read-only token only reads.
- **Anonymising a person** (NFA-009) replaces the author's name on the
  messages (`forget_author`).

### Automations (ADM-013)

- **One action per rule.** Several actions for the same event are several
  rules. Triggers: a mail without project tag arrives (an inquiry,
  optionally only in one mailbox), a project reaches a status (also on
  creation), an answer to a deployment request arrives (acceptance,
  refusal or either), a follow-up is due. Actions: answer the mail (only
  for the inquiry trigger), notify a person, note an open item (only for
  project triggers). Notify recipients: a chosen user, the project
  manager, whoever asked for the deployment, or whom the follow-up is for
  (`ACTIONS_OF`, `RECIPIENTS_OF`; `Automation.problems` checks browser and
  API alike).
- **Where events are caught:** project status and crew answers by
  `post_save` signals (`automations/signals.py`), so every path counts –
  browser, reply mail, packing, API; the old values come from the change
  log's snapshot at no cost. Inquiries in `mail.fetching`, follow-ups in
  `follow_up.notify_due_follow_ups`.
- **When runs execute:** recorded in the transaction of the change (a
  rolled-back change runs nothing), carried out right after commit
  (`transaction.on_commit`); the minute timer (`run_jobs`) takes what was
  left waiting. A run is claimed before it is carried out, so two
  processes never take the same; an interrupted run is marked failed and
  never repeated, so nothing is sent twice. A unique constraint on rule
  and event key (`automation_run_once`) keeps the same event – the same
  mail in two mailboxes – from running a rule twice.
- **Where the answer goes:** through the mailbox the mail arrived in, else
  the one that sends the correspondence; to `Reply-To` if present, else the
  sender. Headers `Auto-Submitted: auto-replied`,
  `X-Auto-Response-Suppress: All`, `In-Reply-To`/`References`, and the
  EML-045 footer. Logged in the mail log as "automatische Antwort"
  (`MailLogEntry.kind` `automatic`).
- **Never answered:** mails marked automatic (`mail.parsing.automatic_reason`:
  `Auto-Submitted` other than "no", `Precedence` bulk/junk/list/auto_reply,
  `List-Id`, `List-Unsubscribe`, `X-Autoreply`, `X-Autorespond`,
  `X-Auto-Response-Suppress`, an empty `Return-Path`, a delivery report);
  senders that are mailer-daemon, postmaster, no-reply, bounce and similar,
  or any own address (mailboxes, system sender, company address); a sender
  this rule already answered today (local calendar day). Every left-out
  run is logged with its reason.
- **This deliberately departs from EML-030** ("keine automatischen
  Antworten auf eingehende Mails"), which the catalogue now names with two
  exceptions: the answers to deployment requests (Part 13) and
  the automations. Part 13 calls the crew answers "the
  one automatic reply to incoming mail"; there are two now.
- **Rights:** module "Einstellungen" (administration) – read to view,
  write to change or delete; the API the same (`/automations`,
  `/automations/runs`).
- **Runs are kept 365 days** (`RUN_RETENTION_DAYS`, daily maintenance)
  and keep the rule's name after it is deleted. Deleting a mailbox
  switches off the rules bound to it first – otherwise they would answer
  every mailbox (EML-046).
- **The default answer text uses "Sie"**: it goes to customers, like the
  document templates; the interface stays in du-form.
- **Anonymising a person** replaces the name in the runs and empties their
  stored placeholder values (`engine.forget_name`).

### Route links, maps and trips (UIX-033, UIX-034, PRJ-097)

- **Positions are stored per address text, not per record:** one table
  `core.AddressPosition`, keyed by the SHA-256 of the normalised address
  (`maps.address_key`). Venues, customers, suppliers, the company and
  free-text places of phases and projects share a position when the
  address is the same; a correction by hand holds everywhere; a changed
  address simply has another row. *Rejected:* coordinates on every record
  – five tables, five forms, and the same place looked up five times.
- **Nothing leaves before the click** (NFA-050): Nominatim is asked by the
  server only after "Karte anzeigen" (or with "Karten sofort laden"), at
  most 5 addresses and 15 s per opening, one request per second across
  all workers (a lock file in the data directory), with a User-Agent
  naming Rentalars, no redirects followed. Every answer is kept, "not
  found" too; network errors are shown on the map and not stored. There is
  no address suggestion while typing: Nominatim's usage policy forbids
  autocomplete (VFG-025 has none either).
- **Content security policy:** only pages that can show a map allow
  images from the tile server (`request.csp_image_sources`, set by
  `{% map_box %}`); Leaflet is loaded from this server only when a map is
  first shown. "Nothing is loaded from other servers"
  (architecture, "The user interface") holds for scripts, styles and fonts;
  map tiles are images from the configured tile server, after the click.
- **Leaflet 1.9.4** (BSD-2-Clause, from npm) is bundled in
  `static/vendor/leaflet/`; `scripts/check_licenses.py` now also checks
  files in sub-folders (its pictures).
- **Correcting a position:** "Position korrigieren" – click into the map,
  drag the marker or type latitude and longitude (the keyboard way); "Neu
  suchen lassen" forgets it. It needs the right to change the record the
  map belongs to (for a project: edit access) and is an event of that
  record; `AddressPosition` itself is a cache and not audited.
- **Map servers:** the `[maps]` section names `tile_url`, `geocoder_url`,
  `attribution`, `attribution_url` and `max_zoom`. An empty `tile_url`
  switches maps off and keeps the route links; an empty `geocoder_url`
  leaves positions to be set by hand.
- **Route links:** `https://www.google.com/maps/dir/?api=1&…`, at most
  nine waypoints, in a new tab with `noreferrer`. Venue, supplier and
  delivery addresses start at the warehouse; the billing address, the
  company and the venue in the Überblick start where the viewer is.
- **Trips** (`projects/trips.py`) come from the phases Aufbau and Abbau
  (warehouse → venue and back, two trips each) and Packen and
  Nachbereitung (one round trip warehouse → every pickup supplier →
  warehouse). Without a Packen or Nachbereitung phase, pickup and return
  happen at the start and end of the subrentals. The venue is taken in
  this order: venue of the phase, venue of the project, place typed into
  the phase, venue typed into the project, delivery address. Optional and
  alternative lines are left out. No distances. Shown on Zeitplanung (with
  hints about missing addresses) and on Überblick for the crew (without
  them); `GET /projects/{id}/trips`.
- **"Wird beim Lieferanten abgeholt"** is a flag per subrental line
  (`MaterialLine.picked_up_at_supplier`), set on the page "Zumietung bei
  …" (column "Abholung"), in the line dialog and through the API.
- **The warehouse** is `CompanyProfile.warehouse_address` ("Anschrift des
  Lagers"), empty: the company's address. Suppliers have an address of
  their own now (street, postal code, city, country); addresses noted in
  "Kontakt" or "Notiz" are not moved – unlike an e-mail address there is
  no reliable pattern for an address.
- **Clean-up:** positions of an anonymised customer are deleted at once;
  positions of addresses nobody uses any more go in the daily maintenance
  (`delete_unused_positions`).

### Surcharges for night, Sunday and holidays (PER-009)

- **A page of its own, Einstellungen → Zuschläge** (`core:time_surcharges`,
  `core.TimeSurchargeSettings`), rather than the Firmendaten: 16 values
  plus the computed holidays of this year and the next, so they can be
  checked. The word: "Zuschläge" (msgid "Surcharges", context "time
  surcharge"); "Aufpreis" stays the product kind `surcharge`, and in the
  code the new things are `time_surcharges`.
- **Two switches, both off by default,** on new and existing
  installations: "Zuschläge im Preis für den Kunden" (`on_price`) and
  "Zuschläge in den Personalkosten" (`on_costs`). Whether customers pay
  surcharges is the company's decision, the federal state has to be chosen
  anyway, and running offers stay unchanged.
- **Each crew line keeps its own two switches**
  (`time_surcharges_on_price`, `time_surcharges_on_cost`), set when it is
  planned from the settings and its service product
  (`crew.defaults_from_job_function`); the planner can change them in the
  dialog – the price switch needs the price right, the cost switch the
  right for personnel costs. Switching the settings never changes lines
  already planned; older lines have both off. Percentages,
  night window, holidays and the before-midnight rule apply live to every
  line with surcharges, closed projects included; stored documents stay as
  they are.
- **A service product can exclude its lines** (`Product.time_surcharges`,
  price right) – a night watch or a flat service.
- **Defaults follow § 3b EStG, every value changeable, 0 means none:**

  | Kind | Default |
  |---|---|
  | Night 20–6 | 25 % |
  | Night 0–4, if the work began before midnight | 40 % |
  | Sunday | 50 % |
  | Holiday, and 31.12. from 14:00 | 125 % |
  | 24.12. from 14:00, 25./26.12., 1.5. | 150 % |

- **The before-midnight rule (§ 3b (3))** is a setting, on by default: 40 %
  from 0 to 4 o'clock, and a Sunday or holiday reaches until 4 o'clock of
  the next day. "Began" is the start of the line's period or of the time
  entry. It answers the question left open in 12.2 number 24 j).
- **How kinds combine** (§ 3b (1) "vorbehaltlich", R 3b LStR): night adds
  to the day kind; of Sunday, holiday and high holiday only the highest
  percentage counts. A holiday on a Sunday at 22:00 is 25 % + 125 %.
- **Holidays** (`core/holidays.py`): computed, no package, no network; one
  federal state for the whole company, not per venue; no choice means the
  nationwide holidays only. Variants for Bavaria with or without
  Assumption Day, the city of Augsburg, and the Saxon and Thuringian
  communities that keep Corpus Christi; Easter and Whit Sunday are
  holidays only in Brandenburg. The law as of 2026, changes since 2017
  included. *Rejected:* a holiday package – one more dependency for one
  table per state.
- **Which hours count:** by plan, the planned period cut at every
  boundary, hand-typed hours spread over the calendar days as PER-035
  spreads them, then in proportion within each day; by effort, each
  approved time entry with its break taken off in proportion. Real
  elapsed hours: the night into summer time is an hour shorter.
- **With hour tiers (PER-035):** the hours beyond the limit are the last
  ones of the day, and their surcharge is a percentage of the price or rate
  from the limit. For the actual cost the base is the rate fixed on the
  entry, or the rate from the limit beyond it.
- **Scope:** only lines billed by plan or by effort, as the hour tiers; no
  cost surcharges when the person has a flat rate (`cost_flat_rate`). The
  line discount applies to the surcharges as well (they are part of the
  base amount).
- **Where it shows:** the planning ("inkl. Zuschläge …" under amount and
  cost, one kind per part), the price overview and its CSV, the documents
  ("inkl. Zuschläge 126,00 €: Nacht 25 % auf 4 Std. …" in the details;
  the amount includes them), the API (`time_surcharges` per crew line,
  `totals.personnel_time_surcharges`), `GET`/`PATCH /settings/surcharges`
  (module Einstellungen) and `GET /holidays?year=&state=` (anyone logged
  in).
- **Queries:** the settings are read at most once per calculation and only
  when a line needs them (`crew.surcharge_rules_for`); a new crew line
  reads them once per request. The API enum of the states is
  `FederalStateEnum`; the availability enum keeps its old name `StateEnum`
  (`SPECTACULAR_SETTINGS`), which the new field `state` would otherwise
  have renamed.

### Hints at times, expenses (ZEI-018, ZEI-019)

- **A working day, not an entry** (ZEI-018, `timetracking/hints.py`).
  Entries store one number of break minutes, not when the break was taken,
  so a working day is judged as a whole: its hours of work are those of
  its entries, its break the recorded minutes plus gaps of at least 15
  minutes between them (ArbZG § 4). The next entry joins the day unless
  the gap is at least the rest limit (11 h), or at least 3 h and it starts
  on a later date – so a night shift is one day, and a load-in in the
  morning and the show in the evening are one day.
- **Plain values, found by the measurement** (NFA-012). The first version
  read the entries around the asked ones as model objects and recomputed
  the end of a working day for every entry; the report of a full month
  took up to 1,059 ms on the measuring machine. `hints_for` now reads
  `values_list` into a slotted `Span`, `WorkingDay` keeps its end as it
  grows, and calendar dates are compared only for gaps of 3 hours and
  more: 567–604 ms.
- **Where hints show:** "long day" and "short break" at every entry of
  that day, "short rest" at the first entry of the next day. Rejected
  entries and a running stopwatch do not count. Shown when entering (the
  confirmation of the quick entry, "Meine Zeiten"), in the approval and
  the report (filter "Nur Einträge mit Hinweisen", CSV column "Hinweise",
  timesheet), and as `hints` of every time entry in the API. Never
  blocking.
- **Hints cross projects:** entries in projects the reader cannot see
  still count – a person's working day is one –, and the hint gives hours,
  never the project. They apply to employees and freelancers alike,
  worded neutrally; a limit of 0 switches its hint off. The limits are
  settings on Firmendaten und Grundeinstellungen
  (`SystemSettings.time_hint_*`).
- **An expense always needs a project** (ZEI-019, `timetracking.Expense`,
  `timetracking/expenses.py`) – no "without project" as for times. It uses
  the four statuses of time entries; "reimbursed" is a date on an approved
  expense (`reimbursed_on`), not a fifth status.
- **Travel:** with kilometres the amount is km × the rate, which is fixed
  on the expense when it is recorded (`km_rate`, like ZEI-008); without
  kilometres the amount is typed in (a ticket). The rate is
  `SystemSettings.expense_km_rate`, 0.30 €.
- **Receipts:** JPEG or PNG are turned upright, reduced to 2,000 px and
  stored as JPEG without metadata (no location); a PDF is checked by its
  first bytes. The size limit is the upload setting (50 MB), because phone
  photos exceed the 2 MB image limit. A receipt's file goes with its
  expense; anonymisation keeps receipts and amounts (the books) and
  empties the notes.
- **Rights:** as for times – one's own; others with "approve times"
  (ZEI-011, ZEI-013), in the projects one may see. Whoever sees an expense
  sees its amount. The cost line in the project totals needs the right for
  personnel costs.
- **Approval** on the existing page "Freigeben", per project, next to the
  times and with the same buttons. The report sits under
  `/times/report/expenses/`: the tab "Spesen" under Personal for
  approvers, "Meine Spesen" in Mein Bereich for everyone. Notifications
  (kind `expense`, by e-mail by default) when expenses are sent back or
  reimbursed.
- **Costs:** only approved expenses count; "Gewinn aus dem Projekt"
  subtracts them (`ProjectPrices.expenses_cost`, the planning page loads
  the sum with the project – no query of its own; the project list in one
  query for all rows). The profit of Part 12 (the sum
  column, `contribution_margin`: net minus subrental cost minus personnel
  cost) now also subtracts the approved expenses.

### Dragging in the timeline, invoices switched off (VFG-026, DOK-014)

- **Where dragging works:** only in hour columns ("Tage") of Planung →
  Zeitstrahl and of the timeline in Zeitplanung, with mouse or pen; a
  finger scrolls the timeline as before. In Planung a click on a bar still
  opens the project; in Zeitplanung the bars of rental period, event and
  phases are links that open the dialog with the times to type in
  (`schedule:move`, without the script a page of its own).
- **Snapping and resizing:** 15 minutes (`STEP_MINUTES`). The middle moves
  the bar, an end changes start or end; an end outside the shown columns
  has no grip. **Keyboard:** on a bar ←/→ move it by 15 minutes, with
  Shift only the end; the new times are announced, Enter opens the dialog,
  Escape takes the move back.
- **The dialog's preview runs the real move in a transaction that is
  rolled back** (`schedule.moves.preview_move`, `_trial`). It shows
  exactly what saving will do: crew moving along, who is asked again
  (PER-034), crew warnings (PRJ-022), material lines that follow, parts
  that move along, the material missing before and after. Nothing is sent
  – mails and notifications go out only after a commit. *Rejected:* a
  second implementation that predicts – it would drift from the services.
- **Moving the whole rental period** (same length) offers "Veranstaltung,
  Phasen und Personal mitverschieben", ticked: event, every phase with its
  crew and the crew without phase move by as much, also in parts that move
  along. This goes beyond the project form. Changing one end changes only
  the rental period.
- **A phase beyond the rental period (PRJ-100):** the extension is an
  unticked box in the same dialog, with the material forecast; phases of
  the kind "Planungen und Besprechungen" never ask.
- **Who may drag:** edit access, and a project that is not closed
  (`movable_project_ids`: no query for a role on all projects, one for a
  role on assigned projects). Cancelled projects can be moved, because the
  existing rules allow changes to them (this differs from the assumption
  12.2 number 24 e), which said not).
- **After saving** the dialog's close reloads the page and puts the focus
  back on the bar; a new rental period notifies the people of the project
  (UIX-005), from the dialog and the API (`POST
  /projects/{id}/reschedule/preview`, which changes nothing, and `POST
  /projects/{id}/reschedule`).
- **Invoices switched off** (DOK-014): `SystemSettings.invoices_enabled`
  ("Rentalars als Buchhaltungsprogramm verwenden", on Firmendaten und
  Grundeinstellungen, `system.invoices_enabled` in the API). Off:
  invoice, invoice draft and cancellation are refused in the browser (a
  message) and in the API (400) – `documents.services.check_invoices_enabled`;
  the head of a project suggests no invoice; the Lexware hand-over and the
  DATEV export are hidden on the Buchhaltung page and refused (400).
  Invoices made before stay readable and sendable, with what became of
  them in Lexware Office; hand-overs already queued still finish. Closing
  a project never needed an invoice.

### The Raspberry Pi (NFA-070)

This differs from Part 14, where NFA-070 was "only recorded" and
"nothing changed in `deploy/`".

- **Pi behaviour only on a Pi.** It runs only when
  `/proc/device-tree/model` starts with "Raspberry Pi"; x86 servers and
  other arm64 boards behave as before (`install.sh` up to the package
  step compared byte for byte for four option sets).
- **The system** (`lib.sh` `check_system`): 64 bit is checked through
  `dpkg --print-architecture` – the installed system, not the CPU (a Pi 4
  can run a 32-bit system on a 64-bit kernel); armhf, armel and i386 are
  refused everywhere. Debian or Raspbian is accepted only on a Raspberry
  Pi; Debian 12 is refused (Python 3.11), Debian 13 supported, a newer one
  gets "nicht erprobt". Pi 4/5/400/500 and CM4/CM5 are intended; other
  models (Pi 3, Zero 2 W) get "nicht erprobt" and are not refused.
  Part 1 ("Only Ubuntu Server with NGINX", NFA-027) now
  reads "Ubuntu Server, on a Raspberry Pi also Raspberry Pi OS".
- **No package name differs on Debian 13**; `system_packages` has one list
  and a hook for future renames. mysqlclient has no Linux wheels and is
  built against `libmariadb-dev` as on x86; every other library has
  aarch64 wheels for Python 3.12 to 3.14 (checked with `pip download`).
- **Memory sizing (NFA-042) only on a Pi**, to keep x86 unchanged
  (`sizing_for_memory`): from 3,500 MB of MemTotal (a "4 GB" Pi) the
  reference values stay (5 workers, 1G for MariaDB); 1,500–3,500 MB 3
  workers and 512M; below 1,500 MB 2 workers and 256M. The workers are
  set with `sed` on the installed unit at every `install_units`
  (`adapt_workers`); MariaDB gets `62-rentalars-memory.cnf` (overrides
  `60-rentalars.cnf`), rewritten or removed at every update
  (`write_database_memory_settings`).
- **SD card:** from the file system's device number to
  `/sys/dev/block/MAJ:MIN`, following dm slaves (LUKS, LVM); any
  `mmcblk*` counts, the eMMC of a Compute Module included; it also works
  where the root shows as `/dev/root`. At install a warning before the
  question, at update a note, in `rentalars status` a row; in the
  self-check a NOTE, not a warning, so a deliberate SD setup does not stay
  yellow. Below 4 GB the self-check notes it on the device line.
- **No permanent "nicht erprobt" for a Pi** in the scripts although no
  real Pi was tried; that honesty lives in `docs/betrieb/installation.md`,
  "Was davon erprobt ist".

### Not built

- **Projects:** no demo data for service cases, show files, chats,
  automations or expenses; show files of real consoles not tried, and the
  endings `.avo` (Titan) and `.dm3f` (DM3) have no manufacturer source;
  LA Network Manager 2/3 sessions go up as ZIP.
- **Chat:** not in the search, the webhooks or the Android app.
- **Maps:** no trips in the PDF "Einsatzübersicht"; supplier addresses
  noted in "Kontakt" or "Notiz" are not moved; no address type-ahead
  (VFG-025), by Nominatim's policy.
- **Surcharges:** no holidays by the venue's location; no surcharges in
  the hours report or CSV per person (payroll) or in the crew's own
  Überblick; overtime surcharges, which the old PER-009 named, are covered
  by the hour limit of PER-035.
- **Expenses:** no webhook events; not in the price overview or its PDF
  (the costs appear in the planning totals, the project list and the API);
  HEIC photos of iPhones not tried (browsers send JPEG).
- **Planning:** no dragging by touch; the Buchhaltung row on the
  Einstellungen page keeps its text when invoices are off.
- **Raspberry Pi:** no real Pi and no Debian 13 package was available;
  install, update, backup, the SSD boot and response times on a Pi are
  untried, mysqlclient was not built for aarch64, and whether MariaDB and
  the wheels load on the 16K-page kernel of Raspberry Pi OS on a Pi 5 is
  not known.
- **MariaDB:** the migrations were run on copies of a
  SQLite database only.

### Assumptions to confirm

For the catalogue, chapter 12.2 number 24 ("Stand vor dem Bau"), as built:

a) A group with packed, issued or allocated material cannot become a
   subproject; documents, mails, files, phases and open items stay at the
   whole project; each crew line stays or goes as chosen, with its time
   entries, its phase copied (PRJ-050).
b) A service case keeps "inquiry" as project status and has its own three
   statuses; from an inquiry the mail becomes its first correspondence;
   converted, it keeps number, mails and history and starts as an inquiry
   (PRJ-090).
c) Show files pass by their ending; folders as ZIP; the upload limit
   stays 50 MB unless changed (PRJ-089).
d) The chat is a tab; mentioned can be whoever can open the project;
   messages are not in the change log (UIX-010).
e) A part stays within its whole project; closed projects cannot be
   dragged, **cancelled ones can** (VFG-026).
f) A position is asked once per address text; a changed address is a new
   question; nothing leaves before "Karte anzeigen" (UIX-033, UIX-034).
g) Trips stand in the Zeitplanung and the Überblick; the suppliers are
   stops of one round trip from and to the warehouse (PRJ-097).
h) Every run is logged, a left-out one with its reason; at most one answer
   per sender, rule and local calendar day (ADM-013).
i) With invoices off no cancellation can be made either; the setting is
   switched on for it (DOK-014).
j) 24.12. from 14:00 150 %, 31.12. from 14:00 125 %; flat and per-day
   crew lines get no surcharges; the before-midnight rule is a setting, on
   by default; one federal state for the company (PER-009).
k) Several entries of a working day count together; gaps of at least 15
   minutes count as break (ZEI-018).
l) Only approved expenses are costs; the rate per kilometre is fixed when
   the trip is recorded (ZEI-019).
m) The Pi is recognised by `/etc/os-release`, the architecture of the
   installed packages and `/proc/device-tree/model`; on a Pi with less
   than 4 GB fewer workers and less MariaDB memory (NFA-070).

## Part 17: Requirements from practice

The 31 points noted while using the application (catalogue,
stage 8 "Weitere Wünsche": EML-047, EML-048, PRJ-107 to
PRJ-109, VFG-031 to VFG-034, UIX-039 to UIX-042, ZEI-024 to ZEI-027,
PER-039, PER-040; amended EML-006, ZEI-018, VFG-023; chapter 12.1;
chapter 12.2 number 25). The decisions below are those of the build,
checked against the code.

### Scope and decisions

- **Every wish is a SOLL requirement of stage 8**, origin
  "Weitere Wünsche"; point 29 (change log) is a fix, point 30
  a question answered in the manual.
- **Alias addresses (EML-047):** a mailbox gets a list of its further
  addresses; the address a mail went to is read from `Delivered-To`,
  `X-Original-To`, `To`, `Cc`; per address the rule for untagged mails
  ("nicht übernehmen", "als Anfrage", "gleich als Servicefall anlegen")
  and the role "nur für Servicefälle" (sender of mails written in a
  service case). The mailbox's own address keeps `process_untagged` unless
  listed itself.
- **Several job functions in one period (ZEI-025):** a period (start, end,
  break) splits into parts, each with job function, crew line, hours and
  rate, adding up to the worked hours; the person's planned crew lines are
  offered first with their times; surcharges spread by hours; hints,
  overlap check and stopwatch treat the period once; approval acts on the
  whole period.
- **Service cases (ZEI-024, PRJ-108):** everybody with time recording can
  record on any open service case without being planned; "Beteiligte"
  (person, optional job function, note) see the case and are notified –
  not crew planning: no availability check, no request, no plan costs.
- **Companion hint (ZEI-024):** a dismissible hint in "Meine Zeiten",
  linking to Mein Konto → API-Token; not on the dashboard.
- **"In der App" (UIX-039):** a third column in the notification settings;
  the server only stores the choice and hands it out in the API.
- **Commute (ZEI-027):** per person "Entfernung Wohnung – Betrieb (km)";
  twice that is deducted once per person, project and day from trips by
  kilometre; the expense shows the calculation; empty distance deducts
  nothing; a setting switches it off.
- **Surcharges international (PER-040):** the fixed percentages become
  rules (time of day, weekdays, public holiday, day of the year from a
  time), each with price and cost percent; day rules count the highest
  only, time-of-day rules add to them; holidays per German federal state
  (computed, no network) plus own holidays (yearly, once, relative to
  Easter); "Nach § 3b EStG einstellen" restores the original set; the update
  converts the settings so no surcharge changes.
- **Point 30, for the manual:** Rentalars computes the holidays itself per
  federal state, the movable ones from the Easter date; no service is
  asked.
- **No mail server (EML-048):** without `[email] host` and without a
  system mailbox a mail is "nicht versendet – kein Mailserver
  eingerichtet", not counted as sent; the sending page warns and points to
  Einstellungen → Postfächer. `rentalars@localhost` is just the config
  file's default sender.
- **Change log fix (ADM-005, point 29):** an earlier update logged
  references as text ("D-001 …" for a service product); `core.history`
  looked them up as IDs and the change log and histories crashed. Now
  `_Lookup.name_of` shows a value that is not an ID as text (test
  `tests/ui/test_081_lead_pages.py`). Rule for every update: log
  references as IDs (`actor_label="Aktualisierung"`).

### Mail and inquiries (EML-047, EML-048, EML-006, PRJ-107)

- **Model:** `MailboxAddress` (mailbox, lower-case address unique per
  mailbox, `untagged` ignore/inquiry/service_case – default inquiry,
  `for_service_cases`, `case_manager`); changes show in the mailbox's
  history (EML-047).
- **Matching:** the first listed alias found in `Delivered-To`,
  `X-Original-To`, `To`, `Cc` (that order) decides; the mailbox's own
  address is checked last, because servers write it into `Delivered-To`
  even for alias mail; a listed own address replaces `process_untagged`
  for mail matching no other alias (EML-047).
- **Edited as a list** with its own small form under the mailbox's edit
  page, not a formset – the project has no formsets (EML-047).
- **Service case at once:** name and customer/contact from the sender as
  PRJ-090 does; stored as `AssignedBy.NEW_CASE`; case and mail saved
  atomically, on failure the mail stays an inquiry; the responsible person
  gets one `NEW_MAIL` notification instead of "ist jetzt deiner"
  (EML-047).
- **Automations:** the "mail without tag" trigger (ADM-013) also fires
  for a mail that became a case, with the case as the run's project; an
  automatic answer goes out from the alias the mail was written to
  (EML-047).
- **Role "nur für Servicefälle":** at most one address; giving it to one
  takes it from the other with a note; service-case mail goes through the
  alias's own mailbox if it can send, else the outgoing mailbox, with the
  alias as sender; aliases count as own addresses ("answer all",
  automation loop protection) (EML-047).
- **No mail server:** no active complete system mailbox and a log-only
  inner backend (console, dummy, file); the mail is still handed to that
  backend (developers see it), logged `not_sent`, `send_mail` returns 0,
  `Notification.emailed_at` stays empty (`mail/server.py`, EML-048).
- **Where it warns:** self-check test mail, invitations (user create,
  resend, person form), the deployment request page; banner on the mail
  settings and mail log; the self-check names the missing server; after
  creating a user without a server the page goes to the user (one-time
  password). API: `send-invitation` 204 when sent, else 200 `{"sent":
  false, "reason"}`; `POST /users` adds `invitation`; the crew-line request
  adds `mail_sent`, `mail_reason` (`null` when no mail was due) (EML-048).
- **"Nur als gelesen markieren":** `AfterAssignment.READ`; the default
  stays mark read and move (EML-006).
- **Anfragen as a table:** built on `core.tables` by area A with its own
  row template (checkbox and action columns); columns, sorting, CSV,
  foldable filters (search, kind, mailbox); grouping by sender, date, tag,
  mailbox and the new column "Empfangsadresse" (`UnknownTagMail.address`,
  empty for older mails) added afterwards (PRJ-107, UIX-040).
- **Project number type-ahead:** `data-typeahead-free` on
  `/mail/projects/?q=`, number or name, only visible projects; without
  scripts the first word is used; no API endpoint of its own (`GET
  /projects?q=` covers it) (PRJ-107).
- **"Als Projekt anlegen":** only for inquiries without a tag and with
  write access to e-mail; reuses the project form with `?inquiry=`;
  project and mail saved together or not at all; `POST /projects` takes
  `inquiry` (PRJ-107).
- **Trash-can button:** single removal asks nothing (the mail stays in
  the inbox); its label is visible on keyboard focus; removing several
  asks first; `POST /mail/unknown/dismiss` with `ids` (PRJ-107).

### Notifications and follow-ups (UIX-039, PRJ-109, VFG-034)

- **Categories in code, not stored** (`notifications/categories.py`), in
  the order Projekt, Personal, Material, System; Projekt: deployment
  request, answer, chat mention, follow-up, new mail, project change,
  shortage, automation (automation triggers are project events);
  Personal: own expenses, expiring qualification; Material: defect, low
  stock, inspections due; System: mail problem, own calendar, application
  error, background task. An unmapped kind counts as Projekt; a unit test
  asks for every kind to be mapped (UIX-039).
- **"In der App" default** on for deployment request, chat mention and
  follow-up – direct and wanting a quick answer; answers concern the
  planner and stay off (`COMPANION_BY_DEFAULT`, UIX-039).
- **Storage:** `Preference.companion` per user, copied to
  `Notification.companion` at creation so the app can ask `?companion=1`;
  a kind wanted only in the app is created as already read in Rentalars
  (like e-mail only); all three off creates nothing (UIX-039).
- **Column names:** "In Rentalars" instead of "In der Anwendung", so it
  cannot be confused with "In der App" (UIX-039).
- **API compatibility:** `PUT /notifications/preferences` without
  `companion` keeps the stored choice; `category` is read-only; an unknown
  `?category=` gives 400 (UIX-039).
- **Follow-up time:** `Project.follow_up_at` (TimeField, nullable); with a
  time due from that time on (also before 6:00), without from 6:00; "due"
  means the same for badge, filter, start page, notification and
  automation; a new day, time or person reminds again; the automation key
  gets `:HHMM` only with a time, so existing keys stay; `{wiedervorlage}`
  reads "Mo 20.10.2026 um 14:30" (PRJ-109).
- **Planung → Wiedervorlagen:** shown to everyone who can read projects;
  with the customer right (AUT-023) every follow-up of visible projects,
  else only one's own; filters Für, Nur fällige, Von/Bis; Tag and Projekt
  always shown, Kunde and Zuständig off by default, Aktionen not in the
  CSV; "Verschieben" opens the project's dialog and returns, "Erledigt" is
  a button of one shared form (one CSRF token); both only with edit
  access; the start page's "Alle meine Wiedervorlagen" links here
  (VFG-034).

### Service cases, commute, hints (PRJ-108, ZEI-027, ZEI-018)

- **Participant model:** `ServiceCaseParticipant` (case, person, optional
  job function, note, added by/at), one row per person and case; deleted
  with case or person, a deleted job function is emptied; change log with
  IDs, shown in the case's history (PRJ-108).
- **Visibility:** for roles limited to assigned projects, taking part
  gives read access to that case – never beyond the role, only while it is
  a service case; crew lines and participations read in one query
  (PRJ-108).
- **Notification:** reuses `PROJECT_CHANGE`, no new kind (PRJ-108).
- **Adding again** changes function and note only; deactivated people or
  functions are refused; removing leaves the times (PRJ-108).
- **Mein Bereich → Servicefälle** (`/me/service-cases/`, `core.tables`):
  cases one takes part in or is responsible for, open and in progress by
  default, "auch erledigte" as filter, groupable by status; the start page
  block lists taken-part cases too (PRJ-108).
- **API:** `participants` on each case; `GET`/`POST
  /service-cases/{id}/participants` (a repeated `POST` answers 200),
  `PATCH`/`DELETE …/{pid}` (removing needs write, not delete);
  `?taking_part=true` (PRJ-108).
- **Commute calculation:** per day, person and project at most twice the
  distance, used up by trips in the order recorded; each trip stores what
  it deducted (`Expense.commute_km`, like `km_rate`); recalculated only
  when its project, kind, day or kilometres change; deleting a trip does
  not recalculate others (only ever in the person's favour); a trip used
  up entirely stays at 0 €, so the amount validator is ≥ 0 for trips
  (ZEI-027).
- **Personal data:** the distance is exported and erased on
  anonymisation; participations are exported, their notes erased
  (ZEI-027, PRJ-108).
- **Hints switch:** `time_hints_enabled`; off means no hints anywhere, the
  limits are kept, "Nur Einträge mit Hinweisen" disappears, the CSV column
  stays empty, the API returns `hints: []` (ZEI-018).

### Time entries (ZEI-025, ZEI-024, ZEI-026)

- **Data model:** each part is its own `TimeEntry`; all parts share a UUID
  in `period_key` and carry the period's start, end, break and note; each
  has its own job function, crew line, rate and share in `hours` – so every
  sum, report, CSV, export, cost, hour tier and total works unchanged;
  `save()` keeps a part's share; `period_key` is left out of the change
  log (ZEI-025).
- **Surcharges:** no change – `entry_pieces` already spreads an entry's
  hours proportionally over its time pieces; a test checks two parts add up
  to the whole period (ZEI-025, PER-009).
- **Once per period:** hints merge the parts (the break counts once); the
  overlap check ignores the period's own parts; hand in, approve, reject,
  take back and delete act on the whole period; a running stopwatch is
  divided only after it stops; the approval has one tick per period
  (ZEI-025).
- **Form:** the person's crew lines first ("Licht – Aufbau, Mi 10.03.
  08:00–12:00", value `line:<id>`), then job functions; "Mehrere
  Funktionen in diesem Zeitraum" folded, rows of function plus hours, the
  top function gets the rest; the plain job function stays preselected
  (acceptance scenario 5), the crew line found by time as before
  (ZEI-025).
- **Crew line times, not phase times,** are shown – more precise; the
  phase name stays in the label (departs from the requirement's wording,
  ZEI-025).
- **Changing a part alone** (API `PATCH` without `parts`): times, project
  and note change for the whole period, shares rescale in proportion
  (rounding to the largest part); a changed job function affects only that
  part (ZEI-025).
- **Splitting a project** (PRJ-050) refuses to tear a divided period
  apart, naming person, day, times and functions; a period whose crew
  lines move together moves whole (`projects.split._keep_periods_together`,
  ZEI-025).
- **Service cases in the choices:** open = open or in progress; every
  active job function; those taken part in after the planned projects,
  with the participant's function preselected, all others last; a case
  not taken part in is never the preselected guess; only in the time form
  and API, not expenses or approval (ZEI-024).
- **Companion hint dismissal** is stored in `TablePreference` (key
  `times.companion-app-hint`), no new table (ZEI-024).
- **Day rate:** an entry on a per-day crew line with the person's own day
  rate shows "Tagessatz" and the rate, its amount once per calendar day and
  crew line, further entries "im Tagessatz"; the week sum adds what is
  shown; a job function's guide value is never shown as pay; reports,
  exports and costs keep hours × rate (ZEI-026).
- **Clipboard:** product name = the crew line's service product, else the
  job function's, else its name; one button at the first part of an
  approved period, one block per part; `navigator.clipboard.writeText`
  with a hidden-textarea fallback for plain http (ZEI-026).

### Planning views (VFG-031, VFG-032, VFG-033, PER-039)

- **Dragging deployments:** a fourth move kind `crew`, reusing the drag
  code, keyboard handling, dialog and API of VFG-026; saved through
  `crew.update_crew_line` (planned hours follow if they were the
  suggested ones; an asked or accepted line asks again); only the
  deployment moves; same rights as VFG-026, only in "Tage"; moving to
  another person not built – it needs vertical dropping, a job-function
  check and new rates (VFG-031).
- **Hover times:** title and hidden text "Mi 10.03., 9:00 Uhr bis 13:30
  Uhr", "… bis 24:00 Uhr", "Mi 10.03., ganztägig" for availabilities,
  absences and deployments (VFG-032).
- **Conflict fill:** a deployment in conflict is filled red, its start
  band keeps the fest/Option/Anfrage colour; availability and absence bars
  are not filled, their "!" and hover name the conflict; the same in the
  availability week and, new, on a person's own timeline (API `kind`
  carries `is-conflict`); all availability kinds hatched (VFG-032,
  VFG-023).
- **Scroll range:** hour views hold two spans before and after the chosen
  one – Zeitstrahl, Personalplan,
  Materialauslastung, Zeitplanung timeline; week views and the
  day-column timelines of a product or person unchanged (VFG-033).
- **Hourly lines** where an hour is at least 8 px wide, measured on the
  panel (container query), not the window: up to 7 days at 1920 px, 4 days
  at 1280 px (VFG-033).
- **Marking in the week:** drag with mouse or pen in 15-minute steps; on a
  phone tap start then end in 30-minute steps; over several days the same
  hours each day (what the form already enters), so a night across
  midnight is typed; the range fills the existing form, a line states it
  in words; the form stays the keyboard way; no new data, the migration
  stays empty (PER-039).

### Tables and the interface (UIX-040, UIX-041, UIX-042)

- **Grouping lives in the address** (`?group=<column>`), like sorting,
  via the column's `group=` (a field or a function); nothing stored per
  user; the empty migration `core 0016_tables_081` stays (UIX-040).
- **Group counts** are for the whole filtered list; a group continuing on
  the next page repeats its heading; fixed-choice fields order by their
  choices, links by name (UIX-040).
- **CSV is never grouped;** `export=False` columns (buttons, ticks) are
  left out (UIX-040).
- **Several tables on one page** use a prefix: Automationen (`runs_`),
  Fehlbestände (`bottlenecks_`, `subrentals_`) (UIX-040).
- **Lists built in Python** (expenses, open items, inspections, shortages)
  sort and group in Python (UIX-040).
- **Expense CSV:** Personal → Spesen uses the standard table export; "CSV
  mit allen Spalten" has the existing columns (plus commute), sorted by day,
  named `spesen-<date>.csv`; the API export is unchanged in form
  (UIX-040, ZEI-027).
- **The "Gruppieren nach" form** repeats the page address as hidden
  fields, so filters and sorting survive (UIX-040).
- **Not converted:** Meine Zeiten, Freigeben, Auswertung (area D rebuilt
  them), Änderungsprotokoll (a feed), Mietstaffeln (a matrix), Personal →
  Verfügbarkeit (a board), small lists (sessions, mailboxes, notification
  settings, "Noch nicht eingereicht"), tables inside detail pages
  (UIX-040).
- **No "Zurück" from the navigation:** the three pages were missing from
  `core.trail.START_PAGES`; `NoBackFromTheNavigationTests` walks every
  navigation entry, the sidebar foot and every tab found, so a new tab
  missing there fails; the phone top-bar back icon (UIX-027) stays
  (UIX-041).
- **Date pickers:** Chromium already hid its indicator, now
  `!important`; for Firefox, where no page can hide it, Rentalars' button
  is drawn over it in the field colour; typing still works (UIX-042).
- **Module names:** area C's `projects/case_tables.py` overwrote area F's
  file of the same name; F's service-case list lives in
  `projects/case_list_table.py`.

### Surcharge rules (PER-040)

- **Rules and own holidays are rows** (`TimeSurchargeRule`,
  `OwnHoliday`), not JSON, so the change log keeps AUT-019 per field
  (`price_percent` needs the price right, `cost_percent` the personnel-cost
  right), in the settings row's history; the old `price_*`/`cost_*` names
  stay in `audit_sensitive` so the update's entries stay protected.
- **Kinds:** time of day (window, may cross midnight), weekdays, public
  holiday, day of the year; the day kinds take an optional "from" time.
- **Combination:** highest day rule plus highest time-of-day rule; on equal
  percentages the rule further down wins (as between kinds); price
  and costs choose separately.
- **Two switches for exact § 3b:** per rule "nur bei Arbeit, die vor 0 Uhr
  begann" (replaces the other time-of-day rules while it holds: 40 %
  instead of 25 %); global `next_day_until` (default 04:00, empty = no) for
  day rules reaching into the next morning.
- **One line per name and percentage** in planning and documents, so
  "Feiertag" and "Weihnachten und 1. Mai" stay one line each, rounded as before.
- **`code`** marks preset rules with the kind (night,
  night_after_midnight, sunday, holiday, high_holiday); the API part
  `kind` stays compatible, hand-made rules give `custom` plus `rule`.
- **Holidays:** switch "gesetzliche Feiertage in Deutschland" (default on)
  plus federal state; own holidays yearly, once, or −80…+240 days from
  Easter Sunday (keeps them in the same year).
- **First use** installs the § 3b rules (`ensure_rules`); afterwards an
  empty list means no surcharges. "Nach § 3b EStG einstellen" confirms,
  replaces all rules and sets 04:00; state, own holidays and switches stay.
- **Settings page:** one card per rule; aligned bottoms fix the offset
  number fields of point 31; one empty row without JavaScript, "Regel
  hinzufügen" clones a template, ↑/↓ renumber (announced); a moved but
  empty new row stays empty.
- **API:** `rules` and `own_holidays` in `GET`/`PATCH
  /settings/surcharges` – a sent list replaces the stored one (with `id`
  updated, without created, missing deleted, order = rule order), errors
  as `rules.N.field`; `POST /settings/surcharges/section-3b`; `/holidays`
  adds own holidays.
- **Queries:** 3 instead of 1 (settings, rules, own holidays), once per
  request and only when a line needs them; scenario 11 holds.
- **Update conversion** (`core 0015_surcharges_081`): a frozen copy of the
  preset; 9 rules for the defaults; change log "Aktualisierung" (one settings entry, one per rule, no references), only where
  the defaults were installed; without a settings row nothing; idempotent;
  reversible from the coded rules.

### Not built

- **Mail:** MariaDB and real IMAP/SMTP servers not tried (mocked); the
  project suggestions have no API endpoint of their own.
- **Service cases:** no type-ahead for the participant's person; the own
  profile does not show the commute distance; participants of a case
  converted to a project stay without effect.
- **Times:** not tried on MariaDB.
- **Planning:** moving a deployment to another person; conflicts in
  Planung → Zeitstrahl and the Zeitplanung timeline (never shown, would
  cost queries – the Zeitplanung timeline shows them, VFG-035,
  Part 18); Firefox/Safari and dragging on a real phone not tried.
- **Interface:** the Firefox cover-up of UIX-042 not tried in Firefox (the
  browser download was blocked).
- **Surcharges:** no holidays by the venue's location, no demo data with
  own rules, no load-test entry for the settings page.

### After the independent check

A reviewer who had not built it checked the 31 wishes in the running
application. 26 were met; these findings were fixed before delivery:

- **UIX-042:** the CSS block for the browser's picker symbol had been
  lost to a concurrent write of `app.css`; restored, and the browser test now
  reads the loaded stylesheets, so a lost block fails.
- **UIX-040:** Freigeben (a form per project, so no "Gruppieren nach", but
  columns, sorting within a project and CSV), the entries of Auswertung (own
  `entries_` parameters, the page's own CSV and `group_by` unchanged),
  Mietstaffeln (one row per scale) and the Django master-data lists
  (`core/admin_tables.py`: columns, CSV, grouping) follow the table
  standard; Rollen have groupable columns. Grouping by a day
  (`created_at__date`) is counted in Python and ordered by the moment itself,
  because MariaDB without time zone tables gives no day.
- **UIX-041:** the test walks every link of the layout, not only `ul.nav`,
  so also `/times/quick/`, a start page.
- **ZEI-024:** "Zeit erfassen" with the case preselected on the service case
  page and in every row of Mein Bereich → Servicefälle (not for done cases).
- **PRJ-108 / UIX-039:** people added to a service case get a notification
  kind of their own, `service_case` ("Zu einem Servicefall hinzugefügt"),
  category Projekt, on by mail and in the app by default – the existing
  `project_change` is off for both. Migration `notifications/0008` (choices).
- **Texts and layout:** the German help text of the role form does not name
  AUT-006; the mail settings page is titled "Postfächer und
  Signatur" like its entry in Einstellungen.

## Part 18: Security, defects and wishes

The requirements from the use of the application and the findings of a
code review (points 16–19, 25–29, 31, 33; catalogue: new SOLL in stage 8: NFA-071 to
NFA-073, EML-049, VFG-035, PRJ-110, PRJ-111, UIX-043; amended API-010,
PCK-027, UIX-010, UIX-015, UIX-038, UIX-040, PRJ-090, UIX-033, UIX-034,
PRJ-089, PRJ-097, NFA-061; chapter 12.1; chapter 12.2 number 26). The decisions below are those of the build, checked against the code.

### Scope and decisions

- **All points except 4 and 15.** Changing the
  server address with its certificate from the interface and German/English
  are stage 9 (ADM-016, UIX-029; the interface shows the command to
  run via SSH; interface language per user, document language one setting
  per company, manual in both languages). Point 15 (local AI summarising
  mail on a Raspberry Pi 4) is decided, not built (EML-040
  stays KANN, stage 10).
- **Stages:** the KANN requirements are stage 10.
- **Point 1** (`ValueError … 'D-001'`) is the change-log defect (ADM-005);
  nothing to do.
- **Mails without tag from a point in time (EML-049, point 20):** by
  default the moment the switch is turned on, editable, optionally only
  unread mails.
- **Customer required on service cases (PRJ-090, point 14):** like a
  project;
  description stays optional. Decided after the reports: a case Rentalars
  creates itself from a mail (EML-047) is created without customer and
  shows "Kunde fehlt" – it is never turned back into an inquiry.
- **Route links (UIX-033, point 10):** always from the user's current
  location – no `origin` in the Google Maps URL –, trips keep their
  waypoints.
- **Tiles (UIX-034, point 9):** requested with `referrerPolicy:
  "strict-origin-when-cross-origin"`, so the OSM tile server gets the
  installation's origin as the policy requires; acceptable because tiles
  load only after "Karte anzeigen".
- **HTTPS (NFA-073, point 33):** production refuses an `http://` site URL
  unless `allow_http = yes`; `deploy/install.sh` always writes `url =
  https://${domain}`, so installations made by it are unaffected.
- **Filters (UIX-038, point 13):** "always folded" taken literally: the
  open state remembered is dropped. (The ideas list, 12.2
  26 k, assumed the opposite; the build follows the decision.)

### Security (API-010, NFA-071, NFA-072, NFA-073)

- **Idempotency bound to the caller (API-010):** a key is stored as
  `token:<pk>` or `user:<pk>` with method, path and a hash of the body; a
  different caller never gets the stored answer.
- **Order of a repeated call (API-010):** authenticate (a call that does
  not log in is treated as without key) → look up the stored call → all
  checks of a new call (login, module rights, rate limit, access to the
  record named by the path; a record that is gone does not refuse, so a
  repeated DELETE still gets its 204) → 409 "in progress", 409 "reused"
  or the stored answer.
- **Key misuse is 409 `idempotency_key_reused` (API-010)**, not 422 as in
  the IETF draft.
- **Key plus `If-Match` (API-010):** a repeat gets the stored answer.
- **Optimistic locking is atomic (API-010):** compare and write are one
  transaction that first takes a row of `api.WriteLock`
  (`record:<app.model>:<pk>`, or `path:<address>` when the path names no
  record); on MariaDB the record's own row is also locked `SELECT … FOR
  UPDATE`, so browser writes wait too; a 5xx answer rolls back. Lock rows
  older than a day go with the daily maintenance.
- **The web has no version check (API-010):** forms save
  last-write-wins, so there is nothing to make race-free there.
  (Catalogue 12.1 says "in API und Oberfläche"; only the API has
  it.)
- **What is internal (NFA-071):** loopback, link-local, private, CGNAT,
  multicast, reserved, unspecified, anything else not globally reachable,
  IPv4 inside IPv6 (mapped, NAT64) and the server's own addresses
  (interfaces, host name, the site URL's address).
- **One guard, `core/network.py` (NFA-071):** resolve, keep only allowed
  answers, connect to exactly the checked address (no second lookup – DNS
  rebinding); TLS still verifies the certificate against the name.
- **Operator exceptions (NFA-071):** `[network] allow_internal` – networks,
  addresses, host names; a host name allows that name whatever it
  resolves to; an invalid entry stops the start.
- **Checked when typed vs. when used (NFA-071):** an IP address or
  `localhost` is refused already in the calendar, CalDAV and webhook forms
  and API; a host name is checked when it is used. Mailbox hosts are not
  checked when typed (that would have touched the mail forms of another
  area); "Verbindung prüfen" shows the refusal.
- **Covered and exempt (NFA-071):** covered – calendar feeds, CalDAV,
  webhooks, IMAP and SMTP of mailboxes including the system mailbox
  (`GuardedSmtpBackend`); exempt because the operator sets them –
  `[email]`, `[maps]`, the database, Lexware (fixed address). WeasyPrint
  was checked: no user HTML reaches it.
- **Proxy from the environment (NFA-071):** when `https_proxy` /
  `http_proxy` applies, the request still goes through the proxy; the name
  is checked first, but the proxy resolves it again, so pinning then
  depends on the proxy.
- **Error texts never show the resolved IP (NFA-071)**, which would
  describe the internal network; the self-check, which only operators see,
  does.
- **Tests allow `127.0.0.0/8` and `::1` by default (NFA-071)** – only under
  `manage.py test` – so the local calendar and webhook servers of the
  suite keep working; the guard's own tests switch it off.
- **Credentials only to the same origin (NFA-072):** exactly the same
  scheme, host and port; the one named exception is iCloud
  (`caldav.icloud.com` → `pNN-caldav.icloud.com`, https, 443). An address on another host named in a
  server's answer (principal, calendar home, calendar) is not contacted;
  the calendar found is checked before it is stored.
- **Redirects (NFA-071, NFA-072):** calendars follow at most five, by
  hand, each target checked again; webhooks follow none (as before).
- **HTTPS (NFA-073):** `config.load_config` raises `ConfigurationError` for
  production with a non-https `url` unless `allow_http = yes`; behind a
  TLS proxy `url` stays https and the proxy sends `X-Forwarded-Proto:
  https`; an update with an http configuration fails at `migrate` and
  rolls back.
- **Self-check (NFA-071, NFA-073):** "Sicherheit → HTTPS" is OK, or a
  warning with `allow_http`; the new group "Verbindungen zu anderen
  Servern" lists settings that lead inside (calendar feeds, CalDAV, active
  webhooks, active mailboxes; a webhook named by description or host,
  never its path) and the allowance. Nothing is deleted.

### Offline sync and chat (PCK-027, UIX-010)

- **One version per pack entry (PCK-027):** `PackEntry.version` counts
  only changes of the packed and returned quantities (web, API, sync,
  handover, "issue everything"); issue, take-back and the snapshot at
  packing start do not count, because every offline change after them
  would conflict and the ticking limits (PCK-028) already guard them. Rows
  without an entry have version 0.
- **`base_version` (PCK-027)** is compared with the version at the start
  of the sync, so changes within one sync do not conflict with each
  other; different and the server already has the wanted quantity →
  `applied`, nothing written; otherwise `conflict`, the server's state
  stays and is returned in `server`.
- **Clock rule without `base_version` (PCK-027):** the server
  reads its clock only after locking the packlist; a future moment counts
  as now; order by moment, then the phone's original moment, then request
  order; within one sync a later change to the same quantity wins; against
  the server only a strictly later moment counts (equal → server); the
  stored moment never goes back. Two changes with equal
  moments in one sync both apply, the later in request order wins.
- **`change_id` (PCK-027):** at most 64 characters, per user; receipts
  (`SyncReceipt`) kept 30 days, pruned by each sync; the same ID for a
  different change is refused; the same ID twice in one request is judged
  once, the copy gets `replayed`.
- **`packing.returned` from the sync (PCK-027):** once per sync and only
  if some change raised a returned quantity – the browser's rule.
- **GET creates nothing (PCK-027):** the main packlist is created by a
  `post_save` signal when a project is created in, or moves into,
  confirmed_open, confirmed or out – every route (web, API, inquiry) – and
  logged like a hand-made one; the migration creates it for existing such
  projects. A project still without one is listed with `packlists: []`.
  The packlist page and the single-project API also create it on first
  open (PCK-001).
- **Lock order (PCK-027):** packlist before entries in the sync and in
  `_LockedEntries` (`pack_all`, `acknowledge_changes`, `issue`);
  `_start_packing` and `resolve_missing` save only their own fields.
- **Chat stamp (UIX-010, UIX-020):** `newest-count-sum of revisions~unread`
  with `ChatMessage.revision` counting edits; `int(timestamp())` alone would miss them, and even with
  microseconds editing an older message does not move the stamp. MariaDB
  stores `datetime(6)`.
- **`up_to` (UIX-010):** lowered to the newest message of that chat not
  after it; the mark only moves forward, guarded against concurrent
  requests; a value that is not a whole number ≥ 0 is 400.
- **Polling as a whole (UIX-020):** project stamp, unknown mails and
  notifications do not depend on time. A tick writes nothing to the change
  log, so the key `packing:<pk>` (sum of versions and row count) lets an
  open packlist follow others' ticks, on packlist pages only,
  without "." so one's own tick does not reload (PER-033).

### Clean-up (EML-024, NFA-061, NFA-062, UIX-015, UIX-038, UIX-040)

- **Form errors (EML-024, point 2):** one helper,
  `core.forms.add_validation_error(form, error)`, for plain and model
  forms – routes through `error_field_map`, sends errors of unknown fields
  to the top, uses Django's public `add_error`; all 13 private
  `_update_errors` calls in 7 files use it. Only Django's own model
  validation still goes through `StyledModelForm._update_errors`
  (`routed_errors`).
- **Every column sorts (UIX-015, UIX-040, point 21):** plain fields by the
  field; multi-valued columns (functions, qualifications, roles,
  categories of a scale) by the alphabetically first value (`Subquery`);
  computed values the database can express by an expression (volume
  L×W×H, notification category, two-factor login, hall plan, an item's
  effective product).
- **Python sort limit (UIX-015):** values that exist only in Python sort
  in Python for lists of at most `PYTHON_SORT_MAX_ROWS` = 2,000 rows;
  above, the default order with `TableState.sort_notice`. This covers the
  8 project sums, rental days, stock / total stock / below minimum, the
  category-specific value, a scale's factors, a template's content, a
  webhook's events and "my part"/note of my service cases.
- **Natural sort (UIX-015):** text with numbers sorts naturally
  (`natural_key`: "5 m" before "10 m").
- **Unsortable only with a reason (UIX-015):** button and tick-box
  columns carry `Column.unsortable = "<reason>"`; a test walks every
  `TableDefinition` and fails on a column that neither sorts nor names a
  reason.
- **Master data (UIX-040):** the admin "path" column sorts by the tree (up
  to 6 levels; deeper is approximate) and is headed "Name"; Django's
  Groups list has a sortable "name" column. The CSV of an already sorted
  material list follows the sort.
- **Filters always folded (UIX-038, point 13):** on every page load at every
  width; the stored open state is ignored and deleted; a filter with an
  error still opens; the button reads "Filter (n aktiv)" with chips. In the
  Django admin `templates/admin/filter.html` renames the attribute
  `admin/js/filters.js` looks for, so nothing is reopened, and the folded
  heading shows the choice ("Nach Aktiv: Ja"). The Materialverwaltung
  lists already used the shared panel; only the remembered state kept them
  open.
- **English identifiers (NFA-061, point 5):** scanned Python names, keys,
  strings, templates, CSS/JS, models (tables, columns, choice values) and
  dev docs; no database identifier is German, so no migration. Fixed: the
  backup page anchors `#sicherung`/`#verschluesselung` → `#backup`/
  `#encryption`, two German test identifiers. Kept on purpose: import
  column aliases (German input data), automation placeholders `{firma}`,
  `{datum}`, `{projekt}` … (users type them; to revisit with
  English), German unit codes in `documents/content.py` (match data),
  quotes of requirements, `docs/dev/traceability.md`
  (generated), CSS/JS comments naming German screens.
- **Leftovers (NFA-062, point 3):** removed `templates/core/confirm.html`,
  `mail.fetching.known_message`, `mail.suppliers.link_by_address`,
  `products.services.kit_price_from_components`,
  `accounts.rights.special_right_required`,
  `availability.services.ExcessCover`,
  `projects.grouptree.GroupTree.children_of`,
  `Qualification.is_valid_on`, `products.scale_tables._may_edit` (none
  used anywhere); merged the duplicate `fold()` of `customers/importer.py`
  and `projects/mvr.py` into `core.tabular.fold`. No TODO/FIXME, no unused
  static files, no unread config keys (`[backup]` is read by
  `deploy/backup.sh`). Kept: compatibility for existing data and API v1
  (`legacy_mailbox`, `/mail/settings`, `delete_after_import`), the
  `mail/settings/` bookmark redirect, data conversions from 0.6.x/0.7.x,
  helpers used only by tests, the duplicate `address_lines` on two
  models, all migrations.

### Project (VFG-035, PRJ-110, PRJ-111, UIX-043, PRJ-090, PRJ-089)

- **Trip adjustments (PRJ-111):** table `TripAdjustment` (audited) points
  to a computed trip by key – `to_venue-<phase>`, `from_venue-<phase>`,
  `pickup`, `return` –; an empty key is an own trip (API key `own-<id>`).
- **Only differences are stored (PRJ-111):** unchanged values keep
  following the phases; a change that ends equal to the computed trip
  deletes the adjustment; an adjustment whose phase is gone has no effect.
- **Removed stays removed (PRJ-111):** across phase changes;
  "Zurücksetzen" deletes the adjustment and so also brings a removed trip
  back.
- **Limits and rights (PRJ-111):** at most 9 stops (Google Maps); edit
  access to the project and a project that is not closed; removing via the
  API needs the write right, not delete. Adjustments are not copied when a
  project is duplicated or split.
- **Crew of a phase (PRJ-110):** the planning's crew dialog opens from
  Zeitplanung with `?from=course` (a page of its own without the page
  script); remove, "anfragen" and "Antwort eintragen" use the existing
  views. After a change the page reloads in place (`HX-Refresh`) – a
  redirect to `…#phases` on the same page would only jump to the anchor.
  `crew_warnings` show at every line of a phase and again as messages
  after saving – the availability check.
- **Timeline like the personnel plan (VFG-035):** overlap (also with
  other projects), absence and "nicht verfügbar" cost 3 queries whatever
  the crew size; conflicts are filled red for everyone who can open the
  page (the planning shows these warnings anyway); the hatched
  availability row only with the right to read personnel; the legend is
  the personnel plan's plus "abgesagt" and "offen"; exact times on hover
  and as hidden text (crew bars only).
- **Meine Einsätze (UIX-043):** a tab at `/me/deployments/`, first in Mein
  Bereich, which the navigation now opens; filters period ("kommende" by
  default with 12 hours' grace as on the start page; "vergangene";
  "alle"; von/bis), state (fest/Option/Anfrage), request status, project;
  cancelled projects left out; no module right needed. Every column sorts;
  "Stand" sorts by the view's annotation `deployment_state` but cannot be
  grouped (`core.tables` groups only by a model field). The start page
  block stays; its button reads "Alle meine Einsätze".
- **Customer of a service case (PRJ-090):** required in the form, in API
  create, in the inquiry flow and whenever a case is edited
  (`update_case`); the status can change without one; `create_case`
  checks only with `customer_required=True`, which the mail fetch
  (EML-047) does not pass; the case page shows "Kunde fehlt" with "Kunden
  wählen" for editors.
- **Showfiles (PRJ-089):** the empty text names Showfiles; a service case
  has its own variant ("…zum Servicefall…").

### Mail and maps (EML-049, UIX-033, UIX-034)

- **Arrival time (EML-049):** IMAP `INTERNALDATE`, else the `Date` header;
  a mail with no date at all is left alone while a point is set.
- **No IMAP `SEARCH SINCE/UNSEEN` (EML-049):** tagged mails must still be
  looked at in full, so a search could only pre-filter the untagged ones;
  `FLAGS` and `INTERNALDATE` come with the existing header FETCH – no
  extra round trip, exact to the second rather than the day.
- **The point follows the switch (EML-049):** switched on with an empty
  field means now; a moment given in the form or API is kept; switching
  off empties it. For an address "takes in" means any rule other than
  "nicht übernehmen".
- **Mail log (EML-049):** a skipped mail is "left in the inbox" with a
  code (`before_cutoff` or `read`, optionally `:address`); the text is
  produced when shown, so no German is stored.
- **Field label (EML-049):** msgid "taken in from" ("übernehmen ab"),
  because plain "from" already exists in several contexts.
- **`origin` removed, not ignored (UIX-033):** `core.maps.route_url
  (destination, *, waypoints=())`, `Place` without `origin`, template tag
  `route_link(destination, label)`; the tag `warehouse_address` is gone.
  `Trip.origin` stays for display, API and map; only the link has no
  start.
- **Referrer on the tile layer only (UIX-034):** the pages keep
  `Referrer-Policy: same-origin`; the value comes from the server
  (`map_data["referrerPolicy"]`, `TILE_REFERRER_POLICY`) with the same
  fallback in the JS.
- **Nominatim User-Agent (UIX-034):** `core.geocoding.user_agent()` →
  `Rentalars/<version> (maps; +<scheme>://<host>)`, never a path or
  credentials.
- **Rest of the OSM policy checked (UIX-034):** attribution links to
  /copyright; tiles only after the click; no bulk or prefetch; normal
  browser caching (no service worker, no no-cache headers); geocoder at
  most one request per second, results kept, no redirects.

### Companion app

- **Compatible without change:** the GET
  of the offline list does not create packlists, but every confirmed
  project has one. Not verified against the real app – if its JSON parser
  rejected unknown keys, the extra keys would break it.
- **What the app should adopt:** keep each row's `version`; send
  `base_version` and a `change_id` (a UUID kept until a result arrives)
  with every change; handle `conflict` (show `server.quantity`, update the
  row from `version`/`server`, let the user tick again); treat `replayed`
  as the original outcome; show `packlists: []` as "keine Packliste";
  repeat idempotent calls with the same token; treat 409
  `idempotency_key_reused` as its own mistake; it may combine `If-Match`
  with `Idempotency-Key`; later perhaps the trip note and own trips.

### Data migrations

`api 0003_safeguards_082` (table `api_writelock`, help text of
`Webhook.url`), `packing 0006_sync_082` (`PackEntry.version`,
`SyncReceipt`, main packlists for confirmed_open/confirmed/out projects
without one, logged "Aktualisierung" with IDs), `chat
0002_reads_082` (`ChatMessage.revision`, 1 for edited messages; read marks
lowered; not logged – chat is not business data), `mail 0010_cutoff_082`
(four fields; `untagged_since` = moment of the update where untagged
mails are taken in, logged), `projects 0024_trips_082` (table only). No
price, cost or sum changes. All were applied only on SQLite copies;
MariaDB not run.

### Not done or not verified

- The two-thread race test of `If-Match` (`SimultaneousVersionCheckTests`)
  runs only on MariaDB and has not run; no test proves `_LockedEntries`
  prevents a lost update (SQLite shows no race).
- The Companion app itself was not tested against this server.
- `scripts/build_traceability.py` reads one-digit stages only (`(S\d)`,
  line 31), so it misses the 27 stage-10 requirements; `(S\d+)` would fix
  it.
- Mailbox hosts are not checked when typed (see Security).

### After the independent check

A reviewer who had not built it checked every point in the code and the running app; no blocking
defect. Fixed before delivery:

- **API-010:** a stored idempotent answer is replayed only if the caller still has at least the access level, in
  every project the first call consulted, that it had then. `projects.access.access_level()` records the caller's
  levels while a keyed call runs (`recording_project_access()`), the project in the address is always recorded,
  and `IdempotentCall.project_access` stores them; a lower level gives 404/403 like a new call. Time entries check
  projects via `visible_projects` and are not covered – the answer there is the caller's own entry. A test walks
  every write route with a project in its path.
- **NFA-071:** the self-check warns when `http_proxy`/`https_proxy` is set (the proxy resolves names itself).
- **PCK-027:** a `change_id` identifies one change completely (packlist, row, field, quantity, base_version); any
  difference is refused with `change_id_reused`; `changed_at` is not compared.
- **UIX-015/UIX-040:** the sums table of Auswertung sorts in Python by every heading (`REPORT_SUM_TABLE`,
  prefix `sums_`); "Projekte" on Engpässe sorts by project numbers.
- **PRJ-110/PRJ-111:** crew and trip forms opened as a page return to Zeitplanung (`#phases`, `#trips`); the
  dialog keeps reloading in place (`HX-Current-URL`).
- **VFG-032/VFG-035:** `Bar(conflict=…)` is the one flag for the red fill and "· Konflikt" in every timeline.
- The compose header shows only the name when no sender address is set.

## Part 19: Server address, German and English, AI and wishes

The requirements: server address and both languages to be prepared,
AI not only on the Raspberry Pi but in general, every
shown column in "Gruppieren nach", three statuses of a service case
and default automations for them. Answers: server address and
German/English fully built; for AI, the summary of a project's
correspondence with an activatable local AI (to save costs), and the
interface for other uses built but off at first. The address change only
shows the command; interface language per user, document language one
setting per company, manuals in both languages.
The catalogue holds the SOLL · S8 requirements ADM-016, UIX-029, EML-040,
EML-044, ADM-017, PRJ-112 and UIX-044, and the related ADM-013, PRJ-090,
PRJ-105, PRJ-109, UIX-040, NFA-071, NFA-061. The decisions below are those of the build, checked against the code.

### Scope and decisions

- **No separate stage for them:** the former stage 9
  (address, languages) and the local-AI summary are SOLL in stage 8 and
  built; the KANN requirements are stage 9 (was 10). PRJ-091
  (template suggestions by AI) stays KANN, S9, shown as "later".
- **Root stays outside the application (since stage 4):** everything that
  needs root – applying an address, installing the local AI – is an
  operator command run via SSH (`sudo rentalars address apply`,
  `sudo rentalars ai …`); the application prepares and shows the command,
  never stores root credentials.
- **Not built, suggested (PRJ-112):** new communication reopening a
  "waiting" case; it needs no code – one more rule with status `waiting`.

### Server address and certificate (ADM-016)

- **Rights (ADM-016):** reading the page needs read access to the
  Administration module; preparing or discarding a change needs its delete
  right, as for backups, because a private key is uploaded.
- **No port (ADM-016):** `install.sh` knows only 443 and 80, and behind NAT
  the outer port differs from the inner one; the address is always
  `https://<name>`.
- **Certificate sources (ADM-016, NFA-035):** Let's Encrypt (webroot over
  port 80, `--cert-name <name>`, installs certbot if missing), self-signed
  (openssl, 825 days, like `install.sh`), own certificate (uploaded), and
  "a server in front encrypts" (only the name changes). Let's Encrypt with
  a DNS record is not offered from the page.
- **Reading the current state (ADM-016):** address from `[rentalars] url`;
  names and certificate path from the NGINX site (readable by the service
  user); kind and expiry from a TLS handshake with 127.0.0.1:443, because
  the certificate files are root-only. No NGINX site → the page says a TLS
  proxy or a development install is likely.
- **Same host, new certificate (ADM-016):** allowed for every kind but
  "proxy" (renewing an own certificate, switching kind).
- **Storage (ADM-016):** model `AddressChange` (token, host, kind, e-mail,
  redirect flag, previous URL, certificate info, checks, status,
  prepared/applied by and at, result); uploaded certificate and key in
  `<data_dir>/address/<token>/` (folder 0700, files 0600, the key also
  Fernet-encrypted like other secrets), deleted after a successful apply;
  a newer preparation supersedes the open one and deletes its files.
- **How root gets the data (ADM-016):** `deploy/address.py` (system Python,
  `python3 -I`, standard library and openssl only) reads the change only
  from the stdout of `manage.py address_change export`, run as the service
  user; root never opens files in the service user's folders, so a planted
  symlink cannot trick it.
- **The command checks everything again (ADM-016):** token, host syntax,
  kind, e-mail, size; for an own certificate with openssl: key matches,
  every link of the chain, the name, validity at the real time.
- **Backup and files (ADM-016):** `/etc/rentalars/address-backup/<time>-<token>/`
  holds the configuration file, the NGINX site and `/etc/rentalars/tls`;
  new certificates go to `/etc/rentalars/tls/<name>/`, old files are never
  overwritten.
- **Targeted NGINX edits (ADM-016):** only `server_name` lines naming the
  old name and the main certificate lines change; if the old name is not in
  the site, the command stops before changing anything. `ALLOWED_HOSTS`
  follows `url`, so the configuration file needs only `url`.
- **Verification and rollback (ADM-016):** `nginx -t`, `reload-or-restart`
  NGINX, restart Rentalars, check the application socket and `/login/` over
  HTTPS under the new name with the newly installed certificate; any
  failure restores every file, reloads and restarts again.
- **Recording (ADM-016):** `address_change record` stores "applied" with
  `SUDO_USER` or "failed" with the error; a failed change can be run again;
  `--dry-run` shows plan and NGINX diff and records nothing.
- **Redirect of the old name (ADM-016, optional, on by default):** one
  block per old name in a section at the end of the site; over HTTP always,
  keeping the ACME path so an old Let's Encrypt certificate keeps renewing;
  over HTTPS only while the old certificate is valid for the old name.
  Later changes point all earlier names to the newest; going back to an old
  name removes its block. No command removes a block; `rentalars
  nginx-site` drops the section (with a diff first).
- **HTTP/2 form (ADM-016):** the command does not run `adapt_nginx_site`;
  NGINX 1.24 warns "protocol options redefined" for the redirect blocks
  without `http2` – a warning only; a later update's adaptation adds it.
- **Without systemd (ADM-016):** files are written and `nginx -t` runs; no
  reload, restart or HTTPS check, and the command says so.
- **Language of the command (ADM-016, UIX-029):** `deploy/address.py` has
  its own `operator_language()` and `t(de, en)` with the rule of
  `deploy/lib.sh`, and passes `RENTALARS_LANG` to its `manage.py` calls.
- **The token is a secret (ADM-016, IMP-006):**
  `"core.addresschange": {"token"}` in `SECRET_FIELDS`; the full export
  leaves it out.
- **API (ADM-016, API-002):** `GET /server-address`,
  `POST /server-address/changes`, `GET`/`DELETE
  /server-address/changes/{token}`; "change" is a typed field, certificate
  info and checks are JSON; the API cannot apply a change, like the
  encryption (ADM-009).

### German and English (UIX-029, NFA-061)

- **The msgids are the English interface (UIX-029, NFA-061):** written as
  finished British English; German comes from `locale/de`. Visible
  renames: sidebar "Administration" → "Settings" ("Einstellungen"
  everywhere), project tab "Course" → "Schedule", "Material utilization"
  → "Material utilisation"; requirement IDs removed from help texts; the
  "crew disposition" rename reverted (it would need a documents migration).
- **Language per user (UIX-029):** `User.language`, empty = the
  installation's `language` from the configuration file; set per request
  by `core.i18n.LanguageMiddleware` (after authentication), so htmx
  partials follow it; responses carry `Content-Language` and
  `Vary: Accept-Language`.
- **Pages without login (UIX-029):** login, password reset and setup
  follow `Accept-Language` (de/en, else the installation's).
- **API (UIX-029, API-002):** the user's choice, else `Accept-Language`,
  else the installation's – for token auth too and for error messages;
  `/me` returns `language` and `effective_language` and has `PATCH` for
  `language` (403 with a read-only token).
- **British formats (UIX-029):** dd/mm/yyyy, 24-hour clock, decimal point,
  thousands comma, money as "€1,234.50" (`core/formats/en`). Templates keep
  German patterns (`d.m.Y`); the built-in `local_dates` library overrides
  `date`/`time` and maps the pattern to the active language
  (`core.i18n.local_pattern`).
- **Number entry (UIX-029):** `parse_decimal` accepts the format shown;
  date pickers label days like "Wed, 10/03/2027".
- **Mails and notifications per recipient (UIX-029):** `LocalText` with
  `LazyCall` values is rendered in each reader's language; mails to a user,
  invitations, password resets, background jobs, crew requests and service
  case notifications (PRJ-112, via `engine.case_event_text`) are written
  in the recipient's language. Kept in one language: the "what changed" of
  project-change notifications (sender's), calendar feeds, CalDAV,
  webhooks, the audit history (installation's), placeholder values and
  run texts of automations (the document language, `engine._language`, as
  automations write to customers), demo data (German).
- **Document language (UIX-029):** `CompanyProfile.document_language`
  (default the installation's) for documents and PDFs, packing lists, crew
  sheets and automation mails to customers; typed text stays as typed;
  document templates get an English start set ("Quotation" …) when first
  created while the document language is English. E-invoice codes are
  unchanged (XRechnung checked; ZUGFeRD does not exist in the code base);
  unit codes also recognise English abbreviations.
- **Reply prefix (UIX-029):** "AW:" in German, "Re:" in English (active
  language); either is recognised.
- **Placeholders (UIX-029, ADM-013):** every automation and signature
  placeholder has an English alias (`ENGLISH_PLACEHOLDERS`: `{company}`,
  `{date}`, …, `{communication}`); both work in every text; the form shows
  the names of the active language.
- **The manual in the application (UIX-029):** `/manual/`, link in the
  sidebar foot; Python-Markdown 3.11.1 (BSD, added to requirements and
  `THIRD-PARTY.md`) with tables, fenced code and a table of contents with
  GitHub-style anchors, cleaned with nh3; links to other files shown as
  text; German with a note while `docs/en/user-manual.md` is missing. A
  start page (no "Back").
- **English start data (UIX-029):** `core.start_data.localise` renames
  start records that still carry their start name (roles, units,
  categories, "Main warehouse", "Standard scale", document types, job
  functions, Dry Hire with its phases, the internal project, the default
  automations, document templates, surcharge rules) when the installation
  or the first-run setup is English; codes stay; existing installations
  are not touched.
- **Setup (UIX-029):** optional field "Language" – document language,
  start data and the first administrator's language; proposed from the
  browser.
- **Server scripts (UIX-029):** `deploy/lib.sh` `operator_language`
  (German if `RENTALARS_LANG`, else `LC_ALL`/`LC_MESSAGES`/`LANG`, starts
  with "de"; English otherwise – so `C.UTF-8` is English) and
  `t "Deutsch" "English"`; `fail`/`warn` print "Fehler:"/"Error:"; `manage`
  passes `RENTALARS_LANG`, so management commands answer in the same
  language.
- **Migrations (UIX-029):** `accounts/0006_language_083` adds
  `User.language` (`""`, also as `db_default` for an old-state test);
  `core/0017_language_083` adds `document_language` set to the
  installation language; no data changed, no audit entries.
- **Other behaviour (UIX-029, AUT-027):** CSV yes/no values and file names
  translated; the API password reset goes through `ResetPasswordForm`, so
  invited accounts get a link too.
- **Not translated:** import column recognition (German headings; labels
  shown in English via `core.tabular.ENGLISH_LABELS`), "Sachkontenlänge"
  (DATEV term), native browser date fields.

### AI (EML-040, EML-044, ADM-017, NFA-071)

- **Own app and settings (EML-040, ADM-017):** `rentalars/ai` with
  `AISettings` (singleton), `AIProvider`, `AISummary`, `AICall`;
  `core/0019_ai_083` stays empty on purpose. `ai/0001` depends on
  `projects/0024_trips_082`.
- **Off at first (EML-040, ADM-017):** the summary use is "off" until
  "Zusammenfassungen mit lokaler KI einschalten" or a per-use choice (off /
  local AI / an interface); the draft use is off too; template
  suggestions (PRJ-091) are listed as "later".
- **Finding the local AI (EML-040, NFA-071):** `sudo rentalars ai install`
  writes `/etc/rentalars/ai-local.conf` (root, 0644) next to the
  configuration file; Rentalars reads it at every use (no restart). Only
  loopback addresses are accepted there, which is why the network guard
  lets the local AI through without `allow_internal`.
- **Typed interfaces go through the guard (ADM-017, NFA-071):** every
  `AIProvider` call uses `core.network.open_url`, even for 127.0.0.1;
  redirects are never followed.
- **Install method (EML-040):** Ubuntu 26.04 has `llama.cpp-tools`
  (8681+dfsg-1) – used there; Ubuntu 24.04 and Debian 13 have no package,
  so the command clones llama.cpp tag `b8681`, checks commit
  `506200cf8b5c…` and builds a static `llama-server` with cmake
  (`GGML_NATIVE`, no curl/openssl). Offline: `--model FILE.gguf`, or
  `register` for a server the operator already runs on this machine.
- **Models (EML-040):** below 6 GB of memory Qwen2.5-1.5B-Instruct Q4_K_M
  (sha256 `6a1a2eb6…407e`, 1.1 GB), from 6 GB Qwen3-4B Q4_K_M (sha256
  `7485fe6f…fdf5`, 2.4 GB) with thinking off; both Apache-2.0
  (Qwen2.5-3B avoided: not Apache-2.0); below 1.5 GB the command refuses.
  Context 8,192 tokens.
- **Service (EML-040):** `deploy/systemd/rentalars-ai.service` ships with
  every release (an update's `install_units` keeps it) and starts only if
  `ai-local.env` and the binary exist; 127.0.0.1, `DynamicUser`,
  `IPAddressAllow=localhost`, `Nice=10`, low CPU/IO weight; `MemoryMax` 2G
  or 5G and `CPUQuota` in a drop-in; threads = cores − 1 (1 to 8).
- **Summary job (EML-040, EML-044):** background job `ai_summary`; mails
  cut to their new text (quotes removed), at most 6,000 characters each;
  long correspondence packed into parts that fit the model, summarised,
  then the parts summarised again (up to 6 levels).
- **One summary per project (EML-040):** stores mail count and newest mail
  id; "veraltet" on a mismatch or, with the chat included, newer chat
  messages. Written in the interface language of whoever started it,
  labelled "von KI erstellt" with model, provider and date.
- **Who sees a summary (EML-040, EML-031):** a whole project's summary
  covers the parts its author could read and is hidden from readers who
  cannot read every covered part; deleting a covered mail (by hand,
  retention, anonymisation) deletes the summary (`ai.signals`).
- **Short overview without AI (EML-044):** always shown: participants,
  counts, first/last date, last writer with "noch nicht beantwortet",
  dates (German, British, ISO, month names), euro amounts, questions from
  the 3 newest mails, attachments; dates and amounts from the newest 200
  mails.
- **Rights (EML-040, ADM-017):** reading the correspondence allows reading
  and starting a summary; a draft needs the right to write correspondence
  and only its starter sees it; the settings need the Administration
  module (write to change, delete to delete an interface).
- **Interfaces (ADM-017):** API key encrypted like mailbox passwords and
  never shown again (in `SECRET_FIELDS`); timeout and context size per
  interface; the cloud warning shows when the host is neither internal,
  allowed, nor a `.local/.lan/.internal` name.
- **Reply draft (ADM-017):** "Entwurf vorschlagen" in the compose page
  runs job `ai_draft` from the thread; the draft is written in the
  language of the mail being answered.
- **Call log (ADM-017):** use, provider, model, duration, characters,
  tokens, success and error – never content; kept 365 days, pruned on each
  insert; a plain paginated table, not a `core.tables` definition (so it
  stays out of UIX-044's walk).
- **API (EML-040, ADM-017):** `GET/POST /projects/{id}/correspondence-summary`,
  `POST /projects/{id}/mails/reply-draft` (202, result in `/jobs/{id}`),
  `GET/PATCH /ai/settings`, `POST /ai/local/speed-test`, `/ai/providers`
  CRUD, `GET /ai/calls`; errors `ai_unavailable` (409).
- **Self-check (NFA-071):** AI interfaces are listed under "Verbindungen zu
  anderen Servern".
- **Backup (EML-040):** program and models under `/opt/rentalars/ai` and
  the two files in `/etc/rentalars` are not backed up; after a restore on a
  new server the operator installs again.

### Service case statuses and automations (PRJ-112, ADM-013, PRJ-109)

- **Three statuses (PRJ-112):** values `waiting`, `closing`, `backlog`
  (fit the column, no schema change for the status); German labels
  "wartet", "wartet auf Schließen", "Rückstand", lower case like the
  existing ones; badges: accent, dark, grey.
- **What a case waits for (PRJ-112):** new field
  `Project.case_waiting_for` – `reply`, `action`, `delivery` (Rückmeldung,
  Aktion, Materiallieferung), shown as "wartet auf Rückmeldung" etc.
- **Saved with the follow-up (PRJ-112, PRJ-109):** `set_case_status` saves
  status and follow-up in one transaction; waiting needs day and reason,
  closing day and time, backlog the day; a closing case keeps the time
  required when its follow-up is moved; "Erledigt" on the follow-up of a
  case in one of these statuses sets it back to "offen" with a message.
- **Browser (PRJ-112):** the status list is sent in the background; for
  the three statuses the server answers with the existing follow-up dialog
  plus the status, saved only when the dialog is sent; without script the
  dialog is a page; cancelling restores the saved status in the list.
- **Backlog off the dashboards (PRJ-112):** `service_cases.off_dashboards()`
  hides a backlog case until its follow-up is due – start page (Meine
  Servicefälle, open items), Mein Bereich → Servicefälle (filter "auch
  Rückstand"), Planung → Wiedervorlagen (filter "Auch Rückstand");
  Projekte → Servicefälle and `GET /service-cases` default to "all not
  done" (`ACTIVE_STATUSES`).
- **Times (PRJ-112, PRJ-090):** times can be recorded on every case that is
  not done (`timetracking.services.OPEN_CASE_STATUSES`).
- **Triggers and action (ADM-013, PRJ-112):** trigger `case_follow_up`
  (with an optional case status), trigger `case_communication` (mail
  received or sent, a mail moved into the case by hand, a new chat message;
  limitable by kind via `Automation.communication` and by status); action
  `case_status` with `Automation.new_case_status` limited to open, in
  progress, done (the other statuses need a follow-up).
- **Loop protection (ADM-013):** automatic replies, delivery failures,
  edited chat messages and anything happening while a rule runs are not
  "communication"; setting a status starts no other rule; before a run is
  carried out it re-checks status and, for a due follow-up, its day and
  time – a change makes the run "skipped" with the reason.
- **Placeholders (ADM-013):** `{status}` and `{link}` refer to the case;
  new `{kommunikation}` / `{communication}`.
- **Default rules (ADM-013):** three active rules created by
  `automations/0002_cases_083` for existing and new installations, named in
  the installation's language: (1) follow-up due while closing → done,
  follow-up removed; (2) communication while closing → open, follow-up
  kept (a plain reminder then); (3) follow-up due while backlog → open.
  Logged "Aktualisierung" by ID on existing installations; not added
  twice; reversible.
- **Follow-ups without anybody to notify (PRJ-112, PRJ-109):**
  `notify_due_follow_ups` marks a service case's due follow-up processed
  even with no follow-up user or responsible person and fires
  `follow_up_due` and `case_follow_up_due`; only the notification is
  skipped.
- **No reminder when the rule closes (PRJ-112):** while an active rule
  (trigger `case_follow_up`, status `closing`, action `case_status`, new
  status `done`) exists, no follow-up reminder is sent for a closing case
  (`_closing_rule_active`, one query per timer run); a backlog case gets
  its reminder as usual.
- **API (PRJ-112, API-002):** `PATCH /service-cases/{id}` takes
  `case_status` with `follow_up_on`, `follow_up_at`, `follow_up_user`,
  `follow_up_note` (and `case_waiting_for` for waiting) – 400 without;
  follow-up fields alone set just the follow-up; `case_waiting_for` alone
  is refused; `POST` sets a follow-up if given, a new case is always open;
  read-only `case_status_label`; `/automations` gains `communication` and
  `new_case_status`.

### Grouping by every shown column (UIX-044, UIX-040)

- **Every shown column groups (UIX-044):** `Column.groupable` is true
  unless the column has `ungroupable` or `unsortable` (buttons, tick boxes
  – `actions`, `choose`, `record`); `TableDefinition(ungroupable=…)`
  removes "Group by" from a table with a reason (time approval: one form
  per project; hours report sums: already groups). A test walks every
  `TableDefinition` and asserts each shown column groups or says why not.
- **Database where possible, Python otherwise (UIX-044):** a column showing
  one model field groups in the database; computed, multi-valued and
  annotated columns group in Python by the value shown (`_shown_value`) up
  to `PYTHON_SORT_MAX_ROWS` (2,000); longer lists stay ungrouped with a
  notice in the `sort_notice` slot. Annotations cannot be a database path
  because the counting query runs on the plain model.
- **Group order (UIX-044):** a group stands where its first row stands when
  sorted by that column (one extra `pk` query for database-sorted
  columns); inside a group the chosen sort stays.
- **Dates and periods (UIX-044):** moments group by local day
  (`grouped_by_day(path)`), a period by its first day, a follow-up by its
  day.
- **Only shown columns are offered (UIX-044):** `group_choices()` lists the
  shown columns in their order, plus the chosen column if it was hidden
  since (a bookmarked grouping keeps working).
- **Master data (UIX-044, UIX-040):** every shown column of the Django
  master-data lists groups – a field by itself, a computed column by its
  `admin_order_field` annotated as `table_group_value` (e.g. the tree path
  of categories and storage locations); headings use `display_for_field`.
- **MariaDB (UIX-044):** grouping by `TEXT` columns relies on
  `max_sort_length` and is case-insensitive there, as the existing
  grouping by city.

## Part 20: Wishes and the companion app

The requirements: take up the requirements of the companion
app (the change time per field, then seven further points),
hour lines in the timelines that miss the hours between about 1236 and
1920 px, shortage notifications with time of day, interval and lead time,
the first tab of a service case called "Überblick", a "Funktion" choice
that can be empty, surcharges only for crew lines, a menu that slides in on
the phone as in the app, and an identical correspondence tab with its box
called "Zusammenfassung". Plus an AI test on a virtual machine (Ubuntu
26.04, 4 cores, 8 GB, qwen3-4b chosen): 10–29 s for a
speed test and a summary of 1,979 characters failing after 600 s.
The catalogue gained SOLL · S8 PRJ-113, PRJ-114, API-015, API-016, VFG-036,
UIX-045, EML-050; amended VFG-033, PRJ-090, ZEI-007, PER-009, PER-040,
EML-040, ADM-017, UIX-029. The decisions below are those of the build,
checked against the code.

### Scope and decisions

- **Crew packs (PCK-013, decided):** the crew may do everything that implies
  writing but has no financial effect; it keeps to the packing list exactly,
  and extra material must be added by authorised people. The role Crew gets write on packing; only adding
  material while packing is gated (below).
- **UIX-045 from the right, phone only:** an earlier draft said "from the left"; it was
  corrected; the drawer exists only up to 900 px, the breakpoint where the
  top bar with the menu button already appeared.
- **"Mail schreiben" on the service case page (EML-050, EML-024, EML-047):**
  the "Latest mails" panel asks the same as the Correspondence tab –
  both correspondence rights (`may_write_mail`) and a mailbox that can send
  this mail (`mailboxes.can_send_from(case)`); a service case may send
  through the mailbox of its "only for service cases" address even without
  the general outgoing mailbox.
- **Sync replays keep their reason (PCK-027):** `SyncReceipt.reason`
  (packing 0007) stores the reason code of the outcome, so a refused change
  sent again with the same change ID gets `reason` back, not only outcome
  and message.
- **Open question (ZEI-026, API-016):** "Meine
  Zeiten" in the browser shows entries of a crew line with a flat rate by
  the hour, while the API calls them `pay_kind: flat`; where a flat amount
  belongs in a weekly sum is undecided, so the web is left alone and the
  manual does not mention it.
- **AI refresh (EML-040):** `ai refresh` is
  run by the update and by `rentalars-ai-refresh.timer`; `update.sh`
  carries no reminder to run `ai install` again.

### Companion app: change times per field (PRJ-113, PRJ-114, API-016)

- **One JSON column (PRJ-113):** `Project.field_changed_at` maps an API key
  to a UTC ISO moment; no extra queries on lists; service cases use the
  same column, so PRJ-114 and PRJ-113 share one mechanism.
- **Keys (PRJ-113):** the nine the app needs – `name`, `venue`, `start`
  (material out from), `end` (material back by), `event_start`,
  `event_end`, `notes`, `status`, `follow_up` (= `follow_up_on`,
  `follow_up_at`, `follow_up_note`, `follow_up_user`) – plus every other
  field PATCH can change (`customer`, `is_internal`, `contact`,
  `billing_address`, `delivery_address`, `venue_site`, `manager`,
  `rental_days`, `case_contact`); `case_status` covers `case_status` and
  `case_waiting_for`.
- **Central stamp (PRJ-113):** `Project.save()` calls
  `projects.field_changes.stamp()`, comparing the values as loaded (the
  audit load snapshot) or last saved with those being written, only
  `update_fields` when given; instants are compared, so the same moment in
  another zone is no change; a hand-built project is compared with its
  row. Covers forms, API, automations, imports, status actions, the
  follow-up dialog, packing setting the status and converting a case.
  `QuerySet.update()` bypasses it; the only such update writes the
  untracked `follow_up_notified_at`.
- **Clock rule and lock (PRJ-113, PCK-027, API-010):** a sent field counts
  only if `changed_at` is later than its stored moment; equal → the server
  wins; a future moment counts as now, the clock read once the lock is
  held (the API-010 lock row `record:projects.project:<pk>` plus `SELECT …
  FOR UPDATE`). An accepted field stores the phone's moment even if its
  value is unchanged; a stored moment never goes back.
- **Answer (PRJ-113):** always the project as it is now; `applied` lists
  the keys taken and appears only when a change time was sent. Without
  `changed_at` every answer is the ordinary one (If-Match etc.).
  Fields that do not count are dropped, the rest validated like a normal
  PATCH (400 stays 400).
- **409 for status (PRJ-113):** a status change no longer allowed gives
  409 with the project, `applied: []` and `error.code`
  `status_not_allowed`; an unknown status or a service case on
  `/projects/{id}/status` stays 400; the same status with a later time
  counts as applied.
- **DELETE follow-up (PRJ-113):** `changed_at` in the query string or the
  body; an unencoded `+` arriving as a space is read as meant.
- **Service cases (PRJ-114):** `case_status_changed_at` is the same value as
  `field_changed_at.case_status` and judges status, `case_waiting_for` and
  the follow-up sent with it as one unit, so a status that needs a
  follow-up never half-applies; `changed_at` judges each field (also the
  status unless `case_status_changed_at` is sent); no 409, as any status
  order is allowed.
- **Start values (PRJ-113, PRJ-114):** there is no `updated_at` on Project;
  projects 0026 takes, per key, the last change-log entry that really
  changed one of its fields, else `created_at`; no log entry for this
  (bookkeeping, as the packing change times). `bulk_create`
  projects fall back to `created_at`.
- **Deployment view (API-016):** `manager_name` and `venue_label` on
  `/projects`, also with access "deployment", which shows
  `field_changed_at` only for the fields it shows; `manager_name` on
  `/service-cases`.
- **Module `email` (APP-001):** nothing to change on the server – the app
  chooses its token's modules on `POST /tokens`; a token limited to
  packing, projects, time_tracking and email reaches chat, mails, price
  overview, `/mail/unknown` and service cases (tested).
- **ETag (API-010):** answers gain fields, so an ETag stored before the
  update fails once with 412 on If-Match.

### Companion app: own data (API-015, API-016)

- **Person change times (API-015):** four columns `phone_changed_at`,
  `email_changed_at`, `share_phone_changed_at`, `share_email_changed_at`,
  set by `Person.save` only for fields that really changed (browser form,
  person form, API, imports, an e-mail change through the account); only
  anonymisation bypasses `save`. Start value: the last logged change of the
  field, else the person's creation (personnel 0013).
- **Same clock rule (API-015):** later wins, equal → server, future → now,
  clock read under the API-010 lock plus a lock on the person row;
  `changed_at` is one moment for all sent fields or `{"phone": …}` per
  field; fields without a time are taken as before.
- **Validation as in the browser (API-015):** `OwnProfileForm`; an e-mail
  of another account gives 400 on `email`; unknown fields 400; a read-only
  token 403 on every write.
- **Profile shape (API-015):** an `updated_at` object keyed by field (H's
  shape); job functions with rates only when the person may see them
  (`rates_visible`); qualifications with `valid_until` and `state`.
- **Absences (API-015):** from 30 days back; `Idempotency-Key` through the
  existing middleware.
- **Deployments (API-015):** `personnel/own_api.py`; the `/projects` ID
  convention kept (`project.parent` an ID with `parent_number` and
  `parent_name`; `job_function` plus `job_function_name`; `phase` plus
  `phase_label`); additive `project.is_service_case` and `state`;
  `venue_label` exactly as "My deployments" (phase venue, project venue,
  phase place, project free text); `from`/`to` take a day or a moment, a
  day as `to` counts to its end; no paging; ETag/304 from the middleware.
- **Server version (API-016):** `server_version` in `GET /me` and in the
  login response.
- **Notifications (API-016):** `unread` counts within the `category`/
  `companion` filter; new `unread_total` for the bell;
  `?companion=1&unread=1` pages through older unread ones.
- **Pay kind (API-016, ZEI-026):** `pay_kind` (`hourly`, `daily`, `flat`)
  and `in_day_rate` only where rates are visible; flat takes precedence
  over daily as for crew-line costs; "in the day rate" computed with one
  query per list.

### Timelines and the phone (VFG-033, UIX-045)

- **Hour lines, cause (VFG-033):** Chromium sizes a repeated background
  tile in 1/64 px and rounds it; the error adds up along up to 840 hour
  tiles (measured up to 5.0 px off at 1600 px, 1366 px happened to be
  almost exact).
- **Hour lines, fix (VFG-033):** each row draws day, column and hour lines
  as one `repeating-linear-gradient` over the whole row, no tiles; the hour
  head draws its lines as one `::after` layer over the second grid row,
  labels above it, cell borders stay the column lines. Tiles counted from
  the outer edge and a gradient per cell were tried and lost lines in
  fractional cells. Result within 0.5 px at 1236–1920 px for 2–7 days; the 8 px threshold unchanged.
- **Drawer look (UIX-045):** width min(300 px, 86vw), over the whole page
  including the top bar; backdrop black at 55 % × progress; 220 ms easing
  out, shortened to the distance left after a swipe; no animation with
  `prefers-reduced-motion`.
- **Drawer content (UIX-045):** the side navigation itself; its head shows
  logo, name and company with the close button where the menu button was;
  `.sidebar-company` is hidden inside it.
- **Swipe (UIX-045):** touch listeners only up to 900 px; follows the
  finger after 10 px sideways; on release by speed (≥ 0.4 px/ms, the
  Android drawer threshold), else by more than half open; never starts on
  something that scrolls sideways, has its own touch handling (maps), a
  slider, drag handles, timeline bars, the availability week, or while a
  dialog is open.
- **Back (UIX-045):** a history entry while open, so Back closes the menu;
  a link or the search form in the menu replaces that entry
  (`location.replace`); logout (POST) is not handled.
- **Focus (UIX-045):** the rest of the page is `inert`, Tab wraps inside,
  focus goes to the close button and back to the opener; growing past
  900 px closes the menu at once; `body.nav-open` stays the one switch, so
  menu button, magnifier and "/" code are unchanged ("/" now also opens a
  hidden menu).

### Service case and correspondence (PRJ-090, EML-050)

- **Tab name (PRJ-090):** msgid "Overview" with context "service case tab"
  (German "Überblick"); the panel heading and the "Servicefall" badge stay.
- **Correspondence (EML-050):** projects and service cases already shared
  view, template and summary block (a UI test now checks the pages are
  identical apart from IDs); the difference was the short overview open
  without an AI summary. It is now always closed on load and stays as the
  reader left it while the block refreshes every 3 s during a run. Box
  heading "Summary" ("Zusammenfassung"); the AI part has a hidden heading
  "Summary by AI" plus the visible badge "made by AI".

### Time tracking, surcharges, labels (ZEI-007, PER-009, PER-040, UIX-029)

- **Why the choice was empty (ZEI-007):** it held only the person's own job
  functions and own crew lines in the project; a person with neither got
  nothing, with or without phases.
- **New rule (ZEI-007):** own and planned job functions first, then those of
  the project's other crew lines and open places (a whole project with its
  parts), and only if that leaves nothing every active job function, as on
  service cases; without a project own ones, else all active. The same in
  the form, the save check and `/time-entries/choices` (never empty). Rate:
  own, else the crew line's, else the guide value.
- **Surcharges audit (PER-009):** calculation, price overview, documents and
  the API line breakdown already applied surcharges to hourly crew lines
  only; the settings texts and the product switch (stored and shown for
  every product kind) suggested otherwise. Fix: plain texts, the switch for
  services only; other products return `time_surcharges: null` and a sent
  value is ignored (form too). Settings labels set in the form, so no core
  migration for them.
- **English labels (UIX-029):** "debitor" → "debtor"; DATEV Beraternummer
  and Mandantennummer stay in brackets; "packlist" → "packing list";
  "Night 0–4" for the § 3b preset (masterdata 0011 renames the stored
  English rule by code and exact old name, logged); "crew disposition"
  left as is (its rename needs a core migration).

### Packing with the role Crew (PCK-013, PCK-026, PCK-027)

- **Rule (PCK-013):** `packing.services.may_add_material` = write on
  packing for all projects or edit access to the project; Lager and
  Projektleitung keep "add material while packing".
- **Classification (PCK-013):** gated is only adding material (it creates a
  charged line); allowed without a financial effect: tick and scan, choose
  items, issue, undo issue, take back, complete the return, clarify missing
  parts (a note), report defects, create/rename/delete packing lists (lines
  go back to the first list), move lines, handovers (charged once at the
  source), taking items out of containers. Ticking is capped at the list
  everywhere. Handovers and container extraction are classified from the
  code, not exercised by Crew tests.
- **API and app (PCK-026, PCK-027):** add-material without the right → 403
  `needs_project_write`; the sync refuses a packed quantity above the list
  with reason `needs_project_write` (message names who may add material) or
  `above_packing_list`, other changes still apply; `/offline/packlists`
  gains `can_add_material`.
- **DELETE on packing (PCK-013, API-002):** packing list, handover and
  extraction need write on packing (`PacklistView.action_levels`) instead
  of the level "delete" other modules ask, as in the browser; Lager can now
  delete packing lists through the API.
- **Migration (PCK-013):** accounts 0007 raises "Crew" from read to write
  only where it still had read, changes its start description only with
  that, logs each change as "Aktualisierung", and notes every other
  role with packing write in assigned projects only and no project write
  as event `role.no_material_while_packing`; reversible.

### Shortage notifications (VFG-036)

- **Where (VFG-036):** a company setting, `NotificationSettings`
  (`core/notification_settings.py`, singleton), page Einstellungen →
  Benachrichtigungen (`notifications:company_settings`, Administration
  read/write), API `GET`/`PATCH /settings/notifications` (flat fields plus
  `shortage_next_check`); the companion token gets 403 there.
- **Which timer (VFG-036):** the minute timer `run_jobs`
  (`rentalars-jobs.timer`), which every installation has; the time lives in
  the database, so no unit is rewritten and nothing needs root (the
  application could not rewrite `OnCalendar` without it). The nightly
  `run_daily_maintenance` does not check. A quiet minute costs one query.
- **When due (VFG-036):** `notifications/schedule.py`: due when the latest
  scheduled moment (`latest_slot`) is later than the last check; a check
  missed while the server was off is made up once (as `Persistent=true`);
  the moment is claimed by a conditional UPDATE, so only one run checks.
- **Changing the schedule (VFG-036):** time, interval or weekday changed
  (page or API) starts from the next moment; a time already past today is
  not made up.
- **Migration (VFG-036):** core 0020 only creates the row; the first
  minute notes its moment, so the first check is the next 4:15
  (noting it in the migration started checks in other tests).
- **Settings (VFG-036):** interval daily / working days (Monday–Friday
  without the holidays of Einstellungen → Zuschläge, read without creating
  that row) / weekly on a weekday / off; lead 1–26 weeks, default 4;
  `shortage_repeat` default off keeps "each shortage once, again if it
  grows or comes back", on reports every open shortage ("Still a shortage
  in …").
- **Forgetting (VFG-036):** only shortages of projects actually looked at
  are forgotten; one reported for a project now beyond the lead time stays
  known. The delete uses two plain queries (MariaDB refuses a DELETE whose
  subquery reads the same table).
- **Bookkeeping fields (VFG-036):** `shortage_last_run`,
  `shortage_checked_at`, `shortage_reported` are written only by the check
  (queryset updates), never by saving the settings, and are not audited.

### Local AI: speed (EML-040, ADM-017)

- **Diagnosis (EML-040):** a reported 1–3 tokens/s points to a virtual machine
  with the default processor type (`x86-64-v2-AES`, no AVX2/FMA); the
  summary failed because it waited at most 600 s for the whole answer.
- **Thinking off (EML-040):** checked against the 26.04 package (llama.cpp
  8681, man page and binary strings): `ai install`/`refresh` pass
  `--reasoning off --reasoning-budget 0` when `llama-server --help` lists
  them; Rentalars also sends `enable_thinking: false` and "/no_think"
  (local AI and Qwen models), `reasoning_effort: "none"` for a registered
  server; `<think>…</think>` and `reasoning_content` never reach the text;
  a server answering 400 to these fields gets the request once more
  without them.
- **Streaming with a silence limit (EML-040):** summaries and drafts stream
  (SSE); local AI 180 s without a word; before the first word 3 × the
  estimated reading time + 60 s, or 30 minutes unmeasured; a provider's
  timeout now means silence; the task stops at 3 × its upper estimate (at
  least 10 minutes, 3 hours unmeasured); progress in the job at most every
  2 s; `max_tokens` lowered to 700 final, 450 parts, 500 draft.
- **Measured speeds (EML-040):** `ai/speed.py`; the speed test sends a
  ~400-token prompt without the prompt cache and reads llama-server
  `timings` for reading and writing apart; every later local call updates
  both, writing only those fields.
- **Estimate (EML-040):** before a summary ("dauert etwa N Minuten", a
  warning above 5 minutes); `estimate` in the API.
- **Processor (ADM-017):** `ai/cpu.py` reads `/proc/cpuinfo` (physical and
  logical cores, AVX2/FMA, VM flag); `ai install`, `ai status` and
  Einstellungen → KI warn with the Proxmox "host" hint; threads = physical
  cores, at most 16.
- **Model choice (ADM-017):** Qwen3 4B only with ≥ 6 GB, ≥ 4 physical cores
  and AVX2/FMA (or an ARM64 server that is not a Pi), else Qwen3 1.7B
  Q4_K_M (ggml-org's conversion, because Qwen offers only Q8_0 at that
  size; Apache-2.0, SHA-256 `d2387ca2…c7b5`, 1.28 GB); `--model
  qwen3-1.7b|qwen3-4b|qwen2.5-1.5b`; a built llama-server (b8681) is kept;
  the previous model file is deleted once the new one runs, unless
  `--keep-model`.
- **Recommendation (ADM-017):** the smaller model below 6 tokens/s writing
  or 30 tokens/s reading, or without AVX2/FMA, with the command to copy;
  changing the model stays the operator's command (root).

### Local AI: refresh (EML-040, NFA-071)

- **Why a timer (EML-040):** `rentalars update` runs the `update.sh` of the
  *installed* version, so an update never calls the new refresh;
  `rentalars-ai-refresh.timer` (`OnActiveSec=1min`) runs it about a minute
  after it is switched on – when the updater enables the new
  version's timers, and at every boot (which also covers a VM whose CPU
  type was just changed). `update.sh` runs `ai.sh refresh || true`
  after the old releases are cleared, not on rollback.
- **What refresh does (EML-040):** only for an AI installed here
  (`server_kind = llama.cpp`, or an older file with `ai-local.env`); rereads
  the processor, rewrites `ai-local.env` and the limits drop-in (threads,
  the options `--help` lists, `MemoryMax`), adds `server_kind`,
  `physical_cores`, `threads` to `ai-local.conf`, restarts `rentalars-ai`
  only if something changed and waits up to 120 s; prints one line; a
  lock against the update and the timer meeting; any failure warns and
  exits 0; `--dry-run`.
- **What it never does (EML-040):** download, build, apt-install or change
  the model; it only hints (`ai install --model …`, the "host" hint,
  `ai install --rebuild` for a build without AVX2 on a CPU that now has it
  – recorded as `built_with = package|avx2,fma|…|none`; the Ubuntu package
  picks its CPU variant at each start, older builds have it empty).
- **Security model (NFA-071, since stage 4):** `rentalars-ai-refresh.service`
  runs `/bin/bash /opt/rentalars/app/deploy/ai.sh refresh` as root, like
  the backup service runs its script from the application directory, only
  if `/etc/rentalars/ai-local.env` exists; it never downloads, and
  Rentalars itself never gets root.
- **Rollback (EML-040):** going back removes the refresh units;
  the options in the env file stay valid because llama-server is unchanged.

### Data migrations

- projects 0026 (field change times), personnel 0013 (person change times),
  accounts 0007 (Crew packing, role texts, logged), packing 0007 (labels,
  `SyncReceipt.reason`), documents 0005 (labels), masterdata 0011 ("Night
  0–4", logged), core 0020 (`NotificationSettings`, surcharge help text),
  ai 0002 (speed fields, timeout help text). No price, cost, sum or status
  changes.

### Not done or not verified

- Not run on MariaDB for this item (the full suite covers it); scenario 11
  time limits failed only under load and are to be rerun on a quiet
  machine.
- Not run for real: llama-server 8681 with `--reasoning off`, the shape of
  its `prompt_progress` events, Ollama's `reasoning_effort: "none"`, the
  refresh timer under real systemd, a real `rentalars update`,
  real speeds on a real VM.
- The drawer was tested in Chromium with emulated touch only – not on a
  real phone, iOS Safari or Firefox.

### Fixed after the independent review

- **Reading before the silence limit (EML-040):** `ai/client.py` `_receive` keeps the first-word budget as the
  read timeout while only `prompt_progress` events have come; the silence limit applies from the first content
  or reasoning token. Before, the first progress event lowered it to 180 s and a slow server was cut off while
  still reading.
- **Echo of `case_status_changed_at` (PRJ-114):** a value equal to the stored instant counts as not sent, so a
  client that sends the case back as `GET` gave it changes the status as before; empty follow-up fields
  on a case without one count as not sent too. `changed_at` keeps "a tie goes
  to the server" (PRJ-113).
- **Root trust in `deploy/ai.sh` (EML-040):** the refresh lock is in `/run` (root only), not `/run/lock`;
  `root_only` and `trusted_binary` make `install` and `refresh` run `llama-server --help/--version` and write
  only where the program and every folder above it belong to root alone; otherwise they change nothing.
- **Login e-mail through a scoped token (API-015):** `PATCH /people/me/profile` changes `email` only for a
  session, a token without module limits or a token including the module `email`; others get 403
  `token_scope`, `GET` says `email_editable`. Phone and share flags stay open to every writing token. There is
  no notice to the old address yet (Rentalars has none for e-mail or password changes).
- **Sync replay (PCK-027):** `SyncReceipt.reason` keeps the reason code, so a change sent again gets
  `needs_project_write`/`above_packing_list` again.
- **Service case panel (EML-050):** "Mail schreiben" uses `mailboxes.can_send_from(project)`, as the tab
  does; a service case may send through the mailbox of its own address without the general outgoing mailbox.

## Part 21: Wishes from practice

Requirements: reminders of invoices – or a
"Rechnung gestellt" tick when another program writes them –, ideas for
monthly invoices of service cases, price and costs per hour asked in the
first-run setup, profitability, what each item earned against its
purchase price, net or gross prices, "#0802" and "#0851" in the material
import, the model on the item page, three labels in the layout of given
label templates (`.lbx`) printed from the
browser, legacy in the URL paths, the logistics written into the
catalogue, a service case (or only an inquiry) of a defect report as an
automation, the settings sorted, a roomier foot of the sidebar; then
configurable logo, names, QR code, phone, URL and text of the labels,
notes in the correspondence and the AI summary folded; then action bars
that appear only when rows are ticked. The catalogue gained SOLL · S8
DOK-015, ADM-018, PRJ-115, MAT-053 to MAT-057, IMP-014 to IMP-016, UIX-046
to UIX-048, EML-051, NFA-074; KANN · S10 DOK-016; chapter 5.17 (LOG-001
to LOG-018) as stage 9 (logistics); also MAT-023, MAT-026, ADM-013, PRJ-090, EML-042, EML-050.

### Scope

- **Everything is stage 8, SOLL** and built. The monthly invoice of
  service cases is an idea only (DOK-016, KANN, ideas in catalogue 12.2
  no. 29 j). The logistics is written down, not built (stage 9; its
  assumptions are 12.2 no. 30).
- **UIX numbers:** the settings are UIX-046, the sidebar UIX-047, the bulk
  bars UIX-048.

### Invoices (DOK-015)

- **Invoiced is calculated, not stored:** with invoices made in Rentalars a
  valid invoice (not cancelled) of the whole project; with invoices off the
  mark `Project.invoice_status = issued`. `not_needed` ends the reminders
  either way. The mark can be set with invoices on as well (API, for
  invoices of the time before Rentalars); the page shows the tick box only
  while invoices are off and an "Undo" for a mark set otherwise.
- **Which projects:** whole projects with a customer, not internal, closed;
  service cases only with "service cases too" (done = closed). Reminded
  only with a net total above 0 (`list_sums._prices_of`, one batch for the
  due projects) and only if closed after `invoice_reminders_since` – the
  migration sets it to the moment of the update; without it every closed
  project of the years before would be reminded of at once. The moment of
  closing is `field_changed_at["status"]` (PRJ-113).
- **When:** the minute timer (`run_jobs`), like the shortage check: claimed
  by a conditional update of `invoice_last_run`, made up once after a
  downtime, the first run after the update only notes its time. First
  reminder `invoice_first_days` after closing, then every
  `invoice_every_days` with five minutes of slack; `InvoiceNotice` per
  project; closed again after reopening starts anew.
- **Whom:** the project manager and `invoice_user`, only those with the
  price right – only they can make the invoice or set the mark.

### First-run setup (ADM-018)

- 45.00 € and 30.00 € proposed, never 0; written only where the start data
  have none (service product price, `guide_cost_rate`). Existing
  installations are untouched.

### Profitability and item revenue (PRJ-115, MAT-053)

- **Nothing stored.** `projects/profitability.py` calculates with
  `projects.pricing` in chunks of 200 projects, like the project list's sums
  (PRJ-085). Whole projects with their parts, statuses from "Bestätigt –
  Einzelheiten offen" on, counted in the month of `end`; service cases left out.
- **Rights:** the pages need the module "Reports" (AUT-014 – listed as
  "later stage" in the roles since stage 1, now in use; Administrator,
  Projektleitung and Nur-Lesen carry it), READ on projects everywhere and
  the price right (`projects.access.may_see_reports`); the item's box
  "Ertrag" and its API too, as they add up the projects of all customers.
  Subrental costs need purchase prices, crew costs personnel costs, the
  profit both – a figure the reader may not see is left out, never shown
  as 0. The page has one column "Kosten", so it shows costs, profit and
  margin only with both rights and says so; CSV and API split them by
  right. The CSV writes names through `csv_text` (no formulas).
- **What a line earned:** its share of the net total after its own discount
  and its groups' (flat prices spread by `GroupPrices.shares`); optional,
  alternative, customer material and taken-over lines earn nothing; a kit's
  line is shared out to its components by their prices (evenly without
  prices).
- **What an item earned:** "assigned" – a piece per allocation issued
  (not via a handover, not inside a container); the rest of the pieces is
  shared out over the items the product had at the project's end,
  weighted by quantity ("estimated"). Only projects whose material went
  out. A set is compared as a set (MAT-054).
- The item's box loads after the page (`hx-trigger="load"`), as it reads
  every project the item went out with.

### Purchase sets and import (MAT-054, IMP-014 to IMP-016)

- `MaterialItem.purchase_price_in` (self, `SET_NULL`): no own price, the
  head has one and points nowhere – no chains, no cycles; deleting the head
  leaves the members without price, as before.
- The import resolves "#0851" in a third pass after all rows are known
  (`_resolve_purchase_sets`); the head may be in the file or in the stock.
  Gross prices are divided by 1 + rate and rounded to cents; the options
  are part of the import kind (`core.imports.ImportOption`), so the page,
  the API and the command share them.

### Labels (MAT-056)

- **The layouts are those of the `.lbx` files:** positions and sizes in
  points read from the templates (`label_layouts.py`), texts fitted to
  their boxes with the metrics of Barlow (fontTools) – the font of the
  templates is not free to ship. One HTML template serves the PDF
  (WeasyPrint) and the browser; the browser page opens the print dialog
  itself (`label-print.js`) with `@page` in the exact size, one label per
  page; up to 240, more as PDF in the background.
- **Settings** in a singleton `LabelSettings`; empty fields take the
  company's data at print time, so a changed company address shows at
  once. The QR target needs `{id}` and http(s); empty is the item's page
  (`/m/0042`). The migration fills only the words in front of phone and ID,
  in the language of the documents.

### Defect report → service case (MAT-057, ADM-013)

- **Heard by a signal** on `material.DefectReport` by model name, so
  `material` imports nothing upwards; every way of reporting (page, return,
  API, app) is caught; one event per report.
- **Default rule active** on every installation (the requirement: create a service case
  directly, changeable as an automation).
- **The case:** internal for own material, the owner's for customer
  material; title and description by default or from the rule's
  placeholders; the reporter is "Gemeldet von"; the photo is copied into
  the case's files (a failure there does not stop the case). One case per
  report – checked by `defect_cases.case_of`, not a constraint, so an old
  case of a deleted report stays.
- **Inquiry instead:** an `UnknownTagMail` with `defect_report`; it is never
  taken over like a mail (`assign_unknown` raises), never a project
  (`inquiries.inquiry_of`, `projects/api._inquiry` exclude it), and becomes
  a case through the existing "Als Servicefall" (`create_from_inquiry`).
  A case made first takes a waiting inquiry off the list.

### Notes in the correspondence (EML-051)

- **A `ProjectMail` with `direction = "note"`**, not a table of its own:
  list, conversation, overview, AI summary, moving to another project,
  retention and anonymisation all work on mails already; the guards are in
  the few places that assume a real mail (answer, mail detail, API document,
  automations, overview counts). A note's time may lie in the past, never
  more than five minutes in the future.
- **Who:** writing needs the correspondence write right (as sending, but no
  mailbox); changing or removing the writer or whoever may edit the
  project. `mail_delete` therefore checks after loading the project (404
  before 403 for a project the user cannot see).

### Interface (EML-050, UIX-046 to UIX-048)

- The AI summary is a `<details>`, open only on the GET right after the job
  finished (`just_written`).
- The settings boxes flow in CSS columns (`column-width`), so boxes of
  different heights leave no gaps; the order in the HTML stays the reading
  order.
- The bulk bar is the form itself, `hidden` until a box is ticked
  (`[data-bulk-bar]`, also restored on `pageshow`), `position: sticky` at
  the bottom like the planning's chosen lines; without scripts it shows
  below the list as before.
- Lists with such a bar: items and Projects → Inquiries. The approval of
  expenses (time tracking) keeps its buttons below each project: its boxes
  are ticked when the page opens, so a bar shown "only when ticked" would
  always be there – and the buttons belong to the project above them.

### Addresses (NFA-074)

- **Moved without redirects:** the requirement was to remove legacy; a redirect
  table would be new legacy. Stored notification links are moved by
  `notifications 0010_addresses_085`; the paths in Python code are made
  with `reverse()`. The API keeps its paths (`/mail/unknown` …) – the app
  and other programs depend on them.

### Fixed after the independent review

- **OpenAPI of `POST /projects/{id}/status` (PRJ-008, PRJ-113):** the new
  `invoice-status` action had been put between `set_status` and its
  `@extend_schema`, so the status change was described with the body of a
  project and the invoice state with `StatusChange`. Each action has its own
  description again (`test_status_and_invoice_status_are_described_apart`).
- **`POST /labels` without `format` (MAT-056):** gives the A4 sheet of 24 as
  before; the pages suggest the label of Einstellungen → Etiketten. A
  program gets the new labels by naming `small`, `large` or `cable`.
- **First invoice reminder (DOK-015):** counted in days of the calendar –
  the check runs once a day, so a project closed at 17:00 is reminded of at
  the next morning's check, not a day later; "0" is "at the next check".
- **Service cases in the reminders (DOK-015):** a case has no lines, so "a
  net total above 0" left every case out. What there is to charge on a case
  is the work recorded on it – times or expenses not rejected.
- **Customer of an internal case (MAT-057, PRJ-090):** `update_case` with a
  customer and without `is_internal` makes the case the customer's; before,
  the customer was dropped silently (the app does not know "intern").
- **Closed earlier (DOK-015):** `projects 0027_invoice_085` marks every
  project closed (every case done) at the update `earlier`: neither "open"
  in the list and its filter nor in the head of the project – nobody knows
  whether its invoice was written elsewhere. An invoice made in Rentalars
  still shows; a change of the status ends the mark (`Project.save`). The
  API's `invoice_state` is `null` for them.
- **Who is reminded (DOK-015):** only who may also read the project – a
  person of the settings limited to assigned projects is not told the names
  of others.
- **Set of an item without the purchase-price right (MAT-054, AUT-019):**
  the field "Price included in" is left out of the form and of the API
  (`restricted_fields`), as the purchase price is.
- **One case per defect report (MAT-057):** `create_from_defect` locks the
  row of the report (`select_for_update`) before it checks for a case.
- **Bulk bar without scripts (UIX-048):** a `<noscript>` style shows it, so
  the actions stay reachable.
- **Smaller ones:** the mail log's `direction` filter lists received and
  sent only; the report endpoints describe their answers; the CSV of the
  profitability writes names through `csv_text` and the date as the other
  exports do; "Settings → Labels" instead of German words in an English
  text.
- **Left as it is:** going back from `notifications 0010_addresses_085`
  maps `/projects/inquiries/<pk>/…` to `/mail/<pk>/…`; notifications link
  to the list only, so no stored link is affected.

Found by measuring on the full amount of test data (MariaDB): the material
tab of the reports read 20,000 items as objects (2 s); it reads plain values
now (0.1 s). The choice of the person for reminders computed the rights of
every user with a query each; the roles are fetched at once now.

## Part 22: Stage 9, the logistics, and wishes

Requirements: build stage 9 (the logistics), with the
monthly invoice of service cases and the import as a preview, take over
the ideas for the monthly invoice, show the revenue of an item also on
the material model, summed over its items; and, while building, inquiries
must also be creatable by hand. Five rounds of questions settled the open points
(catalogue 12.1, "Wünsche und Entscheidungen"). Catalogue:
stage 9 with 30 requirements – LOG-001 to LOG-019, DOK-016, IMP-011,
EML-026, EML-052, EML-053, MAT-058, ZEI-028, AUT-030, DOK-018, NFA-075;
EML-003 fulfilled by EML-052; stage 10 has DOK-017 (contract per
customer) and EML-054 (text blocks per mailbox).

### Vehicles are items (LOG-002)

- **Decided: items of a material model.** A vehicle is a
  `MaterialItem` of a model whose product has the new kind `vehicle`;
  `material.Vehicle` (one-to-one) holds licence plate, seats, licence
  class, towing capacity and weight. Inspections, blocked periods, defects,
  files, labels and the timeline needed nothing new; HU and UVV are
  inspection types.
- **Not stock:** `ProductKind.MATERIAL_KINDS` (rental, sale, kit,
  subrental) replaces `STOCK_KINDS` where products are chosen for material,
  and the availability engine never sees vehicles. Their availability is
  the overlap of bookings, as for people – pointed out, never prevented
  (LOG-004). A vehicle product as a material line is refused with a hint
  to "Logistik".
- **Category FZ "Fuhrpark"** in the start data and, by `masterdata
  0012_fleet_090`, on updated installations unless a main category with
  that code or name exists (nothing renamed).
- **Moving a model kept as material into the fleet** (LOG-016) makes a new
  product of kind vehicle (next free number of the category, the old
  product's name, unit, tax, scale and maximum discount) and leaves the old
  product and its lines alone; open projects that still plan it are named,
  as they show a shortage until re-planned.

### Bookings, trips and prices (LOG-001, LOG-005 to LOG-010)

- **A block of its own below the crew**, built like the crew: a
  `VehicleLine` names the product (rates) and, once chosen, the item; open
  bookings like open places. Default period the project's, or the
  phase's; bookings with exactly that period follow it (LOG-019).
- **The rates are copied** into the booking (PRJ-015): price per km and
  trailer surcharge per km of a motor vehicle, day price or price per km of
  a trailer, discount up to the product's maximum, tax rate; costs per km
  and day only with the purchase-price right. A subrented vehicle
  ("Zumietung wie eigene") is a booking with supplier and its cost, priced
  for the customer like an own one.
- **Kilometres per trip, "wahlweise je Fahrt":** `TripVehicle.billing` is
  `driven` (the default – driven km, while they are missing the planned
  ones), `planned` or `flat` with its price. Trips are the project's
  (`projects.trips`), named by key, so nothing is stored twice.
- **Trailer surcharge on the towing vehicle**, recognised from the trip: a
  vehicle that pulls a trailer on a trip is charged price + surcharge per
  km on that trip only; a flat trip has no surcharge (the flat price is
  what is charged), and a trailer charged per km that is pulled on a flat
  trip is in that flat price. One trailer per combination, one combination per
  trailer and trip.
- **A trailer per day counts the rental days as material does** (typed
  days, else the booking's period, with the rental scale of its product);
  `only_trip_days` switches to the days on which it is pulled. Without a
  scale every day counts fully, as a material line without scale.
- **Into every figure:** `price_logistics` is called by `projects.pricing`
  next to the crew, so net total, whole-project surcharges, discounts,
  capped count, margin and taxes include it – and with them the price
  overview, documents (section "Logistik", XRechnung), list sums and
  profitability. Costs: own vehicles cost per km and day, subrented ones
  the supplier's cost.
- **Drivers:** a crew line may name a vehicle of the project and be its
  driver (LOG-008); the driving time is the crew line's work, the logistics
  charges the vehicle only. Licence class and towing capacity are hints
  (LOG-012, LOG-013), as are seats and inspections.
- **Rights:** planning the logistics needs editing the project or writing
  the material (`access.may_plan_logistics`); prices the price right, costs
  the purchase-price right – fields one may not see are neither shown nor
  accepted, in forms and API alike.

### Route service (LOG-017)

- **Decision: the route service is optional – installable, activatable,
  installable later; when it is not installed, routes are entered by
  hand.** Routino with the OpenStreetMap extract of
  Germany or a Bundesland on the server (no positions leave the house,
  NFA-050), or an OSRM server the operator names. `deploy/route.sh` as
  root, data in `/opt/rentalars/routes` (root-only, as the AI's – the
  service user can write to `/var/lib/rentalars`), the file
  `/etc/rentalars/route-local.conf` read at every use; without it the
  button is simply not there. Not backed up; `route update` swaps the map
  only after a test route.

### Pulled forward from stage 10

- **Monthly statement of service cases (DOK-016):** as proposed
  (12.2 no. 29 j) and "Rentalars als Buchhaltungsprogramm verwenden" decides the
  outcome: a draft invoice when invoices are made in Rentalars, else a
  view to copy from into the other program and "als abgerechnet
  markieren". Contracts per customer later (DOK-017).
- **Import as a preview (IMP-011): "Vorschau im Browser"** instead of a
  checkable SQL file: every row with its outcome and, for changes, field,
  old and new value, as the change log formats them; values one may not
  see are stored without values. The rows are part of the stored job
  report, so the real import shows the same list.
- **Several mailboxes (EML-003)** were there since stage 4 – mailboxes for
  correspondence and system mails, aliases with rules (EML-041 ff.). What
  was missing is choosing the sender: EML-052, a selectable sender, always
  subject to permission, with roles per address. Only correspondence
  mailboxes are offered, so answers come back into Rentalars; the outgoing
  mailbox and the project's default stay open to everyone who may write
  correspondence; further addresses are open to superusers until roles are
  ticked. A signature per mailbox (EML-026) falls back to the common one.

### Further wishes

- **Inquiries noted by hand (EML-053):** an `UnknownTagMail` with
  `source="manual"` – it lives in the list where every inquiry is dealt
  with, and the ways to a project or case stay one; taking it over writes a
  correspondence note (EML-051) with the caller's details. It needs
  somebody to get back to and something it is about.
- **Revenue per model (MAT-058):** the item's box summed over its items,
  with a row per item; a set bought together counts with its share.
- **Flat rate in "Meine Zeiten" (ZEI-028):** once per deployment, on its
  first finished entry, "in der Pauschale" with 0 on the others; reports
  and approval keep hours × rate as decided for day rates (ZEI-026).
- **Notice of changed login details (AUT-030):** to the previous address
  after an e-mail change, to the current one after a password change, from
  every place the change can happen, after the commit; no confirmation to
  the new address (it is not verified, a typo would tell a stranger).
- **Template texts in English or German (DOK-018):** a page that shows
  now/new per field and overwrites only default texts unless asked; the
  document language is a separate tick.
- **Author attribution (NFA-075):** `ADDITIONAL-TERMS.md` under GPL
  section 7 b – a draft, not legal advice.

### Found by the independent review

- **A trip that is gone is not charged (LOG-007):** the kilometres, the
  trailer surcharge and a trailer per km of a trip whose phase was removed
  or that was removed by hand are not charged.
  `price_logistics`
  charges only the uses whose trip exists (`charged_uses`;
  `trips.trip_keys_of` names the trips of many projects in three queries,
  so list sums, profitability and the project agree). The uses stay with
  their kilometres and a warning, the planning says "nicht berechnet".
- **Other projects by number only (AUT-016):** the warning "also booked
  for …" names the other project by its number only, so a reader who may
  not open it does not see its name. Logistics and the crew's double booking name
  the number only, as the fleet does for projects the reader cannot open.
- **A packing list with a vehicle over the API:**
  `create_packlist` takes `vehicle_line` (of the same project).
- **Material does not become a vehicle by changing its kind:** a product
  with material lines or in a kit refuses the kind "vehicle" and points to
  "In den Fuhrpark übernehmen" (LOG-016); its lines would have dropped out
  of availability and packing unnoticed.
- **A booked vehicle is retired, not deleted** – with the reason, in the
  browser and the API.
- **The route suggestion over the API** needs the right to plan the
  logistics, as in the browser – it may look up addresses.
- **Two requests at once** cannot put a trailer behind two vehicles on the
  same trip: putting a vehicle on a trip holds the project's row.
- **No unit price that does not multiply out:** with several rates (with
  and without trailer, different flat rates) `VehiclePrice.unit_price` is
  `None`; documents leave the column empty, the price overview says
  "mehrere Sätze", the details name every trip's rate; the XRechnung states
  the price of the whole quantity.
- **What a vehicle earned (MAT-053, MAT-058):** the item's and the model's
  box "Ertrag" and the tab "Material" of the reports count the bookings of
  a vehicle (an open booking shared over the vehicles of its product, as
  pieces without an item).
- **The crew does not see the supplier** of a rented vehicle
  (`VehicleLine.crew_label` in deployment views, the crew sheet and the
  API of the deployment); the planners do.
- **Licence plates** are unique by a rule of `Vehicle.clean`, not by a
  conditional unique constraint: MariaDB has none and warned on every
  command (models.W036).
- **The category FZ in English:** "Fleet" with "Piece (rental)" on an
  installation in English, from the start data and from the update.

### The monthly statement, as built and reviewed (DOK-016)

- **Where:** a tab "Monatsabrechnung" under Projekte, next to "Servicefälle"
  – only with the price right. One draft per customer and month; further
  statements for cases that come later.
- **What is billed:** the cases done in the month (`field_changed_at
  ["case_status"]`, PRJ-113) or with approved times or expenses in it; a
  case done in the month takes its earlier approved times not yet billed.
  Every time entry and expense is billed by one statement only
  (`StatementClaim`, one-to-one in the database), so a case running over
  months is billed month by month, and an entry moved to another case
  cannot be billed again; taking back the approval of a billed entry or
  expense is refused. Earlier monthly invoices do not stop a later one of
  the same case; an invoice of its own or "Rechnung gestellt" does.
- **Prices:** per job function as crew lines – by the hour or effort hours,
  by the day days per person, flat once per case; the hour limit and the
  surcharges for night, Sunday and holidays as on crew lines (the normal
  and the higher hours are two positions, each rounded – a cent may differ
  from a crew line's total). Expenses at their amount as net at the
  default tax rate, with a hint to correct receipts that include tax.
- **"Neu einsammeln"** keeps activity texts, own and removed positions and
  edited positions whose times did not change; it compares hours, times,
  function and the calculated result, not only the entries. A removed
  position keeps only its own entries; later ones become a new position.
- **Invoice or mark** re-check every case (ticked by hand, "Keine
  Rechnung", invoiced otherwise, internal, another customer, changed
  times, a position without tax rate). The invoice belongs to the case with
  the lowest number; its PDF, XML, the document API and mail attachments
  need read access to every billed case, its cancellation edit access to
  every one; lists hide it from others. Marking is refused while invoices
  are made in Rentalars (page and API). Cancelling makes the statement a
  draft again.
- **Locks:** making a draft and "Neu einsammeln" hold the customer's row,
  making the invoice the cases' rows, a normal invoice its project's.
- **Anonymising a customer** deletes its drafts and empties activity texts
  and details of its invoiced or marked statements; their change log
  carries the new name. The invoices themselves stay as made.
- **Rights:** viewing needs Projekte, the price right, customers visible
  and read access to every case; changing projects write and edit access
  to every case; deleting a draft the delete level; the AI button the
  right to read the correspondence. Messages count cases one may not see
  and never name them. A case billed by a monthly invoice or in a marked
  statement cannot be deleted.

### Tests

- **Each worker of `manage.py test --parallel` has a data folder of its
  own** (`rentalars/testing.py`, `test-worker-N` below the data folder):
  the locks of the mail fetch and the map search live there, and workers
  sharing one folder took each other's lock – a fetch in one test then
  found "a fetch is running already" and fetched nothing, now and then.
- **Query limits of scenario 11:** the planning page may use 47 queries
  (was 45), the usual pages 45 (was 44): the block "Logistik" adds the
  project's vehicle bookings and the vehicles to choose from, the packing
  list the vehicles of "Verladen in" – a fixed number, not one per row.
  The add form of the logistics is made only where a page shows it, and
  without a fleet it asks one query, not three.


## Part 23: Wishes from practice

The 26 points after using the application, with a screenshot of
the logistics block and a scan of printed labels next to the label
originals. Four questions were asked and answered: the invoice upload
(decided: the AI reads the invoice), the sale price of rental products
(decided: remove it), what "Ausgangsbelege" lists (decided: also offers and
the like) and what crew may do in a service case (decided: participating
crew may do everything needed to collaborate, including correspondence,
chat and changing the status; correspondence in projects is always
confidential, in service cases normally not). The catalogue gained SOLL · S9 AUT-031 to AUT-034,
MAT-059 to MAT-066, PRD-047 to PRD-051, PER-041, PRJ-116 to PRJ-118,
VFG-037, VFG-038, ZEI-029 to ZEI-031, DOK-019, DOK-020; amended PRD-013,
PRD-017, DOK-016.

### The logistics bug (PRJ-116)

- **Not a bug of the logistics.** The screenshot showed "Phase: Anfahrt Mo
  08:15 – Di 09:00" and "Aufbau Mo 09:00 – Di 10:00", the van "booked twice
  at the same time" and the trailers charged for two days. A booking with a
  phase takes the phase's period, and that was right; the phases were
  wrong. The dialog "Neue Phase …" started with the period typed in the
  vehicle form, which is the rental period until changed (Mo 08:00 – Di
  20:00). Changing only the times – the moved start takes the end along
  (UIX-025) – kept the end on Tuesday.
- **Fix in the first guess, not a check.** `course.first_guess`: a typed
  period counts only if it differs from the rental period; otherwise the
  phase begins where the latest phase within the rental period ends;
  a guess over several days lasts one hour on its first day. The same
  guess serves the page "Zeitplanung". A warning for phases longer than a
  day was considered and left out: setup over two days is legitimate, and
  the guess removes the trap itself. Existing wrong phases are corrected by
  hand; the vehicle bookings move along (LOG-001).

### Rights (AUT-031 to AUT-034)

- **Why Crew saw the planning:** not the packing. A crew line alone
  gave the overview only; the tabs came with a *membership* under "Zugriff",
  whose default level is "read", and the role Crew had "read" on projects
  for assigned projects. So the fix is a new project scope "deployment"
  that is a **ceiling** over any membership – overview with phases, packing
  list, chat – rather than lowering the role's module level (which would
  also have taken the packing list).
- **Open items and shortages** need `Rights.reads_planning`; the start page
  box, the tab, the page and `/open-items` follow it.
- **Availability is a special right** (`AVAILABILITY`), gated at view and
  API level everywhere availability, shortages, timelines or utilization
  are shown; API fields become `null` rather than disappearing. The fleet's
  availability is not part of it (bookings are not material).
- **Migration with care:** only an unchanged "Crew" gets the new scope; a
  changed one is left alone with a history event. Every other role gets
  the new right, so nothing changes for their users. "Freie Kraft" stays as
  it was – the catalogue's example of AUT-025 is a membership opening the
  planning to a freelancer.
- **Service case work** is a separate path (`projects/case_work.py`): the
  responsible person and the participants work on their own case whatever
  their role – status, fields, participants, open items, chat,
  correspondence – but never convert, delete, see prices without the
  right, or reach another case. Project correspondence stays confidential
  (the rule stated). Documents, moving mails and address
  suggestions stay with the roles.
- **Data access columns** are computed from the roles (`accounts/
  data_access.py`), the same rules the pages use; "kein Zugang" means an
  account nobody can log in with.

### Material (MAT-059 to MAT-066)

- **No purchase model.** Items already carry supplier, invoice number and
  date and the net price; a purchase is the items plus one stored invoice
  file attached to each (deleting one item's file keeps the file on disk
  until the last reference goes).
- **Reading invoices:** pypdf (BSD, pure Python) moved from the test
  requirements into the runtime ones – the update installs it per release.
  Without AI only the head (number, date, known supplier) by patterns; with
  AI a background job like the reply draft, its answer validated strictly
  (expected keys, lengths, numbers and dates parsed by Rentalars, at most
  100 positions). A model is filled in only on an exact match; every row
  from the invoice must be ticked "Geprüft". The upload waits two days
  under a signed token bound to the uploader; the daily maintenance
  removes what was never saved.
- **Gross prices** use the import's rounding (IMP-014) – `services.
  net_from_gross` serves the item forms and the purchase entry.
- **The supplier dialog** is a reusable endpoint (`material:supplier_
  create`, events `supplierCreated`, `objectCreated`) used by the item forms
  and the purchase entry.
- **Labels:** the font is Liberation Sans (metric-compatible with the Arial
  of the `.lbx` files, SIL OFL, shipped unmodified as TTF because the
  licence reserves the name for modified versions). The scan showed the
  print shifted by about 2 mm towards the end of the cable label;
  all content now stays inside the Brother printable area with safety
  margins at the feed ends, and the QR code uses the printable height with
  whole printer dots per module. The cable label keeps the blank lead-in
  of the template (the first wrap); with a 25 mm QR code a 90 mm label has
  room for three repeats instead of four.

### Products (PRD-047 to PRD-051, VFG-037)

- **One price per product** in the model's validation, the form, the
  import and `defaults_from_product`; existing sale lines of rental
  products stay valid and editable (PRJ-015), new ones are refused.
- **Kits in the utilization** count complete kits the way the availability
  engine does, with the components below.

### Crew and times (PER-041, PRJ-117, PRJ-118, ZEI-029 to ZEI-031, VFG-038)

- **"Firm" is a request status** that counts as accepted everywhere
  (`CrewLine.is_confirmed`); it is never asked or answered and never reset
  by new times – the person is told instead.
- **One notice per person and action** (`projects/crew_changes.py`, a
  context collecting notices and sending at the end): bulk changes, a
  phase moved with its crew and a whole schedule
  move (`schedule/moves.apply_move`), where the general "new period"
  message goes only to crew who were told nothing else.
- **Approval reminders** follow the invoice reminders (time of
  day, first after days, then every days, conditional update of the last
  run, a missed run made up once); they are on – as required.
- **Correct and approve** goes through the normal recording rules; the old
  values stay in the change log and the person's history.

### Accounting (DOK-019, DOK-020)

- **A main menu entry** between material and customers; the monthly
  statement moved under `/accounting/monthly/` without redirects (NFA-074).
- **Outgoing documents** list the customer document kinds explicitly
  (offer, confirmation, delivery note, invoice, cancellation), so a future
  kind is never listed by accident; amounts are the stored totals. Seeing
  them needs the price right and read access to every project, like the
  reports – per-document filtering for limited users would leak counts and
  sums. The settings page keeps its name "Buchhaltung".

### Found by the independent review

A reviewer who had not written the code went through all changes, as
pages, partials and API, with throwaway tests. Clean: Crew with the
overview-only scope (every address, partials, API, calendar, search, the
app's offline packing lists, exports), service case work apart from the
customer leak below, "Ausgangsbelege", crew bulk changes, correct and
approve, the token of the kept invoice, the data steps of the migrations,
"firm" in every count, kits in the utilization, the phase guess, constant
query counts of the grown lists. Fixed:

- **Reading a PDF is bounded** (MAT-062): a budget of content bytes and
  characters bounds the reading, because all pages may point to one large
  content stream – extracting every page before the text is cut would let an
  8 KB file take 20 seconds.
- **People working on a service case cannot read any customer** (AUT-033,
  AUT-034): without the right to see customers the form
  has no customer and contact fields, on the page and in the API;
  the API reads (`/service-cases`, `/projects/{id}` with `expand`) leave
  customer, contact, addresses and reporter empty, as the page of the case
  does, and empty values sent back count as unchanged. The customer
  suggestions (`customers:suggest`) are for whoever reads customers, edits
  projects or sees the customers of all projects – not for whoever
  only reads assigned projects, who could list every customer by name.
- **Three places respect the right AVAILABILITY** (AUT-032): the
  shortages in the preview of a move on the timeline, the warnings of the
  MVR import and the shortage message when adding material while packing.
- **Approval reminders count calendar days** (ZEI-029): "every N days" is
  compared in calendar days of the local time zone, not in hours, so a
  reminder is not skipped after the switch to summer time, after a made-up
  run or when the run started late. The reminders of invoices count dates
  as well (a weekly reminder across the switch does not come a day late,
  DOK-015).
- **A schedule move messages a person only once** (PRJ-118): not asked
  again for the new times (PER-034) and "new period" besides.
- **A line renting a sale product can be taken over
  into another subproject** (PRD-047, PRJ-060): a take-over is not
  charged and needs no rental price.
- **Going back from `projects 0030`:** the older version does not know "firm" lines;
  the step back makes them "accepted".

### Tests

- **About 270 tests** in `test_091_*` (rights, purchase entry and
  invoice reading, items, labels, products, crew and times, accounting,
  phase guess, the review findings).
- **Order of the tests:** two browser tests of automations fetch their
  automation by name, because on a fresh database the automations of the start
  data are there as well.
- **Eleven unsortable columns** may exist: one of them is the button "Korrigieren
  und freigeben".

## Part 24: Wishes from practice

The 16 points after using the application. Three
questions were asked and answered: who reads a message without the lock
(decided: open for the crew, new messages locked), what happens to videos
(decided: shrunk on the server) and how audits are recorded (decided: an
audit mode of their own). One
point was a question (how the full export differs from the backup),
answered in the catalogue (IMP-006) and the delivery
note. The catalogue gained SOLL · S9
AUT-035, MAT-067 to MAT-073, PER-042, PRJ-119 to PRJ-121, VFG-039, UIX-049
to UIX-051, IMP-017, EML-055, NFA-076, NFA-077; also UIX-005, UIX-012,
UIX-035, IMP-006.

### Audits and to-dos (MAT-067 to MAT-070)

- **Own tables, not inspections.** An audit is not an inspection (MAT-030):
  no result per check type, no certificate, no blocking of the item. An
  `ItemAudit` (item, when, who, ok or with to-dos) and an `ItemTodo` (item,
  text, noted, done, from which audit) are enough; the interval and the
  quick picks live in the one-row `AuditSettings`.
- **Due date without a flood.** "Last audit + interval" alone would make
  every item of an existing installation due on the day of the update. A
  never audited item is due one interval after it was *created in
  Rentalars* – for imported stock that is the import date, so the oldest
  stock comes first and the rest follows gradually. Bulk material and
  archived items are never due (there is no single piece to look at, or
  none in use) but can still be audited.
- **The audit mode** is a page of its own (the answer "Eigener
  Audit-Modus"): one ID field accepting everything the ID field of the
  material tabs accepts (MAT-063) plus the QR address; a second field
  "In Ordnung – nächste ID" so that the common case – nothing to note – is
  scan, Enter. The round lives in the session. Plain forms, no JavaScript
  needed.
- **Same to-do once.** Noting an open to-do again does nothing; noting it
  after it was done creates a new one. To-dos are never deleted, only
  done – the history keeps who did what.
- **"Offene Punkte"** keeps the old meaning of "Ohne Produkt" as its first
  sub-tab, named "Material ohne Produkt" rather than "Modelle
  ohne Produkt" as requested: the old tab listed items, and so does this one.

### Custom fields (MAT-071 to MAT-073)

- **Fields and fieldsets:** fields, fieldsets of fields with "required" per
  entry, one fieldset per model, values per item. A separate app
  (`rentalars.customfields`) keeps the material app from growing further;
  it depends on material, not the other way round – material reaches it
  through a hook for DB-derived table columns (`core/tables.py`) and small
  calls in forms, history, search and import.
- **Category fields stay.** The category-specific fields (MAT-009,
  MAT-010) describe the *model* – the length of a cable is the same for
  every piece. Custom fields describe the *piece*: MAC address, firmware,
  insurance value. The manual explains the rule of thumb.
- **Sensitive values** are stored in a separate column that the change log
  and the search never read; they are shown and exported only with the
  right to see purchase prices.
- **Definitions follow the data.** A changed type, option list, pattern or
  "unique" is refused while stored values would not fit; a field with
  values is deleted only after a tick, its values one by one with history.
  Values of fields no longer in the model's fieldset are kept and shown
  apart rather than silently lost.
- **Required, but not everywhere.** A required field needs a value when
  one item is created or edited (form and API). Creating many items at
  once, the purchase entry and the import may leave it empty – the typed
  value would apply to all pieces, which is wrong for most per-piece data;
  the item page and the purchase summary name what is missing.

### Chat media (UIX-049, NFA-076)

- **Only the small version is kept** (decided). Photos are
  turned upright and re-encoded at most 2048 px with a 640 px preview,
  metadata (GPS) dropped; videos are re-encoded in a background job with
  ffmpeg to at most 720p, 30 fps, H.264 CRF 26 and AAC, fast start, no
  metadata, with a poster frame. The original goes as soon as the small
  version exists; a failed conversion discards the video and says so.
- **Content, not extension:** Pillow must open a photo; a video must have a
  known container signature and pass `ffprobe` with a forced demuxer and a
  file-only protocol whitelist; ffmpeg runs with list arguments, `-nostdin`,
  a timeout and `nice`. Limits: 25 MB per photo, 200 MB and 20 minutes per
  video, 10 files and 500 MB per message (NGINX accepts 510 MB already).
- **Getting ffmpeg onto servers.** The update runs the *old* `update.sh`,
  which knows only the old package list; the first update would
  not install ffmpeg. The new `deploy/ai.sh refresh`, which the old
  `update.sh` runs after the switch, therefore first installs missing
  packages of the new version's list (`refresh_packages`, sharing the
  package check with `update.sh`): it waits up to two minutes for a
  running package manager and only warns when it fails. Without ffmpeg
  only videos are refused; the self-check warns.

### Correspondence with a lock (EML-055)

- **The rule** (`mail/locks.py`): who may read the correspondence at all is
  unchanged; a locked message additionally needs "Preise und Kalkulation
  sehen", an open one is also readable by the crew planned in the project
  (read only) and by those who work on the service case (AUT-033). Setting
  and removing the lock needs correspondence write access and the price
  right; a writer without the price right writes open messages.
- **New messages:** the decision that new messages are locked, together with
  the rule (correspondence in projects is always confidential,
  in service cases normally not), gave two settings – projects locked,
  service cases open – applied to every way a message comes in
  (`locks.default_lock`). The migration does the same for existing
  messages, so nothing becomes visible that was hidden, and nothing hidden
  that the case workers could read.
- **Unreadable means absent:** 404 for the list entry, the conversation,
  the body, attachments, answering, moving, notes, the API and the search.
  Notifications about a new mail go only to its readers; removing the lock
  tells the crew once. AI summary and reply draft read all messages and
  are therefore only for users who may read all of them.

### Projects (AUT-035, PER-042, PRJ-119 to PRJ-121, VFG-039)

- **"Wer Zugriff hat"** is computed by the same functions the pages use
  (`projects/access.access_of_users`, batched: three queries for any
  number of users) rather than a second, list-only rule that could drift.
- **Accepting marks available** only when the person's own calendar says
  "not available" in that time, for exactly the line's period, cutting or
  splitting overlapping entries (also of series). Linked calendars (.ics)
  are read-only sources and stay untouched. Firm planning (PER-041) is a
  decision of the office, not of the person, and marks nothing. A later
  removal of the deployment leaves the entry – it is the person's calendar.
- **Relations** are stored once per pair (ordered, unique) and shown from
  both sides; whole projects and cases only, since a subproject belongs to
  its project. The other side is named even without access ("Projekt
  2027-0042 (kein Zugriff)") – the number alone reveals nothing the
  history would not.
- **Staffing a phase by function:** functions with places first, then a
  person per place, as when items are created per piece. Existing open
  places of the phase are filled first so that nothing is planned twice; a
  new phase can create its open places right away (also from "Neue Phase
  …" in the planning, whose crew block refreshes).
- **Dragging persons:** the "follow" rule is narrow on purpose – the phase
  follows only if the person is its only person (open places do not
  count), the open places of the function only if the person is its only
  person with the same times. The dialog lists what follows and why; a
  phase pushed beyond the rental period asks as in PRJ-100. The personnel
  plan of "Planung" moves single deployments only.
- **Calendar:** phases on by default (as before), follow-ups off (new);
  only follow-ups the user also sees under "Wiedervorlagen".

### Tables, forms, exports (UIX-005, UIX-050, UIX-051, IMP-006, IMP-017)

- **Page size per user and list** in `TablePreference.page_size`, next to
  the column choice, instead of the per-browser cookie of 0.8.x (deleted
  by a middleware). A test walks every user of `core/_table.html`; tables
  that are a form or a sum as a whole are listed exceptions.
- **Required marks** were checked by a crawler over about 530 pages and
  dialogs as an administrator; the test stays (UIX-051).
- **Notification texts** are stored as HTML for the mail; the table shows
  them as plain text with line breaks (`core.tables.plain_text`).
- **Export or backup.** They differ in purpose, so both stay: the backup
  restores (whole database with secrets, configuration, files, encrypted
  when switched on); the full export is for reading (JSON, CSV, files,
  without secrets, with internal IDs) and restores no installation – at most
  its data can be loaded into a fresh one of the same version (`rentalars
  loaddata`, as its LIESMICH.txt says). As proposed, the export now
  lives on the backup page with a paragraph on the difference.
- **Export in the import format** writes exactly the columns of each import
  in clear text – names instead of IDs, category and storage location as
  paths, German dates, numbers and choice labels – so that re-importing
  the file changes nothing (tested as a round trip). Data the import has
  no column for (a fourth contact person, project lines) is not in it;
  that is what the full export is for. Formula-like cells get an
  apostrophe, which the import now strips again.

### Squashed migrations (NFA-077)

- **Squashed migrations.** The early migrations of each app are one squashed file per app (projects two, because
  other apps depend on its early state), written with Django's `replaces`, so that a database that has them applied
  recognises the squash as applied. The data steps that a fresh installation needs (start data, default rules,
  numbering) are kept as RunPython. A fresh `migrate` takes about half the time of the unsquashed chain. The
  migrations of the workers depend on old names, which Django maps to the squashes.
- **Refusing databases that are too old** before anything changes: a system check (`core/checks.py`, E001) detects
  migration rows of an old chain that is not complete and stops `migrate`; the database stays byte-identical.
  `update.sh` refuses too old installations before making the backup (`OLDEST_UPDATABLE_VERSION` in `lib.sh`), and
  `restore.sh` refuses backups of such a version.
- **Kept on purpose:** former project numbers, API v1 fields, the handling of the companion app, bare-ID
  addresses, `User.language`'s database default and small safety nets of the deploy scripts.

### The independent review

A reviewer who had not written the code went through every new page,
partial, endpoint, download and data path. No critical finding; fixed, each
with tests (`tests/unit/test_092_review_mail.py`,
`tests/unit/test_092_review_media.py`):

- **Subjects of locked messages in the project history** (page and API) –
  the audit entries of mails and the note, move and delete events carry the
  subject. Applied at display time (`mail/history.py`) to all entries, so that
  entries written before are covered too: a viewer sees the subject only
  if they may read that message; a deleted or moved-away message only for
  readers of locked messages; everybody else gets a neutral wording. The
  administration change log shows subjects (administrators only).
- **Values of a field made sensitive later** – hidden in the item history
  by the field's current setting, not by the column an entry
  names, also in the change log.
- **Automation notifications and their open items** say "Mail von …
  (mit Schloss)" instead of the subject of locked mails.
- **Answers inherit the lock** – an answer to a locked message
  starts locked (form, API default), an incoming reply to one is stored
  locked.
- **Images:** a 6 KB PNG of 7070 × 7070 pixels took 593 MB to decode in a
  web worker. The byte size and the pixel count from the header are checked
  before any decoding; PNG, GIF and WebP are limited to 16 megapixels; JPEG
  is decoded with `draft()` at the smallest scale that still gives 2048
  pixels.
- **Videos:** a job kind can register a gate in `core/jobs.py`, so that not
  every video starts its own conversion process; `chat_video` uses an `flock`
  on `DATA_DIR/chat-videos.lock`, so conversions run one after another and
  the holder works off the queue; a crash releases the lock and the minute
  timer picks the job up again. Streams above 4096 pixels, 240 fps or
  72,000 frames are refused, and ffmpeg never converts more than 20
  minutes (`-t 1200`) whatever the container claims. There is no address-space limit
  for ffmpeg: a 1080p conversion needs 1.5 GB on two
  cores, and the need grows with the cores.
- **Check patterns** (ReDoS): `(a+)+` against 30 characters took a minute.
  Patterns with nested variable repetitions, alternatives in open-ended
  repetitions or back-references are refused when saved
  (`customfields/patterns.py`); fixed counts such as `(:[0-9A-F]{2}){5}` stay
  allowed. As a last guard a 0.5-second SIGALRM timer in the main thread –
  gunicorn's sync workers and `run_jobs` run there; elsewhere it is skipped.
  The `regex` module was not an option.
- **Smaller:** declined or unanswered crew lines do not count as planned
  crew for open messages; an account past its "valid until" counts as
  without access in the data-access columns and the access tab; the
  redirect check after setting a lock uses `url_has_allowed_host_and_scheme`;
  link schemes of custom fields are checked when shown; several to-dos can
  be done at once through the API (`POST /material-todos/done`).
- **As designed:** writing `?per_page=` on GET remembers the
  choice (the link is the interface, the worst a foreign page can do is a
  long list); a case worker with the price right reads locked messages of
  their case (AUT-033 gives them the correspondence of the case); the mail
  log and the access log show subjects to administrators; unique custom
  values are checked before saving, without a database constraint (the
  values live in one table for all fields).

While documenting, three more things were corrected: an unknown storage
location path in the material import created one location named after the
whole path – now the locations level by level; the German file name of the
export in the import format was half English (`_()` inside an f-string,
which `makemessages` does not read); and a few German texts said "Sie"
instead of "du".

## Part 25: Wishes from practice

The 16 points after using the application. Two
questions were asked and answered: what the DGUV inspection needs
(decided: measured values and the protection class) and whether the new
notification defaults also switch on an existing installation (decided: yes,
at the update).
The catalogue gained SOLL · S9 MAT-074 to MAT-079, VFG-040, UIX-052, ADM-019,
LOG-020; amended MAT-058, MAT-062, MAT-070, VFG-036, DOK-015, ADM-013,
NFA-025.

### Default automations (ADM-019)

- **Not locked – unreachable.** Nothing locked the four default
  rules; the list row simply had no "Bearbeiten" (the name was the only way
  in), and deleting worked. ADM-013 had promised "bearbeitbar".
- **A stable key** (`Automation.default_key`, unique, nullable) instead of
  recognising defaults by name: names are translated and may be edited.
  The migration assigns keys only to rules without a creator, by German or
  English name first, then by trigger, condition and action; it creates
  nothing. Restoring creates the missing keys only; nothing at startup or
  in a later migration creates or overwrites defaults. "geändert" compares
  with the shipped definition (`defaults.is_changed`); a future change of a
  shipped default needs a new key.
- **Buttons:** "Löschen" carried an icon and sat 4 px higher; the row now
  uses the shared `cell-buttons` flex row. A browser test measures the boxes
  at 1280, 390, 360 and 320 px.

### Purchase entry (MAT-074 to MAT-076)

- **Why 1.072,50 became 1,07:** the prompt asked for "numbers with a dot";
  models wrote `1.072` or `1.0725`, which the parser read as decimals. The
  prompt now asks for amounts as strings exactly as printed, and Rentalars
  parses them (`purchases.parse_amount`): both styles, € and EUR, "1.072,-";
  an ambiguous "1.072" is decided by the answer's other amounts, then the
  amounts in the invoice text, then currency and language. Each amount is
  checked against the amounts in the invoice text.
- **Serial numbers, category, product** were never asked for. The prompt
  lists the categories with own stock (no customer material) and up to 40
  products (those sharing words with the invoice when there are many);
  only exact or unambiguous matches are filled in, otherwise a hint names
  the suggestion. Serial numbers not found in the invoice text are dropped.
- **Sums:** server-side (`purchase_forms.purchase_sums`) and live in the
  script; gross entry sums the typed gross prices and the net as stored,
  net entry multiplies once by the tax rate, as an invoice does. Totals of
  the read invoice travel in hidden fields; everything only with the
  purchase-price right.
- **Net or gross per purchase,** not per row, as before (MAT-059).

### Electrical inspection (MAT-077, MAT-078)

- **Limits as data** in `material/dguv.py` with the DIN VDE 0701-0702
  sections as source; which measurement applies to which protection class
  is data too. The R_PE limit counts every further 7.5 m begun.
- **Suggestion, not verdict:** the inspector decides; "passed" against the
  suggestion needs a note for any reason – a value outside, a failed or
  missing visual inspection, a failed function test. "entfällt" for the
  function test (cables).
- **Protection class** at the model with an optional override at the item;
  an override equal to the model's is cleared on save, as category values
  are. Import: a model without class takes it only if all its rows agree.
- **Protocol** as a WeasyPrint PDF; no new JavaScript – the live marks come
  from an htmx check endpoint, the same code as the form and the API.

### Calendar links (VFG-040)

- **Stricter than asked:** seeing a link needs the availability right and
  read access to all projects, because the feed shows project names without
  login. Changing it needs module write access. Tokens are 256 bits, checked
  in constant time, rate-limited with the person feed.
- **Content from the timelines** (`schedule/timelines.item_events` split out
  of `item_bars`): bookings with number, name, status, quantity and period,
  for items their own events. UIDs are stable per booking. A retired item or
  deactivated product loses its link for good.

### Notifications (UIX-052, VFG-036, DOK-015)

- **The AI setting existed:** `job_finished` was the last row under
  "System" and named without the AI. It is first there now, with examples
  in its label. A test enumerates every `Kind` and every `notify()` call;
  exceptions would need an entry with a reason in `ALWAYS_SENT` (empty).
- **"Erneut melden" flooded:** one mail per shortage line and product every
  morning. Known shortages are now bundled into one reminder per project and
  check; new or grown ones still come one by one.
- **Defaults on, also on update** (decided): the data migration
  writes the change-log entries and its reverse reads them back.
- **Monthly invoice number:** with "service cases too" on, a case head named
  the monthly invoice to users who could not open it; they now see
  "Rechnung gestellt".

### Smaller things

- Fleet only for categories whose product kind default (or a parent's) is
  "vehicle" – in `fleet.transition_problem`, so dialog and API agree.
- The "Offene Punkte" total uses the same three counts as the sub-tabs.
- Audit master data in a constant number of queries; "–" in red marks gaps.
- **Help texts were never read by screen readers:** Django 5 points
  `aria-describedby` to `<id>_helptext`, the shared field template named the
  help `<id>_help`. Fixed in all templates; the tabular admin inline (help
  in the column head) gets `aria-description` instead. A crawl over all
  pages and dialogs now checks every aria reference.
- PDF page margins escaped names with `escapejs` ("u0026"); a `css_string`
  filter writes CSS escapes. The person feed's `X-PUBLISHED-TTL` is a
  duration ("PT30M"). The product page names sales "verkauft" (the far
  future is the year 9000, not after it).

### The independent review

No critical finding; fixed, each with tests (`tests/unit/test_093_review_feeds.py`,
`tests/unit/test_093_review_material.py`):

- **One counter for all feeds:** the failure counter of the calendar feeds
  (of people, and the new ones of products, models and items) was keyed on `REMOTE_ADDR`,
  which is empty behind NGINX on a unix socket – twenty wrong requests (a
  calendar program polling a renewed link) answered 429 to every feed. Now
  per client via `accounts.services.client_ip` (the `X-Forwarded-For` NGINX
  sets); without any address nothing is counted rather than everything
  together – guessing 256 bits is pointless anyway.
- **Feed addresses** are shown only to who may change the link; a reader
  could otherwise keep a permanent address after losing the rights.
- **Required measurements** per protection class as data next to the limits
  (DIN VDE 0701-0702:2008-06, 5.3–5.6): class I R_PE and an insulation check
  (R_ISO, I_PE or I_B), class II R_ISO or I_B, class III only the visual
  inspection. A missing one is a reason, so "passed" without measurements
  needs a note.
- **Old service cases:** switching "service cases too" on by the update
  would have reminded every case done. A cut-off
  (`NotificationSettings.invoice_cases_since`) is set whenever the setting
  goes on – by the migration and by page and API; the lists stay complete.
- **Customer material** is never matched, offered to the AI or joined by a
  purchase (product or existing model); the AI catalogue takes at most a
  third of the prompt, sits in a data block, and a cut invoice text is said.
- **Smaller:** "NaN"/"Infinity" refused as category numbers and ignored when
  stored; crafted invoice totals ignored; the bundled shortage reminder names
  the count in its title and the list in its text; the statement box of a
  case hides the number of a monthly invoice the user may not open.
- **Not changed:** the key migration of the automations treats a rule whose
  creator was deleted as shipped – users are deactivated, not deleted.

## Part 26: Wishes from practice

The points after using the application: no
question was open – how the storage spot can be solved most efficiently is
answered by the design below. Catalogue:
new SOLL · S9 AUT-036, MAT-080 to MAT-083, PER-043, PRJ-122, PRJ-123; amended
AUT-023, AUT-010, PCK-008, PRJ-119, MAT-029, MAT-031, MAT-032, MAT-078,
EML-006, PER-042. The references to other products (as models or for
comparison) are removed from every document; the requirements stay.

### Storage spot (MAT-080)

- One short text field on the item (`storage_spot`, 12 characters), not a
  table of spots: nothing to maintain, and search, import, export, labels
  and the API need no join. `material/spots.py` normalises what is
  recognisable (`^(\d{1,2})[-. ]?([A-Za-z])[-. ]?(\d)$` → `NN-L-N`, "3a2" →
  "03-A-2") and keeps any other short text – a warehouse that numbers its
  spots differently is not forced into the pattern. Whoever wants counted
  spots (occupancy, free spots) asks for it as a wish of its own; that is a
  model, not a field.
- Installed items show the spot of their container (`effective_storage_spot`,
  as the location). A bulk move to another location drops the old spot unless
  a new one is given – a spot belongs to its location.
- Search finds it in any spelling (the term is normalised before matching).

### Overall discount (PRJ-123)

- Two fields on the project, percent (0–100) or amount, never both; set by
  `projects.services.set_overall_discount` – the one door for page and API,
  with the price right, editable and plannable checks.
- Taken off **last** (`pricing.overall_discount_of`): after surcharges,
  rounding and minimum rental, so it is what the customer sees at the foot
  of the sums. The tax lines are scaled by `net_total / net_before_overall_discount`;
  documents, XRechnung and DATEV carry it as an allowance line of its own.
- Per project, not per tree: a subproject keeps its own, a family document
  shows one row per project. Not distributed over lines (profitability uses
  the project total); `discount_total` stays the line and group discounts, so
  the maximum discounts (PER-026, per product) – which cap those – do not
  apply to it.
- Copy and split take it over only for who has the price right.

### Inspections (MAT-081 to MAT-083)

- The visual inspection is a checkbox (`forms.BooleanField`), unticked means
  "not passed" – the same value the dropdown's "no" gave; the API still takes
  true/false.
- Mass inspection: `services.record_inspections` calls `record_inspection` per
  item inside one transaction – every rule of the single inspection holds,
  all or nothing, the errors by item (`BatchInspectionError`). The page asks
  type, day, inspector and test device once; its rows are a `BatchRowForm`
  per item with the prefix `i<id>`; the visual inspection is a column of
  boxes named `visual`, so one header box ticks all. Types offered are those
  that apply to every chosen item. The API (`POST /material-items/inspections/batch`)
  reports errors as `items[n].field`. The length field of a category is asked
  for once per category, not per item (200 items: 18 queries instead of 216).
- The link to the types is the button pattern of the accounting page, shown
  with read access to the administration.

### Roles, customer name, mailbox (AUT-036, PRJ-122, PER-043)

- Start rights in `accounts/defaults.py`.
- "Freie Kraft" gets the project access "deployment" (overview without
  planning): a membership does not open the planning for it (AUT-031).
- The customer's name is not customer data: `Project.customer_name` is shown
  to everyone who sees the project or case; the link, contacts, reporter and
  the customer's page stay with the customer rights.
- A reply to a deployment request is moved into the done folder even when the
  mailbox only marks as read (`imap.effective_action(answer=True)`), unless
  the done folder is the inbox.

### The independent review

A separate reviewer read the changes. No critical finding;
fixed, each with tests (`tests/unit/test_094_review.py`):

- **Splitting a project** shares the overall discount
  (`split._share_overall_discount`; otherwise the whole project would keep
  it for the lines left, the parts would have none and the family would get
  dearer): a percentage in every part, an amount
  shared in proportion to the parts' sums (rounded down; the cents stay with
  the whole project). Whoever splits needs no price right – nothing is set,
  a price stays.
- **Role migration in an English installation:** the start roles are named
  "Project management", "Warehouse", "Freelancer" there; the migration knows
  both the German and the English names (written into the migration,
  which does not import later code) and the English description of "Freelancer".
- **API update of a project** is atomic: a refused discount (no price right,
  percent and amount together) does not leave the other fields saved. The
  discount fields are tracked by `changed_at` like every other field
  (`field_changes.TRACKED["overall_discount"]`).
- **Mass inspection:** one `InspectionPlan` for the whole batch (under 8
  queries per item); IDs like "²" or 30 digits answer
  400 / go back to the list; the API refuses more than 1000
  items and IDs beyond the database range before looking anything up; after
  an error the test device block follows the type that was sent (also
  without scripts).
- **After-calculation:** the overall discount is shared over material,
  personnel and logistics in proportion.
- **Packing list:** the spot is the effective one (the outermost container's)
  and `chosen_items` of the API carries `spot`.
- **Smaller:** the API list of service cases searches the reporter only for
  who may see customers; a copy without material, crew and logistics gets no
  discount; the import normalises the spot before comparing (no false
  "updated"); a bare number in the item search finds the ID, not spots like
  "42-B-3"; the search labels say that the customer's name is searched.
- **Whole-project discount:** a discount on a whole project covers only its own lines,
  never its parts (by design, PRJ-123); the visual-inspection column starts
  unticked, so a row left on "by the values" can suggest "failed"; the answer
  mail of a failed item goes per item (as with every defect). In "mark as
  read" mode on a server without MOVE, the answer is copied and the removal
  can fail with a mailbox error after it was marked read – not retried.

## Part 27: Wishes from practice

The points after using the application, 18 in all.
One question was asked – the planning "save" switch; decided: not built, recorded as
PRJ-129 (KANN, stage 10) with the idea of a saved planning state to go back to.
Catalogue: new SOLL · S9 DOK-021, DOK-022, KND-011, MAT-084, MAT-085,
NFA-078, PER-044, PER-045, PRD-052, PRJ-124 to PRJ-128, UIX-053 to UIX-055;
KANN · S10 PRJ-129. The work was split into eight packages with a shared
conventions file; the catalogue, documents and changelog were put together separately.

### Uninstalling (NFA-078)

- A shell script (`deploy/uninstall.sh`) behind `rentalars uninstall`, like
  every other operation; no Python, because it removes the Python
  installation it would run in. The dispatcher runs it from a temporary copy
  since it deletes its own folder.
- Three explicit modes and no default: with no option it only explains. A
  destructive default would turn a typo into a data loss. `--dry-run`
  prints the same plan the real run would carry out, built by one code path.
- `--purge` needs a typed host name (or, without a terminal, a flag long
  enough that nobody types it by accident; `--yes` deliberately does not
  count) and offers a last backup first. Rejected: asking "yes/no" – it is
  answered by reflex.
- Paths come from constants in `deploy/lib.sh` shared with the installer, so
  the two cannot drift apart; every path to remove must contain "rentalars"
  and not be a top-level folder; the database is dropped first so that a
  failure leaves the config to retry. Packages, the MariaDB encryption key and
  other databases are never touched (a removed key would make MariaDB
  unstartable; a removed package may serve something else).
- A remote database loses only its tables: database and account belong to
  its administrator.
- Not solved: reinstalling on kept data is manual (`install.sh` refuses while
  `/etc/rentalars` exists); the output prints the steps. Tested with stubs for
  every system command in a temporary root, **not on a real server**.

### Overview first, phases, planning layout (PRJ-124, PRJ-125, UIX-053)

- A new phase lasts at most eight hours (`course.first_guess`), starting where
  the last one ended or at the project start, never beyond the rental
  period. Only the suggestion is capped; the user may type anything longer.
- The "Überblick" becomes the first tab and the landing page of a project
  (`projects:overview`); `projects:detail` stays the planning. Alternative
  considered: keep the planning as the landing page and only move the tab –
  rejected because the requirement refers to service cases, where the overview is
  the landing page. It is one redirect to revert. Open point: for planners
  the personal block says "you are not planned in".
- The add-forms of the planning tab share `.add-row`/`.add-actions` in
  `app.css`, so a fourth form cannot drift again.

### Warnings that do not block (PER-044, PRJ-127, MAT-084)

- A warning is a list of texts returned next to the result (`warnings` in the
  API, a message in the browser); the status stays 2xx and nothing is
  refused. Same in all three places so the rule lives in one function each
  (`projects/discounts.py`, `projects/period_warnings.py`,
  `material/serials.py`).
- **Discount above the maximum:** the typed value is stored as typed, the price
  uses the maximum (as before), and the warning says what is applied. The
  requirement said "entered"; the stored/typed distinction is the reading chosen
  and listed as open confirmation 12.2/36.
- **Serial numbers:** no unique constraint (makers repeat numbers). The
  second submit with a tick ("anyway") carries a hash of exactly the
  warnings shown, so a tick cannot confirm a different warning. The same
  serial twice in one list is now a warning, because MAT-004 says duplicates
  warn.
- **Event end after "Material zurück bis"** is a warning on project form,
  reschedule and API; service cases are excluded.

### Product links, text lines, pieces per product (PRJ-126, PRJ-128, PRD-052)

- The availability box takes `?project=` and reads the project's period; a
  wrong or unreadable value is ignored, a typed period wins.
- A text line is a `MaterialLine` with `is_text` (not a new model) so that
  moves, copies, splits and templates work unchanged; every consumer that
  would compute with it (packing, availability, takeover, after-calculation,
  XRechnung, DATEV, sums) skips it explicitly.
- **Pieces per product sits on the product, not the model** (the model had
  been suggested first): two models of one product with different factors
  would make "3 × K-005" mean different numbers of cables. Stock is items ÷
  pieces, rounded down; a line reserves quantity × pieces; blocked periods cut
  at every start and end. Rejected: a Kit – a kit has fixed different parts,
  not N of one. Not supported: container products with more than one piece.

### Contacts and greeting (KND-011)

- `Contact.name` stays stored and is derived from first and last name, so
  every list, export, document and recipient list keeps working unchanged.
  The split rule (last word, particles, "Berg, Anna") lives in
  `customers/names.py` and serves the migration, the import and the API.
  "Dr. Anna Berg" → first name "Dr. Anna" is a known cost of a rule that
  does not guess titles.
- The greeting is per contact (formal/personal/own text), not per company –
  the requirement was an individually configurable greeting; a company default was not built.

### Documents (DOK-021, DOK-022)

- **Descriptions in documents** are a template setting (default off, so no
  document changes) plus a tick at creation stored on the document.
- **Outgoing documents without a project** use a draft (`DocumentDraft`,
  `DraftLine`) that is issued through the same service as project documents:
  one number sequence, one immutability rule, one export path. Rejected: a
  "dummy project" per customer – it would show up in every project list and
  in profitability. A document without a project is excluded from
  profitability and project payment reminders. Credit notes: only as a
  cancellation of an issued document.

### Labels, back button, years, functions (MAT-085, UIX-055, UIX-054, PER-045)

- Labels follow the original `.lbx` templates in size and place; the QR code is
  never smaller than the template's and grows into free space in whole
  printer dots. The order of name and company in the title is not code: it is
  a user setting, "Name auf Etiketten".
- "Back" after the browser's back button: the page comes from the browser's
  back/forward cache without a request, so the signed trail still ended at
  the product seen last. `follow_referer` cuts the trail back to the page the
  click came from. A browser that strips the Referer behaves as before.
- Year choices: five years back, three ahead (`core/years.py`).
- The job function's rate is labelled as the hourly wage of the staff, with
  a link to where customer prices live.

### The independent review

Three separate reviewers read the changes, one for the uninstall
script, one for projects/material/products/availability, one for
customers/documents/API/migrations; none was told what the author concluded.
No finding about deleting outside Rentalars' own files or about confirming a
purge; everything below was reproduced and fixed with tests (the test
modules, `tests/deploy/test_uninstall.sh`):

- **Uninstall:** a configured data or backup folder under a removed path
  (`/opt/rentalars/backups`) is refused
  before any change in both modes; units are only stopped before the database
  step and disabled after it, so a failed `DROP` leaves a restartable
  installation; signals during the destructive phase are caught;
  stopped units are verified;
  a non-interactive purge needs `--backup-to` or `--no-final-backup`; a
  non-default port means a remote database; symlinked folders are reported.
- **Migration 0009 (names)** has a frozen copy of the split rule and falls back
  safely for a name part longer than 100 characters (MariaDB enforces the
  length, SQLite does not); the model refuses a derived
  name over 200 characters. Documents 0007 cannot be reversed while a document
  without a project exists (a last operation raises `IrreversibleError` before
  anything is dropped); the backfill of `Document.customer` reads the frozen
  customer number first.
- **Free documents:** the draft page does not end in a 500 for an expired
  offer validity, an unknown placeholder (`{customer.name}`), a null flag over
  the API, a newline in the mail subject or a second issue of the same draft;
  `{greeting}`/`{anrede}` are filled; anonymising scrubs drafts from the log;
  the customer export lists the documents and drafts; billing address, custom
  greeting and service dates are checked the same in browser and API.
- **Pieces per product:** a container product of several pieces reserved
  too few loose contents; changing the number re-interpreted every existing
  line (refused while running projects use the product); one blocked item
  costs only the difference of the floors, not a whole pack, when spare items
  exist; wishes take the pieces of the line's own product, not of the
  model's default product.
- **Text lines** cannot become the "alternative to" of another line – refused
  everywhere; they are not counted in the
  figures of parts and in the "lines took the new period" notes.
- **Smaller:** `²` in `?project=`, `?group=`, `?year=` does not end in a 500
  (`isdigit()` accepts it; `int()` does not); the serial comparison respects
  collation differences; the back trail cookie stays within 4 KB and the
  encoded paths are found on it; the API warns about a serial on every
  PATCH; the reply draft started with the greeting twice; the import refused
  a contact with only a first name.
- **Not changed (by design):** the placeholder hint of a draft does not block
  issuing; the drafts list pages like the other
  lists (`count`/`results`).

## Part 28: Wishes and the built extensions

The points after using the application, plus nine requirements that had been
kept as KANN in stage 10 and were asked for now. Catalogue
(759 requirements, 12 more): new SOLL · S10 DOK-023 to DOK-025, MAT-086 to
MAT-088, PRJ-130, UIX-056, UIX-057, EML-056, NFA-079; KANN → SOLL and built
AUT-029, MAT-027, MAT-040, PRD-023, PER-038, VFG-015, PCK-010, PCK-011,
UIX-006; changed UIX-020, PRJ-064, PRD-052, PRD-046, PRJ-123, PER-016,
AUT-021, DOK-005, DOK-022, MAT-050, MAT-061, MAT-062, PCK-016, PCK-022;
new KANN · S10 DOK-026. The work was split into nine packages (A, B1, B2 and C to H)
with a shared conventions file, one package per area; the catalogue, documents and changelog were put together separately. Each package had its own tests
(`tests/{unit,ui,api,browser}/test_100_<area>…`) and measured its own cost.

### Not built, on purpose

- **The planning "Auto-Save" switch (PRJ-129):** it was left out.
  Nothing changed; everything is still saved at once.
- **Tax preparation of an incoming invoice (DOK-026, KANN):** only noted
  (a docstring of `IncomingInvoice`). The amounts it would need are stored
  (net unit price and tax rate per position, net/tax/gross per invoice); a
  nullable `tax_account` column can be added later without touching
  anything stored.
- **Depreciation beyond the simple case:** no degressive depreciation, no
  special depreciation (Sonderabschreibung), no half-year rule, no pool of
  low-value assets (GWG-Sammelposten). The rules are a documented standard
  setting, **not tax advice**; a tax adviser's table is the authority.
- **No DATEV export** for the asset register or the sales from stock
  (decided together with the book value, "Mit Restbuchwert").

### Incoming invoices as an app of their own (DOK-023, DOK-024)

- **Context.** The requirement: a register of the invoices suppliers send, read
  by the AI as far as possible, whose goods become items – with the freight
  shared out over them. "Kauf einpflegen" (`material/purchases.py`)
  already turns an invoice into items, but it is a one-shot wizard: the
  invoice is not kept as a record, cannot be corrected later, and cannot be
  booked in step by step.
- **Decision.** A new app `rentalars/incoming/` (tables `incoming_*`):
  `IncomingInvoice` (file, head, status, key, reading) and `InvoicePosition`.
  It owns the register, the correction of every field, the costing and
  the booking-in pages; it owns **no** way of making items. Booking in
  (`incoming/booking.py`) builds the same `purchases.Position` objects the
  wizard builds and calls `purchases.create_purchase`, so consecutive IDs,
  the supplier, invoice number and date, the invoice file as a file of
  each item, customer-material refusal, the limit per step and the price
  right are the existing code, not a copy. What is added is the cost data
  of each item (`item_fields`) and the link back (`source_position`).
  Reading reuses `material.purchases.invoice_text` and `ai/invoices.py`
  (the setting "reading invoices", the same provider): the head is read at
  once from the PDF text by patterns; with AI on, a background job
  (`ai_incoming_invoice`) finds the positions as well.
- **Why an app, not more of `material`.** The register has its own list,
  filters, totals, CSV, 17 API operations, settings page and tests; `material`
  was already the largest package. The price of the cut: `material` and
  `incoming` point to each other (`MaterialItem.source_position` →
  `InvoicePosition`; the incoming code imports `material`). Both
  migrations are ordered (`incoming 0001` depends on `material 0009`,
  `material 0010` on `incoming 0001`), and the FK is a string reference.
  It is the one place where the table graph in
  [architecture.md](architecture.md) is not a line.
- **The source link is the protection against double booking.** Which
  items a position made is written **at the item**
  (`MaterialItem.source_position`, `SET_NULL`), not as a counter on the
  position, so a deleted item gives its piece back and a count cannot drift.
  `booked_counts` counts rows and pieces (a bulk row counts its quantity).
  A position booked in already is booked again only with "Nochmals
  einpflegen" (`Entry.book_again`); a partly booked one is completed
  (the pieces start where the booked ones ended, so the odd cents stay
  where they were). The invoice becomes "eingepflegt" when all goods are in
  (`mark_booked_in_when_complete`).
- **Reading proposes, the user decides.** Re-reading never overwrites
  what was typed and never touches a position that is booked in. A
  supplier that is unknown is proposed (AI) or typed, and created only
  with the button "Lieferanten anlegen" – the AI never writes into the
  master data. A scan or picture is kept and **not** read (no text
  recognition).
- **Foreign currency.** `currency` and `exchange_rate` exist; every cost
  is converted to euros with the rate before it is shared and stored. A
  rate of 0 or less blocks booking in.
- **Rights.** The register is open to who has the purchase-prices right and
  reads the material; changing, re-reading and booking in need write access
  to the material, deleting the delete level (`incoming/access.py`). The
  settings page needs the Administration module. The totals of an invoice
  are `audit_sensitive` with the purchase-prices right.
- **Files** go to `MEDIA_ROOT/incoming/<year>/<random>` and are delivered
  by a protected view; they belong to the backup. Removing a position that
  is booked in is refused; so is deleting an invoice with booked positions.
- **Rejected.** (a) *Extending the wizard to keep its invoice*: it would
  mix a one-step flow with a long-lived record. (b) *Booking in without the
  preview page*: a mistaken booking makes many items at once; the page names
  exactly what will be made and wants "Ja, genau so einpflegen". (c) *Saving
  the cost of an item as a function of the invoice* (so a later change of the
  key rewrites the items): items keep the cost they got; the books must not
  change under an item that was booked.

### Cost allocation: cent-exact, one key per invoice (DOK-024)

- **Context.** Freight, packaging, customs and discounts are positions of
  the invoice. For the books they belong to the cost of the goods
  (Anschaffungsnebenkosten).
- **Decision.** Positions marked "Nebenkosten" (a discount is a negative
  amount) are added and **shared over the goods positions** by **one key per
  invoice** (`IncomingInvoice.allocation_key`): value (default; the net
  amount of the position), quantity, or weight (weight of one piece
  times quantity; the piece's own weight, else the model's). `incoming/
  costing.py` computes it and stores nothing; the page, the API
  and the booking in call the same `costing_of`.
- **Cent-exact.** `spread` works in whole cents with the **largest
  remainder** method, so the shares add up to the ancillary costs exactly;
  a negative amount is shared the same way, negated. The share of a
  position is shared over its pieces by `even_slice_cents`: every piece gets
  `total // pieces` cents and the first `total % pieces` pieces one more. A
  position booked again continues at the piece where it stopped (`start`).
  A bulk row gets the sum of its slice.
- **Why one key per invoice, not per position.** The key is a property of
  the *freight*, not of the goods: a pallet is shared by weight, a postage
  fee by quantity. Per-position keys would need a decision for every
  freight line and an order in which they apply. Changing the key shows
  the new split at once (the page asks `costing`, nothing is saved).
- **Honest failures.** No goods, no weight for a goods position (when
  sharing by weight), or goods that add up to nothing: `Costing.problems`
  says so, booking in is refused, and no key is guessed. A quantity that
  is not a whole number cannot be booked as items ("pieces are counted
  whole").
- **Rejected.** Rounding every share and booking the difference on the
  largest line (hides the error where it is largest); sharing the cost per
  *piece* equally (ignores value); a free percentage per position.

### Asset kind, GWG limit, linear monthly depreciation (MAT-086)

- **Context.** A booked-in piece is merchandise (for sale or rent-out at
  cost), a low-value asset (GWG) or a fixed asset with a useful life.
  The requirement: the book value ("Mit Restbuchwert"), the used sale
  booked against it, and no DATEV export.
- **Decision: the kind sits on the item.** `MaterialItem.asset_kind`
  (`merchandise` / `low_value` / `fixed_asset`; **empty on all existing items** –
  not classified, no book value), `useful_life_months`,
  `ancillary_cost_net`, `acquisition_cost_net` (= purchase price + share;
  kept as a column so lists and the register do not recompute) and
  `source_position`. When nobody names a kind, `assets.kind_for` decides by
  the limit of `AssetSettings.low_value_limit_net` (800 € net) **applied
  to the cost per piece, inclusive** – 800,00 € is still a GWG;
  merchandise is never guessed. A fixed asset without its own life gets
  `default_useful_life_months` (60). Existing items can be entered by hand
  on the card "Anlagevermögen".
- **Rules** (`material/depreciation.py`, pure functions, no database, no
  clock): linear by **months**; the month of acquisition counts as a full
  month (and so does the month of the date a value is asked for); GWG
  fully written off on 31 December of the purchase year (before that day –
  also in that year – the book value is the full cost); merchandise stays at
  cost; optionally 1 € memory value (`AssetSettings.keep_memory_value`, off).
  A date known to the year only starts in January; a date in the future is
  "noch nicht angeschafft" (not in the sums); missing cost, date or life
  means **no book value** (listed apart in the register rather than shown
  as 0).
- **Rounding of the accumulated amount.** After `k` months of `life`,
  the written-off amount is `round(base × k / life)` (halves up), an
  instalment is the difference of two such amounts, and from `life` months
  on it is the whole base. So no instalment is more than a cent from the
  exact one, a year's amount is as exact as cents allow, and **the last
  month balances**: the instalments always add up to the base to the cent.
  Rounding each month and summing would drift by up to half a cent per
  month; a balancing month would hide it in the last cent.
- **Consequences.** The rules are not configurable (the settings hold only
  the limit, the standard life and the memory value): a configurable method
  would be tax advice. The register (`/accounting/assets/`, CSV, API
  `asset-register`) reads the same functions; cost of the page: 12 queries
  whatever the size (0,06 s for 100 items, 0,28 s for 1,000).
- **Rejected.** A stored depreciation schedule per item (it would be stale
  at once when a date or the cost is corrected – the schedule on the card is
  computed on every request); a daily pro-rata method (the month is the
  unit, the "Monatsprinzip"; the half-year rule was abolished for movable
  assets in 2004 and is not applied); degressive depreciation (see above).

### Used sale from stock: status "verkauft" and `SaleFromStock`, no DATEV (MAT-087)

- **Context.** Used sale from stock, like the sale of used goods: an item –
  or a quantity of bulk material – is sold out of the stock for a price,
  and the sale should show gain or loss against the book value.
- **Decision.** The item leaves the stock through the **existing status
  mechanics**: `material.services.set_status(... "sold")` (German
  "verkauft"), so every rule of archiving holds without a second
  implementation (nothing may be installed in it; availability, packing
  and lists already treat the status). The new table `SaleFromStock` keeps
  what the status cannot: buyer (customer, contact or text, kept as
  written), day, price, tax rate, the book value **as it was** with its
  basis (`calculated` or `unknown`), cost, accumulated depreciation,
  gain/loss, and what is needed to reverse (`previous_status`,
  `previous_reason`, `row_quantity_before`, `price_part`,
  `ancillary_part`, `item_left`).
- **Preview, then confirm.** `sales.preview` works out book value and gain
  or loss and lists `problems` (stop), `warnings` (ask for a tick) and
  `notes` (only said). Stopping: left the stock already, in use, installed
  in or containing items, chosen/packed/out for a project, a date in the
  future or before the purchase, a quantity that does not fit, a price
  below 0, no buyer. Asking: wished for by a line of an unfinished
  project, blocked for a coming period. Saying: an item that is no asset in
  the books is sold with book value 0 € and the preview says so.
- **Bulk material:** a part of the row is sold; quantity and cost of the
  row are reduced by that part's share, and `price_part`/`ancillary_part`
  keep the amounts so that the cancel puts them back **exactly**.
- **Storno, not delete.** A sale is cancelled with a reason as long as the
  item is still "verkauft"; the record stays, marked with who/when/why, and
  is listed as cancelled. The history entry of the item carries no amounts
  (the history is read by everyone who reads the material); the amounts
  stay in the record, behind the purchase-prices right.
- **No DATEV, no invoice link.** "Rechnung dazu erstellen" opens a free
  outgoing document draft for a buyer who is a customer; the
  draft is not tied to the sale. A sale to a private person without an
  account is a record only. Anonymising a customer removes the name from
  sales, change log, item history and the status reason.
- **Open:** sales of bulk material are not checked against planned
  quantities; a sale before the purchase date is refused; dates in the
  history are ISO.

### Partial purchase dates: first of the period plus precision (MAT-088, MAT-050)

- **Context.** Of an old item people know the year, or the month: "00.00.2015".
- **Decision.** `purchase_date` stays a real date – the **first day of the
  known period** – and the new `purchase_date_precision` (`day`, `month`,
  `year`; default `day`) says how much is known (`material/partial_dates.py`).
  Typed forms: `12.05.2015`, `00.05.2015`, `05.2015`, `2015` and the ISO
  forms; years outside 1900–2999 are refused (a typo is not stored). Shown
  as `2015`, `05.2015` or the full date in lists, item, model, CSV and the
  check report; in the API `purchase_date` is an ISO text with zeros
  (`2015-05-00`, `2015-00-00`), `purchase_date_precision` is read-only.
- **Why not a "year" integer or a separate text field.** The column keeps
  working in SQLite and MariaDB, sorts sensibly (a year before the dated
  items of the year), and the depreciation needs a date (it starts in the
  month of the first day).
- **Consequences.** "Kauf einpflegen" and booking in an incoming invoice
  still use complete invoice dates, on purpose. A group heading
  "Rechnungsdatum" groups a bare year and 1 January alike. Migration
  `material 0012` is one `AddField`, reversible.

### Wished items: a share per piece, not a split of the line (PRJ-064, PRD-052)

- **Context.** A product may stand for several pieces
  (`Product.pieces_per_product`): "1 pack" of 10 lamps. The requirement: to
  pin one specific lamp to such a line – read literally, the line would be
  split (1/10 pinned, 9/10 free).
- **Decision (different from the literal requirement).** The line keeps its
  quantity and its price. A pinned item **covers one piece** of the line's
  `quantity × pieces` (`MaterialLine.pieces_total`); the line shows "1 von 10
  Stück"; the remaining pieces come from any item. More pins than pieces are
  refused (`_clean_piece_share`). Several pins: `preferred_item` is the
  first, the others are the M2M `MaterialLine.further_preferred_items`
  (input: "Bestimmtes Exemplar" and "Weitere bestimmte Exemplare (ID)",
  comma separated). `wished_items` / `wished_item_ids` give all of them,
  first first, without a query when prefetched.
- **Why not split the line.** The availability engine, the packing and the
  pricing count **whole products**, and the price is **per pack, not per
  piece**. A line of quantity 1/10 does not exist; two lines (1 pinned,
  9 free) would have to be kept in step on every change of quantity, period,
  discount and surcharge, and the price of the pack would have to be cut
  into two prices that add up (rounding). A share per piece changes none of
  those consumers: the test "price unchanged" guards it.
- **Where it shows.** Packing list (screen, PDF, API) names exactly the
  pinned items with their storage spot; the allocation puts them first; the
  item dialog marks them "vom Planer gewünscht"; the wish hints
  (`projects/wishes.py`) look at every pinned item, and so do the checks that
  an item is wished elsewhere (`material/sales.py`, the timelines).
  Duplicating a project or a line copies the M2M.
- **Open.** Kit components cannot carry pins. Adding the same pack again
  with another item creates a **second pack**, not a second pin. If the user
  wants a true split of the line, it needs two lines kept in step – ask
  before building it.

### Planning follows stock; scroll anchoring (UIX-056, UIX-020, PRJ-012)

- **Context.** A planning tab left open did not show a model newly linked
  to a product in another tab: the planning followed only
  `project:<pk>` (the change log with this project as parent), while the
  availability depends on models, items, blocks, products, kits and the
  lines of **all** projects, none of which write a log entry for this one.
- **Decision.** A new change key `stock:<pk>` (`core/changes.py`, on the
  planning page `projects:detail` only), whose stamp
  (`projects/stock_watch.py`) is the **newest change-log id of each of
  seven kinds of object** the availability is computed from
  (`MaterialModel`, `MaterialItem`, `ItemBlock`, `Product`, `KitComponent`,
  `MaterialLine`, `Project`). The question is **8 cheap queries** (the
  project, and seven `MAX(id)` answered from the end of the `content_type`
  index), and builds nothing. It is empty without the Verfügbarkeit right
  (AUT-032) or when the project cannot be read, so such a tab never asks for
  figures. The stamp contains no ".", so the script does not count it
  after the page's own change (PER-033): saving in this tab does not make
  the tab ask for itself; a change by the same user in another tab does –
  that is the wish.
- **A fragment, not a reload.** When the stamp moved, the page fetches
  `projects:planning_availability` (`/projects/<n>/planning/availability/`)
  and swaps only the availability column, the wish hints and the hints above
  the lines (`_planning_stock.html`, `_line_availability.html`,
  `_line_wish.html`). Typed text, scroll position and dialogs stay. Triggers:
  switching back to the tab (visibility/focus, at most every 3 s) and the
  existing 20 s change poll. Measured: a full reload costs 41 queries and
  163 KB, the refresh 38 queries and 15 KB; the poll costs +8 queries.
- **Not covered:** ticks on packlists (`PackEntry` writes no log entry);
  material taken out of the stock shows with the next stamp of the material.
- **Scroll anchoring (same requirement).** Saving a group, subgroup or line
  answers with the whole planning block, which replaces the old one. Chrome's
  scroll anchoring moved the page by the height of the inserted block, and
  with the old block gone the page ended at the bottom. The fix is in
  `static/js/app.js` (block "subgroup scroll"): `htmx:beforeSwap` notes
  scroll position and the open/closed state of every `<details>` of the
  `#planning` block, and puts both back after the swap. Not done: turning
  scroll anchoring off for the whole page (`overflow-anchor`) – the
  browser's behaviour helps elsewhere, so the fix is local to the swap of
  the planning block.

### Overall discount by target amount: 6 decimals, not recomputed (PRJ-123)

- **Context.** The planner types the total the project should come to – net or
  gross, after the discount – and wants the percentage found.
- **Decision.** `projects/overall_target.py`. **Net:** the discount is the
  total before the discount minus the target; the percentage is the one with
  the fewest decimals (2 to 6) whose discount, rounded to the cent as
  `pricing.overall_discount_of` does it, equals that amount. **Gross:** the
  gross total follows from the net by tax **per rate** (a discount lowers
  every rate in proportion, one cent of rounding goes to the largest share),
  so it is not a division; the discount in cents is searched by bisection over
  the pricing code's own split (`totals_after_overall_discount`). If a gross
  amount cannot be reached to the cent, the nearest is taken and the
  user is told ("exact" or "nearest possible").
- **Six decimals** (`overall_discount_percent` 9,6; migration `projects
  0035`) reach the cent for projects up to a million euros. Documents, the CSV and
  the price overview print up to six decimals without needless zeros (R3-3), so
  the printed percentage reproduces the printed discount; the stored value is exact.
- **Not recomputed.** Only the percentage is stored. When material is added
  later, the percentage stays and the total moves; the user types the target
  again. Storing the *target* and recomputing would silently change the
  percentage on documents already sent. Preview first (`dry_run`); API
  `POST /projects/{id}/overall-discount` with `percent`, `amount`,
  `target_net`, `target_gross`, `dry_run`; 403 without the prices right.

### Smaller changes of the planning, PDF and manual (PRD-046, DOK-025, UIX-057)

- **Model search in the product form (PRD-046).** "Vorhandenes Modell
  zuordnen" finds free models by name, manufacturer and category word by word,
  suggests on focus, shows models that belong to a product already (not
  selectable: "gehört schon zu …") and "Kein Modell gefunden".
- **PDF documents (DOK-025).** The discount column prints only if a line has a
  discount; number columns are aligned under their headings; the hierarchy is
  Material, Personal, Logistik (and surcharges) on top, under Material the
  subgroups, then the lines, with a sum row per top level ("Summe Material").
  The amounts are unchanged.
- **Manual in chapters (UIX-057).** `/manual/` is the table of contents with
  search, `/manual/<n>/` one chapter. `core/manual.py` splits the file at its
  second-level headings (outside code blocks) and renders **only the chapter
  asked for, on the first call**, cleans it (nh3) and **caches it in
  memory per process and file modification time**. A link to an anchor in
  another chapter becomes a link to that chapter's page; the old
  `/manual/#7-projekte-planen` is forwarded by a small script (the server
  never sees the anchor) with the help of `/manual/anchors/`. An unknown
  chapter is a 404. Measured: one page of 815 KB and about 900 ms before;
  chapters of 14 to 55 KB and about 400 to 660 ms after. Rejected: a
  cache in the database or on disk (a package update changes the file; the
  modification time is the key) and a static HTML build (the build step the
  project avoids).
- **Mail of the crew request:** a line "Firma:" before "Projekt" – not in the
  calendar description, price overview or packing list. **Mein Konto:** the API
  token table turns into cards at 360 px.

### Scanning: one resolver; the camera is an extra (MAT-027, UIX-006, PCK-010, PCK-011, PCK-016, PCK-022)

- **Context.** A phone's camera, a hand scanner that types like a keyboard
  and a person typing all deliver the same thing: a text.
- **Decision: one resolver.** `material/scan.resolve(code, rights)` is the
  only code that turns that text into something: an **item** (ID with or
  without `#`/leading zeros, the QR address of a label – the setting's
  pattern with `{id}` or `{RENTALARS_URL}/m/<ID>` – or a serial number), a
  **product by GTIN** (8, 12, 13 or 14 digits), a **storage spot**
  (`01-A-1`) or a **storage location**; AIM symbology prefixes (`]Q1`) and
  trailing control characters of a scanner are tolerated, a code over 300
  characters is no label of ours. The pages (`material:scan_resolve`), the
  packing list and the API (`GET /scan/resolve?code=`) all call it
  (API-002). Nothing in it creates or changes anything.
- **A code without a right answers like an unknown code** ("none"): a scan
  must not tell whether something exists.
- **The camera is optional.** The field "ID scannen oder eintippen" always
  works (keyboard, USB scanner). The camera button opens a `<dialog>`
  (`static/js/scan.js`) and works only on HTTPS (localhost counts) in a
  browser with `BarcodeDetector` (Chrome, Edge, Android); Firefox and Safari
  fall back to typing and the USB scanner, and the dialog says so. No
  library is bundled; no inline script (the content security policy forbids
  it). The camera stops when the dialog closes, the page is left or the tab
  is hidden.
- **No camera frame leaves the browser.** The browser decodes; only the
  decoded **text** is sent, and only when the page asks. The header
  `Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=()`
  (`core/middleware.py`; the other three added in the review) lets the page
  itself use the camera and nobody embedded in it. Rejected: decoding on the
  server (it would send video of the warehouse and the people in it to the
  server); a bundled decoder as the fallback (jsQR, Apache-2.0, would work
  in Safari/Firefox; **not built**, the open option if those browsers
  matter).
- **Packing (PCK-010, PCK-011, PCK-016, PCK-022).** `packing/scan.py`:
  a scan chooses the item for the row of its product (the row that has it
  chosen already, else the first that still needs items) and counts it up
  ("4 von 6"; per piece for products of several pieces). The same code twice
  does not count twice. Refused with a reason: no row, defective or blocked,
  planned or out for another project, all pieces chosen; an overdue
  inspection only warns. Scanned items go out first. A return scan counts
  only an item allocated at issue, once; booking the return stays a step of its
  own. Bulk material is confirmed by count, a scan only points to the row.
  Scanning stays voluntary (PCK-020): ticking by hand works as before.
  `Allocation.packed_scan_at` and `returned_scan_at` (migration `packing
  0009`) keep when.
- **Not tested for real:** the camera, `BarcodeDetector`, real labels, a USB
  scanner (all simulated). Planning wishes by scan use the same dialog in
  "plan" mode; the product search in the planning does not take QR
  addresses.

### Accessories and replacements belong to the product (PRD-023, VFG-015)

- **Decision.** `ProductRelation` (product, related product, kind
  `accessory`/`replacement`, order, note, `is_required`, `quantity_per_piece`)
  hangs on the **product**, not on the material model or item: projects are
  planned with products (PRD-001), whichever models stand behind them. The
  product page edits them; the model page shows them read-only. A pair of
  products can be related once per kind (unique constraint).
- **Accessories** (`products/suggestions.py`): for each product in the
  planning, the accessories not in the planning yet – neither as a line nor
  inside a planned kit. The quantity is quantity × pieces per piece, rounded
  up (6 speakers, 1 cable per speaker: 6 cables); "required" says so. One
  click adds the line with that quantity.
- **Replacements:** for a line that is short or whose product is
  deactivated, the replacement products with what is free of them in the
  line's period, **judged by the availability engine as if added to the
  project** (`check_candidate`; nothing is calculated a second time).
  Shown with numbers only to who has the Verfügbarkeit right (AUT-032);
  without it only the product. At most 12 suggestions per kind and 8
  short lines are judged at once (each costs a run of the engine).
- **Beside the planning, never in its way.** The panel is lazy-loaded; a
  suggestion can be dismissed **per project** (`DismissedSuggestion`) and
  restored; in the offer step only a hint appears, nothing is added.
  Cost: the planning of 40 lines +1 `exists` query; the panel 56 queries
  when it loads.
- **Rejected.** Relations on the model (two models of one product would
  need the same list twice); adding accessories automatically (the requirement
  was suggestions); showing replacement availability to everyone.

### Built-in quantity material without a stock ledger (MAT-040)

- **Context.** A rack case holds 10 m of cable and 4 connectors. Cable and
  connectors are bulk material – one row with a quantity (MAT-005).
- **Decision.** `InstalledQuantity` (container, bulk row, quantity, note,
  who/when; unique per pair, `PROTECT` both ways) is the container's bill
  of material. Installing **reduces the quantity of the bulk row** (the free
  stock), taking out raises it. So the stock of the product, the
  availability, the planning and the packing – which all read the row's
  quantity – see the free stock without a change of their own, and nothing
  is counted twice. The container is any item of individual items, never bulk
  material and never archived; an item with built-in parts cannot be sold.
  A case that goes out takes what is built in along; the packing list names it
  under the case as "enthält" lines, not as extra work. Removing with an
  empty quantity takes it all out; partial removal works.
- **Audit events, no stock ledger.** Both movements are written as events
  with quantity, user and time to the history of the container **and** the
  bulk row; the change of the row's quantity is in the change log as for any
  change. There is no table of stock movements, so there is no balance
  to reconcile with.
- **Rejected.** A ledger of movements (every consumer of stock would have to
  sum it); a new bulk row inside the container (it would take an ID and
  split the cost); counting built-in parts as `installed_in` (that is for
  single items, MAT-033).
- **Open:** no overview of what is built in across all containers.

### Login with LDAP / Active Directory (AUT-029)

- **Library and layering.** `ldap3` 2.9.1 (LGPL-3.0, pure Python) with
  `pyasn1`; both in `requirements.txt` and `THIRD-PARTY.md`, the licence
  check accepts the LGPL for them. All that touches the network or the
  library is in `accounts/ldap_client.py`; the rest speaks about
  `DirectoryEntry` and `DirectoryError` (codes `not_configured`, `blocked`,
  `unreachable`, `tls`, `service_bind`, `search`, `ambiguous`, `entry`).
  One connection factory creates every connection – which is how the tests
  replace it.
- **A second authentication backend, not a second login.**
  `AUTHENTICATION_BACKENDS` asks the local `EmailOrUsernameBackend` first and
  then `LdapBackend`. So the login page, the second factor (AUT-006), the
  protection against guessing and lockout (AUT-005) and the security log
  (AUT-022) are the code that existed; the directory is one more way to say
  yes. With 2FA on: the LDAP password first, then the code.
- **Tests: `MOCK_SYNC` and an optional real OpenLDAP.** Almost all tests
  run the real search, filter and bind code against an in-process `ldap3`
  `MOCK_SYNC` directory (`tests/ldap_fake.py`). One opt-in module,
  `tests/unit/test_100_ldap_slapd.py`, starts the operating system's `slapd`
  on 127.0.0.1 with the `memberOf` overlay and a self-signed certificate
  (`RENTALARS_SLAPD=1`, `apt install slapd`; otherwise skipped) and covers
  what a mock cannot: TLS with a certificate check against the host name
  (`ldaps://` and StartTLS), the bind, `memberOf`, groups found by search.
  **Not tested: Active Directory** (`sAMAccountName`, nested groups,
  referrals, paged results, a real company CA).
- **Role sync rules** (`accounts/ldap_sync.py`, one rule set for four callers
  – the login, the dry run "Anmeldung testen", the nightly comparison and
  `set_user_roles` – so they cannot disagree):
  - a user gets the roles of **all** mappings whose group they are in
    (union), in the order of the priority; a mapping with "last match" ends
    the list for that user. The directory never grants "all rights".
  - roles from the directory are written down (`LdapRoleAssignment`) and
    **cannot be removed by hand**; roles an administrator gave stay. If the
    administrator had given the same role first (`also_manual`), it stays
    when the directory takes it back.
  - roles follow the groups at every login. An account is created at the
    first login only if the user gets at least one role (`auto_create_users`);
    a user in no mapped group is refused and, if the directory keeps the
    account, **deactivated** – but only if the directory had activated it
    (`ldap_deactivated_at`); an administrator's deactivation stays.
- **Last-admin protection.** The directory never deactivates, nor takes the
  administrator role from, the last account that can change the settings.
  Switching local passwords off requires an active **local (emergency)
  account** with its own password and the right to change settings
  (`has_local_administrator`), otherwise nobody gets in when the directory is
  down.
- **Local accounts.** `User.local_account` marks an emergency account: the
  directory never changes its roles or deactivates it and is **not even
  asked** at its login; superusers ("all rights") are treated the same.
  Directory accounts have no password in Rentalars (`set_unusable_password`);
  password change, reset and invitation are off for them. Rejected: giving
  every account both ways – a directory outage would lock everybody out.
- **Dry-run default sync.** `manage.py ldap_sync` only reports; `--apply`
  writes; `--force` passes the protection limit that stops the run when more
  than three **and** more than half of the accounts would be deactivated (a
  wrong filter or a directory that answers with nothing must not empty the
  user table). "Unterschiede anzeigen" / "Diese Änderungen anwenden" on the
  settings page are the same two steps; `sync_daily` runs the comparison
  from `run_daily_maintenance` (off by default).
- **Why server names, not IP addresses.** `ldap3` compares a certificate's
  names only with its DNS entries, so `ldaps://10.0.0.5` fails the check
  that must stay on; and the address guard (`core/network.py`)
  already refuses an internal address typed into a form unless the operator
  lists it under `[network] allow_internal`. One rule serves both: enter
  the server by name, list the (internal) name in `allow_internal`.
- **Security details.** The typed name is Unicode-normalised (a name that is empty, over 256
  characters or holds control characters is refused) and escaped with
  `escape_filter_chars`; placeholders
  (`{username}`, `{user_dn}`) are replaced in **one pass** so that a name that
  looks like a placeholder is not replaced again; an **empty password never
  reaches the directory** (many servers take a bind with a name and no
  password as anonymous – and would "log in" the user); no password in logs
  or errors (tested); the bind password of the search account is Fernet-encrypted
  and dropped when the servers or the bind DN change; a changed
  `secret_key` makes it unreadable (enter it again). Five new security-log
  kinds (`ldap_refused`, `ldap_error`, `ldap_account`, `ldap_roles`,
  `ldap_sync`); the reasons reach the log, never the user.
- **Open.** Nested AD groups need a group search with
  `member:1.2.840.113556.1.4.1941:={user_dn}` (not verified); no history page
  of the sync (only the security log); large directories untried.

### Price offers of freelancers (PER-038)

- **Context.** A freelancer asked for a deployment may want to name his own
  price instead of accepting the stored rate. Optional, **off by default**
  (`OfferSettings.enabled`): then a request is answered "accept" or
  "decline" exactly as before.
- **Rules.** The freelancer answers with "Preisangebot machen": per hour,
  per day (only for lines billed per day) or in total, a message, a "valid
  until". Each proposal is one `PriceOffer` row; the company accepts,
  rejects or counters; a counter is answered the same way; the freelancer
  can withdraw. At most `max_rounds` proposals (default 4, 1–10) of both sides
  together, then only accept or reject is left; limits in percent of the
  stored rate (optional, lowest/highest; "temporary staff too" off by
  default). A new request starts a new negotiation. EUR only, two decimals,
  30 actions per user per hour.
- **Accepting is a yes to the deployment at that price:** the request is
  answered "zugesagt" through the usual `answer_deployment` (the people of
  the project are told as always) and the **cost rate of exactly that crew
  line** follows the offer: `hourly_rate`, `daily_rate` or `cost_flat_rate`.
  The previous values are kept on the offer so it can be taken back. The
  customer's price never changes.
- **Why "exactly one crew line".** A stored rate belongs to the person and
  the function; an offer is for one deployment. Writing it into the person's
  rate would change every later project. The line carries a marker while the
  offer applies and **lets go** of it when the cost rate is edited by hand,
  the person or job function changes, or – for a total – new times are
  requested (`after_line_update`, `on_new_request`). Rejected: a
  per-person standing price; applying the offer to the customer price.
- **Privacy.** Amounts are personnel costs (AUT-019): a freelancer sees only
  **his own** offers; the stored rate only with the personnel-cost right or
  `people_see_own_rates`; without the personnel-cost right the planning shows
  nothing of offers (no badge, no "hinterlegt"); notifications go only to
  users with that right who can read the project. The change log of an offer
  belongs to the **person's** history, not the project's, so readers of the
  project do not see that a price was negotiated.
- **Notifications and mail.** Two kinds (`price_offer`, `price_offer_answer`,
  migration `notifications 0012`). The request mail gains one line ("Du
  möchtest deinen eigenen Preis nennen?") while the feature is on. The
  companion-app default of notifications was **not** changed (users can switch
  the new kinds on).
- **Tests:** 108 plus a browser test, MariaDB checked. Not tested for real:
  mail delivery, real phones, real concurrency.

### Importing old projects from their invoices (PRJ-130)

- **Context.** Past projects exist only as invoices (PDF) of the old system.
  The requirement: they become closed projects with history, without disturbing the
  live system.
- **Decision.** Buchhaltung → "Altprojekte importieren"
  (`projects/legacy_*.py`; right: see prices and write projects). Up to 30
  PDFs, 10 MB each, 120 MB a batch, kept under `DATA_DIR/legacy-invoices`
  and fingerprinted (SHA-256). A background job (`legacy_invoices`) reads
  each: with AI (the setting and provider of invoice reading, `Use.INVOICE`;
  only the **text** goes out) or, if AI is off or fails, by patterns
  (`legacy_text.py`). The result is an editable **preview** with warnings
  (sums against totals, tax, quantity × price) and errors (no number, number
  exists, number inside the running sequence); a **confirmation page** says
  exactly what will be created; a batch can be confirmed partly.
- **Strict schema validation of the AI output.** The answer is data from a
  machine that read a document from outside – the invoice may contain
  sentences written to steer it. `parse_answer` accepts only the expected
  keys and types, cuts every text to its column length and cleans control
  characters, parses numbers itself in the invoice's style (never a float), and
  allows at most `MAX_LINES` positions. **Nothing the answer says reaches
  further than the preview**: it cannot choose a customer, product, project,
  number range or right – Rentalars matches those afterwards and the user
  confirms.
- **Quiet mode.** `legacy_quiet.quiet()` (a context variable in a module
  without imports, so the listeners can ask without loading the import) keeps
  the two listeners that would fire on a project created already closed –
  automations "reached a status" and the webhooks – silent. No mail, task,
  notification, reservation or availability (a closed project reserves
  nothing), and nothing is handed to Lexware.
- **Own counter `ALT-<year>-<nnnn>`.** Imported projects must not use up live
  project numbers: `_next_project_number` counts per year under the prefix
  `ALT`. The **live invoice number sequence is untouched** (`NumberRange` is
  not written); the old number stays on the document, and a number inside the
  running sequence is an error in the preview, so it cannot collide later.
- **Historic flag.** The record `LegacyImportItem` (one per PDF; hash,
  proposal, what was created, who, when) has a one-to-one `document`; a
  `Document` is *historic* when it has that reverse link
  (`Document.is_historic`). Historic documents are not bookable, not
  cancellable and not in the Lexware error list; the DATEV export leaves them
  out unless asked ("historische Belege einschließen", API `include_historic`).
  The result per invoice: a closed project with free lines (optionally mapped
  to products), a historic invoice with the original PDF, state "paid"
  selectable, and "Importiert aus Rechnung …" in notes and history.
- **Retention and undo.** An upload not taken over is kept **14 days**
  (`PENDING_DAYS`) – cleaned **when the overview is opened or the next file is
  uploaded**, not by the nightly job. The import can be **undone within
  7 days**, by who made it or an administrator, only if nothing was changed
  since (no change-log entry after the import, no document, mail, file, time …
  added); the same PDF (hash) or the same number plus customer is detected
  as a duplicate.
- **Not supported:** scans (no OCR), other currencies, credit notes.
  Measured: 30 PDFs read in 4.6 s; the batch page 369 queries, 2.3 s, 407 KB;
  confirming 30 takes 5.0 s. **Not verified: the quality of the reading with
  real foreign invoices** – have someone run a few and read the preview
  critically.

### Automatic AI summaries (EML-056)

- **Context.** AI summaries are to be made automatically (for example every
  night) in projects and service cases when something changed since the
  last summary.
- **Decision.** `manage.py ai_summaries` (`ai/auto.py`), started by the
  existing minute timer `run_jobs` as the task `ai_auto_summaries`, once per
  night and only inside the window. **One run at a time**: a row of
  `AutoSummaryRun` with a unique `lock` and a heartbeat (a run silent for two
  hours counts as dead); the unique constraint works on SQLite and MariaDB
  alike. Options `--dry-run`, `--project N`, `--limit N`. It is the second
  door to the **same logic as the button** (`ai/summary.py`: `prepare_texts`,
  `summarise`, `store_summary`).
- **The hash of the input is the change criterion, not a timestamp.**
  The cheap marks first (number of mails, newest mail, newest chat message
  against those the stored summary was made from); only when they differ are
  the texts built, cleaned and hashed, and **no model is called if the hash
  equals the stored one** (e.g. a locked mail arrived that the job may not
  read; planning lines, tasks and documents are not in the text and cannot
  make a summary old). A timestamp would pay for every irrelevant touch of a
  project; the hash pays for exactly the text the model would get.
- **Service principal.** The job has no user; it acts as `system:ai-summaries`
  with a minimal scope fixed by the settings (`automatic_scope`): mails and
  notes of the project and its parts; chat only if the administrator wants it;
  prices only after release; the same data-class removal as every summary.
  Whoever sees the stored summary is decided by the rights on the page, as for
  a summary by hand. Rejected: running as the administrator who switched it
  on (a person's rights would silently widen what is sent).
- **Consent bound to the provider.** Off by default. Switching on records who
  agreed, when, and **for which server**: `consent_key` is `local` or
  `provider:<scheme>://<host>:<port>`. If the summaries' provider changes to
  another server, or from local to a cloud service, `consent_holds` is false
  and the job stops until consent is given again. A change of model or name
  does not need new consent; where the texts go does.
- **Budget and brakes.** Window (default 01:00–05:00); at most 20 a night;
  a budget of 200,000 tokens a night (0: none); a minimum interval (20 h) and
  a minimum of 2 mails; only chosen statuses of projects and service cases;
  exclusion per project and per customer (`AutoSummaryExclusion`); a stop
  after three failures in a row (the provider is probably down), retried
  later the same night up to three times. Errors never stop the job; the
  project is a candidate again the next night; administrators see every run
  and its errors (`/ai/auto-summaries/runs`); no notifications.
- **Versions and labels.** The summary stores time, model, provider, hash and
  "automatisch"; the earlier text goes to `AISummaryVersion` (default 5
  kept); an automatic summary **never overwrites a manual one unmarked**.
  The project page shows the last one with "automatisch erstellt", a hint when
  newer mails exist, "Erneut zusammenfassen" and the earlier versions, for
  those who may read all messages; +2–3 queries.
- **Locked mails** (EML-055) are **read by default**
  (`auto_include_locked`): in projects every message starts with the lock, so
  the job would otherwise read nothing; the summary shows only to who reads
  all messages anyway, and the notice of the opt-in names the data class. This
  is a decision to confirm (finding 17 below).
- **Not tested for real:** real providers, the MariaDB lock column, the systemd
  timer.

### Information-security review of the AI summaries (NFA-079)

The requirement: check the information security of the summaries. All
paths that send text to a provider were reviewed (summary by hand, nightly
summary, reply draft). Seventeen findings; eleven fixed, six left open on
purpose or by nature. (Numbered 1–11 in the order of the review notes; 12–17
as there.)

| No. | Finding | Status | Measure / reason |
|---|---|---|---|
| 1 | Personal and secret data in the text sent (IBAN, cards, passwords, tokens, e-mail addresses, phone numbers) | fixed | `ai/privacy.prepare` removes them before sending, per data class (`AISettings.privacy_remove`, default all); IBAN by check digits, cards by Luhn |
| 2 | The nightly job had no limited identity | fixed | service principal `system:ai-summaries`, minimum scope from the settings |
| 3 | Prompt injection through mails and notes (delimiters, role tokens, hidden characters) | fixed | `privacy.neutralise` takes `>>>`, `<|im_start|>` and the like apart and strips zero-width, bidi and tag characters; instruction and data stay separated |
| 4 | Model output shown or stored as HTML/links/images | fixed | `privacy.clean_output`: plain text, no tags, no Markdown images or links, no `javascript:`, length cap; escaped again on display; no code reads the answer as a command |
| 5 | No brake on cost and misuse | fixed | summaries by hand per user and hour (`manual_per_hour`, 30), cap of input characters, token budget and count per night |
| 6 | Text to internet providers over http, redirects, internal targets | fixed | https required for an address on the internet (saving http is refused), no redirects, the guard of NFA-071; answers capped to 2 MB |
| 7 | API key in `repr`, log or error page | fixed | `Endpoint.api_key` has `repr=False`; the key is stored encrypted and never shown |
| 8 | Consent not tied to where the text goes | fixed | opt-in recorded with who/when/server; stops on a change of server |
| 9 | Automatic calls not told apart from calls by hand in the log | fixed | `AICall.automatic`; calls are logged with counters, the user or the principal, never with content; the job's runs list candidates, summarised, unchanged, failed and tokens |
| 10 | Customer export and anonymisation did not cover summaries | fixed | export lists summaries and versions; anonymising erases them (`ai.auto.forget_customer`) |
| 11 | Reply drafts used unfiltered text | fixed | drafts go through `redact` and `neutralise`, output through `clean_output` |
| 12 | No operator allow-list of provider hosts | **open** | a `[ai] allowed_hosts` list in the configuration would pin where text may go; **not built** |
| 13 | Names and addresses in free text go to the provider | **open, not solvable** | no filter can recognise them; the operator decides by the choice of provider (a local model never leaves the server); the opt-in names the data class |
| 14 | Chat as a trigger of staleness is incomplete | **open** | with chat in the scope a *new* chat message makes a summary outdated (`newest_chat_id`, `auto.py`, `summary.shown_summary`); an edited or deleted message, and chat when the summary was made without it, do not |
| 15 | The model invents or errs | **open, not solvable** | a note in the interface says so |
| 16 | Provider error text can appear in job tracebacks | **open** | not stored with mail content, but visible to administrators in a task's result |
| 17 | Locked mails are read by default | **open, decision** | switchable (`auto_include_locked`); to be confirmed by the user |

The catalogue row (NFA-079) names the same open points: the allow-list of
provider hosts, chat as a trigger of staleness and provider error text in the
log; not solvable: the errors and inventions of models. Besides the table:
the provider layer (`ai/client.py`) now refuses to save an http address for
a provider on the internet and caps the length of answers; the opt-in page
(`templates/ai/auto_settings.html`) says in red when texts leave the company
(check the agreement with the provider) and, in a note, that names and
addresses in plain words go along.

### Traceability counts built S10 SOLL

Stage 10 holds built requirements as well as KANN ones, so
`scripts/build_traceability.py` counts **S1–S9 and the SOLL/MUSS of S10** as built and leaves the
KANN of S10 (DOK-026, PRJ-129 and the like) out; the file says so in its
summary ("and the SOLL of S10"). The generated file went from 722 built
requirements (of 747) to 742 (of 759); all are named in code, tests or
documents, none unnamed. `docs/dev/traceability.md` is generated – never
edited by hand; `scripts/check.sh` fails if it is out of date.

### The independent review

Four reviewers read the finished work, each one area, none told
what the author concluded; they reproduced what they reported (the repro files
are in the review folder, not in the repository). Together they reported 50
findings: R1 18, R2 13, R3 10, R4 9 – most of them low or medium, one
medium-high (R1-1). Each fix has a test that
names its finding as `R1-<n>`, `R3-<n>` and so on
(`tests/unit/test_100_fix_r1.py`, 43 tests; `test_100_fix_r2.py`, 78;
`test_100_fix_r3.py`, 42 and `tests/browser/test_100_fix_r3_in_browser.py`, 7;
`test_100_fix_r4.py`, 3; `tests/api/test_100_hostile_input_api.py`, 7;
`tests/api/test_100_legacy_list_api.py`, 3). This part says what was found and
what was done, and what was **not** done.

**R1 – incoming invoices, assets, sale from stock, old-project import.**

- **The most important finding (R1-1):** the invoice copy that booking attaches
  to an item (`MaterialFile` of the kind "invoice") showed the purchase prices to
  everybody who may read the material (download, file list, API). The copy
  needs the right "purchase prices" on the file page, in the file lists of item
  and model, in the API, and the kind "invoice" cannot be chosen or uploaded
  without it.
- **The bookkeeping drifted** (R1-2, R1-3, R1-4, R1-7, R1-8, R1-9, R1-12): a
  bulk row was counted by its quantity *now*, so building in or selling a part
  made the duplicate protection and the price slices wrong – the pieces a row
  was booked in with are kept (`MaterialItem.source_quantity`, material
  0014, filled for existing rows); after the first booked position the key,
  currency and rate of the invoice, its ancillary positions, and quantity, price
  and weight of the goods are locked (the forms show them disabled), so the
  ancillary costs cannot change under booked positions; an invoice in a foreign
  currency is not booked 1:1 without a word – the rate may be empty and
  booking waits for it (incoming 0002); a part sale takes the acquisition
  cost as price share plus ancillary share (no cent drift); a negative share
  (a discount) can be saved; costs of an asset without a kind are not
  ignored silently and a changed share recalculates the cost; and a rule in
  `MaterialItem.save` moves the acquisition cost with an edited purchase price
  (page and API) – unless the cost was set on purpose and differs from price plus
  share.
- **A new reading erased typed positions** (R1-5): `apply_proposal` replaced
  positions a person had typed or corrected (against DOK-023). Positions carry
  `user_edited`; a reading fills an empty invoice and keeps the touched ones,
  also when it ran while somebody was editing (incoming 0002 marks the positions
  that exist when updating, as they may have been typed by hand).
- **Smaller:** a warning for a missing invoice date (R1-6); integer
  filters beyond 2^31 do not give a 500 on pages and API (R1-10); ambiguous serial
  numbers are reported, the packing list prefers its own item (R1-11); the
  sale of a vehicle that is booked in projects is warned about (R1-14); the
  packing scan does not tell status or product of items outside the list to
  somebody who only has the packing right (R1-15); the buyer's name is not written to the history or to the reason of the
  status, and forgetting a customer replaces exact places only, not substrings
  (R1-16); a negative price of goods or a 13-digit total does not end in an
  error page, the useful life belongs to fixed assets only, and only an active
  customer can buy (R1-18). R1-13 (bulk material that is built in or sold):
  the check reads the locked row, quantity that is out with a project is not
  free, and a fraction is refused – covered **in part**.

**R2 – security: LDAP, the privacy filter of the AI, the export.**

- **Protected accounts (R2-1):** the DN branch of the account lookup did not check
  "local account" and "has all rights", and the nightly comparison could
  deactivate a superuser. The check is in both branches, such accounts are not
  part of the comparison, and `ldap_dn` is emptied when an account becomes
  protected.
- **The privacy filter is not bypassable (R2-2, R2-9):** `redact()` must run
  after the invisible characters are removed, otherwise a zero-width space
  inside an address, a card number or an IBAN gets past it. `privacy.sanitise`
  strips invisible characters, normalises to NFKC, redacts, then neutralises; the separators are
  wider; the summaries, the drafts and the reading of old invoices share it. Old
  invoices lose IBAN, card numbers, secrets and e-mail addresses but keep phone
  numbers (they are on the letterhead).
- **The export (R2-3, R2-10):** the encrypted bind password of the directory was
  missing from `SECRET_FIELDS` of the full export (a test walks all models);
  the customer export gives AI summaries only to somebody who may read them on the
  project's page and counts the rest in `ai_summaries_withheld`; deleting a chat
  message deletes the summaries that read the chat after it was written.
- **Login (R2-4 to R2-8, R2-12):** group assignments take the full DN as the
  default, a bare name is warned about on the page and in the API
  (`name_only`, `warning`); a moved entry can be taken over by an administrator
  ("Adopt the new entry", `POST /ldap/adopt-dn`), only if the old entry no longer
  exists; protected names get a dummy bind (no time difference); the setting
  `link_existing_accounts` (**off by default**) decides whether an existing
  account is taken over by a user of the directory with the same name;
  "Try a login" is
  written to the log as `ldap_test` and counts towards the lockout (API: 429);
  accounts that exist only in the directory can be invited or given a local
  password once LDAP is off.
- **Smaller (R2-11, R2-13):** the consent stop of the nightly job notes the
  night; `ldap://` without StartTLS is warned about (page, API, connection test);
  `ca_certificate_path` must be a readable PEM file; amounts of old invoices are
  range-checked in `Draft.from_json`; `Permissions-Policy` is
  `camera=(self), microphone=(), geolocation=(), payment=()`; the manual cache
  is per language; the names müller/muller, which MariaDB does not tell apart, are
  refused with a note in the log instead of an `IntegrityError`; offer events
  in the project history need the right "personnel costs".

**R3 – planning, products, discount, accessories, wished items.**

- **Pinned items (R3-1, R3-8, R3-9):** deleting the first pinned item moves the
  next one up to `preferred_item`. A pinned item that is blocked in the period is warned
  about ("… is blocked in this period: …"; "retired" keeps the pin with a
  warning). The pieces per product cannot be lowered below the number of pins of
  any line (the message names the lines, e.g. "2027-0003 (3 items, 2 pieces)");
  duplicating a project and copying a group cap the pins at the pieces of the copy.
  The line list of the API preloads `preferred_item`.
- **Overall discount (R3-2, R3-3):** NaN, Infinity and `1e400` give 400 instead of
  500 (a dry run for a finished project is refused like the real call); the
  printed percentage has up to six decimals with a German comma on documents,
  CSV and price overview ("19,99994 %"; round values "10 %"), so the printed
  percentage reproduces the printed discount to the cent.
- **Accessories (R3-4, R3-5, R3-6):** the quantity is the sum over all relations that
  name the same accessory (3 × A and 2 × B with the same K-100 give 5), rounded up
  once, and required if one of them is; an accessory planned in too small a
  quantity is suggested again for the rest; "Add" uses the same sum. A second click
  is refused ("… is already in the planning"), an accepted replacement is not
  suggested again, and editing a relation does not filter by `is_active`. The panel
  judges all lines in one run of the engine, at most six candidates checked, `delay:600ms` and
  `hx-sync="this:queue last"`, no `aria-live` on the swapped region (one status line
  when the number changes). Measured (10 lines, 8 short): service 50,
  request 59 queries.
- **Planning follows stock (R3-7):** the stamp also watches the category buffers and
  the system settings (9 checks); the script keeps at
  least 20 s between refreshes, does one more when a change came during the fetch,
  gives up after 15 s, and leaves cells with the focus or cells replaced in the
  meantime alone. The stamp stays global – per project it would cost one query per
  line per poll.
- **R3-10:** the subgroups' `<details>` are restored by a stable name
  (`data-keep`) instead of their index; `model_suggest` hides the article number
  without the right to read products; `PartialDateField` accepts `12.05.15` as 2015
  (69–99 mean 19xx, as `strptime`).

**R4 – migrations, API, MariaDB.**

- **`stock_stamp()` (R4-1):** `MAX(id)` per content type at every poll cost 0.58 s
  at one million audit rows. Measured on a private MariaDB 10.11: `core_auditlogentry`
  has no index that serves it; migration core 0025 adds `audit_type_newest_idx`
  (content type, id) – index only, no data – and the query is answered from the
  index (0.2 ms at 1.7 million rows). Creating it on a big log takes seconds per
  million rows (online in InnoDB).
- **Hostile input (R4-2):** five inputs gave 500 instead of 400. `rentalars/api/inputs.py`
  (`int_or_400`, `str_or_400`) guards four endpoints (built-in, relations POST
  and PATCH, auto-summaries); `validate_pem` also catches `TypeError` and
  `UnicodeError`. The test tries a dozen hostile values per field.
- **Nightly comparison (R4-3):** `sync_nightly` catches every exception, logs it with
  the traceback and in the history, and `run_daily_maintenance` goes on.
- **MariaDB (R4-4, R4-8):** the unique group key could exceed its column; the group
  is limited to 480 characters (checked on the folded key with its prefix), the
  system check `mysql.W003` is silenced in `settings.py` with the reason, and
  `last_match` is read-only in the API. A group of more than 480 characters would
  make the column change (accounts 0011) fail on MariaDB.
- **API-014 (R4-5):** `tests/api/test_mirror_api.py` imports the ~62 unit modules'
  `ApiTestCase` classes, so that `manage.py test tests.api` reaches all 715 operations (1284 tests,
  about 4.3 minutes). `manage.py test tests` runs nothing twice.
- **Legacy imports (R4-7):** `GET /legacy-imports` is paginated like the other lists
  (API-007).
- **R4-6** (discount decimals) is uniform in the code; the test
  `PrintedPercentEverywhereTests` pins it on the planning page, the price overview,
  the overview CSV and PDF and the document title.
- **R4-9 (offline wheels)** needed no code: see below.

**Not fixed on purpose, or open** (each was weighed; none is hidden):

- **R1-17, the course of the asset register:** the register for a past reporting
  date is not a reconstruction – items that left without a date drop out, and part
  sales lower the historic cost. Fixing it needs the history of costs and
  departures to be kept as such, which the data model does not do; left as it is.
- **R1-12, a further cause:** the fix above covers an edited purchase price
  (`cost_of` prefers `acquisition_cost_net`, and a cost set on purpose is left
  alone by design). The review rated the finding "plausible" and named no
  second repro; whether another route leaves a book value out of date was not
  found and not ruled out.
- **R1-13** is fixed in part (above); the summary of the fix does not say
  which part is left.
- **R2, probing the limits of price offers:** a freelancer can find out the limits
  of the offers by trying. Rated low; a remedy (limiting offers, hiding the limits)
  would change how the negotiation works, and nothing was decided about it.
- **R2, no privacy filter in `ai/invoices.py`:** only the path of old invoices
  (`ai/legacy_invoices.py`) goes through `privacy.sanitise`. The reading of incoming
  invoices sends the invoice text as it is. It runs only with "Read invoices"
  switched on in the AI settings, and the update notes say that these texts go to
  the provider; an open design point, not a decision that none is needed.
- **R2, not tested against a real MariaDB or OpenLDAP:** the collation and range
  behaviour of the new checks (müller/muller, the 480 characters, the comparison
  of DNs) was simulated with mocks.
- **R4, object level not tested dynamically:** freelancer B on the offers of A, the
  scope of a project, deleting a supplier, customer, item or user that new relations
  point to, webhook and automation events. Read, not run.
- **R4, N+1 of the new lists not measured:** R4 did not look at it; R1 found
  none in the incoming and material pages, and only the planning panel was
  measured (above).
- **R3, a percentage above about one million net:** six decimals reach the cent
  only for projects up to about a million euros net; above that a target amount is
  met to the nearest amount that six decimals allow, not exactly (stated under
  "Overall discount by target amount").
- **R4-9, offline wheels:** `deploy/lib.sh` installs from a `wheels/` folder in the
  unpacked package without internet, but nothing in the repository creates that
  folder – no script, no list, no instruction; `build_package.sh` leaves it out on
  purpose. `ldap3==2.9.1` and `pyasn1==0.6.4` (pure Python, universal wheels) are in
  `requirements.txt`, so whoever collects wheels from that file gets them. The
  operations pages now say that no procedure exists and give `pip download` as an
  example only; a script was not written.

### Not done or not verified

- The AI reading of invoices (incoming and old ones) was never run against a
  real provider; scans and pictures are not read at all.
- LDAP against Active Directory; large directories; nested groups.
- The camera, `BarcodeDetector`, real labels and USB scanners (simulated).
- Real mail delivery, real phones, real parallelism (price offers).
- MariaDB with the lock column of the nightly summaries and the systemd
  timer; real AI providers.
- A second real browser window for the stock refresh (simulated); the
  anchor script of the manual in other browsers.
- Open design points: kit components cannot carry pinned items; sales of
  bulk material are not checked against planned quantities; no overview of
  built-in quantities; no `[ai] allowed_hosts`; no sync history page for LDAP;
  no jsQR fallback for Safari and Firefox.

## Part 29: Wishes from practice

Five points: DOK-026 SOLL
and built; also DOK-023, DOK-024, MAT-020, MAT-021, IMP-010, PRJ-130.

- **A soft problem is not an error (IMP-010).** In the item import an entry that
  cannot be read or accepted does not stop the run: `importer._Writer._flag`
  gives the item the status `import_error` and a note line per cell
  (`<heading in the file>: <cell>`, once per line); `_repair` does the same for
  what the model refuses. ID, name and category stay errors – they have no
  substitute. A later import without the problem releases the item
  (`ItemStatus.AVAILABLE` or the status of the file). Only the import may set
  the status (`MaterialItem.by_import`).
- **The quantity of an individual item** (the confusing "Einzelexemplare haben
  immer die Menge 1"): `_repair` sets 1 and keeps the old value in the note.
- **Old invoices: kind of a position.** `legacy_draft.guess_kind` (words and
  unit) proposes material / crew / logistics; crew becomes a `CrewLine`
  without a person (billing from the unit: hours, whole days, else flat),
  logistics a `VehicleLine` with a `TripAdjustment` of its own and a flat
  `TripVehicle`. Real lines in the project, as decided; no free text.
- **Kontierung, not "Positionen".** The term was chosen in the requirements. A row asks
  for the net amount of the whole position; quantity, article number and
  manufacturer leave the form but stay in the model (reading fills them, "Book
  in goods" uses them). If more pieces are booked than the quantity, the amount
  stays and the unit price follows (`booking._chosen_quantities`,
  `costing_of(quantities=…)`; the preview writes nothing, `book` saves it).
- **The live sum** is an htmx `POST` (`incoming:kontierung_sum`) that builds the
  formset from the sent data and reads the fields one by one; nothing is
  validated as a whole or saved. `hx-sync="this:queue last"` – with `replace`
  the browser console logged aborted requests.
- **Two tabs, two prompts.** "Beleg erfassen" (`incoming:capture`) takes the
  upload; after it `?asked=book` shows the question. The reverse question
  after "Kauf einpflegen" calls `services.create_from_purchase` (one position per
  model and price, items linked by `source_position`; the same file in the
  register is not made twice).
- **SKR 03 is a suggestion.** Rentalars proposes no account and books nothing;
  the list is master data to agree with the tax adviser. The hand-over format
  stays open.

### Not done or not verified

- The update with `sudo rentalars update` on a real server; the new pages with
  real phones; the SKR 03 list against a tax adviser.
- The reading of real foreign invoices for the kind of position and the
  customer (unchanged: tried with made-up invoices only).


## Part 30: Payments, e-invoice check, ZUGFeRD, archive, EÜR

Decided earlier: the EÜR comes first and double-entry bookkeeping is only noted for the future (DOK-045; DOK-047 stays noted
only), and the e-invoices get checks of their own core (DOK-042). The gaps against other programs are kept in the
requirements catalogue (5.19), not in a document of their own.

- **Payments are bookings.** `core.payment_base.PaymentBase`: never changed, never deleted; voided with a reason, who and when.
  Balances are computed (`documents.payments`, `incoming.payments`), never stored: invoice (a final invoice after its
  deductions) plus partial credit notes and cancellation, less the payments that count. A refund is a negative payment. An invoice
  taken over from the old system and known as paid counts as paid without a payment, is no open item and takes no payment.
  Incoming payments are in the currency of the invoice; the EÜR converts with the rate of the invoice.
- **The EÜR is on the cash basis** (`documents.euer`). A payment is split over the tax rates (outgoing: the shares of
  the invoice, credit notes and cancellation added) or over the tax accounts (incoming) in proportion to their gross amounts,
  to the cent (`core.tax_split`, the largest part takes the rounding). Fixed assets and GWG are taken out of the expense
  shares **only if items were booked in from their position** (`MaterialItem.source_position`); the ancillary costs spread
  over those items go with them; the input tax stays with the payment. Goods above the GWG limit that are not booked in count as
  expense and the page says so. Depreciation comes from `material.book_values` (month principle, GWG in the year of
  acquisition); a sale leaves the book value as an expense. Sales from stock without an invoice count on the sale day. A small
  business counts gross. Payments to the tax office are not known; turnover tax is shown apart.
- **Own core checks, not the KoSIT rules** (`documents.einvoice_rules`): a neutral model of UBL and CII, rules of EN 16931 and
  the XRechnung that can be checked without Schematron. A finding, not a block, unless the setting says so. The result is kept with
  the document (`DocumentCheck`) or the incoming invoice (`einvoice_check`). Everything Rentalars writes passes its own
  check in the tests (this proves the writer agrees with the rules as read here, not that a recipient's validator agrees).
- **ZUGFeRD** (`documents.zugferd`, `documents.cii`): WeasyPrint `pdf/a-3b` plus the CII as an attachment with the relationship
  "Alternative" and the Factur-X metadata in the XMP. The stored checksum is the one of the finished PDF. **Not validated with veraPDF
  or Mustang** – only read back with pypdf in the tests.
- **Archive** (`documents.archive`): a record per voucher (files with SHA-256), the retention period ends 31 December of the
  voucher year plus 8 (invoices) or 6 (letters) years; the nightly run registers and checks `ceil(n / days)` records, the longest
  unchecked first. A new incoming invoice is archived after one day (a mistaken upload can be deleted); after that its
  deletion is refused until the period ends. The record outlives the voucher ("deleted after the period"). Findings turn the
  self-check red.
- **Audit export** (`documents.audit_export`): CSV tables, `index.xml` in the manner of the Beschreibungsstandard,
  vouchers, `SHA256SUMS`. Built in the request (a spooled temporary file); a very large archive wants a background task. The
  `index.xml` is **not tested with an audit program**.
- **Procedure documentation** (`documents.procedure`): a draft filled from the settings, page, PDF and Markdown; the company
  completes it. Rentalars claims no GoBD certification.
- **DOK-044:** an XRechnung takes its XML along when the customer has a buyer reference; a ZUGFeRD PDF goes alone.
- **API:** `?as=pdf|md` instead of `?format=`: `format` is the content-negotiation parameter of DRF.

### The independent review

A reviewer who had not written the code read payments, EÜR, archive, export and the e-invoice code. Fixed, each with a test
in `tests/unit/test_112_review.py`:

- `verify` also compares the PDF with `Document.sha256`, so a PDF altered *before* its first registration is reported.
- The EÜR takes only the booked cost of a position as the asset if only some of its pieces are booked in; the rest stays an
  expense.
- A payment is split by the invoice with the
  credit notes and the cancellation issued until its day; a refund follows the rates of the credit notes (`euer._shares_of`).
- The audit export uses the day of arrival for incoming invoices without an invoice date, like the archive. Equal
  names made safe get a number; text cells that start like a formula get a leading apostrophe.
- The retention of an incoming invoice counts from the later of its date and its arrival (a typo must not shorten it); an
  invoice older than the grace time that the nightly job has not registered yet is registered when someone tries to delete it.
- `state_for` reads a negative amount (credit note of a supplier) mirrored; control characters do not
  break the XML of both syntaxes; two registrations at once do not raise; the sums of the open items count the euro only;
  a year outside 2000–2100 is a 400 in the API; 403 comes before 404 when voiding.

Left as it is, on purpose: a payment record is immutable by convention (the services), not by a guard in `save()`; payments to
the tax office are not recognised; open items list what is *to pay* (a credit note of a supplier shows in the list of
incoming invoices, not there); BR-DE-21 is not checked.

### Not done or not verified

- ZUGFeRD PDFs with veraPDF / Mustang; `index.xml` with an audit program; the e-invoice rules with the KoSIT validator.
- Double-entry bookkeeping (DOK-047), a bank statement import and matching, dunning from the open items, a deadline of
  the archive check as a background task, a file-level lock of the storage.
- The EÜR was checked against hand-made cases, not against the books of a real company or with a tax adviser.

## Part 31: Editing templates, bank statements, credit balances

- **Template content is edited by a service, not by the forms** (`projects.template_content`, PRJ-135). The content of a template is
  the JSON that `project_templates.capture` writes; the service changes it one entry at a time (`add_entry`, `update_entry`,
  `delete_entry`, `move_entry`, `set_notes`, `replace_content`) and validates the *whole* result after every change, so that a
  template that was stored can always be applied. The pages (`template_content_views`, `template_content_forms`) and the API
  (`template_content_api`, a mixin of `ProjectTemplateViewSet`) are thin: they translate form or JSON to an entry and call the service.
  Both therefore enforce the same rules.
- **Entries are addressed by a key, open items by place and text.** Groups and lines had a key; crew places, vehicle
  bookings and phases get theirs when a template is opened for editing (`ensure_keys`), so a stale page never changes another entry.
  Open items are plain strings: address = place, and `expect` (the text the caller saw) guards against a list that changed meanwhile.
  A stale address is a warning with a redirect on the pages and a 404 in the API.
- **References are kept, not repaired afterwards.** Deleting a group hands its content to its parent (or deletes it with
  `with_content`); deleting a thing an alternative replaced turns the alternative into an optional one; deleting or moving a phase
  renumbers the phase index of crew places and bookings. A period is `start`/`end` in seconds from the start, or from the end
  (`anchor: "end"`, PRJ-095); the forms speak hours.
- **Prices need the price right.** A group's discount and flat price and the price of a free line are written only for callers
  who may see prices; for others they stay as they are (also in `PUT` of the whole content).
- **A payment is a booking, also for the code** (`core.payment_base`, DOK-051). `PaymentQuerySet` refuses `update`, `bulk_update` and
  `delete`; `save()` only creates a payment or voids one once (`VOID_FIELDS`); `delete()` raises `PaymentLockedError`. This replaces
  the earlier convention ("immutable by the services"). Raw SQL and `QuerySet.raw` are not guarded.
- **The tax office is a property of the supplier** (`Supplier.tax_office`, DOK-052): `""`, `"vat"` or `"income"`. In the EÜR a payment to
  a "vat" tax office is no expense but reduces the turnover tax balance (`vat_still_owed`); "income" is shown apart; both are
  excluded from the expenses. A refund is a negative payment. Trade tax stays an ordinary expense. No data migration guesses which
  supplier is a tax office.
- **Credit balances** (`payments.credit_items`, `incoming.payments.credit_items`, DOK-053): the same balance as the open items, with a
  negative `remaining`. Outgoing: invoices with `payable < paid` (overpaid, or cancelled/credited after payment); invoices from the
  old system are not listed. Incoming: credit notes of suppliers and invoices paid too much. The refund is a negative payment.
  The page and the API (`side=credits`) show only the sides the caller may see.
- **BR-DE-21** (specification identifier) is checked (`einvoice_rules.XRECHNUNG_SPECIFICATION`).
- **An external check found a real fault.** `scripts/external_validation.py` (development only; `saxonche`, `lxml`, `factur-x`,
  `odoo-addon-base_ubl` from PyPI) validates our UBL and CII against the official XSDs and the EN 16931 Schematron. It found that the
  CII wrote `FormattedIssueDateTime` in the wrong namespace (`qdt`); fixed in `cii._date`. The Peppol warning R008 is accepted. **What
  could not be done:** Maven Central and GitHub are not reachable from the build environment, so the KoSIT validator, its
  XRechnung configuration (BR-DE Schematron), veraPDF and Mustang were not run. A pass here is not a pass there.
- **The audit export can run as a task** (`audit_export.start`, `run_job`, kind `audit_export`, DOK-054): progress per table and
  voucher, result visible only to the creator, `POST /accounting/audit-export` answers 202 with the task. The download in the
  request stays for small archives.
- **Bank statements** (`documents.bank`, DOK-050). Two models: `BankImport` (the file: name, SHA-256, format, IBAN, period, counts)
  and `BankTransaction` (one booking). The file itself is not stored. Reading is deterministic and never guesses:
  CAMT.053 (any `camt.053.001.xx`, local names, DTD and entities refused, only `BOOK` entries, `RvslInd` turns the sign, a batch
  entry is split only if every part names its amount) and CSV (delimiter by count, UTF-8 else Windows-1252, header row found by name,
  German or English amounts through `parse_amount`). **Duplicates:** the same file by checksum; the same booking in an overlapping
  statement by a fingerprint of IBAN, day, amount, currency, counterparty IBAN, end-to-end ID and purpose plus a counter for equal
  rows within one file, so two real coffees on one day stay two.
- **Matching suggests, a person books.** `suggestions` scores open items by the invoice number in the purpose (60), the amount equal to the
  open rest (30) and a word of the name (15); at least 30 is shown, five at most. The direction decides the candidates: money in →
  outgoing invoices and supplier credit balances, money out → incoming invoices and customer credit balances; the payment amount
  follows the sign convention (a refund is negative). `book` calls the ordinary `record` services, so the rules of payments apply
  (no future day, an invoice without totals is refused) and the audit trail shows a normal payment. A transaction is matched as a
  whole; a part payment is entered at the invoice. Voiding the payment opens the transaction again (`state` is derived: booked only
  while the payment counts). Foreign currency is not matched.
- **Rights of the bank page:** to see, both price rights and reading access to all projects and to the material (`bank.may_use`); to read
  in, book and set aside, writing access to both (`bank.may_change`). One page shows both sides of the books, so one side is not enough.

### The independent review

A separate agent that had not seen the work read it and ran its own scripts against it. What it found and what was done:

- **Prices leaked on reading.** `GET /project-templates/{id}/content`, `PUT` (the answer) and the `content` of the template itself
  showed prices to callers without the price right. Now `template_content.without_prices` takes them out of every answer to such a
  caller (AUT-019); writing already kept them.
- **Keys were reused.** After the last entry of a section was deleted, the next one got the same key, so a stale page changed a new
  entry. Each section now has a counter (`next_keys`, kept in the content, also by a replacement); keys are never given twice. A
  change of single fields (`PATCH`) merges with the entry *under the lock* (`update_entry(merge=True)`), so two callers who change
  different fields do not undo each other. `planned_hours` ends at 99,999.99 – the size of the field of the project.
- **The audit export was not safe for a spreadsheet.** A negative number got an apostrophe, the exchange rate was cut to two places,
  and the CSV of the EÜR and the open items did not neutralise formulas at all. One helper (`core.tables.formula_safe`) now does it
  for all three: text that starts like a formula gets an apostrophe, plain numbers (also as text) do not.
- **The payment guard.** A "new" object with the number of a stored payment cannot overwrite it, nor can `bulk_create(update_conflicts=True)`;
  a payment cannot be voided without a reason. All three are refused (`PaymentLockedError`).
- **Bank import.** `RvslInd` (a reversal) turns the sign as the standard says; camt version 08 names the party in `Pty/Nm`; a CSV
  line that cannot be read **refuses the file** (a statement with a missing line is worse
  than none); a file with a delimiter that is hard to tell is read by the header; the XML limit of the invoice reader holds for bank
  files; amounts above 10^10 and files without any row are refused with a message instead of an error; the same file read by two
  people at once makes one import; the same booking in the statements of two accounts is two bookings.
- **Matching.** A booking is only offered for an invoice if the money goes the right way (`_fits_direction`), and `book` checks it
  again – a tampered request cannot enter a payment the wrong way round. An invoice number of fewer than three characters, or only
  digits below five, is not read from the purpose (dates and amounts look like that). Invoices in a foreign currency are not
  matched: the amount of the bank is in euro, the invoice is not.
- **Tax office.** The mark is part of how the EÜR counts, so it is shown and set only to callers who may see the EÜR – also in the
  API (`SupplierSerializer`): who maintains suppliers with write access to the material must not be able to change the profit of a
  year. A small business owes no turnover tax: its payments to the tax office are shown, nothing is "still owed".
- **BR-DE-21** also accepts the identifier of an extension on its own (`…#conformant#urn:xeinkauf.de:kosit:extension:xrechnung_x.y`).
- The tax-office test requests the page and the API; the audit job compares the files of the two ZIPs.

### Not done or not verified

- The KoSIT validator and the BR-DE Schematron, veraPDF, Mustang (see above); `index.xml` with an audit program.
- Real bank files: the parsers were tested with files rebuilt from the standard and from the column names banks use, not with exports
  of a bank. MT940, bank APIs (FinTS) and automatic fetching are not built.
- Double-entry bookkeeping (DOK-047) and dunning from the open items stay noted in the catalogue.
- The template editor was run in tests and with the test client, not in a browser by a person.
- Known limits: the payment guard does not stop raw SQL or a deletion by the database (a cascade); a CAMT file and a CSV file of the same
  period are two sources – the same booking in both is entered twice, because their fields differ in detail; voiding a payment that
  came from the bank and booking again does not keep the link to the voided one; the weights of the matching (60/30/15, at least 30)
  are assumptions, not measured on real data.

## Part 32: Changes of products in projects that are not confirmed yet

The requirement: when the price of a product is changed while it is planned in projects, the change is neither taken over in those projects
nor reported. In projects that are not yet confirmed, changes to the products (texts and the like included) must be takeable over.

- **Why it was not noticed.** The planning of an inquiry or option pointed out old *prices* (PRJ-072) – but only on the tab
  "Planung", and opening a project lands on "Überblick". Nothing was said about names, units, tax rates or billing modes, and
  nobody was told. So the fix is not a new button but visibility (every project page, the bell, the product page) plus completeness.
- **A line remembers what it took over.** `MaterialLine.product_seen` (JSON: name, unit id, tax rate id, billing mode) is the sibling of
  `list_price`. It is written where a line is created from a product (`services.defaults_from_product` → `seen_state_of`), copied with
  the line (`duplicate`, group copy, `lines.COPIED_FIELDS`) and kept in step when a sale becomes a rental or back. It is excluded from
  the history of the line (`audit_exclude`): it is bookkeeping, not a change by a person.
- **Detection is stateless.** `projects.product_changes.find_changes` compares line, memory and product at the time of asking; nothing is
  recorded when a product is saved. A part is outdated when the product differs from the memory; it is "set by hand" when the line
  differs from the memory. A missing memory means: outdated if line ≠ product, and then always "by hand".
  The data migration fills the memory for every line that still equals its product, line by line in chunks (`iterator`, `bulk_update`).
  The alternative – assume the product changed wherever line ≠ product, and switch automatically – would have overwritten titles
  that people wrote on purpose.
- **What follows the product:** name, unit, tax rate, billing mode (not for sold lines and percentage surcharges), and the price (PRJ-072,
  the existing `OldPrice`; for crew lines only the price of the service product, with the hour tiers). Not: quantity, period, note, discount,
  description (read live from the product), rental scale version (changes only together with the billing mode, as when a line is
  switched from sale to rental). A change of the billing mode asks `defaults_from_product` again for scale and estimate flag; if the
  product cannot be rented any more the part is skipped, not an error.
- **Rights.** Prices are looked at only with the price right (`with_prices`), so neither the list, the count in the banner, the product page
  nor the API reveal a price change to someone without it; taking over without the right leaves the price pending (it still shows for
  who has the right). All other parts need only the right to edit the project. The notification names no prices at all.
- **Where it is shown.** A hint on every project page (`product_change_hint` in `_head.html`, not on the planning itself, which has the list
  with old → new and the actions), the list in the planning (`_planning_notes.html`, `#product-changes`), a section on the product page
  and a message after saving the product. The API has `old-prices` for clients.
- **Notification.** `product_notice` connects `post_save` of `Product` (not on creation, not for `raw`); after the commit it asks
  `changes_of_product` for the lines of that product in inquiries and options that differ and notifies manager and editors once per
  project, but not again while an unread notification of that kind exists for the project (an import of a thousand products must not
  send a thousand). A failure is logged and never reaches the person who saved. Not by e-mail unless the user switches that on.
- **From the product.** `changes_of_product` is the same detection seen from the product. "Take over in all projects" runs
  `take_over_changes(..., automatic=True, only_product=product)` in every project the user may edit; lines with a value set by hand stay.
  Browser and API both need the right to write products (and to edit the project).
- **Not built:** a marker per project in the project list; a setting to take over automatically; taking over the description (it is read
  from the product anyway).

### The independent review

A separate agent read the code and ran probes against it. Found and done:

- **A stale tab could overwrite a confirmed project.** The page was opened as an inquiry, the project was confirmed meanwhile, "take over"
  still worked. `changes_update` now refuses unless the project is not confirmed (`shows_price_hint`). The API stays explicit.
- **The product page and its API named projects whose planning the user may not read** (a crew member with a deployment-view membership and
  the product right). Both use `readable_projects` now, not `visible_projects` (which includes the overview-only case).
- **The percentage of a surcharge is its price** and was not followed. `surcharge_percent` is now part of the memory (as text) and of the
  detection, for those who may see prices. Hour tiers of crew lines are still not compared (only the base price).
- **Notifications were too many.** Saving a product for any reason notified again; an e-mail-only user has every notification stored as
  read, so "unread" never held. Now: a `pre_save` snapshot (`FOLLOWED_FIELDS`) decides whether a followed field changes at all, and nobody
  is told twice about a project within an hour (read or not) or while one is unread.
- **A notification was a side channel for prices.** Users without the price right are counted only what they can see in the planning;
  a price-only change is not told to them.
- **A billing-mode part that cannot be applied** (the product lost its rental price) kept the hint for ever without any button. The
  product's value is noted as seen now, the line keeps what it has.
- Smaller: the same new name typed by hand is no difference; the data migration reads lean rows in key ranges (no joined model objects);
  the product page names the line of each change.
- Left as it is: a project without manager and editors gets no notification (only the hint on its pages); the person who saved is told
  too; saving a line overwrites concurrent edits of the same line (as the old price take-over did); taking over a billing mode also
  renews scale version and estimate flag as the switch from sale to rental does.

## Part 33: Sender of the answer, bookkeeping that can be hidden, "Einzelheiten offen"

The requirements (six points): an answer to a deployment request must not be possible from the
forwarded mail of somebody else; with "Rentalars als Buchhaltungsprogramm verwenden" off the bookkeeping disappears from the menu; the
switch gets its own box; the repository is checked for personal data and the licence; the status is renamed "Bestätigt – Klärung offen" to
"Bestätigt – Einzelheiten offen"; the changed-product hint is shown in that status too.

### The sender of an answer (PER-046)

- **Why the sender counts.** The token in the subject (120 bits) alone does not prove who answers. Whoever gets the request mail forwarded could answer in the name of
  the original recipient – the answer would be recorded as the person's own, and the confirmation would go to the person, who only learns of it
  afterwards.
- **What counts.** `CrewRequestMail.sent_to` stores the (lower-case) address the request was sent to. `sender_reason` compares
  `parsed.sender_address` with it, before `refusal_reason`. A mismatch (or an empty sender) is the reason `sender`; nothing is recorded,
  the mail log gets `crew_answer` with detail `accepted:sender` / `declined:sender`, the mail is filed away like every answer, and
  `reply_message` tells the person at their stored address which address the answer came from.
- **No second list of allowed addresses.** The request is sent
  only to `person.email`, so only that address (as of the sending) is the proof of "this is who got the mail". An address change
  afterwards does not make the new address valid for an old request – the old mail sits in the old mailbox.
- **Forged `From`.** The sender header is free text. Rentalars cannot evaluate SPF or DKIM itself (it sees neither the connecting server
  nor the signed message as the receiving server did). What it can read is the verdict that the receiving mail server wrote:
  `ParsedMail.authentication` joins the `Authentication-Results` headers, and `dmarc=fail` anywhere gives the reason `forged`. Only a
  failure is acted on: a header written by the sender himself could say "pass", so a positive verdict is never trusted as proof, and
  its absence changes nothing. This closes the case of a passing forwarder who types the original address into `From` on a domain
  with DMARC; on a domain without DMARC (or without the header) it does not. Written down for operations (operation manual) and as an
  assumption in the catalogue.
- **Other codes.** The tag `[RA-E-…]` is the only code that comes back by mail. Invitations, password links and the calendar feed are
  links; nothing is answered by mail there.
- **Not built:** a list of additional allowed addresses per person; a setting to switch the check off. An answer from another address
  is answered in the browser.

### Bookkeeping that can be hidden (DOK-055)

- **The switch existed** (`SystemSettings.invoices_enabled`, DOK-014) and already removed invoices and cancellations, the handing
  over to Lexware Office and the DATEV export. It did not touch the tabs that arrived later (incoming documents, asset
  register and sales from stock, open invoices and EÜR, bank, import of old projects).
- **What is bookkeeping** is a list, not a guess: `documents/bookkeeping.py` (`PAGES`, `API`, patterns with `*`). A test walks all URL
  patterns and fails for every page below `accounting/` that is neither on the list nor on the list of what stays (outgoing documents,
  free documents, monthly statement) – a new tab cannot be added without deciding. Another test fails for names on the list that
  match no address.
- **What stays** and why: outgoing documents (offers, order confirmations, delivery notes, invoices made earlier – readable, sendable),
  the monthly statement (it is the way to copy the values into the other program), "Rechnung gestellt", and the settings of
  Lexware Office and DATEV (they hide their own parts). "Import old projects" is hidden: it creates issued invoices.
- **Hiding is not enough.** The menu (`Section.bookkeeping`, `entries_for(bookkeeping=…)` from the context processor, so that a user
  with rights only for hidden tabs loses the entry), the tabs (`outgoing.tabs`) and the links elsewhere (`bookkeeping_on` in the
  templates) follow the setting; in addition `BookkeepingMiddleware.process_view` turns away the addresses: pages to the start page with
  a message, the API with 400 `accounting_disabled` (as the invoice calls already answered 400 while the switch is off), unless the caller
  is not logged in – then the login gate or 401 answers first, so the setting is not revealed to strangers. The middleware sits behind
  the login gates and before the access log.
- **Its own box.** `AccountingSwitchForm` (one field) with its own form name `accounting` on the page; the field left
  `SystemSettingsForm`, so saving the other settings can never switch bookkeeping off (a missing checkbox in a form means "false"). The
  API serializer still has `invoices_enabled` in `system`.
- **Not built:** hiding the field `invoices_enabled`-dependent API fields of single resources (e.g. `incoming_invoice` references in item
  data stay readable); a finer split into "invoices" and "bookkeeping".

### The status and the changed-product hint

- The label `ProjectStatus.CONFIRMED_OPEN` is "Bestätigt – Einzelheiten offen" in German (English "Confirmed – details open").
- `price_updates.CHANGE_NOTICE_STATUSES` holds inquiry, option and confirmed_open. Everything that
  asks "not confirmed" (the hint on every page, the planning, the take-over, the notification, the product page, both API
  views) uses the constant. A project that is `confirmed` (details settled) or later keeps its values. The texts
  say "not fully confirmed yet".

### Independent review

A separate reviewer read the diff and probed it. No blockers; what it found is covered by tests:

- Because a mail with two `From` headers could pass the sender check on the first one while a receiving server judged the last one,
  `ParsedMail.from_count` counts the headers; anything but exactly one is refused as `sender`.
- The warning mail is throttled (the token stays valid, so anyone who ever saw it could send a flood) and does not echo the
  parsed "address", which can be a display string posing as one. One warning per request and reason per hour
  (`WARNING_INTERVAL`, found in the mail log by token and detail), and only a plain address is named, else "–".
- `documents:check` ("check the e-invoice again" on an outgoing invoice) is not listed as bookkeeping;
  the unit test lists it under `STAYS`.
- The API middleware authenticates as the view would (`_api_caller_known`) and answers 400 only for a logged-in user or a valid token.
- IDN addresses are compared in their ASCII form (`_comparable`). HTMX requests to a refused page get `HX-Redirect`.
  The `dmarc=fail` search runs over the whole `Authentication-Results` text. The reason is worded "the check failed", not
  "could not be verified".
- Left as it is, on purpose: without a verdict of the receiving server (or on a domain without DMARC) the check is a speed
  bump, not proof; `dmarc=fail (p=none)` also refuses. A strict mode (second secret in the mail body, or "dmarc=pass
  required") is a candidate for later (Katalog 12.2).

## Part 34: Review before publication

The task: correct the findings of a review before publication (licence, upload
preparation, nine serious logic errors, medium and small errors) and return the result. Each finding was checked in the
code first, then fixed with a test that fails without the fix. A few findings were not what they said, and some are not for the code
to decide.

### What was not a defect, or not for the code to decide

- **"ci.yml is missing from the package."** The delivered package (SHA-256 `871374de…`) contains `.github/workflows/ci.yml`. The
  copy under review had another checksum (`cc23ae20…`) and so was not the package that was delivered; the file was probably lost when it
  was unpacked (a hidden folder). The test that reads the file now skips without it, and `scripts/build_package.sh` refuses to
  build a package without it.
- **The licensor.** The review is right that "die Autorinnen und Autoren von Rentalars" names nobody. The code cannot know who
  publishes: `COPYRIGHT_HOLDER` (and the line in the README) names the holder.
- **AI authorship.** Whether and how copyright and the copyleft apply to code written by agents is not a matter of the code. Left
  to a lawyer.
- **Domains.** Example addresses end in `.example`. `example.de` (used as a placeholder; it is not reserved for examples) and `fld-vt.de`
  (the author credit, intended) stay.

### Licence

- **The additional term applies when conveying only.** The words "or by letting others use it over a network as their own service"
  (German: "als Dienst über das Netz") are gone from `ADDITIONAL-TERMS.md`. The GPL ties duties to conveying; a duty for whoever only
  runs the program would be a "further restriction" that every recipient may strike out (section 7). A duty that covers running
  would need the AGPL; that was not chosen. The catalogue (UIX-031) said "whoever conveys may change it in his copy" and now
  says "may add, may not remove or cover", as the term does.
- **A page "About Rentalars" (UIX-062).** The attribution on a fixed place of the interface is a grey area; a page with the notices
  that is reachable without login (`/about/`) lies closer to what section 7 b asks for ("Appropriate Legal Notices"). It shows
  the GPL notice, the attribution with the note on the term, the holder and the full texts (`/about/<name>.txt`, three fixed
  names, no path from the request).

### The nine logic errors

1. **Number ranges.** `NumberRange.allocate` resets a yearly range to its start on the first allocation of a year only if a recorded year differs;
   `save()` records the year when the counter is set by hand, so a counter set by hand mid-year is not overwritten and
   `RE-2026-0001` is not issued twice.
2. **Free documents.** The date may not lie in the future or in another year than the current one (leave empty: today). A draft that
   waited over New Year is refused with its old date.
3. **EÜR.** (a) The surplus is the profit plus the VAT still owed (the cash basis counts gross), shown beside the result without VAT;
   for a small business both are the same. (b) The ten-day rule is **reported, not applied**: moving payments across the turn of the
   year changes the result of two years, and Rentalars cannot know whether a payment was "recurring" (§ 11 EStG). (c) A partial sale
   of an asset kept as bulk material: the body cost of an earlier year includes the cost of the pieces sold later, and the sold
   pieces get a line of their own until the day of the sale. (d) Lost or retired assets stop depreciating on the day taken from the change log (an assumption: the log has the day of
   the status change; where it is gone, the figures keep depreciating and the EÜR says so) and their book value is a disposal.
   (e) The GWG limit is checked where an asset is set (`low_value_problem`), also when entering a purchase; for bulk material the
   cost per piece counts.
4. **Reverse charge.** A customer with a VAT ID of another EU country and a zero rate is a
   reverse charge case: note on the invoice, category AE with the reason in XRechnung and CII, the seller's VAT ID is demanded
   (BR-AE-02), DATEV and the PDF use the same rule (`DocumentContent.reverse_charge`). **Not covered:** exports to third
   countries, other exemptions, triangular transactions, goods sold to an EU business (that is an intra-Community supply, not a
   reverse charge); the tax adviser decides. Not for a small business (`DocumentContent.small_business`, stored with the
   document; an older document counts as small business, so it is shown as issued) and not for `XI` (Northern
   Ireland is in the EU for goods only).
5. **Sender check.** `_comparable` uses NFC and lower case, with non-ASCII labels in punycode: an IDN and its `xn--` form stay equal, look-alikes do not.
   NFKC would turn full-width letters into ASCII, so `ｇｍａｉｌ.com` would equal `gmail.com`
   while the mail server saw another domain.
6. **Rental days.** Two aware datetimes of one zone subtract as wall-clock times, of different zones as elapsed time: the form
   (local) gave 1, the stored value (UTC) 2 across the end of summer time. Both go to local wall-clock time first.
7. **Double booking.** (a) An overdue project's material is occupied
   until it is booked back (`FAR_FUTURE`, as sales are). The shortage overview names these projects as a consequence – real ones.
   (b) On completing the return of a row whose missing parts were clarified, items not scanned
   back, as many as the row is short, are blocked, not released as "available". For bulk material nothing tells which pieces are meant; the person gets a
   hint to reduce the quantity. **Not solved:** pieces clarified as lost stay in the stock count until somebody reduces it.
8. **API and confirmed projects.** The domain functions refuse confirmed projects (`shows_price_hint`), so web and API agree, and
   `/old-prices` (same flaw) too.
9. **Two-factor code.** A right password recorded a success, which clears the count of failures, so the code could be guessed
   endlessly. A success is recorded only after the code is right; wrong codes count for the account name (not only for the typed
   name, which could be varied), in the browser too (the session counter was dodged by a new session).

### Medium and small

- **"No scale" is the number of days** (manual, section 8; the vehicles already did). The test said "factor one" on purpose –
  that was the decision of 0.5.x and contradicts the manual; the manual wins. **This changes prices**; noted in the update guide.
- **Undoing an issue** restores the status from the change log (an option stays an option); "confirmed" where the log has none.
- **XRechnung:** `"20".rstrip("0")` is `"2"`: `plain_decimal` is used for the percent in XRechnung and in the texts of the documents.
  Tax shares with the same category and percentage are merged for the e-invoice (BR-CO-17); the invoice still shows both.
- **Bookkeeping off:** the nightly archive is skipped; a queued Lexware transfer fails with `switched_off` and can be started again.
- **Server:** `www-data` is in the group of the service account and could read `rentalars.conf` (database password, secret
  key). A first attempt took it out of that group (own group `rentalars-web`); the independent review showed that this breaks
  the socket between NGINX and gunicorn (502 after every update, and rollbacks). Taken back. Now the file belongs to the
  service account with mode `400` (`protect_configuration` in `lib.sh`, called by install, update, move-database); `www-data`
  stays in the group. Left open: a backup made in the browser holds the configuration and is group-readable (advice: encrypt).
  `backup.sh`/`encryption.sh` write their status file without following a link laid in the data folder. **Not tested on a real
  server**, only the script tests and shellcheck; the update guide says what to look at afterwards.
- **XLSX:** rows and cells are counted while reading (100,000 rows, 3 million cells), the unpacked size is limited (200 MB).
- **`deploy/route.sh`:** the age of the map counts calendar days. The diagnosis in the report ("1 Tage alt" at night is a
  flaky test) was wrong: the 25th of October 2026 had 25 hours.
- **Nested LDAP groups:** only through the Active Directory chain rule in the group search. The filter in the manual had no outer
  brackets and was refused by the form; corrected and tested against the filter parser. Not tried on a real Active Directory;
  OpenLDAP has no such rule.

### Independent review

A second reader who had not seen the work went through the changes. What it found and what was done:

- **Serious – the group scheme of the server.** Taking `www-data` out of the group `rentalars` would have cut NGINX off from the
  gunicorn socket (502 after every update, and for every rollback). Taken back; the configuration file is protected by its owner
  and mode instead (see "Medium and small", Server). Verified by the script tests (421 + 84 cases) and shellcheck, **not on a real
  server**.
- **Reverse charge** applied to a small business (§ 19 UStG, no tax at all) and to `XI`. Fixed (see above); goods are not
  distinguished from services – a sale of goods to an EU business needs the tax adviser's decision.
- **Cell limit of the table reader** counted the padded width of a row (Excel writes up to column XFD when a column was formatted),
  so an ordinary file could be refused as "too big". Now the cells after the last filled one are neither counted nor kept. The
  limits (100,000 rows, 3 million cells) hold for imports in the background and for the commands on the server as well.
- **API:** "resolve-missing" returned its hint for bulk material only in the browser; the response carries `hints` now.
- **Two-factor login by e-mail address:** the success was noted under the user name only, the failed passwords under the name as
  typed; it is noted under both now.
- **Rental days** tolerate a time without a zone (counted as wall-clock time).
- Doubts that stay doubts: the ten-day rule of the EÜR is reported, not applied (the person decides); the GWG limit is checked where
  an asset is set, not when the purchase price is changed later.


## Part 35: Security gaps from a review

The task: close the eleven findings S1 to S11 of a security review, each
with its remedy and its proof. Each finding was checked against the code first. Eight were as described, one was
done already, one rests on a wrong assumption, and one is closed in a narrower way than the report proposed.

### Finding by finding

- **S1 – libraries with known vulnerabilities.** True. Pillow 12.3.0 → 13.0.0, pypdf 6.20.0 → 6.21.2, Brotli 1.2.0 → 1.2.1; `pip-audit`
  finds nothing in `requirements.txt` afterwards. `Image.open` gets the list of formats the place expects (new
  `rentalars/core/pictures.py`). Pillow only knows a format in that list once its plugin is loaded, hence `Image.init()` in the
  helper (without it `formats=["MPO"]` raised `KeyError`). Code that is not ours calls `Image.open` without a list (the image fields of
  Django and the REST framework, WeasyPrint); so the program also removes every reader but JPEG, PNG, GIF and WebP from Pillow when it
  starts (`restrict_decoders`; `Image.OPEN` and `Image.ID`). The chat keeps its friendly message for BMP/TIFF/ICO by looking at the
  first bytes. `pip-audit` runs in `scripts/check.sh` (skip with `RENTALARS_SKIP_AUDIT=1`; it needs network). An explicit step in
  `ci.yml` was not added: the CI calls `check.sh`. Dependabot proposes updates weekly (pip) and monthly (GitHub Actions).
  Pillow 13 is a major version; the test suite is the only proof that it works.
- **S2 – the sender check of answers by mail can be got around.** True in three ways: `parseaddr` makes `anna@mail.example` out of
  `From: "anna@mail.example" <x@evil.example>`; an address without a local part or domain passed the normalisation; and without
  DMARC nothing at all stands against a forged `From`. The structured header is used now (`sender_checked`: exactly one address
  with a domain, no defect other than raw UTF-8 and obsolete-but-unambiguous syntax such as dots in a display name). For the third there is no way to prove a sender from inside the mail: SPF and DKIM need the path of
  the mail, which Rentalars does not see. So the operator may name his own mail server (`authserv-id` of RFC 8601); only that
  server's `Authentication-Results` count, with `dmarc=pass`, or `dkim=pass` for the sender's domain (or a parent of it) – a header
  that the sender writes himself never does. Only the topmost such header counts (a server prepends its own; the public name could
  also be written by the sender), comments and quoted strings cannot start a result, a DMARC pass must name the sender's domain
  and a DKIM signer must be more than a top-level domain. Not confirmed → the person gets the mail with the link. **Without the
  setting a reply mail is no proof**; the manuals and the self-check say so, and the setting confirms a domain, not a person.
  Exchange Online does not name itself first in the header and cannot be entered. Rejected: an own SPF/DKIM evaluation (needs the transport path), and a strict mode by default (it would lock out
  every installation whose provider writes no header); the setting is opt-in, and the self-check notes while it is empty.
- **S3 – guessable two-factor codes through the API.** Already fixed (AUT-005: wrong codes are counted and lock the name,
  browser and API). Nothing changed; the tests (`test_overview_api`, `test_security_pages`) show that wrong codes lock the name in the browser and in the API.
- **S4 – a placeholder `secret_key` is accepted.** True for the production environment. The placeholder of the example file
  (`replace-with…`), the development key and the usual defaults stop the start. Short keys are still only warned about: refusing a
  key an operator already uses would lock him out of the stored passwords.
- **S5 – `www-data` can read secrets.** Partly true. The report proposes `--umask 007` for gunicorn and a group `rentalars` without
  `www-data`. Checked: `--umask` of gunicorn sets the mode of the unix socket and of the worker's temporary file, **not** the umask of
  the process, so it protects nothing here; and `www-data` must stay in the group because NGINX connects to the socket as that
  group (the socket has to stay 0660). The configuration file (database password, secret key) is owner-only (400).
  What remains: files in the data folder that the group can read (uploads, backups made in the browser). Closing that needs ACLs or a
  group of its own for NGINX and a test on a real server; not done, listed in 12.2 number 46.
- **S6 – backup and restore as root follow links in a folder of the service account.** True when the working folder is in the data folder
  (owned by the service account): the decrypted archive and key are written there and `media` is moved with `mv`/`chown -R`.
  The working folder is in the folder of the backups (owned by root, checked), `media.before-restore` and the new `media`
  are moved with `mv -T`, and the owner is set in the working folder before the move. `backup.sh` writes its status file with a
  helper that does not follow a link (`place_file`: `rm`, then create with O_EXCL; no later `chmod` by name). Proved by script tests: the behaviour of the helper with a link laid at the name of the status file, and
  the text of `restore.sh` (working folder, `mv -T`); the restore itself was **not run**, neither with a link nor on a real server.
- **S7 – an XLSX import reads all rows before the limit.** True: a sheet with a million formatted empty rows was read to the end,
  and a row costs time in proportion to its width (a sheet whose dimension runs to column XFD yields rows of 16,384 cells; about
  0.8 ms each on the busy test machine). No more than 300,000 rows of any kind are looked at (more: refused, with the advice to
  delete the empty rows), and an XLSX sheet is read only up to column 199 (`MAX_COLUMNS`; a heading beyond is refused). That cuts
  the cost of an empty row to a thirteenth in a measurement and makes the refusal fast.
- **S8 – one IP address for all visitors behind an upstream proxy.** True. The application reads the last `X-Forwarded-For`, which
  NGINX sets to `$remote_addr`; behind a load balancer that is the balancer. `[rentalars] trusted_proxies` is opt-in: NGINX
  (`set_real_ip_from`, `real_ip_header X-Forwarded-For`, `real_ip_recursive on`) takes the address of the visitor only from those
  addresses. It is a snippet file written by the update and by `nginx-site`, and `ensure_realip_include` adds the `include` line to
  existing sites. The uninstall removes both.
  The entries are checked as
  addresses (IPv4/IPv6, network length 1 or more – a network of all addresses would let anybody name his address – and no
  comment, no file name from a `*`). `nginx-site` also writes the file when only the setting changed, and puts it back when
  `nginx -t` refuses the new configuration. Script-tested and shellchecked, **not run behind a real load balancer**.
- **S9 – read-only tokens can delete tokens and sessions and change notification preferences.** True: the views with only
  `IsAuthenticated` never look at the module levels, which are what narrows a read-only token. `WritableCaller` (permission class)
  and the same rule in `ModulePermission` for `AUTHENTICATED_ONLY` views refuse every changing call with such a token (403
  `permission_denied`). Applied to: sessions, notifications (read, preferences), the publish of a scale and the calendar and
  availability actions. Creating a token with a read-only token answers 403. Left
  alone: the API logout (it ends the browser session only), exports (a read), imports (they check the module level themselves).
- **S10 – Crew and Freie Kräfte can see the supplier maps.** True. Crew reads Projects, which is not enough: Material or Administration read, or write on one of the three modules (who plans subrentals) – the rule of
  `may_create_supplier` – is needed (`may_see_suppliers`). The report named the two map URLs; the type-ahead of the supplier field
  (`projects/suppliers/suggest/`) shows the same data (name, contact person, address), so it follows.
- **S11 – three redirects check `next` by hand.** True: `/\evil.example` begins with a slash and not with two, and the browser
  reads it as `//evil.example`. One helper (`rentalars/core/redirects.py`, `safe_next_url`) with Django's
  `url_has_allowed_host_and_scheme` serves the three places. Looked at all the other uses of `next`: all but these three already
  used Django's check.

### Independent review

A second reader who had not seen the work went through the diff and tried to get around each fix. It found no way
around S9, S11 and the picture formats of S1; it found real gaps in the others, which were closed (each with a test where a test
is possible):

- **`rentalars nginx-site` left the new `trusted_proxies` unwritten** when the site file already matched the template (a fresh
  install): the script said "nothing to do" before it wrote the snippet. It compares and writes the snippet too now; the
  documents named `rentalars update`, which needs a package, as the way to apply it; they name `nginx-site` now.
- **A bad `trusted_proxies` value could stay on disk** (`bad`, `1.2.3.4.5`, `0.0.0.0/0`, a trailing comment), and a refused
  `nginx -t` restored only the site, not the snippet. Entries are validated as addresses; the snippet is restored.
- **Globbing** in the split of the entries (`*` expanded to file names) – `read -a` instead.
- **A forged `Authentication-Results` header** with the (public) name of the mail server stood below the server's own and could
  outvote a `dmarc=none`; a `;` inside a quoted field or a comment started a result of its own. Now only the topmost header counts,
  comments and quotes are parsed, `header.from` of a DMARC pass must be the sender's domain, a DKIM signer must have a dot.
- **Legitimate mail was refused** for dots in a display name (`Dr. A. Becker <…>`, an obsolete-syntax defect of Python's parser).
- **The reading of wide empty rows** was still slow, and the stop after 5,000 empty rows dropped data silently – see S7.
- **Django's and DRF's image fields** opened with every Pillow reader – the readers are removed from Pillow itself now.
- **Small leftovers of S6:** `install -m` changes the mode by name after creating the file (replaced by O_EXCL creation under a
  umask); `restore.sh` made `chmod 700` on the backup folder before it checked the owner (reordered).
- **Not changed, on purpose:** the map of a *project* still shows the pickup address of a supplier to whoever drives (12.2 number 46
  g); `www-data` and the group-readable files in the data folder (S5); keys shorter than 50 characters are warned about, not refused
  (S4); a local part is not confirmed by a DMARC pass (said in the manuals).


## Part 36: Logic, operation and layout from a review

The task: fix the problems of a review – 16 logic errors (L1 – L16), 12 findings on operation and wording (B1 – B12), 26 on layout (V1 – V26) and 9 on the code (C1 –
C9). The logic errors were reproduced with a test first (the tests fail without the fix, see the table of the last
part), then fixed. No change of the database.

### Logic (L1 – L16)

- **L1 – anonymising a customer deleted other customers' mails.** True: `icontains` on the address list. The recipient lists are
  split into whole addresses (as `mail/suppliers.py` does); the log entries go by whole addresses too.
- **L2 – hours across the change of the clock.** True. `hours_between` converts both ends to UTC before it subtracts. Decision:
  *a duration is the time that really passes* (the night of 30 October 2027 is 9 hours long); *a count of days is the wall clock*
  (rental days, `started_days`). Stored entries are not recalculated – the hours of an approved entry are what was paid, and a
  correction of old data is the operator's decision. The entry is right after the next edit.
- **L3 – the people API could deactivate the own account or the last administrator.** `PersonSerializer.update` calls
  `accounts.services.check_may_deactivate` (the check `set_user_active` makes, split out for it) before `is_active` is written; the answer is 400 like the page's message.
- **L4 – deleting an item through the API.** One function, `material.services.delete_item`; page and API call it.
- **L5 – sold bulk material counted as out.** Sale lines are left out of `pieces_out_with_projects`.
- **L6 – an old failed inspection made the item defective.** The status changes only if no later inspection of the same type is on
  record. The due date was already right.
- **L7 – driving licence against today.** Against the end of the booking, like the vehicle's inspection beside it.
- **L8 – anonymised customers and people through the API.** 409 `anonymised` (`api.errors.RecordAnonymised`), raised in `perform_update` of the two
  viewsets; the model is not changed (a model rule would block the anonymising itself).
- **L9 – name of the mail server.** `MailSettings.clean` takes one word; the self-test (`core/selfcheck.py`) warns when the last
  mails carry no header of that server. A wrong stored value is not repaired by migration (it may be a name the operator
  knows better than we do) and is not refused either: `clean` checks a value only when it differs from the stored one, so that a
  stored value cannot make the save of other settings fail (found by the independent review).
- **L10 – groups of statuses.** `FIRM_STATUSES`, `ORDER_STATUSES`, `EARNING_STATUSES` and `UNSETTLED_STATUSES` are defined once in
  `projects/models.py`; the other modules import them; a test forbids a second definition.
- **L11 – the note of an answer** is erased with the other free texts (`FREE_TEXT_FIELDS`) and in the change log.
- **L12 – moving a project with parts across the change of the clock.** Compared on the wall clock, as `schedule/moves.py` does.
- **L13 – overlapping blocks.** Merged per item in the engine (`_merged_blocks`); the model still allows the overlap (a note can
  be entered for a period already blocked).
- **L14 – a declined place is not planned.** `request_status=declined` is left out, like cancelled projects.
- **L15 – template list** shows the local date.
- **L16 – the lock against double booking** takes the products that compete with the container's contents too
  (`AvailabilityEngine.competing_products`). Not proved as a fault; the lock is wider now, never narrower.

### Operation and wording (B1 – B12)

- **B1, B4 – the settings.** One form, one button; sections as in `SETTINGS_SECTIONS` (a field without a section lands in "Further
  settings", a test stops that); a field error saves nothing; leaving with unsaved changes asks (`app.js`). Decision against
  separate buttons with warnings: three forms on one page are three ways to lose input.
- **B2 – plural.** `ngettext` where the review named a place and in the 17 texts with a bracket; a test reads every call of
  `_`/`gettext`/`pgettext`/`ngettext` and every `translate` tag for "(en)", "(s)", "(n)". `plural_of` for Decimal and text. The shell
  script says "1 Tag alt".
- **B3 – confirmation.** `data-confirm` on every form that deletes, removes, cancels or rewrites other records; the mass takeover
  names the number of projects. A test scans the templates (with an allow-list for forms that are made in Python). **Undo for the
  mass takeover is not built**: the old values are not kept anywhere, and keeping them is a model change for one button.
- **B5 – statuses.** Packing list "zurückgenommen"; service case "zurückgestellt" (the English label is "Backlog"); project
  "Bestätigt – Preise und Einzelheiten offen". The English label "Confirmed – details open" is left as it is – a changed English
  message ID would change the stored text of the choices and need a migration.
- **B6 – terms.** The [glossary](glossary.md) is the list; the German texts follow it ("Behälter" for case and rack, "Crew" for the
  people of a project, "Personal" for the module and the cost type, "Aufgabe" for what runs in the background, "unterwegs" for the
  state of issued material).
- **B7 – same word, other meaning.** `pgettext`: `group` (directory), `Message` (chat, price offer log); "Apply" is "Anwenden".
- **B8 – capital letters.** `capfirst`; a test forbids `.capitalize()`.
- **B9 – dates and numbers.** Four-digit years; `local_pattern` for `strftime`; files with a format of their own (DATEV, exports,
  the gateway command line) keep the German pattern on purpose; the history writes hours and kilometres with `format_decimal`.
- **B10 – du.** The twelve texts of the review; documents and mails to customers keep "Sie".
- **B11 – English interface.** The two wordings and the title of the profit statement. Quick to-dos and units are stored data
  (written from the start data when the installation was made): not touched.
- **B12 – dashes.** `core/choices.py` replaces Django's `---------` once at the start (`BLANK_CHOICE_DASH` and
  `ModelChoiceField.empty_label`), so that no form has to remember it.

### Layout (V1 – V26)

Measured in a browser (Playwright, demo data) at 390 and 1440 px on the pages the review names, with the page width, the size of
the icon buttons and the height of the pack bar read from the DOM, and looked at in screenshots. One stylesheet section ("7. Layout fixes")
holds the changes. Decisions: the actions of a project stay visible in two columns instead of a menu (a menu hides the main action
from a user who does not know it); the full texts of the licence are pages of the program (`/about/<name>/`) and the plain
text stays at `/about/<name>.txt`; the page "About" is an entry of the navigation and gets no "Back" when logged in.
Not built: V3 compact rows on a phone (only the touch targets), V19 the "Suchen" button of the user list, V20 the chat, V15 the
date of the conflict (the reason stands under the name), and V11 (short phases as wide as their label): tried, and taken out again –
a bar must be as wide as the time it shows (VFG-030), and the label is cut; a minimum width broke both, and two tests said so. The
red text of the dark theme got its own token (`--red-text`), because the row under the pointer (#252525) took the contrast of
"Fehlmenge" below 4.5.

### Code (C1 – C9)

C1/C2 only where a finding needed it (L3, L4, L8, L2, L12); a systematic move of the 58 direct `.save()` and `.delete()` calls is a
project of its own. C3: the count of mypy messages is written down in `docs/dev/getting-started.md` (a baseline; new code is
checked); mypy is not part of `check.sh`. C4: the times and counts in `check.sh` and `getting-started.md` are true now; `check.sh`
runs the tests in two processes, `--unit` for the fast subset. C7: short README, `CONTRIBUTING.md`. C5, C6, C8, C9 are not
touched: splitting modules, import layers, the length of the documents and the requirement IDs in the code are decisions for the
maintainers, not for a release that fixes faults.

### What is left of the review

The appendix of the review lists faults of the accounting that stay as they are: positions of an incoming invoice without a tax
rate (`documents/euer.py`), input tax on fixed assets of a small business, the second transfer of a final invoice to Lexware, the
DATEV revenue account for exports and intra-community supplies, several advance invoices in ZUGFeRD. They are accounting, outside
this task's three areas, and each needs a decision with the tax adviser. `COPYRIGHT_HOLDER` is the publisher's to set.

### Tests

`tests/unit/test_118_logic.py` (L1 – L16), `tests/ui/test_118_pages.py` (B1 – B4), `tests/ui/test_118_wording.py` (B5 – B12, V8, V14,
V18, V21 – V25).

### Independent review of the work

A second reviewer, given the task, the diff and no conclusions, tried to break each fix. What it found, and how it is
handled (every point with a test that fails without the change, unless said otherwise):

- **L9: settings with a stored value.** `MailSettings.clean` checks the name only when it differs from
  the stored one, so that changing another setting works (otherwise: page, a 500 error; API, a 400 about a field not sent).
- **B9: the text of a sale.** `forget_customer` rebuilds the reason text of the status "sold" with the German date in every
  language and with the date in the language of the reader (English installations). Both forms of the date are looked for.
- **B3 test.** The test of the mass takeover renders the product page and the
  planning and asserts the confirmation on both forms and the number of projects.
- **V14:** the box "all" of the approval of times follows the rows (the script does not leave early where there is no bar); covered by a browser test.
- **V17:** no loose paragraph on the mail settings page between two boxes.
- **B7:** "returned" is one word for two things in English; the status of a subrental ("zurückgegeben", it goes back to the supplier)
  got its own context. **B5:** the glossary says that the act is "ausgegeben" and the place of the material "unterwegs", while the
  status of the packing list reads "ausgegeben" too.
- **B2:** the scan reads f-strings (two command line outputs ("task(s) run", "project(s) would be summarised") are f-strings).
- **WCAG 2.5.3:** the hidden text of the arrows of the calendar ("‹ früher") follows the visible word.
- **L7:** a booking that ends at midnight sharp still belongs to the day before.
- **V15:** the red of the warnings under a name uses the same lighter token in the dark theme as the shortage text.
- **Left as it is, and said so:** reactivating a person through `PATCH /people/<id>` does not clear the mark "deactivated by the
  directory" (`ldap_deactivated_at`) as the page of the user does – the same on the person's own page; and
  `my_deployments.FIRM_STATUSES` is an alias of `ORDER_STATUSES` (one definition, two names). V4 and V5 (pack bar on a phone,
  fades of the tab bar) were measured in a browser (not taken over from the review).

## Part 37: Photos, contact person dialog, tab order

The task: four requirements. (1) Images and videos (e.g. in chats) are always
re-rendered so that they are efficient in storage and carry minimal metadata; images keep their location data; video is rendered at 720p
at most. (2) a choice "neuer Ansprechpartner" in the contact list of the project form that opens a dialog, (3) the tab
"Fuhrpark" after "Exemplare", (4) photos on models and items. One small change of the database (`material.0017`).

### Photos are made anew (NFA-084)

What was already so: the chat made every photo anew (upright, JPEG, 2048 pixels, no metadata) and every video (ffmpeg, 720p at most,
H.264/AAC, `-map_metadata -1`). What was not: the photo of a defect report (the file as uploaded, PNG too), the photo of an expense
receipt (made anew with its own code: without the place, and without the limit of pixels and the handling of colour profiles
and transparency of the chat) and – of course – the new photos of the material.

- **One place.** `rentalars/core/photos.py` holds what `chat/media.py` did for photos; the chat, the defect report, the material
  (`add_file`) and the receipt (`prepare_receipt`, with 2000 pixels and the formats JPEG/PNG) call `render_photo_upload`
  (check by content, orientation, pixel limit, JPEG, preview), `location_of` (the GPS block), `jpeg`, `shrink_photo`.
  `chat/media.py` imports and re-exports its names, so that the chat code and its tests did not have to move.
- **The place stays, nothing else.** Latitude and longitude with their references, the altitude with its reference (a byte in
  EXIF; found by a test), only when plausible (a latitude of 200° drops the whole place). The date and time of the GPS block, the
  direction, the device, the time of the camera, the comment and the XMP block are gone; the ICC profile stays (colours) if it has at most 128 KB (a larger one is metadata, not colour). The
  preview has no place and no device, only that profile – "minimal", not "none". A 16-bit grey scale is scaled to 8 bits (it came out white).
- **Small photos are made anew too.** The reason for the rule is not the size: everything after the pixels is not wanted.
- **Not made anew:** documents – project files, invoices and receipts of the bookkeeping (also a photographed invoice at a
  purchase), mail attachments, hall plans, logos, label templates, supplier and certificate files and the copy of an invoice at a
  material. A receipt must stay what it was when it came (proof, retention); the logo and the label template are checked as before
  (`open_picture`). A picture attached to a material as manual, protocol or "other" **is** made anew (review: it would otherwise be shown
  whole, with its place, device and time). Open for the project owner: whether camera photos that arrive as project or supplier files
  should be made anew as well. Said in the catalogue (12.2 number 48 d).
- **Stored files are not recalculated.** Old chat photos have no place and stay without; old defect photos stay as uploaded.
- **Data protection.** The place is personal data (where the person was). The update guide and the catalogue say so.

### Photos on models and items (MAT-090)

No new table: `MaterialFile` (MAT-017) with the kind "picture" is the photo, so rights (`visible_files`), delivery, deletion, the change
log and the API already existed. New: the field `thumbnail` (JPEG, 640 pixels, without metadata), the view `material_file_small`,
the API field `thumbnail_url` and `GET /material-files/<id>/thumbnail` (404 for a document). The upload (`photo_views`, a POST with
`photos`, several files) calls `services.add_file`, which renders the photo; a file that is not a photo is named in the message and
the others are stored. At most 20 files per upload. Deleting a photo redirects to the page it was shown on; the signal
`file_row_deleted` removes the stored files after the commit, unless another row shares them (the copies of an invoice do).
The photos are listed oldest first, so the first one uploaded is the head picture. The tab "Files" lost the kind "picture" (form and lists); pictures from before are shown in the box, without a preview – they are
delivered whole. Alternative considered: a separate model "Photo"; refused, because it would repeat rights and API.

### The contact person dialog (PRJ-140)

The contact field is a `<select>`, and the list is the contacts of the customer chosen when the page was built (changing the customer
reloads the part of the form, as before). A `ContactSelect` widget adds the last choice "+ Neuer Ansprechpartner …" with
`data-create-url`; it is not a value. The script (`app.js`) opens the dialog (`customers:contact_quick_create`) on the change, puts the
list back to what it showed, and on `objectCreated` (the answer of the dialog, as for the customer in PRJ-070) adds the contact as an
option and chooses it. Without a script the value `__new__` is sent as it is: the form shows an error on the field (the first version turned it into
"empty" and saved the project without the contact – review). The choice is only offered if the user may change customers
(`Module.CUSTOMERS`, write), a customer is known and not anonymised. The dialog button is disabled while the request runs, and a
person with the same name and e-mail address as an existing contact of the customer is not added again. The dialog asks for the name and the ways to
reach the person; greeting and "primary contact" stay on the customer page (the first contact of a customer is primary by itself).

### The order of the tabs (UIX-013)

`templates/material/_tabs.html`: Products, Models, Items, Fleet, Open points, Inspections, Audit, Import. Tests that list the tabs were
changed.

### Tests

New: `tests/unit/test_119_photos.py` and `tests/ui/test_119_contact_dialog.py`. Older tests changed: a defect photo is a `.jpg`
(`test_085_defects`, `test_material_stage5_pages`), a picture is not added in the tab "Files" but with the box on the page
(`test_material_stage5_pages`), the chat test keeps the place (`test_092_chat_media`), the order of the tabs
(`test_back_and_page_size`).

### Independent review of the work

A second reader, who had not seen the work, found: pictures attached as manual or other file stayed whole with their metadata
(now made anew); the receipt kept its own code without the pixel limit (now through `render_photo_upload`); the claim "no
metadata at all" for the preview was wrong (the profile stays – the texts say so, and the profile is capped); the choice "New
contact person" sent without script was silently emptied (now an error); no choice for anonymised customers; a double click
created two contacts; the script put a created record into any list of that name; a 16-bit grey PNG came out white; HEIC got
the general message; the photos were listed newest first; stale sentences in the README, the operating manual and the core flows. The full run on MariaDB then found one more error, which
is not new: deleting an item or model that has a file failed there, because Django empties the nullable owner of a file first
(MySQL cannot defer checks) and the rule "exactly one owner" forbids that. Now `files_before_owner` (a `pre_delete` signal) deletes the
files first; a test for the model and one for the item.
Each has a test (`ReviewFixTests`, `test_119_contact_dialog`). Not done: the service case form had no such choice (a contact was
created at the customer first) – the requirement named the project form; it follows in Part 38.

## Part 38: New contact person in the service case, copyright holder, preparing the publication

Open points and the preparation to publish the source. No new requirement, no migration.

### New contact person in the service case (PRJ-140)

The form of a service case (`ServiceCaseForm`, new and edit) got the same last choice as the project form. The logic moved into one function,
`offer_new_contact(form, rights, customer_id)` in `projects/forms.py`: it replaces the widget with `ContactSelect` when the user may change
customers and a non-anonymised customer is known, and it turns a sent `__new__` into an error on the field (`new_contact_sent`). The
project form calls it too, so the two cannot drift apart. The view passes `rights`; a user who may not see customers gets no contact field at all, as before.
In the case form the customer is chosen in a type-ahead and the contact part is reloaded with it (as in the project form), so the dialog always knows its customer.
Tests: `CaseContactDialogTests` in `tests/ui/test_119_contact_dialog.py`.

### Copyright holder (UIX-062)

`COPYRIGHT_HOLDER` is "Lars Wilting, fld-vt.de"; the README names it. `PLACEHOLDER_HOLDER` stays, so a version of someone else can set the
holder back and the page "About Rentalars" shows the translated placeholder. The credit "by fld-vt.de" (`CREDIT_NAME`, `CREDIT_URL`,
ADDITIONAL-TERMS.md) is intended and stays. Whether code written by an AI changes anything for copyright and copyleft is a legal question,
not answered here.

### Keeping the repository free of private data

Rules that the checks and reviews follow, for whoever adds code or documents:

- **No real data.** Example addresses end in `.example` (`example.de`, `.org` and `.com` are tolerated placeholders); names of suppliers, customers
  and users in demo data and tests are invented; no real phone numbers, addresses, keys or tokens. The tests that check a partial match
  (`anna@…` against `hanna@…`) show how to keep the intent with invented addresses.
- **Requirements, not chat.** Comments, docstrings, tests and documents state the requirement or the decision in neutral words; they do not quote
  messages. German names of screens and buttons in quotes are product text and stay. A multi-line search over comments and docstrings for quotes with German function words finds
  the usual slips.
- **Nothing that belongs to the working environment** goes into the package: built apps (`*.apk`), key stores and
  certificates (`*.keystore`, `*.jks`, `*.p12`, `*.pem`) and `.env` files are excluded by `.gitignore`.

## Part 39: Pairing in the browser, gateway in the self-check, photos beside the data

Open points after the preparation: the gateway had no entry in the self-check, pairing an app needed a shell on the server, and the box "Photos" took too much room. No new requirement, no migration.

### Pairing and locking out in the browser, the gateway in the self-check (GWL-011, GWL-014)

An administrator needed a shell on the server to pair a phone (`rentalars gateway pair`). `rentalars/gateway_link/web.py` now does the same work
from the settings (`/administration/gateway/`), on the services that the command uses (`service.create_offer`, `service.revoke_device`). The code is
shown in the answer to the POST only (no redirect, `Cache-Control: no-store`), never stored by the page; the change log gets an event without the code.
Pairing and locking out need the right to delete in the settings, like the change of the server address: whoever pairs an app gives its holder the
account. A device is locked out in the database before the gateway is told; if the gateway is not reachable the device stays locked and the page says
so. Connecting, disconnecting and `rekey` stay commands (they need root and the service). The security log (AUT-021) was not used for pairing: a new
kind there would change the database, which this version does not. The self-check reads the database only and never calls the gateway (a slow or
dead gateway must not slow the page down); the expiry of the gateway's certificate is therefore not checked.

### Further example data and the catalogue

Example names are invented: label tests use "BSP"/"XYZ" and `bsp.test`, demo and mail tests "Jazzclub Beispiel e. V." and "Stadtwerke Beckstadt"
(the mail tests search for "Beck", so the name must contain it). The sample LAN address is `192.168.1.50` (a private range). The catalogue has 822 requirements and no stage 12.

### The box "Photos" beside the data (MAT-090)

The box "Photos" (MAT-090) is beside the data on the page of a model and of an item. The first photo is in the page head
anyway, so the box is not the main thing. The class `.with-aside` (a grid: data 2.2 parts, photos 1 part, at least 240 px) holds the data and the box; under
62 rem it is one column and the box comes last. On the page of an item the existing `.columns` ("Item", "Purchase") stand in `.with-aside-main`. The
previews start at 96 px and the upload field stands above its button. Checked with screenshots at 1440 and 390 px (no sideways scrolling). Alternative considered: the box
further down the page; refused, because the right-hand side beside the data was empty anyway.
