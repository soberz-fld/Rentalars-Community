# SPDX-License-Identifier: GPL-3.0-or-later
"""Related projects and service cases (``ProjectRelation``)."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """The table of the relations; it starts empty."""

    dependencies = [
        ("projects", "0030_crew_firm_091"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectRelation",
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
                    "note",
                    models.CharField(blank=True, max_length=200, verbose_name="note"),
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
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="created by",
                    ),
                ),
                (
                    "first",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="projects.project",
                        verbose_name="project",
                    ),
                ),
                (
                    "second",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="projects.project",
                        verbose_name="related project",
                    ),
                ),
            ],
            options={
                "verbose_name": "project relation",
                "verbose_name_plural": "project relations",
                "ordering": ["created_at", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("first", "second"), name="project_relation_unique"),
                    models.CheckConstraint(
                        condition=models.Q(("first__lt", models.F("second"))),
                        name="project_relation_ordered",
                    ),
                ],
            },
        ),
    ]
