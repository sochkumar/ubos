import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { AlertCircle, ChevronLeft, ExternalLink, Building2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

function fmtDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
  catch { return iso; }
}

function renderValue(fd, v) {
  if (v === null || v === undefined || v === "") return <span className="text-muted-foreground/70 italic">—</span>;
  if (fd.type === "boolean") return v ? "Yes" : "No";
  if (fd.type === "url") return (
    <a href={v} target="_blank" rel="noreferrer noopener" className="text-primary hover:underline inline-flex items-center gap-1">
      {v} <ExternalLink className="w-3 h-3" />
    </a>
  );
  if (fd.type === "email") return <a href={`mailto:${v}`} className="text-primary hover:underline">{v}</a>;
  if (fd.type === "date") return new Date(v).toLocaleDateString(undefined, { dateStyle: "long" });
  if (fd.type === "datetime") return new Date(v).toLocaleString();
  if (fd.type === "currency") {
    try { return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(v)); }
    catch { return String(v); }
  }
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export default function PublicViewRecordPage() {
  const { token, record_id } = useParams();
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API_BASE}/api/public/views/${token}/records/${record_id}`, {
          withCredentials: true,
        });
        if (!cancelled) setState({ loading: false, data: r.data, error: null });
      } catch (e) {
        if (!cancelled) {
          const status = e?.response?.status;
          const detail = e?.response?.data?.detail;
          const code = typeof detail === "object" ? detail?.code : null;
          setState({
            loading: false, data: null,
            error: {
              status: status || 0, code,
              message: typeof detail === "string" ? detail : (detail?.detail || "This record is unavailable."),
            },
          });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [token, record_id]);

  if (state.loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center">
        <div className="text-sm text-muted-foreground" data-testid="public-view-rec-loading">Loading…</div>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4">
        <div className="max-w-md w-full rounded-lg border border-border bg-white p-8 text-center">
          <div className="w-12 h-12 mx-auto rounded-full bg-muted flex items-center justify-center mb-4">
            <AlertCircle className="w-6 h-6 text-muted-foreground" />
          </div>
          <div className="text-lg font-semibold">Record not available</div>
          <div className="text-sm text-muted-foreground mt-1">{state.error.message}</div>
          <Link to={`/v/${token}`} className="mt-4 inline-block text-sm text-primary hover:underline">
            ← Back to view
          </Link>
        </div>
      </div>
    );
  }

  const { record, field_defs, media, view, share } = state.data;

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-muted/30" data-testid="public-view-record-page">
      <header className="border-b border-border bg-white/80 backdrop-blur">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link to={`/v/${token}`} className="text-muted-foreground hover:text-foreground" data-testid="back-to-view">
            <ChevronLeft className="w-5 h-5" />
          </Link>
          <div className="min-w-0">
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
              From shared view · <Link to={`/v/${token}`} className="hover:underline">{view.name}</Link>
            </div>
            <div className="text-sm font-medium truncate">{record.title || record.record_number}</div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <div>
          <div className="text-xs font-mono text-primary uppercase" data-testid="public-view-rec-number">{record.record_number}</div>
          <h1 className="text-3xl font-semibold mt-1 tracking-tight" data-testid="public-view-rec-title">
            {record.title || "Untitled record"}
          </h1>
        </div>

        {field_defs.length > 0 ? (
          <section className="rounded-lg border border-border bg-white overflow-hidden" data-testid="public-view-rec-fields">
            <div className="px-4 py-2.5 border-b border-border text-[10px] font-mono uppercase text-muted-foreground">Details</div>
            <dl className="divide-y divide-border">
              {field_defs.map((fd) => (
                <div key={fd.key} className="grid grid-cols-[180px,1fr] px-4 py-3 gap-4" data-testid={`public-view-rec-field-${fd.key}`}>
                  <dt className="text-xs text-muted-foreground pt-0.5">{fd.label}</dt>
                  <dd className="text-sm break-words">{renderValue(fd, record.fields?.[fd.key])}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : (
          <div className="text-sm text-muted-foreground" data-testid="public-view-rec-fields-empty">
            No fields are exposed on this share.
          </div>
        )}

        {share.include_media && media?.length ? (
          <section data-testid="public-view-rec-media">
            <div className="text-[10px] font-mono uppercase text-muted-foreground mb-2">Media ({media.length})</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              {media.map((m) => (
                <div key={m.id} className="rounded border border-border bg-white p-2 truncate" title={m.filename}>
                  {m.filename}
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}
