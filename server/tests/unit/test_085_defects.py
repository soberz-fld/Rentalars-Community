# SPDX-License-Identifier: GPL-3.0-or-later
"""A reported defect makes a service case – or waits under Projekte → Anfragen (MAT-057, ADM-013).

* The automation "Defektmeldung → Servicefall" is there and active after the
  update; it can be changed or switched off.
* The case is internal (our own material) or, for customer material, for its
  owner; it names who reported the defect, has the photo among its files and
  points back to the report. One report makes one case.
* The action "put it under Projects → Inquiries" only lists the report; there
  it becomes a service case by hand or is taken off – never a project, never
  "taken over" like a mail.
* An internal service case needs no customer – in the form and in the API.
"""

from __future__ import annotations

import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.automations import engine
from rentalars.automations.forms import AutomationForm
from rentalars.automations.models import Action, Automation, AutomationRun, Recipient, RunStatus, Trigger
from rentalars.mail.fetching import assign_unknown
from rentalars.mail.imap import MailboxError
from rentalars.mail.models import UnknownTagMail
from rentalars.material import services as material_services
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import defect_cases, service_cases
from rentalars.projects.case_forms import ServiceCaseForm
from rentalars.projects.models import Project
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_customer, make_item, make_model, make_product, make_user
from tests.ui.base import UiTestCase


