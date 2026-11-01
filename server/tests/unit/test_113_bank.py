# SPDX-License-Identifier: GPL-3.0-or-later
"""Bank statements – CAMT.053 and CSV, suggestions, booking (DOK-050)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.documents import bank, payments
from rentalars.documents.models import BankImport, BankTransaction
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice
from tests.api.base import API, ApiTestCase
from tests.ui.base import UiTestCase
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)

CAMT = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
 <BkToCstmrStmt><GrpHdr><MsgId>1</MsgId></GrpHdr>
  <Stmt><Id>1</Id><Acct><Id><IBAN>DE02120300000000202051</IBAN></Id></Acct>
   <Ntry><Amt Ccy="EUR">291.50</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOKED</Sts><BookgDt><Dt>2027-03-01</Dt></BookgDt>
    <NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
     <RltdPties><Dbtr><Pty><Nm>Stadt Musterstadt</Nm></Pty></Dbtr><DbtrAcct><Id><IBAN>DE89 3704 0044 0532 0130 00</IBAN></Id></DbtrAcct></RltdPties>
     <RmtInf><Ustrd>Rechnung RE-2027-0001</Ustrd><Ustrd>vom 01.03.</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="EUR">119.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts><BookgDt><Dt>2027-03-01</Dt></BookgDt>
    <NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Tonstudio Lieferant GmbH</Nm></Cdtr><CdtrAcct><Id><IBAN>DE75512108001245126199</IBAN></Id></CdtrAcct></RltdPties>
     <RmtInf><Ustrd>ER-4711</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="EUR">5.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>PDNG</Sts><BookgDt><Dt>2027-03-01</Dt></BookgDt></Ntry>
  </Stmt></BkToCstmrStmt></Document>"""

CSV = (
    "Konto;DE02120300000000202051\n"
    "\n"
    "Buchungstag;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;Verwendungszweck;Betrag\n"
    '01.03.2027;"Stadt Musterstadt";DE89370400440532013000;"Rechnung RE-2027-0001";"1.291,50"\n'
    "01.03.2027;Tonstudio Lieferant GmbH;;ER-4711;-119,00\n"
    "Kontostand;;;;12.000,00\n"
).encode("cp1252")


