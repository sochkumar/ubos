import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  AlertCircle, Building2, Calendar, ChevronRight, ExternalLink, FileText,
  Mail, ShieldAlert, ChevronLeft,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

function fmtDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" }); }
  catch { return iso; }
}

function timeUntil(iso) {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "expired";
  const days = Math.floor(diff / 86400e3);
  if (days > 1) return `Link expires in ${days} days`;
  if (days === 1) return "Link expires tomorrow";
  return "Link expires soon";
}

function renderCell(fd, v) {
  if (v === null || v === undefined || v === "") {
    return <span className="text-muted-foreground/70">—</span>;
  }
  if (fd.type === "boolean") return v ? "Yes" : "No";
  if (fd.type === "url") {
    return (
      <a href={v} target="_blank" rel="noreferrer noopener"
        onClick={(e) => e.stopPropagation()}
        className="text-primary hover:underline inline-flex items-center gap-1">
        {v} <ExternalLink className="w-3 h-3" />
      </a>
    );
  }
  if (fd.type === "email") {
    return <a href={`mailto:${v}`} onClick={(e) => e.stopPropagation()}
      className="text-primary hover:underline">{v}</a>;
  }
  if (fd.type === "date") return fmtDate(v);
  if (fd.type === "datetime") return new Date(v).toLocaleString();
  if (fd.type === "currency") {
    try { return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(v)); }
    catch { return String(v); }
  }
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export default function PublicViewPage() {
  const { token } = useParams();
  const nav = useNavigate();
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [cursor, setCursor] = useState(null);
  const [q, setQ] = useState("");
  const [unlockPassword, setUnlockPassword] = useState("");
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockError, setUnlockError] = useState(null);

  const load = async (opts = {}) => {
    try {
      const params = new URLSearchParams();
      if (opts.cursor) params.append("cursor", opts.cursor);
      if (opts.q) params.append("q", opts.q);
      const url = `${API_BASE}/api/public/views/${token}${params.toString() ? "?" + params.toString() : ""}`;
      const r = await axios.get(url, { withCredentials: true });
      setState({ loading: false, data: r.data, error: null });
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      const code = typeof detail === "object" ? detail?.code : null;
      setState({
        loading: false, data: null,
        error: {
          status: status || 0, code: code || (status === 404 ? "not_found" : status === 410 ? "gone" : "error"),
          message: typeof detail === "string" ? detail : (detail?.detail || "This link is unavailable."),
        },
      });
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [token]);

  const submitUnlock = async (e) => {
    e?.preventDefault?.();
    if (!unlockPassword) return;
    setUnlockBusy(true); setUnlockError(null);
    try {
      await axios.post(
        `${API_BASE}/api/public/views/${token}/unlock`,
        { password: unlockPassword },
        { withCredentials: true },
      );
      setUnlockPassword("");
      setState({ loading: true, data: null, error: null });
      await load();
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      setUnlockError({
        type: status === 429 ? "throttled" : "invalid",
        message: (typeof detail === "object" ? detail?.detail : detail) ||
                 (status === 429 ? "Too many attempts." : "Incorrect password."),
      });
    } finally { setUnlockBusy(false); }
  };

  if (state.loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center">
        <div className="text-sm text-muted-foreground" data-testid="public-view-loading">Loading view…</div>
      </div>
    );
  }

  if (state.error) {
    if (state.error.code === "password_required" || state.error.status === 401) {
      return (
        <PasswordGate token={token} onSubmit={submitUnlock}
          password={unlockPassword} setPassword={setUnlockPassword}
          busy={unlockBusy} error={unlockError} />
      );
    }
    return <ErrorScreen err={state.error} />;
  }

  const { view, records, pagination, share } = state.data;
  const cols = view.visible_columns || [];
  const expiry = timeUntil(share.expires_at);

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30" data-testid="public-view-page">
      <header className="border-b border-border bg-white/80 backdrop-blur">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-md flex items-center justify-center text-white"
            style={{ background: view.entity_type_color || "#0f766e" }}
          >
            <Building2 className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Shared view</div>
            <div className="text-sm font-medium truncate" data-testid="public-view-org">
              {view.org_name} · {view.entity_type_name}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {share.visibility !== "public" && (
              <Badge variant="secondary" className="text-[10px] uppercase font-mono">{share.visibility}</Badge>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight" data-testid="public-view-name">{view.name}</h1>
          {view.description && (
            <p className="mt-2 text-sm text-muted-foreground max-w-prose">{view.description}</p>
          )}
          <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
            <span data-testid="public-view-total">{pagination.total.toLocaleString()} items</span>
            <span>·</span>
            <span className="font-mono uppercase">{view.layout}</span>
          </div>
        </div>

        {records.length === 0 ? (
          <div className="rounded-lg border border-border bg-white p-8 text-center" data-testid="public-view-empty">
            <FileText className="w-8 h-8 mx-auto text-muted-foreground/60 mb-2" />
            <div className="text-sm text-muted-foreground">No items match this view.</div>
          </div>
        ) : view.layout === "gallery" || view.layout === "grid" ? (
          <GalleryLayout records={records} cols={cols} token={token} onOpen={(r) => nav(`/v/${token}/r/${r.id}`)} />
        ) : view.layout === "card" ? (
          <CardLayout records={records} cols={cols} onOpen={(r) => nav(`/v/${token}/r/${r.id}`)} />
        ) : view.layout === "list" ? (
          <ListLayout records={records} cols={cols} onOpen={(r) => nav(`/v/${token}/r/${r.id}`)} />
        ) : (
          <TableLayout records={records} cols={cols} onOpen={(r) => nav(`/v/${token}/r/${r.id}`)} />
        )}

        {pagination.next_cursor && (
          <div className="flex justify-center pt-2">
            <Button
              variant="outline"
              onClick={() => load({ cursor: pagination.next_cursor })}
              data-testid="public-view-load-more"
            >
              Load more
            </Button>
          </div>
        )}
      </main>

      <footer className="border-t border-border bg-white mt-8">
        <div className="max-w-6xl mx-auto px-6 py-4 flex flex-col md:flex-row md:items-center gap-2 text-xs text-muted-foreground">
          <a
            href="https://ubos.app"
            target="_blank" rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-2.5 py-1 hover:border-primary/60 hover:text-primary transition-colors w-fit"
            data-testid="powered-by-ubos"
          >
            <span className="inline-block w-4 h-4 rounded-sm bg-primary text-primary-foreground flex items-center justify-center text-[9px] font-bold leading-none">U</span>
            <span>Powered by <b className="font-semibold">UBOS</b></span>
          </a>
          {expiry && (
            <span className="md:ml-auto inline-flex items-center gap-1" data-testid="public-view-expiry">
              <Calendar className="w-3 h-3" /> {expiry}
            </span>
          )}
        </div>
      </footer>
    </div>
  );
}

