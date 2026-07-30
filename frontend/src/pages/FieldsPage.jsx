import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  GripVertical,
  Layers,
  Pencil,
  Plus,
  Trash2,
  ListChecks,
  ImagePlus,
  X as XIcon,
} from "lucide-react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { toast } from "sonner";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { slugifyKey as slugify } from "@/lib/slugify";
import { useTerminology } from "@/lib/terminology";
import { useTabTitle } from "@/lib/tabs";

const FIELD_TYPES = [
  { value: "text", group: "Basic" },
  { value: "longtext", group: "Basic" },
  { value: "richtext", group: "Basic" },
  { value: "number", group: "Numeric" },
  { value: "currency", group: "Numeric" },
  { value: "boolean", group: "Basic" },
  { value: "date", group: "Date & time" },
  { value: "datetime", group: "Date & time" },
  { value: "dropdown", group: "Choice" },
  { value: "multi_select", group: "Choice" },
  { value: "email", group: "Contact" },
  { value: "phone", group: "Contact" },
  { value: "url", group: "Contact" },
  { value: "image", group: "Media (Phase 3)" },
  { value: "file", group: "Media (Phase 3)" },
  { value: "relation", group: "Media (Phase 3)" },
];

const emptyForm = () => ({
  id: null,
  label: "",
  key: "",
  type: "text",
  required: false,
  unique: false,
  sensitive: false,
  help_text: "",
  unit: "",
  custom_type_id: null,
  optionsText: "",
  optionIcons: {},
  min: "",
  max: "",
});

// Rebuild the editable form shape from a stored field definition.
const formFromField = (f) => ({
  id: f.id,
  label: f.label || "",
  key: f.key || "",
  type: f.type || "text",
  required: !!f.required,
  unique: !!f.unique,
  sensitive: !!f.sensitive,
  help_text: f.help_text || "",
  unit: f.unit || "",
  custom_type_id: f.custom_type_id || null,
  optionsText: Array.isArray(f.config?.options) ? f.config.options.join("\n") : "",
  optionIcons: f.config?.option_icons || {},
  min: f.config?.min ?? "",
  max: f.config?.max ?? "",
});

