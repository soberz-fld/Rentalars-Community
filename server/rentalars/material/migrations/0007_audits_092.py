# SPDX-License-Identifier: GPL-3.0-or-later
"""Audits of material items and their to-dos (audits).

``AuditSettings`` – Einstellungen → Audits: the interval (24 months) and the quick picks for to-dos; an English
company gets the quick picks in English (UIX-029), everybody else the German ones. ``ItemAudit`` – one audit of one
item. ``ItemTodo`` – a small thing to be done on an item, noted in an audit or on the item's page.
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

GERMAN_QUICK_TODOS = "Label fehlt\nKlett fehlt\nBeschädigt\nReinigen\nTeile fehlen"
ENGLISH_QUICK_TODOS = "Label missing\nVelcro missing\nDamaged\nClean\nParts missing"


def create_audit_settings(apps, schema_editor):
    """The row of the audit settings, with the quick picks in the company's language."""
    AuditSettings = apps.get_model("material", "AuditSettings")
    CompanyProfile = apps.get_model("core", "CompanyProfile")
    if AuditSettings.objects.filter(pk=1).exists():
        return
    company = CompanyProfile.objects.filter(pk=1).first()
    english = company is not None and company.document_language == "en"
    AuditSettings.objects.create(pk=1, quick_todos=ENGLISH_QUICK_TODOS if english else GERMAN_QUICK_TODOS)


class Migration(migrations.Migration):

    dependencies = [
        ("material", "0006_vehicles_090"),
        ("core", "0022_approval_reminders_091"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "interval_months",
                    models.PositiveSmallIntegerField(
                        default=24,
                        help_text="An item is due again this long after its last audit; one never audited this long after it was created in Rentalars. 0: off – no audit is ever due; audits and to-dos can still be noted.",
                        validators=[django.core.validators.MaxValueValidator(120)],
                        verbose_name="audit interval (months)",
                    ),
                ),
                (
                    "quick_todos",
                    models.TextField(
                        blank=True,
                        default="Label fehlt\nKlett fehlt\nBeschädigt\nReinigen\nTeile fehlen",
                        help_text="One per line, at most 12 – offered as buttons in the audit and on the page of an item.",
                        verbose_name="quick picks for to-dos",
                    ),
                ),
            ],
            options={
                "verbose_name": "audit settings",
                "verbose_name_plural": "audit settings",
            },
        ),
        migrations.CreateModel(
            name="ItemAudit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "audited_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="audited"
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[("ok", "in order"), ("todos", "with to-dos")],
                        default="ok",
                        max_length=10,
                        verbose_name="result",
                    ),
                ),
                (
                    "note",
                    models.CharField(blank=True, max_length=250, verbose_name="note"),
                ),
                (
                    "audited_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="audited by",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audits",
                        to="material.materialitem",
                        verbose_name="item",
                    ),
                ),
            ],
            options={
                "verbose_name": "audit",
                "verbose_name_plural": "audits",
                "ordering": ["-audited_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ItemTodo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text", models.CharField(max_length=200, verbose_name="to-do")),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="noted",
                    ),
                ),
                (
                    "done_at",
                    models.DateTimeField(
                        blank=True, editable=False, null=True, verbose_name="done"
                    ),
                ),
                (
                    "audit",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="todos",
                        to="material.itemaudit",
                        verbose_name="noted in the audit",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="noted by",
                    ),
                ),
                (
                    "done_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="done by",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="todos",
                        to="material.materialitem",
                        verbose_name="item",
                    ),
                ),
            ],
            options={
                "verbose_name": "to-do",
                "verbose_name_plural": "to-dos",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="itemaudit",
            index=models.Index(
                fields=["item", "audited_at"], name="item_audit_latest_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="itemtodo",
            index=models.Index(fields=["item", "done_at"], name="item_todo_open_idx"),
        ),
        migrations.RunPython(create_audit_settings, migrations.RunPython.noop),
    ]
