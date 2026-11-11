import { describe, expect, it } from "vitest";
import { resolveApiBase } from "@/lib/checkout/api";

describe("resolveApiBase (hosted vs local backend)", () => {
  it("uses the page's own address for the hosted build", () => {
    expect(resolveApiBase("same-origin", "https://checkoutpilot.onrender.com")).toBe("https://checkoutpilot.onrender.com");
    expect(resolveApiBase(" same-origin ", "https://x.onrender.com/")).toBe("https://x.onrender.com");
  });

  it("keeps a full URL (local dev) and trims the trailing slash", () => {
    expect(resolveApiBase("http://localhost:8000/", "https://ignored")).toBe("http://localhost:8000");
  });

  it("is empty when not configured (Demo mode only)", () => {
    expect(resolveApiBase(undefined)).toBe("");
    expect(resolveApiBase("same-origin", undefined)).toBe("");
  });
});
