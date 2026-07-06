import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { PageBody, PageHeader, EmptyState } from "@/components/PageChrome";
import { Shield } from "lucide-react";
import { toast } from "sonner";

function relTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function AuditLogPage() {
  const { hasPermission } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");

  const canRead = hasPermission("audit.read");

  const load = async () => {
    try {
      const r = await api.get("/audit-logs", { params: { limit: 100 } });
      setItems(r.data.items);
      setTotal(r.data.total);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canRead) load();
    else setLoading(false);
  }, [canRead]);

  const filtered = q
    ? items.filter(
        (i) =>
          i.action?.includes(q.toLowerCase()) ||
          i.actor_email?.includes(q.toLowerCase()) ||
          i.target_type?.includes(q.toLowerCase()),
      )
    : items;

  if (!canRead) {
    return (
      <>
        <PageHeader
          title="Activity"
          subtitle="Every important action, timestamped."
          breadcrumbs={[{ label: "Settings" }, { label: "Activity" }]}
        />
        <PageBody>
          <EmptyState
            icon={Shield}
            title="Restricted"
            description="Activity is available to admins and owners only."
          />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Activity"
        subtitle={`${total} event${total === 1 ? "" : "s"} recorded.`}
        breadcrumbs={[{ label: "Settings" }, { label: "Activity" }]}
        actions={
          <Input
            placeholder="Filter…"
            className="w-[220px] h-9"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="audit-filter"
          />
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Shield}
            title={q ? "No matching events" : "No events yet"}
            description={q ? "Try a different filter." : "Actions across your workspace will appear here."}
          />
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[140px]">When</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Target</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((row) => (
                  <TableRow key={row.id} data-testid={`audit-row-${row.action}`}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {relTime(row.ts)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="text-sm font-medium">
                          {row.actor_name || "—"}
                        </span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          {row.actor_email || row.actor_id?.slice(0, 8) || "system"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="font-mono text-[10px]">
                        {row.action}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {row.target_type && (
                        <span className="font-mono">
                          {row.target_type}
                          {row.target_id ? `:${row.target_id.slice(0, 8)}` : ""}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </PageBody>
    </>
  );
}
