import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Layers, LayoutGrid, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

const orgSlug = (name) =>
  name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);

export default function OnboardingPage() {
  const { orgs, applyTokens, refreshMe } = useAuth();
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [createdOrgId, setCreatedOrgId] = useState(null);
  const [templates, setTemplates] = useState([]);

  useEffect(() => {
    if (orgs.length > 0) nav("/entity-types", { replace: true });
  }, [orgs, nav]);

  useEffect(() => {
    if (step !== 2) return;
    api.get("/templates").then((r) => setTemplates(r.data)).catch(() => {});
  }, [step]);

  const createOrg = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("/orgs", { name: name.trim(), slug: slug || undefined });
      await applyTokens(res.data);
      setCreatedOrgId(res.data.org.id);
      setStep(2);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const finishBlank = async () => {
    await refreshMe();
    nav("/entity-types", { replace: true });
  };

  const seedDemoAndFinish = async () => {
    setBusy(true);
    try {
      await api.post("/dev/seed-demo");
      toast.success("Demo workspace loaded");
      await refreshMe();
      nav("/entity-types", { replace: true });
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const applyTemplate = async (key, name) => {
    setBusy(true);
    try {
      await api.post(`/templates/${key}/apply`, { conflict_policy: "skip" });
      toast.success(`Template '${name}' applied`);
      await refreshMe();
      nav("/entity-types", { replace: true });
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6 py-12 bg-background"
      data-testid="onboarding"
    >
      <div className="w-full max-w-lg">
        <div className="flex items-center gap-2 mb-6">
          <div className={`w-6 h-6 rounded-full text-xs font-medium flex items-center justify-center ${step >= 1 ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>1</div>
          <div className="h-px flex-1 bg-border" />
          <div className={`w-6 h-6 rounded-full text-xs font-medium flex items-center justify-center ${step >= 2 ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>2</div>
        </div>

        {step === 1 && (
          <div data-testid="onboarding-step-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              Create your organization
            </h1>
            <p className="text-sm text-muted-foreground mt-1.5">
              This is the workspace your data lives in. You can create more later.
            </p>
            <form onSubmit={createOrg} className="mt-8 space-y-4">
              <div>
                <Label htmlFor="name">Organization name</Label>
                <Input
                  id="name" data-testid="input-org-name"
                  value={name}
                  onChange={(e) => {
                    const v = e.target.value;
                    setName(v);
                    if (!slugTouched) setSlug(orgSlug(v));
                  }}
                  placeholder="Acme Furniture"
                  required
                />
              </div>
              <div>
                <Label htmlFor="slug">
                  URL slug{" "}
                  <span className="font-mono text-muted-foreground text-xs">
                    (a-z, 0-9, -)
                  </span>
                </Label>
                <Input
                  id="slug" data-testid="input-org-slug" className="font-mono"
                  value={slug}
                  onChange={(e) => {
                    setSlugTouched(true);
                    setSlug(orgSlug(e.target.value));
                  }}
                  placeholder="acme-furniture"
                />
              </div>
              {error && (
                <p className="text-sm text-destructive" data-testid="onboarding-error">
                  {error}
                </p>
              )}
              <Button
                type="submit" className="w-full" disabled={busy}
                data-testid="submit-create-org"
              >
                {busy ? "Creating…" : "Create organization"}
              </Button>
            </form>
          </div>
        )}

        {step === 2 && (
          <div data-testid="onboarding-step-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              Pick a starting point
            </h1>
            <p className="text-sm text-muted-foreground mt-1.5">
              You can change or extend anything later.
            </p>

            <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={finishBlank}
                className="text-left rounded-lg border border-border bg-white p-4 hover:border-primary/50 transition-colors"
                data-testid="start-blank-btn"
              >
                <div className="w-9 h-9 rounded-md bg-primary/10 text-primary flex items-center justify-center mb-3">
                  <Layers className="w-4 h-4" />
                </div>
                <div className="font-medium">Start blank</div>
                <p className="text-xs text-muted-foreground mt-1">
                  An empty workspace. Design your own entity types from scratch.
                </p>
              </button>

              <button
                type="button"
                onClick={seedDemoAndFinish}
                disabled={busy}
                className="text-left rounded-lg border border-border bg-white p-4 hover:border-primary/50 transition-colors disabled:opacity-60"
                data-testid="load-demo-btn"
              >
                <div className="w-9 h-9 rounded-md bg-primary/10 text-primary flex items-center justify-center mb-3">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div className="font-medium">Load demo workspace</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Products + Machines with sample records. Great for exploring.
                </p>
              </button>
            </div>

            <div className="mt-6 rounded-lg border border-dashed border-border bg-muted/40 p-4">
              <div className="text-[10px] font-mono uppercase tracking-wide text-muted-foreground mb-3">
                Starter templates
              </div>
              <div className="grid grid-cols-2 gap-2">
                {templates.filter((t) => t.key !== "demo_basic").map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => applyTemplate(t.key, t.name)}
                    disabled={busy}
                    className="text-left rounded-md border border-border bg-white p-3 hover:border-primary/50 transition-colors disabled:opacity-60"
                    data-testid={`onboarding-template-${t.key}`}
                  >
                    <div className="text-sm font-medium flex items-center gap-1.5">
                      {t.name}
                      <ArrowRight className="w-3 h-3 opacity-40" />
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                      {t.description}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
