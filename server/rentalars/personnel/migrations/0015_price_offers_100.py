# SPDX-License-Identifier: GPL-3.0-or-later
"""PER-038: price offers of freelancers and their settings."""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("personnel", "0001_squashed_0014_licence_classes_090"),
        ("projects", "0033_text_lines_095"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OfferSettings",
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
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Off: a deployment request is answered with “accept” or “decline” only.",
                        verbose_name="freelancers may offer their own price",
                    ),
                ),
                (
                    "also_temporary",
                    models.BooleanField(
                        default=False,
                        help_text="Off: only people of the kind “freelancer” may make an offer.",
                        verbose_name="temporary staff too",
                    ),
                ),
                (
                    "min_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Empty: no lower limit.",
                        max_digits=6,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0")),
                            django.core.validators.MaxValueValidator(Decimal("1000")),
                        ],
                        verbose_name="lowest offer in percent of the stored rate",
                    ),
                ),
                (
                    "max_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Empty: no upper limit. Without a stored rate no limit can be checked.",
                        max_digits=6,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0")),
                            django.core.validators.MaxValueValidator(Decimal("1000")),
                        ],
                        verbose_name="highest offer in percent of the stored rate",
                    ),
                ),
                (
                    "max_rounds",
                    models.PositiveSmallIntegerField(
                        default=4,
                        help_text="Offers and counter-offers together; after the last one only accepting or rejecting is left.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10),
                        ],
                        verbose_name="proposals per request, at most",
                    ),
                ),
            ],
            options={
                "verbose_name": "settings for price offers",
                "verbose_name_plural": "settings for price offers",
            },
        ),
        migrations.CreateModel(
            name="PriceOffer",
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
                    "round",
                    models.PositiveSmallIntegerField(default=1, verbose_name="round"),
                ),
                (
                    "side",
                    models.CharField(
                        choices=[("freelancer", "freelancer"), ("company", "company")],
                        max_length=10,
                        verbose_name="made by",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01")),
                            django.core.validators.MaxValueValidator(Decimal("99999999.99")),
                        ],
                        verbose_name="amount",
                    ),
                ),
                (
                    "unit",
                    models.CharField(
                        choices=[
                            ("hour", "per hour"),
                            ("day", "per day"),
                            ("total", "in total"),
                        ],
                        default="hour",
                        max_length=5,
                        verbose_name="for",
                    ),
                ),
                (
                    "currency",
                    models.CharField(default="EUR", max_length=3, verbose_name="currency"),
                ),
                (
                    "message",
                    models.CharField(blank=True, max_length=500, verbose_name="message"),
                ),
                (
                    "valid_until",
                    models.DateField(blank=True, null=True, verbose_name="valid until"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "open"),
                            ("accepted", "accepted"),
                            ("rejected", "rejected"),
                            ("countered", "countered"),
                            ("withdrawn", "withdrawn"),
                            ("lapsed", "lapsed"),
                        ],
                        default="open",
                        max_length=10,
                        verbose_name="status",
                    ),
                ),
                (
                    "decided_at",
                    models.DateTimeField(blank=True, editable=False, null=True, verbose_name="decided at"),
                ),
                (
                    "decision_note",
                    models.CharField(blank=True, max_length=250, verbose_name="reason"),
                ),
                (
                    "reference_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        editable=False,
                        max_digits=10,
                        null=True,
                        verbose_name="stored rate at that time",
                    ),
                ),
                (
                    "requested_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                (
                    "applied",
                    models.BooleanField(
                        default=False,
                        editable=False,
                        verbose_name="sets the cost rate of the line",
                    ),
                ),
                (
                    "release_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "still applies"),
                            ("manual", "cost rate changed by hand"),
                            ("person", "another person or job function"),
                            ("times", "new times"),
                            ("revoked", "taken back"),
                        ],
                        editable=False,
                        max_length=10,
                        verbose_name="no longer applies because",
                    ),
                ),
                (
                    "previous_hourly_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        editable=False,
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "previous_daily_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        editable=False,
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "previous_cost_flat_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        editable=False,
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "previous_hourly_rate_above_limit",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        editable=False,
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="made at",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="entered by",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="decided by",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_offers",
                        to="projects.crewline",
                        verbose_name="crew line",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_offers",
                        to="personnel.person",
                        verbose_name="person",
                    ),
                ),
            ],
            options={
                "verbose_name": "price offer",
                "verbose_name_plural": "price offers",
                "ordering": ["line_id", "requested_at", "round", "id"],
                "indexes": [models.Index(fields=["status", "created_at"], name="price_offer_status_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("line", "requested_at", "round"),
                        name="price_offer_round_once",
                    )
                ],
            },
        ),
    ]
