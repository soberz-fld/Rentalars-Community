# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "mail-maps".

* EML-049: mails without project tag are taken in only from a point in time – set when the handling is switched on,
  changeable – and optionally only unread ones; per mailbox and per further address. Tagged mails, replies and
  inquiries taken in before are not affected. The update sets the point to its own moment.
* UIX-033: every route link starts where the viewer is (no ``origin``); trips keep their stops.
* UIX-034: the map pictures carry the origin of the installation as referrer (tile usage policy of OpenStreetMap);
  the geocoder is asked with a User-Agent that names the installation.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from rentalars.core import geocoding, maps
from rentalars.core.models import AuditLogEntry, CompanyProfile
from rentalars.mail.aliases import save_address, stamp_untagged_since, untagged_skip
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.imap import ImapMailbox, parse_internaldate
from rentalars.mail.mailboxes import save_mailbox
from rentalars.mail.models import (
    LogResult,
    Mailbox,
    MailboxAddress,
    MailLogEntry,
    ProjectMail,
    UnknownTagMail,
    Untagged,
)
from rentalars.projects.models import PhaseKind, ProjectPhase
from rentalars.projects.trips import trips_of
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import NOW, RentalarsTestCase, make_project
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes, make_mail

UTC = datetime.UTC
HOUR = datetime.timedelta(hours=1)


def received(minutes: int) -> datetime.datetime:
    """A moment relative to the stopped clock of the tests."""
    return NOW + datetime.timedelta(minutes=minutes)


# --- EML-049: the rule -----------------------------------------------------------------------------------------


class UntaggedSkipTests(SimpleTestCase):
    """EML-049: before the point in time, read although only unread ones count – or take it in."""

    def holder(self, since: datetime.datetime | None = None, unread_only: bool = False) -> Any:
        return SimpleNamespace(untagged_since=since, untagged_unread_only=unread_only)

    def test_before_and_after_the_point(self) -> None:
        """EML-049: a mail that arrived before the point stays; one at or after it is taken in."""
        since = datetime.datetime(2027, 3, 1, 8, tzinfo=UTC)
        self.assertEqual(untagged_skip(self.holder(since), received=since - HOUR, seen=False), "before_cutoff")
        self.assertEqual(untagged_skip(self.holder(since), received=since, seen=False), "")
        self.assertEqual(untagged_skip(self.holder(since), received=since + HOUR, seen=True), "")

    def test_no_date_stays_untouched(self) -> None:
        """EML-049: a mail without any date cannot be placed – it stays in the inbox."""
        since = datetime.datetime(2027, 3, 1, 8, tzinfo=UTC)
        self.assertEqual(untagged_skip(self.holder(since), received=None, seen=False), "before_cutoff")
        self.assertEqual(untagged_skip(self.holder(None), received=None, seen=False), "")

    def test_only_unread(self) -> None:
        """EML-049: with "only unread mails" a read mail stays; an unread one is taken in."""
        self.assertEqual(untagged_skip(self.holder(None, True), received=None, seen=True), "read")
        self.assertEqual(untagged_skip(self.holder(None, True), received=None, seen=False), "")
        self.assertEqual(untagged_skip(self.holder(None, False), received=None, seen=True), "")


class StampTests(SimpleTestCase):
    """EML-049: the point in time follows the switch."""

    def test_switching_on_sets_now_and_a_given_moment_stays(self) -> None:
        moment = datetime.datetime(2027, 3, 1, 8, tzinfo=UTC)
        box = Mailbox(process_untagged=True)
        stamp_untagged_since(box, now=moment)
        self.assertEqual(box.untagged_since, moment)
        given = moment - datetime.timedelta(days=7)
        box.untagged_since = given
        stamp_untagged_since(box, now=moment)
        self.assertEqual(box.untagged_since, given)

    def test_switching_off_empties_it(self) -> None:
        box = Mailbox(process_untagged=False, untagged_since=datetime.datetime(2027, 3, 1, tzinfo=UTC))
        stamp_untagged_since(box)
        self.assertIsNone(box.untagged_since)
        alias = MailboxAddress(untagged=Untagged.IGNORE, untagged_since=datetime.datetime(2027, 3, 1, tzinfo=UTC))
        stamp_untagged_since(alias)
        self.assertIsNone(alias.untagged_since)
        alias.untagged = Untagged.SERVICE_CASE
        stamp_untagged_since(alias, now=datetime.datetime(2027, 3, 2, tzinfo=UTC))
        self.assertEqual(alias.untagged_since, datetime.datetime(2027, 3, 2, tzinfo=UTC))


