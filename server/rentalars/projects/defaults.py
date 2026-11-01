# SPDX-License-Identifier: GPL-3.0-or-later
"""Start data of the projects module: the project template "Dry Hire" (PRJ-095).

Dry hire is renting without our crew: the customer picks the material up at
the warehouse and brings it back. Such a project is planned like any other
– material lines, availability, offer, packlist, delivery note – it only has
no crew and no transport. The template gives it the phases of such a rental:

* **Packen** – the material is put together and set aside for the pick-up,
  from the start of the rental period;
* **Übergabe an den Kunden (Abholung)** – the customer picks it up;
* **Rücknahme** – the customer brings it back, shortly before the end of the
  rental period;
* **Nachbereitung** – unpacking, checking what came back, putting it away,
  until the end.

The first two count from the start of the project, the last two from its end
(``"anchor": "end"``, see ``project_templates._period``), so that they fit a
rental of any length; a very short rental cuts them to its period. The template
has no groups, no lines and no crew places: the material differs from rental
to rental. Its note goes into the notes of a new project and says that the
customer picks up and brings back – the project has no field of its own for
that, and the delivery address stays as the customer's data say.

New installations get the template with the first-run setup
(``core.setup.complete_setup``). It does not overwrite or duplicate a template of the
same name (case ignored), and it runs only once: a template the
company deleted stays deleted.
"""

from __future__ import annotations

import copy
from typing import Any

from rentalars.projects.models import ProjectTemplate

#: The name of the template, in the language of the user interface.
DRY_HIRE_NAME = "Dry Hire (Vermietung ohne Personal)"

#: What the list of templates says about it.
DRY_HIRE_DESCRIPTION = (
    "Vermietung ohne unser Personal: Der Kunde holt das Material im Lager ab und bringt es selbst zurück. "
    "Mit den Phasen Packen, Übergabe an den Kunden, Rücknahme und Nachbereitung – ohne Personal und ohne "
    "Positionen; das Material planst du wie gewohnt."
)

_HOUR = 3600

#: The content in the format of ``project_templates.capture`` (version 2), times in seconds.
_DRY_HIRE_CONTENT: dict[str, Any] = {
    "version": 2,
    "length_seconds": 24 * _HOUR,
    "notes": "Dry Hire: Der Kunde holt das Material im Lager ab und bringt es zurück – ohne Personal und ohne "
    "Transport von uns.",
    "rental_days": None,
    "groups": [],
    "lines": [],
    "crew": [],
    "phases": [
        {
            "kind": "loading",
            "title": "",
            "location": "Lager",
            "notes": "Material zusammenstellen, prüfen und für die Abholung bereitstellen.",
            "venue_site": None,
            "own_period": True,
            "start": 0,
            "end": 2 * _HOUR,
        },
        {
            "kind": "other",
            "title": "Übergabe an den Kunden (Abholung)",
            "location": "Lager",
            "notes": "Material mit dem Kunden durchgehen, Lieferschein unterschreiben lassen.",
            "venue_site": None,
            "own_period": True,
            "start": 2 * _HOUR,
            "end": 3 * _HOUR,
        },
        {
            "kind": "return",
            "title": "Rücknahme",
            "location": "Lager",
            "notes": "Der Kunde bringt das Material zurück: Vollständigkeit prüfen, Schäden notieren.",
            "venue_site": None,
            "own_period": True,
            "anchor": "end",
            "start": -3 * _HOUR,
            "end": -2 * _HOUR,
        },
        {
            "kind": "aftercare",
            "title": "",
            "location": "Lager",
            "notes": "Auspacken, Eingangskontrolle, einlagern.",
            "venue_site": None,
            "own_period": True,
            "anchor": "end",
            "start": -2 * _HOUR,
            "end": 0,
        },
    ],
    "open_items": [],
}


def dry_hire_content() -> dict[str, Any]:
    """A fresh copy of the content of the template "Dry Hire" (PRJ-095)."""
    return copy.deepcopy(_DRY_HIRE_CONTENT)


def install_dry_hire_template() -> ProjectTemplate | None:
    """Create the template "Dry Hire" unless a template of that name exists (PRJ-095).

    Returns:
        The new template, or ``None`` if one of that name was there already;
        that one is left as it is.
    """
    if ProjectTemplate.objects.filter(name__iexact=DRY_HIRE_NAME).exists():
        return None
    template = ProjectTemplate(name=DRY_HIRE_NAME, description=DRY_HIRE_DESCRIPTION, content=dry_hire_content())
    template.full_clean()
    template.save()
    return template
