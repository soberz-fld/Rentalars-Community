# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "mail-maps".

* EML-049: "Mails ohne Projektkennung übernehmen" with "übernehmen ab" and "nur ungelesene Mails" – in the form of a
  mailbox and of a further address, in the list of mailboxes, and the reason in the mail log.
* UIX-033: the route links of the pages start where the viewer is.
* UIX-034: the map tells the page script to send the origin as referrer with the tiles.
"""

from __future__ import annotations

import datetime
import json
import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

from django.urls import reverse
from django.utils import timezone

from rentalars.core.models import CompanyProfile
from rentalars.customers.models import Venue
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import Mailbox, MailboxAddress, Untagged
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import NOW
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data

SETTINGS = "/administration/mail/"


def page_of(mailbox: Mailbox) -> str:
    return f"/administration/mail/mailboxes/{mailbox.pk}/"


class MailboxCutoffPageTests(UiTestCase):
    """EML-049: the point in time and "only unread" with the mailbox."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=False)

    def test_switching_on_sets_the_point_and_it_is_shown(self) -> None:
        form = self.assert_ok(self.client.get(page_of(self.box)))
        self.assertIn('data-show-if="process_untagged=on"', form)
        self.assertIn("Übernehmen ab", form)
        self.assertIn("Nur ungelesene Mails", form)
        self.assertIn('type="datetime-local"', form)
        data = form_data(self.client.get(page_of(self.box)), "name", process_untagged="on")
        response = self.client.post(page_of(self.box), data, follow=True)
        self.assert_ok(response)
        self.box.refresh_from_db()
        self.assertEqual(self.box.untagged_since, timezone.now())
        listed = self.assert_ok(self.client.get(SETTINGS))
        self.assertIn("übernimmt Mails ohne Kennung ab 01.03.2027 08:00 ·", listed)
        # The point is shown in the form and can be changed; "only unread" too.
        form = self.client.get(page_of(self.box))
        self.assertIn('value="2027-03-01T08:00"', self.assert_ok(form))
        data = form_data(form, "name", untagged_since="2027-02-20T12:30", untagged_unread_only="on")
        self.client.post(page_of(self.box), data)
        self.box.refresh_from_db()
        self.assertEqual(timezone.localtime(self.box.untagged_since).strftime("%d.%m.%Y %H:%M"), "20.02.2027 12:30")
        self.assertTrue(self.box.untagged_unread_only)
        self.assertIn("ab 20.02.2027 12:30, nur ungelesene", self.assert_ok(self.client.get(SETTINGS)))
        # Switched off, the point goes; switched on again it is that moment.
        self.client.post(
            page_of(self.box), form_data(self.client.get(page_of(self.box)), "name", process_untagged=None)
        )
        self.box.refresh_from_db()
        self.assertIsNone(self.box.untagged_since)

    def test_further_address(self) -> None:
        new = reverse("mail:address_create", args=[self.box.pk])
        form = self.assert_ok(self.client.get(new))
        self.assertIn('data-show-if="untagged=inquiry|service_case"', form)
        data = form_data(self.client.get(new), "address", address="info@verleih.example", untagged=Untagged.INQUIRY)
        self.client.post(new, data)
        alias = MailboxAddress.objects.get()
        self.assertEqual(alias.untagged_since, timezone.now())
        page = self.assert_ok(self.client.get(page_of(self.box)))
        self.assertIn('Als Anfrage<div class="muted small">ab 01.03.2027 08:00</div>', page)

    def test_the_mail_log_says_why_a_mail_stayed(self) -> None:
        self.box.process_untagged = True
        self.box.untagged_since = NOW
        self.box.save()
        old = make_mail("Uralte Anfrage", date=NOW - datetime.timedelta(days=500))
        with mailboxes({self.box.address: FakeMailbox(old)}):
            fetch_mail(force=True)
        text = self.assert_ok(self.client.get("/administration/mail/log/"))
        self.assertIn("angekommen vor dem Zeitpunkt, ab dem Mails ohne Kennung übernommen werden", text)
        self.assertNotIn("Uralte Anfrage", self.assert_ok(self.client.get("/projects/inquiries/")))


class RouteAndTilePageTests(UiTestCase):
    """UIX-033, UIX-034 on the pages."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.warehouse_address = "Industriestraße 5, 12345 Musterstadt"
        profile.save()
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )

    def test_venue_route_starts_where_one_is(self) -> None:
        html = self.assert_ok(self.client.get(reverse("customers:venue_detail", args=[self.hall.pk])))
        links = re.findall(r'href="(https://www\.google\.com/maps/dir/[^"]+)"', html)
        self.assertEqual(
            [parse_qs(urlsplit(unescape(link)).query) for link in links],
            [{"api": ["1"], "destination": ["Hallenweg 3, 12345 Musterstadt"]}],
        )

    def test_the_map_asks_for_the_referrer(self) -> None:
        with FakeGeocoder({"Hallenweg 3, 12345 Musterstadt": ("52.1", "13.2")}):
            html = self.assert_ok(self.client.get(reverse("core:map", args=["venue", self.hall.pk])))
        data = json.loads(unescape(re.search(r'data-map="([^"]+)"', html).group(1)))
        self.assertEqual(data["referrerPolicy"], "strict-origin-when-cross-origin")
        self.assertNotIn("origin=", html)
