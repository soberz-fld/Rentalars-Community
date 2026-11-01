# Contributing to Rentalars

Thank you for looking. This page is the short way in; the long way is in [docs/dev/](docs/dev/).

Rentalars is free software under the GPL (3.0 or later, with the additional term in
[ADDITIONAL-TERMS.md](ADDITIONAL-TERMS.md)). By sending a change you agree that it is published under the same terms.

## Set up

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate && python manage.py create_demo_data
python manage.py runserver        # http://localhost:8000, first-run setup in the browser
```

[docs/dev/getting-started.md](docs/dev/getting-started.md) goes through it step by step, including the database of the
tests (SQLite; MariaDB for the full run) and the browser tests (Playwright).

## Before you send a change

```sh
scripts/check.sh --unit     # style (ruff), system check, migrations, language file, licences, traceability, unit tests
scripts/check.sh            # everything, including the page, API and browser tests (about 30 minutes on two cores)
```

`scripts/check.sh` is what the continuous integration runs ([.github/workflows/ci.yml](../.github/workflows/ci.yml)). A change
is ready when it ends with "All checks passed".

## How the code is organised

* **Language:** Code, comments and developer documentation are English. The user interface is German and English: the
  English text is the message ID in the code, German comes from `locale/de`. After a text changed:
  `python manage.py makemessages -l de --ignore ".venv/*" --ignore "var/*" --ignore "tests/*" --ignore "docs/*" --ignore "scripts/*"`,
  fill in the German text, `python manage.py compilemessages -l de --ignore ".venv"`. The check fails on a text that is
  untranslated or marked as fuzzy.
* **Words:** Follow the [glossary](docs/dev/glossary.md) – one word for one thing (Exemplar, Behälter, Crew, Personal …), du in
  the interface, `ngettext` for every number with a noun, four-digit years.
* **Rules live in services,** not in views or serializers. A page and the API that do the same thing call the same function,
  so that they decide the same (an example: `accounts/services.set_user_active`, `material/services.delete_item`). A
  business rule names the requirement it implements (`PRJ-008`) in a comment or docstring; that is how
  [docs/dev/traceability.md](docs/dev/traceability.md) is built (`python scripts/build_traceability.py`).
* **Times** are stored in UTC and shown in local time. A duration is the time that really passes, a day count is counted on
  the wall clock – state which one you mean, and test across both nights of the change of the clock.
* **Every change has a test** that fails without it. `tests/unit` for rules, `tests/api` for the API (every operation needs a
  test), `tests/ui` for pages, `tests/browser` for what only a browser shows. Test files are named after their area
  (`test_118_logic.py`) – add yours to the file of its area or open one.
* **Licence header:** a new source file starts with the line `SPDX-License-Identifier: GPL-3.0-or-later` (as a comment).
* **Migrations:** `python manage.py makemigrations --check` must say nothing; a model change comes with its migration.

## Work with AI assistants

Large parts of Rentalars were written with AI assistants (mainly Claude through Claude Code); see the README. You may use one for
your change, on these terms:

* **You answer for the change,** as if you had written every line: read it, run `scripts/check.sh`, and be able to explain it.
* **Say so.** Name the assistant in the description of the pull request. A commit that an assistant made carries a trailer after
  a blank line at the end of its message – `Co-Authored-By: Claude <noreply@anthropic.com>` or the name of the assistant you used – so that
  GitHub shows the co-author.
* **Nothing private goes into a prompt:** no real customer data, access data or secrets (the same rule as for a report below).
* **Licences:** do not send code you cannot publish under the GPL, whoever or whatever wrote it.

## Where things are decided

[docs/dev/decisions.md](docs/dev/decisions.md) lists what was decided and why, version by version; the requirements are in
[docs/anforderungen/Rentalars_Anforderungskatalog.md](docs/anforderungen/Rentalars_Anforderungskatalog.md) (German). If your
change turns on a decision of the catalogue, say which one.

## Reporting a problem

Say the version (it stands in the foot of the menu and on the page “About Rentalars”), what you did, what you expected and what
happened. Do not put real customer data or secrets in a report; `python manage.py create_demo_data` makes data you can share.
For a security problem please do not open a public issue; write to the maintainers privately (the address is on the page of the project where you found Rentalars).
