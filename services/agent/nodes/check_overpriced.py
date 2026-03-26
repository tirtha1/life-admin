"""
Node: check_overpriced
Uses Claude to evaluate whether the bill amount is unusually high for its type.
Returns a pricing_verdict: "overpriced" | "fair" | "unknown"
"""
import os
import structlog

import anthropic

from services.agent.state import AgentState

log = structlog.get_logger()

ANTHROPIC_MODEL = "claude-opus-4-6"

# Rough Indian market benchmarks (INR) for common bill types
# Used as context for Claude — not hardcoded thresholds
MARKET_BENCHMARKS = {
    "electricity": {"low": 500, "high": 5000, "unit": "per month for residential"},
    "water": {"low": 100, "high": 800, "unit": "per month for residential"},
    "internet": {"low": 400, "high": 2000, "unit": "per month broadband"},
    "mobile": {"low": 200, "high": 1500, "unit": "per month postpaid"},
    "subscription": {"low": 99, "high": 1500, "unit": "per month streaming/software"},
    "insurance": {"low": 500, "high": 15000, "unit": "per month premium"},
    "credit_card": {"low": 1000, "high": 100000, "unit": "statement total"},
    "loan": {"low": 2000, "high": 50000, "unit": "monthly EMI"},
    "gas": {"low": 800, "high": 1200, "unit": "per LPG cylinder"},
    "rent": {"low": 5000, "high": 80000, "unit": "per month"},
}

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
    return _client


def check_overpriced(state: AgentState) -> dict:
    """
    Use Claude to assess whether the bill amount is unusually high.
    Skips if amount is None or bill_type has no benchmark.
    """
    amount = state.get("amount")
    bill_type = state.get("bill_type", "other")
    currency = state.get("currency", "INR")
    provider = state.get("provider", "")

    if amount is None:
        return {
            "pricing_verdict": "unknown",
            "market_context": None,
            "execution_notes": ["No amount available — pricing check skipped"],
        }

    benchmark = MARKET_BENCHMARKS.get(bill_type)
    if not benchmark or currency != "INR":
        return {
            "pricing_verdict": "unknown",
            "market_context": None,
            "execution_notes": [
                f"No benchmark available for {bill_type}/{currency} — pricing check skipped"
            ],
        }

    # Quick heuristic: if > 3x benchmark high → likely overpriced without LLM call
    if amount > benchmark["high"] * 3:
        context = (
            f"Amount {currency} {amount:,.0f} is more than 3x the typical high "
            f"({benchmark['high']:,.0f}) for {bill_type} ({benchmark['unit']})"
        )
        log.info(
            "Pricing heuristic: overpriced",
            bill_id=state["bill_id"],
            amount=amount,
            benchmark_high=benchmark["high"],
        )
        return {
            "pricing_verdict": "overpriced",
            "market_context": context,
            "execution_notes": [f"Pricing: overpriced (heuristic) — {context}"],
        }

    # For borderline cases: ask Claude
    try:
        client = _get_client()
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Is {currency} {amount:,.2f} an unusually high amount for a "
                        f"{bill_type} bill from '{provider}' in India?\n"
                        f"Typical range: {benchmark['low']:,}–{benchmark['high']:,} INR "
                        f"{benchmark['unit']}.\n"
                        f"Reply with EXACTLY one word: 'overpriced', 'fair', or 'unknown'. "
                        f"Then one sentence explanation."
                    ),
                }
            ],
        )
        reply = response.content[0].text.strip().lower()
        verdict = "unknown"
        if reply.startswith("overpriced"):
            verdict = "overpriced"
        elif reply.startswith("fair"):
            verdict = "fair"

        log.info(
            "Pricing verdict from Claude",
            bill_id=state["bill_id"],
            verdict=verdict,
            amount=amount,
        )
        return {
            "pricing_verdict": verdict,
            "market_context": reply[:200],
            "execution_notes": [f"Pricing: {verdict} — {reply[:100]}"],
        }

    except Exception as exc:
        log.warning(
            "Pricing check failed",
            bill_id=state["bill_id"],
            error=str(exc),
        )
        return {
            "pricing_verdict": "unknown",
            "market_context": None,
            "execution_notes": [f"Pricing check error: {exc}"],
        }
