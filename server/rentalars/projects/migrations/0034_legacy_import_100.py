# SPDX-License-Identifier: GPL-3.0-or-later
"""The records of the legacy import (batch and old invoice)."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Creates ``LegacyImportBatch`` and ``LegacyImportItem``."""

    dependencies = [
        ("core", "0024_notification_defaults_093"),
        ("customers", "0009_split_contact_names_095"),
        ("documents", "0007_free_documents_095"),
        ("projects", "0033_text_lines_095"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LegacyImportBatch",
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
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now, verbose_name="started"),
                ),
                (
                    "used_ai",
                    models.BooleanField(default=False, verbose_name="read with AI"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.backgroundjob",
                    ),
                ),
            ],
            options={
                "verbose_name": "import of old invoices",
                "verbose_name_plural": "imports of old invoices",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="LegacyImportItem",
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
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "original_name",
                    models.CharField(max_length=200, verbose_name="file"),
                ),
                (
                    "sha256",
                    models.CharField(db_index=True, max_length=64, verbose_name="checksum"),
                ),
                ("size", models.PositiveIntegerField(default=0)),
                ("stored_name", models.CharField(blank=True, max_length=60)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("uploaded", "waiting to be read"),
                            ("reading", "being read"),
                            ("read", "to be checked"),
                            ("duplicate", "already imported"),
                            ("imported", "taken over"),
                            ("skipped", "skipped"),
                            ("undone", "import undone"),
                        ],
                        default="uploaded",
                        max_length=10,
                        verbose_name="state",
                    ),
                ),
                ("message", models.CharField(blank=True, max_length=500)),
                ("proposal", models.JSONField(blank=True, default=dict)),
                (
                    "invoice_number",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=60,
                        verbose_name="invoice number",
                    ),
                ),
                (
                    "invoice_date",
                    models.DateField(blank=True, null=True, verbose_name="invoice date"),
                ),
                ("customer_created", models.BooleanField(default=False)),
                ("paid", models.BooleanField(default=False, verbose_name="paid")),
                (
                    "paid_on",
                    models.DateField(blank=True, null=True, verbose_name="paid on"),
                ),
                (
                    "imported_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="taken over"),
                ),
                ("audit_mark", models.PositiveBigIntegerField(default=0)),
                ("undone_at", models.DateTimeField(blank=True, null=True)),
                ("source", models.CharField(blank=True, max_length=10)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="projects.legacyimportbatch",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_items",
                        to="customers.customer",
                    ),
                ),
                (
                    "document",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_item",
                        to="documents.document",
                    ),
                ),
                (
                    "imported_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "merge_into",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="joined",
                        to="projects.legacyimportitem",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_items",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "old invoice",
                "verbose_name_plural": "old invoices",
                "ordering": ["batch_id", "position", "id"],
            },
        ),
    ]
