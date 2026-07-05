import { useEffect, useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Plus, Trash2, Pencil, Layers, ListChecks } from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage, extractFieldErrors } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { DynamicField } from "@/components/DynamicField";

function initialValues(fields, existing) {
  const v = {};
  fields.forEach((f) => {
    if (existing && existing.fields && existing.fields[f.key] !== undefined) {
      v[f.key] = existing.fields[f.key];
    } else if (f.type === "multi_select") {
      v[f.key] = [];
    } else if (f.type === "boolean") {
      v[f.key] = false;
    } else {
      v[f.key] = "";
    }
  });
  return v;
}

function formatCellValue(field, value) {
  if (value === null || value === undefined || value === "") return "—";
  switch (field.type) {
    case "boolean":
      return value ? "Yes" : "No";
    case "currency":
      return typeof value === "number"
        ? new Intl.NumberFormat(undefined, {
            style: "currency",
            currency: "USD",
          }).format(value)
        : value;
    case "multi_select":
      return Array.isArray(value) ? value.join(", ") : String(value);
    case "longtext":
    case "richtext":
      return typeof value === "string" && value.length > 60
        ? value.slice(0, 60) + "…"
        : value;
    default:
      return String(value);
  }
}

export default function RecordsPage() {
  const { id: etId } = useParams();
  const nav = useNavigate();
  const [et, setEt] = useState(null);
  const [fields, setFields] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null); // record or null (creating)
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});

  const load = async () => {
    try {
      const [etRes, flRes, rcRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get(`/entity-types/${etId}/fields`),
        api.get(`/entity-types/${etId}/records`, { params: { limit: 200 } }),
      ]);
      setEt(etRes.data);
      setFields(flRes.data);
      setItems(rcRes.data.items || []);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [etId]);

  const columns = useMemo(() => fields.slice(0, 5), [fields]);

  const openCreate = () => {
    setEditing(null);
    setValues(initialValues(fields, null));
    setErrors({});
    setOpen(true);
  };

  const openEdit = (rec) => {
    setEditing(rec);
    setValues(initialValues(fields, rec));
    setErrors({});
    setOpen(true);
  };

  const setField = (key, v) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    if (errors[`fields.${key}`]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[`fields.${key}`];
        return next;
      });
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    // strip empty strings; leave booleans/multi_select as-is
    const clean = {};
    fields.forEach((f) => {
      const v = values[f.key];
      if (v === "" || v === undefined) return;
      clean[f.key] = v;
    });
    try {
      if (editing) {
        await api.patch(`/records/${editing.id}`, { fields: clean });
        toast.success("Record updated");
      } else {
        await api.post(`/entity-types/${etId}/records`, { fields: clean });
        toast.success("Record created");
      }
      setOpen(false);
      await load();
    } catch (err) {
      const fe = extractFieldErrors(err);
      if (fe) {
        setErrors(fe);
        toast.error("Please fix the errors below");
      } else {
        toast.error(extractErrorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  const remove = async (rec) => {
    if (!window.confirm(`Delete record ${rec.record_number}?`)) return;
    try {
      await api.delete(`/records/${rec.id}`);
      toast.success("Record deleted");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
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
            <Button
              variant="outline"
              onClick={() => nav(`/entity-types/${etId}/fields`)}
              data-testid="go-fields-btn"
            >
              <Layers className="w-4 h-4 mr-1.5" /> Fields
            </Button>
            <Button
              onClick={openCreate}
              disabled={fields.length === 0}
              data-testid="new-record-btn"
            >
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
            icon={Layers}
            title="Define fields first"
            description="You need at least one field before you can create records."
            action={
              <Button onClick={() => nav(`/entity-types/${etId}/fields`)}>
                <Layers className="w-4 h-4 mr-1.5" /> Go to fields
              </Button>
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title="No records yet"
            description={`Create the first ${et?.name_singular || "record"} — the form below is generated from your field definitions.`}
            action={
              <Button onClick={openCreate} data-testid="empty-new-record">
                <Plus className="w-4 h-4 mr-1.5" /> New record
              </Button>
            }
            testId="records-empty"
          />
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="records-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-32">Record #</TableHead>
                  {columns.map((c) => (
                    <TableHead key={c.id}>{c.label}</TableHead>
                  ))}
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((r) => (
                  <TableRow key={r.id} data-testid={`record-row-${r.record_number}`}>
                    <TableCell className="font-mono text-xs text-primary">
                      {r.record_number}
                    </TableCell>
                    {columns.map((c) => (
                      <TableCell key={c.id} className="max-w-[280px] truncate">
                        {formatCellValue(c, r.fields?.[c.key])}
                      </TableCell>
                    ))}
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => openEdit(r)}
                          data-testid={`edit-record-${r.record_number}`}
                          aria-label="Edit"
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          onClick={() => remove(r)}
                          data-testid={`delete-record-${r.record_number}`}
                          aria-label="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </PageBody>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="sm:max-w-2xl max-h-[90vh] overflow-y-auto"
          data-testid="record-dialog"
        >
          <form onSubmit={submit}>
            <DialogHeader>
              <DialogTitle>
                {editing ? (
                  <span className="flex items-center gap-2">
                    Edit record
                    <span className="font-mono text-xs text-primary">
                      {editing.record_number}
                    </span>
                  </span>
                ) : (
                  `New ${et?.name_singular || "record"}`
                )}
              </DialogTitle>
            </DialogHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
              {fields.map((f) => (
                <div
                  key={f.id}
                  className={
                    f.type === "longtext" ||
                    f.type === "richtext" ||
                    f.type === "multi_select"
                      ? "md:col-span-2"
                      : ""
                  }
                >
                  <DynamicField
                    field={f}
                    value={values[f.key]}
                    onChange={(v) => setField(f.key, v)}
                    error={errors[`fields.${f.key}`]}
                  />
                </div>
              ))}
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
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
