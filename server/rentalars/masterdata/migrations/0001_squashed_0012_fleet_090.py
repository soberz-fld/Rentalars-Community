# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``masterdata`` from 0001_initial to 0012_fleet_090 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import datetime
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
from django.db.models import Max


#: (name, visible to the crew)
DOCUMENT_TYPES = [
    ("Bühnenplan", True),
    ("Rider", True),
    ("Ablaufplan", True),
    ("Hallenplan", True),
    ("Vertrag", False),
    ("Bestellung", False),
    ("Sonstiges", False),
]


def create_document_types(apps, schema_editor):
    """PRJ-007, EML-021: the usual kinds of project documents (masterdata 0003)."""
    DocumentType = apps.get_model("masterdata", "DocumentType")
    if DocumentType.objects.exists():
        return
    for position, (name, visible_to_crew) in enumerate(DOCUMENT_TYPES, start=1):
        DocumentType.objects.create(name=name, visible_to_crew=visible_to_crew, position=position)


SHOWFILE = "Showfile"


#: Names under which an administrator may have created the kind already.
KNOWN_NAMES = ("showfile", "showfiles", "show-datei", "show-dateien")


def add_showfile_type(apps, schema_editor):
    """PRJ-089: the kind of document for show files, right before "Sonstiges" (masterdata 0009)."""
    type_model = apps.get_model("masterdata", "DocumentType")
    if type_model.objects.filter(is_showfile=True).exists():
        return
    existing = next(
        (kind for kind in type_model.objects.order_by("pk") if kind.name.strip().lower() in KNOWN_NAMES), None
    )
    if existing is not None:
        type_model.objects.filter(pk=existing.pk).update(is_showfile=True)
        return
    other = type_model.objects.filter(name__iexact="Sonstiges").first()
    if other is not None:
        # Same position as "Sonstiges": sorted by position and name, "Showfile" comes right before it.
        position = other.position
    else:
        position = (type_model.objects.aggregate(last=Max("position"))["last"] or 0) + 1
    type_model.objects.create(name=SHOWFILE, visible_to_crew=True, position=position, is_active=True, is_showfile=True)



