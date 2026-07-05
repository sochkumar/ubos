import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";

export default function RegisterPage() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({
    name: "",
    email: params.get("email") || "",
    password: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);

  useEffect(() => {
    api.get("/auth/google/status").then((r) => setGoogleEnabled(!!r.data.enabled)).catch(() => {});
  }, []);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register(form);
      const next = params.get("next");
      nav(next ? decodeURIComponent(next) : "/onboarding", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const startGoogle = async () => {
    try {
      const redirect_uri = `${window.location.origin}/auth/google/callback`;
      const res = await api.get("/auth/google/login", { params: { redirect_uri } });
      window.location.assign(res.data.url);
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  return (
    <div data-testid="register-page">
      <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
      <p className="text-sm text-muted-foreground mt-1.5">
        Start with an empty workspace — bring your own data model.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <Label htmlFor="name">Name</Label>
          <Input
            id="name" data-testid="input-name" required autoComplete="name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email" data-testid="input-email" type="email" required autoComplete="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password" data-testid="input-password" type="password" required
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <p className="text-[11px] text-muted-foreground mt-1">At least 8 characters.</p>
        </div>
        {error && (
          <p className="text-sm text-destructive" data-testid="register-error">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy} data-testid="submit-register">
          {busy ? "Creating…" : "Create account"}
        </Button>
      </form>

      <div className="my-6 relative">
        <div className="h-px bg-border" />
        <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-3 text-[11px] font-mono uppercase text-muted-foreground">
          or
        </span>
      </div>

      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className="block w-full"
              data-testid="google-register-wrap"
              tabIndex={!googleEnabled ? 0 : -1}
            >
              <Button
                type="button" variant="outline" className="w-full pointer-events-auto"
                onClick={startGoogle} disabled={!googleEnabled}
                data-testid="google-register-btn"
              >
                Continue with Google
              </Button>
            </span>
          </TooltipTrigger>
          {!googleEnabled && (
            <TooltipContent
              side="bottom"
              data-testid="google-register-tooltip"
            >
              Google Sign-In not configured for this environment
            </TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>

      <p className="mt-8 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="text-primary font-medium hover:underline" data-testid="link-login">
          Sign in
        </Link>
      </p>
    </div>
  );
}