class BankParserTests(AccountingCase):
    def test_camt_entries_get_sign_party_purpose_and_iban(self) -> None:
        statement = bank.parse(CAMT)
        self.assertEqual((statement.file_format, statement.iban), ("camt053", "DE02120300000000202051"))
        # The pending entry is not on the account yet.
        self.assertEqual(len(statement.rows), 2)
        money_in, money_out = statement.rows
        self.assertEqual((money_in.amount, money_in.counterparty), (D("291.50"), "Stadt Musterstadt"))
        self.assertEqual(money_in.counterparty_iban, "DE89370400440532013000")
        self.assertEqual(money_in.purpose, "Rechnung RE-2027-0001 vom 01.03.")
        self.assertEqual(money_in.end_to_end_id, "")  # NOTPROVIDED is no reference
        self.assertEqual((money_out.amount, money_out.counterparty), (D("-119.00"), "Tonstudio Lieferant GmbH"))

    def test_a_reversal_keeps_the_movement_of_the_account(self) -> None:
        # A returned direct debit: the account is debited (DBIT) and the entry is a reversal. The money left.
        data = CAMT.replace(b"<CdtDbtInd>CRDT</CdtDbtInd>", b"<CdtDbtInd>DBIT</CdtDbtInd><RvslInd>true</RvslInd>")
        self.assertEqual(bank.parse(data).rows[0].amount, D("-291.50"))
        credit = CAMT.replace(b"<CdtDbtInd>DBIT</CdtDbtInd>", b"<CdtDbtInd>CRDT</CdtDbtInd><RvslInd>true</RvslInd>")
        self.assertEqual(bank.parse(credit).rows[1].amount, D("119.00"))

    def test_the_name_of_the_other_side_is_read_in_both_layouts(self) -> None:
        old = CAMT.replace(b"camt.053.001.08", b"camt.053.001.02").replace(
            b"<Pty><Nm>Stadt Musterstadt</Nm></Pty>", b"<Nm>Stadt Musterstadt</Nm>"
        )
        for data in (CAMT, old):
            self.assertEqual(bank.parse(data).rows[0].counterparty, "Stadt Musterstadt")

    def test_amounts_beyond_the_column_and_zero_entries(self) -> None:
        for value in (b"1E+40", b"99999999999999.00", b"10000000000.00"):
            with self.assertRaises(bank.BankFileError, msg=value):
                bank.parse(CAMT.replace(b"291.50", value))
        zero = bank.parse(CAMT.replace(b'<Amt Ccy="EUR">291.50', b'<Amt Ccy="EUR">0.00'))
        self.assertEqual([r.amount for r in zero.rows], [D("-119.00")])

    def test_a_large_statement_is_not_taken_for_a_huge_invoice(self) -> None:
        entry = (
            b'<Ntry><Amt Ccy="EUR">1.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2027-03-01</Dt></BookgDt>'
            b"<NtryDtls><TxDtls><RmtInf><Ustrd>x</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"
        )
        data = (
            b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt>'
            + entry * 9000
            + b"</Stmt></BkToCstmrStmt></Document>"
        )  # about 90,000 elements and 1.2 MB
        self.assertEqual(len(bank.parse(data).rows), 9000)

    def test_a_batch_entry_is_split_when_every_part_names_its_amount(self) -> None:
        data = (
            b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>'
            b'<Ntry><Amt Ccy="EUR">30.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2027-03-01</Dt></BookgDt><NtryDtls>'
            b'<TxDtls><AmtDtls><TxAmt><Amt Ccy="EUR">10.00</Amt></TxAmt></AmtDtls><RmtInf><Ustrd>A</Ustrd></RmtInf></TxDtls>'
            b'<TxDtls><AmtDtls><TxAmt><Amt Ccy="EUR">20.00</Amt></TxAmt></AmtDtls><RmtInf><Ustrd>B</Ustrd></RmtInf></TxDtls>'
            b"</NtryDtls></Ntry></Stmt></BkToCstmrStmt></Document>"
        )
        self.assertEqual([(r.amount, r.purpose) for r in bank.parse(data).rows], [(D("10.00"), "A"), (D("20.00"), "B")])

    def test_csv_with_a_preamble_german_numbers_and_a_footer(self) -> None:
        statement = bank.parse(CSV)
        self.assertEqual(statement.file_format, "csv")
        self.assertEqual(
            [(r.booked_on, r.amount) for r in statement.rows], [(TODAY, D("1291.50")), (TODAY, D("-119.00"))]
        )
        self.assertEqual(statement.rows[0].counterparty_iban, "DE89370400440532013000")
        self.assertEqual(statement.rows[1].counterparty_iban, "")

    def test_csv_with_comma_and_english_names(self) -> None:
        data = b"Date,Amount,Counterparty,Purpose\n2027-03-01,-12.50,Shop,Fee\n"
        self.assertEqual(
            [(r.amount, r.counterparty, r.purpose) for r in bank.parse(data).rows], [(D("-12.50"), "Shop", "Fee")]
        )

    def test_csv_odd_but_real_notations(self) -> None:
        data = (
            "Buchungstag;Betrag;Verwendungszweck;Auftragskonto\n"
            "2027-03-01 00:00:00;12,50-;Rg 1, Kd 2, Dank, Gruß, Hallo, Tschüss;DE02120300000000202051\n"
            "01.03.27;7,25 H;Gutschrift;DE02120300000000202051\n"
            "01.03.27;7,25 S;Lastschrift;DE02120300000000202051\n"
        ).encode("cp1252")
        statement = bank.parse(data)
        self.assertEqual([r.amount for r in statement.rows], [D("-12.50"), D("7.25"), D("-7.25")])
        self.assertEqual((statement.iban, statement.rows[0].purpose[:5]), ("DE02120300000000202051", "Rg 1,"))

    def test_a_row_that_cannot_be_read_refuses_the_file_with_its_line(self) -> None:
        data = b"Datum;Betrag;Verwendungszweck\n01.03.2027;-5,00;a\n02.03.2027;viel;b\n03.03.2027;-1,00;c\n"
        with self.assertRaises(bank.BankFileError) as raised:
            bank.parse(data)
        self.assertIn("3", str(raised.exception))
        # A closing balance without a day is no transaction.
        ok = b"Datum;Betrag\n01.03.2027;-5,00\n;12.000,00\nKontostand;\n"
        self.assertEqual(len(bank.parse(ok).rows), 1)

    def test_what_is_no_statement_is_refused_with_a_reason(self) -> None:
        for data in (
            b"",
            b"Hallo;Welt\n1;2\n",
            b"<a/>",
            b"<?xml version='1.0'?><Document xmlns='urn:x'/>",
            b"Datum;Betrag\n",
        ):
            with self.assertRaises(bank.BankFileError, msg=data):
                bank.parse(data)

    def test_xml_with_entities_is_not_read(self) -> None:
        data = b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x "boom">]><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">&x;</Document>'
        with self.assertRaises(bank.BankFileError) as raised:
            bank.parse(data)
        self.assertTrue(str(raised.exception))

    def test_a_file_that_is_too_large_is_refused(self) -> None:
        with self.assertRaises(bank.BankFileError):
            bank.parse(b"x" * (bank.MAX_BYTES + 1))


