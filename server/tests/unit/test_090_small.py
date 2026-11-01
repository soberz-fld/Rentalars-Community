# SPDX-License-Identifier: GPL-3.0-or-later
"""Three smaller requirements – a flat rate in "My times", a notice of changed login details, template texts.

ZEI-028, the requirement: once per deployment – the flat rate counts once in the weekly amount, the hours only as
hours, as the companion app already receives it.

* The flat rate of a deployment counts once, with its first finished entry, in the week that entry lies in;
  every further entry shows "in der Pauschale" with 0. The hours count as hours. The API says the same
  (``pay_kind: flat``, ``in_flat_rate``).

AUT-030, the requirement: a mail "Deine Anmeldedaten wurden geändert" to the previous address, with the time and a
hint what to do.

* A new e-mail address is noticed to the previous one, a new password to the current one – from every place it is
  changed, exactly once, after the commit, in the holder's language; never at creation, without an address or for
  a deactivated account; a failure to send never undoes the change.

DOK-018, the requirement: a button "Englische Vorlagentexte übernehmen" (and back to German); own texts are shown
first, nothing is overwritten without confirmation.

* The page and ``/document-templates/defaults`` compare with the default texts of a language; own texts are marked
  and taken over only when chosen; footer and logo stay; the change is logged.
"""

from __future__ import annotations

import re
from decimal import Decimal as D  # noqa: N817
from typing import Any
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db import transaction
from django.test import Client
from django.urls import reverse

from rentalars.accounts import notices, services
from rentalars.accounts.models import Role, SecurityEvent, User
from rentalars.core.audit import acting_as
from rentalars.core.models import AuditAction, AuditLogEntry, CompanyProfile
from rentalars.documents import template_texts
from rentalars.documents.models import DocumentKind, DocumentTemplate
from rentalars.documents.services import DEFAULT_TEMPLATES, DEFAULT_TEMPLATES_ENGLISH, template_for
from rentalars.personnel.models import Person
from rentalars.personnel.privacy import anonymise_person
from rentalars.projects.models import CrewBilling
from rentalars.timetracking import display
from rentalars.timetracking.models import TimeEntry
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    LATER,
    PASSWORD,
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)
from tests.ui.base import UiTestCase, form_data

# --- ZEI-028: a flat rate counts once per deployment ------------------------------------------------------------


class FlatRateCase(RentalarsTestCase):
    """Anna: Licht by the hour on the 10th; Rigging with a flat rate of 500 € from Friday 12th to Tuesday 16th.

    March 2027 begins on a Monday: the deployment spans the weeks of the 8th and of the 15th.
    """

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.project = make_project("Stadtfest", start=at(10), end=at(17))
        self.light, self.rig = job_function("Licht"), job_function("Rigging")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", user=self.anna_user, rates={"Licht": "30.00", "Rigging": "40.00"})
        self.line = plan(self.project, self.rig, self.anna, start=at(12, 8), end=at(16, 18), cost_flat_rate=D("500"))
        self.hourly = record_time(self.anna, self.project, self.light, at(10, 8), at(10, 12))
        self.first = record_time(self.anna, self.project, self.rig, at(12, 8), at(12, 18), crew_line=self.line)
        self.second = record_time(self.anna, self.project, self.rig, at(13, 8), at(13, 12), crew_line=self.line)
        self.later = record_time(self.anna, self.project, self.rig, at(15, 8), at(15, 18), crew_line=self.line)

    def week(self, day: int) -> list[TimeEntry]:
        monday = at(day - (day - 1) % 7)
        return list(
            TimeEntry.objects.filter(person=self.anna, start__gte=monday, start__lt=at(monday.day + 7))
            .select_related("crew_line")
            .order_by("start", "id")
        )


