# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``material`` from 0001_initial to 0006_vehicles_090 in one.

Squashed: a new database is built from here, and a database that has applied the replaced
migrations counts it as applied (``replaces``). Data steps that only converted the data of older
versions are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.core.uploads
import rentalars.material.models
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


def create_label_settings(apps, schema_editor):
    """MAT-056: the row of the label settings (material 0005).

    In German: no company profile exists yet while a new database is created; an English installation gets the
    English words with its start data (``core.start_data``).
    """
    LabelSettings = apps.get_model("material", "LabelSettings")
    if LabelSettings.objects.filter(pk=1).exists():
        return
    LabelSettings.objects.create(pk=1, phone_caption="Telefonnummer:", id_caption="Equipment-ID:")



class Migration(migrations.Migration):

    replaces = [('material', '0001_initial'), ('material', '0002_item_status_reason'), ('material', '0003_stage5'), ('material', '0004_items_071'), ('material', '0005_material_085'), ('material', '0006_vehicles_090')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('masterdata', '0001_squashed_0012_fleet_090'),
        ('products', '0001_squashed_0008_vehicles_090'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MaterialModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(error_messages={'unique': 'A material model with this article name already exists.'}, max_length=200, unique=True, verbose_name='article name')),
                ('short_name', models.CharField(blank=True, help_text='For lists and labels. Empty: the article name.', max_length=60, verbose_name='short name')),
                ('specification', models.TextField(blank=True, help_text='Short technical description.', verbose_name='description')),
                ('field_values', models.JSONField(blank=True, default=dict, verbose_name='category-specific values')),
                ('tracking_mode', models.CharField(choices=[('items', 'individual items'), ('bulk', 'bulk quantity')], default='items', max_length=10, verbose_name='stock is kept as')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='material_models', to='masterdata.category', verbose_name='category')),
                ('default_product', models.ForeignKey(blank=True, help_text='Applies to all items of this model unless an item names a different product.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='material_models', to='products.product', verbose_name='product')),
                ('manufacturer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='material_models', to='masterdata.manufacturer', verbose_name='manufacturer')),
                ('height_cm', models.DecimalField(blank=True, decimal_places=1, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='height (cm)')),
                ('length_cm', models.DecimalField(blank=True, decimal_places=1, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='length (cm)')),
                ('weight_kg', models.DecimalField(blank=True, decimal_places=2, help_text='Of one piece, ready to load (in its case, if it travels in one).', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='weight (kg)')),
                ('width_cm', models.DecimalField(blank=True, decimal_places=1, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='width (cm)')),
                ('power_w', models.DecimalField(blank=True, decimal_places=2, help_text='Electrical power of one piece in watts.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='power (W)')),
            ],
            options={
                'verbose_name': 'material model',
                'verbose_name_plural': 'material models',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='MaterialItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inventory_number', models.PositiveIntegerField(error_messages={'unique': 'This ID is already taken.'}, unique=True, verbose_name='ID')),
                ('connection_type', models.CharField(choices=[('fixed', 'permanently installed'), ('loose', 'loosely contained')], default='fixed', max_length=10, verbose_name='kind of connection')),
                ('individually_rentable', models.BooleanField(default=False, help_text='For permanently installed items that are taken out when needed.', verbose_name='can be rented on its own')),
                ('serial_number', models.CharField(blank=True, max_length=120, verbose_name='serial number')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('purchase_date', models.DateField(blank=True, null=True, verbose_name='invoice date')),
                ('purchase_note', models.CharField(blank=True, max_length=250, verbose_name='purchase note')),
                ('purchase_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='purchase price (net)')),
                ('supplier_article_number', models.CharField(blank=True, max_length=120, verbose_name="supplier's article number")),
                ('status', models.CharField(choices=[('available', 'available'), ('in_use', 'in use'), ('defective', 'defective'), ('in_repair', 'in repair'), ('blocked', 'blocked'), ('retired', 'retired'), ('sold', 'sold'), ('lost', 'lost')], default='available', max_length=12, verbose_name='status')),
                ('quantity', models.PositiveIntegerField(default=1, help_text='Only for bulk material; individual items always count 1.', verbose_name='quantity')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('installed_in', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='contents', to='material.materialitem', verbose_name='installed in')),
                ('product_override', models.ForeignKey(blank=True, help_text='Only if this item belongs to a different product than its model.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='override_items', to='products.product', verbose_name='different product')),
                ('storage_location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='material_items', to='masterdata.storagelocation', verbose_name='storage location')),
                ('supplier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='material_items', to='masterdata.supplier', verbose_name='bought from')),
                ('material_model', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='material.materialmodel', verbose_name='material model')),
                ('status_reason', models.CharField(blank=True, help_text='Why the item has its current status, e.g. what is defective.', max_length=250, verbose_name='reason for the status')),
                ('field_value_overrides', models.JSONField(blank=True, default=dict, verbose_name='own category-specific values')),
                ('specification_override', models.TextField(blank=True, help_text='Only if this item differs from its model, e.g. after a modification.', verbose_name='own description')),
                ('taken_out_of', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='material.materialitem', verbose_name='taken out of')),
                ('invoice_number', models.CharField(blank=True, max_length=60, verbose_name='invoice number')),
                ('purchase_price_in', models.ForeignKey(blank=True, help_text='Bought as a set: the item whose purchase price includes this one. It then has no price of its own.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_set_members', to='material.materialitem', verbose_name='price included in')),
            ],
            options={
                'verbose_name': 'material item',
                'verbose_name_plural': 'material items',
                'ordering': ['inventory_number'],
                'indexes': [models.Index(fields=['status'], name='item_status_idx'), models.Index(fields=['serial_number'], name='item_serial_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='DefectReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField(verbose_name='what is defective')),
                ('photo', models.ImageField(blank=True, max_length=200, upload_to=rentalars.material.models.defect_photo_path, verbose_name='photo')),
                ('context', models.CharField(blank=True, max_length=250, verbose_name='found')),
                ('reported_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='reported')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='defect_reports', to='material.materialitem', verbose_name='item')),
                ('reported_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'defect report',
                'verbose_name_plural': 'defect reports',
                'ordering': ['-reported_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='InspectionType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('interval_months', models.PositiveSmallIntegerField(default=12, validators=[django.core.validators.MinValueValidator(1)], verbose_name='interval (months)')),
                ('description', models.TextField(blank=True, help_text='What is checked, which standard.', verbose_name='description')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('categories', models.ManyToManyField(blank=True, related_name='inspection_types', to='masterdata.category', verbose_name='categories')),
                ('material_models', models.ManyToManyField(blank=True, related_name='inspection_types', to='material.materialmodel', verbose_name='material models')),
            ],
            options={
                'verbose_name': 'inspection type',
                'verbose_name_plural': 'inspection types',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Inspection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='date')),
                ('inspector', models.CharField(max_length=120, verbose_name='inspected by')),
                ('result', models.CharField(choices=[('passed', 'passed'), ('failed', 'failed')], max_length=10, verbose_name='result')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('protocol', models.FileField(blank=True, max_length=200, upload_to=rentalars.material.models.inspection_protocol_path, verbose_name='protocol')),
                ('protocol_name', models.CharField(blank=True, max_length=255, verbose_name='file name')),
                ('recorded_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='recorded')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inspections', to='material.materialitem', verbose_name='item')),
                ('recorded_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('inspection_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inspections', to='material.inspectiontype', verbose_name='inspection')),
            ],
            options={
                'verbose_name': 'inspection',
                'verbose_name_plural': 'inspections',
                'ordering': ['-date', '-id'],
                'indexes': [models.Index(fields=['item', 'inspection_type', 'date'], name='inspection_latest_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ItemBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start', models.DateTimeField(verbose_name='from')),
                ('end', models.DateTimeField(verbose_name='until')),
                ('reason', models.CharField(max_length=250, verbose_name='reason')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks', to='material.materialitem', verbose_name='item')),
            ],
            options={
                'verbose_name': 'blocked period',
                'verbose_name_plural': 'blocked periods',
                'ordering': ['start', 'id'],
                'indexes': [models.Index(fields=['start', 'end'], name='item_block_period_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='MaterialFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('picture', 'picture'), ('manual', 'manual'), ('invoice', 'invoice'), ('protocol', 'inspection protocol'), ('other', 'other')], default='other', max_length=10, verbose_name='kind')),
                ('title', models.CharField(blank=True, max_length=200, verbose_name='title')),
                ('file', models.FileField(max_length=200, upload_to=rentalars.material.models.material_file_path, verbose_name='file')),
                ('original_name', models.CharField(max_length=255, verbose_name='file name')),
                ('size', models.PositiveBigIntegerField(default=0, verbose_name='size')),
                ('uploaded_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='uploaded')),
                ('item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='files', to='material.materialitem', verbose_name='item')),
                ('material_model', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='files', to='material.materialmodel', verbose_name='material model')),
                ('uploaded_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'material file',
                'verbose_name_plural': 'material files',
                'ordering': ['kind', '-uploaded_at', '-id'],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('item__isnull', True), ('material_model__isnull', False)), models.Q(('item__isnull', False), ('material_model__isnull', True)), _connector='OR'), name='material_file_one_owner')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='LabelSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(blank=True, help_text='Printed next to the logo. Empty: the name of the company.', max_length=120, verbose_name='name on labels')),
                ('cable_name', models.CharField(blank=True, help_text='The cable label has little room. Empty: the name on labels.', max_length=60, verbose_name='name on cable labels')),
                ('logo', models.ImageField(blank=True, help_text='PNG or JPEG, at most 2 MB, square; black and white prints best on label printers.', upload_to='labels/', validators=[rentalars.core.uploads.validate_image_upload], verbose_name='logo for labels')),
                ('phone', models.CharField(blank=True, help_text='Empty: the phone number of the company.', max_length=60, verbose_name='phone number')),
                ('phone_caption', models.CharField(blank=True, default='Telefonnummer:', max_length=40, verbose_name='words before the phone number')),
                ('id_caption', models.CharField(blank=True, default='Equipment-ID:', max_length=40, verbose_name='words before the ID')),
                ('url', models.CharField(blank=True, help_text='As it is printed, e.g. EXAMPLE.DE. Empty: the website of the company.', max_length=100, verbose_name='web address printed')),
                ('wrap_text', models.CharField(blank=True, help_text='Repeated where the cable label wraps around the cable. Empty: the web address printed.', max_length=100, verbose_name='text around the cable')),
                ('notice', models.TextField(blank=True, help_text='Small print on the small and the large label, e.g. where to report a found item.', max_length=300, verbose_name='text for finders')),
                ('qr_target', models.CharField(blank=True, help_text="A web address with {id} for the ID, e.g. https://equip.example.de/id/{id}. Empty: the item's page in Rentalars.", max_length=250, verbose_name='QR code leads to')),
                ('default_kind', models.CharField(choices=[('small', 'Small, 17 × 54 mm'), ('large', 'Large, 29 × 90 mm'), ('cable', 'Cable, 29 mm roll')], default='small', max_length=10, verbose_name='label suggested')),
                ('cable_length_mm', models.PositiveSmallIntegerField(default=90, help_text='Of the 29 mm roll; the text around the cable is repeated to fill it.', validators=[django.core.validators.MinValueValidator(60), django.core.validators.MaxValueValidator(200)], verbose_name='length of the cable label (mm)')),
            ],
            options={
                'verbose_name': 'label settings',
                'verbose_name_plural': 'label settings',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('licence_plate', models.CharField(blank=True, max_length=20, verbose_name='licence plate')),
                ('seats_min', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name='seats min.')),
                ('seats_max', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name='seats max.')),
                ('licence_class', models.CharField(blank=True, help_text='For example B, BE, C1. For a trailer: the class of the combination.', max_length=12, verbose_name='driving licence class')),
                ('towing_capacity_kg', models.PositiveIntegerField(blank=True, help_text='Only for motor vehicles. 0: may not tow.', null=True, verbose_name='towing capacity (kg)')),
                ('gross_weight_kg', models.PositiveIntegerField(blank=True, null=True, verbose_name='permissible total weight (kg)')),
                ('item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vehicle', to='material.materialitem', verbose_name='item')),
            ],
            options={
                'verbose_name': 'vehicle',
                'verbose_name_plural': 'vehicles',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.RunPython(create_label_settings, migrations.RunPython.noop),
    ]