class BankImportTests(AccountingCase):
    def test_reading_in_stores_the_transactions_and_not_twice(self) -> None:
        created = bank.import_file(CAMT, "auszug.xml", user=self.user)
        self.assertEqual(
            (created.new_count, created.skipped_count, created.account_iban), (2, 0, "DE02120300000000202051")
        )
        self.assertEqual(BankTransaction.objects.count(), 2)
        with self.assertRaises(ValidationError):
            bank.import_file(CAMT, "again.xml")

    def test_an_overlapping_statement_adds_only_what_is_new(self) -> None:
        bank.import_file(CAMT, "march.xml")
        newer = CAMT.replace(
            b"</Stmt>",
            b'<Ntry><Amt Ccy="EUR">9.99</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2027-03-02</Dt></BookgDt></Ntry></Stmt>',
        )
        second = bank.import_file(newer, "later.xml")
        self.assertEqual((second.new_count, second.skipped_count), (1, 2))
        self.assertEqual(BankTransaction.objects.count(), 3)

    def test_equal_rows_of_two_own_accounts_stay_two(self) -> None:
        row = "01.03.2027;-5,00;Kaffee;{}\n"
        head = "Datum;Betrag;Verwendungszweck;Auftragskonto\n"
        first = bank.import_file((head + row.format("DE02120300000000202051")).encode(), "a.csv")
        second = bank.import_file((head + row.format("DE89370400440532013000")).encode(), "b.csv")
        self.assertEqual((first.new_count, second.new_count), (1, 1))

    def test_two_equal_transactions_on_one_day_stay_two(self) -> None:
        data = b"Datum;Betrag;Verwendungszweck\n01.03.2027;-5,00;Kaffee\n01.03.2027;-5,00;Kaffee\n"
        self.assertEqual(bank.import_file(data, "k.csv").new_count, 2)
        # The same two rows in a bigger file are not new again.
        more = data + b"02.03.2027;-1,00;Tee\n"
        self.assertEqual(bank.import_file(more, "k2.csv").new_count, 1)


class BankNumberTests(AccountingCase):
    def test_a_number_is_found_whole_and_with_any_separators(self) -> None:
        for text in ("Rechnung RE-2027-0001 vom 01.03.", "RE 2027 0001", "re20270001", "Zahlung RE-2027-0001."):
            self.assertTrue(bank.number_in(text, "RE-2027-0001"), text)
        for text in ("RE-2027-00012", "XRE-2027-0001", "RE-2027", "Danke"):
            self.assertFalse(bank.number_in(text, "RE-2027-0001"), text)

    def test_a_short_number_does_not_hide_in_a_longer_one(self) -> None:
        self.assertTrue(bank.number_in("Rg R4711 bezahlt", "R4711"))
        self.assertFalse(bank.number_in("Auftrag XR4711", "R4711"))
        self.assertFalse(bank.number_in("Rg R47110", "R4711"))
        self.assertFalse(bank.number_in("A1 bezahlt", "A1"))  # too short to say anything
        self.assertFalse(bank.number_in("anything", ""))

    def test_a_number_of_digits_is_not_found_in_a_date_or_an_amount(self) -> None:
        self.assertFalse(bank.number_in("Rechnung vom 01.03.2027", "03/2027"))
        self.assertFalse(bank.number_in("Betrag 119,00 EUR", "119"))
        self.assertFalse(bank.number_in("Betrag 12345,67 EUR", "12345"))
        self.assertFalse(bank.number_in("Zahlung 2027", "2027"))
        self.assertTrue(bank.number_in("Rechnung 20270001 danke", "20270001"))
        self.assertTrue(bank.number_in("Rg-Nr. 2027-0001.", "2027-0001"))


