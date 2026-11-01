# SPDX-License-Identifier: GPL-3.0-or-later
"""KND-004: split the names of existing contacts into first and last name.

``name`` is not touched – the name shown stays what it was. Forward: every contact without first and last name gets
them from ``name``. Contacts that have a first or last name are left alone, so the step can run again. Backward: a
name that no longer agrees with the parts (they were edited since) is rebuilt from them; the parts are dropped by the
step before.

The rule that splits a name is a frozen copy of ``customers.names.parse_name`` and does not import it: a
migration must do the same on every installation, whatever the live rule becomes later. It reads like this: text in
parentheses is cut; a comma after a whole name starts a remark ("Anna Berg, Technik"); "Berg, Anna" is last name Berg;
a leading Frau/Herr/Mr/Ms/Mrs is the salutation (when the contact has none); otherwise the last word is the last
name and the particles in front of it stay with it. The remark becomes the position when that is empty.

The columns ``first_name`` and ``last_name`` hold 100 characters, ``name`` 200. A part that is longer (one word of
150 characters, "Anna " and 140 letters) does not fit: such a contact gets no first name and the first 100 characters
of its name as last name – the name shown is unchanged – instead of stopping the upgrade (MariaDB: error 1406).
"""

import re

from django.db import migrations

#: How many rows are written at once (20,000 contacts take a few seconds).
BATCH = 1000

#: The size of the columns.
PART_LENGTH = 100
NAME_LENGTH = 200
SALUTATION_LENGTH = 40
POSITION_LENGTH = 120

# --- The rule, frozen (a copy of customers.names) -----------------------------------------------------

_PARTICLES = frozenset(
    {
        "von", "vom", "van", "de", "den", "der", "zu", "zur", "zum", "ten", "ter", "da", "di", "du", "la", "le",
        "del", "della", "dos", "das", "af", "el", "al", "bin", "ibn", "y",
    }
)  # fmt: skip
_SALUTATION_WORDS = frozenset({"frau", "fr", "herr", "hr", "mr", "ms", "mrs", "miss"})
_SPACES = re.compile(r"\s+")
_PARENTHESES = re.compile(r"\([^)]*\)?")


def _tidy(text):
    return _SPACES.sub(" ", text or "").strip()


def _join(first_name, last_name):
    return " ".join(part for part in (_tidy(first_name), _tidy(last_name)) if part)


def _is_particle(word):
    return word.casefold() in _PARTICLES


def _parse(name):
    """(first name, last name, salutation, remark) of a whole name."""
    text = _PARENTHESES.sub(" ", name or "")
    segments = [part for part in (_tidy(segment) for segment in text.split(",")) if part]
    if not segments:
        return "", "", "", ""
    words = segments[0].split()
    salutation = ""
    if len(words) > 1 and words[0].rstrip(".").casefold() in _SALUTATION_WORDS:
        salutation = words.pop(0)
    rest = segments[1:]
    if rest and words and all(_is_particle(word) for word in words[:-1]):
        return rest[0], " ".join(words), salutation, ", ".join(rest[1:])
    start = len(words) - 1
    while start > 0 and _is_particle(words[start - 1]):
        start -= 1
    return " ".join(words[:start]), " ".join(words[start:]), salutation, ", ".join(rest)


def _split_for_columns(name):
    """The parts of a name as the columns take them; a part over 100 characters: no first name, the name's start."""
    first, last, salutation, remark = _parse(name)
    if len(first) > PART_LENGTH or len(last) > PART_LENGTH:
        return "", _tidy(name)[:PART_LENGTH], "", ""
    return first, last, salutation, remark


# --- The steps -----------------------------------------------------------------------------------------------


def split_names(apps, schema_editor):
    """Fill first_name and last_name of the contacts that have neither."""
    Contact = apps.get_model("customers", "Contact")
    fields = ["first_name", "last_name", "salutation", "position"]
    pending = []
    rows = (
        Contact.objects.filter(first_name="", last_name="")
        .exclude(name="")
        .only("pk", "name", "first_name", "last_name", "salutation", "position")
    )
    for contact in rows.iterator(chunk_size=BATCH):
        first, last, salutation, remark = _split_for_columns(contact.name)
        contact.first_name, contact.last_name = first, last
        if salutation and not contact.salutation:
            contact.salutation = salutation[:SALUTATION_LENGTH]
        if remark and not contact.position:
            contact.position = remark[:POSITION_LENGTH]
        pending.append(contact)
        if len(pending) >= BATCH:
            Contact.objects.bulk_update(pending, fields)
            pending = []
    if pending:
        Contact.objects.bulk_update(pending, fields)


def join_names(apps, schema_editor):
    """Set ``name`` from the parts where the name is empty or does not agree with them any more."""
    Contact = apps.get_model("customers", "Contact")
    pending = []
    rows = Contact.objects.exclude(first_name="", last_name="").only("pk", "name", "first_name", "last_name")
    for contact in rows.iterator(chunk_size=BATCH):
        first, last = _parse(contact.name)[:2]
        if (contact.first_name, contact.last_name) not in ((first, last), _split_for_columns(contact.name)[:2]) and (
            _join(contact.first_name, contact.last_name) != " ".join(contact.name.split())
        ):
            # Two parts of 100 characters and the space between them can be one character more than the name takes.
            contact.name = _join(contact.first_name, contact.last_name)[:NAME_LENGTH]
            pending.append(contact)
        if len(pending) >= BATCH:
            Contact.objects.bulk_update(pending, ["name"])
            pending = []
    if pending:
        Contact.objects.bulk_update(pending, ["name"])


class Migration(migrations.Migration):
    """Split the names of the existing contacts into first and last name (contacts; KND-011)."""

    dependencies = [("customers", "0008_contact_names_095")]

    operations = [migrations.RunPython(split_names, join_names)]
