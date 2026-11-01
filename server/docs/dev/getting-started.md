# Getting started

This guide takes you from an empty folder to a running development copy of
Rentalars with all tests passing. It assumes that you know basic Python and
have never seen this project. It should take about fifteen minutes, plus the time of the tests if you run them all (see step 4).

Everything here is for development on your own machine. Installing Rentalars
on a server is a different thing and described in
[docs/en/operations/installation.md](../en/operations/installation.md)
(German original: [docs/betrieb/installation.md](../betrieb/installation.md)).

## 1. What you need

| | |
|---|---|
| Python | 3.12 to 3.14 (`python3 --version`); 3.12 is what Ubuntu 24.04 brings, 3.14 what Ubuntu 26.04 brings, and the tests run with both |
| Operating system | Linux or macOS. On Windows use WSL. |
| System libraries | Pango, for creating PDF files (packlists, documents, labels) |
| Database | none – development uses SQLite, a file |

On Ubuntu or Debian the system libraries come with:

```sh
sudo apt install python3-venv python3-dev build-essential pkg-config \
    libmariadb-dev libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
```

`libmariadb-dev` and the compiler are needed because the requirements
include the MariaDB connector, even though development does not use
MariaDB. On macOS: `brew install pango mariadb-connector-c pkg-config`.

## 2. Get the code and create the environment

```sh
tar -xzf rentalars-1.0.0.tar.gz     # or: git clone …
cd rentalars-1.0.0
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
```

`.venv` is a private Python environment for this project. `. .venv/bin/activate`
switches your shell to it; you need that line again in every new terminal.

## 3. Create the database and start

```sh
python manage.py migrate
python manage.py runserver
```

`migrate` creates the tables in `var/development.sqlite3` and fills in the
start data every installation has: categories with their codes (also
N "Nebenkosten"), units, tax rates, the suggested roles, the
default rental scale, and the storage location "Hauptlager"
as the default for new items and eight job functions – Techniker,
Lichttechniker, Tontechniker, Medientechniker, Stagehand, Lager,
Projektplanung, Sonstiges –, each with its service product in category D,
without a price yet. The document types of project files
include "Showfile" (visible to the crew, before "Sonstiges"); the
settings of the surcharges for night, Sunday and holidays are created
with the rates of § 3b EStG when they are first used, switched off;
invoices are switched on, maps load only after "Karte anzeigen", and the
warehouse address is empty (the company's address counts). `migrate` also creates the three automations of the service cases
(`automations/0002_cases_083`) and the empty AI settings (everything off);
the notification settings of the company (shortages every day
at 4:15, four weeks ahead), and the role "Crew" packs (write on packing in
its assigned projects).

**Language**: the start data are German unless the
installation's `language` is `en` (a configuration file with
`[rentalars] language = en`, see section 7) or you choose "English" in the
first-run setup – then `core.start_data.localise` gives them their English
names ("Main warehouse", "Standard scale", "Lighting technician" …). The
interface follows your browser on the login page and your account's
"Language" afterwards (My account). The English texts are the msgids in
the code; German comes from `locale/de/LC_MESSAGES/django.po`.

Open <http://localhost:8000>. A fresh installation shows the **first-run
setup**: enter a company name and the first administrator, tick "Beispieldaten
anlegen" and you have products, material, customers and three projects to
click through. The setup also creates the project template "Dry Hire
(Vermietung ohne Personal)"; the project numbers read
`2026-0001`. The sample data use the job
functions of the start data and give them prices – "Tontechniker" with
hour tiers (10 hours a day, then 55.00 instead of 45.00) –, plan the
transport F-001 as Nebenkosten, and give the suppliers an e-mail address,
so that "Zumietung bei …" finds their mails. The sample data
have no service case, show file, chat message,
automation or expense, their suppliers have no address, and their crew
lines have no surcharges (the settings start switched off). (The sample data can also be
created later with `python manage.py create_demo_data`, as long as the
installation has no data of its own; the service products of the start
data do not count as such.)