export default function FieldsPage() {
  const { id: etId } = useParams();
  const nav = useNavigate();
  const { t } = useTerminology();
  const [et, setEt] = useState(null);
  const [fields, setFields] = useState([]);
  const [library, setLibrary] = useState([]);
  const [customTypes, setCustomTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [keyTouched, setKeyTouched] = useState(false);
  // Custom-type mini-dialog
  const [typeOpen, setTypeOpen] = useState(false);
  const [typeForm, setTypeForm] = useState({ name: "", base_type: "number", unit: "" });
  const [savingType, setSavingType] = useState(false);

  const isEditing = !!form.id;

  useTabTitle(et ? `${et.name_plural} · Fields` : null, "layers");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const load = async () => {
    try {
      const [etRes, flRes, libRes, ctRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get(`/entity-types/${etId}/fields`),
        api.get(`/field-library`),
        api.get(`/field-types`),
      ]);
      setEt(etRes.data);
      setFields(flRes.data);
      setLibrary(Array.isArray(libRes.data) ? libRes.data : []);
      setCustomTypes(Array.isArray(ctRes.data) ? ctRes.data : []);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [etId]);

  const customTypeById = useMemo(
    () => Object.fromEntries(customTypes.map((c) => [c.id, c])),
    [customTypes],
  );

  // Apply a custom type to the field form: adopt its base type, unit, and any
  // default config (options / min / max).
  const applyCustomType = (ct) => {
    setForm((f) => ({
      ...f,
      type: ct.base_type,
      unit: ct.unit || "",
      custom_type_id: ct.id,
      optionsText: Array.isArray(ct.default_config?.options)
        ? ct.default_config.options.join("\n") : f.optionsText,
      min: ct.default_config?.min ?? f.min,
      max: ct.default_config?.max ?? f.max,
    }));
  };

  const onTypeChange = (v) => {
    if (v === "__create_type__") {
      setTypeForm({ name: "", base_type: "number", unit: "" });
      setTypeOpen(true);
      return;
    }
    if (v.startsWith("ct:")) {
      const ct = customTypeById[v.slice(3)];
      if (ct) applyCustomType(ct);
      return;
    }
    // built-in base type — clear any custom-type link
    setForm((f) => ({ ...f, type: v, custom_type_id: null }));
  };

  const submitType = async (e) => {
    e.preventDefault();
    setSavingType(true);
    try {
      const r = await api.post("/field-types", {
        name: typeForm.name,
        base_type: typeForm.base_type,
        unit: typeForm.unit || null,
      });
      toast.success(`Type '${typeForm.name}' created`);
      setCustomTypes((prev) => [...prev, r.data]);
      applyCustomType(r.data); // select it immediately
      setTypeOpen(false);
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setSavingType(false);
    }
  };

  // Library fields not already attached to this catalogue — offered for reuse.
  const attachable = useMemo(() => {
    const usedKeys = new Set(fields.map((f) => f.key));
    return library.filter((l) => !usedKeys.has(l.key));
  }, [library, fields]);

  const attachFromLibrary = async (lib) => {
    try {
      await api.post(`/entity-types/${etId}/fields/attach`, { library_id: lib.id });
      toast.success(`Added '${lib.label}' from your library`);
      setOpen(false);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const openForCreate = () => {
    setForm(emptyForm());
    setKeyTouched(false);
    setOpen(true);
  };

  const openForEdit = (f) => {
    setForm(formFromField(f));
    setKeyTouched(true); // don't auto-derive key from label while editing
    setOpen(true);
  };

  const buildPayload = () => {
    const config = {};
    if (form.type === "dropdown" || form.type === "multi_select") {
      const opts = form.optionsText
        .split(/\n|,/)
        .map((s) => s.trim())
        .filter(Boolean);
      config.options = opts;
      // keep only icons whose option still exists
      const icons = {};
      opts.forEach((o) => { if (form.optionIcons?.[o]) icons[o] = form.optionIcons[o]; });
      if (Object.keys(icons).length) config.option_icons = icons;
    }
    if (form.type === "number" || form.type === "currency") {
      if (form.min !== "") config.min = Number(form.min);
      if (form.max !== "") config.max = Number(form.max);
    }
    return {
      label: form.label,
      key: form.key,
      type: form.type,
      required: form.required,
      unique: form.unique,
      sensitive: form.sensitive,
      help_text: form.help_text || null,
      unit: form.unit || null,
      custom_type_id: form.custom_type_id || null,
      config,
    };
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEditing) {
        // key is immutable once created — never send it on edit.
        const { key, ...patch } = buildPayload();
        await api.patch(`/fields/${form.id}`, patch);
        toast.success(`Field '${form.label}' updated`);
      } else {
        await api.post(`/entity-types/${etId}/fields`, buildPayload());
        toast.success(`Field '${form.label}' added`);
      }
      setOpen(false);
      setForm(emptyForm());
      setKeyTouched(false);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const persistOrder = async (ordered) => {
    const prev = fields;
    setFields(ordered);
    try {
      await api.post(`/entity-types/${etId}/fields/reorder`, {
        order: ordered.map((f) => f.id),
      });
    } catch (err) {
      toast.error(extractErrorMessage(err));
      setFields(prev); // rollback on failure
    }
  };

  const onDragEnd = (e) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = fields.findIndex((f) => f.id === active.id);
    const to = fields.findIndex((f) => f.id === over.id);
    if (from === -1 || to === -1) return;
    persistOrder(arrayMove(fields, from, to));
  };

  const remove = async (f) => {
    if (!window.confirm(`Delete field "${f.label}"?\n\nThis action cannot be undone.`)) return;
    try {
      await api.delete(`/fields/${f.id}`);
      toast.success(t("field.deleted_toast", { fieldName: f.label }));
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const groupedTypes = useMemo(() => {
    const map = {};
    FIELD_TYPES.forEach((ft) => {
      map[ft.group] = map[ft.group] || [];
      map[ft.group].push(ft.value);
    });
    return map;
  }, []);

  const supportsOptions = form.type === "dropdown" || form.type === "multi_select";
  const supportsMinMax = form.type === "number" || form.type === "currency";
  const supportsUnit = ["number", "currency", "text", "longtext"].includes(form.type);
  const optionValues = supportsOptions
    ? form.optionsText.split(/\n|,/).map((s) => s.trim()).filter(Boolean)
    : [];

  const setOptionIcon = (value, mediaId) => {
    setForm((f) => {
      const next = { ...(f.optionIcons || {}) };
      if (mediaId) next[value] = mediaId; else delete next[value];
      return { ...f, optionIcons: next };
    });
  };

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Fields` : "Fields"}
        subtitle="Define what you'll fill in for each item. Drag the handle to reorder. Add text, numbers, dates, dropdowns, files, and more."
        breadcrumbs={[
          { label: "My Data", to: "/entity-types" },
          { label: et?.name_plural || "…" },
          { label: "Fields" },
        ]}
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => nav(`/entity-types/${etId}/records`)}
              data-testid="go-records-btn"
            >
              <ListChecks className="w-4 h-4 mr-1.5" /> Records
            </Button>
            <Button onClick={openForCreate} data-testid="new-field-btn">
              <Plus className="w-4 h-4 mr-1.5" /> Add field
            </Button>
          </div>
        }
      />

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="field-dialog">
          <form onSubmit={submit}>
            <DialogHeader>
              <DialogTitle>{isEditing ? "Edit field" : "Add field"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {!isEditing && attachable.length > 0 && (
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <div className="text-xs font-medium mb-2">
                    Reuse from your library{" "}
                    <span className="text-muted-foreground font-normal">— shared across catalogues</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto" data-testid="attach-library-list">
                    {attachable.map((l) => (
                      <button
                        key={l.id}
                        type="button"
                        onClick={() => attachFromLibrary(l)}
                        className="text-xs px-2 py-1 rounded-full border border-border bg-white hover:border-primary/60 hover:bg-primary/5 transition-colors"
                        data-testid={`attach-lib-${l.key}`}
                        title={`${l.type}${l.unit ? " · " + l.unit : ""}`}
                      >
                        + {l.label}
                      </button>
                    ))}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-2">Or create a new field below.</div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Label</Label>
                  <Input
                    data-testid="field-input-label"
                    value={form.label}
                    onChange={(e) => {
                      const v = e.target.value;
                      setForm((f) => ({
                        ...f,
                        label: v,
                        key: keyTouched ? f.key : slugify(v),
                      }));
                    }}
                    placeholder="SKU"
                    required
                  />
                </div>
                <div>
                  <Label>
                    Key{" "}
                    {isEditing && (
                      <span className="text-xs text-muted-foreground font-normal">
                        (can't change)
                      </span>
                    )}
                  </Label>
                  <Input
                    data-testid="field-input-key"
                    className="font-mono"
                    value={form.key}
                    disabled={isEditing}
                    onChange={(e) => {
                      setKeyTouched(true);
                      setForm((f) => ({ ...f, key: slugify(e.target.value) }));
                    }}
                    placeholder="sku"
                    required
                  />
                </div>
              </div>
              <div>
                <Label>Type</Label>
                <Select
                  value={form.custom_type_id ? `ct:${form.custom_type_id}` : form.type}
                  onValueChange={onTypeChange}
                >
                  <SelectTrigger data-testid="field-input-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {customTypes.length > 0 && (
                      <div>
                        <div className="px-2 py-1.5 text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
                          Your types
                        </div>
                        {customTypes.map((ct) => (
                          <SelectItem key={ct.id} value={`ct:${ct.id}`} data-testid={`field-type-ct-${ct.id}`}>
                            {ct.name}
                            <span className="text-muted-foreground">
                              {" "}· {ct.base_type}{ct.unit ? ` (${ct.unit})` : ""}
                            </span>
                          </SelectItem>
                        ))}
                      </div>
                    )}
                    {Object.entries(groupedTypes).map(([g, arr]) => (
                      <div key={g}>
                        <div className="px-2 py-1.5 text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
                          {g}
                        </div>
                        {arr.map((v) => (
                          <SelectItem key={v} value={v} data-testid={`field-type-${v}`}>
                            {v}
                          </SelectItem>
                        ))}
                      </div>
                    ))}
                    <div className="border-t border-border mt-1">
                      <SelectItem value="__create_type__" data-testid="field-type-create">
                        ＋ Create a field type…
                      </SelectItem>
                    </div>
                  </SelectContent>
                </Select>
                {form.custom_type_id && customTypeById[form.custom_type_id] && (
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Using your <b>{customTypeById[form.custom_type_id].name}</b> type
                    {" "}(base: {form.type}{form.unit ? `, unit ${form.unit}` : ""}).
                  </p>
                )}
              </div>

              {supportsOptions && (
                <div>
                  <Label>
                    Options{" "}
                    <span className="text-xs text-muted-foreground font-normal">
                      (one per line, or comma-separated)
                    </span>
                  </Label>
                  <Textarea
                    data-testid="field-input-options"
                    rows={3}
                    value={form.optionsText}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, optionsText: e.target.value }))
                    }
                    placeholder={"chair\ntable\nsofa"}
                  />
                </div>
              )}
              {supportsOptions && optionValues.length > 0 && (
                <OptionIconEditor
                  options={optionValues}
                  icons={form.optionIcons || {}}
                  onSet={setOptionIcon}
                />
              )}
              {supportsMinMax && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Min</Label>
                    <Input
                      data-testid="field-input-min"
                      type="number"
                      step="any"
                      value={form.min}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, min: e.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <Label>Max</Label>
                    <Input
                      data-testid="field-input-max"
                      type="number"
                      step="any"
                      value={form.max}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, max: e.target.value }))
                      }
                    />
                  </div>
                </div>
              )}

              {supportsUnit && (
                <div>
                  <Label>
                    Unit{" "}
                    <span className="text-xs text-muted-foreground font-normal">
                      (shown after the value, e.g. GSM)
                    </span>
                  </Label>
                  <Input
                    data-testid="field-input-unit"
                    value={form.unit}
                    onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))}
                    placeholder="GSM"
                  />
                </div>
              )}
              <div>
                <Label>Help text</Label>
                <Input
                  data-testid="field-input-help"
                  value={form.help_text}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, help_text: e.target.value }))
                  }
                />
              </div>
              <div className="flex gap-6 pt-1 flex-wrap">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <Switch
                    checked={form.required}
                    onCheckedChange={(v) =>
                      setForm((f) => ({ ...f, required: v }))
                    }
                    data-testid="field-input-required"
                  />
                  Required
                </label>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <Switch
                    checked={form.unique}
                    onCheckedChange={(v) =>
                      setForm((f) => ({ ...f, unique: v }))
                    }
                    data-testid="field-input-unique"
                  />
                  Unique
                </label>
                <label
                  className="flex items-center gap-2 text-sm cursor-pointer"
                  title="Private fields are never shown in public share links"
                >
                  <Switch
                    checked={form.sensitive}
                    onCheckedChange={(v) =>
                      setForm((f) => ({ ...f, sensitive: v }))
                    }
                    data-testid="field-input-sensitive"
                  />
                  Private
                </label>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="ghost"
                type="button"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={saving} data-testid="submit-field">
                {saving
                  ? isEditing ? "Saving…" : "Adding…"
                  : isEditing ? "Save changes" : "Add field"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Create-a-custom-type mini dialog */}
      <Dialog open={typeOpen} onOpenChange={setTypeOpen}>
        <DialogContent className="sm:max-w-sm" data-testid="field-type-dialog">
          <form onSubmit={submitType}>
            <DialogHeader>
              <DialogTitle>Create a field type</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <Label>Name</Label>
                <Input
                  data-testid="type-input-name"
                  value={typeForm.name}
                  onChange={(e) => setTypeForm((t) => ({ ...t, name: e.target.value }))}
                  placeholder="GSM"
                  required
                  autoFocus
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Base type</Label>
                  <Select
                    value={typeForm.base_type}
                    onValueChange={(v) => setTypeForm((t) => ({ ...t, base_type: v }))}
                  >
                    <SelectTrigger data-testid="type-input-base"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(groupedTypes).map(([g, arr]) => (
                        <div key={g}>
                          <div className="px-2 py-1.5 text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
                            {g}
                          </div>
                          {arr.map((v) => (
                            <SelectItem key={v} value={v}>{v}</SelectItem>
                          ))}
                        </div>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Unit</Label>
                  <Input
                    data-testid="type-input-unit"
                    value={typeForm.unit}
                    onChange={(e) => setTypeForm((t) => ({ ...t, unit: e.target.value }))}
                    placeholder="GSM"
                  />
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">
                A reusable type (e.g. GSM = number + unit “GSM”). Selecting it prefills a field's base type and unit.
              </p>
            </div>
            <DialogFooter>
              <Button variant="ghost" type="button" onClick={() => setTypeOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={savingType} data-testid="submit-type">
                {savingType ? "Creating…" : "Create type"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : fields.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No fields defined yet"
            description="Add the first field to shape this entity. You can add text, numbers, dates, dropdowns, and more."
            action={
              <Button onClick={openForCreate} data-testid="empty-new-field">
                <Plus className="w-4 h-4 mr-1.5" /> Add first field
              </Button>
            }
            testId="fields-empty"
          />
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="fields-table-wrap">
            {/* DndContext wraps the whole Table — dnd-kit injects hidden a11y
                nodes at its location, which must NOT land inside <tbody>. */}
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={onDragEnd}
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Label</TableHead>
                    <TableHead>Key</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Flags</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <SortableContext
                    items={fields.map((f) => f.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    {fields.map((f, i) => (
                      <SortableFieldRow
                        key={f.id}
                        field={f}
                        index={i}
                        typeName={f.custom_type_id ? customTypeById[f.custom_type_id]?.name : null}
                        onEdit={openForEdit}
                        onDelete={remove}
                      />
                    ))}
                  </SortableContext>
                </TableBody>
              </Table>
            </DndContext>
          </div>
        )}
      </PageBody>
    </>
  );
}

function SortableFieldRow({ field: f, index, typeName, onEdit, onDelete }) {
  const {
    attributes, listeners, setNodeRef, transform, transition, isDragging,
  } = useSortable({ id: f.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };
  return (
    <TableRow ref={setNodeRef} style={style} data-testid={`field-row-${f.key}`}>
      <TableCell className="w-8 pr-0">
        <button
          type="button"
          className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground touch-none p-1"
          data-testid={`field-drag-${f.key}`}
          aria-label="Drag to reorder"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="w-4 h-4" />
        </button>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {index + 1}
      </TableCell>
      <TableCell className="font-medium">{f.label}</TableCell>
      <TableCell className="font-mono text-xs">{f.key}</TableCell>
      <TableCell>
        <Badge variant="secondary" className="font-mono text-[10px]">
          {typeName || f.type}
        </Badge>
        {typeName && (
          <span className="ml-1 font-mono text-[10px] text-muted-foreground">{f.type}</span>
        )}
        {f.unit && (
          <span className="ml-1 font-mono text-[10px] text-muted-foreground">· {f.unit}</span>
        )}
      </TableCell>
      <TableCell className="space-x-1">
        {f.required && (
          <Badge className="bg-primary/10 text-primary hover:bg-primary/10 border-transparent">
            required
          </Badge>
        )}
        {f.unique && (
          <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100 border-transparent">
            unique
          </Badge>
        )}
        {f.sensitive && (
          <Badge
            className="bg-rose-100 text-rose-800 hover:bg-rose-100 border-transparent"
            data-testid={`field-badge-sensitive-${f.key}`}
            title="Hidden from public share links"
          >
            sensitive
          </Badge>
        )}
      </TableCell>
      <TableCell className="text-right">
        <div className="inline-flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onEdit(f)}
            data-testid={`field-edit-${f.key}`}
            aria-label="Edit field"
          >
            <Pencil className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={() => onDelete(f)}
            data-testid={`field-delete-${f.key}`}
            aria-label="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

// Backend origin (strip the trailing /api) for building media preview URLs.
const MEDIA_ORIGIN = (api.defaults?.baseURL || "").replace(/\/api\/?$/, "");

/**
 * Per-option icon uploader for dropdown / multi_select fields. Lets the user
 * attach an image to each option value (e.g. End Use → curtain / blind /
 * upholstery). Icons print on labels when "Show icons" is on in the Print dialog.
 */
function OptionIconEditor({ options, icons, onSet }) {
  const [previews, setPreviews] = useState({}); // value -> object/URL
  const [busy, setBusy] = useState({});

  // Resolve previews for options that already have a stored media id.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (const v of options) {
        const mid = icons[v];
        if (!mid || previews[v]) continue;
        try {
          const r = await api.get(`/media/${mid}/file`);
          const url = r.data?.url || "";
          const src = url.startsWith("http") ? url : MEDIA_ORIGIN + url;
          if (!cancelled) setPreviews((p) => ({ ...p, [v]: src }));
        } catch { /* ignore */ }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.join("|"), JSON.stringify(icons)]);

  const upload = async (value, file) => {
    if (!file) return;
    setPreviews((p) => ({ ...p, [value]: URL.createObjectURL(file) }));
    setBusy((b) => ({ ...b, [value]: true }));
    try {
      const fd = new FormData();
      fd.append("files", file);
      fd.append("role", "field");
      const r = await api.post("/media/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const created = Array.isArray(r.data) ? r.data[0] : r.data;
      const mid = created?.id || created?._id;
      if (mid) onSet(value, mid);
    } catch (err) {
      toast.error(extractErrorMessage(err));
      setPreviews((p) => { const n = { ...p }; delete n[value]; return n; });
    } finally {
      setBusy((b) => ({ ...b, [value]: false }));
    }
  };

  return (
    <div>
      <Label>
        Option icons{" "}
        <span className="text-xs text-muted-foreground font-normal">
          (optional — printed on labels when “Show icons” is on)
        </span>
      </Label>
      <div className="mt-1.5 space-y-1.5" data-testid="option-icon-editor">
        {options.map((v) => (
          <div key={v} className="flex items-center gap-2 text-sm">
            <div className="w-7 h-7 rounded border border-border bg-muted/40 flex items-center justify-center overflow-hidden shrink-0">
              {previews[v] ? (
                <img src={previews[v]} alt="" className="w-full h-full object-contain" />
              ) : (
                <ImagePlus className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </div>
            <span className="flex-1 truncate">{v}</span>
            {icons[v] && (
              <button
                type="button"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => { onSet(v, null); setPreviews((p) => { const n = { ...p }; delete n[v]; return n; }); }}
                data-testid={`option-icon-remove-${v}`}
                aria-label="Remove icon"
              >
                <XIcon className="w-3.5 h-3.5" />
              </button>
            )}
            <label className="text-xs text-primary hover:underline cursor-pointer shrink-0">
              {busy[v] ? "Uploading…" : icons[v] ? "Replace" : "Upload"}
              <input
                type="file"
                accept="image/*"
                className="hidden"
                data-testid={`option-icon-upload-${v}`}
                onChange={(e) => upload(v, e.target.files?.[0])}
              />
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}
