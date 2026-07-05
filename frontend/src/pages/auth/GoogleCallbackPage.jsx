import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { extractErrorMessage } from "@/lib/errors";

export default function GoogleCallbackPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { applyTokens } = useAuth();
  const [error, setError] = useState(null);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const code = params.get("code");
    const state = params.get("state");
    const err = params.get("error");
    if (err) {
      setError(err);
      return;
    }
    if (!code || !state) {
      setError("Missing OAuth code or state");
      return;
    }
    (async () => {
      try {
        const redirect_uri = `${window.location.origin}/auth/google/callback`;
        const res = await api.post("/auth/google/exchange", {
          code, state, redirect_uri,
        });
        const me = await applyTokens(res.data);
        if ((me.organizations || []).length === 0) {
          nav("/onboarding", { replace: true });
        } else {
          nav("/entity-types", { replace: true });
        }
      } catch (e) {
        setError(extractErrorMessage(e));
      }
    })();
  }, [params, applyTokens, nav]);

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      data-testid="google-callback"
    >
      <div className="text-center max-w-md">
        {error ? (
          <>
            <h1 className="text-lg font-semibold">Sign-in failed</h1>
            <p className="text-sm text-destructive mt-2">{error}</p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold">Signing you in…</h1>
            <p className="text-sm text-muted-foreground mt-2 font-mono">
              exchanging authorization code
            </p>
          </>
        )}
      </div>
    </div>
  );
}
