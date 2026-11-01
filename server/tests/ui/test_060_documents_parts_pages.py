# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for the prices and documents of a whole project with subprojects (PRJ-045, PRJ-046, PRJ-049, PRJ-060).

The festival of ``tests.unit.test_060_documents_parts``: the whole project
"Stadtfest" with the stages "Marktplatz" and "Schlosspark".
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight
from rentalars.documents.models import Document
from rentalars.projects import services as project_services
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.helpers import ALL_RIGHTS, make_user
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_060_documents_parts import billing_family


def content_of(response: Any) -> bytes:
    """The body of a file response, streamed or not."""
    streamed = getattr(response, "streaming_content", None)
    return b"".join(streamed) if streamed is not None else response.content


def kinds_offered(page: str) -> list[str]:
    """The kinds of document the form of the documents tab offers."""
    start = page.index('name="kind"')
    select = page[start : page.index("</select>", start)]
    return [part.split('"')[0] for part in select.split('value="')[1:]]


class FamilyPagesCase(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        family = billing_family()
        self.whole, self.market, self.park = family.whole, family.market, family.park

    def external_with_prices(self, *, park: str = ProjectAccessLevel.NONE) -> Any:
        """A browser of somebody limited to assigned projects: the whole project, but not the Schlosspark."""
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            special_rights=[SpecialRight.PRICES],
            project_scope=ProjectScope.ASSIGNED,
        )
        user = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=user, level=ProjectAccessLevel.EDIT)
        ProjectMembership.objects.create(project=self.park, user=user, level=park)
        return self.browser_of(user)