class BankBase(AccountingCase):
    def setUp(self) -> None:
        super().setUp()
        self.out = self.invoice()  # RE-2027-0001, 291,50
        self.supplier_invoice = self.incoming("ER-4711", "119.00")
        bank.import_file(CAMT, "auszug.xml", user=self.user)
        self.money_in = BankTransaction.objects.get(amount=D("291.50"))
        self.money_out = BankTransaction.objects.get(amount=D("-119.00"))

    def incoming(self, number: str, gross: str) -> IncomingInvoice:
        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=D("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number=number, total_net=D(gross) / D("1.19"), total_gross=D(gross), invoice_date=TODAY
        )
        return IncomingInvoice.objects.get(pk=invoice.pk)


class BankSuggestionTests(BankBase):
    def suggest(self, tx: BankTransaction) -> list[bank.Suggestion]:
        return bank.suggestions(tx, bank.load_candidates())

    def test_money_in_finds_the_invoice_by_number_and_amount(self) -> None:
        found = self.suggest(self.money_in)
        self.assertEqual([(s.side, s.target.pk) for s in found], [("outgoing", self.out.pk)])
        self.assertGreaterEqual(found[0].score, bank.SCORE_NUMBER + bank.SCORE_AMOUNT)
        self.assertEqual(found[0].amount, D("291.50"))

    def test_money_out_finds_the_incoming_invoice(self) -> None:
        found = self.suggest(self.money_out)
        self.assertEqual(
            [(s.side, s.target.pk, s.amount) for s in found], [("incoming", self.supplier_invoice.pk, D("119.00"))]
        )
        self.assertGreaterEqual(found[0].score, bank.SCORE_NUMBER + bank.SCORE_AMOUNT)

    def test_the_amount_alone_is_enough_the_name_alone_is_not(self) -> None:
        tx = BankTransaction.objects.get(pk=self.money_in.pk)
        tx.purpose = "Danke"
        self.assertEqual([s.score for s in self.suggest(tx)], [bank.SCORE_AMOUNT + bank.SCORE_NAME])
        tx.amount = D("10.00")
        self.assertEqual(self.suggest(tx), [])

    def test_the_wrong_direction_is_not_suggested(self) -> None:
        tx = BankTransaction.objects.get(pk=self.money_in.pk)
        tx.amount = D("-291.50")  # money out cannot pay a customer's invoice
        self.assertEqual(self.suggest(tx), [])

    def test_a_refund_to_a_customer_and_from_a_supplier(self) -> None:
        payments.record(self.out, paid_on=TODAY, amount=D("300.00"), user=self.user)  # 8,50 too much
        refund = BankTransaction.objects.create(
            bank_import=self.money_in.bank_import,
            booked_on=TODAY,
            amount=D("-8.50"),
            purpose="Erstattung RE-2027-0001",
            fingerprint="r1",
        )
        found = self.suggest(refund)
        self.assertEqual([(s.side, s.amount) for s in found], [("outgoing", D("-8.50"))])
        note = self.incoming("GS-1", "-50.00")
        back = BankTransaction.objects.create(
            bank_import=self.money_in.bank_import,
            booked_on=TODAY,
            amount=D("50.00"),
            purpose="Gutschrift GS-1",
            fingerprint="r2",
        )
        found = self.suggest(back)
        self.assertEqual([(s.side, s.target.pk, s.amount) for s in found], [("incoming", note.pk, D("-50.00"))])

    def test_a_foreign_currency_gets_no_suggestion(self) -> None:
        tx = BankTransaction.objects.get(pk=self.money_in.pk)
        tx.currency = "USD"
        self.assertEqual(self.suggest(tx), [])


