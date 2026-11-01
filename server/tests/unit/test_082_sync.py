# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "sync": the offline sync with server versions (PCK-027), the list for the phone
that reads only (PCK-026), the read marks and change stamps of the chat (UIX-010) and the change polling (UIX-020).

The findings of the code review (numbered 25 to 29 in its list) each have a test here that fails
with the code:

* two future changes of one quantity in one sync – the later was refused as "older" (finding 25);
* ``packing.returned`` for a returned quantity that went down (finding 26);
* ``up_to`` beyond the newest message marked later messages as read (finding 27);
* two changes of a message within one second did not move the chat's stamp (finding 28);
* reading the list for the phone created packlists (finding 29).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import resolve

from rentalars.api.models import WebhookDelivery
from rentalars.chat import services as chat
from rentalars.chat.models import ChatMessage, ChatReadMark
from rentalars.core.changes import stamps, watch_keys
from rentalars.core.models import AuditAction, AuditLogEntry
from rentalars.packing import offline, services
from rentalars.packing.models import PackEntry, Packlist, SyncReceipt
from rentalars.projects import services as project_services
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import (
    ALL_RIGHTS,
    at,
    make_project,
    make_user,
    set_clock,
)
from tests.unit.test_060_webhooks import make_hook
from tests.unit.test_070_packing import PackingTestCase
from tests.unit.test_080_communication import ChatTestCase

D = Decimal


class SyncTestCase(PackingTestCase):
    """Ten cables and a rack on the packlist of a confirmed project; the clock stands on 9 March, 12:00."""

    def setUp(self) -> None:
        super().setUp()
        self.warehouse = make_user("luka", roles=("Lager",))
        set_clock(at(9, 12))

    def change(self, field: str, quantity: int, moment: datetime.datetime, **extra: Any) -> offline.Change:
        return offline.Change(self.cable_line.pk, self.cable.pk, field, D(quantity), moment, **extra)

    def sync(self, *changes: offline.Change, user: Any = None) -> list[offline.Result]:
        return offline.apply_changes(self.packlist, list(changes), user=user or self.warehouse)

    def entry(self) -> PackEntry:
        return PackEntry.objects.get(packlist=self.packlist, line=self.cable_line, product=self.cable)


class VersionTests(SyncTestCase):
    """PCK-027: every change of a ticked quantity counts the row's version up – web, API and sync."""

    def test_every_way_counts_once(self) -> None:
        self.tick(self.cable_line, 4)
        self.assertEqual(self.entry().version, 1)
        self.tick(self.cable_line, 4)  # the same quantity is no change
        self.assertEqual(self.entry().version, 1)
        set_clock(at(9, 12, 1))
        self.sync(self.change("packed", 6, at(9, 12, 1)))
        self.assertEqual(self.entry().version, 2)
        services.pack_all(self.packlist)
        self.assertEqual(self.entry().version, 3)
        services.issue(self.packlist, only_packed=True)  # issued only: no tick changes
        self.assertEqual(self.entry().version, 3)
        self.tick_back(self.cable_line, 2)
        self.assertEqual((self.entry().version, self.row().version), (4, 4))

    def test_the_snapshot_when_packing_starts_writes_no_quantity(self) -> None:
        """PCK-015/PCK-027: starting to pack notes text and quantity only – a stale quantity is not written back."""
        stale = services._entry_for(self.packlist, self.row())
        PackEntry.objects.filter(pk=stale.pk).update(packed_quantity=3, version=1)
        services._start_packing(self.packlist)
        self.assertEqual((self.entry().packed_quantity, self.entry().version), (3, 1))
        self.assertEqual(self.entry().required_snapshot, 10)


