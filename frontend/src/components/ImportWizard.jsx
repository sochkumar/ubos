import { useEffect, useRef, useState } from "react";
import {
  Upload, FileSpreadsheet, FileText, Check, ChevronRight, ChevronLeft,
  AlertCircle, Loader2, CheckCircle2, Download,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api, API_BASE, tokenStore } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";

const STEPS = [
  { key: "upload", label: "Upload" },
  { key: "preview", label: "Preview" },
  { key: "mapping", label: "Mapping" },
  { key: "options", label: "Options" },
  { key: "run", label: "Run" },
];

export function ImportWizard({ open, onOpenChange, entityTypeId, fields, onImported }) {
  const [step, setStep] = useState(0);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [selectedSheet, setSelectedSheet] = useState(null);
  const [mapping, setMapping] = useState({});
  const [matchBy, setMatchBy] = useState("");
  const [conflictPolicy, setConflictPolicy] = useState("error");
  const [autoCreateTags, setAutoCreateTags] = useState(true);
  const [autoCreateCats, setAutoCreateCats] = useState(false);
  const [plan, setPlan] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const pollerRef = useRef(null);

  const reset = () => {
    setStep(0);
    setFile(null); setPreview(null); setSelectedSheet(null);
    setMapping({}); setMatchBy(""); setConflictPolicy("error");
    setAutoCreateTags(true); setAutoCreateCats(false);
    setPlan(null); setJob(null); setBusy(false); setError(null);
    if (pollerRef.current) { clearInterval(pollerRef.current); pollerRef.current = null; }
  };

  useEffect(() => {
    if (!open) reset();
  }, [open]);

  // ── Step 1: upload → preview ─────────────────────────────
  const doPreview = async (fileObj, sheet) => {
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", fileObj);
      const r = await api.post(
        `/entity-types/${entityTypeId}/records/import/preview`,
        fd, { headers: { "Content-Type": "multipart/form-data" } },
      );
      setPreview(r.data);
      setSelectedSheet(r.data.selected_sheet || null);
      // Seed mapping from suggestions
      const seed = {};
      for (const [h, sug] of Object.entries(r.data.suggested_mapping || {})) {
        seed[h] = sug.field_key || null;
      }
      setMapping(seed);
      setStep(1);
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const onFilePicked = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    doPreview(f);
  };

  // ── Step 4: plan (dry-run) ───────────────────────────────
  const doPlan = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.post(`/entity-types/${entityTypeId}/records/import/plan`, {
        import_token: preview.import_token,
        mapping,
        options: {
          match_by: matchBy || null,
          conflict_policy: conflictPolicy,
          auto_create_tags: autoCreateTags,
          auto_create_categories: autoCreateCats,
          sheet_name: selectedSheet || undefined,
        },
      });
      setPlan(r.data);
      setStep(4);
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  // ── Step 5: execute + progress polling ────────────────────
  const doRun = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.post(`/entity-types/${entityTypeId}/records/import/execute`, {
        plan_id: plan.plan_id,
      });
      const jobId = r.data.job_id;
      setJob({ id: jobId, status: "queued", processed: 0, total: plan.total_rows });
      pollerRef.current = setInterval(async () => {
        try {
          const p = await api.get(`/imports/${jobId}/progress`);
          setJob(p.data);
          if (["completed", "failed", "cancelled"].includes(p.data.status)) {
            clearInterval(pollerRef.current);
            pollerRef.current = null;
            if (p.data.status === "completed") {
              toast.success(
                `Import complete · ${p.data.inserted} inserted, ${p.data.updated} updated, ${p.data.errors} errors`,
              );
              onImported?.();
            } else if (p.data.status === "failed") {
              toast.error("Import failed");
            }
          }
        } catch { /* ignore */ }
      }, 1000);
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const downloadErrorReport = async () => {
    if (!job?.error_report_url) return;
    try {
      const resp = await fetch(`${API_BASE}${job.error_report_url}`, {
        headers: { Authorization: `Bearer ${tokenStore.access}` },
      });
      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `import-errors-${job.id}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch { toast.error("Couldn't download error report"); }
  };

  const printableFields = (fields || []).filter((f) => !["image", "file", "relation"].includes(f.type));
  const requiredKeys = new Set(printableFields.filter((f) => f.required).map((f) => f.key));
  const mappedKeys = new Set(Object.values(mapping).filter(Boolean));
  const missingRequired = [...requiredKeys].filter((k) => !mappedKeys.has(k));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="import-wizard">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Import records
          </DialogTitle>
        </DialogHeader>

        {/* Stepper */}
        <div className="flex items-center gap-1 py-3 border-b border-border">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1 text-xs">
              <div className={`w-5 h-5 rounded-full flex items-center justify-center font-semibold text-[10px] ${
                step === i ? "bg-primary text-primary-foreground" :
                step > i ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
              }`}>
                {step > i ? <Check className="w-3 h-3" /> : i + 1}
              </div>
              <span className={step === i ? "font-medium" : "text-muted-foreground"}>{s.label}</span>
              {i < STEPS.length - 1 && <ChevronRight className="w-3 h-3 text-muted-foreground mx-1" />}
            </div>
          ))}
        </div>

        {error && (
          <div className="mt-3 p-3 rounded border border-destructive/30 bg-destructive/5 text-sm text-destructive flex items-start gap-2" data-testid="wizard-error">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* ── Step 1: Upload ── */}
        {step === 0 && (
          <div className="py-6 text-center" data-testid="wizard-step-upload">
            <label className="block cursor-pointer">
              <input
                type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={onFilePicked}
                className="hidden"
                data-testid="wizard-file-input"
              />
              <div className="border-2 border-dashed border-border rounded-lg p-10 hover:border-primary/60 transition-colors">
                {busy ? (
                  <>
                    <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin text-primary" />
                    <div className="text-sm">Parsing…</div>
                  </>
                ) : (
                  <>
                    <Upload className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
                    <div className="text-sm font-medium">Drop a CSV or Excel file, or click to browse</div>
                    <div className="text-xs text-muted-foreground mt-1">Max 10 MB · max 50,000 rows</div>
                  </>
                )}
              </div>
            </label>
          </div>
        )}

        {/* ── Step 2: Preview ── */}
        {step === 1 && preview && (
          <div className="py-4 space-y-3" data-testid="wizard-step-preview">
            <div className="flex items-center gap-2 flex-wrap text-sm">
              {preview.detected_format === "xlsx" ?
                <FileSpreadsheet className="w-4 h-4 text-primary" /> :
                <FileText className="w-4 h-4 text-primary" />}
              <span className="font-medium">{file?.name}</span>
              <Badge variant="secondary" className="text-[10px] uppercase font-mono">
                {preview.detected_format}
              </Badge>
              <Badge variant="secondary" className="text-[10px] font-mono">
                {preview.total_rows} rows
              </Badge>
              {preview.sheet_names?.length > 1 && (
                <Select value={selectedSheet} onValueChange={setSelectedSheet}>
                  <SelectTrigger className="h-7 w-40 text-xs" data-testid="wizard-sheet-picker">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {preview.sheet_names.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            {preview.warnings?.length > 0 && (
              <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 space-y-1">
                {preview.warnings.map((w, i) => (<div key={i}>⚠ {w}</div>))}
              </div>
            )}
            <div className="border border-border rounded overflow-x-auto max-h-64">
              <table className="w-full text-xs">
                <thead className="bg-muted/40">
                  <tr>{preview.headers.map((h) => (
                    <th key={h} className="text-left px-3 py-1.5 font-mono">{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {preview.preview_rows.map((row, i) => (
                    <tr key={i} className="border-t border-border">
                      {preview.headers.map((h) => (
                        <td key={h} className="px-3 py-1.5 whitespace-nowrap max-w-[240px] truncate">
                          {row[h] === null || row[h] === undefined ? "" : String(row[h])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Step 3: Column Mapping ── */}
        {step === 2 && preview && (
          <div className="py-4 space-y-2" data-testid="wizard-step-mapping">
            <p className="text-xs text-muted-foreground">
              Map each column from your file to a field on this entity. Choose &quot;Ignore this column&quot; to skip.
            </p>
            {missingRequired.length > 0 && (
              <div className="text-xs text-destructive bg-destructive/5 border border-destructive/30 rounded p-2">
                Unmapped required fields: <b>{missingRequired.join(", ")}</b>
              </div>
            )}
            <div className="rounded border border-border overflow-hidden">
              {preview.headers.map((h) => {
                const sug = preview.suggested_mapping[h];
                const val = mapping[h] || "";
                return (
                  <div key={h} className="flex items-center gap-3 px-3 py-2 border-b last:border-b-0 border-border">
                    <div className="w-40 shrink-0">
                      <div className="text-sm font-mono truncate">{h}</div>
                      {sug?.confidence > 0 && (
                        <div className="text-[10px] text-muted-foreground">
                          {sug.reason} · <b>{Math.round(sug.confidence * 100)}%</b>
                        </div>
                      )}
                    </div>
                    <ChevronRight className="w-3 h-3 text-muted-foreground" />
                    <Select
                      value={val || "__ignore__"}
                      onValueChange={(v) => setMapping((m) => ({ ...m, [h]: v === "__ignore__" ? null : v }))}
                    >
                      <SelectTrigger className="h-8 text-xs flex-1" data-testid={`wizard-map-${h}`}>
                        <SelectValue placeholder="Select field…" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__ignore__" className="text-muted-foreground italic">
                          Ignore this column
                        </SelectItem>
                        <SelectItem value="title">Title (item-level)</SelectItem>
                        <SelectItem value="tags">Tags (comma-separated)</SelectItem>
                        {printableFields.map((f) => (
                          <SelectItem key={f.key} value={f.key}>
                            {f.label} · <span className="text-muted-foreground font-mono">{f.key}</span>
                            {f.required && <span className="text-destructive"> *</span>}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Step 4: Options + Plan preview ── */}
        {step === 3 && (
          <div className="py-4 space-y-4" data-testid="wizard-step-options">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Match items by</Label>
                <Select value={matchBy || "__none__"} onValueChange={(v) => setMatchBy(v === "__none__" ? "" : v)}>
                  <SelectTrigger data-testid="wizard-matchby"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Always insert new</SelectItem>
                    <SelectItem value="record_number">Record number</SelectItem>
                    {printableFields.filter((f) => f.unique).map((f) => (
                      <SelectItem key={f.key} value={f.key}>{f.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm">On duplicate</Label>
                <Select value={conflictPolicy} onValueChange={setConflictPolicy}>
                  <SelectTrigger data-testid="wizard-conflict" disabled={!matchBy}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skip">Skip</SelectItem>
                    <SelectItem value="update">Update</SelectItem>
                    <SelectItem value="error">Error out</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex gap-6 flex-wrap pt-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <Switch checked={autoCreateTags} onCheckedChange={setAutoCreateTags} data-testid="wizard-autocreate-tags" />
                Auto-create tags
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <Switch checked={autoCreateCats} onCheckedChange={setAutoCreateCats} data-testid="wizard-autocreate-cats" />
                Auto-create categories
              </label>
            </div>
          </div>
        )}

        {/* ── Step 5: Plan review + run + progress ── */}
        {step === 4 && plan && !job && (
          <div className="py-4 space-y-3" data-testid="wizard-step-review">
            <div className="grid grid-cols-4 gap-2 text-center">
              <PlanStat label="Insert" value={plan.would_insert} color="text-emerald-600" />
              <PlanStat label="Update" value={plan.would_update} color="text-blue-600" />
              <PlanStat label="Skip" value={plan.would_skip} color="text-amber-600" />
              <PlanStat label="Error" value={plan.would_error} color="text-destructive" />
            </div>
            {plan.first_errors?.length > 0 && (
              <div>
                <div className="text-xs font-mono uppercase text-muted-foreground mb-1">First errors</div>
                <div className="max-h-48 overflow-y-auto rounded border border-border text-xs">
                  {plan.first_errors.map((e, i) => (
                    <div key={i} className="px-3 py-1.5 border-b border-border last:border-b-0">
                      <span className="font-mono text-muted-foreground">Row {e.row_idx + 1}:</span>{" "}
                      {e.errors.map((er, j) => (
                        <span key={j} className="mr-2">
                          <b>{er.field}</b> — {er.msg}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {plan.warnings?.length > 0 && (
              <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 space-y-1">
                {plan.warnings.map((w, i) => (<div key={i}>⚠ {w}</div>))}
              </div>
            )}
          </div>
        )}

        {step === 4 && job && (
          <div className="py-6 space-y-3" data-testid="wizard-progress">
            <div className="flex items-center gap-2">
              {job.status === "completed" ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> :
               job.status === "failed" ? <AlertCircle className="w-5 h-5 text-destructive" /> :
               <Loader2 className="w-5 h-5 animate-spin text-primary" />}
              <div className="text-sm font-medium">
                {job.status === "completed" ? "Import complete" :
                 job.status === "failed" ? "Import failed" :
                 `Running… ${job.processed}/${job.total_rows}`}
              </div>
            </div>
            <div className="h-2 bg-muted rounded overflow-hidden">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${job.total_rows ? (job.processed / job.total_rows) * 100 : 0}%` }}
                data-testid="wizard-progress-bar"
              />
            </div>
            <div className="grid grid-cols-4 gap-2 text-center text-xs">
              <PlanStat label="Inserted" value={job.inserted || 0} color="text-emerald-600" />
              <PlanStat label="Updated" value={job.updated || 0} color="text-blue-600" />
              <PlanStat label="Skipped" value={job.skipped || 0} color="text-amber-600" />
              <PlanStat label="Errors" value={job.errors || 0} color="text-destructive" />
            </div>
            {job.error_report_url && (
              <Button
                variant="outline" size="sm"
                onClick={downloadErrorReport}
                data-testid="wizard-download-errors"
              >
                <Download className="w-4 h-4 mr-1.5" /> Download error report
              </Button>
            )}
          </div>
        )}

        <DialogFooter>
          {step === 0 ? (
            <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          ) : job ? (
            <Button
              onClick={() => onOpenChange(false)}
              disabled={!["completed", "failed", "cancelled"].includes(job.status)}
              data-testid="wizard-close"
            >
              Close
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || busy}>
                <ChevronLeft className="w-4 h-4 mr-1" /> Back
              </Button>
              {step === 1 && (
                <Button onClick={() => setStep(2)} data-testid="wizard-next-mapping">
                  Continue <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              )}
              {step === 2 && (
                <Button
                  onClick={() => setStep(3)}
                  disabled={missingRequired.length > 0}
                  data-testid="wizard-next-options"
                >
                  Continue <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              )}
              {step === 3 && (
                <Button onClick={doPlan} disabled={busy} data-testid="wizard-preview-plan">
                  {busy ? "Analyzing…" : "Preview import"}
                </Button>
              )}
              {step === 4 && plan && !job && (
                <Button onClick={doRun} disabled={busy || plan.would_insert + plan.would_update === 0} data-testid="wizard-run">
                  Run import
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PlanStat({ label, value, color }) {
  return (
    <div className="rounded border border-border p-2 bg-white">
      <div className={`text-2xl font-semibold ${color}`}>{value}</div>
      <div className="text-[10px] font-mono uppercase text-muted-foreground">{label}</div>
    </div>
  );
}
