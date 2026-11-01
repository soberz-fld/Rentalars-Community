# SPDX-License-Identifier: GPL-3.0-or-later
"""Depreciation, used sale from stock: the setting "memory value" and the table of sales out of the stock."""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """One setting field and one new table; reversing drops both."""

    dependencies = [
        ("customers", "0009_split_contact_names_095"),
        ("masterdata", "0001_squashed_0012_fleet_090"),
        ("material", "0012_partial_purchase_date_100"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="assetsettings",
            name="keep_memory_value",
            field=models.BooleanField(
                default=False,
                help_text="A fixed asset that is fully depreciated stays in the books with 1 € (Erinnerungswert) until it is sold or retired. Off: the book value goes down to 0 €.",
                verbose_name="keep a memory value of 1 €",
            ),
        ),
        migrations.CreateModel(
            name="SaleFromStock",
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
                    "quantity",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Pieces sold; 1 for an item.",
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="quantity",
                    ),
                ),
                ("sold_on", models.DateField(verbose_name="sold on")),
                (
                    "buyer_name",
                    models.CharField(
                        help_text="A customer or contact, or a name typed in. Kept as written.",
                        max_length=200,
                        verbose_name="buyer",
                    ),
                ),
                (
                    "net_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                        verbose_name="price (net)",
                    ),
                ),
                (
                    "tax_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=5,
                        verbose_name="tax rate in percent",
                    ),
                ),
                ("note", models.TextField(blank=True, verbose_name="note")),
                (
                    "asset_kind",
                    models.CharField(blank=True, max_length=12, verbose_name="kind of asset"),
                ),
                (
                    "cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="acquisition cost of the pieces sold (net)",
                    ),
                ),
                (
                    "accumulated_depreciation",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="depreciation until the sale",
                    ),
                ),
                (
                    "book_value",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=12,
                        verbose_name="book value at the sale",
                    ),
                ),
                (
                    "book_value_basis",
                    models.CharField(default="calculated", max_length=12, verbose_name="book value"),
                ),
                (
                    "gain_loss",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        help_text="Price minus book value; a negative amount is a loss.",
                        max_digits=12,
                        verbose_name="gain or loss",
                    ),
                ),
                (
                    "previous_status",
                    models.CharField(max_length=12, verbose_name="status before the sale"),
                ),
                (
                    "previous_reason",
                    models.CharField(
                        blank=True,
                        max_length=250,
                        verbose_name="reason before the sale",
                    ),
                ),
                (
                    "row_quantity_before",
                    models.PositiveIntegerField(default=1, verbose_name="quantity of the row before the sale"),
                ),
                (
                    "item_left",
                    models.BooleanField(
                        default=True,
                        help_text="Yes: the item is sold. No: a part of a bulk row was sold, the row stays.",
                        verbose_name="the item left the stock",
                    ),
                ),
                (
                    "price_part",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="purchase price of the pieces sold",
                    ),
                ),
                (
                    "ancillary_part",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="ancillary cost of the pieces sold",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "cancelled_at",
                    models.DateTimeField(blank=True, editable=False, null=True, verbose_name="reversed"),
                ),
                (
                    "cancel_reason",
                    models.CharField(
                        blank=True,
                        max_length=250,
                        verbose_name="reason for the reversal",
                    ),
                ),
                (
                    "cancelled_by",
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
                    "contact",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="customers.contact",
                        verbose_name="contact",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="customers.customer",
                        verbose_name="customer",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_sales",
                        to="material.materialitem",
                        verbose_name="item",
                    ),
                ),
                (
                    "sold_by",
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
                    "tax_rate",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="masterdata.taxrate",
                        verbose_name="tax rate",
                    ),
                ),
            ],
            options={
                "verbose_name": "sale from stock",
                "verbose_name_plural": "sales from stock",
                "ordering": ["-sold_on", "-id"],
                "indexes": [models.Index(fields=["sold_on"], name="stocksale_sold_on_idx")],
            },
        ),
    ]
