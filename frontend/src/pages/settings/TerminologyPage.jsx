import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { RefreshCcw, RotateCcw, Save, Undo2, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DEFAULT_TERMS, TERM_GROUPS, useTerminology, t as tPure,
} from "@/lib/terminology";
import { useAuth } from "@/lib/auth";
import { extractErrorMessage } from "@/lib/errors";

export default function TerminologyPage() {
  const { activeRole } = useAuth();
  const { overrides, saveOverrides, resetOverrides, loading } = useTerminology();
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  const canEdit = activeRole === "owner" || activeRole === "admin";

  // Hydrate the draft whenever server-side overrides change.
  useEffect(() => { setDraft(overrides || {}); }, [overrides]);

  const dirty = useMemo(() => {
    // Anything different from `overrides` counts as dirty.
    const keys = new Set([...Object.keys(draft), ...Object.keys(overrides || {})]);
    for (const k of keys) {
      const dv = (draft[k] ?? "").trim();
      const ov = (overrides?.[k] ?? "").trim();
      if (dv !== ov) return true;
    }
    return false;
  }, [draft, overrides]);

  const onChange = (key, value) => {
    setDraft((prev) => {
      const next = { ...prev };
      const trimmed = (value || "").trim();
      if (!trimmed) {
        delete next[key];   // empty = revert to default
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const revertRow = (key) => {
    setDraft((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const save = async () => {
    if (!canEdit) return;
    setSaving(true);
    try {
      // Send only trimmed non-empty overrides.
      const clean = Object.fromEntries(
        Object.entries(draft)
          .map(([k, v]) => [k, (v || "").trim()])
          .filter(([, v]) => v),
      );
      await saveOverrides(clean);
      toast.success("Terminology saved");
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const resetAll = async () => {
    if (!canEdit) return;
    setResetting(true);
    try {
      await resetOverrides();
      setDraft({});
      toast.success("Reverted all terms to defaults");
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5" data-testid="terminology-page">
      <header className="flex items-start gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Terminology</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Rename how your team refers to core concepts. For example, a bakery
            might rename <b>Collections</b> to <b>Menu Sections</b> and{" "}
            <b>Items</b> to <b>Menu Items</b>. Changes are visible to everyone
            in your workspace and take effect immediately.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline" size="sm"
            onClick={resetAll}
            disabled={!canEdit || resetting || Object.keys(overrides || {}).length === 0}
            data-testid="terminology-reset-all"
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
            Reset all
          </Button>
          <Button
            size="sm"
            onClick={save}
            disabled={!canEdit || saving || !dirty}
            data-testid="terminology-save"
          >
            <Save className="w-3.5 h-3.5 mr-1.5" />
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </header>

      {!canEdit && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" data-testid="terminology-readonly-banner">
          Only owners and admins can edit terminology. You can view current
          values below.
        </div>
      )}

      {loading && (
        <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground flex items-center gap-2">
          <RefreshCcw className="w-3.5 h-3.5 animate-spin" /> Loading current terms…
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start">
        {/* ─── Term table ─── */}
        <div className="space-y-6" data-testid="terminology-groups">
          {TERM_GROUPS.map((group) => (
            <section
              key={group.label}
              className="rounded-lg border border-border bg-white overflow-hidden"
              data-testid={`terminology-group-${group.label.toLowerCase().replace(/\W+/g, "-")}`}
            >
              <header className="px-4 py-3 border-b border-border bg-muted/20">
                <div className="text-sm font-semibold">{group.label}</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">{group.hint}</div>
              </header>
              <div className="divide-y divide-border">
                {group.keys.map((key) => {
                  const def = DEFAULT_TERMS[key] ?? key;
                  const val = draft[key] ?? "";
                  const overridden = !!val && val.trim() && val.trim() !== def;
                  return (
                    <div
                      key={key}
                      className="grid grid-cols-1 md:grid-cols-[220px_140px_1fr_36px] gap-3 items-center px-4 py-2.5"
                      data-testid={`terminology-row-${key}`}
                    >
                      <div>
                        <div className="text-xs font-mono text-muted-foreground truncate" title={key}>
                          {key}
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground italic truncate" title={def}>
                        {def}
                      </div>
                      <Input
                        value={val}
                        onChange={(e) => onChange(key, e.target.value)}
                        placeholder={def}
                        disabled={!canEdit}
                        className={`h-8 text-sm ${overridden ? "border-primary/50" : ""}`}
                        data-testid={`terminology-input-${key}`}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0"
                        onClick={() => revertRow(key)}
                        disabled={!canEdit || (!val && !overrides?.[key])}
                        title="Revert to default"
                        data-testid={`terminology-revert-${key}`}
                      >
                        <Undo2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        {/* ─── Live preview ─── */}
        <aside
          className="rounded-lg border border-border bg-white sticky top-6"
          data-testid="terminology-preview"
        >
          <header className="px-4 py-3 border-b border-border bg-muted/20 flex items-center gap-2">
            <Eye className="w-3.5 h-3.5 text-primary" />
            <div className="text-sm font-semibold">Preview</div>
          </header>
          <div className="p-4 space-y-3 text-sm">
            <PreviewSnippet label="Sidebar heading">
              {tPure("nav.data", {}, draft)}
            </PreviewSnippet>
            <PreviewSnippet label="Primary CTA">
              + {tPure("collection.new", {}, draft)}
            </PreviewSnippet>
            <PreviewSnippet label="Records page — with a collection called Product">
              <span className="font-medium">{tPure("record.new", { collectionName: "Product" }, draft)}</span>
            </PreviewSnippet>
            <PreviewSnippet label="Field builder helper">
              {tPure("field.help", {}, draft)}
            </PreviewSnippet>
            <PreviewSnippet label="Empty state — no collections yet">
              You don&apos;t have any {tPure("collection.plural", {}, draft).toLowerCase()} yet.
            </PreviewSnippet>
            <PreviewSnippet label="Share link visibility">
              {tPure("share.public", {}, draft)} · {tPure("share.password", {}, draft)}
            </PreviewSnippet>
          </div>
          <div className="px-4 py-3 border-t border-border text-[11px] text-muted-foreground">
            Preview updates as you type. Save to apply for everyone in your workspace.
          </div>
        </aside>
      </div>
    </div>
  );
}

function PreviewSnippet({ label, children }) {
  return (
    <div>
      <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1 tracking-wider">
        {label}
      </div>
      <div className="rounded border border-dashed border-border bg-muted/20 px-3 py-1.5 text-sm">
        {children}
      </div>
    </div>
  );
}
