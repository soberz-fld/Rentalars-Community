# SPDX-License-Identifier: GPL-3.0-or-later
"""Photos of models and items (MAT-090): the preview of a photo, next to the photo itself."""

import rentalars.material.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("material", "0016_sale_invoice_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialfile",
            name="thumbnail",
            field=models.FileField(
                blank=True,
                max_length=200,
                upload_to=rentalars.material.models.material_file_path,
                verbose_name="preview",
            ),
        ),
    ]
