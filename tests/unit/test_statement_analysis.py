import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "backend"))

from app.models.transaction import TransactionCategory
from app.services.statement_analysis import analyze_statement_file


@pytest.mark.asyncio
async def test_csv_statement_analysis_detects_leaks_and_actions():
    csv_content = """Date,Description,Amount
2026-01-05,NETFLIX INDIA,-649
2026-02-05,NETFLIX INDIA,-649
2026-03-02,Swiggy order 1,-1200
2026-03-07,Swiggy order 2,-1500
2026-03-11,Swiggy order 3,-1800
2026-03-18,Swiggy order 4,-1000
2026-03-25,Swiggy order 5,-900
2026-03-15,Salary,50000
2026-03-20,Amazon Purchase,-5000
"""

    response = await analyze_statement_file("march-statement.csv", csv_content.encode("utf-8"))

    assert response.file_type == "csv"
    assert response.summary.total_spent == pytest.approx(12698.0)
    assert response.summary.total_income == pytest.approx(50000.0)
    assert response.summary.top_category == TransactionCategory.FOOD
    assert response.summary.potential_monthly_savings > 0
    assert any(item.merchant == "Netflix" for item in response.recurring_payments)
    assert any(action.title == "Cap food delivery spend" for action in response.suggested_actions)
    assert any(action.action_type == "cancel_subscription" for action in response.suggested_actions)
    assert any(insight.category == TransactionCategory.FOOD for insight in response.leak_insights)


@pytest.mark.asyncio
async def test_csv_statement_neftcr_is_treated_as_credit_not_recurring_debit():
    csv_content = """Date,Description,Amount
2026-01-25,Neftcr Scbl Natixisglobalservi,87448
2026-02-25,Neftcr Scbl Natixisglobalservi,87448
2026-03-25,Neftcr Scbl Natixisglobalservi,87448
2026-03-10,Netflix,-649
"""

    response = await analyze_statement_file("credits.csv", csv_content.encode("utf-8"))

    assert response.summary.total_income == pytest.approx(262344.0)
    assert response.summary.total_spent == pytest.approx(649.0)
    assert all(txn.type == "credit" for txn in response.transactions if "Neftcr" in txn.description)
    assert not any(item.merchant == "Neftcr Scbl Natixisglobalservi" for item in response.recurring_payments)


@pytest.mark.asyncio
async def test_pdf_statement_analysis_uses_fallback_parser():
    pdf_bytes = b"""%PDF-1.4
1 0 obj
<< /Length 140 >>
stream
01/03/2026 NETFLIX 649.00 DR
03/03/2026 SWIGGY 450.00 DR
05/03/2026 SALARY 50000.00 CR
endstream
endobj
%%EOF
"""

    response = await analyze_statement_file("demo.pdf", pdf_bytes)

    assert response.file_type == "pdf"
    assert response.summary.transaction_count >= 3
    assert any(txn.merchant == "Netflix" for txn in response.transactions)
    assert any(txn.merchant == "Swiggy" for txn in response.transactions)
    assert response.parser_used in {"pdf-text-fallback", "pdfplumber"}


@pytest.mark.asyncio
async def test_pdf_statement_prefers_transaction_amount_over_reference_or_balance():
    pdf_bytes = b"""%PDF-1.4
1 0 obj
<< /Length 220 >>
stream
01/03/2026 SWIGGY ORDER 123456 649.00 50,567.31
03/03/2026 NETFLIX 654321 149.00 50,418.31
endstream
endobj
%%EOF
"""

    response = await analyze_statement_file("amount-priority.pdf", pdf_bytes)

    assert response.summary.total_spent == pytest.approx(798.0)
    assert [txn.amount for txn in response.transactions] == [649.0, 149.0]