class BaseVersionTests(SyncTestCase):
    """PCK-027: with ``base_version`` the version decides; a conflict keeps the server's state."""

    def test_unchanged_since_the_phone_saw_it(self) -> None:
        self.tick(self.cable_line, 2)
        results = self.sync(self.change("packed", 5, at(9, 1), base_version=1))
        # The moment of the phone lies before the server's – with the version it does not matter.
        self.assertEqual(results[0].outcome, "applied")
        self.assertEqual((self.entry().packed_quantity, self.entry().version), (5, 2))
        self.assertEqual((results[0].version, results[0].server_quantity), (2, 5))
        # The stored moment never goes back.
        self.assertEqual(self.entry().packed_changed_at, at(9, 12))

    def test_a_conflict_keeps_the_server_and_says_what_it_has(self) -> None:
        self.tick(self.cable_line, 2)
        set_clock(at(9, 12, 5))
        self.tick(self.cable_line, 3)  # somebody in the browser – version 2
        results = self.sync(self.change("packed", 7, at(9, 12, 10), base_version=1))
        self.assertEqual(results[0].outcome, "conflict")
        self.assertEqual(results[0].message, "Inzwischen auf dem Server geändert; dort steht jetzt 3.")
        self.assertEqual(
            (results[0].version, results[0].server_quantity, results[0].server_changed_at), (2, 3, at(9, 12, 5))
        )
        self.assertEqual(self.entry().packed_quantity, 3)

    def test_what_the_server_has_already_is_no_conflict(self) -> None:
        self.tick(self.cable_line, 3)
        results = self.sync(self.change("packed", 3, at(9, 11), base_version=0))
        self.assertEqual((results[0].outcome, self.entry().version), ("applied", 1))

    def test_several_changes_of_one_sync_against_the_state_at_its_start(self) -> None:
        results = self.sync(
            self.change("packed", 4, at(9, 11, 30), base_version=0),
            self.change("packed", 6, at(9, 11), base_version=0),
        )
        self.assertEqual([result.outcome for result in results], ["applied", "applied"])
        self.assertEqual((self.entry().packed_quantity, self.entry().version), (4, 2))

    def test_a_row_without_entry_has_version_0(self) -> None:
        self.assertEqual(self.row().version, 0)
        self.assertEqual(self.sync(self.change("packed", 1, at(9, 11), base_version=0))[0].outcome, "applied")


class ClockRuleTests(SyncTestCase):
    """PCK-027: without ``base_version`` the moments decide – deterministic, also for future moments."""

    def test_future_moments_keep_their_order(self) -> None:
        """Finding 25: both lie in the future; the later one remains."""
        results = self.sync(self.change("packed", 8, at(9, 14)), self.change("packed", 5, at(9, 13)))
        self.assertEqual([result.outcome for result in results], ["applied", "applied"])
        self.assertEqual((self.entry().packed_quantity, self.entry().packed_changed_at), (8, at(9, 12)))

    def test_equal_moments_in_the_order_of_the_request(self) -> None:
        results = self.sync(self.change("packed", 2, at(9, 11)), self.change("packed", 9, at(9, 11)))
        self.assertEqual([result.outcome for result in results], ["applied", "applied"])
        self.assertEqual(self.entry().packed_quantity, 9)

    def test_an_older_change_never_overrides_a_newer_one(self) -> None:
        self.sync(self.change("packed", 8, at(9, 20)))  # in the future: counts as 12:00
        set_clock(at(9, 12, 1))
        results = self.sync(self.change("packed", 3, at(9, 11, 59)))
        self.assertEqual(results[0].outcome, "older")
        self.assertEqual(self.entry().packed_quantity, 8)
        # A server change after the clamped moment wins.
        set_clock(at(9, 12, 2))
        self.tick(self.cable_line, 1)
        self.assertEqual(self.entry().packed_quantity, 1)


