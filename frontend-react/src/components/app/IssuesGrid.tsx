/**
 * Sortable, filterable table of every finding, built with AG Grid Community.
 *
 * One row per issue, joined with its recommendation: rank, severity, impact
 * score (0-100 from the impact ranker), how it was found (rule check / AI
 * vision), whether the code agent can fix it, and the cited source behind the
 * impact score. Used on the Audit page next to the finding cards.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Download } from "lucide-react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
} from "ag-grid-community";
import type { ScanResult, Severity } from "@/lib/checkout/types";
import { SeverityBadge } from "./ui";

ModuleRegistry.registerModules([AllCommunityModule]);

export type IssueRow = {
  rank: number;
  title: string;
  severity: Severity;
  severityOrder: number;
  impact: number | null;
  foundBy: string;
  fixable: boolean;
  surface: string;
  source: string;
  recommendation: string;
};

const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

// Readable line spacing for cells whose text wraps onto several lines.
const WRAPPED = { lineHeight: "1.45", paddingTop: "10px", paddingBottom: "10px" };

/** Join issues with their recommendations into table rows (pure; tested). */
export function buildIssueRows(scan: ScanResult): IssueRow[] {
  const recByIssue = new Map(scan.recommendations.map((r) => [r.issue_id, r]));
  return scan.issues.map((issue, index) => {
    const rec = recByIssue.get(issue.id);
    const foundBy = issue.evidence.find((e) => e.startsWith("Found by:"))?.replace("Found by:", "").trim() ?? "";
    return {
      rank: rec?.priority ?? index + 1,
      title: issue.title,
      severity: issue.severity,
      severityOrder: SEVERITY_ORDER[issue.severity] ?? 3,
      impact: typeof rec?.impact_score === "number" ? rec.impact_score : null,
      foundBy,
      fixable: Boolean(rec?.fixable_by_agent ?? issue.evidence.includes("Auto-fixable")),
      surface: issue.surface ?? "both",
      source: rec?.impact_source ?? "",
      recommendation: rec?.title ?? "",
    };
  });
}

// Match the dashboard's own colours and type (CSS variables from the app theme).
const gridTheme = themeQuartz.withParams({
  accentColor: "var(--primary)",
  backgroundColor: "var(--card)",
  foregroundColor: "var(--foreground)",
  borderColor: "var(--border)",
  headerBackgroundColor: "var(--muted)",
  headerTextColor: "var(--muted-foreground)",
  rowHoverColor: "var(--accent)",
  fontFamily: "inherit",
  fontSize: 13,
  headerFontWeight: 600,
  wrapperBorderRadius: 10,
  spacing: 7,
});

function SeverityCell(p: ICellRendererParams<IssueRow>) {
  return p.data ? <SeverityBadge severity={p.data.severity} /> : null;
}

function ImpactCell(p: ICellRendererParams<IssueRow>) {
  if (!p.data || p.data.impact === null) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="inline-flex items-center gap-2 tabular-nums">
      <span className="inline-block h-1.5 w-16 overflow-hidden rounded-full bg-muted align-middle">
        <span className="block h-full rounded-full bg-primary" style={{ width: `${p.data.impact}%` }} />
      </span>
      {p.data.impact}
    </span>
  );
}

/** "checkoutpilot-findings-demo-paypal-com-2026-11-11.csv" */
export function csvFileName(storeUrl: string, date = new Date()): string {
  let host = "store";
  try {
    host = new URL(storeUrl).host.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  } catch {
    /* keep "store" */
  }
  return `checkoutpilot-findings-${host}-${date.toISOString().slice(0, 10)}.csv`;
}

export function IssuesGrid({ scan }: { scan: ScanResult }) {
  const gridRef = useRef<AgGridReact<IssueRow>>(null);
  // AG Grid needs the browser (window); render it only after the page has mounted.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const rows = useMemo(() => buildIssueRows(scan), [scan]);
  const columns = useMemo<ColDef<IssueRow>[]>(
    () => [
      { field: "rank", headerName: "Rank", width: 105, sort: "asc" },
      { field: "title", headerName: "Finding", flex: 2, minWidth: 200, wrapText: true, autoHeight: true, cellStyle: WRAPPED },
      {
        field: "severity",
        headerName: "Severity",
        width: 120,
        cellRenderer: SeverityCell,
        comparator: (_a, _b, nodeA, nodeB) => (nodeA.data?.severityOrder ?? 0) - (nodeB.data?.severityOrder ?? 0),
      },
      { field: "impact", headerName: "Impact", width: 140, cellRenderer: ImpactCell, filter: "agNumberColumnFilter" },
      { field: "foundBy", headerName: "Found by", width: 130, wrapText: true, autoHeight: true, cellStyle: WRAPPED },
      {
        field: "fixable",
        headerName: "Auto-fix",
        width: 105,
        cellDataType: "text",
        valueFormatter: (p) => (p.value ? "Yes" : "—"),
      },
      { field: "surface", headerName: "Where", width: 95 },
      { field: "source", headerName: "Impact source", flex: 1.6, minWidth: 180, wrapText: true, autoHeight: true, cellStyle: WRAPPED },
    ],
    [],
  );
  const defaultColDef = useMemo<ColDef>(() => ({ sortable: true, filter: true, resizable: true }), []);

  if (!mounted) {
    return <div className="h-40 animate-pulse rounded-lg border border-border bg-muted/40" />;
  }
  const exportCsv = () =>
    gridRef.current?.api.exportDataAsCsv({
      fileName: csvFileName(scan.store_url),
      // Readable values in the file, not the drawn badges/bars.
      processCellCallback: (p) => (p.column.getColId() === "fixable" ? (p.value ? "Yes" : "No") : p.value ?? ""),
    });

  return (
    <div className="w-full" data-testid="issues-grid">
      <div className="mb-2 flex justify-end">
        <button type="button" className="btn-outline h-8 px-3 text-xs" onClick={exportCsv}>
          <Download className="h-3.5 w-3.5" /> Download CSV
        </button>
      </div>
      <AgGridReact<IssueRow>
        ref={gridRef}
        theme={gridTheme}
        rowData={rows}
        columnDefs={columns}
        defaultColDef={defaultColDef}
        domLayout="autoHeight"
        suppressCellFocus
        overlayNoRowsTemplate="No issues found"
      />
    </div>
  );
}
