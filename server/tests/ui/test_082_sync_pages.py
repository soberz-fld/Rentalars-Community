# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "sync": the packlist page follows the ticks of others (UIX-020, PCK-027), and the chat's
list of messages carries a stamp that moves with every change (UIX-010).
"""

from __future__ import annotations

from decimal import Decimal

from rentalars.chat import services as chat
from rentalars.packing import offline, services
from tests.helpers import add_line, at, make_person, make_project, make_stock, make_user, plan
from tests.ui.base import UiTestCase


class PacklistFollowsTicksPageTests(UiTestCase):
    """UIX-020: what a colleague or the app ticks reloads an open packlist page."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.cable = make_stock("K-005", 12, "XLR-Kabel 5 m")
        self.line = add_line(self.project, self.cable, 10).line
        self.packlist = services.get_packlist(self.project)
        self.key = f"packing:{self.project.pk}"

    def stamp(self) -> str:
        answer = self.client.get("/changes/", {"keys": f"project:{self.project.pk},{self.key}"})
        self.assertEqual(answer.status_code, 200)
        return answer.json()["stamps"][self.key]

    def test_the_packlist_page_watches_the_ticks(self) -> None:
        text = self.assert_ok(self.client.get(f"/projects/{self.project.number}/packlist/"))
        self.assertIn(f"chat:{self.project.pk},{self.key}", text)
        text = self.assert_ok(self.client.get(f"/projects/{self.project.number}/"))
        self.assertNotIn(self.key, text)

    def test_a_tick_from_the_app_moves_the_stamp(self) -> None:
        services.set_packed(self.packlist, self.line.pk, self.cable.pk, Decimal(2))
        before = self.stamp()
        luka = make_user("luka", roles=("Lager",))
        change = offline.Change(self.line.pk, self.cable.pk, "packed", Decimal(5), at(1, 7), base_version=1)
        offline.apply_changes(self.packlist, [change], user=luka)
        self.assertNotEqual(self.stamp(), before)


class ChatStampPageTests(UiTestCase):
    """UIX-010: the list of messages shows the state it shows – changed twice in a second, it differs."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.crew_user = make_user("anna", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Anna Becker", user=self.crew_user))
        self.url = f"/projects/{self.project.number}/chat/messages/"

    def shown_stamp(self) -> str:
        text = self.assert_ok(self.client.get(self.url))
        return text.split('data-stamp="', 1)[1].split('"', 1)[0]

    def test_two_changes_within_one_second(self) -> None:
        message = chat.post_message(self.project, user=self.crew_user, text="Bin um 8 da")
        chat.edit_message(message, user=self.crew_user, text="Bin um 9 da")
        first = self.shown_stamp()
        self.assertEqual(first, f"{message.pk}-1-1")
        chat.edit_message(message, user=self.crew_user, text="Bin um 10 da")  # the clock stands
        self.assertEqual(self.shown_stamp(), f"{message.pk}-1-2")
        self.assertIn("Bin um 10 da", self.assert_ok(self.client.get(self.url)))
