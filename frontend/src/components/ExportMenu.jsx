import { useState } from "react";
import { Download, ChevronDown, FileText, FileSpreadsheet } from "lucide-react";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { API_BASE, tokenStore } from "@/lib/api";
import { toast } from "sonner";

/**
 * ExportMenu — split button on the records list header.
 * Streams the file via `<a download>` after building an authed URL.
 * Requires a valid access_token in tokenStore.
 */
export function ExportMenu({ entityTypeId, currentState, selectedIds, disabled }) {
  const [busy, setBusy] = useState(false);

  const doExport = async (format, opts = {}) => {
    setBusy(true);
    try {
      let url, method = "GET", body = null;
      if (opts.selected && selectedIds?.length) {
        // POST bulk endpoint
        url = `${API_BASE}/entity-types/${entityTypeId}/records/export-bulk`;
        method = "POST";
        body = JSON.stringify({
          record_ids: selectedIds,
          format,
          include_metadata: true,
        });
      } else {
        const params = new URLSearchParams({ format });
        if (currentState?.q) params.set("q", currentState.q);
        if (currentState?.category_id) params.set("category_id", currentState.category_id);
        if (currentState?.tag_ids?.length) params.set("tag_ids", currentState.tag_ids.join(","));
        if (opts.columns?.length) params.set("columns", opts.columns.join(","));
        url = `${API_BASE}/entity-types/${entityTypeId}/records/export?${params.toString()}`;
      }
      toast.info("Preparing your export…");
      const resp = await fetch(url, {
        method,
        headers: {
          "Authorization": `Bearer ${tokenStore.access}`,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body,
      });
      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(txt || `Export failed (${resp.status})`);
      }
      const cd = resp.headers.get("content-disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      const filename = m?.[1] || `export.${format}`;
      const blob = await resp.blob();
      const a = document.createElement("a");
      const objectUrl = URL.createObjectURL(blob);
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      toast.success("Export downloaded");
    } catch (e) {
      toast.error(e.message || "Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="inline-flex" data-testid="export-menu">
      <Button
        variant="outline"
        onClick={() => doExport("csv")}
        disabled={disabled || busy}
        className="rounded-r-none border-r-0"
        data-testid="export-default-btn"
      >
        <Download className="w-4 h-4 mr-1.5" />
        Export
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className="rounded-l-none px-2"
            disabled={disabled || busy}
            data-testid="export-menu-trigger"
          >
            <ChevronDown className="w-4 h-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="text-xs">Format</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => doExport("csv")} data-testid="export-csv">
            <FileText className="w-4 h-4 mr-2" /> Export CSV
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => doExport("xlsx")} data-testid="export-xlsx">
            <FileSpreadsheet className="w-4 h-4 mr-2" /> Export Excel (.xlsx)
          </DropdownMenuItem>
          {selectedIds?.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs">
                Selection ({selectedIds.length})
              </DropdownMenuLabel>
              <DropdownMenuItem
                onClick={() => doExport("csv", { selected: true })}
                data-testid="export-selected-csv"
              >
                <FileText className="w-4 h-4 mr-2" /> Selected as CSV
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => doExport("xlsx", { selected: true })}
                data-testid="export-selected-xlsx"
              >
                <FileSpreadsheet className="w-4 h-4 mr-2" /> Selected as Excel
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
