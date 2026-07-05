import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity, ArrowRight, Boxes, Clock, Database, FolderKanban,
  HardDrive, Plus, RefreshCw, Trash2, User as UserIcon, Share2, Tag as TagIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

function humanBytes(b) {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(b) / Math.log(1024));
  return `${(b / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${u[i]}`;
}

function relTime(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }); } catch { return ""; }
}

const ACTION_VERBS = {
  "record.created": "created record",
  "record.updated": "updated record",
  "record.deleted": "deleted record",
  "records.bulk_deleted": "bulk-deleted records",
  "records.bulk_updated": "bulk-updated records",
  "share.created": "created a share link",
  "share.updated": "updated a share link",
  "share.revoked": "revoked a share link",
  "share.deleted": "deleted a share link",
  "entity_type.created": "added entity type",
  "entity_type.updated": "updated entity type",
  "entity_type.deleted": "deleted entity type",
  "field.created": "added a field",
  "field.updated": "updated a field",
  "field.deleted": "deleted a field",
  "media.uploaded": "uploaded a file",
  "media.deleted": "deleted a file",
  "labels.printed": "printed labels",
  "labels.printed_view": "printed view labels",
  "member.role_changed": "changed a member role",
  "org.updated": "updated the workspace",
  "auth.login": "signed in",
};

const FAMILY_COLORS = {
  images: "#0d9488",
  documents: "#4f46e5",
  videos: "#dc2626",
  audio: "#d97706",
  other: "#71717a",
};

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();

  const load = async (bust = false) => {
    setRefreshing(bust);
    try {
      if (bust) await api.post("/dashboard/refresh").catch(() => {});
      const r = await api.get("/dashboard/summary");
      setData(r.data);
    } catch { /* toast handled */ }
    finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-4 max-w-7xl mx-auto" data-testid="dashboard-loading">
        <div className="h-8 bg-muted rounded w-48 animate-pulse" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-64 bg-muted rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5" data-testid="dashboard-page">
      <header className="flex items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            A quick pulse of your workspace.
          </p>
        </div>
        <Button
          variant="outline" size="sm" className="ml-auto"
          onClick={() => load(true)}
          disabled={refreshing}
          data-testid="dashboard-refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RecentRecordsWidget records={data.recent_records} onOpen={(id) => navigate(`/records/${id}`)} />
        <ActivityWidget activity={data.activity} />
        <StorageWidget storage={data.storage} onOpen={() => navigate("/media")} />
        <EntityTypesWidget entityTypes={data.entity_types} onOpen={(id) => navigate(`/entity-types/${id}/records`)} onNew={() => navigate("/entity-types")} />
      </div>
    </div>
  );
}

