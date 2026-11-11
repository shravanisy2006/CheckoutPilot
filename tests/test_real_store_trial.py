"""Tests for scripts/real_store_trial.py (no internet needed)."""

from scripts import real_store_trial as trial


def test_reached_letters_and_verdicts():
    good = {"url": "u", "error": "", "sdk": "v5", "health": 21, "issues": [], "seconds": 1,
            "reached": {"desktop": {"product": True, "cart": True, "checkout": True},
                        "mobile": {"product": True, "cart": False, "checkout": True}}}
    assert trial.reached_text(good) == "desktop PCK / mobile P-K"
    assert trial.verdict(good) == "GOOD for demo"
    # All pages reached but the store doesn't use PayPal: say so, not "pages not reached".
    assert trial.verdict(dict(good, sdk="none")) == "reached, but no PayPal found"
    cart_missing = dict(good, reached={"desktop": {"product": True, "cart": False, "checkout": False}})
    assert trial.verdict(cart_missing) == "PayPal found, but the cart/checkout could not be reached"
    assert trial.verdict(dict(good, error="blocked")) == "skip (scan failed)"


def test_failed_scan_gets_no_score(monkeypatch, tmp_path):
    import scanner
    monkeypatch.setattr(scanner, "scan_store", lambda *a, **k: {
        "status": "failed", "detected_sdk_version": "unknown", "errors": ["blocked"], "pages": []})
    row = trial.scan_one("https://blocked.example", tmp_path, include_mobile=False)
    assert row["health"] is None and row["issues"] == [] and row["verdict"] == "skip (scan failed)"


def test_read_urls_from_file(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# comment\nhttps://a.example  # note\n\nhttps://a.example\nhttps://b.example\n")

    class Args:
        urls = ["https://c.example"]
        file = str(f)
    assert trial.read_urls(Args) == ["https://c.example", "https://a.example", "https://b.example"]
