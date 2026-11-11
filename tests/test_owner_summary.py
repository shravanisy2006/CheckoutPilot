"""Plain-language owner summary: AI with guardrails, template fallback. Run: pytest tests/test_owner_summary.py -v"""

from ai_engine.summary import summarize_for_owner, template_summary

SCAN = {
    "health_score": 21, "health_label": "poor", "paypal_sdk_version": "v5",
    "issues": [
        {"title": "PayPal JavaScript SDK v5 is outdated", "severity": "high", "surface": "both", "priority": 1},
        {"title": "PayPal button missing on the cart page", "severity": "high", "surface": "both", "priority": 2},
    ],
}


def _model(reply):
    return lambda system, prompt, images: reply


def test_ai_summary_is_used_when_it_follows_the_rules():
    text = ("Your checkout scores 21/100, which is poor. The main problem is that it runs an older version of "
            "PayPal's code. Upgrade it first.")
    result = summarize_for_owner(SCAN, call_model=_model(text))
    assert result == {"text": text, "generated_by": "ai"}


def test_promises_or_invented_numbers_fall_back_to_the_template():
    for bad in ["Fixing this will raise sales by 30%.", "You lose $500 a month.",
                "Your score is 45/100.", "**Summary**: upgrade now."]:
        result = summarize_for_owner(SCAN, call_model=_model(bad))
        assert result["generated_by"] == "template", bad


def test_model_errors_fall_back_to_the_template():
    def broken(system, prompt, images):
        raise RuntimeError("network down")
    assert summarize_for_owner(SCAN, call_model=broken)["generated_by"] == "template"


def test_the_model_only_sees_findings_not_page_content():
    seen = {}
    def spy(system, prompt, images):
        seen["prompt"], seen["images"] = prompt, images
        return "Your checkout scores 21/100. Upgrade PayPal first."
    summarize_for_owner({**SCAN, "pages": [{"html": "<secret>"}]}, call_model=spy)
    assert "<secret>" not in seen["prompt"] and seen["images"] == []


def test_template_reads_well():
    text = template_summary(SCAN)
    assert text.startswith("Your PayPal checkout scores 21/100 (poor).")
    assert "PayPal JavaScript SDK v5 is outdated" in text and "1 smaller issue" in text
    assert "looks healthy" in template_summary({"health_score": 100, "issues": []})