An existing development database is brought up to date by the same
`migrate`. Run it in one go, as the server's update does: when
`projects 0012` ("P-" given) and `projects 0014` ("P-"
taken away) run in the same `migrate`, the numbers end up as before
without a former number; run separately, the P- numbers stay as former
numbers (core-flows, section 16). Some migrations change data as
well – job functions get service products of their own, services without
function become Nebenkosten, subrentals without supplier become "offen",
the power moves out of category fields; core-flows, section 20 lists them.
Further ones add two packages with their tables (`chat`, `automations`),
the expenses, the positions of addresses and the surcharge settings, and
change only one thing in the data: the document type "Showfile" is created
or an existing one marked (core-flows, section 29). Further ones add
the package `ai` with its tables, the languages, the prepared address
changes and the status reason of service cases, and create the three
default automations (core-flows, section 35). Further ones fill the
change times per field of projects and people from the change log, let
the role "Crew" pack, rename an English "Night 0–4 o'clock" rule, and
create the notification settings (core-flows, section 38).
Copy `var/development.sqlite3` first if you want to compare.

**Shortage checks in development**: a server runs them from
the minute timer; in development run `python manage.py run_jobs` by hand.
The first run after `migrate` only notes its time; the next one at or
after the time set under Einstellungen → Benachrichtigungen checks.
`python manage.py run_daily_maintenance` does not check shortages.

**The local AI in development**: nothing to install. The
tests use `tests/ai_fake.py`, an OpenAI-compatible server on 127.0.0.1.
To try the pages against a real model, run any OpenAI-compatible server on
this machine (Ollama, LM Studio, `llama-server`) and either enter it under
Einstellungen → KI as an interface (internal addresses need
`[network] allow_internal = 127.0.0.1` in a configuration file) or, with a
configuration file (`RENTALARS_CONFIG`, section 7), write next to it the
file `ai-local.conf` that `deploy/ai.sh` would write – at least
`[local_ai]` with `url = http://127.0.0.1:PORT/v1` and `model = NAME`; the
other keys are in the docstring of `rentalars/ai/local.py`.
`bash deploy/ai.sh install --dry-run` shows the plan without root, and
 `bash deploy/ai.sh refresh --dry-run` as well. Settings → AI
reads the processor of your machine from `/proc/cpuinfo` (`ai/cpu.py`;
the setting `RENTALARS_AI_CPUINFO` names another file for tests); without
the file (macOS) the report is empty. The tests of `refresh` run
`deploy/ai.sh` with `RENTALARS_AI_TEST_ROOT` (every path below a folder)
and `RENTALARS_AI_SYSTEMCTL` (a stand-in for systemctl), so they need no
root. `tests/ai_fake.py` streams (server-sent events), can "think aloud"
(`<think>` blocks), stall (for the silence limit) and refuse extra fields
with 400.

**The server address page** reads the NGINX site and the certificate on
127.0.0.1:443; on a development machine it says that a TLS proxy or a
development install is likely. Preparing a change works; applying needs
`deploy/address.py` as root on a real installation.

Maps need the internet in development as well: after "Karte anzeigen" the
server asks Nominatim and the browser loads tiles from OpenStreetMap. To
keep everything local, use a configuration file (as in section 7) with an
empty `[maps] tile_url =` (no maps, route links stay) or your own servers – see
`[maps]` in [deploy/rentalars.conf.example](../../deploy/rentalars.conf.example).

Without a configuration file Rentalars runs in development mode: SQLite,
debug pages on errors, e-mails printed to the terminal instead of sent. A
server reads `/etc/rentalars/rentalars.conf`; the meaning of every setting is
explained in [deploy/rentalars.conf.example](../../deploy/rentalars.conf.example)
and in `rentalars/config.py`.

## 4. Run the tests

```sh
python manage.py test
```

Over 8,600 tests (unit, API, page, acceptance and browser tests – the browser
tests are skipped where Playwright is not installed). All of them take about 30 minutes on two cores
(`--parallel 2`), a single folder or file only a few seconds or minutes.
They use their own database in memory; your development data is not
touched. Useful variations:

