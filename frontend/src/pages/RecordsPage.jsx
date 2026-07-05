import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Plus, Trash2, Layers, ListChecks, FolderTree, Tag as TagIcon,
  Table2, LayoutGrid, Rows3, Boxes, List as ListIcon,
} from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage, extractFieldErrors } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { DynamicField } from "@/components/DynamicField";
import { CategoryPicker, CategoryFilter } from "@/components/CategoryPicker";
import { TagCombobox } from "@/components/TagCombobox";
import { FilterBar } from "@/components/FilterBar";
import { ViewsBar } from "@/components/ViewsBar";
import { BulkToolbar } from "@/components/BulkToolbar";
import { RecordsLayoutRenderer, LAYOUTS } from "@/components/RecordLayouts";
import { useAuth } from "@/lib/auth";

const LAYOUT_ICONS = {
  table: Table2, gallery: LayoutGrid, grid: Boxes, card: Rows3, list: ListIcon,
};

function initialValues(fields, existing) {
  const v = {};
  fields.forEach((f) => {
    if (existing && existing.fields && existing.fields[f.key] !== undefined) {
      v[f.key] = existing.fields[f.key];
    } else if (f.type === "multi_select") v[f.key] = [];
    else if (f.type === "boolean") v[f.key] = false;
    else v[f.key] = "";
  });
  return v;
}

