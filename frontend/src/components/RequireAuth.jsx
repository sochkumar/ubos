import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export function RequireAuth({ children }) {
  const { status, orgs } = useAuth();
  const loc = useLocation();

  if (status === "checking") {
    return (
      <div
        className="min-h-screen flex items-center justify-center text-sm text-muted-foreground"
        data-testid="auth-loading"
      >
        Loading…
      </div>
    );
  }
  if (status === "guest") {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  // Force onboarding when user has zero orgs
  if (orgs.length === 0 && loc.pathname !== "/onboarding") {
    return <Navigate to="/onboarding" replace />;
  }
  return children;
}

export function RequireGuest({ children }) {
  const { status } = useAuth();
  if (status === "checking") return null;
  if (status === "authed") return <Navigate to="/dashboard" replace />;
  return children;
}
