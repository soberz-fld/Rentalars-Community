# SPDX-License-Identifier: GPL-3.0-or-later
"""Standard-Automationen: the automations that came with Rentalars get a stable key.

* ``Automation.default_key``: empty for the company's own rules; for the four rules Rentalars brought – the three
  of the service cases (PRJ-112) and "Defektmeldung → Servicefall" (MAT-057) – their key, by which
  "Standard-Automationen wiederherstellen" knows which ones are missing (``automations.defaults``).
* The existing defaults are found as the earlier migration made them: without a creator (rules made in the browser
  or through the API have one), by their name in German or English – or, renamed, by trigger, condition and action.
  A deleted default stays deleted; one that was changed in name *and* rule is taken for an own rule.

The update creates no automation and changes no value a user sees – no name, no condition, no action, not whether a
rule is active – and writes no entry in the change log. Backwards the column is dropped.
"""

from django.db import migrations, models

#: (key, trigger, status, action, new status of the case, German name, English name) – as the defaults came;
#: frozen here, like every migration, whatever ``automations.defaults`` says later.
KNOWN = (
    (
        "case_closing_due",
        "case_follow_up",
        "closing",
        "case_status",
        "done",
        "Wartet auf Schließen: zum Termin schließen",
        "Waiting to close: close at the time set",
    ),
    (
        "case_closing_communication",
        "case_communication",
        "closing",
        "case_status",
        "open",
        "Wartet auf Schließen: bei neuer Kommunikation wieder öffnen",
        "Waiting to close: open again on new communication",
    ),
    (
        "case_backlog_due",
        "case_follow_up",
        "backlog",
        "case_status",
        "open",
        "Rückstand: zur Wiedervorlage wieder öffnen",
        "Backlog: open again when the follow-up is due",
    ),
    ("defect_case", "defect", "", "create_case", "", "Defektmeldung → Servicefall", "Defect report → service case"),
)


def give_keys(apps, schema_editor):
    """Give each default that is there its key – all by name first, then the rest by their rule; create nothing."""
    rule_model = apps.get_model("automations", "Automation")
    for by_name in (True, False):
        for key, trigger, status, action, new_status, german, english in KNOWN:
            if rule_model.objects.filter(default_key=key).exists():
                continue
            candidates = rule_model.objects.filter(created_by__isnull=True, default_key__isnull=True).order_by("pk")
            if by_name:
                rule = candidates.filter(name__in=(german, english)).first()
            else:
                rule = candidates.filter(
                    trigger=trigger, status=status, action=action, new_case_status=new_status
                ).first()
            if rule is not None:
                # A plain update: no signal, no entry in the change log, nothing else of the rule touched.
                rule_model.objects.filter(pk=rule.pk).update(default_key=key)


def drop_keys(apps, schema_editor):
    """Backwards: forget the keys (the column goes right after)."""
    apps.get_model("automations", "Automation").objects.exclude(default_key=None).update(default_key=None)


class Migration(migrations.Migration):
    """Add ``Automation.default_key`` and give the existing defaults theirs."""

    dependencies = [
        ("automations", "0001_squashed_0003_defects_085"),
    ]

    operations = [
        migrations.AddField(
            model_name="automation",
            name="default_key",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="Set for the automations that come with Rentalars.",
                max_length=40,
                null=True,
                unique=True,
                verbose_name="default automation",
            ),
        ),
        migrations.RunPython(give_keys, drop_keys),
    ]