export default function RecordsPage() {
  const { id: etId } = useParams();
  const nav = useNavigate();
  const { activeRole } = useAuth();
  const canShare = ["owner", "admin"].includes(activeRole);

  const [et, setEt] = useState(null);
  const [fields, setFields] = useState([]);
  const [tagsById, setTagsById] = useState({});
  const [catsById, setCatsById] = useState({});

  // Query state
  const [layout, setLayout] = useState("table");
  const [q, setQ] = useState("");
  const [filterCat, setFilterCat] = useState(null);
  const [filterTags, setFilterTags] = useState([]);
  const [filters, setFilters] = useState([]);
  const [sort, setSort] = useState([]);
  const [activeViewId, setActiveViewId] = useState(null);

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());

  // Record dialog
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [recCats, setRecCats] = useState([]);
  const [recTags, setRecTags] = useState([]);

  const load = async () => {
    try {
      const [etRes, flRes, tagsRes, catsRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get(`/entity-types/${etId}/fields`),
        api.get("/tags", { params: { entity_type_id: etId } }),
        api.get(`/entity-types/${etId}/categories`, { params: { flat: true } }),
      ]);
      setEt(etRes.data);
      setFields(flRes.data);
      setTagsById(Object.fromEntries(tagsRes.data.map((t) => [t.id, t])));
      setCatsById(Object.fromEntries(catsRes.data.map((c) => [c.id, c])));
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const body = {
        q: q || null,
        category_id: filterCat,
        tag_ids: filterTags,
        filters,
        sort,
        limit: 200,
        skip: 0,
      };
      const r = await api.post(`/entity-types/${etId}/records/search`, body);
      setItems(r.data.items || []);
      setTotal(r.data.total || 0);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etId, q, filterCat, JSON.stringify(filterTags), JSON.stringify(filters), JSON.stringify(sort)]);

  useEffect(() => { load(); }, [etId]);
  useEffect(() => { loadRecords(); }, [loadRecords]);

  // When switching a view, hydrate the local state from it
  const applyView = async (viewId) => {
    setActiveViewId(viewId);
    setSelected(new Set());
    if (!viewId) {
      setLayout("table"); setQ(""); setFilterCat(null);
      setFilterTags([]); setFilters([]); setSort([]);
      return;
    }
    try {
      const r = await api.get(`/views/${viewId}`);
      const v = r.data;
      setLayout(v.layout || "table");
      setQ(v.q || "");
      setFilterCat((v.category_ids || [])[0] || null);
      setFilterTags(v.tag_ids || []);
      setFilters(v.filters || []);
      setSort(v.sort || []);
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const columns = fields.slice(0, 4);

  const toggleSelect = (id) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const toggleAll = () => {
    setSelected((s) => {
      if (items.every((r) => s.has(r.id))) return new Set();
      return new Set(items.map((r) => r.id));
    });
  };
  const clearSelection = () => setSelected(new Set());

  const openCreate = () => {
    setEditing(null);
    setValues(initialValues(fields, null));
    setRecCats([]); setRecTags([]);
    setErrors({});
    setOpen(true);
  };
  const openEdit = (rec) => {
    setEditing(rec);
    setValues(initialValues(fields, rec));
    setRecCats(rec.category_ids || []);
    setRecTags(rec.tag_ids || []);
    setErrors({});
    setOpen(true);
  };
  const setField = (key, v) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    if (errors[`fields.${key}`]) {
      setErrors((p) => { const n = { ...p }; delete n[`fields.${key}`]; return n; });
    }
  };
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    const clean = {};
    fields.forEach((f) => {
      const v = values[f.key];
      if (v === "" || v === undefined) return;
      clean[f.key] = v;
    });
    const body = { fields: clean, category_ids: recCats, tag_ids: recTags };
    try {
      if (editing) {
        await api.patch(`/records/${editing.id}`, body);
        toast.success("Record updated");
      } else {
        await api.post(`/entity-types/${etId}/records`, body);
        toast.success("Record created");
      }
      setOpen(false);
      loadRecords();
    } catch (err) {
      const fe = extractFieldErrors(err);
      if (fe) { setErrors(fe); toast.error("Please fix the errors below"); }
      else toast.error(extractErrorMessage(err));
    } finally { setSaving(false); }
  };

  const removeRec = async (rec) => {
    if (!window.confirm(`Delete record ${rec.record_number}?`)) return;
    try {
      await api.delete(`/records/${rec.id}`);
      toast.success("Record deleted");
      loadRecords();
    } catch (err) { toast.error(extractErrorMessage(err)); }
  };

  const toggleFilterTag = (tid) => setFilterTags((p) => p.includes(tid) ? p.filter((x) => x !== tid) : [...p, tid]);

  const currentState = { layout, q, category_id: filterCat, tag_ids: filterTags, filters, sort, visible_fields: [] };

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Records` : "Records"}
        subtitle={`${total} record${total === 1 ? "" : "s"} · pick a view or build a query below.`}
        breadcrumbs={[
          { label: "Entity Types", to: "/entity-types" },
          { label: et?.name_plural || "…" },
          { label: "Records" },
        ]}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => nav(`/entity-types/${etId}/categories`)} data-testid="go-cats-btn">
              <FolderTree className="w-4 h-4 mr-1.5" /> Categories
            </Button>
            <Button variant="outline" onClick={() => nav(`/entity-types/${etId}/fields`)} data-testid="go-fields-btn">
              <Layers className="w-4 h-4 mr-1.5" /> Fields
            </Button>
            <Button onClick={openCreate} disabled={fields.length === 0} data-testid="new-record-btn">
              <Plus className="w-4 h-4 mr-1.5" /> New record
            </Button>
          </div>
        }
      />
      <PageBody>
        {fields.length === 0 ? (
          <EmptyState
            icon={Layers} title="Define fields first"
            description="You need at least one field before you can create records."
            action={<Button onClick={() => nav(`/entity-types/${etId}/fields`)}><Layers className="w-4 h-4 mr-1.5" /> Go to fields</Button>}
          />
        ) : (
          <div className="space-y-4">
            {/* Top row: view picker + layout switch + search */}
            <div className="flex items-center gap-3 flex-wrap">
              <ViewsBar
                entityTypeId={etId}
                activeViewId={activeViewId}
                onSelectView={applyView}
                currentState={currentState}
                canShare={canShare}
              />
              <div className="inline-flex bg-muted/40 border border-border rounded-md p-0.5">
                {LAYOUTS.map((L) => {
                  const Icon = LAYOUT_ICONS[L.key];
                  const on = layout === L.key;
                  return (
                    <button
                      key={L.key} type="button"
                      onClick={() => setLayout(L.key)}
                      className={`h-7 px-2.5 flex items-center gap-1 rounded text-xs transition-colors ${on ? "bg-white shadow-sm font-medium" : "text-muted-foreground hover:text-foreground"}`}
                      title={L.label}
                      data-testid={`layout-${L.key}`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      <span className="hidden md:inline">{L.label}</span>
                    </button>
                  );
                })}
              </div>
              <div className="flex-1 min-w-[160px] max-w-md">
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search records…"
                  className="h-8 text-sm"
                  data-testid="records-search"
                />
              </div>
            </div>

            {/* Filter chips row */}
            <div className="flex items-center gap-2 flex-wrap">
              <CategoryFilter
                entityTypeId={etId}
                value={filterCat}
                onChange={setFilterCat}
                testId="records-cat-filter"
              />
              <div className="flex items-center gap-1.5 flex-wrap">
                {Object.values(tagsById).slice(0, 8).map((t) => {
                  const on = filterTags.includes(t.id);
                  return (
                    <button
                      key={t.id} type="button"
                      onClick={() => toggleFilterTag(t.id)}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium transition-all ${on ? "ring-2 ring-primary/40" : "opacity-70 hover:opacity-100"}`}
                      style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
                      data-testid={`filter-tag-${t.slug}`}
                    >
                      <TagIcon className="w-2.5 h-2.5" /> {t.name}
                    </button>
                  );
                })}
              </div>
              {(filterCat || filterTags.length > 0 || q) && (
                <Button variant="ghost" size="sm" className="h-7 text-xs"
                  onClick={() => { setFilterCat(null); setFilterTags([]); setQ(""); }}
                  data-testid="clear-filters">Clear</Button>
              )}
              <span className="mx-1 text-border">·</span>
              <FilterBar fields={fields} filters={filters} sort={sort}
                onFiltersChange={setFilters} onSortChange={setSort} />
            </div>

            {selected.size > 0 && (
              <BulkToolbar
                etId={etId}
                selectedIds={[...selected]}
                fields={fields}
                onDone={() => { clearSelection(); loadRecords(); }}
                onClear={clearSelection}
              />
            )}

            {/* Content */}
            {loading ? (
              <div className="text-sm text-muted-foreground">Loading…</div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title={filters.length || filterCat || filterTags.length || q ? "No records match" : "No records yet"}
                description={filters.length || filterCat || filterTags.length || q ? "Try relaxing the filters or clearing search." : `Create the first ${et?.name_singular || "record"}.`}
                action={!(filters.length || filterCat || filterTags.length || q) && <Button onClick={openCreate}><Plus className="w-4 h-4 mr-1.5" /> New record</Button>}
              />
            ) : (
              <RecordsLayoutRenderer
                layout={layout}
                records={items}
                columns={columns}
                selected={selected}
                onToggle={toggleSelect}
                onToggleAll={toggleAll}
                catsById={catsById}
                tagsById={tagsById}
                onEdit={openEdit}
                onDelete={removeRec}
              />
            )}
          </div>
        )}
      </PageBody>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="record-dialog">
          <form onSubmit={submit}>
            <DialogHeader>
              <DialogTitle>
                {editing ? (
                  <span className="flex items-center gap-2">
                    Edit record
                    <span className="font-mono text-xs text-primary">{editing.record_number}</span>
                  </span>
                ) : (`New ${et?.name_singular || "record"}`)}
              </DialogTitle>
            </DialogHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
              {fields.map((f) => (
                <div key={f.id}
                  className={f.type === "longtext" || f.type === "richtext" || f.type === "multi_select" ? "md:col-span-2" : ""}>
                  <DynamicField field={f} value={values[f.key]}
                    onChange={(v) => setField(f.key, v)}
                    error={errors[`fields.${f.key}`]} />
                </div>
              ))}
              <div className="md:col-span-2 pt-2 border-t border-border">
                <Label className="text-sm">Categories</Label>
                <CategoryPicker entityTypeId={etId} value={recCats} onChange={setRecCats} testIdPrefix="record-cat" />
              </div>
              <div className="md:col-span-2">
                <Label className="text-sm">Tags</Label>
                <TagCombobox entityTypeId={etId} value={recTags} onChange={setRecTags} testIdPrefix="record-tag" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving} data-testid="submit-record">
                {saving ? "Saving…" : editing ? "Save changes" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
