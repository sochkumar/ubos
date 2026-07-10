/**
 * Phase 8 — BrowsePage: cross-collection "All Items" feed.
 *
 * Single page that queries GET /api/records/browse and renders results in
 * the user's chosen layout (table / gallery / grid / card / list).
 * Layouts are adaptive: they pull per-collection field_definitions from the
 * browse response and pick the first 3–5 "important" fields to render.
 *
 * Save-as-view is delegated to a lightweight BrowseViewsBar (below) since
 * the existing ViewsBar is tied to a specific entity_type_id.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Boxes, Compass, X, ChevronDown, ArrowUpDown, Loader2,
  Table2, LayoutGrid, Rows3, List as ListIcon, Save, Bookmark,
  Search as SearchIcon, RefreshCw, FolderTree, Tag as TagIcon,
} from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger, DropdownMenuCheckboxItem,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { useTerminology } from "@/lib/terminology";
import { useTabTitle } from "@/lib/tabs";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { formatCellValue } from "@/components/RecordLayouts";

const LAYOUTS = [
  { key: "table",   label: "Table",   icon: Table2 },
  { key: "gallery", label: "Gallery", icon: LayoutGrid },
  { key: "grid",    label: "Grid",    icon: Boxes },
  { key: "card",    label: "Card",    icon: Rows3 },
  { key: "list",    label: "List",    icon: ListIcon },
];

const SORTS = [
  { key: "updated_at:desc", label: "Recently updated" },
  { key: "updated_at:asc",  label: "Least recently updated" },
  { key: "created_at:desc", label: "Newest first" },
  { key: "created_at:asc",  label: "Oldest first" },
  { key: "title:asc",       label: "Title A→Z" },
  { key: "title:desc",      label: "Title Z→A" },
];

/** Given a list of field definitions, pick the 3–5 most "important" fields to
 * render on adaptive cards/lists. Priority:
 *   1. First image field (rendered separately as hero)
 *   2. Required fields, ordered by `order`
 *   3. Remaining fields, ordered by `order`
 * Returns { image, columns } — image is a FieldDef or null.
 */
function pickAdaptiveFields(defs, max = 4) {
  if (!defs || !defs.length) return { image: null, columns: [] };
  const image = defs.find((d) => d.type === "image") || null;
  const nonImg = defs.filter((d) => d.type !== "image" && d.type !== "file");
  const sorted = nonImg.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const required = sorted.filter((d) => d.required);
  const rest     = sorted.filter((d) => !d.required);
  const ordered = [...required, ...rest];
  const priority = ["text", "number", "currency", "dropdown", "date", "email", "phone"];
  ordered.sort((a, b) => {
    const ai = priority.indexOf(a.type); const bi = priority.indexOf(b.type);
    if (ai === bi) return 0;
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
  return { image, columns: ordered.slice(0, max).map((d) => ({
    id: d.id, key: d.key, label: d.label, type: d.type,
  })) };
}

function CollectionBadge({ entity_type }) {
  const c = entity_type?.color || "#0d9488";
  return (
    <Link
      to={`/entity-types/${entity_type.id}/records`}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium hover:underline"
      style={{ backgroundColor: c + "1a", color: c }}
      onClick={(e) => e.stopPropagation()}
      data-testid={`collection-badge-${entity_type.key}`}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c }} />
      {entity_type.name_plural || entity_type.name_singular}
    </Link>
  );
}

function ImageHero({ url, title }) {
  const backend = process.env.REACT_APP_BACKEND_URL || "";
  const src = url ? (url.startsWith("http") ? url : `${backend}${url}`) : null;
  if (!src) {
    return (
      <div className="aspect-video bg-gradient-to-br from-muted to-muted/50 flex items-center justify-center text-muted-foreground/40">
        <Boxes className="w-8 h-8" />
      </div>
    );
  }
  return (
    <div className="aspect-video bg-muted overflow-hidden">
      <img src={src} alt={title || ""} loading="lazy"
           className="w-full h-full object-cover" />
    </div>
  );
}

