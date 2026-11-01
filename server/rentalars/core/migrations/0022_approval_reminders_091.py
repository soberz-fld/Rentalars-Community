# SPDX-License-Identifier: GPL-3.0-or-later
"""Reminders of the times waiting for approval (Einstellungen → Benachrichtigungen, ZEI-013).

Switched on, at 08:00, the first after a day, then daily. The first minute of the timer after the update only notes
its time (``approval_last_run``): the first reminders go out at the next 08:00.
"""

import datetime
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_invoice_085"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_checked_at",
            field=models.DateTimeField(
                blank=True, editable=False, null=True, verbose_name="last check"
            ),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_every_days",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="As long as times are waiting; 1: every day.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(60),
                ],
                verbose_name="then again every (days)",
            ),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_first_days",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Days after the day a time was handed in; 0: at the next check after handing in.",
                validators=[django.core.validators.MaxValueValidator(60)],
                verbose_name="first reminder after (days)",
            ),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_last_run",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_reminded",
            field=models.PositiveIntegerField(
                default=0, editable=False, verbose_name="reminded at the last check"
            ),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_reminders",
            field=models.BooleanField(
                default=True,
                help_text="Everybody who may approve times is reminded of the times and expenses handed in and waiting for their approval – each only of those they may approve, not of their own.",
                verbose_name="remind of times to approve",
            ),
        ),
        migrations.AddField(
            model_name="notificationsettings",
            name="approval_time",
            field=models.TimeField(
                default=datetime.time(8, 0), verbose_name="time of day"
            ),
        ),
    ]
