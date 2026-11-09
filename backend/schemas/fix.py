"""Request model for POST /api/fix (see docs/api_contract.md, section 2)."""

from pydantic import BaseModel, Field

DEFAULT_FIXABLE = ["sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"]


class FixRequest(BaseModel):
    """Which store to upgrade and which issues to fix.

    ``scan_id`` (from POST /api/scan) picks the store that was scanned; or name it with
    ``store`` ("legacy"). The code agent only patches stores whose code we have (our demo
    stores); for a real merchant it would work on their repository instead.
    """

    scan_id: str | None = Field(None, examples=[None])
    store: str | None = Field(None, examples=["legacy"])
    issue_ids: list[str] = Field(default_factory=lambda: list(DEFAULT_FIXABLE), examples=[DEFAULT_FIXABLE])
