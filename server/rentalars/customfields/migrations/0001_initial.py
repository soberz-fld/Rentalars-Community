# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom fields of material items – definitions, fieldsets, values of items."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("material", "0006_vehicles_090"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomField",
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
                    "name",
                    models.CharField(
                        error_messages={
                            "unique": "A custom field with this name already exists."
                        },
                        help_text="Also the heading of its column in lists, exports and imports.",
                        max_length=80,
                        unique=True,
                        verbose_name="name",
                    ),
                ),
                (
                    "field_type",
                    models.CharField(
                        choices=[
                            ("text", "text"),
                            ("long_text", "long text"),
                            ("number", "number with unit"),
                            ("date", "date"),
                            ("boolean", "yes/no"),
                            ("choice", "choice list"),
                            ("url", "web address"),
                            ("email", "e-mail address"),
                        ],
                        default="text",
                        max_length=12,
                        verbose_name="type",
                    ),
                ),
                (
                    "unit",
                    models.CharField(
                        blank=True,
                        help_text="For numbers, e.g. m, W, kg.",
                        max_length=20,
                        verbose_name="unit",
                    ),
                ),
                (
                    "choices",
                    models.JSONField(blank=True, default=list, verbose_name="options"),
                ),
                (
                    "pattern",
                    models.CharField(
                        blank=True,
                        help_text="Optional: a regular expression every value must match, e.g. ^[0-9A-F]{2}(:[0-9A-F]{2}){5}$ for a MAC address. For text, long text, number, web and e-mail address.",
                        max_length=250,
                        verbose_name="check pattern",
                    ),
                ),
                (
                    "help_text",
                    models.CharField(
                        blank=True,
                        help_text="Shown below the field in the form.",
                        max_length=250,
                        verbose_name="help text",
                    ),
                ),
                (
                    "show_in_lists",
                    models.BooleanField(
                        default=False,
                        help_text="The item list offers the field as a column – to show, sort, filter and export.",
                        verbose_name="choosable as a column in lists",
                    ),
                ),
                (
                    "is_unique",
                    models.BooleanField(
                        default=False,
                        help_text="No two items may have the same value, e.g. a MAC address.",
                        verbose_name="unique",
                    ),
                ),
                (
                    "is_sensitive",
                    models.BooleanField(
                        default=False,
                        help_text="The values are shown, searched, exported and changed only by who may see purchase prices – also in the history and the API.",
                        verbose_name="only with the right to see purchase prices",
                    ),
                ),
            ],
            options={
                "verbose_name": "custom field",
                "verbose_name_plural": "custom fields",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Fieldset",
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
                    "name",
                    models.CharField(
                        error_messages={
                            "unique": "A fieldset with this name already exists."
                        },
                        max_length=80,
                        unique=True,
                        verbose_name="name",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True, max_length=250, verbose_name="description"
                    ),
                ),
            ],
            options={
                "verbose_name": "fieldset",
                "verbose_name_plural": "fieldsets",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ModelFieldset",
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
                    "fieldset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="customfields.fieldset",
                        verbose_name="fieldset",
                    ),
                ),
                (
                    "material_model",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_fieldset",
                        to="material.materialmodel",
                        verbose_name="material model",
                    ),
                ),
            ],
            options={
                "verbose_name": "fieldset of a material model",
                "verbose_name_plural": "fieldsets of material models",
            },
        ),
        migrations.CreateModel(
            name="CustomFieldValue",
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
                ("value", models.TextField(blank=True, verbose_name="value")),
                (
                    "protected_value",
                    models.TextField(
                        blank=True,
                        verbose_name="value only for who may see purchase prices",
                    ),
                ),
                (
                    "field",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="values",
                        to="customfields.customfield",
                        verbose_name="custom field",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_values",
                        to="material.materialitem",
                        verbose_name="material item",
                    ),
                ),
            ],
            options={
                "verbose_name": "value of a custom field",
                "verbose_name_plural": "values of custom fields",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("item", "field"), name="customfields_value_unique"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="FieldsetEntry",
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
                    "position",
                    models.PositiveSmallIntegerField(
                        default=1, verbose_name="position"
                    ),
                ),
                (
                    "is_required",
                    models.BooleanField(default=False, verbose_name="required field"),
                ),
                (
                    "field",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fieldset_entries",
                        to="customfields.customfield",
                        verbose_name="custom field",
                    ),
                ),
                (
                    "fieldset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="customfields.fieldset",
                        verbose_name="fieldset",
                    ),
                ),
            ],
            options={
                "verbose_name": "field of a fieldset",
                "verbose_name_plural": "fields of fieldsets",
                "ordering": ["position", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("fieldset", "field"), name="customfields_entry_unique"
                    )
                ],
            },
        ),
    ]
