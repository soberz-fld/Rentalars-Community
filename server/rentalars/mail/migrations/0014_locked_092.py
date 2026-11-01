# SPDX-License-Identifier: GPL-3.0-or-later
"""Schloss: messages of the correspondence "with lock" or open, and how new messages start.

* ``ProjectMail.locked``: every message that exists in a **project** gets the lock – who read it before and may see
  prices reads it as before, nobody new reads anything. Every message of a **service case** stays open – whoever
  worked on the case keeps reading it (correspondence in service cases is normally not confidential).
* ``MailSettings.lock_new_in_projects`` (on) and ``lock_new_in_cases`` (off): how new messages start.

Two updates of the database, no entries in the change log. Backwards the columns are dropped.
"""

from django.db import migrations, models


def open_messages_of_service_cases(apps, schema_editor):
    """The messages of service cases are open; those of projects keep the lock of the column's default."""
    ProjectMail = apps.get_model("mail", "ProjectMail")
    ProjectMail.objects.filter(project__kind="service_case").update(locked=False)


class Migration(migrations.Migration):
    """Add ``ProjectMail.locked`` – projects with lock, service cases open – and the two defaults."""

    dependencies = [
        ("mail", "0013_senders_signatures_inquiries_090"),
        ("projects", "0019_service_cases_080"),  # ``Project.kind``
    ]

    operations = [
        migrations.AddField(
            model_name="projectmail",
            name="locked",
            field=models.BooleanField(
                default=True,
                help_text="With lock, only those who may see prices and calculation read the message. Without, the "
                "crew planned in the project reads it as well.",
                verbose_name="with lock",
            ),
        ),
        migrations.AddField(
            model_name="mailsettings",
            name="lock_new_in_projects",
            field=models.BooleanField(
                default=True,
                help_text="Only those who may see prices and calculation read them until the lock is taken off.",
                verbose_name="new messages in projects: with lock",
            ),
        ),
        migrations.AddField(
            model_name="mailsettings",
            name="lock_new_in_cases",
            field=models.BooleanField(
                default=False,
                help_text="Without lock, whoever works on the service case reads them, also without the price right.",
                verbose_name="new messages in service cases: with lock",
            ),
        ),
        # Backwards nothing is to be done: the column goes.
        migrations.RunPython(open_messages_of_service_cases, migrations.RunPython.noop),
    ]
