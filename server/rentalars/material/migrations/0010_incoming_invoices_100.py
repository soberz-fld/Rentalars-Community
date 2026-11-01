# SPDX-License-Identifier: GPL-3.0-or-later
"""Incoming invoices: acquisition data of items and the settings for assets."""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Fields for the acquisition of items, the settings for assets."""

    dependencies = [
        ("incoming", "0001_incoming_invoices_100"),
        ("material", "0009_storage_spot_094"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssetSettings",
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
                    "low_value_limit_net",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("800.00"),
                        help_text="A piece whose acquisition cost – price plus its share of the ancillary costs – does not exceed this amount counts as a low-value asset, a more expensive one as a fixed asset, unless you choose otherwise. In Germany the limit is 800 € net.",
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                        verbose_name="limit of a low-value asset (GWG), net",
                    ),
                ),
                (
                    "default_useful_life_months",
                    models.PositiveSmallIntegerField(
                        default=60,
                        help_text="A fixed asset without a useful life of its own gets this one. 60 months are five years.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(600),
                        ],
                        verbose_name="standard useful life (months)",
                    ),
                ),
            ],
            options={
                "verbose_name": "asset settings",
                "verbose_name_plural": "asset settings",
            },
        ),
        migrations.AddField(
            model_name="materialitem",
            name="acquisition_cost_net",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Purchase price plus the share of the ancillary costs.",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                verbose_name="acquisition cost (net)",
            ),
        ),
        migrations.AddField(
            model_name="materialitem",
            name="ancillary_cost_net",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="The share of transport, packaging, customs … of the invoice that fell to this item.",
                max_digits=10,
                null=True,
                verbose_name="ancillary acquisition cost (net)",
            ),
        ),
        migrations.AddField(
            model_name="materialitem",
            name="asset_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("merchandise", "merchandise"),
                    ("low_value", "low-value asset (GWG)"),
                    ("fixed_asset", "fixed asset"),
                ],
                help_text="Merchandise, low-value asset (GWG) or fixed asset. Empty: not classified.",
                max_length=12,
                verbose_name="kind of asset",
            ),
        ),
        migrations.AddField(
            model_name="materialitem",
            name="source_position",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="items",
                to="incoming.invoiceposition",
                verbose_name="incoming invoice position",
            ),
        ),
        migrations.AddField(
            model_name="materialitem",
            name="useful_life_months",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="For a fixed asset: the months it is written off over.",
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(600),
                ],
                verbose_name="useful life (months)",
            ),
        ),
    ]
