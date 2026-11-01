# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages settled while the areas were put together.

EML-050: the panel "Letzte Mails" of a service case offers "Mail schreiben" by
the same rule as the tab "Korrespondenz" – the correspondence rights and a
mailbox that can send this mail; a service case may send through the mailbox
of its own address (EML-047) even without the general outgoing mailbox.
"""

from __future__ import annotations

from django.urls import reverse

from rentalars.mail.models import MailboxAddress
from rentalars.projects import service_cases
from tests.helpers import make_customer, make_project
from tests.mailbox import add_mailbox, configure_mailbox
from tests.ui.base import UiTestCase


class CaseWriteMailTests(UiTestCase):
    """EML-050: "Mail schreiben" on the service case page and in its tab alike."""

    def setUp(self) -> None:
        super().setUp()
        self.case = service_cases.create_case(name="Spot flackert", customer=make_customer())
        self.compose = reverse("mail:compose", args=[self.case.pk])

    def offers(self, url: str) -> bool:
        return f'href="{self.compose}' in self.assert_ok(self.client.get(url))

    def both(self) -> tuple[bool, bool]:
        return (
            self.offers(reverse("projects:case_detail", args=[self.case])),
            self.offers(reverse("mail:project_mails", args=[self.case.pk])),
        )

    def test_without_a_mailbox_neither_offers_it(self) -> None:
        self.assertEqual(self.both(), (False, False))

    def test_with_the_outgoing_mailbox_both_offer_it(self) -> None:
        configure_mailbox()
        self.assertEqual(self.both(), (True, True))

    def test_the_address_for_service_cases_is_enough_for_a_case(self) -> None:
        mailbox = add_mailbox("Service", "service@verleih.example")
        MailboxAddress.objects.create(mailbox=mailbox, address="service@verleih.example", for_service_cases=True)
        self.assertEqual(self.both(), (True, True))
        # A project that is not a service case still needs the outgoing mailbox.
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("mail:project_mails", args=[project.pk])))
        self.assertNotIn(f'href="{reverse("mail:compose", args=[project.pk])}', page)