/* ────── Widget shells ────── */
function WidgetCard({ title, icon: Icon, action, children, testId }) {
  return (
    <section
      className="rounded-lg border border-border bg-white flex flex-col min-h-[280px]"
      data-testid={testId}
    >
      <header className="px-4 py-3 border-b border-border flex items-center gap-2">
        <Icon className="w-4 h-4 text-primary" />
        <div className="text-sm font-medium">{title}</div>
        {action && <div className="ml-auto">{action}</div>}
      </header>
      <div className="flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}

/* ────── Widget 1: Recent Records ────── */
function RecentRecordsWidget({ records, onOpen }) {
  return (
    <WidgetCard
      title="Recent records"
      icon={Clock}
      testId="widget-recent-records"
      action={
        records.length > 0 && (
          <Link to="/entity-types" className="text-xs text-primary hover:underline">View all →</Link>
        )
      }
    >
      {records.length === 0 ? (
        <EmptyState title="No records yet" cta="Create your first record" to="/entity-types" />
      ) : (
        <ul className="divide-y divide-border">
          {records.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => onOpen(r.id)}
                className="w-full text-left px-4 py-2.5 hover:bg-muted/30 flex items-center gap-3"
                data-testid={`recent-record-${r.id}`}
              >
                <div
                  className="w-8 h-8 rounded flex items-center justify-center shrink-0"
                  style={{ backgroundColor: (r.entity_type.color || "#0d9488") + "1a", color: r.entity_type.color || "#0d9488" }}
                >
                  <Database className="w-3.5 h-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{r.title}</div>
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <span className="font-mono">{r.record_number}</span>
                    <span>·</span>
                    <span>{r.entity_type.name}</span>
                    <span>·</span>
                    <span>{relTime(r.updated_at)}</span>
                  </div>
                </div>
                {r.tags?.length > 0 && (
                  <div className="hidden md:flex items-center gap-1 shrink-0">
                    {r.tags.slice(0, 2).map((t) => (
                      <span
                        key={t.id}
                        className="text-[9px] px-1.5 py-0.5 rounded-full font-medium"
                        style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
                      >
                        {t.name}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  );
}

/* ────── Widget 2: Activity ────── */
function ActivityWidget({ activity }) {
  return (
    <WidgetCard
      title="Activity"
      icon={Activity}
      testId="widget-activity"
      action={
        activity.length > 0 && (
          <Link to="/settings/audit-log" className="text-xs text-primary hover:underline">View all →</Link>
        )
      }
    >
      {activity.length === 0 ? (
        <EmptyState title="No activity yet" hint="Once your team starts using the workspace, events will appear here." />
      ) : (
        <ul className="divide-y divide-border">
          {activity.map((a) => (
            <li key={a.id} className="px-4 py-2.5 flex items-start gap-3" data-testid={`activity-${a.id}`}>
              <div className="w-7 h-7 rounded-full bg-primary/10 text-primary text-[10px] font-semibold flex items-center justify-center overflow-hidden shrink-0">
                {a.actor.avatar_url ? (
                  <img src={a.actor.avatar_url} alt="" className="w-full h-full object-cover" />
                ) : (
                  (a.actor.name || "?").slice(0, 2).toUpperCase()
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm">
                  <b>{a.actor.name}</b>{" "}
                  <span className="text-muted-foreground">
                    {ACTION_VERBS[a.action] || a.action.replace(/[._]/g, " ")}
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-1.5">
                  <span>{relTime(a.ts)}</span>
                  {a.target_type && (
                    <>
                      <span>·</span>
                      <span className="font-mono">{a.target_type}</span>
                    </>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  );
}

/* ────── Widget 3: Storage ────── */
function StorageWidget({ storage, onOpen }) {
  const pct = Math.min(100, storage.pct || 0);
  const nearFull = pct > 85;
  const families = Object.entries(storage.by_mime_family || {})
    .sort((a, b) => b[1].size - a[1].size);

  return (
    <WidgetCard
      title="Storage"
      icon={HardDrive}
      testId="widget-storage"
      action={
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onOpen} data-testid="storage-manage-btn">
          Manage →
        </Button>
      }
    >
      <div className="p-4 space-y-4">
        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <div className="text-2xl font-semibold tracking-tight" data-testid="storage-used">
              {humanBytes(storage.used_bytes)}
            </div>
            <div className="text-xs text-muted-foreground">
              of {humanBytes(storage.quota_bytes)}
            </div>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full transition-all rounded-full ${nearFull ? "bg-amber-500" : "bg-primary"}`}
              style={{ width: `${pct}%` }}
              data-testid="storage-bar"
            />
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">
            {pct.toFixed(1)}% used
          </div>
        </div>

        {families.length > 0 ? (
          <div className="space-y-1.5">
            <div className="text-[10px] font-mono uppercase text-muted-foreground">By type</div>
            {families.map(([fam, val]) => {
              const famPct = storage.used_bytes > 0 ? (val.size / storage.used_bytes) * 100 : 0;
              return (
                <div key={fam} className="text-xs" data-testid={`storage-family-${fam}`}>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="capitalize">{fam}</span>
                    <span className="text-muted-foreground font-mono">
                      {humanBytes(val.size)} · {val.count}
                    </span>
                  </div>
                  <div className="h-1 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${famPct}%`, backgroundColor: FAMILY_COLORS[fam] || FAMILY_COLORS.other }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">No files uploaded yet.</div>
        )}
      </div>
    </WidgetCard>
  );
}

/* ────── Widget 4: Entity Types Overview ────── */
function EntityTypesWidget({ entityTypes, onOpen, onNew }) {
  return (
    <WidgetCard
      title="Entity types"
      icon={Boxes}
      testId="widget-entity-types"
      action={
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onNew} data-testid="ets-new-btn">
          <Plus className="w-3 h-3 mr-1" /> New
        </Button>
      }
    >
      {entityTypes.length === 0 ? (
        <EmptyState title="No entity types yet" cta="Create your first entity type" to="/entity-types" />
      ) : (
        <div className="grid grid-cols-2 gap-2 p-3" data-testid="ets-grid">
          {entityTypes.map((e) => (
            <button
              key={e.id}
              onClick={() => onOpen(e.id)}
              className="text-left rounded border border-border bg-white p-3 hover:border-primary/60 transition-colors"
              data-testid={`et-tile-${e.key}`}
            >
              <div className="flex items-start gap-2 mb-1">
                <div
                  className="w-6 h-6 rounded flex items-center justify-center shrink-0"
                  style={{ backgroundColor: (e.color || "#0d9488") + "1a", color: e.color || "#0d9488" }}
                >
                  <Boxes className="w-3 h-3" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{e.name_plural || e.name_singular}</div>
                  <div className="text-[11px] text-muted-foreground font-mono truncate">{e.key}</div>
                </div>
              </div>
              <div className="text-[11px] text-muted-foreground pl-8">
                <b className="text-foreground">{e.record_count}</b> record{e.record_count === 1 ? "" : "s"}
              </div>
            </button>
          ))}
        </div>
      )}
    </WidgetCard>
  );
}

function EmptyState({ title, hint, cta, to }) {
  return (
    <div className="h-full flex flex-col items-center justify-center p-8 text-center gap-2">
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="text-xs text-muted-foreground max-w-xs">{hint}</div>}
      {cta && to && (
        <Link to={to} className="mt-2 text-sm text-primary hover:underline inline-flex items-center gap-1">
          {cta} <ArrowRight className="w-3 h-3" />
        </Link>
      )}
    </div>
  );
}
