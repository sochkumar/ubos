import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowUp,
  ArrowDown,
  Layers,
  Plus,
  Trash2,
  ListChecks,
} from "lucide-react";
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
  DialogTrigger,
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
  label: "",
  key: "",
  type: "text",
  required: false,
  unique: false,
  sensitive: false,
  help_text: "",
  optionsText: "",
  min: "",
  max: "",
});

export default function FieldsPage() {
  const { id: etId } = useParams();
  const nav = useNavigate();
  const [et, setEt] = useState(null);
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [keyTouched, setKeyTouched] = useState(false);

  const load = async () => {
    try {
      const [etRes, flRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get(`/entity-types/${etId}/fields`),
      ]);
      setEt(etRes.data);
      setFields(flRes.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [etId]);

  const buildPayload = () => {
    const config = {};
    if (form.type === "dropdown" || form.type === "multi_select") {
      config.options = form.optionsText
        .split(/\n|,/)
        .map((s) => s.trim())
        .filter(Boolean);
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
      config,
    };
  };

  const submit = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post(`/entity-types/${etId}/fields`, buildPayload());
      toast.success(`Field '${form.label}' added`);
      setOpen(false);
      setForm(emptyForm());
      setKeyTouched(false);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const move = async (index, dir) => {
    const swap = index + dir;
    if (swap < 0 || swap >= fields.length) return;
    const next = fields.slice();
    [next[index], next[swap]] = [next[swap], next[index]];
    setFields(next);
    try {
      await api.post(`/entity-types/${etId}/fields/reorder`, {
        order: next.map((f) => f.id),
      });
    } catch (err) {
      toast.error(extractErrorMessage(err));
      load();
    }
  };

  const remove = async (f) => {
    if (!window.confirm(`Delete field "${f.label}"?`)) return;
    try {
      await api.delete(`/fields/${f.id}`);
      toast.success("Field deleted");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const groupedTypes = useMemo(() => {
    const map = {};
    FIELD_TYPES.forEach((t) => {
      map[t.group] = map[t.group] || [];
      map[t.group].push(t.value);
    });
    return map;
  }, []);

  const supportsOptions = form.type === "dropdown" || form.type === "multi_select";
  const supportsMinMax = form.type === "number" || form.type === "currency";

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Fields` : "Fields"}
        subtitle="Design the schema — these fields drive the dynamic form and validation."
        breadcrumbs={[
          { label: "Entity Types", to: "/entity-types" },
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
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button data-testid="new-field-btn">
                  <Plus className="w-4 h-4 mr-1.5" /> Add field
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg" data-testid="field-dialog">
                <form onSubmit={submit}>
                  <DialogHeader>
                    <DialogTitle>Add field</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
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
                        <Label>Key</Label>
                        <Input
                          data-testid="field-input-key"
                          className="font-mono"
                          value={form.key}
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
                        value={form.type}
                        onValueChange={(v) => setForm((f) => ({ ...f, type: v }))}
                      >
                        <SelectTrigger data-testid="field-input-type">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
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
                        </SelectContent>
                      </Select>
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
                        title="Sensitive fields are never exposed in public share links"
                      >
                        <Switch
                          checked={form.sensitive}
                          onCheckedChange={(v) =>
                            setForm((f) => ({ ...f, sensitive: v }))
                          }
                          data-testid="field-input-sensitive"
                        />
                        Sensitive
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
                    <Button type="submit" disabled={creating} data-testid="submit-field">
                      {creating ? "Adding…" : "Add field"}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : fields.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No fields defined yet"
            description="Add the first field to shape this entity. You can add text, numbers, dates, dropdowns, and more."
            action={
              <Button onClick={() => setOpen(true)} data-testid="empty-new-field">
                <Plus className="w-4 h-4 mr-1.5" /> Add first field
              </Button>
            }
            testId="fields-empty"
          />
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="fields-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Flags</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fields.map((f, i) => (
                  <TableRow key={f.id} data-testid={`field-row-${f.key}`}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {i + 1}
                    </TableCell>
                    <TableCell className="font-medium">{f.label}</TableCell>
                    <TableCell className="font-mono text-xs">{f.key}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="font-mono text-[10px]">
                        {f.type}
                      </Badge>
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
                          onClick={() => move(i, -1)}
                          disabled={i === 0}
                          data-testid={`field-up-${f.key}`}
                          aria-label="Move up"
                        >
                          <ArrowUp className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => move(i, 1)}
                          disabled={i === fields.length - 1}
                          data-testid={`field-down-${f.key}`}
                          aria-label="Move down"
                        >
                          <ArrowDown className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          onClick={() => remove(f)}
                          data-testid={`field-delete-${f.key}`}
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
    </>
  );
}
