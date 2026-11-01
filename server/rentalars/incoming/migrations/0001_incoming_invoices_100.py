# SPDX-License-Identifier: GPL-3.0-or-later
"""Incoming invoices and their positions."""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import rentalars.incoming.models


class Migration(migrations.Migration):
    """The tables of the register."""

    initial = True

    dependencies = [
        ("core", "0024_notification_defaults_093"),
        ("masterdata", "0001_squashed_0012_fleet_090"),
        ("material", "0009_storage_spot_094"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IncomingInvoice",
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
                    "supplier_name",
                    models.CharField(
                        blank=True,
                        max_length=120,
                        verbose_name="supplier as named on the invoice",
                    ),
                ),
                (
                    "invoice_number",
                    models.CharField(blank=True, max_length=60, verbose_name="invoice number"),
                ),
                (
                    "invoice_date",
                    models.DateField(blank=True, null=True, verbose_name="invoice date"),
                ),
                (
                    "due_date",
                    models.DateField(blank=True, null=True, verbose_name="due date"),
                ),
                (
                    "currency",
                    models.CharField(default="EUR", max_length=3, verbose_name="currency"),
                ),
                (
                    "exchange_rate",
                    models.DecimalField(
                        decimal_places=6,
                        default=Decimal("1"),
                        help_text="Euros for one unit of the currency; only for an invoice in another currency than the euro.",
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.000001"))],
                        verbose_name="exchange rate",
                    ),
                ),
                (
                    "total_net",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="total net",
                    ),
                ),
                (
                    "total_tax",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="tax",
                    ),
                ),
                (
                    "total_gross",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="total gross",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "open"),
                            ("checked", "checked"),
                            ("booked_in", "booked in"),
                        ],
                        default="open",
                        max_length=10,
                        verbose_name="status",
                    ),
                ),
                (
                    "allocation_key",
                    models.CharField(
                        choices=[
                            ("value", "by value"),
                            ("quantity", "by quantity"),
                            ("weight", "by weight"),
                        ],
                        default="value",
                        help_text="By what the ancillary costs of this invoice are spread over its goods.",
                        max_length=10,
                        verbose_name="ancillary costs are spread",
                    ),
                ),
                ("note", models.TextField(blank=True, verbose_name="note")),
                (
                    "file",
                    models.FileField(
                        max_length=200,
                        upload_to=rentalars.incoming.models.invoice_file_path,
                        verbose_name="file",
                    ),
                ),
                (
                    "original_name",
                    models.CharField(max_length=255, verbose_name="file name"),
                ),
                (
                    "size",
                    models.PositiveBigIntegerField(default=0, verbose_name="size"),
                ),
                (
                    "content_hash",
                    models.CharField(blank=True, db_index=True, editable=False, max_length=64),
                ),
                (
                    "reading_state",
                    models.CharField(
                        choices=[
                            ("none", "not read"),
                            ("running", "being read"),
                            ("done", "read"),
                            ("failed", "not readable"),
                        ],
                        default="none",
                        editable=False,
                        max_length=10,
                    ),
                ),
                ("reading", models.JSONField(blank=True, default=dict, editable=False)),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="uploaded",
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
                    ),
                ),
                (
                    "reading_job",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.backgroundjob",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incoming_invoices",
                        to="masterdata.supplier",
                        verbose_name="supplier",
                    ),
                ),
            ],
            options={
                "verbose_name": "incoming invoice",
                "verbose_name_plural": "incoming invoices",
                "ordering": ["-invoice_date", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="InvoicePosition",
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
                    "place",
                    models.PositiveSmallIntegerField(default=1, verbose_name="position"),
                ),
                (
                    "description",
                    models.CharField(max_length=250, verbose_name="description"),
                ),
                (
                    "article_number",
                    models.CharField(
                        blank=True,
                        max_length=120,
                        verbose_name="supplier's article number",
                    ),
                ),
                (
                    "manufacturer",
                    models.CharField(blank=True, max_length=120, verbose_name="manufacturer"),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=3,
                        default=Decimal("1"),
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                        verbose_name="quantity",
                    ),
                ),
                (
                    "unit_price_net",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        help_text="In the currency of the invoice. For ancillary cost: the amount; a discount is negative.",
                        max_digits=12,
                        null=True,
                        verbose_name="unit price (net)",
                    ),
                ),
                (
                    "tax_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0")),
                            django.core.validators.MaxValueValidator(Decimal("100")),
                        ],
                        verbose_name="tax rate (%)",
                    ),
                ),
                (
                    "position_type",
                    models.CharField(
                        choices=[
                            ("goods", "material"),
                            ("ancillary", "ancillary cost"),
                            ("other", "other"),
                        ],
                        default="goods",
                        max_length=10,
                        verbose_name="kind of position",
                    ),
                ),
                (
                    "asset_kind",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("merchandise", "merchandise"),
                            ("low_value", "low-value asset (GWG)"),
                            ("fixed_asset", "fixed asset"),
                        ],
                        help_text="Empty: by the limit in the settings – up to it a low-value asset, above it a fixed asset.",
                        max_length=12,
                        verbose_name="kind of asset",
                    ),
                ),
                (
                    "useful_life_months",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="For a fixed asset. Empty: the standard useful life of the settings.",
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(600),
                        ],
                        verbose_name="useful life (months)",
                    ),
                ),
                (
                    "weight_kg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        help_text="Only to spread ancillary costs by weight. Empty: the weight of the model.",
                        max_digits=8,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                        verbose_name="weight of one piece (kg)",
                    ),
                ),
                (
                    "serial_numbers",
                    models.TextField(blank=True, verbose_name="serial numbers"),
                ),
                (
                    "suggestion",
                    models.JSONField(blank=True, default=dict, editable=False),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="positions",
                        to="incoming.incominginvoice",
                    ),
                ),
                (
                    "material_model",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="incoming_positions",
                        to="material.materialmodel",
                    ),
                ),
                (
                    "storage_location",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="masterdata.storagelocation",
                    ),
                ),
            ],
            options={
                "verbose_name": "invoice position",
                "verbose_name_plural": "invoice positions",
                "ordering": ["invoice", "place", "pk"],
            },
        ),
        migrations.AddIndex(
            model_name="incominginvoice",
            index=models.Index(fields=["status"], name="incoming_status_idx"),
        ),
    ]
