# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "ai": the automatic AI summaries and their settings, runs, dry run and switches. (EML-056, NFA-079)

The requirement: automatic AI summaries (e.g. every night) in projects and service cases when the project changed since
the last summary, and a check of the information security of the AI summaries. Every new operation is called (API-014); the fake model server stands in for the model.
"""

from __future__ import annotations

from rentalars.ai import auto
from rentalars.ai.models import AISettings, AISummary, AutoSummaryExclusion, AutoSummaryRun, Source
from rentalars.core.models import BackgroundJob
from tests.api.base import API
from tests.api.test_083_ai_api import AIApiTestCase


class AutoSummariesApiTests(AIApiTestCase):
    """``/ai/auto-summaries`` and below: administrators only."""

    url = f"{API}/ai/auto-summaries"

    def setUp(self) -> None:
        super().setUp()
        self.switch("summary", Source.LOCAL)

    def switch_automatic_on(self) -> dict:
        response = self.admin.patch(self.url, {"enabled": True, "consent": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_get_shows_the_defaults_and_the_notice_of_what_goes_where(self) -> None:
        """Off by default; the notice names the provider, the data classes sent and the ones never sent."""
        data = self.admin.get(self.url).json()
        self.assertFalse(data["enabled"])
        self.assertEqual(data["state"], "off")
        self.assertEqual((data["window_start"], data["window_end"]), ("01:00", "05:00"))
        self.assertTrue(data["notice"]["local"])
        self.assertFalse(data["notice"]["leaves_company"])
        self.assertTrue(data["notice"]["sent"])
        self.assertTrue(data["notice"]["never"])
        self.assertIn("iban", data["remove"])

    def test_switching_on_needs_the_consent_and_records_who(self) -> None:
        """Without ``consent`` 400 and still off; with it on, with the user and the provider noted."""
        response = self.admin.patch(self.url, {"enabled": True}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(AISettings.load().auto_enabled)
        data = self.switch_automatic_on()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["state"], "ok")
        self.assertEqual(data["enabled_by"], str(self.admin_user))
        self.assertIsNotNone(data["enabled_at"])

    def test_without_a_provider_it_cannot_be_switched_on(self) -> None:
        """Summaries off: there is nothing to agree to – 400, and nothing changes."""
        self.switch("summary", Source.OFF)
        response = self.admin.patch(self.url, {"enabled": True, "consent": True}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(AISettings.load().auto_enabled)

    def test_settings_are_validated_and_saved(self) -> None:
        """Numbers, windows and class lists go through the form of the page; a wrong value is a 400 with its field."""
        response = self.admin.patch(
            self.url,
            {"max_per_run": 7, "token_budget": 50000, "keep_versions": 2, "remove": ["iban", "secret"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        saved = AISettings.load()
        self.assertEqual((saved.auto_max_per_run, saved.auto_token_budget, saved.auto_keep_versions), (7, 50000, 2))
        self.assertEqual(sorted(saved.privacy_remove), ["iban", "secret"])
        self.assertEqual(self.admin.get(self.url).json()["remove"], saved.privacy_remove)
        bad = self.admin.patch(self.url, {"max_per_run": -3}, format="json")
        self.assertEqual(bad.status_code, 400, bad.content)
        self.assertEqual(AISettings.load().auto_max_per_run, 7)
        unknown = self.admin.patch(self.url, {"nonsense": 1}, format="json")
        self.assertEqual(unknown.status_code, 400, unknown.content)

    def test_dry_run_lists_the_projects_and_asks_no_model(self) -> None:
        """What would be summarised, and why; nothing stored, no request to the model."""
        self.switch_automatic_on()
        response = self.admin.post(f"{self.url}/dry-run")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["candidates"], 1)
        self.assertEqual(data["details"][0]["number"], self.project.number)
        self.assertEqual(self.fake.requests, [])
        self.assertFalse(AISummary.objects.exists())

    def test_run_now_summarises_and_the_runs_list_shows_it(self) -> None:
        """202 and a task; afterwards the summary is there, marked automatic, and the run is listed."""
        refused = self.admin.post(f"{self.url}/run")
        self.assertEqual(refused.status_code, 409, refused.content)
        self.switch_automatic_on()
        response = self.admin.post(f"{self.url}/run")
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(BackgroundJob.objects.get(pk=response.json()["job"]).status, "done")
        self.assertTrue(AISummary.objects.get().is_automatic)
        runs = self.admin.get(f"{self.url}/runs").json()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["summarised"], 1)
        self.assertEqual(AutoSummaryRun.objects.count(), 1)

    def test_only_administrators(self) -> None:
        """Settings, runs, dry run and run now need the right to administer – 403 for a project manager."""
        manager = self.client_for("pl", "Projektleitung")
        self.assertEqual(manager.get(self.url).status_code, 403)
        self.assertEqual(manager.patch(self.url, {"enabled": False}, format="json").status_code, 403)
        self.assertEqual(manager.get(f"{self.url}/runs").status_code, 403)
        self.assertEqual(manager.post(f"{self.url}/dry-run").status_code, 403)
        self.assertEqual(manager.post(f"{self.url}/run").status_code, 403)


class ProjectSummaryApiTests(AIApiTestCase):
    """The summary of a project tells how it was made; the project can be taken out of the nightly job."""

    def url(self) -> str:
        return f"{API}/projects/{self.project.pk}/correspondence-summary"

    def make_automatic(self) -> None:
        self.switch("summary", Source.LOCAL)
        ai_settings = AISettings.load()
        auto.switch_on(ai_settings, self.admin_user)
        ai_settings.save()
        self.assertIsNotNone(auto.run(ignore_window=True))

    def test_get_tells_automatic_format_and_versions(self) -> None:
        """``automatic``, ``format: plain``, the history, and the state of the switches."""
        self.make_automatic()
        data = self.admin.get(self.url()).json()
        self.assertTrue(data["summary"]["automatic"])
        self.assertEqual(data["summary"]["format"], "plain")
        self.assertTrue(data["summary"]["covers_locked"])
        self.assertEqual(data["versions"], [])
        self.assertTrue(data["auto_summaries"]["on"])
        self.assertFalse(data["auto_summaries"]["project_excluded"])

    def test_patch_takes_the_project_out_and_back_in(self) -> None:
        """``auto_summaries: false`` excludes the project; ``true`` takes the exclusion off."""
        response = self.admin.patch(self.url(), {"auto_summaries": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["project_excluded"])
        self.assertTrue(AutoSummaryExclusion.objects.filter(project=self.project).exists())
        response = self.admin.patch(self.url(), {"auto_summaries": True}, format="json")
        self.assertFalse(response.json()["project_excluded"])
        self.assertFalse(AutoSummaryExclusion.objects.exists())
        self.assertEqual(self.admin.patch(self.url(), {"auto_summaries": "no"}, format="json").status_code, 400)

    def test_patch_needs_the_right_to_change_and_to_read_all_messages(self) -> None:
        """Nur-Lesen reads the correspondence but may not change the project – 403."""
        reader = self.client_for("leser", "Nur-Lesen")
        self.assertEqual(reader.patch(self.url(), {"auto_summaries": False}, format="json").status_code, 403)
        crew = self.client_for("crew", "Crew")
        # A crew member does not even see a project he is not on (AUT-020): 404, as for every project endpoint.
        self.assertIn(crew.patch(self.url(), {"auto_summaries": False}, format="json").status_code, (403, 404))
        self.assertFalse(AutoSummaryExclusion.objects.exists())


class CustomerSwitchApiTests(AIApiTestCase):
    """``/customers/{id}/ai-summaries``: no automatic summaries for any project of a customer."""

    def url(self) -> str:
        return f"{API}/customers/{self.project.customer_id}/ai-summaries"

    def test_get_and_patch(self) -> None:
        """On by default; ``false`` excludes the customer, ``true`` takes it off again."""
        self.assertTrue(self.admin.get(self.url()).json()["auto_summaries"])
        response = self.admin.patch(self.url(), {"auto_summaries": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["auto_summaries"])
        self.assertFalse(self.admin.get(self.url()).json()["auto_summaries"])
        self.assertTrue(AutoSummaryExclusion.objects.filter(customer=self.project.customer).exists())
        self.admin.patch(self.url(), {"auto_summaries": True}, format="json")
        self.assertFalse(AutoSummaryExclusion.objects.exists())

    def test_wrong_value_and_missing_right(self) -> None:
        """A non-boolean is a 400; reading customers is not enough to change the switch."""
        self.assertEqual(self.admin.patch(self.url(), {"auto_summaries": 5}, format="json").status_code, 400)
        reader = self.client_for("leser", "Nur-Lesen")
        self.assertEqual(reader.get(self.url()).status_code, 200)
        self.assertEqual(reader.patch(self.url(), {"auto_summaries": False}, format="json").status_code, 403)
        self.assertEqual(self.admin.get(f"{API}/customers/999999/ai-summaries").status_code, 404)
