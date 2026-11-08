import { createFileRoute, Link } from "@tanstack/react-router";
import {
  CheckCircle2,
  Download,
  FileCode2,
  FlaskConical,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useCheckout } from "@/lib/checkout/store";
import {
  EmptyState,
  ErrorBlock,
  PageHeader,
  Panel,
  ProgressBlock,
  ScreenshotFrame,
  SimulatedBanner,
  VerificationPill,
} from "@/components/app/ui";
import { cn } from "@/lib/utils";
import type { FixResult, Mode, ScanResult, VerificationResult } from "@/lib/checkout/types";

export const Route = createFileRoute("/proof")({
  head: () => ({
    meta: [
      { title: "Proof — CheckoutPilot" },
      {
        name: "description",
        content: "PayPal Sandbox verification results and downloadable report.",
      },
      { property: "og:title", content: "Proof — CheckoutPilot" },
      {
        property: "og:description",
        content: "PayPal Sandbox verification results and downloadable report.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: ProofPage,
});

function ProofPage() {
  const { verify, fix, scan, startVerify, mode } = useCheckout();
  const v = verify.data;

  const generatePDF = async () => {
    try {
      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 20;
    const contentWidth = pageWidth - margin * 2;
    let y = 28;

    const sectionHeader = (text: string) => {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(13);
      doc.setTextColor(41, 37, 36);
      doc.text(text, margin, y);
      y += 10;
    };

    const bodyText = (
      text: string,
      opts: { size?: number; bold?: boolean; color?: number[]; indent?: number } = {},
    ) => {
      const { size = 10, bold = false, color = [100, 100, 100], indent = 0 } = opts;
      const lines = doc.splitTextToSize(text, contentWidth - indent);
      doc.setFont("helvetica", bold ? "bold" : "normal");
      doc.setFontSize(size);
      doc.setTextColor(...color);
      doc.text(lines, margin + indent, y);
      y += lines.length * 4.6 + 5;
    };

    const newPageIfNeeded = (neededHeight: number) => {
      if (y + neededHeight > pageHeight - 30) {
        doc.addPage();
        y = 28;
      }
    };

    // --- Header ---
    doc.setFont("helvetica", "bold");
    doc.setFontSize(26);
    doc.setTextColor(41, 37, 36);
    doc.text("CheckoutPilot", margin, y);
    y += 12;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(13);
    doc.setTextColor(100, 100, 100);
    doc.text("PayPal Checkout Optimization Report", margin, y);
    y += 16;

    // Demo Mode disclaimer
    if (mode === "demo") {
      doc.setFillColor(255, 243, 220);
      doc.roundedRect(margin, y, contentWidth, 12, 2, 2, "F");
      doc.setTextColor(200, 80, 40);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      doc.text(
        "DEMO MODE — recorded results from the CheckoutPilot demo store (no new scan).",
        margin + 6,
        y + 7,
      );
      y += 20;
    }

    newPageIfNeeded(40);

    // --- Scan Information ---
    sectionHeader("Scan Information");
    const storeUrl = scan.data?.store_url ?? "—";
    const healthScore = scan.data?.health_score ?? 0;
    const createdAt = scan.data?.created_at ?? "—";

    bodyText(`Store URL: ${storeUrl}`);
    bodyText(`Checkout Health Score: ${healthScore} / 100`);
    bodyText(`Scan Date: ${new Date(createdAt).toLocaleString()}`);
    bodyText(`Data Source: ${mode === "demo" ? "Demo Mode — sample data" : "Live backend"}`);
    y += 6;

    // Issue Summary
    const issues = scan.data?.issues ?? [];
    const issueCounts: Record<string, number> = { high: 0, medium: 0, low: 0 };
    issues.forEach((i) => {
      issueCounts[i.severity] = (issueCounts[i.severity] ?? 0) + 1;
    });

    bodyText(
      `Issues Found: ${issues.length} total (${issueCounts.high} high, ${issueCounts.medium} medium, ${issueCounts.low} low)`,
    );
    y += 4;

    // --- Recommendations ---
    const recommendations = scan.data?.recommendations ?? [];

    if (recommendations.length > 0) {
      newPageIfNeeded(40);
      sectionHeader("Recommendations");

      recommendations.forEach((r) => {
        newPageIfNeeded(30);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(11);
        doc.setTextColor(41, 37, 36);
        doc.text(`P${r.priority} · ${r.title}`, margin, y);
        y += 6;

        doc.setFont("helvetica", "normal");
        doc.setFontSize(9);
        doc.setTextColor(100, 100, 100);
        const descLines = doc.splitTextToSize(r.description, contentWidth - 10);
        doc.text(descLines, margin + 8, y);
        y += descLines.length * 4.6 + 3;

        doc.setFont("helvetica", "italic");
        doc.setFontSize(8.5);
        doc.setTextColor(140, 140, 140);
        const rationaleLines = doc.splitTextToSize(`Why: ${r.rationale}`, contentWidth - 10);
        doc.text(rationaleLines, margin + 8, y);
        y += rationaleLines.length * 4.2 + 6;

        if (typeof r.impact_score === "number") {
          doc.setFont("helvetica", "normal");
          doc.setFontSize(8.5);
          doc.setTextColor(90, 90, 90);
          const impactLines = doc.splitTextToSize(
            `Impact score: ${r.impact_score}/100. Source: ${r.impact_source ?? "n/a"}. Effect not measured for this store.`,
            contentWidth - 10,
          );
          doc.text(impactLines, margin + 8, y);
          y += impactLines.length * 4.2 + 2;
        }
      });
    }

    // --- Fix Information ---
    if (fix?.data) {
      newPageIfNeeded(40);
      sectionHeader("Proposed Fix");

      const fixData = fix.data;
      bodyText(`Fix ID: ${fixData.fix_id}`, { size: 10 });
      bodyText(`Status: ${fixData.confirmed ? "Applied" : "Proposed — not yet applied"}`, {
        size: 10,
      });
      bodyText(`Summary: ${fixData.summary ?? `${fixData.files.length} file(s) changed`}`, {
        size: 10,
      });
      if (fixData.pull_request_url) {
        bodyText(`Pull Request: ${fixData.pull_request_url}`, { size: 10 });
      }
      y += 4;

      // Changed files
      sectionHeader("Changed Files");
      fixData.files.forEach((f, idx) => {
        newPageIfNeeded(50);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(10);
        doc.setTextColor(41, 37, 36);
        doc.text(`${idx + 1}. ${f.path}`, margin, y);
        y += 6;

        doc.setFont("helvetica", "normal");
        doc.setFontSize(8);
        doc.setTextColor(100, 100, 100);
        const beforeLines = doc.splitTextToSize(f.before, contentWidth - 20);
        doc.text(beforeLines, margin + 8, y);
        y += beforeLines.length * 4.2 + 3;

        doc.setFont("helvetica", "bold");
        doc.setTextColor(34, 139, 34);
        doc.text("After:", margin + 8, y);
        y += 5;

        doc.setFont("helvetica", "normal");
        doc.setTextColor(41, 37, 36);
        const afterLines = doc.splitTextToSize(f.after, contentWidth - 20);
        doc.text(afterLines, margin + 8, y);
        y += afterLines.length * 4.2 + 8;
      });
    }

    // --- Verification Information ---
    if (v) {
      newPageIfNeeded(40);
      sectionHeader("Verification Results");

      bodyText(`Result: ${v.passed ? "Pass" : "Fail"}`, {
        size: 12,
        bold: true,
        color: v.passed ? [34, 139, 34] : [220, 38, 38],
      });
      bodyText(`Status: ${v.status}`);
      bodyText(`Environment: PayPal ${v.environment}`);
      bodyText(`Verification ID: ${v.verification_id}`);
      bodyText(`Fix ID: ${fix?.data?.fix_id ?? "—"}`);
      if (v.order_id) {
        bodyText(`Order ID: ${v.order_id}`);
      } else if (v.simulated) {
        bodyText(`Order ID: None (simulated)`);
      }
      y += 4;

      // Evidence
      if (v.evidence.length > 0) {
        sectionHeader("Evidence");
        v.evidence.forEach((e) => {
          newPageIfNeeded(20);
          doc.setFont("helvetica", "normal");
          doc.setFontSize(9);
          doc.setTextColor(41, 37, 36);
          const lines = doc.splitTextToSize(`• ${e}`, contentWidth - 20);
          doc.text(lines, margin + 8, y);
          y += lines.length * 4.6 + 3;
        });
      }

      if (v.simulated) {
        y += 6;
        doc.setFillColor(255, 243, 220);
        doc.roundedRect(margin, y, contentWidth, 12, 2, 2, "F");
        doc.setTextColor(200, 80, 40);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(9);
        doc.text(
          "Simulated — sample data. No PayPal transaction occurred, real or sandbox.",
          margin + 6,
          y + 7,
        );
        y += 20;
      }
    }

    // --- Footer ---
    y += 10;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(150, 150, 150);
    const footerText = `Generated by CheckoutPilot on ${new Date().toLocaleString()}. This report documents checkout optimization findings and is not a financial record.`;
    const footerLines = doc.splitTextToSize(footerText, contentWidth);
    doc.text(footerLines, margin, y);

    const fileName = `checkoutpilot-report-${mode}-${Date.now()}.pdf`;
    doc.save(fileName);
    } catch (err) {
      console.error("PDF generation failed", err);
    }
  };

  const canReport = !!scan.data;

  return (
    <div className="space-y-6">
      <PageHeader
        step="Step 4 · Prove"
        title="Sandbox verification"
        description="Evidence that the updated checkout works in the PayPal Sandbox."
        action={
          <div className="flex gap-3">
            <button onClick={generatePDF} disabled={!canReport} className="btn-primary">
              <Download className="h-4 w-4" /> Download PDF Report
            </button>
          </div>
        }
      />

      {verify.phase === "idle" && (
        <EmptyState
          icon={ShieldCheck}
          title="Not verified yet"
          description={
            fix.data
              ? "Run a Sandbox verification for the generated fix."
              : "Generate a fix before verifying."
          }
          action={
            fix.data ? (
              <button onClick={startVerify} className="btn-primary">
                <ShieldCheck className="h-4 w-4" /> Run verification
              </button>
            ) : (
              <Link to="/fix" className="btn-primary">
                <FileCode2 className="h-4 w-4" /> Go to fix
              </Link>
            )
          }
        />
      )}
      {verify.phase === "running" && (
        <ProgressBlock
          label="Verifying in PayPal Sandbox"
          stage={verify.stage}
          progress={verify.progress}
        />
      )}
      {verify.phase === "error" && (
        <ErrorBlock
          title="Verification failed to run"
          message={verify.error}
          onRetry={startVerify}
        />
      )}

      {v && verify.phase === "success" && (
        <div className="space-y-6 animate-in fade-in duration-500">
          {v.simulated && <SimulatedBanner />}
          <VerificationPill passed={v.passed} status={v.status} />

          <div className="grid gap-4 md:grid-cols-3">
            <Panel className="p-5 md:col-span-1">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Result
                  </p>
                  <p
                    className={cn(
                      "font-display text-3xl font-light tabular-nums",
                      v.passed ? "text-success" : "text-destructive",
                    )}
                  >
                    {v.passed ? "Pass" : "Fail"}
                  </p>
                </div>
                <div
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-xl",
                    v.passed ? "bg-success/10" : "bg-destructive/10",
                  )}
                >
                  {v.passed ? (
                    <CheckCircle2 className="h-5 w-5 text-success" />
                  ) : (
                    <XCircle className="h-5 w-5 text-destructive" />
                  )}
                </div>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">{v.status}</p>
            </Panel>
            <Panel className="p-5 md:col-span-2">
              <div className="grid gap-3 md:grid-cols-4">
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Environment
                  </p>
                  <p className="text-sm text-foreground">PayPal {v.environment}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Order ID
                  </p>
                  <p className="text-sm font-mono text-foreground truncate">
                    {v.order_id ?? (v.simulated ? "None (simulated)" : "Not returned")}
                  </p>
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Verification ID
                  </p>
                  <p className="text-sm font-mono text-foreground truncate">{v.verification_id}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Fix ID
                  </p>
                  <p className="text-sm font-mono text-foreground truncate">
                    {fix.data?.fix_id ?? "—"}
                  </p>
                </div>
              </div>
            </Panel>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
            <Panel className="p-5">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Evidence
              </p>
              <ul className="space-y-2">
                {v.evidence.map((e) => (
                  <li key={e} className="flex gap-2.5 text-sm text-foreground/90">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    {e}
                  </li>
                ))}
              </ul>
            </Panel>
            <Panel className="p-5">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Before / after checkout
              </p>
              <div className="grid grid-cols-2 gap-3">
                <ScreenshotFrame variant="desktop" label="Before" src={v.screenshots?.before} />
                <ScreenshotFrame variant="desktop" label="After" src={v.screenshots?.after} />
              </div>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