class FlatRateTests(FlatRateCase):
    """ZEI-028: once per deployment, in the week of its first entry."""

    def test_the_week_of_the_first_entry_counts_the_flat_rate_once(self) -> None:
        entries = self.week(10)
        total = display.attach_pay(entries)
        self.assertEqual(
            [(entry.pay_kind, entry.pay_rate, entry.pay_amount, entry.pay_in_flat_rate) for entry in entries],
            [
                ("hourly", D("30.00"), D("120.00"), False),
                ("flat", D("500.00"), D("500.00"), False),
                ("flat", D("500.00"), D("0"), True),
            ],
        )
        self.assertEqual(total, D("620.00"))  # 4 h × 30 € and the flat rate once – not 14 h × 40 €

    def test_a_later_week_shows_the_entries_in_the_flat_rate(self) -> None:
        """A deployment spanning weeks counts in the week of its first entry."""
        entries = self.week(15)
        self.assertEqual(display.attach_pay(entries), D("0"))
        self.assertEqual([(entry.pay_kind, entry.pay_in_flat_rate) for entry in entries], [("flat", True)])
        self.assertEqual(entries[0].hours, D("10.00"))  # the hours stay hours

    def test_without_the_first_entry_the_next_one_carries_it(self) -> None:
        TimeEntry.objects.filter(pk=self.first.pk).delete()
        entries = self.week(10)
        display.attach_pay(entries)
        self.assertEqual([entry.pay_amount for entry in entries], [D("120.00"), D("500.00")])

    def test_a_day_rate_still_counts_per_day_and_the_flat_rate_comes_first(self) -> None:
        sound = job_function("Tontechnik")
        daily = plan(
            self.project,
            sound,
            self.anna,
            start=at(11, 8),
            end=at(11, 22),
            billing=CrewBilling.DAY,
            daily_rate=D("280"),
        )
        record_time(self.anna, self.project, sound, at(11, 8), at(11, 12), crew_line=daily)
        both = plan(self.project, sound, self.anna, start=at(14, 8), end=at(14, 20), billing=CrewBilling.DAY)
        both.daily_rate, both.cost_flat_rate = D("280"), D("300")
        both.save()
        record_time(self.anna, self.project, sound, at(14, 8), at(14, 12), crew_line=both)
        entries = self.week(10)
        display.attach_pay(entries)
        kinds = [(entry.pay_kind, entry.pay_amount) for entry in entries]
        self.assertIn(("daily", D("280.00")), kinds)
        self.assertEqual(kinds[-1], ("flat", D("300.00")))  # flat before daily, as in the costs of the line

    def test_the_api_names_the_same_for_any_choice_of_entries(self) -> None:
        """API-016, ZEI-028: ``in_flat_rate`` also where the list does not hold the first entry – in one query."""
        later = TimeEntry.objects.get(pk=self.later.pk)
        display.attach_pay_kinds([later])
        self.assertEqual((later.pay_kind, later.pay_in_day_rate, later.pay_in_flat_rate), ("flat", False, True))
        first = TimeEntry.objects.get(pk=self.first.pk)
        display.attach_pay_kinds([first])
        self.assertEqual((first.pay_kind, first.pay_in_flat_rate), ("flat", False))
        entries = list(TimeEntry.objects.select_related("crew_line"))
        with self.assertNumQueries(1):
            display.attach_pay_kinds(entries)
        hourly = next(entry for entry in entries if entry.pk == self.hourly.pk)
        self.assertEqual((hourly.pay_kind, hourly.pay_in_flat_rate), ("hourly", False))