function TagChips({ tags = [], max = 3 }) {
  if (!tags.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {tags.slice(0, max).map((t) => (
        <span key={t.id}
              className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
              style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}>
          {t.name}
        </span>
      ))}
      {tags.length > max && (
        <span className="text-[10px] text-muted-foreground">+{tags.length - max}</span>
      )}
    </div>
  );
}

function CategoryInline({ paths = [] }) {
  const first = paths[0];
  if (!first) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span className="text-xs" title={first.path_names?.join(" › ")}>
      {first.name}{paths.length > 1 && <span className="text-muted-foreground"> +{paths.length - 1}</span>}
    </span>
  );
}

/* ────────────────────── layout: table ────────────────────── */
function BrowseTable({ results }) {
  return (
    <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="browse-layout-table">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-32">Record #</TableHead>
            <TableHead>Title</TableHead>
            <TableHead className="w-40">Collection</TableHead>
            <TableHead className="w-40">Category</TableHead>
            <TableHead className="w-40">Tags</TableHead>
            <TableHead className="w-40 text-right">Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((r) => (
            <TableRow key={r.id} data-testid={`browse-row-${r.record_number}`}>
              <TableCell className="font-mono text-xs">
                <Link to={`/records/${r.id}`} className="text-primary hover:underline">
                  {r.record_number}
                </Link>
              </TableCell>
              <TableCell className="max-w-[320px] truncate">
                <Link to={`/records/${r.id}`} className="hover:underline font-medium">
                  {r.title || "—"}
                </Link>
              </TableCell>
              <TableCell><CollectionBadge entity_type={r.entity_type} /></TableCell>
              <TableCell><CategoryInline paths={r.category_paths} /></TableCell>
              <TableCell><TagChips tags={r.tags} /></TableCell>
              <TableCell className="text-right text-xs text-muted-foreground">
                {r.updated_at ? new Date(r.updated_at).toLocaleDateString() : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/* ────────────────────── layout: gallery (adaptive cards) ────────────────────── */
function BrowseGallery({ results, fieldDefsByEt }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4" data-testid="browse-layout-gallery">
      {results.map((r) => {
        const defs = fieldDefsByEt[r.entity_type_id] || [];
        const { image, columns } = pickAdaptiveFields(defs, 4);
        return (
          <Card key={r.id} className="group overflow-hidden hover:shadow-md transition-shadow" data-testid={`browse-card-${r.record_number}`}>
            <Link to={`/records/${r.id}`} className="block">
              <ImageHero url={r.primary_image_url} title={r.title} />
            </Link>
            <CardHeader className="pb-2 pt-3 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <CollectionBadge entity_type={r.entity_type} />
                <span className="font-mono text-[10px] text-muted-foreground">{r.record_number}</span>
              </div>
              <CardTitle className="text-base truncate">
                <Link to={`/records/${r.id}`} className="hover:underline">
                  {r.title || "—"}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 pb-3 space-y-1.5 text-xs">
              {columns.slice(0, image ? 2 : 3).map((c) => {
                const v = r.fields?.[c.key];
                if (v === null || v === undefined || v === "") return null;
                return (
                  <div key={c.id} className="flex items-baseline gap-1.5 min-w-0">
                    <span className="text-muted-foreground shrink-0">{c.label}:</span>
                    <span className="truncate">{formatCellValue(c, v)}</span>
                  </div>
                );
              })}
              <TagChips tags={r.tags} max={4} />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/* ────────────────────── layout: grid (compact) ────────────────────── */
function BrowseGrid({ results }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2" data-testid="browse-layout-grid">
      {results.map((r) => (
        <Link key={r.id} to={`/records/${r.id}`}
              data-testid={`browse-grid-${r.record_number}`}
              className="group border border-border rounded-lg bg-white p-3 hover:border-primary/50 hover:shadow-sm transition-all">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-primary">{r.record_number}</span>
          </div>
          <div className="text-sm font-medium mt-1 truncate">{r.title || "—"}</div>
          <div className="mt-1.5"><CollectionBadge entity_type={r.entity_type} /></div>
          <div className="mt-1.5"><TagChips tags={r.tags} max={2} /></div>
        </Link>
      ))}
    </div>
  );
}

/* ────────────────────── layout: card (rich, 2-col) ────────────────────── */
function BrowseCard({ results, fieldDefsByEt }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="browse-layout-card">
      {results.map((r) => {
        const defs = fieldDefsByEt[r.entity_type_id] || [];
        const { columns } = pickAdaptiveFields(defs, 4);
        return (
          <Card key={r.id} className="hover:shadow-md transition-shadow" data-testid={`browse-cardrow-${r.record_number}`}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <CollectionBadge entity_type={r.entity_type} />
                    <span className="font-mono text-[10px] text-muted-foreground">{r.record_number}</span>
                  </div>
                  <CardTitle className="text-base truncate">
                    <Link to={`/records/${r.id}`} className="hover:underline">
                      {r.title || "—"}
                    </Link>
                  </CardTitle>
                </div>
                <CategoryInline paths={r.category_paths} />
              </div>
            </CardHeader>
            <CardContent className="pt-0 space-y-2">
              <div className="grid grid-cols-2 gap-2 text-xs">
                {columns.map((c) => (
                  <div key={c.id} className="min-w-0">
                    <div className="text-muted-foreground text-[10px] font-mono uppercase">{c.label}</div>
                    <div className="truncate">{formatCellValue(c, r.fields?.[c.key])}</div>
                  </div>
                ))}
              </div>
              <TagChips tags={r.tags} max={5} />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/* ────────────────────── layout: list ────────────────────── */
function BrowseList({ results }) {
  return (
    <div className="divide-y divide-border rounded-lg border border-border bg-white overflow-hidden" data-testid="browse-layout-list">
      {results.map((r) => (
        <div key={r.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/40" data-testid={`browse-list-${r.record_number}`}>
          <div className="font-mono text-xs text-primary w-24 shrink-0">
            <Link to={`/records/${r.id}`} className="hover:underline">{r.record_number}</Link>
          </div>
          <div className="flex-1 min-w-0">
            <Link to={`/records/${r.id}`} className="font-medium text-sm truncate block hover:underline">
              {r.title || "—"}
            </Link>
          </div>
          <div className="hidden sm:block"><CollectionBadge entity_type={r.entity_type} /></div>
          <div className="hidden md:block"><TagChips tags={r.tags} max={3} /></div>
          <div className="hidden lg:block w-32 text-xs text-muted-foreground text-right">
            {r.updated_at ? new Date(r.updated_at).toLocaleDateString() : "—"}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ────────────────────── views bar ────────────────────── */
function BrowseViewsBar({ activeViewId, onPick, currentState, canShare }) {
  const [views, setViews] = useState([]);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [isShared, setIsShared] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/browse/views");
      setViews(r.data || []);
    } catch {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveNew = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const body = {
        name: name.trim(),
        layout: currentState.layout,
        q: currentState.q || null,
        entity_type_ids: currentState.entity_type_ids || [],
        category_ids: currentState.category_ids || [],
        tag_ids: currentState.tag_ids || [],
        updated_since: currentState.updated_since || null,
        sort: currentState.sort,
        is_shared: !!isShared,
      };
      const r = await api.post("/browse/views", body);
      toast.success(`View "${r.data.name}" saved`);
      setSaveOpen(false); setName(""); setIsShared(false);
      await load();
      onPick(r.data);
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (v) => {
    if (!window.confirm(`Delete view "${v.name}"?`)) return;
    try {
      await api.delete(`/views/${v.id}`);
      toast.success("View deleted");
      await load();
      if (v.id === activeViewId) onPick(null);
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  return (
    <div className="flex items-center gap-1.5" data-testid="browse-views-bar">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5" data-testid="browse-views-trigger">
            <Bookmark className="w-3.5 h-3.5" />
            {views.find((v) => v.id === activeViewId)?.name || "Views"}
            <ChevronDown className="w-3 h-3 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[280px]">
          <DropdownMenuLabel className="text-[10px] font-mono uppercase text-muted-foreground">
            Saved views
          </DropdownMenuLabel>
          {views.length === 0 && (
            <div className="px-2 py-3 text-xs text-muted-foreground text-center">
              No saved views yet.
            </div>
          )}
          {views.map((v) => (
            <DropdownMenuItem key={v.id} onSelect={(e) => { e.preventDefault(); onPick(v); }}
                              className="flex items-center justify-between gap-2 cursor-pointer"
                              data-testid={`browse-view-${v.id}`}>
              <div className="min-w-0">
                <div className="text-sm truncate">{v.name}</div>
                {v.is_shared && <div className="text-[10px] text-primary">shared</div>}
              </div>
              <button
                type="button" onClick={(e) => { e.stopPropagation(); remove(v); }}
                className="text-muted-foreground hover:text-destructive p-0.5"
                data-testid={`browse-view-del-${v.id}`}
                aria-label={`Delete view ${v.name}`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={(e) => { e.preventDefault(); setSaveOpen(true); }} data-testid="browse-view-save">
            <Save className="w-3.5 h-3.5 mr-2" /> Save current filters as view…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent data-testid="browse-view-save-dialog">
          <form onSubmit={saveNew}>
            <DialogHeader><DialogTitle>Save this view</DialogTitle></DialogHeader>
            <div className="space-y-3 py-3">
              <div>
                <Label htmlFor="view-name">Name</Label>
                <Input id="view-name" value={name} onChange={(e) => setName(e.target.value)}
                       placeholder="Everything updated today" required data-testid="browse-view-name-input" />
              </div>
              {canShare && (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={isShared}
                         onChange={(e) => setIsShared(e.target.checked)}
                         data-testid="browse-view-shared-input" />
                  Share with everyone in this workspace
                </label>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setSaveOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving} data-testid="browse-view-save-submit">
                {saving ? "Saving…" : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ────────────────────── main page ────────────────────── */
export default function BrowsePage() {
  const nav = useNavigate();
  const { t } = useTerminology();
  const [searchParams, setSearchParams] = useSearchParams();
  useTabTitle(t("nav.browse") || "All Items", "compass");

  // Query state — hydrated from URL params so tabs/refresh preserve filters.
  const [q, setQ] = useState(searchParams.get("q") || "");
  const [entityTypeIds, setEntityTypeIds] = useState(
    (searchParams.get("et") || "").split(",").filter(Boolean),
  );
  const [categoryIds, setCategoryIds] = useState(
    (searchParams.get("cat") || "").split(",").filter(Boolean),
  );
  const [tagIds, setTagIds] = useState(
    (searchParams.get("tag") || "").split(",").filter(Boolean),
  );
  const [layout, setLayout] = useState(searchParams.get("layout") || "table");
  const [sort, setSort]     = useState(searchParams.get("sort") || "updated_at:desc");
  const [activeViewId, setActiveViewId] = useState(null);

  // Server state
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState(null);
  const [appending, setAppending] = useState(false);

  const load = useCallback(async ({ append = false } = {}) => {
    if (append) setAppending(true); else setLoading(true);
    try {
      const params = { limit: 50, sort };
      if (q) params.q = q;
      if (entityTypeIds.length) params.entity_type_ids = entityTypeIds.join(",");
      if (categoryIds.length)   params.category_ids   = categoryIds.join(",");
      if (tagIds.length)        params.tag_ids        = tagIds.join(",");
      if (append && cursor) params.cursor = cursor;

      const r = await api.get("/records/browse", { params });
      if (append && data) {
        setData({
          ...r.data,
          results: [...data.results, ...r.data.results],
          entity_type_field_defs: { ...data.entity_type_field_defs, ...r.data.entity_type_field_defs },
        });
      } else {
        setData(r.data);
      }
      setCursor(r.data.next_cursor);
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setLoading(false); setAppending(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, entityTypeIds, categoryIds, tagIds, sort]);

  // Reload when filters change; sync to URL for shareability / refresh survival
  useEffect(() => {
    const p = {};
    if (q) p.q = q;
    if (entityTypeIds.length) p.et = entityTypeIds.join(",");
    if (categoryIds.length)   p.cat = categoryIds.join(",");
    if (tagIds.length)        p.tag = tagIds.join(",");
    if (layout !== "table")   p.layout = layout;
    if (sort !== "updated_at:desc") p.sort = sort;
    setSearchParams(p, { replace: true });
    setCursor(null);
    load({ append: false });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, entityTypeIds, categoryIds, tagIds, sort]);

  const applyView = useCallback((v) => {
    if (!v) {
      setActiveViewId(null);
      return;
    }
    setActiveViewId(v.id);
    setQ(v.q || "");
    setEntityTypeIds(v.browse_entity_type_ids || []);
    setCategoryIds(v.category_ids || []);
    setTagIds(v.tag_ids || []);
    setLayout(v.layout || "table");
    setSort(v.browse_sort || "updated_at:desc");
  }, []);

  const toggleEt = (id) => {
    setEntityTypeIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };
  const toggleTag = (id) => {
    setTagIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };
  const toggleCat = (id) => {
    setCategoryIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const clearAll = () => {
    setQ(""); setEntityTypeIds([]); setCategoryIds([]); setTagIds([]);
    setSort("updated_at:desc"); setLayout("table"); setActiveViewId(null);
  };

  const activeCount = entityTypeIds.length + categoryIds.length + tagIds.length + (q ? 1 : 0);
  const currentLayoutMeta = LAYOUTS.find((l) => l.key === layout) || LAYOUTS[0];
  const activeSortLabel   = SORTS.find((s) => s.key === sort)?.label || sort;

  const fieldDefsByEt = data?.entity_type_field_defs || {};

  return (
    <>
      <PageHeader
        title={t("nav.browse") || "All Items"}
        subtitle={`Every ${(t("record.singular") || "item").toLowerCase()} across every ${(t("collection.singular") || "collection").toLowerCase()}, in one place.`}
        breadcrumbs={[{ label: "UBOS" }, { label: t("nav.browse") || "All Items" }]}
        actions={
          <BrowseViewsBar
            activeViewId={activeViewId}
            onPick={applyView}
            currentState={{
              layout, q, sort,
              entity_type_ids: entityTypeIds,
              category_ids: categoryIds,
              tag_ids: tagIds,
            }}
            canShare={true}
          />
        }
      />
      <PageBody>
        {/* Search + facet filter chips row */}
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="relative flex-1 min-w-[240px] max-w-md">
            <SearchIcon className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`Search everything…`}
              className="pl-8 h-9 text-sm"
              data-testid="browse-search-input"
            />
          </div>

          {/* Collection filter (multi-select) */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5" data-testid="browse-facet-et-trigger">
                <Boxes className="w-3.5 h-3.5" />
                In collection
                {entityTypeIds.length > 0 && (
                  <Badge variant="secondary" className="text-[10px] px-1.5 h-4">{entityTypeIds.length}</Badge>
                )}
                <ChevronDown className="w-3 h-3 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[260px] max-h-[400px] overflow-y-auto">
              <DropdownMenuLabel className="text-[10px] font-mono uppercase text-muted-foreground">
                Filter by collection
              </DropdownMenuLabel>
              {(data?.facets?.entity_types || []).map((f) => (
                <DropdownMenuCheckboxItem
                  key={f.id}
                  checked={entityTypeIds.includes(f.id)}
                  onCheckedChange={() => toggleEt(f.id)}
                  data-testid={`browse-facet-et-${f.id}`}
                >
                  <span className="w-2 h-2 rounded-full mr-2" style={{ backgroundColor: f.color || "#0d9488" }} />
                  <span className="flex-1 truncate">{f.name}</span>
                  <span className="text-[10px] text-muted-foreground ml-2">{f.count}</span>
                </DropdownMenuCheckboxItem>
              ))}
              {(!data?.facets?.entity_types?.length) && (
                <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                  No collections in the current results.
                </div>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Category filter */}
          {(data?.facets?.categories || []).length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5" data-testid="browse-facet-cat-trigger">
                  <FolderTree className="w-3.5 h-3.5" />
                  Category
                  {categoryIds.length > 0 && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 h-4">{categoryIds.length}</Badge>
                  )}
                  <ChevronDown className="w-3 h-3 opacity-60" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-[260px] max-h-[400px] overflow-y-auto">
                {(data.facets.categories).map((f) => (
                  <DropdownMenuCheckboxItem
                    key={f.id}
                    checked={categoryIds.includes(f.id)}
                    onCheckedChange={() => toggleCat(f.id)}
                    data-testid={`browse-facet-cat-${f.id}`}
                  >
                    <span className="flex-1 truncate" title={f.path_names?.join(" › ")}>{f.name}</span>
                    <span className="text-[10px] text-muted-foreground ml-2">{f.count}</span>
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {/* Tag filter */}
          {(data?.facets?.tags || []).length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5" data-testid="browse-facet-tag-trigger">
                  <TagIcon className="w-3.5 h-3.5" />
                  Tag
                  {tagIds.length > 0 && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 h-4">{tagIds.length}</Badge>
                  )}
                  <ChevronDown className="w-3 h-3 opacity-60" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-[220px] max-h-[400px] overflow-y-auto">
                {(data.facets.tags).map((f) => (
                  <DropdownMenuCheckboxItem
                    key={f.id}
                    checked={tagIds.includes(f.id)}
                    onCheckedChange={() => toggleTag(f.id)}
                    data-testid={`browse-facet-tag-${f.id}`}
                  >
                    <span className="w-2 h-2 rounded-full mr-2" style={{ backgroundColor: f.color || "#0d9488" }} />
                    <span className="flex-1 truncate">{f.name}</span>
                    <span className="text-[10px] text-muted-foreground ml-2">{f.count}</span>
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <div className="flex-1" />

          {/* Sort */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5" data-testid="browse-sort-trigger">
                <ArrowUpDown className="w-3.5 h-3.5" />
                {activeSortLabel}
                <ChevronDown className="w-3 h-3 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {SORTS.map((s) => (
                <DropdownMenuItem key={s.key} onSelect={() => setSort(s.key)} data-testid={`browse-sort-${s.key}`}>
                  {s.key === sort ? "• " : "  "}{s.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Layout switcher */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5" data-testid="browse-layout-trigger">
                <currentLayoutMeta.icon className="w-3.5 h-3.5" />
                {currentLayoutMeta.label}
                <ChevronDown className="w-3 h-3 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {LAYOUTS.map((l) => (
                <DropdownMenuItem key={l.key} onSelect={() => setLayout(l.key)} data-testid={`browse-layout-${l.key}`}>
                  <l.icon className="w-3.5 h-3.5 mr-2" />
                  {l.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {activeCount > 0 && (
            <Button variant="ghost" size="sm" onClick={clearAll} data-testid="browse-clear-filters">
              <X className="w-3.5 h-3.5 mr-1" /> Clear
            </Button>
          )}
        </div>

        {/* Result meta strip */}
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
          <div data-testid="browse-total-count">
            {loading ? "Loading…" : `${data?.total_estimate || 0} result${(data?.total_estimate || 0) === 1 ? "" : "s"}`}
            {data?.took_ms != null && !loading && <span className="ml-2 opacity-60">· {data.took_ms}ms</span>}
          </div>
          <Button variant="ghost" size="sm" onClick={() => load()} disabled={loading} className="h-7">
            <RefreshCw className={`w-3 h-3 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>

        {/* Results */}
        {loading && !data ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground" data-testid="browse-loading">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading items…
          </div>
        ) : !data?.results?.length ? (
          <EmptyState
            icon={Compass}
            title="No items match"
            description={q || activeCount > 0
              ? "Try broadening or clearing your filters."
              : `You don't have any ${(t("record.plural") || "items").toLowerCase()} yet. Create your first ${(t("collection.singular") || "Collection").toLowerCase()} and start adding.`}
            action={<Button onClick={() => nav("/entity-types")}>Go to My Data</Button>}
            testId="browse-empty"
          />
        ) : (
          <>
            {layout === "table"   && <BrowseTable   results={data.results} />}
            {layout === "gallery" && <BrowseGallery results={data.results} fieldDefsByEt={fieldDefsByEt} />}
            {layout === "grid"    && <BrowseGrid    results={data.results} />}
            {layout === "card"    && <BrowseCard    results={data.results} fieldDefsByEt={fieldDefsByEt} />}
            {layout === "list"    && <BrowseList    results={data.results} />}

            {cursor && (
              <div className="flex justify-center pt-4">
                <Button variant="outline" size="sm" onClick={() => load({ append: true })} disabled={appending}
                        data-testid="browse-load-more">
                  {appending ? <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> : null}
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </PageBody>
    </>
  );
}
