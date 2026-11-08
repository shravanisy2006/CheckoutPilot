"""Fake verifier for backend/frontend work without a browser or PayPal (MOCK_VERIFIER=true)."""

import time


def verify_checkout_mock(store_url: str = "http://localhost:8101", label: str = "before", **_) -> dict:
    sdk = "v6" if label == "after" else "v5"
    return {
        "verification_id": f"verify_{label}_mock",
        "store_url": store_url,
        "label": label,
        "purchase_succeeded": True,
        "order_id": "MOCK" + str(int(time.time()))[-9:],
        "order_status": "COMPLETED",
        "amount": "35.00",
        "currency": "USD",
        "paypal_sdk": sdk,
        "payment_saved": False,
        "api_confirmed": True,
        "screenshots": [],
        "steps": [{"name": name, "ok": True, "detail": "", "at_seconds": 0.0} for name in (
            "added_to_cart", "paypal_button_found", "paypal_window_opened",
            "paid_in_paypal_window", "store_success_page", "orders_api_check")],
        "error_code": "",
        "error_message": "",
        "warnings": ["Mock result: no real browser or PayPal was used."],
        "duration_seconds": 0.0,
    }