class BankBookingTests(BankBase):
    def test_booking_money_in_enters_a_payment_and_closes_the_transaction(self) -> None:
        tx = bank.book(self.money_in, "outgoing", self.out.pk, user=self.user)
        self.assertEqual(tx.state, "booked")
        payment = self.out.payments.get()
        self.assertEqual((payment.amount, payment.paid_on, payment.method), (D("291.50"), TODAY, "transfer"))
        self.assertIn("auszug.xml", payment.note)
        self.assertEqual(payments.balance(self.out).state, "paid")
        # It is not suggested again and cannot be booked twice.
        self.assertEqual(bank.suggestions(tx, bank.load_candidates()), [])
        with self.assertRaises(ValidationError):
            bank.book(tx, "outgoing", self.out.pk, user=self.user)

    def test_booking_money_out_pays_the_incoming_invoice(self) -> None:
        bank.book(self.money_out, "incoming", self.supplier_invoice.pk, user=self.user)
        self.assertEqual(self.supplier_invoice.payments.get().amount, D("119.00"))
        self.assertEqual(incoming_payments.balance(self.supplier_invoice).state, "paid")

    def test_refunds_are_negative_payments_in_both_directions(self) -> None:
        payments.record(self.out, paid_on=TODAY, amount=D("300.00"), user=self.user)
        refund = BankTransaction.objects.create(
            bank_import=self.money_in.bank_import, booked_on=TODAY, amount=D("-8.50"), fingerprint="r1"
        )
        bank.book(refund, "outgoing", self.out.pk, user=self.user)
        self.assertEqual(sorted(p.amount for p in self.out.payments.all()), [D("-8.50"), D("300.00")])
        note = self.incoming("GS-1", "-50.00")
        back = BankTransaction.objects.create(
            bank_import=self.money_in.bank_import, booked_on=TODAY, amount=D("50.00"), fingerprint="r2"
        )
        bank.book(back, "incoming", note.pk, user=self.user)
        self.assertEqual(note.payments.get().amount, D("-50.00"))
        self.assertEqual(incoming_payments.credit_items(today=TODAY), [])

    def test_a_voided_payment_opens_the_transaction_again(self) -> None:
        bank.book(self.money_in, "outgoing", self.out.pk, user=self.user)
        payments.void(self.out.payments.get(), reason="wrong invoice", user=self.user)
        tx = BankTransaction.objects.get(pk=self.money_in.pk)
        self.assertEqual(tx.state, "open")
        bank.book(tx, "outgoing", self.out.pk, user=self.user)  # booked again, at the right invoice
        self.assertEqual(BankTransaction.objects.get(pk=tx.pk).state, "booked")
        self.assertEqual(sorted(p.voided_at is None for p in self.out.payments.all()), [False, True])

    def test_booking_against_the_direction_of_the_invoice_is_refused(self) -> None:
        # Money paid out cannot be a payment of a customer's invoice; money received not a payment to a supplier.
        with self.assertRaises(ValidationError):
            bank.book(self.money_out, "outgoing", self.out.pk, user=self.user)
        with self.assertRaises(ValidationError):
            bank.book(self.money_in, "incoming", self.supplier_invoice.pk, user=self.user)
        self.assertEqual((self.out.payments.count(), self.supplier_invoice.payments.count()), (0, 0))
        self.assertEqual(BankTransaction.objects.filter(matched_at__isnull=False).count(), 0)

    def test_an_invoice_in_a_foreign_currency_is_neither_suggested_nor_booked(self) -> None:
        IncomingInvoice.objects.filter(pk=self.supplier_invoice.pk).update(currency="USD")
        self.assertEqual(bank.suggestions(self.money_out, bank.load_candidates()), [])
        with self.assertRaises(ValidationError):
            bank.book(self.money_out, "incoming", self.supplier_invoice.pk, user=self.user)
        self.assertEqual(self.supplier_invoice.payments.count(), 0)

    def test_a_refused_payment_books_nothing(self) -> None:
        future = BankTransaction.objects.create(
            bank_import=self.money_in.bank_import,
            booked_on=datetime.date(2099, 1, 1),
            amount=D("1.00"),
            fingerprint="f",
        )
        with self.assertRaises(ValidationError):
            bank.book(future, "outgoing", self.out.pk, user=self.user)
        self.assertEqual(BankTransaction.objects.get(pk=future.pk).state, "open")
        with self.assertRaises(ValidationError):
            bank.book(self.money_in, "outgoing", 999_999, user=self.user)
        with self.assertRaises(ValidationError):
            bank.book(self.money_in, "elsewhere", self.out.pk, user=self.user)

    def test_ignoring_needs_a_reason_and_can_be_taken_back(self) -> None:
        with self.assertRaises(ValidationError):
            bank.ignore(self.money_in, reason="  ")
        tx = bank.ignore(self.money_in, reason="private", user=self.user)
        self.assertEqual((tx.state, tx.ignore_reason), ("ignored", "private"))
        with self.assertRaises(ValidationError):
            bank.book(tx, "outgoing", self.out.pk, user=self.user)
        self.assertEqual(bank.restore(tx).state, "open")
        with self.assertRaises(ValidationError):
            bank.restore(tx)


