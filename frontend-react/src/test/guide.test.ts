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
    expect(nextStep({ ...done, passed: false }, "/proof", "live").text).toMatch(/did not pass/);
    expect(nextStep({ ...done, passed: true }, "/proof", "live").cta?.to).toBe("/audit");
  });
});
