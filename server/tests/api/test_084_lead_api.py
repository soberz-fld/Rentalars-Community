# SPDX-License-Identifier: GPL-3.0-or-later
"""API settled while the areas were put together.

PCK-027 with the Crew rule: a refused change sent again with the same
change ID gets the outcome of the first time – now with its reason code too,
so the phone can say "needs the right to change the project" after a lost answer.
"""

from __future__ import annotations

from tests.api.test_070_packing_api import PacklistApiTestCase
from tests.api.test_084_fixes_api import COMPANION_MODULES
from tests.helpers import at, job_function, make_person, make_user, plan, set_clock


class SyncReplayReasonApiTests(PacklistApiTestCase):
    """A change sent again keeps its reason code (``needs_project_write``)."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(at(9, 12))
        lea = make_user("lea", roles=("Crew",))
        plan(self.project, job_function("Stagehand"), make_person("Lea Vogel", user=lea))
        self.crew = self.client_of(lea, allowed_modules=COMPANION_MODULES)  # the token of the companion app

    def result(self, *changes: dict) -> list[tuple[str, str, bool]]:
        answer = self.sync(*changes, client=self.crew)
        self.assertEqual(answer.status_code, 200, answer.content)
        return [(r["outcome"], r["reason"], r["replayed"]) for r in answer.json()["results"]]

    def test_a_refused_change_sent_again_keeps_its_reason(self) -> None:
        change = dict(self.change("packed", "11", "2027-03-09T11:00:00+01:00"), change_id="lea-1")
        self.assertEqual(self.result(change), [("refused", "needs_project_write", False)])
        self.assertEqual(self.result(change), [("refused", "needs_project_write", True)])

    def test_twice_in_one_sync_both_carry_the_reason(self) -> None:
        change = dict(self.change("packed", "11", "2027-03-09T11:00:00+01:00"), change_id="lea-2")
        self.assertEqual(
            self.result(change, change),
            [("refused", "needs_project_write", False), ("refused", "needs_project_write", True)],
        )