class InternalDateTests(SimpleTestCase):
    """EML-049: the moment a mail arrived, as the IMAP server tells it."""

    def test_formats(self) -> None:
        self.assertEqual(
            parse_internaldate(b"17-Jul-1996 02:44:25 -0700"), datetime.datetime(1996, 7, 17, 9, 44, 25, tzinfo=UTC)
        )
        self.assertEqual(
            parse_internaldate(" 1-Mar-2027 08:00:00 +0100"), datetime.datetime(2027, 3, 1, 7, 0, tzinfo=UTC)
        )
        self.assertIsNone(parse_internaldate("gestern"))
        self.assertIsNone(parse_internaldate("31-Feb-2027 08:00:00 +0000"))
        self.assertIsNone(parse_internaldate("01-Mrz-2027 08:00:00 +0000"))

    def test_headers_bring_flags_and_arrival(self) -> None:
        """EML-049: the header fetch asks for FLAGS and INTERNALDATE and keeps "read" and the arrival."""
        imap = mock.Mock()
        header = b"Subject: Frage\r\n\r\n"
        imap.uid.side_effect = [
            ("OK", [b"5 6"]),
            (
                "OK",
                [
                    (
                        b'5 (UID 5 RFC822.SIZE 99 FLAGS (\\Seen) INTERNALDATE "01-Mar-2027 09:00:00 +0100" BODY[...] {18}',
                        header,
                    ),
                    b")",
                    (
                        b'6 (UID 6 RFC822.SIZE 99 FLAGS () INTERNALDATE "02-Mar-2027 09:00:00 +0100" BODY[...] {18}',
                        header,
                    ),
                    b")",
                ],
            ),
        ]
        box = ImapMailbox(SimpleNamespace())
        box.imap = imap
        infos = box.headers_after(4)
        self.assertIn("INTERNALDATE", imap.uid.call_args_list[1].args[2])
        self.assertEqual([(info.uid, info.seen) for info in infos], [(5, True), (6, False)])
        self.assertEqual(infos[0].received, datetime.datetime(2027, 3, 1, 8, tzinfo=UTC))


# --- EML-049: the fetch -----------------------------------------------------------------------------------------


