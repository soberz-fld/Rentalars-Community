# SPDX-License-Identifier: GPL-3.0-or-later
"""PER-038: the notifications about price offers."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0011_crew_times_091"),
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
                    ("price_offer", "Price offer of a freelancer"),
                    ("price_offer_answer", "Answer to my price offer"),
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
                    ("price_offer", "Price offer of a freelancer"),
                    ("price_offer_answer", "Answer to my price offer"),
                ],
                max_length=24,
                verbose_name="kind",
            ),
        ),
    ]