class ChangeIdTests(SyncTestCase):
    """PCK-027: a change sent again with its ID gets the same outcome and is not judged again."""

    def test_a_replay_is_not_applied_twice(self) -> None:
        first = self.sync(self.change("packed", 5, at(9, 11), change_id="a1"))
        self.assertEqual((first[0].outcome, first[0].replayed), ("applied", False))
        set_clock(at(9, 12, 30))
        self.tick(self.cable_line, 2)  # the browser after the sync
        again = self.sync(self.change("packed", 5, at(9, 11), change_id="a1"))
        self.assertEqual((again[0].outcome, again[0].replayed), ("applied", True))
        self.assertEqual((self.entry().packed_quantity, again[0].server_quantity), (2, 2))
        self.assertEqual(SyncReceipt.objects.count(), 1)

    def test_the_ids_belong_to_one_user(self) -> None:
        self.sync(self.change("packed", 5, at(9, 11), change_id="a1"))
        other = make_user("pia", roles=("Lager",))
        results = self.sync(self.change("packed", 6, at(9, 11, 30), change_id="a1"), user=other)
        self.assertEqual((results[0].outcome, results[0].replayed, self.entry().packed_quantity), ("applied", False, 6))

    def test_an_id_for_another_change_is_refused(self) -> None:
        self.sync(self.change("packed", 5, at(9, 11), change_id="a1"))
        rack = offline.Change(self.rack_line.pk, self.rack_product.pk, "packed", D(1), at(9, 11), change_id="a1")
        results = self.sync(rack, self.change("returned", 1, at(9, 11), change_id="a1"))
        self.assertEqual([result.outcome for result in results], ["refused", "refused"])
        self.assertEqual(results[0].message, "Diese Änderungskennung gehört schon zu einer anderen Änderung.")

    def test_the_same_id_twice_in_one_sync(self) -> None:
        results = self.sync(
            self.change("packed", 5, at(9, 11), change_id="b"), self.change("packed", 5, at(9, 11), change_id="b")
        )
        self.assertEqual(
            [(result.outcome, result.replayed) for result in results], [("applied", False), ("applied", True)]
        )
        self.assertEqual(self.entry().version, 1)

    def test_a_reused_id_with_another_quantity_or_base_version_is_refused(self) -> None:
        """Review: the same row, another value – refused with a reason, never "applied, replayed"."""
        self.sync(self.change("packed", 5, at(9, 11), change_id="r"))
        results = self.sync(
            self.change("packed", 7, at(9, 11, 30), change_id="r"),
            self.change("packed", 5, at(9, 11), change_id="r", base_version=0),
        )
        self.assertEqual([(result.outcome, result.reason) for result in results], [("refused", "change_id_reused")] * 2)
        self.assertEqual((self.entry().packed_quantity, self.entry().version), (5, 1))
        # The very same change again: its outcome, also with the quantity written differently.
        again = self.sync(
            offline.Change(self.cable_line.pk, self.cable.pk, "packed", D("5.00"), at(9, 11), change_id="r")
        )
        self.assertEqual((again[0].outcome, again[0].replayed, again[0].reason), ("applied", True, ""))

    def test_a_reused_id_within_one_sync(self) -> None:
        results = self.sync(
            self.change("packed", 5, at(9, 11), change_id="s"), self.change("packed", 6, at(9, 11, 30), change_id="s")
        )
        self.assertEqual(
            [(result.outcome, result.reason) for result in results], [("applied", ""), ("refused", "change_id_reused")]
        )
        self.assertEqual(self.entry().packed_quantity, 5)

    def test_old_receipts_go(self) -> None:
        self.sync(self.change("packed", 5, at(9, 11), change_id="old"))
        set_clock(at(9, 12) + datetime.timedelta(days=offline.RECEIPT_DAYS + 1))
        self.sync()
        self.assertFalse(SyncReceipt.objects.exists())


class ReturnedWebhookTests(SyncTestCase):
    """Finding 26, API-012: ``packing.returned`` only when a returned quantity goes up – as in the browser."""

    def test_down_is_no_event(self) -> None:
        make_hook("packing.returned")
        self.tick(self.cable_line, 10)
        services.issue(self.packlist, only_packed=True)
        set_clock(at(11, 12))
        self.sync(self.change("returned", 6, at(11, 10)))
        self.assertEqual(WebhookDelivery.objects.filter(event="packing.returned").count(), 1)
        self.sync(self.change("returned", 4, at(11, 11)))  # a correction downwards
        self.assertEqual(WebhookDelivery.objects.filter(event="packing.returned").count(), 1)
        self.sync(self.change("returned", 4, at(11, 11, 30)))  # the same again
        self.assertEqual(WebhookDelivery.objects.filter(event="packing.returned").count(), 1)
        self.sync(self.change("returned", 5, at(11, 11, 40)))
        self.assertEqual(WebhookDelivery.objects.filter(event="packing.returned").count(), 2)


class ReadOnlyListTests(SyncTestCase):
    """Finding 29, PCK-026: reading the list for the phone creates nothing; confirming a project creates the packlist."""

    def test_reading_creates_nothing(self) -> None:
        bare = make_project("Ohne Packliste")
        Packlist.objects.filter(project=bare).delete()
        count = Packlist.objects.count()
        found = {entry.project.pk: entry for entry in offline.offline_projects(ALL_RIGHTS, None)}
        self.assertEqual(found[bare.pk].packlists, [])
        self.assertEqual(Packlist.objects.count(), count)

    def test_confirming_creates_the_main_packlist_once(self) -> None:
        option = make_project("Option", status=ProjectStatus.OPTION)
        self.assertFalse(option.packlists.exists())
        project_services.change_status(option, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.assertEqual(option.packlists.count(), 1)
        created = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Packlist), action=AuditAction.CREATED
        )
        self.assertTrue(created.filter(object_id=str(option.packlists.get().pk)).exists())
        option.refresh_from_db()
        option.name = "Option bestätigt"
        option.save()
        Project.objects.get(pk=option.pk).save()
        self.assertEqual(option.packlists.count(), 1)

    def test_created_confirmed(self) -> None:
        self.assertEqual(make_project("Gleich bestätigt").packlists.count(), 1)
        self.assertEqual(make_project("Anfrage", status=ProjectStatus.INQUIRY).packlists.count(), 0)


