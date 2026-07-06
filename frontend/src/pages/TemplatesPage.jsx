import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Package, Boxes, Cog, Users, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PageBody, PageHeader, EmptyState } from "@/components/PageChrome";

const ICON_MAP = { Package, Boxes, Cog, Users, Sparkles };

export default function TemplatesPage() {
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);
  const [applyTarget, setApplyTarget] = useState(null);
  const [policy, setPolicy] = useState("skip");
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    api.get("/templates").then((r) => setItems(r.data)).catch((e) =>
      toast.error(extractErrorMessage(e)),
    ).finally(() => setLoading(false));
  }, []);

  const openPreview = async (key) => {
    try {
      const r = await api.get(`/templates/${key}`);
      setPreview(r.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const apply = async () => {
    if (!applyTarget) return;
    setApplying(true);
    try {
      const r = await api.post(`/templates/${applyTarget.key}/apply`, {
        conflict_policy: policy,
      });
      toast.success(
        `Applied '${applyTarget.name}' — ${Object.entries(r.data.inserted || {})
          .map(([k, v]) => `${v} ${k.replace("_", " ")}`)
          .join(", ") || "no new items"}`,
      );
      setApplyTarget(null);
      setPreview(null);
      nav("/entity-types");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setApplying(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Starter Packs"
        subtitle="Pre-built Collections you can drop into your workspace in one click. Start with a template and rename anything you like."
        breadcrumbs={[{ label: "Workspace" }, { label: "Starter Packs" }]}
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : items.length === 0 ? (
          <EmptyState icon={Sparkles} title="No starter packs available" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {items.map((t) => {
              const Icon = ICON_MAP[t.icon] || Sparkles;
              return (
                <div
                  key={t.key}
                  className="rounded-lg border border-border bg-white p-5 flex flex-col hover:border-primary/40 transition-colors"
                  data-testid={`template-card-${t.key}`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-10 h-10 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                      <Icon className="w-5 h-5" />
                    </div>
                    <Badge variant="secondary" className="text-[10px] font-mono">
                      {t.entity_type_count} collections
                    </Badge>
                  </div>
                  <div className="text-base font-semibold">{t.name}</div>
                  <p className="text-sm text-muted-foreground mt-1 flex-1">
                    {t.description}
                  </p>
                  <div className="mt-4 flex gap-2">
                    <Button
                      variant="outline" size="sm"
                      onClick={() => openPreview(t.key)}
                      data-testid={`preview-template-${t.key}`}
                    >
                      Preview
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => { setApplyTarget(t); setPolicy("skip"); }}
                      data-testid={`apply-template-${t.key}`}
                    >
                      Use this starter pack <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </PageBody>

      {/* Preview drawer */}
      <Sheet open={!!preview} onOpenChange={(v) => !v && setPreview(null)}>
        <SheetContent className="w-[520px] overflow-y-auto" data-testid="template-preview">
          <SheetHeader>
            <SheetTitle>{preview?.name}</SheetTitle>
          </SheetHeader>
          {preview && (
            <div className="mt-6 space-y-5">
              <p className="text-sm text-muted-foreground">{preview.description}</p>
              {preview.entity_types.map((e) => (
                <div key={e.key} className="rounded-lg border border-border p-3">
                  <div className="flex items-center justify-between">
                    <div className="font-medium">{e.name_plural}</div>
                    <Badge variant="secondary" className="text-[10px] font-mono">
                      {e.key}
                    </Badge>
                  </div>
                  <div className="mt-2 space-y-0.5">
                    {e.fields.map((f) => (
                      <div
                        key={f.key}
                        className="text-xs font-mono text-muted-foreground flex gap-2"
                      >
                        <span className="text-foreground">{f.label}</span>
                        <span>{f.type}</span>
                        {f.required && <span className="text-primary">required</span>}
                        {f.unique && <span className="text-amber-700">unique</span>}
                      </div>
                    ))}
                  </div>
                  {e.categories?.length > 0 && (
                    <div className="mt-3 text-xs">
                      <span className="text-[10px] font-mono uppercase text-muted-foreground">
                        Categories:
                      </span>{" "}
                      <span>
                        {e.categories.map((c) => c.name).join(", ")}
                        {e.categories.some((c) => c.children?.length) && " (+ subcategories)"}
                      </span>
                    </div>
                  )}
                </div>
              ))}
              {preview.relationships?.length > 0 && (
                <div>
                  <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1.5">
                    Relationships
                  </div>
                  {preview.relationships.map((r) => (
                    <div key={r.key} className="text-sm font-mono">
                      {r.from_key} → {r.to_key} <span className="text-muted-foreground">({r.cardinality})</span>
                    </div>
                  ))}
                </div>
              )}
              <Button
                className="w-full"
                onClick={() => { setApplyTarget(preview); setPolicy("skip"); }}
                data-testid="preview-apply-btn"
              >
                Apply to this workspace
              </Button>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Apply confirm dialog */}
      <Dialog open={!!applyTarget} onOpenChange={(v) => !v && setApplyTarget(null)}>
        <DialogContent data-testid="apply-dialog">
          <DialogHeader>
            <DialogTitle>Use "{applyTarget?.name}"</DialogTitle>
          </DialogHeader>
          <div className="py-3 space-y-4">
            <p className="text-sm text-muted-foreground">
              On conflict with an existing Collection:
            </p>
            <RadioGroup value={policy} onValueChange={setPolicy}>
              <label className="flex items-start gap-2 cursor-pointer" data-testid="policy-skip">
                <RadioGroupItem value="skip" id="skip" className="mt-0.5" />
                <div>
                  <Label htmlFor="skip" className="font-medium">Skip</Label>
                  <p className="text-xs text-muted-foreground">
                    Keep the existing Collection and don't overwrite anything.
                  </p>
                </div>
              </label>
              <label className="flex items-start gap-2 cursor-pointer" data-testid="policy-rename">
                <RadioGroupItem value="rename" id="rename" className="mt-0.5" />
                <div>
                  <Label htmlFor="rename" className="font-medium">Rename</Label>
                  <p className="text-xs text-muted-foreground">
                    Create the Collection with a suffix like <code>_2</code>.
                  </p>
                </div>
              </label>
              <label className="flex items-start gap-2 cursor-pointer" data-testid="policy-error">
                <RadioGroupItem value="error" id="error" className="mt-0.5" />
                <div>
                  <Label htmlFor="error" className="font-medium">Abort</Label>
                  <p className="text-xs text-muted-foreground">
                    Fail the operation without creating anything.
                  </p>
                </div>
              </label>
            </RadioGroup>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setApplyTarget(null)}>Cancel</Button>
            <Button onClick={apply} disabled={applying} data-testid="submit-apply">
              {applying ? "Adding…" : "Add to workspace"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