```sh
python manage.py test tests.unit                       # one folder
python manage.py test tests.unit.test_pricing          # one file
python manage.py test tests.unit.test_pricing.BillingModeTests.test_flat_ignores_the_rental_days   # one test
python manage.py test --parallel 2                     # faster on several cores (the browser tests may time out when the machine is busy; run those again alone)
scripts/check.sh --unit                                # all checks, and only the unit tests
```

The tests are sorted by what they prove:

| Folder | Contents |
|---|---|
| `tests/acceptance` | One file per acceptance scenario of catalogue chapter 11, named after it. Start reading here. |
| `tests/unit` | Business rules in detail: availability, prices, packing, import, rights. |
| `tests/api` | Every operation of the HTTP API. The run fails if an operation is not reached *successfully* by at least one test (API-014, `rentalars/testing.py`). |
| `tests/ui` | The browser pages, read as HTML: forms, lists, rights – and, in `test_accessibility.py`, the rules of WCAG 2.1 that the HTML alone shows, on every main page (NFA-025). |
| `tests/browser` | A real browser clicks through the pages that change without reloading. Skipped unless Playwright is installed, see below; the axe-core check also needs axe-core. |

Test files are named after their area (`tests/unit/test_<area>.py`, `tests/ui/test_<area>_pages.py`,
`tests/api/test_<area>_api.py`, `tests/browser/test_<area>_in_browser.py`); a number in a file name only keeps
related files together. A few files need a word:

- `tests/unit/test_080_pi.py` runs the shell test `tests/deploy/test_system.sh` (the functions of `deploy/lib.sh` that
  decide about system, Raspberry Pi, packages, memory and SD card, with made-up `/etc/os-release`,
  `/proc/device-tree/model`, `/proc/meminfo` and `/sys/dev/block`; `bash tests/deploy/test_system.sh` runs it alone).
- `tests/ai_fake.py` is an OpenAI-compatible server on 127.0.0.1 that the AI tests talk to;
  `tests/address_certificates.py` is a small certificate authority and an isolation helper for the address command.
- `tests/ui/test_083_i18n_pages.py` crawls the main pages in English and fails on typical German words;
  `tests/unit/test_083_tables.py` walks every `TableDefinition` and fails on a shown column that neither groups nor
  names a reason. Tests that read the German output of the server scripts set `RENTALARS_LANG=de`, so they do not
  depend on the machine's locale.
- `tests/browser/test_084_ui_in_browser.py` measures the hour lines against the hour columns at 1236, 1366, 1440, 1600
  and 1920 px and drives the drawer with emulated touch; the companion API tests use a token limited to packing,
  projects, time_tracking and email, as the app does.
- The LDAP tests need no server: `tests/ldap_fake.py` replaces the one function that creates connections by an
  in-process `ldap3` directory (`MOCK_SYNC`), so the real search, filter and bind code runs. **One test is opt-in**
  and talks to a real OpenLDAP: it starts the operating system's `slapd` on 127.0.0.1 with the `memberOf` overlay and
  a self-signed certificate and is skipped unless you ask for it and `slapd` is installed
  (`sudo apt install slapd`):

```sh
RENTALARS_SLAPD=1 python manage.py test tests.unit.test_100_ldap_slapd
```

Nothing in the suite uses a real camera: the scanner's browser tests give the page a simulated `BarcodeDetector` and
video, and the AI reading of invoices runs against `tests/ai_fake.py`. The libraries (`ldap3`, `pyasn1`) come with
`pip install -r requirements-dev.txt`.

Every test takes place on 1 March 2027, 08:00 (`tests/helpers.py`,
`stop_the_clock`): the examples use fixed dates in March 2027, and the
application compares dates with today in a few places.

No test talks to a real mail server. `tests/mailbox.py` provides a mailbox
in memory that behaves like an IMAP server (`FakeMailbox`, passed to
`fetch_mail(opener=…)`) and `capture_smtp()`, which catches what would be
sent. Nor does a test ask a real geocoder: `tests/geocoder_fake.py`
(`FakeGeocoder`,) replaces `core.geocoding._send` and the wait
between two requests, answers like Nominatim from a table of addresses
and keeps the questions asked; the browser tests of the maps take their
tiles from the test server.

