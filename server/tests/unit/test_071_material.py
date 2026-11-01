# SPDX-License-Identifier: GPL-3.0-or-later
"""Material: manufacturer and supplier typed and created right there (MAT-048), the power of a model
(MAT-049), new items from a start ID with a serial number each (MAT-050), a product made from a model (MAT-051),
the default storage location (MAT-052), and models assigned from the product's side (PRD-046)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.masterdata import defaults
from rentalars.masterdata.models import CategoryField, FieldType, Manufacturer, StorageLocation, Supplier
from rentalars.material import services
from rentalars.material.forms import ItemCreateForm, MaterialItemForm, MaterialModelForm
from rentalars.material.models import MaterialItem
from rentalars.products import services as product_services
from rentalars.products.models import BillingMode, Product, ProductKind
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    category,
    make_customer,
    make_item,
    make_items,
    make_model,
    make_product,
)

D = Decimal


class StartIdTests(RentalarsTestCase):
    """MAT-050: the first item gets the start ID, each further one the next free ID after it."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM", make_product("K-005"), category_code="K")

    def test_the_following_items_take_the_next_free_ids(self) -> None:
        make_item(self.model, 43)
        created = services.create_items(self.model, 3, inventory_number=42)
        self.assertEqual([item.inventory_number for item in created], [42, 44, 45])

    def test_the_counter_continues_behind_the_last_one(self) -> None:
        services.create_items(self.model, 2, inventory_number=2000)
        self.assertEqual(services.create_items(self.model, 1)[0].inventory_number, 2002)
        self.assertGreaterEqual(NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value, 2002)

    def test_a_taken_start_id_is_refused(self) -> None:
        make_item(self.model, 42)
        with self.assertRaises(ValidationError):
            services.create_items(self.model, 2, inventory_number=42)
        self.assertEqual(MaterialItem.objects.count(), 1)

    def test_without_start_id_the_number_range_gives_the_ids(self) -> None:
        created = services.create_items(self.model, 3)
        self.assertEqual([item.inventory_number for item in created], [1, 2, 3])

    def test_a_long_run_of_taken_ids_is_read_in_windows(self) -> None:
        make_items(self.model, 3)  # 1, 2, 3
        with self.assertNumQueries(1):
            numbers = services.following_free_numbers(1, 3)
        self.assertEqual(numbers, [1, 4, 5])


