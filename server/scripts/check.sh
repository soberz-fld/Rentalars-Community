#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run every automatic check of the project (NFA-020, NFA-053, NFA-062).
#
#     scripts/check.sh           everything; the tests are over 8,600 and take about 30 minutes on two cores
#     scripts/check.sh --unit    the checks and only the unit tests (tests/unit), a few minutes
#     scripts/check.sh --quick   without the tests (about two minutes)
#
# The tests run in RENTALARS_TEST_PROCESSES processes (default 2; 1 runs them one after the other).
#
# This is what the continuous integration runs on every change
# (.github/workflows/ci.yml). A change is ready when this script ends with
# "All checks passed".
#
#   1. Style and formatting, docstrings, likely bugs, security smells (ruff)
#   2. The Django system check and "no model change without migration" (NFA-004)
#   3. The language file is complete and compiled (NFA-026)
#   4. The OpenAPI description builds without warnings (API-004)
#   5. Licences of all libraries are compatible with the GPL (NFA-053)
#   6. The traceability file is up to date (NFA-057)
#   7. Server scripts pass shellcheck, if shellcheck is installed, and recognise the
#      operating system and the device (tests/deploy/test_system.sh, NFA-063, NFA-070),
#      and "rentalars uninstall" works (tests/deploy/test_uninstall.sh)
#   8. All tests, including "every API operation has a test" (API-014, see rentalars/testing.py)
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "1/8  Style, docstrings, likely bugs (ruff)"
ruff check .
ruff format --check .

step "2/8  Django system check and migrations"
python manage.py check
python manage.py makemigrations --check --dry-run

step "3/8  Language file"
python - <<'PYTHON'
import sys

import polib

catalogue = polib.pofile("locale/de/LC_MESSAGES/django.po")
problems = [entry.msgid for entry in catalogue.untranslated_entries() + catalogue.fuzzy_entries()]
if problems:
    sys.exit("Untranslated or doubtful texts in locale/de: " + "; ".join(problems[:10]))
print(f"{len(catalogue)} texts, all translated.")
PYTHON

step "4/8  OpenAPI description"
warnings="$(python manage.py spectacular --validate --file /dev/null 2>&1 || true)"
if [[ -n "${warnings}" ]]; then
    echo "${warnings}"
    echo "The OpenAPI description has warnings or errors."
    exit 1
fi
echo "OpenAPI description builds without warnings."

step "5/8  Licences and known vulnerabilities of the libraries"
python scripts/check_licenses.py
# S1: the versions in requirements.txt are fixed, so every installation stays as vulnerable as the list is old.
# pip-audit asks the vulnerability database (PyPI); RENTALARS_SKIP_AUDIT=1 skips it where there is no network.
if [[ "${RENTALARS_SKIP_AUDIT:-}" == "1" ]]; then
    echo "pip-audit skipped (RENTALARS_SKIP_AUDIT=1)."
elif command -v pip-audit > /dev/null; then
    pip-audit -r requirements.txt --no-deps --disable-pip --strict
else
    echo "pip-audit is not installed (pip install -r requirements-dev.txt); skipped."
fi

step "6/8  Traceability"
python scripts/build_traceability.py --check

step "7/8  Server scripts (shellcheck, system detection)"
if command -v shellcheck > /dev/null; then
    LANG=C.UTF-8 shellcheck -x deploy/*.sh deploy/rentalars scripts/*.sh tests/deploy/*.sh
    echo "Shell scripts ok."
else
    echo "shellcheck is not installed; skipped."
fi
# How the scripts recognise Ubuntu, Raspberry Pi OS and the Raspberry Pi, with made-up systems (NFA-070).
if ! system_detection="$(bash tests/deploy/test_system.sh)"; then
    grep -A2 '^FAIL' <<<"${system_detection}"
    exit 1
fi
echo "System detection: ${system_detection##*$'\n'}"
# "rentalars uninstall" against a made-up server with stand-ins for the system commands (uninstall).
if ! uninstall_check="$(bash tests/deploy/test_uninstall.sh)"; then
    grep -A2 '^FAIL' <<<"${uninstall_check}"
    exit 1
fi
echo "Uninstall: ${uninstall_check##*$'\n'}"

if [[ "${1:-}" == "--quick" ]]; then
    printf '\n\033[1mQuick checks passed (tests not run).\033[0m\n'
    exit 0
fi

step "8/8  Tests"
if [[ "${1:-}" == "--unit" ]]; then
    labels=(tests.unit)
else
    labels=(tests)
fi
python manage.py test "${labels[@]}" --parallel "${RENTALARS_TEST_PROCESSES:-2}"

printf '\n\033[1mAll checks passed.\033[0m\n'
