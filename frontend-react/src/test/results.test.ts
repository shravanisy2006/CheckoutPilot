import { describe, expect, it } from "vitest";
import { compareScans, estimate, SCENARIOS } from "@/components/app/Results";
import { csvFileName } from "@/components/app/IssuesGrid";
import { adaptScan } from "@/lib/checkout/adapt";
import type { ScanResult } from "@/lib/checkout/types";

const scan = (score: number, ids: string[]): ScanResult => ({
  scan_id: "s",
  store_url: "http://localhost:8101",
  health_score: score,
  issues: ids.map((id) => ({ id, title: id, severity: "high", explanation: "", evidence: [] })),
  recommendations: [],
});

describe("compareScans", () => {
  it("counts fixed issues and the health change", () => {
    const r = compareScans(scan(21, ["sdk_outdated", "no_paypal_on_cart", "no_paypal_on_product"]), scan(76, ["no_paypal_on_product"]));
    expect(r.delta).toBe(55);
    expect(r.fixedCount).toBe(2);
    expect(r.changes.find((c) => c.id === "no_paypal_on_product")?.fixed).toBe(false);
  });
});

describe("estimate", () => {
  it("is plain arithmetic on the merchant's own numbers", () => {
    const r = estimate(400, 45, 30); // 400 x $45 x 30% = $5,400 a month through PayPal
    expect(r.paypalMonthly).toBe(5400);
    expect(r.rows.map((x) => x.pct)).toEqual(SCENARIOS);
    expect(r.rows[0]).toEqual({ pct: 1, monthly: 54, yearly: 648 });
  });

  it("treats empty or silly input as zero and caps the share at 100%", () => {
    expect(estimate(NaN, -5, 30).paypalMonthly).toBe(0);
    expect(estimate(10, 10, 250).paypalMonthly).toBe(100);
  });
});

describe("csvFileName", () => {
  it("names the file after the store and date", () => {
    expect(csvFileName("https://demo.paypal.com/us/demo/home", new Date("2026-11-11T10:00:00Z"))).toBe(
      "checkoutpilot-findings-demo-paypal-com-2026-11-11.csv",
    );
    expect(csvFileName("not a url", new Date("2026-11-11T10:00:00Z"))).toBe("checkoutpilot-findings-store-2026-11-11.csv");
  });
});

describe("owner summary", () => {
  it("is passed through, and labelled honestly", () => {
    expect(adaptScan({ owner_summary: { text: "Hi", generated_by: "ai" } }).owner_summary).toEqual({ text: "Hi", generated_by: "ai" });
    expect(adaptScan({ owner_summary: { text: "Hi", generated_by: "weird" } }).owner_summary?.generated_by).toBe("template");
    expect(adaptScan({}).owner_summary).toBeNull();
  });
});
