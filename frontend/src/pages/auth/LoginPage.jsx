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

export default function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);

  useEffect(() => {
    api.get("/auth/google/status").then((r) => setGoogleEnabled(!!r.data.enabled)).catch(() => {});
  }, []);

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login({ email, password });
      const next = params.get("next") || "/entity-types";
      nav(decodeURIComponent(next), { replace: true });
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
    <div data-testid="login-page">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="text-sm text-muted-foreground mt-1.5">
        Welcome back. Continue where you left off.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            data-testid="input-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link
              to="/forgot-password"
              className="text-xs text-primary hover:underline"
              data-testid="link-forgot-password"
            >
              Forgot?
            </Link>
          </div>
          <Input
            id="password"
            data-testid="input-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p className="text-sm text-destructive" data-testid="login-error">
            {error}
          </p>
        )}
        <Button
          type="submit"
          className="w-full"
          disabled={busy}
          data-testid="submit-login"
        >
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <div className="my-6 relative">
        <div className="h-px bg-border" />
        <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-3 text-[11px] font-mono uppercase text-muted-foreground">
          or
        </span>
      </div>

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block w-full">
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={startGoogle}
                disabled={!googleEnabled}
                data-testid="google-signin-btn"
              >
                <GoogleIcon /> Continue with Google
              </Button>
            </span>
          </TooltipTrigger>
          {!googleEnabled && (
            <TooltipContent side="bottom">Google Sign-In not configured</TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>

      <p className="mt-8 text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link
          to="/register"
          className="text-primary font-medium hover:underline"
          data-testid="link-register"
        >
          Create one
        </Link>
      </p>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24" aria-hidden>
      <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.24 1.3-1.7 3.9-5.5 3.9-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.9 3.4 14.7 2.4 12 2.4 6.7 2.4 2.4 6.7 2.4 12S6.7 21.6 12 21.6c6.9 0 9.6-4.8 9.6-9.6 0-.6-.1-1.2-.2-1.8H12z" />
    </svg>
  );
}
