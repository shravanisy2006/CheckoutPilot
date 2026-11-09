import { describe, expect, it } from "vitest";
import { buildIssueRows } from "@/components/app/IssuesGrid";
import { demoScan } from "@/lib/checkout/demo";

describe("buildIssueRows", () => {
  it("joins every real demo issue with its recommendation", () => {
    const rows = buildIssueRows(demoScan());
    expect(rows).toHaveLength(4);
    const sdk = rows.find((r) => r.title.includes("SDK"));
    expect(sdk).toMatchObject({ severity: "high", impact: 100, foundBy: "rule check", fixable: true, rank: 1 });
    expect(sdk?.source).toContain("PayPal");
    expect(rows.every((r) => ["high", "medium", "low"].includes(r.severity))).toBe(true);
  });

  it("copes with a scan that has no recommendations", () => {
    const scan = { ...demoScan(), recommendations: [] };
    const rows = buildIssueRows(scan);
    expect(rows[0]?.impact).toBeNull();
    expect(rows[0]?.rank).toBe(1);
  });
});
