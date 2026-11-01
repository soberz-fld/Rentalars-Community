# SPDX-License-Identifier: GPL-3.0-or-later
"""Ten people record their times at the same moment: the measurement for NFA-051.

After a job the whole crew writes down its hours within a few minutes. The
catalogue wants the reference system to stay usable then, with up to ten
people at once. :func:`measure_concurrent_recording` plays exactly that
against the *running* server – through NGINX and HTTPS, the way phones do –
and reports how long the answers took.

What happens
------------
1. Test accounts are created: ten people with a user account and an API
   token each, and an internal project to book on.
2. All of them start at the same moment. Each one records a time, then
   reads their own times, several rounds in a row, without any pause – more
   impatient than any crew.
3. Everything that was created is removed again. Only the change log keeps
   the traces, under names that begin with ``lasttest-``.

The command ``measure_concurrency`` calls this function and prints the
result (see ``docs/betrieb/betrieb.md``).
"""

from __future__ import annotations

import datetime
import json
import ssl
import statistics
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from rentalars.accounts.models import ApiToken, Role, User
from rentalars.core.audit import acting_as
from rentalars.personnel.models import JobFunction, Person
from rentalars.personnel.services import set_rate
from rentalars.projects.models import Project, ProjectStatus
from rentalars.projects.services import create_project
from rentalars.timetracking.models import TimeEntry

#: Names of everything the measurement creates begin with this, so that it can be found and removed.
PREFIX = "lasttest-zeit"

#: An answer slower than this, with ten people at once, no longer counts as "usable" (NFA-051).
LIMIT_SECONDS = 2.0


@dataclass
class ConcurrencyResult:
    """What the measurement found."""

    users: int
    rounds: int
    #: Seconds per answer, by step: "record" and "read".
    seconds: dict[str, list[float]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    entries_saved: int = 0
    total_seconds: float = 0.0

    @property
    def entries_expected(self) -> int:
        """Every user records one entry per round."""
        return self.users * self.rounds

    def slowest(self, step: str) -> float:
        """The longest answer of a step."""
        return max(self.seconds.get(step) or [0.0])

    def median(self, step: str) -> float:
        """The middle answer of a step."""
        values = self.seconds.get(step) or [0.0]
        return statistics.median(values)

    @property
    def ok(self) -> bool:
        """No error, nothing lost, and every answer within the limit."""
        return (
            not self.errors
            and self.entries_saved == self.entries_expected
            and all(self.slowest(step) < LIMIT_SECONDS for step in self.seconds)
        )


def _prepare(users: int) -> tuple[Project, JobFunction, list[str]]:
    """Create the internal project, the people with their accounts, and a token for each."""
    remove_test_data()
    with acting_as("system:measure_concurrency"), transaction.atomic():
        now = timezone.now()
        project = create_project(
            name=f"{PREFIX} Lager",
            is_internal=True,
            status=ProjectStatus.CONFIRMED,
            start=now - datetime.timedelta(days=30),
            end=now + datetime.timedelta(days=30),
        )
        job_function = JobFunction.objects.get_or_create(name="Lager")[0]
        crew_role = Role.objects.filter(name="Crew").first()
        keys = []
        for number in range(1, users + 1):
            user = User.objects.create_user(f"{PREFIX}-{number}", f"{PREFIX}-{number}@example.invalid", None)
            if crew_role is not None:
                user.roles.add(crew_role)
            # The account brings its person (AUT-026); it gets the name of the measurement.
            person = user.person
            person.first_name, person.last_name = "Lasttest", f"{PREFIX}-{number}"
            person.full_clean()
            person.save()
            set_rate(person, job_function, Decimal("20.00"), datetime.date(2020, 1, 1))
            _token, key = ApiToken.create_for_user(user, PREFIX)
            keys.append(key)
    return project, job_function, keys


def remove_test_data() -> None:
    """Remove everything an earlier measurement left behind, e.g. after it was interrupted."""
    with acting_as("system:measure_concurrency"), transaction.atomic():
        TimeEntry.objects.filter(person__last_name__startswith=PREFIX).delete()
        Person.objects.filter(last_name__startswith=PREFIX).delete()
        User.objects.filter(username__startswith=PREFIX).delete()
        Project.objects.filter(name__startswith=PREFIX, is_internal=True).delete()


def _opener(verify_tls: bool) -> urllib.request.OpenerDirector:
    """An HTTP client that talks to the server directly, never through a proxy of the machine."""
    context = ssl.create_default_context()
    if not verify_tls:
        # For a test installation with a self-signed certificate; chosen by the caller with --insecure.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))


def measure_concurrent_recording(
    base_url: str, *, users: int = 10, rounds: int = 5, verify_tls: bool = True
) -> ConcurrencyResult:
    """Let ``users`` people record and read times at the same moment; see the module description.

    Args:
        base_url: Address of the running installation, e.g. ``https://rentalars.example.de``.
        users: How many people work at once.
        rounds: How many times each of them records and reads.
        verify_tls: Check the certificate of the server.

    Returns:
        The timings, the errors, and whether every entry arrived.
    """
    base_url = base_url.rstrip("/")
    project, job_function, keys = _prepare(users)
    result = ConcurrencyResult(users=users, rounds=rounds, seconds={"record": [], "read": []})
    lock = threading.Lock()
    start_together = threading.Barrier(users)
    day = timezone.localtime().replace(hour=6, minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)

    def call(opener: Any, key: str, path: str, body: dict[str, Any] | None = None) -> float:
        request = urllib.request.Request(  # noqa: S310 - the address is given by the administrator
            base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        started = time.perf_counter()
        with opener.open(request, timeout=60) as response:
            response.read()
        return time.perf_counter() - started

    def work(key: str) -> None:
        opener = _opener(verify_tls)
        try:
            start_together.wait(timeout=30)
            for round_number in range(rounds):
                start = day + datetime.timedelta(hours=round_number)
                body = {
                    "project": project.pk,
                    "job_function": job_function.pk,
                    "start": start.isoformat(),
                    "end": (start + datetime.timedelta(minutes=45)).isoformat(),
                    "submit": True,
                }
                recorded = call(opener, key, "/api/v1/time-entries", body)
                read = call(opener, key, "/api/v1/time-entries?page_size=50")
                with lock:
                    result.seconds["record"].append(recorded)
                    result.seconds["read"].append(read)
        except urllib.error.HTTPError as error:
            with lock:
                result.errors.append(f"HTTP {error.code}: {error.read()[:200].decode(errors='replace')}")
        except Exception as error:  # a broken connection is a finding, not a crash of the measurement
            with lock:
                result.errors.append(f"{type(error).__name__}: {error}")

    threads = [threading.Thread(target=work, args=(key,)) for key in keys]
    started = time.perf_counter()
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=300)
        result.total_seconds = time.perf_counter() - started
        result.entries_saved = TimeEntry.objects.filter(project=project).count()
    finally:
        remove_test_data()
    return result