Tasks in the background (imports, many labels, the full export) run at
once inside the request during tests (`JOBS_RUN_INLINE` in `settings.py`),
so a test sees their result directly. On your development server they run
as on a server: as a process of their own, `python manage.py run_jobs
--job N`, started by the page; its output appears in the terminal of
`runserver`. A server has a timer for what was not started or was
interrupted (`rentalars-jobs.timer`); on your machine,
`python manage.py run_jobs` does the same by hand – it starts interrupted
tasks once more and runs whatever is still waiting.

Invoices need company and customer data for the electronic invoice;
`tests/helpers.py` has `ready_for_invoices()` for that.

### Tests in a real browser

The page tests do not run the scripts of a page. Mistakes in the interplay of
page and script only show in a browser, so a small set of tests drives one:

```sh
pip install playwright
playwright install chromium
python manage.py test tests.browser
```

### The accessibility check with axe-core

`tests/browser/test_accessibility_in_browser.py` runs axe-core – the
checker browser tools for accessibility are built on – over the main pages
in a real browser, against WCAG 2.1 level A and AA (NFA-025), colour
contrast included. axe-core is not part of Rentalars (it has a licence of
its own, MPL 2.0); the test is skipped unless it is at hand. With Node.js
installed, fetch it once and point the test to it:

```sh
npm pack axe-core@4.10.2 && tar xzf axe-core-4.10.2.tgz
RENTALARS_AXE=$PWD/package/axe.min.js python manage.py test tests.browser.test_accessibility_in_browser
```

(An `axe-core` in `node_modules/` of the project folder is found without
`RENTALARS_AXE`.) The test needs Playwright like the other browser tests.
What the HTML alone shows – names of fields and buttons, text alternatives,
unique IDs – is checked on every test run anyway, by
`tests/ui/test_accessibility.py`.

## 5. Run all checks

```sh
scripts/check.sh
```

