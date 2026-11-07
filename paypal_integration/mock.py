"""
Fake PayPal client for tests and offline demos (MOCK_PAYPAL=true in .env).

Same methods and return shapes as PayPalClient, but nothing leaves your laptop.
Note: the real PayPal popup in a browser can't approve fake order IDs, so use
the mock only for backend/pipeline tests, not for clicking through a store.
"""

import uuid

from paypal_integration.client import _clean_amount, _safe_id
from paypal_integration.errors import PAYPAL_REQUEST_FAILED, ModuleError


class MockPayPalClient:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}

    def is_configured(self) -> bool:
        return True

    def get_access_token(self) -> str:
        return "mock-token"

    def create_order(self, amount, currency: str = "USD") -> dict:
        order_id = "MOCK" + uuid.uuid4().hex[:13].upper()
        self.orders[order_id] = {"id": order_id, "status": "CREATED",
                                 "amount": _clean_amount(amount), "currency": currency}
        return {"id": order_id, "status": "CREATED",
                "approve_url": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"}

    def get_order(self, order_id: str) -> dict:
        order = self.orders.get(_safe_id(order_id))
        if order is None:
            raise ModuleError(PAYPAL_REQUEST_FAILED, "RESOURCE_NOT_FOUND - order does not exist")
        return dict(order)

    def capture_order(self, order_id: str) -> dict:
        order = self.orders.get(_safe_id(order_id))
        if order is None:
            raise ModuleError(PAYPAL_REQUEST_FAILED, "RESOURCE_NOT_FOUND - order does not exist")
        if order["status"] == "COMPLETED":
            raise ModuleError(PAYPAL_REQUEST_FAILED, "UNPROCESSABLE_ENTITY - ORDER_ALREADY_CAPTURED")
        order["status"] = "COMPLETED"
        return {"id": order_id, "status": "COMPLETED", "capture_id": "MOCKCAP" + order_id[4:],
                "capture_status": "COMPLETED", "amount": order["amount"], "currency": order["currency"],
                "payer_email": "sb-mockbuyer@personal.example.com"}
