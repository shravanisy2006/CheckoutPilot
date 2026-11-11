import { describe, expect, it } from "vitest";
import { nextStep } from "@/components/app/Guide";

const base = { scan: "idle", fix: "idle", verify: "idle", issues: 0, selected: 0 };

describe("nextStep", () => {
  it("starts by asking for a store and offers the scan page", () => {
    const s = nextStep(base, "/proof", "live");
    expect(s.current).toBe("scan");
    expect(s.text).toMatch(/example store/i);
    expect(s.cta?.to).toBe("/audit");
  });

  it("no button for the page you are already on", () => {
    expect(nextStep(base, "/audit", "live").cta).toBeUndefined();
  });

  it("after a scan: choose fixes, with the issue count", () => {
    const s = nextStep({ ...base, scan: "success", issues: 4, selected: 3 }, "/audit", "live");
    expect(s.current).toBe("choose");
    expect(s.text).toContain("4 issues");
    expect(s.cta).toEqual({ label: "Choose fixes", to: "/recommendations" });
    expect(nextStep({ ...base, scan: "success", issues: 4, selected: 3 }, "/recommendations", "live").text).toContain(
      "3 selected",
    );
  });

  it("while busy there is no button, and live mode says how long", () => {
    const s = nextStep({ ...base, scan: "success", fix: "success", verify: "running" }, "/proof", "live");
    expect(s.busy).toBe(true);
    expect(s.cta).toBeUndefined();
    expect(s.text).toMatch(/1-2 minutes/);
  });

  it("fix ready: review it; on the Fix page: press Verify", () => {
    const st = { ...base, scan: "success", fix: "success" };
    expect(nextStep(st, "/recommendations", "live").cta?.to).toBe("/fix");
    expect(nextStep(st, "/fix", "live").text).toMatch(/Verify in Sandbox/);
  });

  it("finished: passed or failed is said honestly", () => {
    const done = { ...base, scan: "success", fix: "success", verify: "success" };
    expect(nextStep({ ...done, passed: true }, "/proof", "live").text).toMatch(/took a Sandbox payment/);
    expect(nextStep({ ...done, passed: true }, "/proof", "live").text).toMatch(/before\/after/);
    expect(nextStep({ ...done, passed: false }, "/proof", "live").text).toMatch(/did not pass/);
    expect(nextStep({ ...done, passed: true }, "/proof", "live").cta?.to).toBe("/audit");
  });
});

describe("real stores", () => {
  it("only our example stores count as fixable", async () => {
    const { isExampleStore } = await import("@/components/app/Guide");
    expect(isExampleStore("http://localhost:8101")).toBe(true);
    expect(isExampleStore("http://127.0.0.1:8102/")).toBe(true);
    expect(isExampleStore("https://demo.paypal.com/us/demo/home")).toBe(false);
    expect(isExampleStore("http://localhost:3000")).toBe(false);
    expect(isExampleStore("")).toBe(false);
  });

  it("after a real-store scan, explains Fix needs the code and points to the example store", () => {
    const s = nextStep({ ...base, scan: "success", issues: 3, realStore: true }, "/audit", "live");
    expect(s.text).toMatch(/needs the store's code/);
    expect(s.cta).toEqual({ label: "See recommendations", to: "/recommendations" });
    // On the recommendations page the note there carries the "Scan the example store" button.
    expect(nextStep({ ...base, scan: "success", issues: 3, realStore: true }, "/recommendations", "live").cta).toBeUndefined();
  });
});
