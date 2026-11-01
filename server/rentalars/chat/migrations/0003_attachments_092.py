# SPDX-License-Identifier: GPL-3.0-or-later
"""Chat media: photos and videos at chat messages (UIX-010).

* ``ChatAttachment`` – a photo or video of a message in its smaller version,
  with its preview; a video waits in the state "processing" until it is
  converted in the background.
* ``ChatMessage.text`` may be empty: a message may carry photos or videos only.

Nothing existing is changed; going back drops the attachments (their files
stay in ``media/chat``).
"""

import django.db.models.deletion
import django.utils.timezone
import rentalars.chat.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_reads_082"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatmessage",
            name="text",
            field=models.TextField(blank=True, max_length=4000, verbose_name="message"),
        ),
        migrations.CreateModel(
            name="ChatAttachment",
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
                    "kind",
                    models.CharField(
                        choices=[("photo", "photo"), ("video", "video")],
                        max_length=8,
                        verbose_name="kind",
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("processing", "being made smaller"),
                            ("ready", "ready"),
                            ("failed", "failed"),
                        ],
                        default="ready",
                        max_length=12,
                        verbose_name="state",
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        max_length=200,
                        upload_to=rentalars.chat.models.attachment_path,
                        verbose_name="file",
                    ),
                ),
                (
                    "thumbnail",
                    models.FileField(
                        blank=True,
                        max_length=200,
                        upload_to=rentalars.chat.models.attachment_path,
                        verbose_name="preview",
                    ),
                ),
                (
                    "original_name",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="file name"
                    ),
                ),
                (
                    "size",
                    models.PositiveBigIntegerField(default=0, verbose_name="size"),
                ),
                (
                    "width",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="width"
                    ),
                ),
                (
                    "height",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="height"
                    ),
                ),
                (
                    "duration",
                    models.FloatField(blank=True, null=True, verbose_name="duration"),
                ),
                ("source", models.CharField(blank=True, editable=False, max_length=80)),
                (
                    "failure",
                    models.CharField(blank=True, editable=False, max_length=20),
                ),
                ("position", models.PositiveSmallIntegerField(default=0)),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="uploaded"
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="chat.chatmessage",
                        verbose_name="chat message",
                    ),
                ),
            ],
            options={
                "verbose_name": "chat attachment",
                "verbose_name_plural": "chat attachments",
                "ordering": ["position", "id"],
            },
        ),
    ]
