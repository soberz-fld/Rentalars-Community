# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``customers`` from 0001_initial to 0007_maps_080 in one.

Squashed: a new database is built from here, and a database that has applied the replaced
migrations counts it as applied (``replaces``). Data steps that only converted the data of older
versions are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.core.uploads
import rentalars.customers.models
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('customers', '0001_initial'), ('customers', '0002_venue'), ('customers', '0003_stage5'), ('customers', '0004_customer_import_lexware'), ('customers', '0005_lexware_contact'), ('customers', '0006_reactivate_quick_created'), ('customers', '0007_maps_080')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(editable=False, max_length=30, unique=True, verbose_name='customer number')),
                ('kind', models.CharField(choices=[('company', 'company or organisation'), ('private', 'private person')], default='company', max_length=10, verbose_name='kind')),
                ('name', models.CharField(max_length=200, verbose_name='name or company')),
                ('name_addition', models.CharField(blank=True, help_text='Department, c/o …', max_length=200, verbose_name='addition')),
                ('street', models.CharField(blank=True, max_length=200, verbose_name='street and number')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('city', models.CharField(blank=True, max_length=120, verbose_name='city')),
                ('country', models.CharField(blank=True, max_length=80, verbose_name='country')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='e-mail')),
                ('phone', models.CharField(blank=True, max_length=60, verbose_name='phone')),
                ('note', models.TextField(blank=True, verbose_name='note')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('anonymised_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='anonymised')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('buyer_reference', models.CharField(blank=True, help_text='For invoices to public authorities: the Leitweg-ID. Empty: the electronic invoice names the project number as buyer reference.', max_length=100, verbose_name='Leitweg-ID or buyer reference')),
                ('default_discount_percent', models.DecimalField(decimal_places=2, default=Decimal('0'), help_text="Taken over by every new material line of the customer's projects; changeable per line.", max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='standard discount in percent')),
                ('payment_terms_days', models.PositiveSmallIntegerField(blank=True, help_text='Empty: as in the company settings.', null=True, validators=[django.core.validators.MaxValueValidator(365)], verbose_name='payment terms in days')),
                ('vat_id', models.CharField(blank=True, help_text='e.g. DE123456789', max_length=30, validators=[rentalars.customers.models.validate_vat_id], verbose_name='VAT ID')),
                ('tax_number', models.CharField(blank=True, max_length=40, verbose_name='tax number')),
                ('lexware_contact_id', models.CharField(blank=True, editable=False, max_length=40, verbose_name='contact in Lexware Office')),
            ],
            options={
                'verbose_name': 'customer',
                'verbose_name_plural': 'customers',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='name')),
                ('position', models.CharField(blank=True, help_text='e.g. technical director', max_length=120, verbose_name='position')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='e-mail')),
                ('phone', models.CharField(blank=True, max_length=60, verbose_name='phone')),
                ('is_primary', models.BooleanField(default=False, verbose_name='primary contact')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='customers.customer', verbose_name='customer')),
                ('salutation', models.CharField(blank=True, help_text='e.g. Ms, Mr, Dr', max_length=40, verbose_name='salutation')),
            ],
            options={
                'verbose_name': 'contact',
                'verbose_name_plural': 'contacts',
                'ordering': ['-is_primary', 'name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Venue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='name')),
                ('street', models.CharField(blank=True, max_length=200, verbose_name='street and number')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('city', models.CharField(blank=True, max_length=120, verbose_name='city')),
                ('country', models.CharField(blank=True, max_length=80, verbose_name='country')),
                ('contact_name', models.CharField(blank=True, max_length=200, verbose_name='contact on site')),
                ('contact_phone', models.CharField(blank=True, max_length=60, verbose_name='phone on site')),
                ('contact_email', models.EmailField(blank=True, max_length=254, verbose_name='e-mail on site')),
                ('access_notes', models.TextField(blank=True, help_text='Loading bay, height limits, parking, keys …', verbose_name='access and loading')),
                ('power_notes', models.TextField(blank=True, help_text='Connections, fuses, distances …', verbose_name='power')),
                ('notes', models.TextField(blank=True, verbose_name='notes')),
                ('hall_plan', models.FileField(blank=True, help_text='PDF or image.', upload_to='venues/', validators=[rentalars.core.uploads.validate_document_upload], verbose_name='hall plan')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'venue',
                'verbose_name_plural': 'venues',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='CustomerAddress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('billing', 'billing address'), ('delivery', 'delivery address')], default='delivery', max_length=10, verbose_name='kind')),
                ('label', models.CharField(blank=True, help_text='e.g. “Warehouse Nord”', max_length=120, verbose_name='label')),
                ('name', models.CharField(blank=True, help_text='Empty: the name of the customer.', max_length=200, verbose_name='name or company')),
                ('name_addition', models.CharField(blank=True, help_text='Department, c/o …', max_length=200, verbose_name='addition')),
                ('street', models.CharField(max_length=200, verbose_name='street and number')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('city', models.CharField(max_length=120, verbose_name='city')),
                ('country', models.CharField(blank=True, max_length=80, verbose_name='country')),
                ('is_default', models.BooleanField(default=False, help_text='New projects take this address.', verbose_name='default')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addresses', to='customers.customer', verbose_name='customer')),
            ],
            options={
                'verbose_name': 'address',
                'verbose_name_plural': 'addresses',
                'ordering': ['kind', '-is_default', 'label', 'city'],
                'indexes': [],
                'constraints': [],
            },
        ),
    ]
