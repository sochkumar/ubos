/**
 * Phase 7 Sub-pass B — Onboarding wizard.
 *
 * Replaces the previous 2-step (create org → optional template) flow with a
 * business-type-first, 3-step visual picker:
 *
 *   Step 1 — Pick a business type (or "Something else" to skip)
 *   Step 2 — Name the workspace (auto-suggested from the picked type)
 *   Step 3 — Confirm & create (one button)
 *
 * On confirm, the sequence is:
 *   1. POST /orgs                      → create the org
 *   2. POST /templates/{key}/apply     → seed collections + fields + sample
 *                                        records + terminology overlay
 *      (skipped for "Something else")
 *   3. refreshMe()                     → hydrate the auth store with the new
 *                                        org and its role
 *   4. navigate("/dashboard")          → land the user on Home with a toast
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Sparkles, ArrowRight, ArrowLeft, Check, Loader2, Skull,
  Boxes, LayoutGrid,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { useAuth } from "@/lib/auth";
import { INDUSTRY_PRESETS, findPresetByKey } from "@/lib/industryPresets";

/* helpers */
const orgSlug = (name) =>
  (name || "")
    .toLowerCase().trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);

const SKIP_KEY = "__skip__";

/* ─────────────────── stepper ─────────────────── */
function Stepper({ step }) {
  const steps = ["Pick a business type", "Name your workspace", "Ready to go"];
  return (
    <div className="flex items-center gap-2 mb-6" data-testid="wizard-stepper">
      {steps.map((label, i) => {
        const idx = i + 1;
        const done = step > idx;
        const active = step === idx;
        return (
          <div key={label} className="flex items-center gap-2 flex-1">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0 ${
                done ? "bg-primary text-primary-foreground" :
                active ? "bg-primary/10 text-primary border border-primary" :
                "bg-muted text-muted-foreground"
              }`}
              data-testid={`wizard-step-badge-${idx}`}
            >
              {done ? <Check className="w-3 h-3" /> : idx}
            </div>
            <div className={`text-[13px] ${active ? "font-medium" : "text-muted-foreground"}`}>
              {label}
            </div>
            {idx < steps.length && (
              <div className={`flex-1 h-px ${done ? "bg-primary/50" : "bg-border"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────── step 1: business type ─────────────────── */
function StepPickType({ onPick }) {
  return (
    <div data-testid="wizard-step-1">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">What kind of business?</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Pick the closest match — we'll pre-fill your workspace with a starter
          setup you can customise later.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {INDUSTRY_PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            data-testid={`wizard-preset-${p.key}`}
            onClick={() => onPick(p.key)}
            className="group text-left border border-border rounded-xl p-4 bg-white hover:border-primary/60 hover:shadow-md transition-all"
          >
            <div className="text-3xl mb-2">{p.emoji}</div>
            <div className="font-medium text-[15px] group-hover:text-primary transition-colors">
              {p.label}
            </div>
            <div className="text-xs text-muted-foreground mt-1 line-clamp-2">
              {p.tagline}
            </div>
          </button>
        ))}
        <button
          type="button"
          data-testid="wizard-preset-skip"
          onClick={() => onPick(SKIP_KEY)}
          className="group text-left border border-dashed border-border rounded-xl p-4 bg-muted/20 hover:border-primary/40 hover:bg-muted/40 transition-all"
        >
          <div className="text-3xl mb-2">🎨</div>
          <div className="font-medium text-[15px]">Something else</div>
          <div className="text-xs text-muted-foreground mt-1">
            An empty workspace. Design your own Collections from scratch.
          </div>
        </button>
      </div>
    </div>
  );
}

/* ─────────────────── step 2: name workspace ─────────────────── */
function StepName({ preset, name, setName, slug, setSlug, slugTouched, setSlugTouched, onBack, onNext }) {
  const isSkip = !preset;
  const collections = preset?.collections || [];
  return (
    <div data-testid="wizard-step-2" className="max-w-xl">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Name your workspace</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {isSkip
            ? "You can rename this any time from Settings."
            : `We'll create a workspace with these ${preset.label.toLowerCase()} collections.`}
        </p>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); onNext(); }}
        className="space-y-4"
      >
        <div className="space-y-1.5">
          <Label htmlFor="wiz-name">Workspace name</Label>
          <Input
            id="wiz-name"
            data-testid="wizard-name-input"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slugTouched) setSlug(orgSlug(e.target.value));
            }}
            placeholder="My Bakery"
            autoFocus
            required
            minLength={1}
            maxLength={120}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="wiz-slug">URL slug <span className="text-muted-foreground font-normal text-xs">(optional)</span></Label>
          <Input
            id="wiz-slug"
            data-testid="wizard-slug-input"
            value={slug}
            onChange={(e) => { setSlugTouched(true); setSlug(e.target.value.toLowerCase()); }}
            placeholder="my-bakery"
            pattern="[a-z0-9\-]+"
            maxLength={64}
          />
          <p className="text-[11px] text-muted-foreground">Auto-derived from the name unless you change it.</p>
        </div>

        {collections.length > 0 && (
          <div className="rounded-lg border border-border bg-muted/30 p-3.5 space-y-2" data-testid="wizard-collection-preview">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
              <Boxes className="w-3.5 h-3.5" />
              You'll start with
            </div>
            <div className="flex flex-wrap gap-1.5">
              {collections.map((c) => (
                <span key={c} className="px-2 py-0.5 rounded-full text-[11px] bg-white border border-border text-foreground">
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex justify-between pt-2">
          <Button type="button" variant="ghost" onClick={onBack} data-testid="wizard-back-1">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <Button type="submit" disabled={!name.trim()} data-testid="wizard-next-2">
            Continue <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </form>
    </div>
  );
}

/* ─────────────────── step 3: confirm & create ─────────────────── */
function StepConfirm({ preset, name, slug, onBack, onCreate, busy }) {
  const isSkip = !preset;
  return (
    <div data-testid="wizard-step-3" className="max-w-xl">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Ready to go</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Review your choices and create the workspace.
        </p>
      </div>

      <div className="border border-border rounded-xl bg-white p-4 space-y-3">
        <Row label="Workspace name" value={name} />
        <Row label="URL slug" value={slug || orgSlug(name)} mono />
        <Row
          label="Business type"
          value={
            preset ? (
              <span className="inline-flex items-center gap-1.5">
                <span>{preset.emoji}</span> {preset.label}
              </span>
            ) : (
              <span className="text-muted-foreground">Blank workspace</span>
            )
          }
        />
        {!isSkip && (
          <>
            <Row
              label="Starter collections"
              value={
                <div className="flex flex-wrap gap-1">
                  {preset.collections.map((c) => (
                    <span key={c} className="px-1.5 py-0.5 rounded text-[11px] bg-muted">
                      {c}
                    </span>
                  ))}
                </div>
              }
            />
            <Row
              label="Terminology"
              value={
                <span className="text-xs text-muted-foreground">
                  We'll say “{preset.terminology["record.singular"] || "Item"}” instead of
                  “Record”, and “{preset.terminology["collection.singular"] || "Collection"}”
                  instead of “Entity Type”. You can tweak these in Settings.
                </span>
              }
            />
          </>
        )}
      </div>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack} disabled={busy} data-testid="wizard-back-2">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back
        </Button>
        <Button type="button" onClick={onCreate} disabled={busy} data-testid="wizard-create-btn">
          {busy ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating…
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4 mr-2" /> Create my workspace
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="text-xs font-mono uppercase text-muted-foreground w-32 shrink-0 pt-0.5">
        {label}
      </div>
      <div className={`flex-1 text-sm ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}

/* ─────────────────── page ─────────────────── */
export default function OnboardingPage() {
  const { orgs, applyTokens, refreshMe } = useAuth();
  const nav = useNavigate();

  const [step, setStep] = useState(1);
  const [presetKey, setPresetKey] = useState(null); // null | "bakery_store" | SKIP_KEY
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [busy, setBusy] = useState(false);

  const preset = useMemo(
    () => (presetKey && presetKey !== SKIP_KEY ? findPresetByKey(presetKey) : null),
    [presetKey],
  );

  // If the user already has orgs (came back to the page unnecessarily), bounce them
  useEffect(() => {
    if (orgs.length > 0) nav("/dashboard", { replace: true });
  }, [orgs, nav]);

  const pickType = (key) => {
    setPresetKey(key);
    // Auto-suggest name from the preset if the user hasn't typed one yet
    if (key !== SKIP_KEY && !name) {
      const p = findPresetByKey(key);
      if (p) {
        setName(p.suggested_name);
        setSlug(orgSlug(p.suggested_name));
      }
    }
    setStep(2);
  };

  const create = async () => {
    setBusy(true);
    try {
      // 1. Create org
      const res = await api.post("/orgs", { name: name.trim(), slug: slug || undefined });
      await applyTokens(res.data);
      const newOrgId = res.data.org.id;

      // 2. Apply template (skipped for blank flow)
      if (preset) {
        try {
          await api.post(`/templates/${preset.key}/apply`, { conflict_policy: "skip" });
        } catch (e) {
          // Template apply failure shouldn't undo the org — we already own it.
          toast.error(`Template apply failed: ${extractErrorMessage(e)}. Your workspace was still created.`);
        }
      }

      // 3. Refresh + go
      await refreshMe();
      toast.success(
        preset
          ? `Welcome to ${name}! Your ${preset.label.toLowerCase()} workspace is ready.`
          : `Welcome to ${name}!`
      );
      nav("/dashboard", { replace: true });
    } catch (err) {
      toast.error(extractErrorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/30 py-10 px-4" data-testid="onboarding-page">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6 flex items-center gap-2">
          <LayoutGrid className="w-6 h-6 text-primary" />
          <div className="font-semibold text-lg tracking-tight">UBOS</div>
        </div>

        <Stepper step={step} />

        {step === 1 && <StepPickType onPick={pickType} />}
        {step === 2 && (
          <StepName
            preset={preset}
            name={name}
            setName={setName}
            slug={slug}
            setSlug={setSlug}
            slugTouched={slugTouched}
            setSlugTouched={setSlugTouched}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <StepConfirm
            preset={preset}
            name={name}
            slug={slug}
            onBack={() => setStep(2)}
            onCreate={create}
            busy={busy}
          />
        )}
      </div>
    </div>
  );
}
