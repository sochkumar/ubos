import { useEffect, useState } from "react";
import { Printer, X } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";

const CODE_MODES = [
  { value: "qr_and_barcode", label: "QR + Code128" },
  { value: "qr_only", label: "QR only" },
  { value: "barcode_only", label: "Code128 only" },
];

/**
 * PrintLabelsDialog
 * ─────────────────
 * Props:
 *   open, onOpenChange
 *   recordIds     : string[]  (required — the batch to print)
 *   fields        : optional list of field defs to power the "extra fields" picker
 *
 * Downloads the generated PDF as an attachment.
 */
export function PrintLabelsDialog({ open, onOpenChange, recordIds, fields = [] }) {
  const [presets, setPresets] = useState([]);
  const [preset, setPreset] = useState("avery_5160");
  const [codeMode, setCodeMode] = useState("qr_and_barcode");
  const [showTitle, setShowTitle] = useState(true);
  const [showRecNum, setShowRecNum] = useState(true);
  const [showFields, setShowFields] = useState([]);
  const [copies, setCopies] = useState(1);
  const [startPos, setStartPos] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/labels/presets")
      .then((r) => setPresets(r.data || []))
      .catch(() => { /* ignore */ });
  }, [open]);

  const currentPreset = presets.find((p) => p.key === preset);
  const perPage = currentPreset?.per_page || 30;
  const totalLabels = (recordIds?.length || 0) * copies;
  const pageCount = Math.max(1, Math.ceil((totalLabels + startPos) / perPage));

  const toggleField = (k) => {
    setShowFields((prev) =>
      prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k].slice(0, 3),
    );
  };

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        record_ids: recordIds,
        config: {
          preset,
          code_mode: codeMode,
          show_title: showTitle,
          show_record_number: showRecNum,
          show_fields: showFields,
          copies_per_record: Math.max(1, Number(copies) || 1),
          start_position: Math.max(0, Number(startPos) || 0),
        },
      };
      const r = await api.post("/records/labels", body, { responseType: "blob" });
      const blob = new Blob([r.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `labels-${preset}-${Date.now()}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded ${totalLabels} label${totalLabels === 1 ? "" : "s"}`);
      onOpenChange(false);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally { setBusy(false); }
  };

  // Show only Phase-4-friendly field types
  const printableFields = fields.filter((f) =>
    ["text", "number", "currency", "email", "phone", "url", "date", "dropdown"].includes(f.type)
    && !f.sensitive,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl" data-testid="print-labels-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Printer className="w-4 h-4" />
            Print labels
            <span className="ml-1 text-xs text-muted-foreground font-normal">
              {recordIds?.length || 0} record{(recordIds?.length || 0) === 1 ? "" : "s"}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-5 py-2">
          {/* Preset */}
          <div className="col-span-2">
            <Label className="text-sm">Label sheet</Label>
            <Select value={preset} onValueChange={setPreset}>
              <SelectTrigger data-testid="labels-preset"><SelectValue /></SelectTrigger>
              <SelectContent>
                {presets.map((p) => (
                  <SelectItem key={p.key} value={p.key}>
                    {p.label} · {p.cols}×{p.rows} · {p.page}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Code mode */}
          <div>
            <Label className="text-sm">Code mode</Label>
            <Select value={codeMode} onValueChange={setCodeMode}>
              <SelectTrigger data-testid="labels-code-mode"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CODE_MODES.map((m) => (
                  <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Copies + start */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-sm">Copies</Label>
              <Input
                type="number" min={1} max={100} value={copies}
                onChange={(e) => setCopies(e.target.value)}
                data-testid="labels-copies"
              />
            </div>
            <div>
              <Label className="text-sm">Start slot</Label>
              <Input
                type="number" min={0} max={perPage - 1} value={startPos}
                onChange={(e) => setStartPos(e.target.value)}
                data-testid="labels-start-pos"
              />
            </div>
          </div>

          {/* Toggles */}
          <div className="col-span-2 flex gap-6 pt-1">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={showTitle} onCheckedChange={setShowTitle} data-testid="labels-show-title" />
              Show title
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={showRecNum} onCheckedChange={setShowRecNum} data-testid="labels-show-recnum" />
              Show record #
            </label>
          </div>

          {/* Extra fields */}
          {printableFields.length > 0 && (
            <div className="col-span-2">
              <Label className="text-sm">
                Extra fields on label <span className="text-muted-foreground text-xs">(max 3)</span>
              </Label>
              <div className="flex flex-wrap gap-1.5 mt-1.5" data-testid="labels-extra-fields">
                {printableFields.map((f) => {
                  const on = showFields.includes(f.key);
                  return (
                    <button
                      key={f.key}
                      type="button"
                      onClick={() => toggleField(f.key)}
                      className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                        on
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-white text-foreground border-border hover:border-primary/60"
                      }`}
                      data-testid={`labels-field-${f.key}`}
                    >
                      {on && <X className="w-3 h-3 inline -mt-0.5 mr-1" />}
                      {f.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Preview stats */}
          <div className="col-span-2 rounded-md bg-muted/40 p-3 text-xs">
            <div className="flex flex-wrap gap-4">
              <div><span className="text-muted-foreground">Records:</span> <b>{recordIds?.length || 0}</b></div>
              <div><span className="text-muted-foreground">Copies each:</span> <b>{copies}</b></div>
              <div><span className="text-muted-foreground">Total labels:</span> <b>{totalLabels}</b></div>
              <div><span className="text-muted-foreground">Labels/page:</span> <b>{perPage}</b></div>
              <div><span className="text-muted-foreground">Pages:</span> <b>{pageCount}</b></div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !(recordIds?.length)} data-testid="labels-submit">
            <Printer className="w-4 h-4 mr-1.5" />
            {busy ? "Generating…" : "Download PDF"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