class DocumentsTabTests(FamilyPagesCase):
    """PRJ-045: offer, order confirmation and invoice at the whole project; the tab of a part leads there."""

    def test_the_tab_of_a_part_points_to_the_whole_project(self) -> None:
        url = reverse("documents:list", args=[self.market.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn(
            f"Angebot, Auftragsbestätigung und Rechnung entstehen am Gesamtprojekt {self.whole.number} – mit allen "
            "Teilprojekten.",
            page,
        )
        self.assertIn(f'href="{reverse("documents:list", args=[self.whole.pk])}"', page)
        self.assertIn(f"Zu den Dokumenten von {self.whole.number} Stadtfest", page)
        self.assertEqual(kinds_offered(page), ["delivery_note", "crew_sheet"])
        # Sent anyway, the invoice is refused with the same clear words.
        refused = self.client.post(reverse("documents:create", args=[self.market.pk]), {"kind": "invoice"}, follow=True)
        self.assertIn(
            f"Angebot, Auftragsbestätigung und Rechnung entstehen am Gesamtprojekt {self.whole.number} – mit allen "
            "Teilprojekten.",
            self.messages_of(refused),
        )
        draft = self.client.post(reverse("documents:preview", args=[self.market.pk]), {"kind": "offer"}, follow=True)
        self.assertEqual(draft.status_code, 200)
        self.assertFalse(draft.content.startswith(b"%PDF"))
        # Its delivery note is made here.
        data = form_data(self.client.get(url), "kind", kind="delivery_note")
        made = self.client.post(reverse("documents:create", args=[self.market.pk]), data, follow=True)
        self.assertIn("Lieferschein LS-2027-0001 erstellt.", self.messages_of(made))
        self.assertEqual(Document.objects.get().project, self.market)

    def test_the_tab_of_the_whole_project_names_its_parts_and_makes_the_invoice(self) -> None:
        cancelled = project_services.create_subproject(self.whole, name="Bühne Hof")
        project_services.change_status(cancelled, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        url = reverse("documents:list", args=[self.whole.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("jedes als eigener Block mit Zwischensumme", page)
        self.assertIn(f"Storniert, daher nicht enthalten: {cancelled.number} Bühne Hof", page)
        self.assertIn(f'<a href="{reverse("documents:list", args=[self.market.pk])}">{self.market.number} Bühne', page)
        self.assertIn("invoice", kinds_offered(page))

        data = form_data(self.client.get(url), "kind", kind="invoice")
        draft = self.client.post(reverse("documents:preview", args=[self.whole.pk]), data)
        self.assertTrue(draft.content.startswith(b"%PDF"))
        made = self.client.post(reverse("documents:create", args=[self.whole.pk]), data, follow=True)
        self.assertIn("Rechnung RE-2027-0001 erstellt.", self.messages_of(made))
        invoice = Document.objects.get()
        self.assertEqual((invoice.project, str(invoice.gross_total)), (self.whole, "1134.02"))
        page = self.assert_ok(self.client.get(url))
        self.assertIn("1.134,02", page)
        self.assertTrue(content_of(self.client.get(reverse("documents:file", args=[invoice.pk]))).startswith(b"%PDF"))
        xml = content_of(self.client.get(reverse("documents:xml", args=[invoice.pk])))
        self.assertIn(b'<cbc:PayableAmount currencyID="EUR">1134.02</cbc:PayableAmount>', xml)
        self.assertIn(b"<cbc:Name>Mischpult</cbc:Name>", xml)

    def test_who_may_not_read_every_part_cannot_make_the_invoice(self) -> None:
        external = self.external_with_prices()
        url = reverse("documents:list", args=[self.whole.pk])
        page = self.assert_ok(external.get(url))
        # The part the user may not read is named, but not linked.
        self.assertIn(f"<li>{self.park.number} Bühne Schlosspark</li>", page)
        refused = external.post(reverse("documents:create", args=[self.whole.pk]), {"kind": "invoice"}, follow=True)
        self.assertIn(
            f"Dieses Dokument enthält alle Teilprojekte, und {self.park.number} darfst du nicht lesen. Bitte "
            "jemanden, der alle Teilprojekte lesen darf, es zu erstellen.",
            self.messages_of(refused),
        )
        self.assertFalse(Document.objects.exists())
        made = external.post(reverse("documents:create", args=[self.whole.pk]), {"kind": "delivery_note"}, follow=True)
        self.assertIn("Lieferschein LS-2027-0001 erstellt.", self.messages_of(made))


class PriceOverviewPageTests(FamilyPagesCase):
    """PRJ-035, PRJ-036, DOK-009 with PRJ-046: the price overview of a whole project and of a part."""

    def test_the_whole_project_shows_its_own_lines_every_part_and_the_sum_of_all(self) -> None:
        url = reverse("projects:price_overview", args=[self.whole.pk])
        page = self.assert_ok(self.client.get(url))
        market = self.market.number
        own = page.index(f"Gemeinsame Positionen des Gesamtprojekts {self.whole.number}")
        first = page.index(f'data-price-block="{self.market.pk}"')
        second = page.index(f'data-price-block="{self.park.pk}"')
        totals = page.index("Summen des Gesamtprojekts mit allen Teilprojekten")
        self.assertLess(own, first)
        self.assertLess(first, second)
        self.assertLess(second, totals)
        block = page[first:second]
        self.assertIn(f"Teilprojekt {market} Bühne Marktplatz", block)
        self.assertIn("10.03.–12.03.2027 · Marktplatz", block)
        self.assertIn("<h3>", block)  # the groups of a part one level below its heading
        self.assertIn("Licht", block)
        self.assertIn(f"Summe Teilprojekt {market} Bühne Marktplatz", block)
        self.assertIn('data-copy="158,00"', block)
        # PRJ-060: the taken-over spotlights stand in the Schlosspark, not charged there.
        taken = page[second:totals]
        self.assertIn("übernommen", taken)
        self.assertIn(f"berechnet in {market}", taken)
        self.assertIn("nicht berechnet", taken)
        summary = page[totals:]
        for text in ("500,00", "158,00", "300,00", 'data-copy="958,00"', "172,52", "3,50", 'data-copy="1.134,02"'):
            self.assertIn(text, summary)
        groups = self.assert_ok(self.client.get(url, {"detail": "groups"}))
        self.assertIn("Enthält: 1 × Mischpult", groups)
        self.assertNotIn("L-100", groups)
        self.assertIn(f'href="{reverse("projects:price_overview", args=[self.market.pk])}?detail=groups"', groups)

    def test_files_of_the_whole_project_have_the_parts(self) -> None:
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.whole.pk])).content.decode()
        self.assertIn(f"Teilprojekt {self.market.number} Bühne Marktplatz, 10.03.–12.03.2027", csv)
        self.assertIn(f"{self.park.number} › Ton", csv)
        self.assertIn("Summe brutto;;;;;;;;;1134,02", csv)
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.whole.pk]), {"detail": "groups"})
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_a_part_shows_itself_with_a_hint_to_the_whole_project(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.market.pk])))
        self.assertIn(f"Teil von {self.whole.number} Stadtfest; Summe aller Teile im Gesamtprojekt.", page)
        self.assertIn(f'href="{reverse("projects:price_overview", args=[self.whole.pk])}"', page)
        self.assertIn("Preisübersicht des Gesamtprojekts", page)
        self.assertNotIn("Mischpult", page)
        self.assertNotIn("Summen des Gesamtprojekts", page)
        self.assertIn('data-copy="158,00"', page)

    def test_parts_the_user_may_not_read_are_left_out_and_counted(self) -> None:
        external = self.external_with_prices()
        page = self.assert_ok(external.get(reverse("projects:price_overview", args=[self.whole.pk])))
        self.assertIn("1 Teilprojekt ist nicht enthalten, weil du es nicht lesen darfst.", page)
        self.assertNotIn("Mischpult", page)
        self.assertIn('data-copy="658,00"', page)
        csv = external.get(reverse("projects:price_overview_csv", args=[self.whole.pk])).content.decode()
        self.assertNotIn("Schlosspark", csv)
        # Somebody who knows only the Marktplatz sees the hint, but no way into the whole project.
        stage = make_user("sina", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.market, user=stage, level=ProjectAccessLevel.READ)
        page = self.assert_ok(self.browser_of(stage).get(reverse("projects:price_overview", args=[self.market.pk])))
        self.assertIn(f"Teil von {self.whole.number} Stadtfest; Summe aller Teile im Gesamtprojekt.", page)
        self.assertNotIn("Preisübersicht des Gesamtprojekts", page)
        documents = self.assert_ok(self.browser_of(stage).get(reverse("documents:list", args=[self.market.pk])))
        self.assertNotIn(f'href="{reverse("documents:list", args=[self.whole.pk])}"', documents)