class PackingStampTests(SyncTestCase):
    """UIX-020: a packlist page follows the ticks of others – a tick writes no change log entry."""

    def test_the_key_and_its_stamp(self) -> None:
        request = RequestFactory().get(f"/projects/{self.project.number}/packlist/")
        request.resolver_match = resolve(request.path)
        self.assertIn(f"packing:{self.project.pk}", watch_keys(request))
        keys = [f"project:{self.project.pk}", f"packing:{self.project.pk}"]
        self.tick(self.cable_line, 2)
        before = stamps(keys, self.warehouse)
        set_clock(at(9, 12, 1))
        self.tick(self.cable_line, 3)  # status stays "in progress": nothing in the change log
        after = stamps(keys, self.warehouse)
        self.assertEqual(after[keys[0]], before[keys[0]])
        self.assertNotEqual(after[keys[1]], before[keys[1]])
        self.assertNotIn(".", after[keys[1]])  # not counted after the page's own change (PER-033)
        outsider = make_user("otto", roles=("Crew",))
        self.assertEqual(stamps(keys, outsider)[keys[1]], "")

    def test_other_project_pages_do_not_watch_the_ticks(self) -> None:
        request = RequestFactory().get(f"/projects/{self.project.number}/")
        request.resolver_match = resolve(request.path)
        self.assertNotIn(f"packing:{self.project.pk}", watch_keys(request))


# --- UIX-010: the chat ---------------------------------------------------------------------------------------


class ReadMarkTests(ChatTestCase):
    """Finding 27: ``up_to`` is taken down to the newest message of the chat; later messages stay unread."""

    def test_beyond_the_newest_message(self) -> None:
        first = chat.post_message(self.project, user=self.manager, text="Eins")
        self.assertEqual(chat.mark_read(self.project, self.crew_user, up_to=first.pk + 1000), first.pk)
        chat.post_message(self.project, user=self.manager, text="Zwei")
        self.assertEqual(chat.unread_count(self.project, self.crew_user), 1)

    def test_a_message_of_another_chat(self) -> None:
        other = make_project("Anderes Fest")
        first = chat.post_message(self.project, user=self.manager, text="Eins")
        elsewhere = chat.post_message(other, user=self.manager, text="Woanders")
        self.assertEqual(chat.mark_read(self.project, self.crew_user, up_to=elsewhere.pk), first.pk)
        self.assertEqual(ChatReadMark.objects.get(user=self.crew_user, project=self.project).last_read_id, first.pk)
        chat.post_message(self.project, user=self.manager, text="Zwei")
        self.assertEqual(chat.unread_count(self.project, self.crew_user), 1)

    def test_an_empty_chat(self) -> None:
        self.assertEqual(chat.mark_read(self.project, self.crew_user, up_to=99), 0)
        chat.post_message(self.project, user=self.manager, text="Eins")
        self.assertEqual(chat.unread_count(self.project, self.crew_user), 1)


class ChatStampTests(ChatTestCase):
    """Finding 28: the stamp counts changes – two within one second, and a change of an older message, move it."""

    def test_two_changes_within_one_second(self) -> None:
        message = chat.post_message(self.project, user=self.manager, text="Eins")
        set_clock(at(1, 8, 5))
        chat.edit_message(message, user=self.manager, text="Eins!")
        first = chat.stamp(self.project.pk, self.crew_user)
        chat.edit_message(message, user=self.manager, text="Eins!!")  # the clock stands: the same second
        self.assertNotEqual(chat.stamp(self.project.pk, self.crew_user), first)
        self.assertEqual(ChatMessage.objects.get(pk=message.pk).revision, 2)

    def test_a_change_of_an_older_message(self) -> None:
        older = chat.post_message(self.project, user=self.manager, text="Eins")
        newer = chat.post_message(self.project, user=self.manager, text="Zwei")
        set_clock(at(1, 8, 6))
        chat.edit_message(newer, user=self.manager, text="Zwei!")
        first = chat.stamp(self.project.pk, self.crew_user)
        set_clock(at(1, 8, 5))  # a clock that went back a little
        chat.edit_message(older, user=self.manager, text="Eins!")
        self.assertNotEqual(chat.stamp(self.project.pk, self.crew_user), first)

    def test_new_and_deleted_messages(self) -> None:
        self.assertEqual(chat.stamp(self.project.pk, self.crew_user), "0-0-0~0")
        message = chat.post_message(self.project, user=self.manager, text="Eins")
        self.assertEqual(chat.stamp(self.project.pk, self.crew_user), f"{message.pk}-1-0~1")
        chat.delete_message(message, user=self.manager)
        self.assertEqual(chat.stamp(self.project.pk, self.crew_user), "0-0-0~0")


# --- The data migrations ----------------------------------------------------------------------------------------