def png_file(name: str = "riss.png") -> SimpleUploadedFile:
    """A tiny real PNG image."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (238, 89, 31)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def default_rule() -> Automation:
    return Automation.objects.get(trigger=Trigger.DEFECT, action=Action.CREATE_CASE)


class DefectCase(RentalarsTestCase):
    """Luka from the warehouse reports defects of the SM58 0042 – our own material."""

    def setUp(self) -> None:
        super().setUp()
        self.luka = make_user("luka", roles=("Lager",))
        self.luka.first_name, self.luka.last_name = "Luka", "Lager"
        self.luka.save()
        self.product = make_product("S-058", "Mikrofon SM58")
        self.model = make_model("Shure SM58", self.product)
        self.item = make_item(self.model, 42, serial_number="SN-58-1")

    def report(self, description: str = "Gitterkorb eingedrückt", **fields: object) -> object:
        with self.captureOnCommitCallbacks(execute=True):
            return material_services.report_defect(self.item, description, user=self.luka, **fields)

    def case(self) -> Project:
        return Project.objects.get(source_defect__item=self.item)


class DefaultRuleTests(DefectCase):
    """ADM-013, MAT-057: the rule of the update – active, changeable."""

    def test_the_rule_is_there_and_active(self) -> None:
        rule = default_rule()
        self.assertTrue(rule.is_active)
        self.assertEqual(rule.name, "Defektmeldung → Servicefall")
        self.assertEqual((rule.subject, rule.text, rule.user), ("", "", None))

    def test_a_defect_makes_an_internal_service_case(self) -> None:
        report = self.report(photo=png_file(), context="Rücknahme 2027-0007")
        case = self.case()
        self.assertTrue(case.is_service_case)
        self.assertTrue(case.is_internal)
        self.assertIsNone(case.customer)
        self.assertEqual(case.source_defect, report)
        self.assertEqual(case.name, "Defekt 0042 Shure SM58")
        self.assertEqual(case.case_contact, "Luka Lager")
        self.assertIn("Gitterkorb eingedrückt", case.notes)
        self.assertIn("Exemplar: 0042 Shure SM58", case.notes)
        self.assertIn("Seriennummer: SN-58-1", case.notes)
        self.assertIn("Gefunden: Rücknahme 2027-0007", case.notes)
        self.assertIn("Gemeldet von Luka Lager am 01.03.2027", case.notes)
        self.assertIn(f"/material/items/{self.item.pk}/", case.notes)
        # The photo of the report is among the files of the case.
        photo = case.files.get()
        self.assertEqual(photo.title, "Foto der Defektmeldung")
        # MAT-090: the photo of the report is made anew – always a JPEG.
        self.assertTrue(photo.original_name.endswith(".jpg"))
        run = AutomationRun.objects.get(trigger=Trigger.DEFECT)
        self.assertEqual((run.status, run.project, run.recipient), (RunStatus.DONE, case, case.number))
        self.assertEqual(run.detail, f"Servicefall {case.number} angelegt.")
        self.assertEqual(run.event, "Defekt an 0042: Gitterkorb eingedrückt")
        # The item is defective, as before.
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "defective")

    def test_customer_material_makes_a_case_for_its_owner(self) -> None:
        """PRD-043: material of a customer – the case is the owner's, not internal."""
        owner = make_customer("Theater am Markt")
        self.product.owner = owner
        self.product.save()
        self.report()
        case = self.case()
        self.assertFalse(case.is_internal)
        self.assertEqual(case.customer, owner)

    def test_texts_and_person_responsible_of_the_rule(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        rule = default_rule()
        rule.subject = "Reparatur {id} ({kurzname}) – {gemeldet_von}"
        rule.text = "{beschreibung}\nGerät: {modell}, {produkt}, SN {seriennummer}\n{link}"
        rule.user = paula
        rule.save()
        self.report()
        case = self.case()
        self.assertEqual(case.name, "Reparatur 0042 (Shure SM58) – Luka Lager")
        self.assertEqual(
            case.notes.splitlines()[:2], ["Gitterkorb eingedrückt", "Gerät: Shure SM58, Mikrofon SM58, SN SN-58-1"]
        )
        self.assertEqual(case.manager, paula)
        # PRJ-090: the person responsible is told that the case is theirs.
        self.assertTrue(Notification.objects.filter(user=paula, project=case).exists())

    def test_english_placeholders_work_as_well(self) -> None:
        """UIX-029: {id}, {short_name}, {reported_by} …"""
        rule = default_rule()
        rule.subject = "{short_name} {id}: {description} ({found})"
        rule.save()
        self.report(context="Lager")
        self.assertEqual(self.case().name, "Shure SM58 0042: Gitterkorb eingedrückt (Lager)")

    def test_switched_off_nothing_happens(self) -> None:
        rule = default_rule()
        rule.is_active = False
        rule.save()
        self.report()
        self.assertFalse(Project.objects.filter(source_defect__isnull=False).exists())
        self.assertFalse(AutomationRun.objects.filter(trigger=Trigger.DEFECT).exists())

    def test_every_report_makes_its_own_case_but_only_one(self) -> None:
        first = self.report()
        second = self.report("Kabel abgerissen")
        self.assertEqual(Project.objects.filter(source_defect__in=[first, second]).count(), 2)
        with self.assertRaises(ValidationError):
            defect_cases.create_from_defect(first)
        # The same rule a second time for the same report: left out with the reason.
        run = AutomationRun.objects.filter(trigger=Trigger.DEFECT).first()
        outcome = engine._create_case(run, default_rule())
        self.assertEqual(outcome.status, RunStatus.SKIPPED)
        self.assertIn("wurde schon", outcome.detail)

    def test_a_report_on_return_starts_the_rule_as_well(self) -> None:
        """PCK-017: the report on return is a defect report like any other – the signal hears every path."""
        from rentalars.material.models import DefectReport

        with self.captureOnCommitCallbacks(execute=True):
            DefectReport.objects.create(item=self.item, description="Wackelkontakt", context="Rücknahme 2027-0001")
        self.assertEqual(self.case().name, "Defekt 0042 Shure SM58")
        self.assertEqual(self.case().case_contact, "")

    def test_notify_on_a_defect_links_the_item(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        Automation.objects.create(
            name="Defekt melden",
            trigger=Trigger.DEFECT,
            action=Action.NOTIFY,
            recipient=Recipient.USER,
            user=paula,
            subject="Defekt {id}",
        )
        self.report()
        notice = Notification.objects.get(user=paula, kind=Kind.AUTOMATION)
        self.assertEqual(notice.url, reverse("material:item_files", args=[self.item.pk]))


class InquiryActionTests(DefectCase):
    """MAT-057: "put it under Projects → Inquiries" – the report waits there until somebody decides."""

    def setUp(self) -> None:
        super().setUp()
        default_rule().delete()
        self.rule = Automation.objects.create(
            name="Defekte zur Anfrage", trigger=Trigger.DEFECT, action=Action.CREATE_INQUIRY
        )

    def test_the_report_waits_as_an_inquiry(self) -> None:
        report = self.report(photo=png_file())
        waiting = UnknownTagMail.objects.get(defect_report=report)
        self.assertEqual(waiting.subject, "Defekt 0042 Shure SM58: Gitterkorb eingedrückt")
        self.assertEqual((waiting.sender, waiting.tag, waiting.mailbox), ("Luka Lager", "", None))
        self.assertTrue(waiting.is_defect)
        self.assertTrue(waiting.is_inquiry)
        self.assertFalse(Project.objects.filter(source_defect=report).exists())
        # Only once per report.
        run = AutomationRun.objects.get(trigger=Trigger.DEFECT)
        self.assertEqual(engine._create_inquiry(run, self.rule).status, RunStatus.SKIPPED)

    def test_the_subject_of_the_rule(self) -> None:
        self.rule.subject = "Defekt {id} – {beschreibung}"
        self.rule.save()
        report = self.report()
        self.assertEqual(
            UnknownTagMail.objects.get(defect_report=report).subject, "Defekt 0042 – Gitterkorb eingedrückt"
        )

    def test_it_becomes_a_service_case_and_leaves_the_list(self) -> None:
        report = self.report(photo=png_file())
        waiting = UnknownTagMail.objects.get(defect_report=report)
        initial = service_cases.suggestions_from_inquiry(waiting)
        self.assertEqual(initial["name"], "Defekt 0042 Shure SM58")
        self.assertTrue(initial["is_internal"])
        case = service_cases.create_from_inquiry(waiting, **{**initial, "name": "SM58 Korb tauschen"})
        self.assertEqual((case.name, case.source_defect, case.is_internal), ("SM58 Korb tauschen", report, True))
        self.assertEqual(case.files.count(), 1)
        waiting.refresh_from_db()
        self.assertIsNotNone(waiting.resolved_at)

    def test_a_defect_is_no_mail_to_take_over(self) -> None:
        report = self.report()
        waiting = UnknownTagMail.objects.get(defect_report=report)
        project = service_cases.create_case(name="Irgendwas", customer=make_customer())
        with self.assertRaises(MailboxError):
            assign_unknown(waiting, project)

    def test_both_rules_make_the_case_and_deal_with_the_inquiry(self) -> None:
        """Both rules active: the case takes the inquiry off the list – whichever ran first."""
        Automation.objects.create(name="Fall", trigger=Trigger.DEFECT, action=Action.CREATE_CASE)
        report = self.report()
        self.assertTrue(Project.objects.filter(source_defect=report).exists())
        waiting = UnknownTagMail.objects.filter(defect_report=report).first()
        self.assertTrue(waiting is None or waiting.resolved_at is not None)
        # The other way round: the case first, the inquiry is left out.
        second = self.report("Kabel ab")
        run = AutomationRun.objects.filter(action=Action.CREATE_INQUIRY).first()
        run.data = {**run.data, "defect": second.pk}
        self.assertEqual(engine._create_inquiry(run, self.rule).status, RunStatus.SKIPPED)


class RuleFormTests(RentalarsTestCase):
    """ADM-013: the form of a rule for a defect report."""

    def data(self, **changes: object) -> dict[str, object]:
        return {
            "name": "Defekt → Fall",
            "is_active": "on",
            "trigger": "defect",
            "action": "create_case",
            "answer": "",
            "communication": "",
            **changes,
        }

    def test_create_case_with_title_text_and_person_responsible(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        form = AutomationForm(
            self.data(case_title="Defekt {id}", case_text="{beschreibung}", case_manager=paula.pk, user="")
        )
        self.assertTrue(form.is_valid(), form.errors)
        rule = form.save()
        self.assertEqual((rule.subject, rule.text, rule.user), ("Defekt {id}", "{beschreibung}", paula))
        # Opened again, the fields show what is stored.
        again = AutomationForm(instance=rule)
        self.assertEqual(
            (again.initial["case_title"], again.initial["case_text"], again.initial["case_manager"]),
            ("Defekt {id}", "{beschreibung}", paula.pk),
        )

    def test_only_the_actions_of_a_defect(self) -> None:
        form = AutomationForm(self.data(action="reply", reply_text="Danke"))
        self.assertFalse(form.is_valid())
        self.assertIn("action", form.errors)

    def test_an_inquiry_has_a_subject_and_no_text(self) -> None:
        form = AutomationForm(self.data(action="create_inquiry", inquiry_subject="Defekt {id}", case_text="weg"))
        self.assertTrue(form.is_valid(), form.errors)
        rule = form.save()
        self.assertEqual((rule.subject, rule.text, rule.user), ("Defekt {id}", "", None))

    def test_the_placeholders_of_a_defect(self) -> None:
        tokens = [token for token, _label in engine.placeholders_of(Trigger.DEFECT)]
        self.assertIn("{beschreibung}", tokens)
        self.assertIn("{gemeldet_von}", tokens)
        self.assertNotIn("{projekt}", tokens)  # no project


class InternalCaseTests(RentalarsTestCase):
    """MAT-057: an internal service case – our own material – needs no customer."""

    def test_internal_without_customer(self) -> None:
        case = service_cases.create_case(name="Lüfter Amp 3", is_internal=True, customer_required=True)
        self.assertTrue(case.is_internal)
        with self.assertRaises(ValidationError):
            service_cases.create_case(name="Ohne Kunde", customer_required=True)

    def test_internal_drops_a_customer(self) -> None:
        case = service_cases.create_case(name="Lüfter", is_internal=True, customer=make_customer())
        self.assertIsNone(case.customer)

    def test_a_customer_chosen_later_makes_it_the_customers_case(self) -> None:
        """Review finding 5: e.g. the app, which does not know "intern", sets the customer of such a case."""
        case = service_cases.create_case(name="Defekt 0042 SM58", is_internal=True)
        customer = make_customer("Stadttheater")
        case = service_cases.update_case(case, customer=customer)
        case.refresh_from_db()
        self.assertEqual((case.customer, case.is_internal), (customer, False))
        # Said explicitly, "intern" still wins.
        case = service_cases.update_case(case, customer=customer, is_internal=True)
        self.assertEqual((case.customer, case.is_internal), (None, True))

    def test_the_form(self) -> None:
        form = ServiceCaseForm({"name": "Lüfter Amp 3", "is_internal": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        form = ServiceCaseForm({"name": "Lüfter Amp 3"})
        self.assertFalse(form.is_valid())
        self.assertIn("customer", form.errors)


class DefectPageTests(UiTestCase):
    """The pages: the item's defects with their case, the list of inquiries, the form of a case from a report."""

    def setUp(self) -> None:
        super().setUp()
        default_rule().delete()
        Automation.objects.create(name="Zur Anfrage", trigger=Trigger.DEFECT, action=Action.CREATE_INQUIRY)
        self.item = make_item(make_model("Shure SM58", make_product("S-058", "Mikrofon SM58")), 42)
        with self.captureOnCommitCallbacks(execute=True):
            self.report = material_services.report_defect(self.item, "Gitterkorb eingedrückt", user=self.admin_user)

    def test_the_inquiry_list_offers_a_service_case_only(self) -> None:
        waiting = UnknownTagMail.objects.get(defect_report=self.report)
        page = self.assert_ok(self.client.get(reverse("mail:unknown_list")))
        self.assertIn("Defektmeldung", page)
        self.assertIn(f"{reverse('projects:case_create')}?inquiry={waiting.pk}", page)
        self.assertNotIn(f"{reverse('projects:create')}?inquiry={waiting.pk}", page)
        self.assertNotIn(reverse("mail:unknown_assign", args=[waiting.pk]), page)
        page = self.assert_ok(self.client.get(reverse("mail:unknown_list"), {"kind": "defect"}))
        self.assertIn("Gitterkorb eingedrückt", page)
        page = self.assert_ok(self.client.get(reverse("mail:unknown_list"), {"kind": "inquiry"}))
        self.assertNotIn("Gitterkorb eingedrückt", page)
        # A project cannot be made of it.
        self.assertEqual(self.client.get(reverse("projects:create"), {"inquiry": waiting.pk}).status_code, 404)

    def test_case_from_the_inquiry(self) -> None:
        waiting = UnknownTagMail.objects.get(defect_report=self.report)
        url = f"{reverse('projects:case_create')}?inquiry={waiting.pk}"
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Aus der Defektmeldung zu 0042 Shure SM58", page)
        self.assertIn('value="Defekt 0042 Shure SM58"', page)
        response = self.client.post(
            url, {"inquiry": waiting.pk, "name": "Korb tauschen", "is_internal": "on", "manager": self.admin_user.pk}
        )
        case = Project.objects.get(source_defect=self.report)
        self.assertRedirects(response, reverse("projects:case_detail", args=[case.pk]))
        self.assertTrue(case.is_internal)
        page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[case.pk])))
        self.assertIn("eigenes Material", page)

    def test_the_item_page_offers_and_then_names_the_case(self) -> None:
        files = reverse("material:item_files", args=[self.item.pk])
        page = self.assert_ok(self.client.get(files))
        create = f"{reverse('projects:case_create')}?defect={self.report.pk}"
        self.assertIn(create, page)
        page = self.assert_ok(self.client.get(create))
        self.assertIn('value="Defekt 0042 Shure SM58"', page)
        self.client.post(create, {"defect": self.report.pk, "name": "Korb", "is_internal": "on"})
        case = Project.objects.get(source_defect=self.report)
        page = self.assert_ok(self.client.get(files))
        self.assertIn(reverse("projects:case_detail", args=[case.pk]), page)
        self.assertNotIn(create, page)
        # The inquiry of the report is dealt with by the case.
        self.assertIsNotNone(UnknownTagMail.objects.get(defect_report=self.report).resolved_at)
        # Asked again, the form leads to the case.
        self.assertRedirects(self.client.get(create), reverse("projects:case_detail", args=[case.pk]))

    def test_the_rule_form_shows_the_fields_of_the_actions(self) -> None:
        page = self.assert_ok(self.client.get(reverse("automations:create")))
        self.assertIn('data-show-when="action:create_case"', page)
        self.assertIn('data-show-when="action:create_inquiry"', page)
        self.assertIn("Titel des Servicefalls", page)
        self.assertIn("{gemeldet_von}", page)


class DefectApiTests(ApiTestCase):
    """API-014: the new fields and the new trigger through the API."""

    def test_internal_case_and_its_defect(self) -> None:
        response = self.admin.post(f"{API}/service-cases", {"name": "Lüfter Amp 3", "is_internal": True}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["is_internal"])
        self.assertIsNone(response.json()["source_defect"])
        item = make_item(make_model("Shure SM58"), 42)
        with self.captureOnCommitCallbacks(execute=True):
            report = material_services.report_defect(item, "Korb eingedrückt")
        case = Project.objects.get(source_defect=report)
        data = self.admin.get(f"{API}/service-cases/{case.pk}").json()
        self.assertEqual((data["source_defect"], data["is_internal"], data["customer"]), (report.pk, True, None))

    def test_rules_of_defects(self) -> None:
        response = self.admin.post(
            f"{API}/automations",
            {"name": "Defekt → Anfrage", "trigger": "defect", "action": "create_inquiry", "subject": "{id}"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        response = self.admin.post(
            f"{API}/automations", {"name": "x", "trigger": "defect", "action": "reply", "text": "Hallo"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "action")

    def test_waiting_defects_in_the_list(self) -> None:
        default_rule().delete()
        Automation.objects.create(name="Anfrage", trigger=Trigger.DEFECT, action=Action.CREATE_INQUIRY)
        item = make_item(make_model("Shure SM58"), 42)
        with self.captureOnCommitCallbacks(execute=True):
            report = material_services.report_defect(item, "Korb eingedrückt")
        entries = self.admin.get(f"{API}/mail/unknown").json()
        entry = next(entry for entry in entries if entry["defect_report"] == report.pk)
        self.assertTrue(entry["is_inquiry"])
        project = service_cases.create_case(name="Irgendwas", customer=make_customer())
        response = self.admin.post(f"{API}/mail/unknown/{entry['id']}/assign", {"project": project.pk}, format="json")
        self.assert_error(response, 400, "validation_error")
        response = self.admin.post(
            f"{API}/service-cases", {"name": "Korb", "inquiry": entry["id"], "is_internal": True}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["source_defect"], report.pk)