class Migration(migrations.Migration):

    replaces = [('masterdata', '0001_initial'), ('masterdata', '0002_document_type'), ('masterdata', '0003_default_document_types'), ('masterdata', '0004_default_master_data_062'), ('masterdata', '0005_customer_material_063'), ('masterdata', '0006_incidental_071'), ('masterdata', '0007_suppliers_071'), ('masterdata', '0008_storage_071'), ('masterdata', '0009_showfiles_080'), ('masterdata', '0010_maps_080'), ('masterdata', '0011_labels_084'), ('masterdata', '0012_fleet_090')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Manufacturer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'manufacturer',
                'verbose_name_plural': 'manufacturers',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='RentalScale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True, verbose_name='name')),
                ('is_default', models.BooleanField(default=False, verbose_name='default scale')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'rental scale',
                'verbose_name_plural': 'rental scales',
                'ordering': ['-is_default', 'name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('contact', models.CharField(blank=True, help_text='Who to ask there.', max_length=250, verbose_name='contact')),
                ('customer_number', models.CharField(blank=True, max_length=60, verbose_name='our customer number there')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('email', models.EmailField(blank=True, help_text='Mails of a project from and to this address belong to its subrentals.', max_length=254, verbose_name='e-mail')),
                ('phone', models.CharField(blank=True, max_length=60, verbose_name='phone')),
                ('street', models.CharField(blank=True, max_length=200, verbose_name='street and number')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('city', models.CharField(blank=True, max_length=120, verbose_name='city')),
                ('country', models.CharField(blank=True, max_length=80, verbose_name='country')),
            ],
            options={
                'verbose_name': 'supplier',
                'verbose_name_plural': 'suppliers',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='TaxRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, unique=True, verbose_name='name')),
                ('rate', models.DecimalField(decimal_places=2, max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='rate in percent')),
                ('valid_from', models.DateField(default=datetime.date(2007, 1, 1), verbose_name='valid from')),
                ('is_default', models.BooleanField(default=False, verbose_name='default for new products')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'tax rate',
                'verbose_name_plural': 'tax rates',
                'ordering': ['-is_default', 'name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Unit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40, unique=True, verbose_name='name')),
                ('abbreviation', models.CharField(max_length=12, verbose_name='abbreviation')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'unit',
                'verbose_name_plural': 'units',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='name')),
                ('code', models.CharField(blank=True, help_text='Capital letters; forms the first part of article numbers. Only for main categories.', max_length=6, verbose_name='code')),
                ('has_own_stock', models.BooleanField(default=True, help_text='Products of categories without own stock are not checked for availability.', verbose_name='own stock')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('buffer_before_hours', models.DecimalField(blank=True, decimal_places=2, help_text='Empty: use the default.', max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='buffer before use (hours)')),
                ('buffer_after_hours', models.DecimalField(blank=True, decimal_places=2, help_text='Empty: use the default.', max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='buffer after use (hours)')),
                ('default_product_kind', models.CharField(choices=[('rental', 'rental product'), ('sale', 'sale or consumable'), ('service', 'service'), ('kit', 'kit'), ('surcharge', 'surcharge'), ('subrental', 'subrental'), ('incidental', 'incidental costs'), ('vehicle', 'vehicle')], default='rental', max_length=12, verbose_name='preset: product kind')),
                ('default_billing_mode', models.CharField(blank=True, help_text='Empty: follow the product kind.', max_length=20, verbose_name='preset: billing mode')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='masterdata.category', verbose_name='parent category')),
                ('rental_scale', models.ForeignKey(blank=True, help_text='Empty: use the default scale.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='categories', to='masterdata.rentalscale', verbose_name='rental scale')),
                ('default_tax_rate', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='masterdata.taxrate', verbose_name='preset: tax rate')),
                ('default_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='masterdata.unit', verbose_name='preset: unit')),
                ('is_customer_material', models.BooleanField(default=False, help_text="Products of this category belong to a customer: they have an owner and no price, and they can only be planned in that customer's projects. Only for main categories with own stock.", verbose_name='customer material')),
            ],
            options={
                'verbose_name': 'category',
                'verbose_name_plural': 'categories',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('parent', 'name'), name='category_unique_name')],
            },
        ),
        migrations.CreateModel(
            name='CategoryField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=80, verbose_name='label')),
                ('field_type', models.CharField(choices=[('text', 'text'), ('number', 'number with unit'), ('choice', 'choice'), ('boolean', 'yes/no')], default='text', max_length=10, verbose_name='type')),
                ('unit', models.CharField(blank=True, help_text='For numbers, e.g. m, W, kg.', max_length=20, verbose_name='unit')),
                ('choices', models.JSONField(blank=True, default=list, help_text='For the type “choice”.', verbose_name='options')),
                ('position', models.PositiveSmallIntegerField(default=1, verbose_name='position')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='masterdata.category', verbose_name='category')),
            ],
            options={
                'verbose_name': 'category-specific field',
                'verbose_name_plural': 'category-specific fields',
                'ordering': ['position', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='RentalScaleVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField(verbose_name='version')),
                ('extra_day_increment', models.DecimalField(decimal_places=3, default=Decimal('0'), help_text='Added to the last factor for every day beyond the last row.', max_digits=7, verbose_name='increment per further day')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('scale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='masterdata.rentalscale')),
            ],
            options={
                'verbose_name': 'rental scale version',
                'verbose_name_plural': 'rental scale versions',
                'ordering': ['scale', '-number'],
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('scale', 'number'), name='rental_scale_version_unique')],
            },
        ),
        migrations.CreateModel(
            name='RentalScaleRow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('days', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name='rental days')),
                ('factor', models.DecimalField(decimal_places=3, max_digits=7, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='factor')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rows', to='masterdata.rentalscaleversion')),
            ],
            options={
                'verbose_name': 'rental scale row',
                'verbose_name_plural': 'rental scale rows',
                'ordering': ['days'],
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('version', 'days'), name='rental_scale_row_unique')],
            },
        ),
        migrations.CreateModel(
            name='StorageLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='name')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='masterdata.storagelocation', verbose_name='part of')),
                ('is_default', models.BooleanField(default=False, help_text='The form for new items preselects this location. Only one location can be the default.', verbose_name='default for new items')),
            ],
            options={
                'verbose_name': 'storage location',
                'verbose_name_plural': 'storage locations',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [models.UniqueConstraint(fields=('parent', 'name'), name='storage_location_unique_name')],
            },
        ),
        migrations.CreateModel(
            name='DocumentType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True, verbose_name='name')),
                ('visible_to_crew', models.BooleanField(default=False, help_text='Files of this kind are shown in the deployment view, too.', verbose_name='visible to the crew')),
                ('position', models.PositiveSmallIntegerField(default=0, verbose_name='position')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('is_showfile', models.BooleanField(default=False, help_text='Files of this kind note the console or software, its version and which one is current.', verbose_name='show files')),
            ],
            options={
                'verbose_name': 'document type',
                'verbose_name_plural': 'document types',
                'ordering': ['position', 'name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.RunPython(create_document_types, migrations.RunPython.noop),
        migrations.RunPython(add_showfile_type, migrations.RunPython.noop),
    ]
