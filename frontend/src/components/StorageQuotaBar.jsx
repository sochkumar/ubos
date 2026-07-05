import { useEffect, useState } from "react";
import { api } from "@/lib/api";

function fmt(bytes) {
  if (bytes === 0 || bytes == null) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const v = bytes / Math.pow(1024, i);
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

/** Reusable — pass `data` to inject externally, or let it fetch itself. */
export function StorageQuotaBar({ data, compact = false }) {
  const [status, setStatus] = useState(data || null);

  useEffect(() => {
    if (data) { setStatus(data); return; }
    api.get("/media/storage").then((r) => setStatus(r.data)).catch(() => {});
  }, [data]);

  if (!status) return null;
  const pct = Math.min(100, Math.max(0, status.percent || 0));
  const state =
    pct >= 95 ? { bar: "bg-destructive", txt: "text-destructive" }
    : pct >= 80 ? { bar: "bg-amber-500", txt: "text-amber-700" }
    : { bar: "bg-primary", txt: "text-primary" };

  return (
    <div className={compact ? "w-56" : "w-full max-w-md"} data-testid="storage-quota-bar">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] font-mono uppercase text-muted-foreground">Storage</span>
        <span className={`text-xs font-medium ${state.txt}`}>
          {fmt(status.used_bytes)} <span className="text-muted-foreground">of {fmt(status.quota_bytes)}</span>
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full ${state.bar} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function humanBytes(b) { return fmt(b); }
