import { describe, expect, it } from "vitest";
import { changedLines } from "@/components/app/ui";

describe("changedLines", () => {
  it("marks only lines that really changed", () => {
    const before = ["STORE_NAME = 'Inkwell'", "CURRENCY = 'USD'", "<script src='paypal.com/sdk/js'>"];
    const after = ["STORE_NAME = 'Inkwell'", "CURRENCY = 'USD'", "SANDBOX_SDK_URL = 'web-sdk/v6'", "<script src='{{PAYPAL_SDK_URL}}'>"];
    const { removed, added } = changedLines(before, after);
    expect(removed).toEqual([false, false, true]);
    expect(added).toEqual([false, false, true, true]);
  });

  it("does not mark blank lines or hunk separators", () => {
    const { removed, added } = changedLines(["", "⋯"], ["⋯", "  "]);
    expect(removed).toEqual([false, false]);
    expect(added).toEqual([false, false]);
  });
});

import { adaptVerification } from "@/lib/checkout/adapt";

describe("adaptVerification", () => {
  it("does not call a failed REAL payment simulated", () => {
    const raw = {
      simulated: false,
      safe_to_approve: false,
      before: { purchase_succeeded: true, order_id: "63041390B7587830T", is_real_sandbox_payment: true, warnings: [] },
      after: { purchase_succeeded: false, error_code: "PAYPAL_BUTTON_MISSING", is_real_sandbox_payment: false, warnings: [] },
    };
    expect(adaptVerification(raw).simulated).toBe(false);
  });

  it("still marks mock runs as simulated", () => {
    expect(adaptVerification({ simulated: true, after: { purchase_succeeded: true } }).simulated).toBe(true);
  });
});