This is what the continuous integration runs on every change
(`.github/workflows/ci.yml`): style and formatting, missing descriptions,
the Django system check, "no model change without migration", the language
file, the OpenAPI description, licences of all libraries (also
the files in sub-folders of `static/vendor/`, such as Leaflet's pictures),
the traceability file, the server scripts – `shellcheck` over `deploy/`,
`scripts/` and, `tests/deploy/`, and the shell test
`tests/deploy/test_system.sh` –, and all tests. A change is ready when the script
ends with "All checks passed". `scripts/check.sh --quick` leaves out the
tests.

Two findings you will meet sooner or later:

- **`D103 Missing docstring`** – every module, class and function says what
  it is for (NFA-056). Write the *why*: the business rule, the trade-off, the
  known trap. Name the requirement the code implements, e.g. `VFG-002`.
- **"The language file is not complete"** – you added a text to the user
  interface. Texts are written in English in the code and translated in
  `locale/de/LC_MESSAGES/django.po`:

  ```sh
  python manage.py makemessages -l de --ignore ".venv/*" --ignore "var/*" \
      --ignore "tests/*" --ignore "docs/*" --ignore "scripts/*"
  # translate the new entries in locale/de/LC_MESSAGES/django.po, then:
  python manage.py compilemessages -l de --ignore ".venv"
  ```

Formatting is automatic: `ruff format .` rewrites the files, `ruff check --fix .`
repairs what can be repaired.

**Types (mypy).** `mypy rentalars` is not part of `scripts/check.sh`: it takes about 30 seconds and reports the loosely
typed parts of the frameworks. The baseline (mypy 2.4.0 with the Django and DRF plugins): **1,526
messages in 286 of 651 files**, mostly `union-attr` (441), `attr-defined` (345) and `arg-type` (267) – related models,
request data and serializers. Run it for the files you touched and do not add messages to them:
`mypy rentalars | grep "rentalars/<module>/"`. Lowering the count is welcome; a change that raises it needs a reason.

## 6. Find your way around

- **From a requirement to the code:** search for its ID.
  `grep -rn "VFG-002" rentalars tests` leads to the availability calculation
  and to its tests. [traceability.md](traceability.md) lists this for every
  requirement of the stages built so far.
- **From a page to the code:** the address tells the module.
  `/projects/…` is `rentalars/projects/urls.py` → `views.py` → `services.py`.
- **From the API to the code:** <http://localhost:8000/api/v1/docs/> lists
  all operations; each is a class in the `api.py` of its module.
- **The big picture:** [architecture.md](architecture.md), then
  [data-model.md](data-model.md), then [core-flows.md](core-flows.md).

German terms of the catalogue have fixed English names in the code –
"Exemplar" is always `material item`, "Teilgruppe" always `group`, "Set"
always `kit`, "Funktion" always `job function`, "Personalposition" always
`crew line`, "Zeiteintrag" always `time entry`. The list is section 2.1 of the
[requirements catalogue](../anforderungen/Rentalars_Anforderungskatalog.md).

## 7. Developing against MariaDB (optional)

Servers run MariaDB. Differences between the two databases are rare but
real – one of them is described in [decisions.md](decisions.md), "No
`__date` lookups". To run the tests against MariaDB, create a database user
that may create databases whose name starts with `test_`, and point
Rentalars at a configuration file:

```sh
sudo mariadb -e "CREATE DATABASE rentalars_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER 'rentalars_dev'@'localhost' IDENTIFIED BY 'devpassword';
  GRANT ALL ON rentalars_dev.* TO 'rentalars_dev'@'localhost';
  GRANT ALL ON test_rentalars_dev.* TO 'rentalars_dev'@'localhost';"

cat > var/mariadb.conf <<'EOF'
[rentalars]
environment = test

[database]
name = rentalars_dev
user = rentalars_dev
password = devpassword
EOF

RENTALARS_CONFIG=var/mariadb.conf python manage.py test
```

A few tests only run on MariaDB: `tests/unit/test_concurrency.py` books the
same product from two connections at once (VFG-007), sends the same time
entry twice at the same moment (ZEI-009) and lets ten people record at once
(NFA-051), which SQLite cannot do.

## 8. Large amounts of data

```sh
python manage.py create_load_test_data     # 100 users, 20,000 items, 1,000 projects
python manage.py measure_performance       # times the pages of acceptance scenario 11
python manage.py measure_performance --create-test-data   # both in one step (NFA-044)
python manage.py measure_concurrency --url https://… --users 10   # ten people record times at once (NFA-051)
```

Besides opening the big project and adding a line, `measure_performance`
times the ordinary pages listed in `USUAL_PAGES` in
`rentalars/core/loadtest.py`; a page that matters for speed is added
there. They include the week of the calendar, the lists with all
columns and as CSV, the timelines and the documents of the big project;
the chat of the big project (the load data give it 300
messages of ten people), its change question with the chat key and the
chat API, the service cases, the expenses of a month, one's own expenses
and the expense dialog (the load data add expenses to the projects).

`measure_concurrency` talks to a *running* server and needs a database with
real row locks; it creates its own test accounts and removes them again.

Use a separate database for this (a configuration file as above); the
command refuses to mix test data into an installation that has customers or
projects. Measured values are recorded in
[docs/betrieb/betrieb.md](../betrieb/betrieb.md).

To fill your development copy from files, or to look at all its data at
once:

```sh
python manage.py import_material bestand.xlsx --commit            # the material list
python manage.py import_data customers kunden.csv --commit        # products, customers, people
python manage.py export_data var/export.zip                       # everything as JSON, CSV and files
```

Without `--commit` an import is a dry run. The guide for operators,
[docs/betrieb/import.md](../betrieb/import.md), lists the columns each
import recognises.

## 9. Building the package

```sh
scripts/check.sh && scripts/build_package.sh      # → dist/rentalars-<version>.tar.gz
```

The version number lives in `rentalars/__init__.py` (and, for the tools, in
`pyproject.toml`). A new version gets an entry in `CHANGELOG.md`.
