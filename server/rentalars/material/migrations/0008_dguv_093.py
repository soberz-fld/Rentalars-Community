# SPDX-License-Identifier: GPL-3.0-or-later
"""Fields for the electrical inspection after DGUV V3 / DIN VDE 0701-0702 (DGUV).

The protection class of a material model and, if it differs, of an item; inspection types can be marked
"electrical"; an inspection keeps what was measured. Everything starts empty – no inspection type becomes
electrical by the update, no model gets a protection class.
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """The new fields, all empty or "no"."""

    dependencies = [
        ("material", "0007_audits_092"),
    ]

    operations = [
        migrations.AddField(
            model_name="inspection",
            name="cord_length_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="cord length (m)",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="function_test_passed",
            field=models.BooleanField(blank=True, null=True, verbose_name="function test passed"),
        ),
        migrations.AddField(
            model_name="inspection",
            name="insulation_resistance_mohm",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=9,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="insulation resistance (MΩ)",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="pe_current_ma",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=7,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="protective conductor current (mA)",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="pe_resistance_ohm",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=7,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="protective conductor resistance (Ω)",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="protection_class",
            field=models.CharField(
                blank=True,
                choices=[
                    ("I", "I (protective conductor)"),
                    ("II", "II (protective insulation)"),
                    ("III", "III (safety extra-low voltage)"),
                ],
                max_length=3,
                verbose_name="protection class",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="test_device",
            field=models.CharField(blank=True, max_length=120, verbose_name="test device"),
        ),
        migrations.AddField(
            model_name="inspection",
            name="touch_current_ma",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=7,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="touch current (mA)",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="visual_check_passed",
            field=models.BooleanField(blank=True, null=True, verbose_name="visual inspection passed"),
        ),
        migrations.AddField(
            model_name="inspectiontype",
            name="is_electrical",
            field=models.BooleanField(
                default=False,
                help_text="Recording asks for visual inspection, protective conductor and insulation resistance, leakage currents, function test and test device, checks the limits and suggests the result.",
                verbose_name="electrical inspection (DGUV V3 / DIN VDE 0701-0702)",
            ),
        ),
        migrations.AddField(
            model_name="materialitem",
            name="protection_class_override",
            field=models.CharField(
                blank=True,
                choices=[
                    ("I", "I (protective conductor)"),
                    ("II", "II (protective insulation)"),
                    ("III", "III (safety extra-low voltage)"),
                ],
                help_text="Only if this item differs from its model.",
                max_length=3,
                verbose_name="own protection class",
            ),
        ),
        migrations.AddField(
            model_name="materialmodel",
            name="protection_class",
            field=models.CharField(
                blank=True,
                choices=[
                    ("I", "I (protective conductor)"),
                    ("II", "II (protective insulation)"),
                    ("III", "III (safety extra-low voltage)"),
                ],
                help_text="Of an electrical device: I with protective conductor, II with protective insulation, III for safety extra-low voltage. Empty: not electrical, or not known.",
                max_length=3,
                verbose_name="protection class",
            ),
        ),
    ]
