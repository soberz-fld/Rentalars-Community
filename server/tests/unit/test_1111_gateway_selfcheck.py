# SPDX-License-Identifier: GPL-3.0-or-later
"""The self-check names the link to the gateway (GWL-014)."""

from __future__ import annotations

import datetime

from django.test import override_settings
from django.utils import timezone
from django.utils.translation import override

from rentalars.core.selfcheck import ERROR, NOTE, OK, WARNING, Finding, run_checks
from rentalars.gateway_link.models import GatewayDevice, GatewayLink
from tests.helpers import RentalarsTestCase, make_user


def gateway_findings() -> dict[str, Finding]:
    """The findings of the group "Gateway" by title (English)."""
    with override("en"):
        report = run_checks()
    return {finding.title: finding for finding in report.findings if finding.group == "Gateway"}


def connect(**fields: object) -> GatewayLink:
    link = GatewayLink(
        gateway_url="https://gateway.example:8799",
        link_key="stored-encrypted",
        enrolled_at=timezone.now(),
    )
    for name, value in fields.items():
        setattr(link, name, value)
    link.save()
    return link


@override_settings(LANGUAGE_CODE="en")
class GatewaySelfCheckTests(RentalarsTestCase):
    def test_without_a_gateway_one_line_says_so(self) -> None:
        findings = gateway_findings()
        self.assertEqual(list(findings), ["Gateway link"])
        self.assertEqual(findings["Gateway link"].state, OK)
        self.assertIn("directly", findings["Gateway link"].detail)

    def test_a_link_that_was_never_connected_counts_as_none(self) -> None:
        GatewayLink.objects.create(gateway_url="", enrolled_at=None)
        self.assertEqual(list(gateway_findings()), ["Gateway link"])

    def test_a_fresh_answer_is_ok(self) -> None:
        connect(last_poll_at=timezone.now() - datetime.timedelta(seconds=12))
        findings = gateway_findings()
        self.assertEqual(findings["Gateway link"].detail, "https://gateway.example:8799")
        self.assertEqual(findings["Connection"].state, OK)
        self.assertIn("12 seconds", findings["Connection"].detail)

    def test_an_old_answer_is_an_error(self) -> None:
        connect(last_poll_at=timezone.now() - datetime.timedelta(minutes=10))
        finding = gateway_findings()["Connection"]
        self.assertEqual(finding.state, ERROR)
        self.assertIn("rentalars-gateway-link", finding.detail)

    def test_no_answer_yet_is_a_warning(self) -> None:
        connect()
        self.assertEqual(gateway_findings()["Connection"].state, WARNING)

    def test_the_last_error_is_shown(self) -> None:
        connect(
            last_poll_at=timezone.now(),
            last_error="OSError: connection refused",
            last_error_at=timezone.now(),
        )
        finding = gateway_findings()["Last error"]
        self.assertEqual(finding.state, WARNING)
        self.assertIn("connection refused", finding.detail)

    def test_no_error_no_line(self) -> None:
        connect(last_poll_at=timezone.now())
        self.assertNotIn("Last error", gateway_findings())

    def test_the_apps_are_counted(self) -> None:
        connect(last_poll_at=timezone.now())
        user = make_user("anna")
        for number in range(3):
            GatewayDevice.objects.create(
                device_id=f"{number:032x}",
                public_key="04" + f"{number:0128x}",
                user=user,
                revoked_at=timezone.now() if number == 2 else None,
            )
        self.assertEqual(gateway_findings()["Paired apps"].detail, "2 paired, 1 revoked")

    def test_an_announced_move_is_a_note(self) -> None:
        connect(last_poll_at=timezone.now(), move_url="https://new.example:8799")
        finding = gateway_findings()["Move announced"]
        self.assertEqual(finding.state, NOTE)
        self.assertIn("new.example", finding.detail)

    def test_the_check_reads_the_database_only(self) -> None:
        from unittest import mock

        connect(last_poll_at=timezone.now())
        with mock.patch("rentalars.gateway_link.service.GatewayClient.for_link", side_effect=AssertionError("called")):
            self.assertEqual(gateway_findings()["Connection"].state, OK)

    def test_german_titles(self) -> None:
        connect(last_poll_at=timezone.now())
        with override("de"):
            report = run_checks()
        titles = {finding.title for finding in report.findings if finding.group == "Gateway"}
        self.assertEqual(titles, {"Verbindung zum Gateway", "Verbindung", "Gekoppelte Apps"})