class SerialNumberTests(RentalarsTestCase):
    """MAT-050: one serial number per item, in the order of the IDs."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Shure SM58", make_product("T-010"), category_code="T")

    def test_each_item_gets_its_serial_number(self) -> None:
        created = services.create_items(self.model, 3, serial_numbers=["A1", "", "A3"])
        self.assertEqual([item.serial_number for item in created], ["A1", "", "A3"])

    def test_fewer_serial_numbers_leave_the_last_items_without(self) -> None:
        created = services.create_items(self.model, 3, serial_numbers=["A1"])
        self.assertEqual([item.serial_number for item in created], ["A1", "", ""])

    def test_more_serial_numbers_than_items_are_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            services.create_items(self.model, 2, serial_numbers=["A1", "A2", "A3"])
        self.assertIn("serial_numbers", caught.exception.message_dict)
        self.assertFalse(MaterialItem.objects.exists())

    def test_a_serial_number_twice_is_created_with_a_warning_of_the_forms(self) -> None:
        # Duplicate serial numbers: a number given twice is a warning
        # (the form asks for "Trotzdem anlegen", see tests/unit/test_095_small_things.py); nothing is unique.
        created = services.create_items(self.model, 2, serial_numbers=["A1", "a1"])
        self.assertEqual([item.serial_number for item in created], ["A1", "a1"])

    def test_empty_lines_at_the_end_do_not_count(self) -> None:
        self.assertEqual(services.check_serial_numbers(["A1", " ", ""], 1), ["A1"])

    def test_the_form_reads_one_per_line(self) -> None:
        form = ItemCreateForm(
            {"count": "2", "status": "available", "serial_numbers": "S-1\r\nS-2\r\n"},
            material_model=self.model,
            rights=ALL_RIGHTS,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["serial_list"], ["S-1", "S-2"])
        too_many = ItemCreateForm(
            {"count": "1", "status": "available", "serial_numbers": "S-1\nS-2"},
            material_model=self.model,
            rights=ALL_RIGHTS,
        )
        self.assertFalse(too_many.is_valid())
        self.assertIn("serial_numbers", too_many.errors)


class TypedNamesTests(RentalarsTestCase):
    """MAT-048, MAT-050: a typed name finds the manufacturer or supplier, a new name creates it."""

    def test_a_known_name_is_found_whatever_the_case(self) -> None:
        cordial = Manufacturer.objects.create(name="Cordial")
        self.assertEqual(services.manufacturer_named(" cordial "), cordial)
        self.assertEqual(Manufacturer.objects.count(), 1)

    def test_a_new_name_creates_it(self) -> None:
        created = services.supplier_named("Musikhaus Nord")
        self.assertEqual(Supplier.objects.get(name="Musikhaus Nord"), created)

    def test_nothing_typed_means_none(self) -> None:
        self.assertIsNone(services.manufacturer_named("  "))
        self.assertIsNone(services.supplier_named(""))

    def test_the_model_form_creates_the_manufacturer(self) -> None:
        form = MaterialModelForm(
            {
                "name": "Sennheiser e935",
                "category": category("T").pk,
                "tracking_mode": "items",
                "manufacturer_name": "Sennheiser",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        model = form.save()
        self.assertEqual(model.manufacturer.name, "Sennheiser")

    def test_the_item_form_creates_the_supplier(self) -> None:
        item = make_items(make_model("Rack", category_code="R"))[0]
        form = MaterialItemForm(
            {"supplier_name": "Thomann", "invoice_number": "RE-4711", "connection_type": "fixed"},
            instance=item,
            rights=ALL_RIGHTS,
        )
        self.assertTrue(form.is_valid(), form.errors)
        services.save_item(form.save(commit=False))
        item.refresh_from_db()
        self.assertEqual((item.supplier.name, item.invoice_number), ("Thomann", "RE-4711"))


class KeptValuesTests(RentalarsTestCase):
    """Lost weight, dimensions and own values when a model or item was saved in the browser (MAT-049)."""

    def test_saving_a_model_keeps_weight_dimensions_and_power(self) -> None:
        model = make_model("Robe Pointe", make_product("L-020"), category_code="L")
        model.weight_kg, model.length_cm, model.power_w = D("15.00"), D("40.0"), D("470.00")
        model.save()
        form = MaterialModelForm(instance=model)
        data = {name: form[name].value() for name in form.fields}
        data = {name: "" if value is None else value for name, value in data.items()}
        data["weight_kg"], data["length_cm"], data["power_w"] = "15", "40", "470"
        bound = MaterialModelForm(data, instance=model)
        self.assertTrue(bound.is_valid(), bound.errors)
        bound.save()
        model.refresh_from_db()
        self.assertEqual((model.weight_kg, model.length_cm, model.power_w), (D("15.00"), D("40.0"), D("470.00")))


class ProductFromModelTests(RentalarsTestCase):
    """MAT-051: one click makes a product of the same name, the model assigned."""

    def test_a_rental_product_of_the_category(self) -> None:
        model = make_model("Robe Pointe", category_code="L")
        product = services.create_product_from_model(model, ALL_RIGHTS)
        model.refresh_from_db()
        self.assertEqual(model.default_product, product)
        self.assertEqual(
            (product.name, product.kind, product.category), ("Robe Pointe", ProductKind.RENTAL, category("L"))
        )
        self.assertEqual((product.article_number, product.price), ("L-001", D("0")))
        self.assertEqual(product.billing_mode, BillingMode.DAILY_PER_PIECE)

    def test_a_sale_product_where_the_category_presets_sale(self) -> None:
        model = make_model("Gaffa-Tape schwarz", category_code="V", bulk=True)
        product = services.create_product_from_model(model, ALL_RIGHTS)
        self.assertEqual((product.kind, product.sale_price, product.price), (ProductKind.SALE, D("0"), None))

    def test_a_model_with_product_is_refused(self) -> None:
        model = make_model("Cordial", make_product("K-005"))
        before = Product.objects.count()
        with self.assertRaises(ValidationError):
            services.create_product_from_model(model, ALL_RIGHTS)
        self.assertEqual(Product.objects.count(), before)

    def test_customer_material_needs_the_form(self) -> None:
        model = make_model("Mischpult der Band", category_code="C")
        with self.assertRaises(ValidationError):
            services.create_product_from_model(model, ALL_RIGHTS)
        self.assertFalse(Product.objects.filter(category__code="C").exists())


class AssignModelTests(RentalarsTestCase):
    """PRD-046: an existing model without product is given to a product from the product's page."""

    def test_the_model_is_assigned(self) -> None:
        product = make_product("K-005")
        model = make_model("Cordial CPM 5 FM", category_code="K")
        self.assertEqual(services.assign_model_to_product(model, product), "")
        model.refresh_from_db()
        self.assertEqual(model.default_product, product)

    def test_another_main_category_gives_a_hint(self) -> None:
        hint = services.assign_model_to_product(make_model("Stativ", category_code="R"), make_product("K-005"))
        self.assertIn("K-005", hint)

    def test_a_model_with_product_or_a_product_without_stock_is_refused(self) -> None:
        other = make_product("K-006")
        with self.assertRaises(ValidationError):
            services.assign_model_to_product(make_model("Cordial", other), make_product("K-005"))
        transport = make_product("F-001", kind=ProductKind.SURCHARGE)
        with self.assertRaises(ValidationError):
            services.assign_model_to_product(make_model("Sprinter", category_code="R"), transport)