class FlatRatePageTests(FlatRateCase, UiTestCase):
    """ZEI-028 on "My times"."""

    def test_my_times_show_the_flat_rate_once(self) -> None:
        browser = self.browser_of(self.anna_user)
        week = self.assert_ok(browser.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertIn('<span class="muted small">Pauschale</span> 500,00 €', week)
        self.assertIn('<span class="muted small">in der Pauschale</span>', week)
        sum_row = week.split("Summe der Woche")[1].split("</tr>")[0]
        self.assertIn('data-label="Stunden">18</td>', sum_row)  # 4 + 10 + 4 hours: the hours stay hours
        self.assertIn('data-label="Betrag">620,00 €</td>', sum_row)  # 120 € and the flat rate once
        later = self.assert_ok(browser.get(reverse("timetracking:my_times"), {"week": "2027-03-15"}))
        self.assertIn('<span class="muted small">in der Pauschale</span>', later)
        self.assertIn('data-label="Betrag">0,00 €</td>', later.split("Summe der Woche")[1])


class FlatRateApiTests(FlatRateCase, ApiTestCase):
    """ZEI-028: ``in_flat_rate`` beside ``pay_kind`` and ``in_day_rate`` (API-016)."""

    def test_lists_single_entries_and_the_report(self) -> None:
        app = self.client_of(self.anna_user)
        rows = app.get(f"{API}/time-entries").json()["results"]
        named = {row["id"]: (row["pay_kind"], row["in_day_rate"], row["in_flat_rate"]) for row in rows}
        self.assertEqual(
            named,
            {
                self.hourly.pk: ("hourly", False, False),
                self.first.pk: ("flat", False, False),
                self.second.pk: ("flat", False, True),
                self.later.pk: ("flat", False, True),
            },
        )
        single = app.get(f"{API}/time-entries/{self.later.pk}").json()
        self.assertEqual((single["pay_kind"], single["in_flat_rate"]), ("flat", True))
        report = app.get(f"{API}/reports/hours", {"from": "2027-03-15", "to": "2027-03-21"}).json()
        self.assertEqual([row["in_flat_rate"] for row in report["entries"]], [True])


# --- AUT-030: a notice of changed login details ---------------------------------------------------------------


def notices_to(address: str) -> list[Any]:
    """The mails "login details changed" that went to an address."""
    return [message for message in mail.outbox if address in message.to and "Anmeldedaten" in message.subject]


class NoticeCase(UiTestCase):
    """Berta (crew) logs in with ``PASSWORD``; the administrator is called "admin"."""

    def setUp(self) -> None:
        super().setUp()
        self.admin_user.first_name, self.admin_user.last_name = "Ada", "Admin"
        self.admin_user.save()
        self.berta = make_user("berta", roles=("Crew",))
        self.browser = self.browser_of(self.berta)
        mail.outbox.clear()

    def reload(self) -> User:
        return User.objects.get(pk=self.berta.pk)


class EmailNoticeTests(NoticeCase):
    """AUT-030: a new address – to the previous one, once, whichever way it was changed."""

    def test_own_personnel_data_in_the_browser(self) -> None:
        url = reverse("personnel:own_profile")
        page = self.browser.get(url)
        with self.captureOnCommitCallbacks(execute=True):
            self.browser.post(url, form_data(page, containing="phone", email="berta.neu@example.de"))
        self.assertEqual(self.reload().email, "berta.neu@example.de")
        self.assertEqual(len(mail.outbox), 1)  # exactly one – the person passes it on to the account
        notice = mail.outbox[0]
        self.assertEqual(notice.to, ["berta@example.de"])
        self.assertEqual(notice.subject, "Deine Anmeldedaten wurden geändert")
        body = notice.body
        self.assertIn("Hallo berta,", body)
        self.assertIn("von berta@example.de auf berta.neu@example.de geändert", body)
        self.assertIn("Wann: 01.03.2027 um 08:00 Uhr", body)
        self.assertNotIn("Geändert von", body)  # she did it herself
        self.assertIn("Dein Benutzername: berta", body)
        self.assertIn("sag sofort den Administratoren", body)
        self.assertIn("Diese Nachricht betrifft dein Konto unter http", body)
        self.assertEqual(notices_to("berta.neu@example.de"), [])  # the new address gets nothing

    def test_the_user_form_of_the_administration_names_who_changed_it(self) -> None:
        url = reverse("accounts:user_edit", args=[self.berta.pk])
        page = self.client.get(url)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, form_data(page, containing="username", email="b@example.de"))
        self.assertEqual(Person.objects.get(user=self.berta).email, "b@example.de")
        self.assertEqual(len(mail.outbox), 1)  # the account passes it on to the person: still one
        self.assertIn("Geändert von: Ada Admin", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["berta@example.de"])

    def test_in_the_language_of_the_holder(self) -> None:
        self.berta.language = "en"
        self.berta.save()
        with self.captureOnCommitCallbacks(execute=True), acting_as(self.admin_user):
            person = Person.objects.get(user=self.berta)
            person.email = "b.en@example.de"
            person.save()
        notice = mail.outbox[0]
        self.assertEqual((notice.to, notice.subject), (["berta@example.de"], "Your login details were changed"))
        self.assertIn("was changed from berta@example.de to b.en@example.de", notice.body)
        self.assertIn("When: 01/03/2027 at 08:00", notice.body)
        self.assertIn("Changed by: Ada Admin", notice.body)

    def test_an_import_is_rentalars_itself(self) -> None:
        with self.captureOnCommitCallbacks(execute=True), acting_as("system:import"):
            person = Person.objects.get(user=self.berta)
            person.email = "import@example.de"
            person.save()
        self.assertIn("Geändert von: Rentalars selbst (automatisch)", mail.outbox[0].body)

    def test_exactly_once_whichever_record_is_saved(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            person = Person.objects.select_related("user").get(user=self.berta)
            person.email = "eins@example.de"
            person.save()
            person.user.save()  # the account of the person, saved again with what the person passed on
            account = self.reload()
            account.email = "zwei@example.de"
            account.save()
        self.assertEqual([message.to for message in mail.outbox], [["berta@example.de"], ["eins@example.de"]])

    def test_noted_in_the_security_log(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            account = self.reload()
            account.email = "log@example.de"
            account.save()
        entry = AuditLogEntry.objects.get(event="user.notice_email")
        self.assertEqual(entry.changes, {"to": "berta@example.de", "old": "berta@example.de", "new": "log@example.de"})
        page = self.assert_ok(self.client.get(reverse("accounts:security_log")))
        self.assertIn("E-Mail-Adresse von berta@example.de auf log@example.de geändert", page)

    def test_no_notice_at_creation_without_old_address_inactive_or_anonymised(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            services.invite_user(username="neu", email="neu@example.de")
            make_person("Nina Neu", email="nina@example.de")
            nobody = make_user("ohne")
            nobody.email = None
            nobody.save()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            nobody.email = "jetzt@example.de"  # no previous address
            nobody.save()
            sleeping = make_user("still")
            sleeping.is_active = False
            sleeping.save()
            sleeping.email = "anders@example.de"
            sleeping.save()
            anonymise_person(Person.objects.get(user=self.berta))
        self.assertEqual(mail.outbox, [])

    def test_a_rolled_back_change_sends_nothing(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    account = self.reload()
                    account.email = "nie@example.de"
                    account.save()
                    raise RuntimeError("rolled back")
            except RuntimeError:
                pass
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.reload().email, "berta@example.de")

    def test_a_failure_to_send_does_not_undo_the_change(self) -> None:
        with (
            mock.patch("rentalars.accounts.notices.send_mail", side_effect=OSError("no server")),
            self.assertLogs("rentalars.accounts.notices", "WARNING"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            account = self.reload()
            account.email = "trotzdem@example.de"
            account.save()
        self.assertEqual(self.reload().email, "trotzdem@example.de")
        self.assertFalse(AuditLogEntry.objects.filter(event="user.notice_email").exists())


class PasswordNoticeTests(NoticeCase):
    """AUT-030: a new password – to the current address."""

    def test_own_password_on_my_account(self) -> None:
        new = "Ein-ganz-neues-Passwort-77"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.browser.post(
                reverse("accounts:account"),
                {"form": "password", "old_password": PASSWORD, "new_password1": new, "new_password2": new},
            )
        self.assertEqual(response.status_code, 302)
        notice = mail.outbox[0]
        self.assertEqual((len(mail.outbox), notice.to), (1, ["berta@example.de"]))
        self.assertIn("das Passwort deines Rentalars-Kontos wurde geändert.", notice.body)
        self.assertIn("über „Passwort vergessen?“ ein neues Passwort", notice.body)
        self.assertIn("/password-reset/", notice.body)
        self.assertTrue(AuditLogEntry.objects.filter(event="user.notice_password").exists())

    def test_reset_with_the_link_and_the_first_password_of_an_invitation(self) -> None:
        self.client.logout()
        self.client.post(reverse("accounts:password_reset"), {"email": "berta@example.de"})
        link = re.search(r"https?://\S+/password-reset/\S+", mail.outbox[0].body).group(0)  # type: ignore[union-attr]
        page = self.client.get("/" + link.split("/", 3)[3], follow=True)
        new = "Ein-ganz-neues-Passwort-77"
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(page.redirect_chain[-1][0], {"new_password1": new, "new_password2": new})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("über den Link aus der E-Mail zurückgesetzt", mail.outbox[0].body)
        self.assertEqual(SecurityEvent.objects.filter(user=self.berta, detail="reset by link").count(), 1)
        # An invited account sets its first password with the same page: nothing is replaced, no notice.
        invited = services.invite_user(username="ines", email="ines@example.de")
        link = re.search(r"https?://\S+/password-reset/\S+", mail.outbox[-1].body).group(0)  # type: ignore[union-attr]
        page = self.client.get("/" + link.split("/", 3)[3], follow=True)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(page.redirect_chain[-1][0], {"new_password1": new, "new_password2": new})
        self.assertTrue(User.objects.get(pk=invited.pk).check_password(new))
        self.assertEqual(mail.outbox, [])
        self.assertTrue(SecurityEvent.objects.filter(user=invited, detail="first password by link").exists())

    def test_one_time_password_by_an_administrator_and_the_own_one_after_it(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            shown = self.client.post(reverse("accounts:user_one_time_password", args=[self.berta.pk]))
        notice = mail.outbox[0]
        self.assertEqual(notice.to, ["berta@example.de"])
        self.assertIn("ein Administrator hat für dein Rentalars-Konto ein Einmal-Passwort festgelegt", notice.body)
        self.assertIn("Geändert von: Ada Admin", notice.body)
        mail.outbox.clear()
        # Her session ended with the old password; she logs in with the one-time password and chooses her own.
        browser = Client()
        self.assertTrue(browser.login(username="berta", password=shown.context["password"]))
        new = "Ein-ganz-neues-Passwort-77"
        with self.captureOnCommitCallbacks(execute=True):
            browser.post(reverse("accounts:new_password"), {"new_password1": new, "new_password2": new})
        self.assertTrue(self.reload().check_password(new))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("wurde geändert.", mail.outbox[0].body)
        self.assertNotIn("Geändert von", mail.outbox[0].body)

    def test_one_time_password_for_an_account_that_never_had_one(self) -> None:
        invited = services.invite_user(username="ines", email="ines@example.de")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            services.set_one_time_password(invited, acting_user=self.admin_user)
        self.assertEqual(mail.outbox, [])

    def test_no_address_no_notice(self) -> None:
        self.berta.email = None
        self.berta.save()
        with self.captureOnCommitCallbacks(execute=True):
            services.set_one_time_password(self.berta, acting_user=self.admin_user)
        self.assertEqual(mail.outbox, [])

    def test_unknown_change(self) -> None:
        with self.assertRaises(ValueError):
            notices.credentials_changed(self.berta, "everything")


class NoticeApiTests(ApiTestCase):
    """AUT-030 through the API: ``/users``, ``/people`` and ``/people/me/profile`` – each change once."""

    def setUp(self) -> None:
        super().setUp()
        self.berta = make_user("berta", roles=("Crew",))
        self.person = Person.objects.get(user=self.berta)
        mail.outbox.clear()

    def test_users(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.admin.patch(f"{API}/users/{self.berta.pk}", {"email": "u@example.de"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([message.to for message in mail.outbox], [["berta@example.de"]])
        self.assertIn("Geändert von: admin", mail.outbox[0].body)

    def test_people(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.admin.patch(f"{API}/people/{self.person.pk}", {"email": "p@example.de"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([message.to for message in mail.outbox], [["berta@example.de"]])
        self.assertIn("auf p@example.de geändert", mail.outbox[0].body)

    def test_own_profile(self) -> None:
        own = self.client_of(self.berta)
        with self.captureOnCommitCallbacks(execute=True):
            response = own.patch(f"{API}/people/me/profile", {"email": "me@example.de"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([message.to for message in mail.outbox], [["berta@example.de"]])
        self.assertNotIn("Geändert von", mail.outbox[0].body)
        with self.captureOnCommitCallbacks(execute=True):
            own.patch(f"{API}/people/me/profile", {"phone": "0170 2"}, format="json")
        self.assertEqual(len(mail.outbox), 1)  # no new address, no notice


# --- DOK-018: the default texts of the templates in English or German ------------------------------------------


def english(kind: str, field: str) -> str:
    return DEFAULT_TEMPLATES_ENGLISH[DocumentKind(kind)][field]


def german(kind: str, field: str) -> str:
    return DEFAULT_TEMPLATES[DocumentKind(kind)][field]


class TemplateTextTests(RentalarsTestCase):
    """DOK-018: compare, take over, own texts only when chosen; footer and logo stay; logged."""

    def setUp(self) -> None:
        super().setUp()
        for kind in DocumentKind.values:
            template_for(kind)
        offer = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        offer.introduction = "Unser eigener Text für {project}."
        offer.footer = "Geschäftsführer: Max Muster"
        offer.show_logo = False
        offer.save()

    def test_the_comparison_marks_own_texts(self) -> None:
        comparisons = {comparison.kind: comparison for comparison in template_texts.compare("en")}
        self.assertEqual(set(comparisons), set(DocumentKind.values))
        offer = {change.name: change for change in comparisons[DocumentKind.OFFER].changes}
        self.assertEqual(set(offer), {"title", "introduction", "closing"})
        self.assertTrue(offer["introduction"].own)
        self.assertFalse(offer["title"].own)
        self.assertEqual((offer["title"].current, offer["title"].new), ("Angebot", "Quotation"))
        # Empty closing texts are the same in both languages: nothing to change.
        self.assertEqual(
            [change.name for change in comparisons[DocumentKind.CANCELLATION].changes], ["title", "introduction"]
        )
        self.assertEqual(template_texts.suggested_language(), "en")

    def test_take_over_without_own_texts_then_back_in_german(self) -> None:
        result = template_texts.take_over("en")
        offer = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        self.assertEqual(offer.title, "Quotation")
        self.assertEqual(offer.closing, english("offer", "closing"))
        self.assertEqual(offer.introduction, "Unser eigener Text für {project}.")  # own text kept
        self.assertEqual(
            (offer.footer, offer.show_logo, offer.validity_days), ("Geschäftsführer: Max Muster", False, 14)
        )
        self.assertEqual([change.key for change in result.kept_own], ["offer:introduction"])
        invoice = DocumentTemplate.objects.get(kind=DocumentKind.INVOICE)
        self.assertEqual((invoice.title, invoice.introduction), ("Invoice", english("invoice", "introduction")))
        self.assertEqual(template_texts.suggested_language(), "de")
        # The change log keeps the previous texts, with the actor.
        log = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(DocumentTemplate),
            object_id=str(invoice.pk),
            action=AuditAction.UPDATED,
        ).get()
        self.assertEqual(log.changes["title"], ["Rechnung", "Invoice"])
        # And back in German – the own text again only if asked for.
        template_texts.take_over("de", include_own=True)
        offer.refresh_from_db()
        self.assertEqual((offer.title, offer.introduction), ("Angebot", german("offer", "introduction")))

    def test_only_what_is_ticked_and_nothing_changed_in_the_meantime(self) -> None:
        comparison = {item.kind: item for item in template_texts.compare("en")}[DocumentKind.OFFER]
        seen = {change.key: change.seen for change in comparison.changes}
        offer = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        offer.title = "Kostenvoranschlag"  # changed by somebody else after the page was shown
        offer.save()
        result = template_texts.take_over(
            "en", chosen=["offer:title", "offer:introduction"], seen=seen, document_language=True
        )
        offer.refresh_from_db()
        self.assertEqual([change.key for change in result.changed], ["offer:introduction"])  # ticked own text
        self.assertEqual([change.key for change in result.stale], ["offer:title"])
        self.assertEqual((offer.title, offer.introduction), ("Kostenvoranschlag", english("offer", "introduction")))
        self.assertEqual(offer.closing, german("offer", "closing"))  # not ticked
        self.assertTrue(result.document_language_changed)
        self.assertEqual(CompanyProfile.load().document_language, "en")


class TemplateTextPageTests(UiTestCase):
    """DOK-018: the page under Settings; reading with read access, taking over with write access."""

    def setUp(self) -> None:
        super().setUp()
        offer = template_for(DocumentKind.OFFER)
        offer.introduction = "Unser eigener Text."
        offer.save()
        self.url = reverse("documents:template_defaults")

    def test_shown_with_own_texts_unticked_then_taken_over(self) -> None:
        page = self.client.get(self.url, {"language": "en"})
        text = self.assert_ok(page)
        self.assertIn("Vorlagentexte auf Englisch oder Deutsch", text)
        self.assertIn("eigener Text", text)
        self.assertIn("Englische Vorlagentexte übernehmen", text)
        self.assertIn("Sprache der Dokumente ist eine eigene Einstellung (zurzeit: Deutsch)", text)
        data = form_data(page, containing="fields")
        self.assertIn("offer:title", data["fields"])
        self.assertNotIn("offer:introduction", data["fields"])  # the own text is not ticked
        response = self.client.post(self.url, data, follow=True)
        self.assertIn("Texte wurden durch ihre Standardtexte ersetzt.", " ".join(self.messages_of(response)))
        offer = DocumentTemplate.objects.get(kind=DocumentKind.OFFER)
        self.assertEqual((offer.title, offer.introduction), ("Quotation", "Unser eigener Text."))
        self.assertEqual(CompanyProfile.load().document_language, "de")  # only when ticked
        again = self.assert_ok(self.client.get(self.url, {"language": "en"}))
        self.assertIn("schon die englischen Texte", again)

    def test_in_english(self) -> None:
        """UIX-029: the page in the user's language (the crawl of the English pages skips it, see test_083)."""
        self.admin_user.language = "en"
        self.admin_user.save()
        text = self.assert_ok(self.client.get(self.url, {"language": "en"}))
        self.assertIn("<h1>Template texts in English or German</h1>", text)
        self.assertIn("own text", text)
        self.assertIn("Take over the English template texts", text)
        self.assertIn("Also make the documents English", text)
        self.assertIn("The language of the documents is a setting of its own (now: Deutsch).", text)

    def test_reached_from_the_settings_and_the_template_list(self) -> None:
        self.assertIn(self.url, self.assert_ok(self.client.get(reverse("core:administration"))))
        listing = self.assert_ok(self.client.get(reverse("admin:documents_documenttemplate_changelist")))
        self.assertIn(self.url, listing)

    def test_rights(self) -> None:
        crew = self.browser_for("carla", "Crew")
        self.assertEqual(crew.get(self.url).status_code, 403)
        Role.objects.create(name="Einstellungen lesen", module_levels={"administration": 1})
        reader = self.browser_for("rita", "Einstellungen lesen")
        text = self.assert_ok(reader.get(self.url, {"language": "en"}))
        self.assertNotIn('name="fields"', text)
        self.assertIn("Texte übernehmen darf nur, wer die Einstellungen ändern darf.", text)
        self.assertEqual(reader.post(self.url, {"language": "en", "fields": ["offer:title"]}).status_code, 403)
        self.assertEqual(DocumentTemplate.objects.get(kind=DocumentKind.OFFER).title, "Angebot")


class TemplateTextApiTests(ApiTestCase):
    """DOK-018: ``GET``/``POST /document-templates/defaults``."""

    url = f"{API}/document-templates/defaults"

    def setUp(self) -> None:
        super().setUp()
        offer = template_for(DocumentKind.OFFER)
        offer.introduction = "Unser eigener Text."
        offer.save()

    def test_look_then_take_over(self) -> None:
        data = self.admin.get(self.url, {"language": "en"}).json()
        self.assertEqual((data["language"], data["document_language"]), ("en", "de"))
        offer = next(item for item in data["templates"] if item["kind"] == "offer")
        changes = {change["field"]: change for change in offer["changes"]}
        self.assertEqual(
            changes["introduction"],
            {
                "field": "introduction",
                "current": "Unser eigener Text.",
                "new": english("offer", "introduction"),
                "own": True,
            },
        )
        self.assertEqual(DocumentTemplate.objects.get(kind="offer").title, "Angebot")  # GET changes nothing
        response = self.admin.post(self.url, {"language": "en", "kinds": ["offer", "invoice"]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(
            sorted((item["kind"], item["field"]) for item in result["changed"]),
            [
                ("invoice", "closing"),
                ("invoice", "introduction"),
                ("invoice", "title"),
                ("offer", "closing"),
                ("offer", "title"),
            ],
        )
        self.assertEqual(result["kept_own"], [{"kind": "offer", "field": "introduction"}])
        self.assertFalse(result["document_language_changed"])
        self.assertEqual(DocumentTemplate.objects.get(kind="delivery_note").title, "Lieferschein")  # not asked for
        own = self.admin.post(
            self.url,
            {"language": "en", "kinds": ["offer"], "include_own": True, "document_language": True},
            format="json",
        ).json()
        self.assertEqual(own["changed"], [{"kind": "offer", "field": "introduction"}])
        self.assertTrue(own["document_language_changed"])
        self.assertEqual(DocumentTemplate.objects.get(kind="offer").introduction, english("offer", "introduction"))

    def test_rights_and_errors(self) -> None:
        crew = self.client_for("carla", "Crew")
        self.assert_error(crew.get(self.url, {"language": "en"}), 403, "permission_denied")
        self.assert_error(crew.post(self.url, {"language": "en"}, format="json"), 403, "permission_denied")
        Role.objects.create(name="Einstellungen lesen", module_levels={"administration": 1})
        reader = self.client_for("rita", "Einstellungen lesen")
        self.assertEqual(reader.get(self.url, {"language": "de"}).status_code, 200)
        self.assert_error(reader.post(self.url, {"language": "en"}, format="json"), 403, "permission_denied")
        self.assert_error(self.admin.get(self.url), 400, "validation_error", "language")
        self.assert_error(self.admin.post(self.url, {"language": "fr"}, format="json"), 400, "validation_error")
        self.assertEqual(DocumentTemplate.objects.get(kind="offer").title, "Angebot")