class FetchFromAPointInTimeTests(RentalarsTestCase):
    """EML-049: old mails without tag stay in the inbox; tagged mails are assigned as always."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True, untagged_since=NOW)
        self.project = make_project()

    def fetch(self, fake: FakeMailbox) -> None:
        with mailboxes({self.box.address: fake}):
            fetch_mail(force=True)

    def test_old_mails_stay_new_ones_come_in(self) -> None:
        fake = FakeMailbox()
        fake.add(make_mail("Alte Anfrage", message_id="<old@x>"), received=received(-60 * 24 * 400))
        fake.add(make_mail("Neue Anfrage", message_id="<new@x>"), received=received(5))
        fake.add(make_mail(f"[RL#{self.project.number}] Alte Antwort", message_id="<tag@x>"), received=received(-600))
        self.fetch(fake)
        self.assertEqual(list(UnknownTagMail.objects.values_list("subject", flat=True)), ["Neue Anfrage"])
        self.assertTrue(ProjectMail.objects.filter(project=self.project, subject__endswith="Alte Antwort").exists())
        left = MailLogEntry.objects.get(subject="Alte Anfrage")
        self.assertEqual((left.result, left.detail), (LogResult.LEFT_IN_INBOX, "before_cutoff"))
        self.assertIn("vor dem Zeitpunkt", left.detail_text)
        self.assertEqual(len(fake.inbox), 2)  # the old inquiry and the new one stay in the inbox; tagged moved

    def test_the_date_header_counts_without_internaldate(self) -> None:
        """EML-049: without INTERNALDATE (a fake mailbox) the Date header of the mail decides."""
        old = make_mail("Alt", date=datetime.datetime(2026, 1, 5, 9, tzinfo=UTC))
        new = make_mail("Neu", date=NOW + HOUR)
        self.fetch(FakeMailbox(old, new))
        self.assertEqual(list(UnknownTagMail.objects.values_list("subject", flat=True)), ["Neu"])

    def test_only_unread(self) -> None:
        self.box.untagged_unread_only = True
        self.box.save()
        fake = FakeMailbox()
        fake.add(make_mail("Gelesen"), seen=True, received=received(5))
        fake.add(make_mail("Ungelesen"), received=received(6))
        fake.add(make_mail(f"[RL#{self.project.number}] Gelesen mit Kennung"), seen=True, received=received(7))
        self.fetch(fake)
        self.assertEqual(list(UnknownTagMail.objects.values_list("subject", flat=True)), ["Ungelesen"])
        self.assertEqual(MailLogEntry.objects.get(subject="Gelesen").detail, "read")
        self.assertEqual(ProjectMail.objects.filter(project=self.project).count(), 1)

    def test_an_address_has_its_own_point(self) -> None:
        """EML-049: a further address decides by its own point in time and its own "only unread"."""
        support = MailboxAddress(
            mailbox=self.box,
            address="support@verleih.example",
            untagged=Untagged.INQUIRY,
            untagged_since=NOW - datetime.timedelta(days=30),
        )
        save_address(support)
        fake = FakeMailbox()
        fake.add(make_mail("An Support", to="support@verleih.example"), received=received(-60 * 24 * 7))
        fake.add(make_mail("An Projekte"), received=received(-60 * 24 * 7))
        self.fetch(fake)
        self.assertEqual(list(UnknownTagMail.objects.values_list("subject", flat=True)), ["An Support"])
        self.assertEqual(MailLogEntry.objects.get(subject="An Projekte").detail, "before_cutoff")

    def test_inquiries_taken_in_before_stay(self) -> None:
        self.fetch(FakeMailbox(make_mail("Schon da", date=NOW + HOUR)))
        self.box.untagged_since = NOW + 2 * HOUR
        save_mailbox(self.box)
        self.fetch(FakeMailbox(make_mail("Später", date=NOW + HOUR)))
        self.assertEqual(list(UnknownTagMail.objects.values_list("subject", flat=True)), ["Schon da"])


class SaveTests(RentalarsTestCase):
    """EML-049: switching on through the services sets the point; it is in the change log."""

    def test_mailbox(self) -> None:
        box = configure_mailbox(process_untagged=False)
        self.assertIsNone(box.untagged_since)
        box.process_untagged = True
        save_mailbox(box)
        box.refresh_from_db()
        self.assertEqual(box.untagged_since, timezone.now())
        entry = AuditLogEntry.objects.filter(object_id=str(box.pk), changes__has_key="untagged_since").first()
        self.assertIsNotNone(entry)
        box.process_untagged = False
        save_mailbox(box)
        box.refresh_from_db()
        self.assertIsNone(box.untagged_since)

    def test_address(self) -> None:
        box = configure_mailbox(process_untagged=False)
        alias = MailboxAddress(mailbox=box, address="info@verleih.example", untagged=Untagged.IGNORE)
        save_address(alias)
        self.assertIsNone(alias.untagged_since)
        alias.untagged = Untagged.INQUIRY
        save_address(alias)
        self.assertEqual(MailboxAddress.objects.get().untagged_since, timezone.now())


# --- UIX-033: routes from where the viewer is ------------------------------------------------------------------


class RouteFromHereTests(RentalarsTestCase):
    """UIX-033: no route link names a start; trips keep their stops."""

    def test_route_url_has_no_origin(self) -> None:
        url = maps.route_url("Hallenweg 3, Musterstadt", waypoints=["Nordweg 1", "Südring 2"])
        self.assertEqual(
            parse_qs(urlsplit(url).query),
            {"api": ["1"], "destination": ["Hallenweg 3, Musterstadt"], "waypoints": ["Nordweg 1|Südring 2"]},
        )
        with self.assertRaises(TypeError):
            maps.route_url("Ziel", origin="Lager")  # type: ignore[call-arg]

    def test_the_template_tag(self) -> None:
        html = Template('{% load maps %}{% route_link "Hallenweg 3" %}').render(Context())
        self.assertIn('href="https://www.google.com/maps/dir/?api=1&amp;destination=Hallenweg%203"', html)

    def test_trips_start_where_the_viewer_is(self) -> None:
        profile = CompanyProfile.load()
        profile.warehouse_address = "Industriestraße 5, Musterstadt"
        profile.save()
        project = make_project(venue="Hallenweg 3, Musterstadt")
        ProjectPhase.objects.create(project=project, kind=PhaseKind.SETUP, start=NOW, end=NOW + HOUR, title="Aufbau")
        trips = trips_of(project)
        self.assertTrue(trips)
        for trip in trips:
            query = parse_qs(urlsplit(trip.route_url).query)
            self.assertNotIn("origin", query)
        self.assertEqual(trips[0].origin.address, "Industriestraße 5, Musterstadt")  # the trip still says where


# --- UIX-034: the tile usage policy -------------------------------------------------------------------------------


class TilePolicyTests(RentalarsTestCase):
    """UIX-034: the map pictures carry the origin of the installation; the geocoder knows who asks."""

    def test_the_map_data_name_the_referrer_policy(self) -> None:
        page = maps.MapPage(target="company", pk=1, title="Firma", record=CompanyProfile.load(), places=[])
        self.assertEqual(maps.map_data(page)["referrerPolicy"], "strict-origin-when-cross-origin")

    def test_the_tile_layer_uses_it(self) -> None:
        script = (Path(settings.SOURCE_DIR) / "static" / "js" / "app.js").read_text(encoding="utf-8")
        layer = script[script.index("L.tileLayer(data.tiles") :][:900]
        self.assertIn('referrerPolicy: data.referrerPolicy || "strict-origin-when-cross-origin"', layer)

    @override_settings(RENTALARS_URL="https://user:secret@verleih.example:8443/rentalars/")
    def test_user_agent_names_the_installation(self) -> None:
        self.assertEqual(geocoding.user_agent(), f"Rentalars/{_version()} (maps; +https://verleih.example:8443)")
        with FakeGeocoder({"Hallenweg 3": ("52.1", "13.2")}) as geocoder:
            geocoding.look_up("Hallenweg 3")
        self.assertEqual(geocoder.headers["User-Agent"], geocoding.user_agent())

    @override_settings(RENTALARS_URL="")
    def test_user_agent_without_an_address(self) -> None:
        self.assertEqual(geocoding.user_agent(), geocoding.USER_AGENT)


def _version() -> str:
    from rentalars import __version__

    return __version__
