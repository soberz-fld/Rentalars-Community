#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the installation package of Rentalars (NFA-046).
#
#     scripts/build_package.sh
#
# writes  dist/rentalars-<version>.tar.gz . The package contains one folder,
# rentalars-<version>/, with everything needed to install and to develop:
# program, language files, server scripts, documentation, tests, licence.
#
# Run scripts/check.sh first; this script only packs.
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."

version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' rentalars/__init__.py)"
[[ -n "${version}" ]] || { echo "Version not found in rentalars/__init__.py" >&2; exit 1; }
name="rentalars-${version}"

# The compiled language file must match its source; the server only reads the compiled one.
if [[ locale/de/LC_MESSAGES/django.po -nt locale/de/LC_MESSAGES/django.mo ]]; then
    echo "locale/de/LC_MESSAGES/django.mo is older than django.po. Run: python manage.py compilemessages" >&2
    exit 1
fi

mkdir -p dist
tar -czf "dist/${name}.tar.gz" \
    --transform "s|^\.|${name}|" \
    --exclude './.git' --exclude './.venv' --exclude './var' --exclude './dist' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude './.coverage' \
    --exclude './.mypy_cache' --exclude './.ruff_cache' --exclude './wheels' \
    --owner=0 --group=0 --numeric-owner \
    .

echo "dist/${name}.tar.gz  ($(du -h "dist/${name}.tar.gz" | cut -f1))"
