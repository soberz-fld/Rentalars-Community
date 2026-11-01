# SPDX-License-Identifier: GPL-3.0-or-later
"""Start data for personnel: the job functions with their service products (PER-037, PRD-044).

The requirement: a default set of job functions (Techniker,
Lichttechniker, Tontechniker, Medientechniker, Stagehand, Lager,
Projektplanung, Sonstiges). Each comes with its service product of the same
name in the category of services (D), by the hour, without price yet – the
price is entered on the product, or when the function is edited.
"""

from __future__ import annotations

from rentalars.personnel.models import JobFunction
from rentalars.personnel.services import save_job_function

#: PER-037: the job functions of a new installation, in this order.
JOB_FUNCTIONS = [
    "Techniker",
    "Lichttechniker",
    "Tontechniker",
    "Medientechniker",
    "Stagehand",
    "Lager",
    "Projektplanung",
    "Sonstiges",
]


def install() -> None:
    """Create the job functions of the start data with their service products, unless there are functions."""
    if JobFunction.objects.exists():
        return
    for name in JOB_FUNCTIONS:
        save_job_function(JobFunction(name=name))
