import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams, Link } from "react-router-dom";
import axios from "axios";
import {
  Building2, Check, AlertCircle, LogIn, UserPlus, Mail, Loader2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, tokenStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

function fmtDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
  catch { return iso; }
}

export default function AcceptInvitationPage() {
  const { token } = useParams();
  const nav = useNavigate();
  const [, setParams] = useSearchParams();
  const { status: authStatus, user, refreshMe } = useAuth();
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [accepting, setAccepting] = useState(false);

  // 1. Load invitation meta (public)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API_BASE}/api/invitations/${token}`);
        if (!cancelled) setState({ loading: false, data: r.data, error: null });
      } catch (e) {
        if (!cancelled) {
          const status = e?.response?.status;
          const detail = e?.response?.data?.detail;
          const code = typeof detail === "object" ? detail?.code : null;
          setState({
            loading: false, data: null,
            error: {
              status: status || 0,
              code: code || (status === 404 ? "invitation_not_found" : "error"),
              message: typeof detail === "string" ? detail : (detail?.detail || "This invitation is invalid."),
            },
          });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // 2. Auto-accept if user is authed with matching email
  useEffect(() => {
    const inv = state.data;
    if (!inv || accepting) return;
    if (inv.status !== "pending") return;
    if (authStatus !== "authed") return;
    if (!user) return;
    if ((user.email || "").toLowerCase() !== (inv.email || "").toLowerCase()) return;
    // matched — accept automatically after a small delay so the user sees the CTA briefly
  }, [state.data, authStatus, user, accepting]);

  const doAccept = async () => {
    setAccepting(true);
    try {
      const res = await api.post(`/invitations/${token}/accept`);
      toast.success(`Welcome to ${res.data.org_name}`);
      // Switch to the new org and reload
      try {
        const switchRes = await api.post(`/orgs/${res.data.org_id}/switch`);
        tokenStore.set(switchRes.data);
      } catch { /* ignore, refresh will pick up */ }
      await refreshMe();
      const dest = res.data.was_first_org ? "/onboarding" : "/dashboard";
      nav(dest, { replace: true });
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      const code = typeof detail === "object" ? detail?.code : null;
      const msg = typeof detail === "string" ? detail : (detail?.detail || "Could not accept invitation.");
      if (status === 403 && code === "email_mismatch") {
        toast.error(msg);
        setState((s) => ({ ...s, error: { status: 403, code: "email_mismatch", message: msg } }));
      } else if (status === 410) {
        setState((s) => ({ ...s, error: { status: 410, code, message: msg } }));
      } else {
        toast.error(msg);
      }
    } finally {
      setAccepting(false);
    }
  };

  if (state.loading) {
    return (
      <Shell>
        <div className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="invite-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading invitation…
        </div>
      </Shell>
    );
  }

  if (state.error) {
    return <ErrorState err={state.error} token={token} authedEmail={user?.email} />;
  }

  const inv = state.data;
  const isMismatch = (
    authStatus === "authed" && user &&
    (user.email || "").toLowerCase() !== (inv.email || "").toLowerCase()
  );

  const isExpired = inv.status === "expired";
  const isRevoked = inv.status === "revoked";
  const isAccepted = inv.status === "accepted";

  return (
    <Shell>
      <div className="text-center">
        <div className="w-14 h-14 mx-auto rounded-2xl bg-primary text-primary-foreground flex items-center justify-center mb-4">
          <Building2 className="w-6 h-6" />
        </div>
        <h1 className="text-xl font-semibold" data-testid="invite-org-name">
          You&apos;ve been invited to <span className="text-primary">{inv.org_name || "an organization"}</span>
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {inv.inviter?.name || inv.inviter?.email || "A teammate"} invited{" "}
          <span className="font-mono text-foreground" data-testid="invite-invitee-email">{inv.email}</span>
          {" "}as <Badge variant="secondary" className="ml-1 mr-1" data-testid="invite-role">{inv.role_name}</Badge>
          on UBOS.
        </p>
        {inv.expires_at && (
          <p className="mt-1 text-xs text-muted-foreground/80">
            Expires {fmtDate(inv.expires_at)}
          </p>
        )}
      </div>

      {isExpired && <StateBanner tone="error" title="This invitation expired" body="Ask the workspace owner to send you a fresh invite." />}
      {isRevoked && <StateBanner tone="error" title="This invitation was revoked" body="Ask the workspace owner to send you a fresh invite." />}
      {isAccepted && <StateBanner tone="ok" title="Already accepted" body="You've already accepted this invitation." />}

      {inv.status === "pending" && (
        <div className="mt-8 space-y-3">
          {authStatus === "authed" && !isMismatch ? (
            <Button
              size="lg"
              className="w-full"
              onClick={doAccept}
              disabled={accepting}
              data-testid="invite-accept-btn"
            >
              {accepting ? "Joining…" : (<><Check className="w-4 h-4 mr-2" /> Accept & join {inv.org_name}</>)}
            </Button>
          ) : authStatus === "authed" && isMismatch ? (
            <div className="text-center rounded-lg border border-amber-300 bg-amber-50 p-4">
              <div className="text-sm text-amber-900">
                This invitation was sent to <b className="font-mono">{inv.email}</b>,{" "}
                but you&apos;re signed in as <b className="font-mono">{user.email}</b>.
              </div>
              <Link
                to={`/login?next=${encodeURIComponent(`/invitations/${token}/accept`)}`}
                className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
                data-testid="invite-switch-account"
              >
                <LogIn className="w-3.5 h-3.5" /> Sign in with {inv.email}
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Link
                to={`/login?next=${encodeURIComponent(`/invitations/${token}/accept`)}&email=${encodeURIComponent(inv.email)}`}
                className="w-full inline-flex items-center justify-center gap-2 h-10 rounded-md border border-border bg-white text-sm hover:border-primary/60 hover:text-primary transition-colors"
                data-testid="invite-signin-link"
              >
                <LogIn className="w-4 h-4" /> Sign in and accept
              </Link>
              <Link
                to={`/register?next=${encodeURIComponent(`/invitations/${token}/accept`)}&email=${encodeURIComponent(inv.email)}`}
                className="w-full inline-flex items-center justify-center gap-2 h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                data-testid="invite-register-link"
              >
                <UserPlus className="w-4 h-4" /> Create account
              </Link>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4">
      <div className="max-w-md w-full rounded-lg border border-border bg-white p-8" data-testid="accept-invite-page">
        {children}
        <div className="mt-8 text-[10px] font-mono text-muted-foreground/70 uppercase tracking-wider text-center">
          UBOS · secure invitation
        </div>
      </div>
    </div>
  );
}

function StateBanner({ tone, title, body }) {
  const color = tone === "error"
    ? "border-destructive/30 bg-destructive/5 text-destructive"
    : "border-emerald-300 bg-emerald-50 text-emerald-900";
  return (
    <div className={`mt-6 rounded-md border p-4 ${color}`} data-testid="invite-state-banner">
      <div className="text-sm font-semibold">{title}</div>
      <div className="text-xs mt-1 opacity-80">{body}</div>
    </div>
  );
}

function ErrorState({ err, token, authedEmail }) {
  const isGone = err.status === 410;
  return (
    <Shell>
      <div className="text-center">
        <div className="w-12 h-12 mx-auto rounded-full bg-muted flex items-center justify-center mb-4">
          <AlertCircle className="w-6 h-6 text-muted-foreground" />
        </div>
        <h1 className="text-lg font-semibold mb-1" data-testid="invite-error-title">
          {isGone ? "This invitation is no longer valid" : "Invitation not found"}
        </h1>
        <p className="text-sm text-muted-foreground" data-testid="invite-error-message">
          {err.message}
        </p>
        <Link
          to="/login"
          className="mt-6 inline-block text-sm text-primary hover:underline"
        >
          Go to sign in →
        </Link>
      </div>
    </Shell>
  );
}