function TableLayout({ records, cols, onOpen }) {
  return (
    <div className="rounded-lg border border-border bg-white overflow-x-auto" data-testid="public-view-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="text-left px-3 py-2 font-medium text-[10px] font-mono uppercase text-muted-foreground w-28">#</th>
            <th className="text-left px-3 py-2 font-medium text-[10px] font-mono uppercase text-muted-foreground">Title</th>
            {cols.map((c) => (
              <th key={c.field_key} className="text-left px-3 py-2 font-medium text-[10px] font-mono uppercase text-muted-foreground">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr
              key={r.id}
              className="border-b border-border last:border-0 hover:bg-muted/20 cursor-pointer"
              onClick={() => onOpen(r)}
              data-testid={`public-view-row-${r.record_number}`}
            >
              <td className="px-3 py-2 font-mono text-xs text-primary whitespace-nowrap">{r.record_number}</td>
              <td className="px-3 py-2 font-medium">{r.title || <span className="text-muted-foreground italic">Untitled</span>}</td>
              {cols.map((c) => (
                <td key={c.field_key} className="px-3 py-2">
                  {renderCell(c, r.fields?.[c.field_key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GalleryLayout({ records, cols, onOpen }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3" data-testid="public-view-gallery">
      {records.map((r) => (
        <div
          key={r.id}
          onClick={() => onOpen(r)}
          className="rounded-lg border border-border bg-white p-3 cursor-pointer hover:border-primary/50 hover:shadow-sm transition-all"
          data-testid={`public-view-tile-${r.record_number}`}
        >
          <div className="text-[10px] font-mono text-primary uppercase mb-1">{r.record_number}</div>
          <div className="font-medium text-sm line-clamp-2">{r.title || "Untitled"}</div>
          {cols.slice(0, 3).map((c) => (
            <div key={c.field_key} className="text-xs text-muted-foreground mt-1 truncate">
              <span className="text-muted-foreground/70">{c.label}:</span>{" "}
              {renderCell(c, r.fields?.[c.field_key])}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function CardLayout({ records, cols, onOpen }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="public-view-cards">
      {records.map((r) => (
        <div
          key={r.id}
          onClick={() => onOpen(r)}
          className="rounded-lg border border-border bg-white p-4 cursor-pointer hover:border-primary/50 transition-colors"
          data-testid={`public-view-card-${r.record_number}`}
        >
          <div className="text-[10px] font-mono text-primary uppercase mb-1">{r.record_number}</div>
          <div className="font-medium">{r.title || "Untitled"}</div>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
            {cols.map((c) => (
              <div key={c.field_key} className="text-xs">
                <dt className="text-muted-foreground/70">{c.label}</dt>
                <dd>{renderCell(c, r.fields?.[c.field_key])}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

function ListLayout({ records, cols, onOpen }) {
  return (
    <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="public-view-list">
      <ul className="divide-y divide-border">
        {records.map((r) => (
          <li
            key={r.id}
            onClick={() => onOpen(r)}
            className="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-muted/20"
            data-testid={`public-view-listrow-${r.record_number}`}
          >
            <span className="font-mono text-xs text-primary w-24 shrink-0">{r.record_number}</span>
            <span className="font-medium truncate flex-1">{r.title || "Untitled"}</span>
            <div className="hidden md:flex items-center gap-4 text-xs text-muted-foreground">
              {cols.slice(0, 2).map((c) => (
                <span key={c.field_key} className="truncate max-w-[160px]">
                  {renderCell(c, r.fields?.[c.field_key])}
                </span>
              ))}
            </div>
            <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
          </li>
        ))}
      </ul>
    </div>
  );
}

function PasswordGate({ token, onSubmit, password, setPassword, busy, error }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4">
      <form onSubmit={onSubmit}
        className="max-w-md w-full rounded-lg border border-border bg-white p-8"
        data-testid="view-password-gate">
        <div className="w-12 h-12 mx-auto rounded-full bg-primary/10 flex items-center justify-center mb-4">
          <ShieldAlert className="w-6 h-6 text-primary" />
        </div>
        <h1 className="text-lg font-semibold text-center">Password required</h1>
        <p className="mt-1 text-sm text-muted-foreground text-center">
          This shared view is protected. Enter the password to continue.
        </p>
        <div className="mt-6 space-y-2">
          <label className="text-xs font-mono uppercase text-muted-foreground" htmlFor="view-unlock-pw">Password</label>
          <input id="view-unlock-pw" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)} autoFocus autoComplete="off"
            className="w-full h-10 px-3 rounded-md border border-border bg-white text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            data-testid="view-unlock-password-input"
          />
          {error && (
            <div className={`text-xs ${error.type === "throttled" ? "text-amber-800" : "text-destructive"}`}
              data-testid="view-unlock-error">
              {error.message}
            </div>
          )}
        </div>
        <button type="submit" disabled={busy || password.length < 1}
          className="mt-6 w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
          data-testid="view-unlock-submit">
          {busy ? "Unlocking…" : "Unlock"}
        </button>
        <div className="mt-6 text-[10px] font-mono text-muted-foreground/70 uppercase tracking-wider text-center">
          UBOS · secure view · token {token.slice(0, 8)}…
        </div>
      </form>
    </div>
  );
}

function ErrorScreen({ err }) {
  const isGone = err.status === 410;
  const isNotFound = err.status === 404;
  const title = isGone ? "View no longer available" : isNotFound ? "View not found" : "Something went wrong";
  const message = isGone ? "This link has been revoked, expired, or the workspace is closed."
                 : isNotFound ? "The view behind this link has been removed."
                 : (err.message || "This link is unavailable.");
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4">
      <div className="max-w-md w-full rounded-lg border border-border bg-white p-8 text-center" data-testid="public-view-error">
        <div className="w-12 h-12 mx-auto rounded-full bg-muted flex items-center justify-center mb-4">
          <AlertCircle className="w-6 h-6 text-muted-foreground" />
        </div>
        <h1 className="text-lg font-semibold mb-1" data-testid="public-view-error-title">{title}</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}
