# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``products`` from 0001_initial to 0008_vehicles_090 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.products.models
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('products', '0001_initial'), ('products', '0002_stage5'), ('products', '0003_fixture_type_mapping'), ('products', '0004_product_max_discount'), ('products', '0005_owner_063'), ('products', '0006_services_071'), ('products', '0007_surcharges_080'), ('products', '0008_vehicles_090')]

    initial = True

    dependencies = [
        ('customers', '0001_squashed_0007_maps_080'),
        ('masterdata', '0001_squashed_0012_fleet_090'),
    ]

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('article_number', models.CharField(error_messages={'unique': 'This article number is already taken.'}, max_length=20, unique=True, validators=[rentalars.products.models.validate_article_number_format], verbose_name='article number')),
                ('gtin', models.CharField(blank=True, max_length=14, validators=[rentalars.products.models.validate_gtin], verbose_name='GTIN/EAN')),
                ('name', models.CharField(help_text='Appears on documents.', max_length=200, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('note', models.TextField(blank=True, help_text='Never appears on customer documents.', verbose_name='internal note')),
                ('kind', models.CharField(choices=[('rental', 'rental product'), ('sale', 'sale or consumable'), ('service', 'service'), ('kit', 'kit'), ('surcharge', 'surcharge'), ('subrental', 'subrental'), ('incidental', 'incidental costs'), ('vehicle', 'vehicle')], default='rental', max_length=12, verbose_name='product kind')),
                ('price', models.DecimalField(blank=True, decimal_places=2, help_text='For rental products the price per day.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price (net)')),
                ('sale_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='sale price (net)')),
                ('calculation_note', models.TextField(blank=True, verbose_name='calculation note')),
                ('billing_mode', models.CharField(choices=[('daily_piece', 'daily rental per piece'), ('daily_kit', 'daily rental per kit'), ('flat', 'flat'), ('hourly', 'by the hour'), ('effort', 'by effort')], default='daily_piece', max_length=20, verbose_name='billing mode')),
                ('rental_scale_mode', models.CharField(choices=[('inherit', 'as the category or the default'), ('custom', 'own scale'), ('none', 'no scale')], default='inherit', max_length=10, verbose_name='rental scale')),
                ('surcharge_type', models.CharField(choices=[('fixed', 'fixed amount'), ('percent', 'percentage')], default='fixed', max_length=10, verbose_name='surcharge type')),
                ('surcharge_percent', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('1000'))], verbose_name='surcharge in percent')),
                ('buffer_before_hours', models.DecimalField(blank=True, decimal_places=2, help_text='Empty: as the category or the default.', max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='buffer before use (hours)')),
                ('buffer_after_hours', models.DecimalField(blank=True, decimal_places=2, help_text='Empty: as the category or the default.', max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='buffer after use (hours)')),
                ('is_active', models.BooleanField(default=True, help_text='Deactivated products stay visible in old projects but cannot be added to new ones.', verbose_name='active')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='masterdata.category', verbose_name='category')),
                ('rental_scale', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='products', to='masterdata.rentalscale', verbose_name='own rental scale')),
                ('tax_rate', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='masterdata.taxrate', verbose_name='tax rate')),
                ('unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='masterdata.unit', verbose_name='unit')),
                ('minimum_stock', models.PositiveIntegerField(blank=True, help_text='For sale and consumable products: below this, the warehouse is warned. Empty: no warning.', null=True, verbose_name='minimum stock')),
                ('max_discount_percent', models.DecimalField(blank=True, decimal_places=2, help_text="No line of this product is discounted more – by its own discount, the customer's standard discount or its group's. 0: never discounted. Empty: no limit.", max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='maximum discount in percent')),
                ('owner', models.ForeignKey(blank=True, help_text='Only for customer material: the customer it belongs to. It is planned only in their projects.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='owned_products', to='customers.customer', verbose_name='owner')),
                ('hours_limit', models.DecimalField(blank=True, decimal_places=2, help_text='Only for services billed by the hour: the hours of one day beyond this cost the price from the limit, e.g. 10 – from the 11th hour of a day. Empty: every hour costs the same.', max_digits=4, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.25')), django.core.validators.MaxValueValidator(Decimal('23.75'))], verbose_name='limit in hours per day')),
                ('price_above_limit', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price per hour from the limit (net)')),
                ('time_surcharges', models.BooleanField(default=True, help_text='Only for services billed by the hour. Off: crew lines of this service get no surcharges, neither on the price nor on the costs.', verbose_name='surcharges for night, Sunday and holidays')),
                ('cost_per_day', models.DecimalField(blank=True, decimal_places=2, help_text='Only for trailers billed per day: what a day costs the company.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='internal cost per day')),
                ('cost_per_km', models.DecimalField(blank=True, decimal_places=2, help_text='Fuel, wear, insurance – what a kilometre costs the company.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='internal cost per kilometre')),
                ('price_per_km', models.DecimalField(blank=True, decimal_places=2, help_text='For a motor vehicle its rate; for a trailer the rate when it is billed per kilometre.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='price per kilometre (net)')),
                ('trailer_billing', models.CharField(choices=[('day', 'per day'), ('km', 'per kilometre')], default='day', help_text='Only for trailers: how a new booking is billed; it can be switched in the project.', max_length=4, verbose_name='trailer billed')),
                ('trailer_surcharge_per_km', models.DecimalField(blank=True, decimal_places=2, help_text='Only for motor vehicles: added to the price per kilometre on trips with a trailer.', max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='trailer surcharge per kilometre (net)')),
                ('vehicle_type', models.CharField(blank=True, choices=[('car', 'motor vehicle'), ('trailer', 'trailer')], help_text='Only for vehicles.', max_length=10, verbose_name='vehicle type')),
            ],
            options={
                'verbose_name': 'product',
                'verbose_name_plural': 'products',
                'ordering': ['article_number'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='KitComponent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name='quantity')),
                ('position', models.PositiveSmallIntegerField(default=0, verbose_name='position')),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='used_in_kits', to='products.product', verbose_name='component')),
                ('kit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='components', to='products.product', verbose_name='kit')),
            ],
            options={
                'verbose_name': 'kit component',
                'verbose_name_plural': 'kit components',
                'ordering': ['position', 'id'],
                'constraints': [models.UniqueConstraint(fields=('kit', 'component'), name='kit_component_unique')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='FixtureTypeMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gdtf_spec', models.CharField(max_length=200, verbose_name='GDTF fixture type')),
                ('gdtf_mode', models.CharField(blank=True, max_length=200, verbose_name='DMX mode')),
                ('label', models.CharField(blank=True, help_text='Manufacturer and model.', max_length=250, verbose_name='fixture type')),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last used')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fixture_type_mappings', to='products.product', verbose_name='product')),
            ],
            options={
                'verbose_name': 'fixture type mapping',
                'verbose_name_plural': 'fixture type mappings',
                'ordering': ['gdtf_spec', 'gdtf_mode'],
                'constraints': [models.UniqueConstraint(fields=('gdtf_spec', 'gdtf_mode'), name='fixture_type_mapping_unique')],
                'indexes': [],
            },
        ),
    ]
