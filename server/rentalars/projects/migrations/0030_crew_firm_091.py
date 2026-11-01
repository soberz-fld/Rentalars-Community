# SPDX-License-Identifier: GPL-3.0-or-later
"""A person can be planned firmly, without request – the request status ``firm``."""

from django.db import migrations, models


def firm_to_accepted(apps, schema_editor):
    """Going back to a version that knows no "firm": a person planned firmly counts as having accepted.

    That is what "firm" means (``CrewLine.is_confirmed``); the times of the line were stored as the asked
    times when it was planned firmly, so the earlier version does not see changed times either.
    """
    apps.get_model("projects", "CrewLine").objects.filter(request_status="firm").update(request_status="accepted")


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0029_logistics_090"),
    ]

    operations = [
        migrations.AlterField(
            model_name="crewline",
            name="request_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "not asked"),
                    ("requested", "asked"),
                    ("accepted", "accepted"),
                    ("declined", "declined"),
                    ("firm", "planned firmly"),
                ],
                default="",
                max_length=10,
                verbose_name="request",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, firm_to_accepted),
    ]
