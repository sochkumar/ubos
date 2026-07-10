import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import {
  AlertCircle, Building2, Calendar, ExternalLink, FileText, Image as ImageIcon,
  Link2, Mail, QrCode, ScanLine, ShieldAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

function fmtDate(iso, opts = { dateStyle: "medium" }) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(undefined, opts); } catch { return iso; }
}

function timeUntil(iso) {
  if (!iso) return null;
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "expired";
  const days = Math.floor(diffMs / 86400e3);
  const hours = Math.floor((diffMs % 86400e3) / 3600e3);
  if (days > 1) return `Link expires in ${days} days`;
  if (days === 1) return `Link expires tomorrow`;
  if (hours >= 1) return `Link expires in ${hours}h`;
  return `Link expires soon`;
}

function renderValue(fd, v) {
  if (v === null || v === undefined || v === "") {
    return <span className="text-muted-foreground/70 italic">—</span>;
  }
  if (fd.type === "boolean") return v ? "Yes" : "No";
  if (fd.type === "url") {
    return (
      <a href={v} target="_blank" rel="noreferrer noopener" className="text-primary hover:underline inline-flex items-center gap-1">
        {v} <ExternalLink className="w-3 h-3" />
      </a>
    );
  }
  if (fd.type === "email") {
    return <a href={`mailto:${v}`} className="text-primary hover:underline">{v}</a>;
  }
  if (fd.type === "date") return fmtDate(v, { dateStyle: "long" });
  if (fd.type === "datetime") return new Date(v).toLocaleString();
  if (fd.type === "currency") {
    try { return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(v)); }
    catch { return String(v); }
  }
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export default function PublicRecordPage() {
  const { token } = useParams();
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [qrDataUrl, setQrDataUrl] = useState(null);
  const [bcDataUrl, setBcDataUrl] = useState(null);
  const [mediaUrls, setMediaUrls] = useState({});
  const [unlockPassword, setUnlockPassword] = useState("");
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockError, setUnlockError] = useState(null);

  const load = async () => {
    try {
      // withCredentials so any unlock cookie is sent
      const r = await axios.get(`${API_BASE}/api/public/records/${token}`, {
        withCredentials: true,
      });
      setState({ loading: false, data: r.data, error: null });
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      const code = typeof detail === "object" ? detail?.code : null;
      setState({
        loading: false, data: null,
        error: {
          status: status || 0,
          code: code || (status === 404 ? "not_found" : status === 410 ? "gone" : "error"),
          message: typeof detail === "string" ? detail : (detail?.detail || "This link is unavailable."),
        },
      });
    }
  };

  useEffect(() => {
    load();
  }, [token]);

  const submitUnlock = async (e) => {
    e?.preventDefault?.();
    if (!unlockPassword) return;
    setUnlockBusy(true);
    setUnlockError(null);
    try {
      await axios.post(
        `${API_BASE}/api/public/records/${token}/unlock`,
        { password: unlockPassword },
        { withCredentials: true },
      );
      setUnlockPassword("");
      setState({ loading: true, data: null, error: null });
      await load();
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      if (status === 429) {
        setUnlockError({
          type: "throttled",
          message: (typeof detail === "object" ? detail?.detail : detail) || "Too many attempts.",
        });
      } else {
        setUnlockError({
          type: "invalid",
          message: (typeof detail === "object" ? detail?.detail : detail) || "Incorrect password.",
        });
      }
    } finally {
      setUnlockBusy(false);
    }
  };

  useEffect(() => {
    if (!state.data || state.data.share.visibility === "org_only" || state.data.share.visibility === "private") return;
    let cancelled = false;
    (async () => {
      try {
        const [q, b] = await Promise.all([
          axios.get(`${API_BASE}/api/public/records/${token}/qr.png?size=280`, {
            responseType: "blob", withCredentials: true,
          }),
          axios.get(`${API_BASE}/api/public/records/${token}/barcode.png?height=90`, {
            responseType: "blob", withCredentials: true,
          }),
        ]);
        if (cancelled) return;
        setQrDataUrl(URL.createObjectURL(q.data));
        setBcDataUrl(URL.createObjectURL(b.data));
      } catch { /* codes are optional */ }
    })();
    return () => { cancelled = true; };
  }, [state.data, token]);

  // Prefetch signed media URLs for images (if included)
  useEffect(() => {
    if (!state.data || !state.data.share.include_media) return;
    const imageMedia = (state.data.media || []).filter((m) => m.mime?.startsWith("image/"));
    let cancelled = false;
    (async () => {
      const entries = await Promise.all(
        imageMedia.map(async (m) => {
          try {
            const r = await axios.get(`${API_BASE}/api/public/records/${token}/media/${m.id}`, {
              withCredentials: true,
            });
            return [m.id, r.data.url];
          } catch { return [m.id, null]; }
        }),
      );
      if (cancelled) return;
      setMediaUrls(Object.fromEntries(entries));
    })();
    return () => { cancelled = true; };
  }, [state.data, token]);

  if (state.loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center">
        <div className="text-sm text-muted-foreground" data-testid="public-loading">Loading…</div>
      </div>
    );
  }

  if (state.error) {
    // Password-protected shares raise 401 with code=password_required.
    // Show the unlock form instead of the generic error screen.
    if (state.error.code === "password_required" || state.error.status === 401) {
      return (
        <PasswordGate
          token={token}
          onSubmit={submitUnlock}
          password={unlockPassword}
          setPassword={setUnlockPassword}
          busy={unlockBusy}
          error={unlockError}
        />
      );
    }
    return (
      <ErrorScreen err={state.error} />
    );
  }

  const { record, field_defs, org, share, media, relationships } = state.data;
  const expiry = timeUntil(share.expires_at);

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30" data-testid="public-record-page">
      {/* Header */}
      <header className="border-b border-border bg-white/80 backdrop-blur">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
            <Building2 className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Shared item</div>
            <div className="text-sm font-medium truncate" data-testid="public-org-name">{org?.name || "—"}</div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {share.visibility !== "public" && (
              <Badge variant="secondary" className="text-[10px] uppercase font-mono">{share.visibility}</Badge>
            )}
          </div>
        </div>
      </header>

      {/* Body */}
      <main className="max-w-5xl mx-auto px-6 py-8 grid grid-cols-1 md:grid-cols-[1fr,300px] gap-8">
        {/* Left: content */}
        <div className="space-y-6">
          <div>
            <div className="text-xs font-mono text-primary uppercase tracking-wider" data-testid="public-record-number">
              {record.record_number}
            </div>
            <h1 className="text-3xl font-semibold mt-1 tracking-tight" data-testid="public-record-title">
              {record.title || "Untitled"}
            </h1>
            {record.description && (
              <p className="mt-3 text-sm text-muted-foreground max-w-prose whitespace-pre-wrap">
                {record.description}
              </p>
            )}
          </div>

          {/* Fields */}
          {field_defs.length > 0 ? (
            <section className="rounded-lg border border-border bg-white overflow-hidden" data-testid="public-fields">
              <div className="px-4 py-2.5 border-b border-border text-[10px] font-mono uppercase text-muted-foreground">
                Details
              </div>
              <dl className="divide-y divide-border">
                {field_defs.map((fd) => (
                  <div key={fd.key} className="grid grid-cols-[180px,1fr] px-4 py-3 gap-4" data-testid={`public-field-${fd.key}`}>
                    <dt className="text-xs text-muted-foreground pt-0.5">{fd.label}</dt>
                    <dd className="text-sm break-words">{renderValue(fd, record.fields?.[fd.key])}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : (
            <section className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground" data-testid="public-fields-empty">
              No fields exposed on this share.
            </section>
          )}

          {/* Categories / Tags */}
          {(record.categories?.length || record.tags?.length) ? (
            <section className="flex flex-wrap gap-1.5" data-testid="public-cats-tags">
              {(record.categories || []).map((c) => (
                <Badge key={c.id} variant="secondary" className="text-xs">{c.name}</Badge>
              ))}
              {(record.tags || []).map((t) => (
                <span key={t.id}
                  className="text-xs px-2 py-0.5 rounded-full font-medium"
                  style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}>
                  {t.name}
                </span>
              ))}
            </section>
          ) : null}

          {/* Media */}
          {share.include_media && media?.length ? (
            <section data-testid="public-media">
              <div className="text-[10px] font-mono uppercase text-muted-foreground mb-2">
                Media ({media.length})
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {media.map((m) => (
                  <div key={m.id} className="rounded-md border border-border bg-white overflow-hidden group" data-testid={`public-media-${m.id}`}>
                    {m.mime?.startsWith("image/") && mediaUrls[m.id] ? (
                      <a href={mediaUrls[m.id]} target="_blank" rel="noreferrer noopener">
                        <img src={mediaUrls[m.id]} alt={m.filename} className="w-full aspect-square object-cover group-hover:opacity-90 transition-opacity" />
                      </a>
                    ) : (
                      <div className="w-full aspect-square bg-muted/40 flex items-center justify-center">
                        <FileText className="w-8 h-8 text-muted-foreground/70" />
                      </div>
                    )}
                    <div className="px-2 py-1.5 text-[11px] truncate" title={m.filename}>{m.filename}</div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {/* Relationships */}
          {share.include_relationships && relationships?.length ? (
            <section data-testid="public-relationships" className="space-y-3">
              <div className="text-[10px] font-mono uppercase text-muted-foreground">Related</div>
              {relationships.map((g, i) => (
                <div key={`${g.label}-${i}`} className="rounded-md border border-border bg-white">
                  <div className="px-3 py-2 border-b border-border text-xs font-medium flex items-center gap-2">
                    <Link2 className="w-3.5 h-3.5 text-muted-foreground" />
                    {g.label}
                    <Badge variant="secondary" className="text-[9px] ml-auto">{g.direction}</Badge>
                  </div>
                  <ul className="divide-y divide-border">
                    {g.items.map((it, j) => (
                      <li key={j} className="px-3 py-2 flex items-center gap-2 text-sm">
                        <span className="font-mono text-xs text-muted-foreground">{it.record_number}</span>
                        <span className="truncate">{it.title || "—"}</span>
                        {it.entity_type_name && (
                          <span className="ml-auto text-[10px] font-mono uppercase text-muted-foreground">{it.entity_type_name}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ) : null}
        </div>

        {/* Right: sidebar with codes */}
        <aside className="space-y-4 md:sticky md:top-6 self-start">
          {(share.visibility === "public" || share.visibility === "password") && (
            <div className="rounded-lg border border-border bg-white p-4 space-y-3" data-testid="public-codes">
              <div className="text-[10px] font-mono uppercase text-muted-foreground flex items-center gap-1.5">
                <QrCode className="w-3 h-3" /> Scan to open this page
              </div>
              {qrDataUrl ? (
                <img src={qrDataUrl} alt="QR code" className="w-full max-w-[240px] mx-auto" data-testid="public-qr" />
              ) : (
                <div className="w-full aspect-square bg-muted animate-pulse rounded" />
              )}
              {bcDataUrl && (
                <div className="pt-2 border-t border-border">
                  <div className="text-[10px] font-mono uppercase text-muted-foreground flex items-center gap-1.5 mb-2">
                    <ScanLine className="w-3 h-3" /> {record.record_number}
                  </div>
                  <img src={bcDataUrl} alt="Barcode" className="w-full" data-testid="public-barcode" />
                </div>
              )}
            </div>
          )}

          <div className="rounded-lg border border-border bg-white p-4 text-xs space-y-1.5">
            <div className="text-[10px] font-mono uppercase text-muted-foreground">About</div>
            <div><span className="text-muted-foreground">Updated:</span> {fmtDate(record.updated_at, { dateStyle: "medium" })}</div>
            <div><span className="text-muted-foreground">Workspace:</span> {org?.name}</div>
          </div>
        </aside>
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-white mt-8">
        <div className="max-w-5xl mx-auto px-6 py-4 flex flex-col md:flex-row md:items-center gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <a
              href="https://ubos.app"
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-2.5 py-1 hover:border-primary/60 hover:text-primary transition-colors"
              data-testid="powered-by-ubos"
            >
              <span className="inline-block w-4 h-4 rounded-sm bg-primary text-primary-foreground flex items-center justify-center text-[9px] font-bold leading-none">U</span>
              <span>Powered by <b className="font-semibold">UBOS</b></span>
            </a>
            <span className="hidden md:inline">·</span>
            <span className="hidden md:inline">read-only public view</span>
          </div>
          <div className="md:ml-auto flex flex-wrap items-center gap-4">
            {expiry && (
              <span className="inline-flex items-center gap-1" data-testid="public-expiry">
                <Calendar className="w-3 h-3" /> {expiry}
                {share.expires_at && (
                  <span className="text-muted-foreground/70">
                    {" "}
                    ({fmtDate(share.expires_at, { dateStyle: "medium" })})
                  </span>
                )}
              </span>
            )}
            {org?.support_email && (
              <a
                href={`mailto:${org.support_email}?subject=${encodeURIComponent(`Question about ${record.record_number}`)}`}
                className="text-primary hover:underline inline-flex items-center gap-1"
                data-testid="public-support-link"
              >
                <Mail className="w-3 h-3" /> Report a problem
              </a>
            )}
          </div>
        </div>
      </footer>
    </div>
  );
}

function PasswordGate({ token, onSubmit, password, setPassword, busy, error }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="max-w-md w-full rounded-lg border border-border bg-white p-8"
        data-testid="password-gate"
      >
        <div className="w-12 h-12 mx-auto rounded-full bg-primary/10 flex items-center justify-center mb-4">
          <ShieldAlert className="w-6 h-6 text-primary" />
        </div>
        <h1 className="text-lg font-semibold text-center">Password required</h1>
        <p className="mt-1 text-sm text-muted-foreground text-center">
          This link is protected. Enter the password to view the item.
        </p>
        <div className="mt-6 space-y-2">
          <label className="text-xs font-mono uppercase text-muted-foreground" htmlFor="unlock-pw">
            Password
          </label>
          <input
            id="unlock-pw"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            autoComplete="off"
            className="w-full h-10 px-3 rounded-md border border-border bg-white text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            data-testid="unlock-password-input"
          />
          {error && (
            <div
              className={`text-xs ${error.type === "throttled" ? "text-amber-800" : "text-destructive"}`}
              data-testid="unlock-error"
            >
              {error.message}
            </div>
          )}
        </div>
        <button
          type="submit"
          disabled={busy || password.length < 1}
          className="mt-6 w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          data-testid="unlock-submit"
        >
          {busy ? "Unlocking…" : "Unlock"}
        </button>
        <div className="mt-6 text-[10px] font-mono text-muted-foreground/70 uppercase tracking-wider text-center">
          UBOS · secure share · token {token.slice(0, 8)}…
        </div>
      </form>
    </div>
  );
}

function ErrorScreen({ err }) {
  const isGone = err.status === 410;
  const isNotFound = err.status === 404;
  const isAuth = err.status === 401;
  const Icon = isAuth ? ShieldAlert : AlertCircle;

  const title = isAuth
    ? "Sign-in required"
    : isGone
      ? "Link no longer available"
      : isNotFound
        ? "Not found"
        : "Something went wrong";

  const message = isAuth
    ? "This share requires you to be signed in to the owning workspace."
    : isGone
      ? "This link has been revoked, has expired, or the workspace is closed."
      : isNotFound
        ? "The item behind this link has been removed."
        : (err.message || "This link is unavailable.");

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4">
      <div className="max-w-md w-full rounded-lg border border-border bg-white p-8 text-center" data-testid="public-error">
        <div className="w-12 h-12 mx-auto rounded-full bg-muted flex items-center justify-center mb-4">
          <Icon className="w-6 h-6 text-muted-foreground" />
        </div>
        <h1 className="text-lg font-semibold mb-1" data-testid="public-error-title">{title}</h1>
        <p className="text-sm text-muted-foreground" data-testid="public-error-message">{message}</p>
        {isAuth && (
          <Link
            to="/login"
            className="mt-6 inline-block text-sm text-primary hover:underline"
            data-testid="public-error-login-link"
          >
            Go to sign in →
          </Link>
        )}
        <div className="mt-6 text-[10px] font-mono text-muted-foreground/70 uppercase tracking-wider">
          UBOS · code {err.code}
        </div>
      </div>
    </div>
  );
}
