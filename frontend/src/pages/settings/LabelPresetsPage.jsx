import { useEffect, useState } from "react";
import {
  Plus, Trash2, Tag, Ruler, Pencil, Info,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { handleApiError } from "@/lib/errors";
import { useAuth } from "@/lib/auth";
import { PageBody, PageHeader, EmptyState } from "@/components/PageChrome";
import { Skeleton } from "@/components/ui/skeleton";

const DEFAULT_PRESET = {
  key: "",
  name: "",
  page_size: "A4",
  page_width_mm: "",
  page_height_mm: "",
  cols: 3,
  rows: 8,
  label_w_mm: 63.5,
  label_h_mm: 38.1,
  margin_top_mm: 15,
  margin_left_mm: 7.21,
  gutter_h_mm: 2.54,
  gutter_v_mm: 0,
};

export default function LabelPresetsPage() {
  const { activeOrgId, activeRole } = useAuth();
  const canManage = ["owner", "admin"].includes(activeRole);
  const [data, setData] = useState({ system: [], custom: [] });
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // preset or {new:true}

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/orgs/${activeOrgId}/label-presets`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (activeOrgId) load(); }, [activeOrgId]);

  const remove = async (p) => {
    if (!window.confirm(`Delete preset "${p.name}"? This can't be undone.`)) return;
    try {
      await api.delete(`/label-presets/${p.id}`);
      toast.success("Preset deleted");
      await load();
    } catch (e) { handleApiError(e); }
  };

  return (
    <>
      <PageHeader
        title="Label presets"
        subtitle="Built-in Avery sheets + your custom sizes."
        breadcrumbs={[{ label: "Settings" }, { label: "Label presets" }]}
        actions={
          canManage && (
            <Button onClick={() => setEditing({ ...DEFAULT_PRESET, new: true })} data-testid="new-preset-btn">
              <Plus className="w-4 h-4 mr-1.5" /> New preset
            </Button>
          )
        }
      />
      <PageBody>
        <section className="space-y-6">
          <div className="rounded-lg border border-border bg-white overflow-hidden">
            <div className="px-3 py-2 border-b border-border flex items-center gap-2">
              <div className="text-xs font-mono uppercase text-muted-foreground">Custom presets</div>
              <Badge variant="secondary" className="text-[10px]">{data.custom?.length || 0}</Badge>
            </div>
            {loading ? (
              <div className="p-3 space-y-2">
                {[1,2,3].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
              </div>
            ) : (data.custom?.length || 0) === 0 ? (
              <EmptyState
                icon={Ruler}
                title="No custom presets yet"
                description="Add sheet sizes that suit your printer or roll labeller."
                action={
                  canManage ? (
                    <Button onClick={() => setEditing({ ...DEFAULT_PRESET, new: true })}
                      data-testid="empty-new-preset-btn">
                      <Plus className="w-4 h-4 mr-1.5" /> Create your first preset
                    </Button>
                  ) : null
                }
                testId="empty-custom-presets"
              />
            ) : (
              <PresetTable rows={data.custom} onEdit={setEditing} onRemove={remove} canManage={canManage} />
            )}
          </div>

          <div className="rounded-lg border border-border bg-white overflow-hidden">
            <div className="px-3 py-2 border-b border-border flex items-center gap-2">
              <div className="text-xs font-mono uppercase text-muted-foreground">Built-in</div>
              <Badge variant="secondary" className="text-[10px]">{data.system?.length || 0}</Badge>
              <span className="ml-auto text-[10px] text-muted-foreground inline-flex items-center gap-1">
                <Info className="w-3 h-3" /> read-only
              </span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Preset</TableHead>
                  <TableHead>Page</TableHead>
                  <TableHead>Cols × Rows</TableHead>
                  <TableHead>Labels / page</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data.system || []).map((p) => (
                  <TableRow key={p.key} data-testid={`system-preset-${p.key}`}>
                    <TableCell>
                      <div className="font-medium">{p.name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{p.key}</div>
                    </TableCell>
                    <TableCell>{p.page_size}</TableCell>
                    <TableCell>{p.cols} × {p.rows}</TableCell>
                    <TableCell>{p.per_page}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      </PageBody>

      {editing && (
        <PresetEditor
          preset={editing}
          isNew={!!editing.new}
          orgId={activeOrgId}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </>
  );
}

function PresetTable({ rows, onEdit, onRemove, canManage }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Preset</TableHead>
          <TableHead>Page</TableHead>
          <TableHead>Grid</TableHead>
          <TableHead>Label (mm)</TableHead>
          <TableHead>Margins</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((p) => (
          <TableRow key={p.id} data-testid={`preset-row-${p.key}`}>
            <TableCell>
              <div className="font-medium flex items-center gap-1">
                <Tag className="w-3 h-3 text-muted-foreground" /> {p.name}
              </div>
              <div className="text-xs text-muted-foreground font-mono">{p.key}</div>
            </TableCell>
            <TableCell>
              {p.page_size}
              {p.page_size === "custom" && (
                <div className="text-xs text-muted-foreground">
                  {p.page_width_mm} × {p.page_height_mm} mm
                </div>
              )}
            </TableCell>
            <TableCell>{p.cols} × {p.rows}</TableCell>
            <TableCell>{p.label_w_mm} × {p.label_h_mm}</TableCell>
            <TableCell className="text-xs text-muted-foreground">
              top {p.margin_top_mm} · left {p.margin_left_mm}
            </TableCell>
            <TableCell className="text-right">
              {canManage && (
                <div className="flex justify-end gap-1">
                  <Button variant="ghost" size="icon" className="h-8 w-8"
                    onClick={() => onEdit(p)} data-testid={`edit-preset-${p.key}`}>
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() => onRemove(p)} data-testid={`delete-preset-${p.key}`}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function PresetEditor({ preset, isNew, orgId, onClose, onSaved }) {
  const [form, setForm] = useState({ ...preset });
  const [busy, setBusy] = useState(false);

  const upd = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    const body = {
      key: form.key?.trim(),
      name: form.name?.trim(),
      page_size: form.page_size,
      cols: Number(form.cols) || 1,
      rows: Number(form.rows) || 1,
      label_w_mm: Number(form.label_w_mm) || 0,
      label_h_mm: Number(form.label_h_mm) || 0,
      margin_top_mm: Number(form.margin_top_mm) || 0,
      margin_left_mm: Number(form.margin_left_mm) || 0,
      gutter_h_mm: Number(form.gutter_h_mm) || 0,
      gutter_v_mm: Number(form.gutter_v_mm) || 0,
    };
    if (form.page_size === "custom") {
      body.page_width_mm = Number(form.page_width_mm) || 0;
      body.page_height_mm = Number(form.page_height_mm) || 0;
    }
    setBusy(true);
    try {
      if (isNew) {
        await api.post(`/orgs/${orgId}/label-presets`, body);
        toast.success("Preset created");
      } else {
        // Strip immutable key when editing
        const { key, ...upd } = body;
        await api.patch(`/label-presets/${preset.id}`, upd);
        toast.success("Preset saved");
      }
      onSaved();
    } catch (e) { handleApiError(e); }
    finally { setBusy(false); }
  };

  // Live preview: naive scaled SVG of the label grid on the chosen page
  const pageWmm = form.page_size === "custom" ? Number(form.page_width_mm) || 210 :
                  form.page_size === "Letter" ? 215.9 : form.page_size === "A3" ? 297 : 210;
  const pageHmm = form.page_size === "custom" ? Number(form.page_height_mm) || 297 :
                  form.page_size === "Letter" ? 279.4 : form.page_size === "A3" ? 420 : 297;
  const scale = 220 / Math.max(pageWmm, pageHmm);
  const previewW = pageWmm * scale;
  const previewH = pageHmm * scale;

  const cols = Number(form.cols) || 1;
  const rows = Number(form.rows) || 1;
  const lw = Number(form.label_w_mm) || 0;
  const lh = Number(form.label_h_mm) || 0;
  const mt = Number(form.margin_top_mm) || 0;
  const ml = Number(form.margin_left_mm) || 0;
  const gx = Number(form.gutter_h_mm) || 0;
  const gy = Number(form.gutter_v_mm) || 0;

  const rects = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x = (ml + c * (lw + gx)) * scale;
      const y = (mt + r * (lh + gy)) * scale;
      rects.push({ x, y, w: lw * scale, h: lh * scale, k: `${r}-${c}` });
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl" data-testid="preset-editor">
        <DialogHeader>
          <DialogTitle>{isNew ? "New label preset" : `Edit ${preset.name}`}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-[1fr,220px] gap-6 py-2">
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Key</Label>
                <Input value={form.key} onChange={(e) => upd("key", e.target.value)}
                  placeholder="my-labels" disabled={!isNew}
                  data-testid="preset-key" />
              </div>
              <div>
                <Label className="text-sm">Name</Label>
                <Input value={form.name} onChange={(e) => upd("name", e.target.value)}
                  placeholder="Big Boxes" data-testid="preset-name" />
              </div>
            </div>
            <div>
              <Label className="text-sm">Page size</Label>
              <Select value={form.page_size} onValueChange={(v) => upd("page_size", v)}>
                <SelectTrigger data-testid="preset-page-size"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Letter">Letter (215.9 × 279.4 mm)</SelectItem>
                  <SelectItem value="A4">A4 (210 × 297 mm)</SelectItem>
                  <SelectItem value="A3">A3 (297 × 420 mm)</SelectItem>
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.page_size === "custom" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-sm">Page width (mm)</Label>
                  <Input type="number" value={form.page_width_mm}
                    onChange={(e) => upd("page_width_mm", e.target.value)}
                    data-testid="preset-page-w" />
                </div>
                <div>
                  <Label className="text-sm">Page height (mm)</Label>
                  <Input type="number" value={form.page_height_mm}
                    onChange={(e) => upd("page_height_mm", e.target.value)}
                    data-testid="preset-page-h" />
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Columns</Label>
                <Input type="number" min={1} max={20} value={form.cols}
                  onChange={(e) => upd("cols", e.target.value)}
                  data-testid="preset-cols" />
              </div>
              <div>
                <Label className="text-sm">Rows</Label>
                <Input type="number" min={1} max={40} value={form.rows}
                  onChange={(e) => upd("rows", e.target.value)}
                  data-testid="preset-rows" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Label width (mm)</Label>
                <Input type="number" value={form.label_w_mm}
                  onChange={(e) => upd("label_w_mm", e.target.value)}
                  data-testid="preset-label-w" />
              </div>
              <div>
                <Label className="text-sm">Label height (mm)</Label>
                <Input type="number" value={form.label_h_mm}
                  onChange={(e) => upd("label_h_mm", e.target.value)}
                  data-testid="preset-label-h" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Margin top (mm)</Label>
                <Input type="number" value={form.margin_top_mm}
                  onChange={(e) => upd("margin_top_mm", e.target.value)} />
              </div>
              <div>
                <Label className="text-sm">Margin left (mm)</Label>
                <Input type="number" value={form.margin_left_mm}
                  onChange={(e) => upd("margin_left_mm", e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Gutter horizontal (mm)</Label>
                <Input type="number" value={form.gutter_h_mm}
                  onChange={(e) => upd("gutter_h_mm", e.target.value)} />
              </div>
              <div>
                <Label className="text-sm">Gutter vertical (mm)</Label>
                <Input type="number" value={form.gutter_v_mm}
                  onChange={(e) => upd("gutter_v_mm", e.target.value)} />
              </div>
            </div>
          </div>

          <div>
            <div className="text-[10px] font-mono uppercase text-muted-foreground mb-2">Layout preview</div>
            <div
              className="rounded border border-border bg-muted/20 flex items-center justify-center"
              style={{ width: previewW + 8, height: previewH + 8 }}
              data-testid="preset-preview"
            >
              <svg width={previewW} height={previewH} className="bg-white border border-border">
                {rects.map((r) => (
                  <rect key={r.k} x={r.x} y={r.y} width={r.w} height={r.h}
                    fill="#0d948820" stroke="#0d9488" strokeWidth={0.5} />
                ))}
              </svg>
            </div>
            <div className="text-[10px] text-muted-foreground mt-2 font-mono">
              {cols} × {rows} = {cols * rows} labels/page
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy} data-testid="preset-save">
            {busy ? "Saving…" : isNew ? "Create preset" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
