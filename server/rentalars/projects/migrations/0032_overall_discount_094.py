# SPDX-License-Identifier: GPL-3.0-or-later
"""The overall discount of a project (PRJ-123)."""

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    """Two empty fields: no project has an overall discount so far."""

    dependencies = [
        ("projects", "0031_relations_092"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="overall_discount_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Taken off the net total of the project, after surcharges.",
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(Decimal("100")),
                ],
                verbose_name="overall discount in percent",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="overall_discount_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Taken off the net total of the project, after surcharges.",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                verbose_name="overall discount as amount",
            ),
        ),
    ]
