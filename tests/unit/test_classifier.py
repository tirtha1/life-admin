"""
Unit tests for the bill classifier.
"""
import pytest
from services.processor.classifier import is_bill_candidate, classify_bill_type


class TestIsBillCandidate:
    def test_bill_keyword_in_subject(self):
        assert is_bill_candidate("Airtel Bill - June 2025", "", "") is True

    def test_invoice_keyword(self):
        assert is_bill_candidate("Invoice #12345 from AWS", "Amount due: $50", "") is True

    def test_payment_due_keyword(self):
        assert is_bill_candidate("Payment due for your subscription", "", "") is True

    def test_hindi_keyword(self):
        assert is_bill_candidate("आपका बिल", "", "") is True

    def test_negative_marketing(self):
        assert is_bill_candidate(
            "unsubscribe from our marketing emails",
            "great deals await",
            ""
        ) is False

    def test_amount_and_due_date_in_body(self):
        assert is_bill_candidate(
            "Account Update",
            "Your account statement",
            "Due date: 15 Jun 2025\nTotal: ₹1,500.00",
        ) is True

    def test_non_bill_email(self):
        assert is_bill_candidate(
            "Welcome to Netflix!",
            "Start watching today",
            "Enjoy unlimited movies",
        ) is False

    def test_empty_email(self):
        assert is_bill_candidate("", "", "") is False


class TestClassifyBillType:
    def test_electricity(self):
        assert classify_bill_type("Electricity Bill June 2025", "bescom@karnataka.gov.in") == "electricity"

    def test_mobile(self):
        assert classify_bill_type("Airtel Postpaid Bill", "noreply@airtel.com") == "mobile"

    def test_jio(self):
        assert classify_bill_type("Jio Postpaid Bill", "") == "mobile"

    def test_credit_card(self):
        assert classify_bill_type("HDFC Credit Card Statement", "") == "credit_card"

    def test_internet(self):
        assert classify_bill_type("Broadband Bill - July", "billing@actsfiber.com") == "internet"

    def test_subscription(self):
        assert classify_bill_type("Netflix subscription renewal", "") == "subscription"

    def test_unknown_defaults_to_other(self):
        assert classify_bill_type("Random subject", "unknown@example.com") == "other"
