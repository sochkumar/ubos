import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity, ArrowRight, Boxes, Clock, Database, FolderKanban,
  HardDrive, Plus, RefreshCw, Trash2, User as UserIcon, Share2, Tag as TagIcon,
  GripVertical, MoreVertical, Settings2, Check, EyeOff, RotateCcw,
} from "lucide-react";
import {
  DndContext, PointerSensor, KeyboardSensor, useSensor, useSensors,
  closestCenter,
} from "@dnd-kit/core";
import {
  SortableContext, arrayMove, useSortable, rectSortingStrategy,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
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

const WIDGET_META = {
  recent_records: { title: "Recent records", icon: Clock },
  activity:       { title: "Activity",       icon: Activity },
  storage:        { title: "Storage",        icon: HardDrive },
  entity_types:   { title: "Entity types",   icon: Boxes },
};

const DEFAULT_LAYOUT = [
  { widget_key: "recent_records", visible: true, order: 0 },
  { widget_key: "activity",       visible: true, order: 1 },
  { widget_key: "storage",        visible: true, order: 2 },
  { widget_key: "entity_types",   visible: true, order: 3 },
];

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [layout, setLayout] = useState(DEFAULT_LAYOUT);
  const [customizing, setCustomizing] = useState(false);
  const navigate = useNavigate();

  // Guard so an in-flight PUT doesn't clobber user edits after remount.
  const layoutLoadedRef = useRef(false);
  const debouncedSaveRef = useRef(null);

  const load = async (bust = false) => {
    setRefreshing(bust);
    try {
      if (bust) await api.post("/dashboard/refresh").catch(() => {});
      const r = await api.get("/dashboard/summary");
      setData(r.data);
    } catch { /* toast handled globally */ }
    finally { setLoading(false); setRefreshing(false); }
  };

  const loadLayout = async () => {
    try {
      const r = await api.get("/dashboard/layout");
      setLayout(r.data.layout || DEFAULT_LAYOUT);
    } catch {
      setLayout(DEFAULT_LAYOUT);
    } finally {
      layoutLoadedRef.current = true;
    }
  };

  useEffect(() => { load(); loadLayout(); }, []);

  // Debounced save (500 ms) on layout change — skips the initial load.
  useEffect(() => {
    if (!layoutLoadedRef.current) return;
    if (debouncedSaveRef.current) clearTimeout(debouncedSaveRef.current);
    debouncedSaveRef.current = setTimeout(async () => {
      try {
        await api.put("/dashboard/layout", { layout });
      } catch (e) {
        toast.error("Couldn't save dashboard layout");
      }
    }, 500);
    return () => { if (debouncedSaveRef.current) clearTimeout(debouncedSaveRef.current); };
  }, [layout]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const visibleSlots = useMemo(
    () => layout.filter((s) => s.visible),
    [layout],
  );
  const hiddenSlots = useMemo(
    () => layout.filter((s) => !s.visible),
    [layout],
  );

  const onDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = visibleSlots.findIndex((s) => s.widget_key === active.id);
    const newIndex = visibleSlots.findIndex((s) => s.widget_key === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const reordered = arrayMove(visibleSlots, oldIndex, newIndex);
    // Rebuild the full layout: visible in new order (0..N-1) + hidden after.
    const rebuilt = [
      ...reordered.map((s, i) => ({ ...s, order: i })),
      ...hiddenSlots.map((s, i) => ({ ...s, order: reordered.length + i })),
    ];
    setLayout(rebuilt);
  };

  const hideWidget = (key) => {
    setLayout((prev) => {
      const next = prev.map((s) =>
        s.widget_key === key ? { ...s, visible: false } : s,
      );
      // Re-number so visible ones stay 0..N-1.
      const visible = next.filter((s) => s.visible);
      const hidden = next.filter((s) => !s.visible);
      return [
        ...visible.map((s, i) => ({ ...s, order: i })),
        ...hidden.map((s, i) => ({ ...s, order: visible.length + i })),
      ];
    });
  };

  const showWidget = (key) => {
    setLayout((prev) => {
      const next = prev.map((s) =>
        s.widget_key === key ? { ...s, visible: true } : s,
      );
      const visible = next.filter((s) => s.visible);
      const hidden = next.filter((s) => !s.visible);
      return [
        ...visible.map((s, i) => ({ ...s, order: i })),
        ...hidden.map((s, i) => ({ ...s, order: visible.length + i })),
      ];
    });
  };

  const resetLayout = async () => {
    try {
      const r = await api.post("/dashboard/layout/reset");
      setLayout(r.data.layout || DEFAULT_LAYOUT);
      toast.success("Dashboard layout reset");
    } catch {
      toast.error("Couldn't reset dashboard layout");
    }
  };

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

  const renderWidgetBody = (key) => {
    switch (key) {
      case "recent_records":
        return <RecentRecordsBody records={data.recent_records} onOpen={(id) => navigate(`/records/${id}`)} />;
      case "activity":
        return <ActivityBody activity={data.activity} />;
      case "storage":
        return <StorageBody storage={data.storage} onOpen={() => navigate("/media")} />;
      case "entity_types":
        return <EntityTypesBody entityTypes={data.entity_types} onOpen={(id) => navigate(`/entity-types/${id}/records`)} onNew={() => navigate("/entity-types")} />;
      default:
        return null;
    }
  };

  const widgetAction = (key) => {
    switch (key) {
      case "recent_records":
        return data.recent_records.length > 0 && (
          <Link to="/entity-types" className="text-xs text-primary hover:underline" data-testid="widget-recent-records-viewall">View all →</Link>
        );
      case "activity":
        return data.activity.length > 0 && (
          <Link to="/settings/audit-log" className="text-xs text-primary hover:underline" data-testid="widget-activity-viewall">View all →</Link>
        );
      case "storage":
        return (
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => navigate("/media")} data-testid="storage-manage-btn">
            Manage →
          </Button>
        );
      case "entity_types":
        return (
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => navigate("/entity-types")} data-testid="ets-new-btn">
            <Plus className="w-3 h-3 mr-1" /> New
          </Button>
        );
      default:
        return null;
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5" data-testid="dashboard-page">
      <header className="flex items-center gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            A quick pulse of your workspace.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {customizing && (
            <Button
              variant="ghost" size="sm"
              onClick={resetLayout}
              data-testid="dashboard-reset-layout"
              className="text-xs"
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              Reset
            </Button>
          )}
          <Button
            variant={customizing ? "default" : "outline"}
            size="sm"
            onClick={() => setCustomizing((v) => !v)}
            data-testid="dashboard-customize-toggle"
          >
            {customizing ? (
              <><Check className="w-3.5 h-3.5 mr-1.5" /> Done</>
            ) : (
              <><Settings2 className="w-3.5 h-3.5 mr-1.5" /> Customize</>
            )}
          </Button>
          <Button
            variant="outline" size="sm"
            onClick={() => load(true)}
            disabled={refreshing}
            data-testid="dashboard-refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={onDragEnd}
      >
        <SortableContext
          items={visibleSlots.map((s) => s.widget_key)}
          strategy={rectSortingStrategy}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="dashboard-grid">
            {visibleSlots.map((slot) => (
              <SortableWidget
                key={slot.widget_key}
                slot={slot}
                customizing={customizing}
                onHide={() => hideWidget(slot.widget_key)}
                action={widgetAction(slot.widget_key)}
              >
                {renderWidgetBody(slot.widget_key)}
              </SortableWidget>
            ))}
          </div>
        </SortableContext>
      </DndContext>

      {hiddenSlots.length > 0 && (
        <div className="pt-2" data-testid="dashboard-hidden-tray">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline" size="sm"
                data-testid="dashboard-add-widget-btn"
              >
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Add widget
                <Badge variant="secondary" className="ml-2 h-5 px-1.5 text-[10px]">
                  {hiddenSlots.length}
                </Badge>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64">
              <DropdownMenuLabel>Hidden widgets</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {hiddenSlots.map((slot) => {
                const meta = WIDGET_META[slot.widget_key];
                if (!meta) return null;
                const Icon = meta.icon;
                return (
                  <DropdownMenuItem
                    key={slot.widget_key}
                    onClick={() => showWidget(slot.widget_key)}
                    data-testid={`dashboard-restore-${slot.widget_key}`}
                    className="cursor-pointer"
                  >
                    <Icon className="w-3.5 h-3.5 mr-2 text-primary" />
                    {meta.title}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </div>
  );
}

/* ────── Sortable widget shell ────── */
function SortableWidget({ slot, customizing, onHide, action, children }) {
  const {
    attributes, listeners, setNodeRef, transform, transition, isDragging,
  } = useSortable({ id: slot.widget_key, disabled: !customizing });

  const meta = WIDGET_META[slot.widget_key];
  if (!meta) return null;
  const Icon = meta.icon;

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <section
      ref={setNodeRef}
      style={style}
      className={`rounded-lg border bg-white flex flex-col min-h-[280px] ${
        customizing ? "border-primary/30 ring-1 ring-primary/10" : "border-border"
      } ${isDragging ? "shadow-lg" : ""}`}
      data-testid={`widget-${slot.widget_key}`}
    >
      <header className="px-4 py-3 border-b border-border flex items-center gap-2">
        {customizing && (
          <button
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing p-1 -ml-1 rounded hover:bg-muted/60 text-muted-foreground"
            aria-label="Drag to reorder"
            data-testid={`widget-drag-${slot.widget_key}`}
          >
            <GripVertical className="w-4 h-4" />
          </button>
        )}
        <Icon className="w-4 h-4 text-primary" />
        <div className="text-sm font-medium">{meta.title}</div>
        <div className="ml-auto flex items-center gap-1">
          {!customizing && action}
          {customizing && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="p-1 rounded hover:bg-muted/60 text-muted-foreground"
                  aria-label="Widget options"
                  data-testid={`widget-menu-${slot.widget_key}`}
                >
                  <MoreVertical className="w-4 h-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem
                  onClick={onHide}
                  data-testid={`widget-hide-${slot.widget_key}`}
                  className="cursor-pointer"
                >
                  <EyeOff className="w-3.5 h-3.5 mr-2" />
                  Hide widget
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}

/* ────── Widget 1: Recent Records body ────── */
function RecentRecordsBody({ records, onOpen }) {
  if (records.length === 0) {
    return <EmptyState title="No records yet" cta="Create your first record" to="/entity-types" />;
  }
  return (
    <ul className="divide-y divide-border" data-testid="widget-recent-records-list">
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
              <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 flex-wrap">
                <span className="font-mono">{r.record_number}</span>
                <span>·</span>
                <span>{r.entity_type.name}</span>
                <span>·</span>
                <span>{relTime(r.updated_at)}</span>
                {r.actor?.name && (
                  <>
                    <span>·</span>
                    <span className="inline-flex items-center gap-1">
                      <UserIcon className="w-2.5 h-2.5" />
                      <span data-testid={`recent-actor-${r.id}`}>{r.actor.name}</span>
                    </span>
                  </>
                )}
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
  );
}

/* ────── Widget 2: Activity body ────── */
function ActivityBody({ activity }) {
  if (activity.length === 0) {
    return <EmptyState title="No activity yet" hint="Once your team starts using the workspace, events will appear here." />;
  }
  return (
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
  );
}

/* ────── Widget 3: Storage body ────── */
function StorageBody({ storage }) {
  const pct = Math.min(100, storage.pct || 0);
  const nearFull = pct > 85;
  const families = Object.entries(storage.by_mime_family || {})
    .sort((a, b) => b[1].size - a[1].size);

  return (
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
  );
}

/* ────── Widget 4: Entity types body ────── */
function EntityTypesBody({ entityTypes, onOpen, onNew }) {
  if (entityTypes.length === 0) {
    return <EmptyState title="No entity types yet" cta="Create your first entity type" to="/entity-types" />;
  }
  return (
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
              <div className="text-sm font-medium truncate">{e.name || e.name_plural || e.name_singular}</div>
              <div className="text-[11px] text-muted-foreground font-mono truncate">{e.key}</div>
            </div>
          </div>
          <div className="text-[11px] text-muted-foreground pl-8">
            <b className="text-foreground">{e.record_count}</b> record{e.record_count === 1 ? "" : "s"}
          </div>
        </button>
      ))}
    </div>
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
