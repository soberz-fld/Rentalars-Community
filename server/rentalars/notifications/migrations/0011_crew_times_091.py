# SPDX-License-Identifier: GPL-3.0-or-later
"""Notifications of changed deployments and of approved times, the reminders of times to approve."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0010_addresses_085"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("deployment_request", "Deployment request"),
                    ("deployment_answer", "Answer to a deployment request"),
                    ("project_change", "Change of a project"),
                    ("shortage", "Shortage"),
                    ("defect", "Defect reported"),
                    ("new_mail", "New mail for a project"),
                    ("mail_problem", "Problem fetching mails"),
                    ("system_error", "Error of the application"),
                    ("low_stock", "Stock below the minimum"),
                    ("inspection_due", "Inspections due"),
                    ("qualification_expiry", "Qualification expiring"),
                    ("job_finished", "A task in the background is finished"),
                    ("calendar_problem", "Problem with my calendar"),
                    ("follow_up", "Follow-up of a project"),
                    ("chat_mention", "Mentioned in a project chat"),
                    ("automation", "Message of an automation"),
                    ("expense", "My expenses sent back or reimbursed"),
                    ("service_case", "Added to a service case"),
                    ("invoice_reminder", "Invoice still to be written"),
                    ("deployment_change", "Change of my deployment"),
                    ("times_to_approve", "Times waiting for my approval"),
                    ("time_decision", "My times approved, corrected or sent back"),
                ],
                max_length=24,
                verbose_name="kind",
            ),
        ),
        migrations.AlterField(
            model_name="preference",
            name="kind",
            field=models.CharField(
                choices=[
                    ("deployment_request", "Deployment request"),
                    ("deployment_answer", "Answer to a deployment request"),
                    ("project_change", "Change of a project"),
                    ("shortage", "Shortage"),
                    ("defect", "Defect reported"),
                    ("new_mail", "New mail for a project"),
                    ("mail_problem", "Problem fetching mails"),
                    ("system_error", "Error of the application"),
                    ("low_stock", "Stock below the minimum"),
                    ("inspection_due", "Inspections due"),
                    ("qualification_expiry", "Qualification expiring"),
                    ("job_finished", "A task in the background is finished"),
                    ("calendar_problem", "Problem with my calendar"),
                    ("follow_up", "Follow-up of a project"),
                    ("chat_mention", "Mentioned in a project chat"),
                    ("automation", "Message of an automation"),
                    ("expense", "My expenses sent back or reimbursed"),
                    ("service_case", "Added to a service case"),
                    ("invoice_reminder", "Invoice still to be written"),
                    ("deployment_change", "Change of my deployment"),
                    ("times_to_approve", "Times waiting for my approval"),
                    ("time_decision", "My times approved, corrected or sent back"),
                ],
                max_length=24,
                verbose_name="kind",
            ),
        ),
        migrations.CreateModel(
            name="ApprovalNotice",
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
                    "first_reminded_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "last_reminded_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("count", models.PositiveIntegerField(default=1)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
