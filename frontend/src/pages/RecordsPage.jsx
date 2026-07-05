import { useEffect, useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Plus, Trash2, Pencil, Layers, ListChecks, FolderTree, Tag as TagIcon } from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage, extractFieldErrors } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { DynamicField } from "@/components/DynamicField";
import { CategoryPicker, CategoryFilter } from "@/components/CategoryPicker";
import { TagCombobox } from "@/components/TagCombobox";

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

function formatCellValue(field, value) {
  if (value === null || value === undefined || value === "") return "—";
  switch (field.type) {
    case "boolean": return value ? "Yes" : "No";
    case "currency":
      return typeof value === "number"
        ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value)
        : value;
    case "multi_select": return Array.isArray(value) ? value.join(", ") : String(value);
    case "longtext":
    case "richtext":
      return typeof value === "string" && value.length > 60 ? value.slice(0, 60) + "…" : value;
    default: return String(value);
  }
}

export default function RecordsPage() {
  const { id: etId } = useParams();
  const nav = useNavigate();
  const [et, setEt] = useState(null);
  const [fields, setFields] = useState([]);
  const [tagsById, setTagsById] = useState({});
  const [catsById, setCatsById] = useState({});
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [recCats, setRecCats] = useState([]);
  const [recTags, setRecTags] = useState([]);

  // Filters
  const [filterCat, setFilterCat] = useState(null);
  const [filterTags, setFilterTags] = useState([]);

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
      await loadRecords();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const loadRecords = async () => {
    const params = { limit: 200 };
    if (filterCat) params.category_id = filterCat;
    if (filterTags.length) params.tag_ids = filterTags;
    const rcRes = await api.get(`/entity-types/${etId}/records`, { params });
    setItems(rcRes.data.items || []);
  };

  useEffect(() => { load(); }, [etId]);
  useEffect(() => { if (!loading) loadRecords(); }, [filterCat, JSON.stringify(filterTags)]);

  const columns = useMemo(() => fields.slice(0, 4), [fields]);

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
      setErrors((prev) => { const next = { ...prev }; delete next[`fields.${key}`]; return next; });
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
      await loadRecords();
    } catch (err) {
      const fe = extractFieldErrors(err);
      if (fe) { setErrors(fe); toast.error("Please fix the errors below"); }
      else toast.error(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (rec) => {
    if (!window.confirm(`Delete record ${rec.record_number}?`)) return;
    try {
      await api.delete(`/records/${rec.id}`);
      toast.success("Record deleted");
      await loadRecords();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const toggleFilterTag = (tid) => {
    setFilterTags((prev) => prev.includes(tid) ? prev.filter((x) => x !== tid) : [...prev, tid]);
  };

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Records` : "Records"}
        subtitle="Data lives here — every field on the form comes from your field definitions."
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
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : fields.length === 0 ? (
          <EmptyState
            icon={Layers} title="Define fields first"
            description="You need at least one field before you can create records."
            action={<Button onClick={() => nav(`/entity-types/${etId}/fields`)}><Layers className="w-4 h-4 mr-1.5" /> Go to fields</Button>}
          />
        ) : (
          <div className="space-y-4">
            {/* Filter bar */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-mono uppercase text-muted-foreground">Filters:</span>
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
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium transition-all ${
                        on ? "ring-2 ring-primary/40" : "opacity-70 hover:opacity-100"
                      }`}
                      style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
                      data-testid={`filter-tag-${t.slug}`}
                    >
                      <TagIcon className="w-2.5 h-2.5" />
                      {t.name}
                    </button>
                  );
                })}
              </div>
              {(filterCat || filterTags.length > 0) && (
                <Button
                  variant="ghost" size="sm" onClick={() => { setFilterCat(null); setFilterTags([]); }}
                  data-testid="clear-filters"
                >
                  Clear
                </Button>
              )}
            </div>

            {items.length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title={filterCat || filterTags.length ? "No records match those filters" : "No records yet"}
                description={filterCat || filterTags.length ? "Try clearing filters." : `Create the first ${et?.name_singular || "record"}.`}
                action={!filterCat && !filterTags.length && <Button onClick={openCreate}><Plus className="w-4 h-4 mr-1.5" /> New record</Button>}
              />
            ) : (
              <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="records-table-wrap">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-28">Record #</TableHead>
                      {columns.map((c) => (
                        <TableHead key={c.id}>{c.label}</TableHead>
                      ))}
                      <TableHead>Category</TableHead>
                      <TableHead>Tags</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((r) => {
                      const firstCat = r.category_ids?.[0] && catsById[r.category_ids[0]];
                      return (
                        <TableRow key={r.id} data-testid={`record-row-${r.record_number}`}>
                          <TableCell className="font-mono text-xs text-primary">
                            {r.record_number}
                          </TableCell>
                          {columns.map((c) => (
                            <TableCell key={c.id} className="max-w-[220px] truncate">
                              {formatCellValue(c, r.fields?.[c.key])}
                            </TableCell>
                          ))}
                          <TableCell>
                            {firstCat ? (
                              <span
                                className="text-xs"
                                title={firstCat.path_names?.join(" › ")}
                                data-testid={`record-cat-${r.record_number}`}
                              >
                                {firstCat.name}
                                {r.category_ids.length > 1 && (
                                  <span className="text-muted-foreground"> +{r.category_ids.length - 1}</span>
                                )}
                              </span>
                            ) : <span className="text-xs text-muted-foreground">—</span>}
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">
                              {r.tag_ids?.slice(0, 3).map((tid) => {
                                const t = tagsById[tid];
                                if (!t) return null;
                                return (
                                  <span
                                    key={tid}
                                    className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                                    style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
                                    data-testid={`record-tag-${r.record_number}-${t.slug}`}
                                  >
                                    {t.name}
                                  </span>
                                );
                              })}
                              {r.tag_ids?.length > 3 && (
                                <span className="text-[10px] text-muted-foreground">+{r.tag_ids.length - 3}</span>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="inline-flex gap-1">
                              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(r)} data-testid={`edit-record-${r.record_number}`}>
                                <Pencil className="w-4 h-4" />
                              </Button>
                              <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => remove(r)} data-testid={`delete-record-${r.record_number}`}>
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
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
                <div
                  key={f.id}
                  className={
                    f.type === "longtext" || f.type === "richtext" || f.type === "multi_select"
                      ? "md:col-span-2" : ""
                  }
                >
                  <DynamicField
                    field={f} value={values[f.key]}
                    onChange={(v) => setField(f.key, v)}
                    error={errors[`fields.${f.key}`]}
                  />
                </div>
              ))}
              <div className="md:col-span-2 pt-2 border-t border-border">
                <Label className="text-sm">Categories</Label>
                <CategoryPicker
                  entityTypeId={etId} value={recCats} onChange={setRecCats}
                  testIdPrefix="record-cat"
                />
              </div>
              <div className="md:col-span-2">
                <Label className="text-sm">Tags</Label>
                <TagCombobox
                  entityTypeId={etId} value={recTags} onChange={setRecTags}
                  testIdPrefix="record-tag"
                />
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
