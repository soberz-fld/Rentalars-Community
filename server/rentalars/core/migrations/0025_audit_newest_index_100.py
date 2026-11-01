# SPDX-License-Identifier: GPL-3.0-or-later
"""An index for "the newest change-log entry of a kind" (stock watch; R4-1).

``stock_stamp`` asks for the highest ID per kind of object on every poll of an open planning page. The existing
index ``(content_type, object_id)`` cannot answer that from the index alone; this one can. Reverse: drop the index.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the index."""

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0024_notification_defaults_093"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(fields=["content_type", "id"], name="audit_type_newest_idx"),
        ),
    ]
