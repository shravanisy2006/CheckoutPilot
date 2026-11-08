"""Request model for POST /api/verify (see docs/api_contract.md, section 3)."""

from typing import Literal

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    """What to prove with a real PayPal Sandbox payment.

    Send ONE of:
      - ``fix_id``: verify the original store and the code agent's patched copy
        (works once POST /api/fix exists and has registered the fix), or
      - ``after_store`` (and optionally ``before_store``): any two stores to
        compare, e.g. "legacy" and "upgraded".

    A store can be a demo-store name ("legacy", "upgraded"), a store folder
    (e.g. "outputs/patched/fix_123"), or a local URL ("http://localhost:8101").
    """

    fix_id: str | None = Field(None, examples=[None])
    before_store: str | None = Field(None, examples=["legacy"])
    after_store: str | None = Field(None, examples=["upgraded"])
    page: Literal["checkout", "cart"] = Field(
        "checkout", description="Where to click PayPal. 'cart' works on the upgraded store only."
    )