class ProductPresetTests(RentalarsTestCase):
    """PRD-046: the kind is chosen first and stays when the category brings its presets."""

    def test_the_category_presetting_the_kind_keeps_its_billing(self) -> None:
        self.assertEqual(product_services.presets_for_kind("rental", category("K")), {"kind": "rental"})

    def test_another_kind_brings_its_own_billing(self) -> None:
        self.assertEqual(
            product_services.presets_for_kind("sale", category("K")), {"kind": "sale", "billing_mode": BillingMode.FLAT}
        )
        self.assertEqual(
            product_services.presets_for_kind("kit", None), {"kind": "kit", "billing_mode": BillingMode.DAILY_PER_KIT}
        )

    def test_customer_material_stays_flat(self) -> None:
        self.assertEqual(product_services.presets_for_kind("kit", category("C"))["billing_mode"], BillingMode.FLAT)


class DefaultLocationTests(RentalarsTestCase):
    """MAT-052: "Hauptlager" is the default; only one location is."""

    def test_start_data_has_the_main_store_as_default(self) -> None:
        self.assertEqual(StorageLocation.get_default().name, "Hauptlager")

    def test_only_one_location_is_the_default(self) -> None:
        hall = StorageLocation(name="Halle 2", is_default=True)
        hall.save()
        self.assertEqual(list(StorageLocation.objects.filter(is_default=True)), [hall])
        self.assertEqual(StorageLocation.get_default(), hall)

    def test_a_deactivated_location_is_not_the_default(self) -> None:
        main = StorageLocation.get_default()
        main.is_active = False
        with self.assertRaises(ValidationError):
            main.full_clean()

    def test_the_form_for_new_items_preselects_it(self) -> None:
        form = ItemCreateForm(material_model=make_model("Rack", category_code="R"), rights=ALL_RIGHTS)
        self.assertEqual(form["storage_location"].value(), StorageLocation.get_default().pk)

    def test_install_again_adds_no_second_store(self) -> None:
        defaults.install()
        self.assertEqual(StorageLocation.objects.filter(name="Hauptlager").count(), 1)

    def test_no_main_store_where_there_are_locations(self) -> None:
        StorageLocation.objects.all().delete()
        StorageLocation.objects.create(name="Halle 1")
        defaults.install()
        self.assertFalse(StorageLocation.objects.filter(name="Hauptlager").exists())


class PowerTests(RentalarsTestCase):
    """MAT-049: the power is a field of every model; a category field for it is neither delivered nor allowed."""

    def test_the_start_data_has_no_power_field(self) -> None:
        self.assertFalse(CategoryField.objects.filter(label="Leistung").exists())
        self.assertEqual(category("K").primary_field.label, "Länge")

    def test_a_category_field_for_the_power_is_refused(self) -> None:
        field = CategoryField(category=category("L"), label="Leistung", field_type=FieldType.NUMBER, unit="W")
        with self.assertRaises(ValidationError):
            field.full_clean()
        CategoryField(category=category("L"), label="Leistung", field_type=FieldType.NUMBER, unit="kW").full_clean()


class CustomerMaterialFormTests(RentalarsTestCase):
    """PRD-043 stays: the product field of a model offers customer material with its owner."""

    def test_the_product_text_names_the_product(self) -> None:
        owner = make_customer("Die Band")
        product = make_product("C-001", "Mischpult der Band", price=None, owner=owner)
        model = make_model("Yamaha CL5", product)
        self.assertEqual(MaterialModelForm(instance=model).product_text, "C-001 Mischpult der Band")
