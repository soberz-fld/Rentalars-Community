# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of stage 4 outside the mailbox.

Two-factor login (AUT-006, RFC 6238), duplicating (PRJ-029), the planning
overviews (PRJ-028, VFG-014), the daily maintenance, the database fingerprint
(NFA-067, NFA-068) and the self-check (NFA-037).
"""

from __future__ import annotations

import datetime
import io
import json

from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.test import SimpleTestCase

from rentalars.accounts import twofactor
from rentalars.accounts.models import Role, SecurityEvent, UserSession
from rentalars.core.management.commands.database_fingerprint import database_fingerprint
from rentalars.core.models import SystemSettings
from rentalars.core.selfcheck import run_checks
from rentalars.notifications.models import Notification
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.models import CrewLine, ProjectPhase, ProjectStatus
from rentalars.schedule import services as schedule
from tests.helpers import (
    ALL_RIGHTS,
    NOW,
    RentalarsTestCase,
    add_line,
    at,
    make_person,
    make_project,
    make_stock,
    make_user,
    plan,
)


class TotpTests(SimpleTestCase):
    """The codes are those of RFC 6238, so every authenticator app shows the same."""

    #: The test key of RFC 6238, appendix B ("12345678901234567890"), in Base32.
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_the_test_vectors_of_rfc_6238(self) -> None:
        # Appendix B lists eight digits; the apps show the last six.
        for unix_time, expected in (
            (59, "94287082"),
            (1111111109, "07081804"),
            (1234567890, "89005924"),
            (2000000000, "69279037"),
        ):
            self.assertEqual(twofactor.code_at(self.SECRET, twofactor.current_step(unix_time)), expected[-6:])

    def test_a_step_before_and_after_is_accepted(self) -> None:
        now = 1_000_000_000.0
        step = twofactor.current_step(now)
        for offset, accepted in ((-2, False), (-1, True), (0, True), (1, True), (2, False)):
            code = twofactor.code_at(self.SECRET, step + offset)
            self.assertEqual(twofactor.matching_step(self.SECRET, code, now=now) is not None, accepted, offset)
        self.assertIsNone(twofactor.matching_step(self.SECRET, "12345", now=now))
        code = twofactor.code_at(self.SECRET, step)
        self.assertEqual(twofactor.matching_step(self.SECRET, f" {code[:3]} {code[3:]} ", now=now), step)

    def test_the_address_for_the_app(self) -> None:
        uri = twofactor.provisioning_uri(self.SECRET, "anna", "Rentalars Verleih")
        self.assertTrue(uri.startswith("otpauth://totp/Rentalars%20Verleih%3Aanna?secret=GEZD"))
        self.assertIn("<svg", twofactor.qr_code_svg(uri))

    def test_recovery_codes(self) -> None:
        codes = twofactor.new_recovery_codes()
        self.assertEqual(len(set(codes)), 10)
        self.assertTrue(all(len(code) == 9 and code[4] == "-" for code in codes))


class TwoFactorRuleTests(RentalarsTestCase):
    """AUT-006, NFA-049: codes are used once; roles and the setting require it."""

    def test_each_code_only_once(self) -> None:
        anna = make_user("anna")
        secret = twofactor.new_secret()
        step = twofactor.current_step()
        codes = twofactor.enable(anna, secret, twofactor.code_at(secret, step))
        self.assertFalse(twofactor.verify_code(anna, twofactor.code_at(secret, step)))  # used to set it up
        self.assertTrue(twofactor.verify_code(anna, twofactor.code_at(secret, step + 1)))
        self.assertFalse(twofactor.verify_code(anna, twofactor.code_at(secret, step + 1)))
        self.assertTrue(twofactor.verify_code(anna, codes[3]))
        self.assertFalse(twofactor.verify_code(anna, codes[3]))
        anna.refresh_from_db()
        self.assertEqual(len(anna.recovery_code_hashes), 9)
        self.assertNotIn(codes[0], str(anna.recovery_code_hashes))

    def test_who_must_use_it(self) -> None:
        anna = make_user("anna", roles=("Projektleitung",))
        admin = make_user("admin", superuser=True)
        self.assertFalse(anna.needs_two_factor or admin.needs_two_factor)
        settings = SystemSettings.load()
        settings.two_factor_for_administrators = True
        settings.save()
        self.assertTrue(admin.needs_two_factor)
        self.assertFalse(anna.needs_two_factor)
        Role.objects.filter(name="Projektleitung").update(requires_two_factor=True)
        anna = type(anna).objects.get(pk=anna.pk)
        self.assertTrue(anna.needs_two_factor)

    def test_disable_is_logged(self) -> None:
        anna = make_user("anna")
        secret = twofactor.new_secret()
        twofactor.enable(anna, secret, twofactor.code_at(secret, twofactor.current_step()))
        twofactor.disable(anna, by=make_user("admin", superuser=True))
        kinds = list(SecurityEvent.objects.filter(user=anna).values_list("kind", flat=True))
        self.assertEqual(sorted(kinds), ["2fa_disabled", "2fa_enabled"])


class DuplicateTests(RentalarsTestCase):
    """PRJ-029: the copy keeps the shape of the project and moves along in time."""

    def test_everything_moves_by_the_same_shift(self) -> None:
        source = make_project(
            "Stadtfest", start=at(10, 8), end=at(12, 20), event_start=at(11, 18), event_end=at(11, 23)
        )
        add_line(source, make_stock("L-001", 10), 2, start=at(10, 8), end=at(11, 8))
        ProjectPhase.objects.create(project=source, kind="setup", start=at(10, 8), end=at(10, 18))
        plan(source, "Stagehand", make_person("Ben"), start=at(10, 8), end=at(10, 18))
        user = make_user("paula")
        copy = duplicate_project(
            source,
            name="",
            start=at(10, 8, month=4),
            end=at(12, 20, month=4),
            with_crew=True,
            rights=ALL_RIGHTS,
            user=user,
        )
        self.assertEqual((copy.name, copy.status, copy.manager), ("Stadtfest", ProjectStatus.INQUIRY, user))
        self.assertEqual(copy.event_start, at(11, 18, month=4))
        line = copy.material_lines.get()
        self.assertEqual((line.start, line.end), (at(10, 8, month=4), at(11, 8, month=4)))
        self.assertEqual(copy.phases.get().start, at(10, 8, month=4))
        crew_line = CrewLine.objects.get(project=copy)
        self.assertEqual((crew_line.person, crew_line.start), (None, at(10, 8, month=4)))

    def test_a_shorter_period_drops_the_event(self) -> None:
        source = make_project(start=at(10), end=at(13), event_start=at(12), event_end=at(13))
        copy = duplicate_project(
            source, name="Kurz", start=at(10, month=5), end=at(11, month=5), with_material=False,
            rights=ALL_RIGHTS, user=None,
        )  # fmt: skip
        self.assertIsNone(copy.event_start)


class ScheduleTests(RentalarsTestCase):
    """PRJ-028, VFG-014: calendar weeks and bars."""

    def test_the_month_has_whole_weeks(self) -> None:
        project = make_project()
        weeks = schedule.month_calendar(type(project).objects.all(), 2027, 3)
        self.assertEqual(weeks[0][0].day, datetime.date(2027, 3, 1))  # 1 March 2027 is a Monday
        self.assertTrue(all(len(week) == 7 for week in weeks))
        days_with_project = [day.day.day for week in weeks for day in week if day.projects]
        self.assertEqual(days_with_project, [10, 11])  # the project ends at midnight before the 12th

    def test_bars_and_conflicts(self) -> None:
        days = schedule.day_range(datetime.date(2027, 3, 8), 7)
        bar = schedule.bar_for(at(10, 8), at(11, 12), days, label="x")
        self.assertEqual((bar.first, bar.last), (3, 4))  # grid columns, counted from 1
        self.assertIsNone(schedule.bar_for(at(20), at(21), days, label="x"))
        other = schedule.bar_for(at(11, 14), at(12), days, label="y")
        self.assertTrue(schedule.has_conflicts([bar, other]))
        later = schedule.bar_for(at(13, 8), at(13, 18), days, label="z")
        self.assertFalse(schedule.has_conflicts([bar, later]))


class MaintenanceTests(RentalarsTestCase):
    """NFA-036: the daily jobs, including the new ones of stage 4."""

    def test_sessions_and_old_entries_are_cleaned(self) -> None:
        anna = make_user("anna")
        session = SessionStore()
        session.create()
        UserSession.objects.create(user=anna, session_key=session.session_key)
        UserSession.objects.create(user=anna, session_key="gone")
        SecurityEvent.objects.create(kind="login", user=anna, timestamp=NOW - datetime.timedelta(days=400))
        SecurityEvent.objects.create(kind="login", user=anna)
        Notification.objects.create(
            user=anna, kind="defect", title="alt", created_at=NOW - datetime.timedelta(days=200)
        )
        output = io.StringIO()
        call_command("run_daily_maintenance", stdout=output)
        self.assertEqual(list(UserSession.objects.values_list("session_key", flat=True)), [session.session_key])
        self.assertEqual(SecurityEvent.objects.count(), 1)
        self.assertFalse(Notification.objects.filter(title="alt").exists())
        self.assertIn("security log entries", output.getvalue())


class FingerprintTests(RentalarsTestCase):
    """NFA-067, NFA-068: the fingerprint that proves a copy of the database complete."""

    def test_same_data_same_fingerprint_any_change_shows(self) -> None:
        make_project("Stadtfest")
        before = database_fingerprint()
        self.assertEqual(database_fingerprint(), before)
        output = io.StringIO()
        call_command("database_fingerprint", stdout=output)
        self.assertEqual(json.loads(output.getvalue()), before)
        project = make_project("Weinfest")
        after = database_fingerprint()
        table = project._meta.db_table
        self.assertEqual(after["tables"][table]["rows"], before["tables"][table]["rows"] + 1)
        project.delete()
        # Deleting the new row brings the checksum back; the order of rows does not matter.
        self.assertEqual(database_fingerprint()["tables"][table], before["tables"][table])


def broken_check(report: object) -> None:
    """A check that fails as a whole."""
    raise OSError("no disk")


class SelfCheckTests(RentalarsTestCase):
    """NFA-037: the self-check never fails as a whole; a broken check is a finding of its own."""

    def test_a_broken_check_is_reported(self) -> None:
        from unittest import mock

        with mock.patch("rentalars.core.selfcheck._space", broken_check):
            report = run_checks()
        broken = [finding for finding in report.findings if "no disk" in finding.detail]
        self.assertEqual(len(broken), 1)
        self.assertEqual(report.worst, "error")

    def test_the_command_exits_with_an_error_code(self) -> None:
        from unittest import mock

        with mock.patch("rentalars.core.selfcheck._space", broken_check), self.assertRaises(SystemExit) as stop:
            call_command("selfcheck", stdout=io.StringIO())
        self.assertEqual(stop.exception.code, 1)


class ResetTwoFactorCommandTests(RentalarsTestCase):
    """AUT-006: on the server, root can switch off the second factor of a locked-out administrator."""

    def test_reset_on_the_command_line(self) -> None:
        from django.core.management.base import CommandError

        anna = make_user("anna", superuser=True)
        secret = twofactor.new_secret()
        twofactor.enable(anna, secret, twofactor.code_at(secret, twofactor.current_step()))
        output = io.StringIO()
        call_command("reset_two_factor", "ANNA", stdout=output)
        anna.refresh_from_db()
        self.assertFalse(anna.has_two_factor)
        self.assertIn("switched off", output.getvalue())
        call_command("reset_two_factor", "anna", stdout=output)
        self.assertIn("nothing to do", output.getvalue())
        with self.assertRaises(CommandError):
            call_command("reset_two_factor", "nobody")


class ProblemReportTests(RentalarsTestCase):
    """NFA-018: the daily maintenance reports errors of the self-check to the operators."""

    def test_a_missing_backup_reaches_the_operators(self) -> None:
        from unittest import mock

        from django.test import override_settings

        from rentalars.core.models import ErrorRecord
        from rentalars.core.selfcheck import report_problems

        admin = make_user("admin", superuser=True)
        # The console would print the reported problem; only the operators should get it here.
        import logging

        for handler in logging.getLogger("rentalars").handlers:
            if isinstance(handler, logging.StreamHandler):
                self.addCleanup(handler.setLevel, handler.level)
                handler.setLevel(logging.CRITICAL)
        with (
            override_settings(RENTALARS_IS_PRODUCTION=True),
            mock.patch("rentalars.core.selfcheck._security", lambda report: None),
            mock.patch("rentalars.core.selfcheck._files", lambda report: None),
        ):
            self.assertGreaterEqual(report_problems(), 1)
        record = ErrorRecord.objects.get(message__contains="sudo rentalars backup")
        self.assertEqual(record.source, "rentalars.selfcheck")
        self.assertTrue(Notification.objects.filter(user=admin, kind="system_error").exists())


class NginxSelfCheckTests(RentalarsTestCase):
    """NFA-037, NFA-049: the self-check compares the NGINX site with the template of the version."""

    def findings(self, site_text: str) -> dict[str, tuple[str, str]]:
        import tempfile
        from pathlib import Path
        from unittest import mock

        from rentalars.core import selfcheck

        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder) / "rentalars"
            site.write_text(site_text, encoding="utf-8")
            report = selfcheck.Report()
            with mock.patch.object(selfcheck, "NGINX_SITE", site):
                selfcheck._nginx(report, "Sicherheit")
        return {finding.title: (finding.state, finding.detail) for finding in report.findings}

    def test_the_template_of_this_version_is_complete(self) -> None:
        from django.conf import settings

        template = (settings.BASE_DIR / "deploy" / "nginx" / "rentalars.conf").read_text(encoding="utf-8")
        found = self.findings(template)
        self.assertEqual(found["NGINX"][0], "ok")
        self.assertNotIn("NGINX: Größe beim Hochladen", found)

    def test_a_site_from_version_0_3_is_reported_with_the_command_that_helps(self) -> None:
        old_site = "server_tokens off;\nssl_protocols TLSv1.2 TLSv1.3;\nlimit_req zone=x;\nclient_max_body_size 30m;\n"
        found = self.findings(old_site)
        state, detail = found["NGINX"]
        self.assertEqual(state, "warning")
        self.assertIn("ssl_reject_handshake on", detail)
        self.assertIn("sudo rentalars nginx-site", detail)
        state, detail = found["NGINX: Größe beim Hochladen"]
        self.assertEqual(state, "warning")
        self.assertIn("bis 30 MB", detail)
        self.assertIn("bis 50 MB", detail)

    def test_no_limit_and_a_large_limit_are_fine(self) -> None:
        for line in ("client_max_body_size 0;", "client_max_body_size 1g;"):
            with self.subTest(line):
                self.assertNotIn("NGINX: Größe beim Hochladen", self.findings(line))