class BankPageTests(UiTestCase, BankBase):
    def test_the_page_shows_transactions_with_suggestions_and_the_tab(self) -> None:
        page = self.assert_ok(self.client.get(reverse("documents:bank")))
        self.assertIn("Stadt Musterstadt", page)
        self.assertIn(self.out.number, page)
        self.assertIn(reverse("documents:bank_book", args=[self.money_in.pk]), page)
        self.assertIn(
            'href="' + reverse("documents:bank") + '"', self.assert_ok(self.client.get(reverse("documents:open_items")))
        )

    def test_booking_by_a_click_enters_the_payment(self) -> None:
        response = self.client.post(
            reverse("documents:bank_book", args=[self.money_in.pk]),
            {"side": "outgoing", "target": self.out.pk, "state": "open"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.out.payments.count(), 1)
        page = self.assert_ok(self.client.get(reverse("documents:bank") + "?state=booked"))
        self.assertIn('data-state="booked"', page)
        self.assertIn(self.out.number, page)

    def test_a_wrong_choice_is_said_and_books_nothing(self) -> None:
        response = self.client.post(
            reverse("documents:bank_book", args=[self.money_in.pk]), {"side": "outgoing", "target": "x"}, follow=True
        )
        self.assertEqual(self.out.payments.count(), 0)
        self.assertTrue(self.messages_of(response))

    def test_ignore_and_take_back(self) -> None:
        self.client.post(reverse("documents:bank_ignore", args=[self.money_out.pk]), {"reason": "private"})
        page = self.assert_ok(self.client.get(reverse("documents:bank") + "?state=ignored"))
        self.assertIn("private", page)
        self.client.post(reverse("documents:bank_restore", args=[self.money_out.pk]))
        self.assertEqual(BankTransaction.objects.get(pk=self.money_out.pk).state, "open")

    def test_upload_reads_a_file_and_says_what_is_wrong(self) -> None:
        BankTransaction.objects.all().delete()
        BankImport.objects.all().delete()
        url = reverse("documents:bank_upload")
        response = self.client.post(url, {"file": SimpleUploadedFile("a.xml", CAMT)}, follow=True)
        self.assertEqual(BankTransaction.objects.count(), 2)
        self.assertIn("2", " ".join(self.messages_of(response)))
        again = self.client.post(url, {"file": SimpleUploadedFile("a.xml", CAMT)}, follow=True)
        self.assertEqual(BankTransaction.objects.count(), 2)
        self.assertTrue(self.messages_of(again))
        bad = self.client.post(url, {"file": SimpleUploadedFile("b.csv", b"nothing useful")}, follow=True)
        self.assertTrue(self.messages_of(bad))
        self.assertTrue(self.messages_of(self.client.post(url, {}, follow=True)))

    def test_only_who_may_see_both_sides_may_open_the_page(self) -> None:
        for username, role in (("lagerist", "Lager"), ("crewperson", "Crew")):
            browser = self.browser_for(username, role)
            self.assertEqual(browser.get(reverse("documents:bank")).status_code, 403, role)
            self.assertEqual(
                browser.post(reverse("documents:bank_ignore", args=[self.money_in.pk]), {"reason": "x"}).status_code,
                403,
            )
        self.assertEqual(BankTransaction.objects.get(pk=self.money_in.pk).state, "open")


class BankApiTests(BankBase, ApiTestCase):
    base = f"{API}/accounting/bank"

    def test_list_with_suggestions_and_states(self) -> None:
        body = self.admin.get(f"{self.base}/transactions").json()
        self.assertEqual(body["count"], 2)
        by_amount = {r["amount"]: r for r in body["results"]}
        suggestion = by_amount["291.50"]["suggestions"][0]
        self.assertEqual(
            (suggestion["side"], suggestion["invoice"], suggestion["number"]),
            ("outgoing", self.out.pk, self.out.number),
        )
        self.assertEqual(self.admin.get(f"{self.base}/transactions?state=booked").json()["count"], 0)
        self.assertEqual(
            self.admin.get(f"{self.base}/transactions?suggestions=false").json()["results"][0]["suggestions"], []
        )
        self.assertEqual(self.admin.get(f"{self.base}/transactions?state=nope").status_code, 400)
        self.assertEqual(self.admin.get(f"{self.base}/transactions?limit=1").json()["results"].__len__(), 1)

    def test_book_ignore_restore(self) -> None:
        url = f"{self.base}/transactions/{self.money_in.pk}"
        booked = self.admin.post(f"{url}/book", {"side": "outgoing", "invoice": self.out.pk}, format="json")
        self.assertEqual(booked.status_code, 200, booked.content)
        self.assertEqual(
            (booked.json()["state"], booked.json()["invoice"], booked.json()["side"]),
            ("booked", self.out.pk, "outgoing"),
        )
        self.assertEqual(
            self.admin.post(f"{url}/book", {"side": "outgoing", "invoice": self.out.pk}, format="json").status_code, 400
        )
        other = f"{self.base}/transactions/{self.money_out.pk}"
        self.assertEqual(self.admin.post(f"{other}/ignore", {}, format="json").status_code, 400)
        ignored = self.admin.post(f"{other}/ignore", {"reason": "private"}, format="json")
        self.assertEqual((ignored.status_code, ignored.json()["state"]), (200, "ignored"))
        self.assertEqual(self.admin.post(f"{other}/restore", format="json").json()["state"], "open")
        self.assertEqual(self.admin.post(f"{other}/restore", format="json").status_code, 400)
        self.assertEqual(
            self.admin.post(
                f"{self.base}/transactions/999999/book", {"side": "outgoing", "invoice": 1}, format="json"
            ).status_code,
            404,
        )

    def test_upload_and_the_list_of_statements(self) -> None:
        BankTransaction.objects.all().delete()
        BankImport.objects.all().delete()
        created = self.admin.post(
            f"{self.base}/imports", {"file": SimpleUploadedFile("a.xml", CAMT)}, format="multipart"
        )
        self.assertEqual((created.status_code, created.json()["new_count"]), (201, 2), created.content)
        again = self.admin.post(f"{self.base}/imports", {"file": SimpleUploadedFile("a.xml", CAMT)}, format="multipart")
        self.assertEqual(again.status_code, 400)
        bad = self.admin.post(f"{self.base}/imports", {"file": SimpleUploadedFile("b.csv", b"x")}, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.admin.post(f"{self.base}/imports", {}, format="multipart").status_code, 400)
        self.assertEqual(len(self.admin.get(f"{self.base}/imports").json()), 1)

    def test_rights(self) -> None:
        for username, role in (("lars3", "Lager"), ("crew2", "Crew")):
            client = self.client_for(username, role)
            self.assertEqual(client.get(f"{self.base}/transactions").status_code, 403)
            self.assertEqual(client.get(f"{self.base}/imports").status_code, 403)
            self.assertEqual(
                client.post(
                    f"{self.base}/imports", {"file": SimpleUploadedFile("a.xml", CAMT)}, format="multipart"
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    f"{self.base}/transactions/{self.money_in.pk}/book",
                    {"side": "outgoing", "invoice": self.out.pk},
                    format="json",
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    f"{self.base}/transactions/{self.money_in.pk}/ignore", {"reason": "x"}, format="json"
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(f"{self.base}/transactions/{self.money_in.pk}/restore", format="json").status_code, 403
            )
