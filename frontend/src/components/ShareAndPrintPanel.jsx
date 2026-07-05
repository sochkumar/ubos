import { useEffect, useState } from "react";
import {
  Copy, Link as LinkIcon, Lock, Printer, QrCode, ScanLine, Share2, ShieldOff, Trash2,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PrintLabelsDialog } from "@/components/PrintLabelsDialog";
import { DatePicker } from "@/components/DatePicker";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

function toDateInput(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  } catch { return ""; }
}

function fromDateInput(v) {
  if (!v) return null;
  const [y, m, d] = v.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 23, 59, 59)).toISOString();
}

/**
 * ShareAndPrintPanel — right-rail card on RecordDetailPage.
 * Shows QR + Code128 previews, active share links, and buttons for
 * "New share" and "Print labels".
 */
export function ShareAndPrintPanel({ record, fields }) {
  const rid = record?.id;
  const [shares, setShares] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [printOpen, setPrintOpen] = useState(false);
  const [qrTs, setQrTs] = useState(Date.now()); // bust cache after share create

  const load = async () => {
    if (!rid) return;
    setLoading(true);
    try {
      const r = await api.get(`/records/${rid}/shares`);
      setShares(r.data || []);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [rid]);

  // Because <img src> can't set Authorization headers, fetch the PNGs as blobs
  // and convert to object URLs.
  const [qrUrl, setQrUrl] = useState(null);
  const [bcUrl, setBcUrl] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function pull() {
      if (!rid) return;
      try {
        const [q, b] = await Promise.all([
          api.get(`/records/${rid}/qr.png?size=256&_t=${qrTs}`, { responseType: "blob" }),
          api.get(`/records/${rid}/barcode.png?height=90&_t=${qrTs}`, { responseType: "blob" }),
        ]);
        if (cancelled) return;
        setQrUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(q.data); });
        setBcUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(b.data); });
      } catch { /* ignore */ }
    }
    pull();
    return () => { cancelled = true; };
  }, [rid, qrTs]);

  const activeShare = shares.find((s) => !s.revoked_at) || null;

  const copyLink = async (url) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Public URL copied");
    } catch {
      toast.error("Couldn't copy — long-press the link instead");
    }
  };

  const revoke = async (s) => {
    if (!window.confirm("Revoke this public link? The URL will stop working immediately.")) return;
    try {
      await api.post(`/shares/${s.id}/revoke`);
      toast.success("Link revoked");
      await load();
      setQrTs(Date.now()); // QR points to different destination now
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const remove = async (s) => {
    if (!window.confirm("Permanently delete this share?")) return;
    try {
      await api.delete(`/shares/${s.id}`);
      toast.success("Share deleted");
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  return (
    <>
      <div className="rounded-lg border border-border bg-white" data-testid="share-print-panel">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <Share2 className="w-3.5 h-3.5 text-primary" />
          <div className="text-sm font-medium">Share &amp; Print</div>
        </div>

        {/* Codes preview */}
        <div className="p-4 grid grid-cols-2 gap-3">
          <div className="rounded-md bg-muted/30 border border-border/70 p-2 flex flex-col items-center gap-1.5" data-testid="qr-preview-wrap">
            <div className="flex items-center gap-1 text-[10px] font-mono uppercase text-muted-foreground">
              <QrCode className="w-3 h-3" /> QR
            </div>
            {qrUrl ? (
              <img src={qrUrl} alt="QR code" className="w-[104px] h-[104px]" data-testid="qr-preview" />
            ) : (
              <div className="w-[104px] h-[104px] bg-muted animate-pulse rounded" />
            )}
          </div>
          <div className="rounded-md bg-muted/30 border border-border/70 p-2 flex flex-col items-center gap-1.5" data-testid="barcode-preview-wrap">
            <div className="flex items-center gap-1 text-[10px] font-mono uppercase text-muted-foreground">
              <ScanLine className="w-3 h-3" /> Code128
            </div>
            {bcUrl ? (
              <img src={bcUrl} alt="Barcode" className="max-w-full h-[90px] object-contain" data-testid="barcode-preview" />
            ) : (
              <div className="w-full h-[90px] bg-muted animate-pulse rounded" />
            )}
          </div>
        </div>

        <div className="px-4 pb-3 flex gap-2">
          <Button
            size="sm" className="flex-1" onClick={() => setCreateOpen(true)}
            data-testid="new-share-btn"
          >
            <LinkIcon className="w-3.5 h-3.5 mr-1.5" /> New public link
          </Button>
          <Button
            size="sm" variant="outline" className="flex-1" onClick={() => setPrintOpen(true)}
            data-testid="print-labels-btn"
          >
            <Printer className="w-3.5 h-3.5 mr-1.5" /> Print labels
          </Button>
        </div>

        {/* Active shares */}
        <div className="px-4 pb-4 space-y-2 border-t border-border pt-3" data-testid="shares-list">
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading shares…</div>
          ) : shares.length === 0 ? (
            <div className="text-xs text-muted-foreground">No links created yet.</div>
          ) : (
            shares.map((s) => (
              <ShareRow key={s.id} share={s} onCopy={copyLink} onRevoke={revoke} onDelete={remove} />
            ))
          )}
        </div>
      </div>

      <CreateShareDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        record={record}
        fields={fields}
        onCreated={() => { load(); setQrTs(Date.now()); }}
      />

      <PrintLabelsDialog
        open={printOpen}
        onOpenChange={setPrintOpen}
        recordIds={rid ? [rid] : []}
        fields={fields}
      />
    </>
  );
}

function ShareRow({ share, onCopy, onRevoke, onDelete }) {
  const revoked = !!share.revoked_at;
  const expiresSoon = share.expires_at ? new Date(share.expires_at) < new Date(Date.now() + 3 * 86400e3) : false;
  return (
    <div
      className={`rounded border ${revoked ? "border-border/60 opacity-60" : "border-border"} bg-white p-2.5`}
      data-testid={`share-row-${share.token}`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <Badge variant="secondary" className="text-[9px] font-mono uppercase">{share.visibility}</Badge>
        {share.has_password && (
          <Badge className="bg-amber-100 text-amber-800 border-transparent text-[9px] inline-flex items-center gap-0.5" data-testid={`share-locked-${share.token}`}>
            <Lock className="w-2.5 h-2.5" /> password
          </Badge>
        )}
        {revoked && <Badge className="bg-destructive/15 text-destructive border-transparent text-[9px]">revoked</Badge>}
        {!revoked && share.expires_at && (
          <Badge className={`text-[9px] border-transparent ${expiresSoon ? "bg-amber-100 text-amber-800" : "bg-muted text-muted-foreground"}`}>
            expires {new Date(share.expires_at).toLocaleDateString()}
          </Badge>
        )}
        <div className="ml-auto text-[10px] font-mono text-muted-foreground">
          {share.view_count || 0} views
        </div>
      </div>
      <div className="flex items-center gap-1">
        <a
          href={share.public_url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-xs font-mono truncate text-primary hover:underline flex-1"
          data-testid={`share-url-${share.token}`}
        >
          {share.public_url}
        </a>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onCopy(share.public_url)}
          data-testid={`share-copy-${share.token}`}>
          <Copy className="w-3.5 h-3.5" />
        </Button>
        {!revoked && (
          <Button variant="ghost" size="icon" className="h-7 w-7 text-amber-700" onClick={() => onRevoke(share)}
            data-testid={`share-revoke-${share.token}`} title="Revoke">
            <ShieldOff className="w-3.5 h-3.5" />
          </Button>
        )}
        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => onDelete(share)}
          data-testid={`share-delete-${share.token}`} title="Delete">
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}

function CreateShareDialog({ open, onOpenChange, record, fields, onCreated }) {
  const [visibility, setVisibility] = useState("public");
  const [expires, setExpires] = useState("");
  const [password, setPassword] = useState("");
  const [includeMedia, setIncludeMedia] = useState(true);
  const [includeRels, setIncludeRels] = useState(false);
  const [restrict, setRestrict] = useState(false);
  const [visibleFields, setVisibleFields] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setVisibility("public");
      setExpires("");
      setPassword("");
      setIncludeMedia(true);
      setIncludeRels(false);
      setRestrict(false);
      setVisibleFields([]);
    }
  }, [open]);

  const nonSensitive = (fields || []).filter((f) => !f.sensitive && !["image", "file", "relation", "richtext"].includes(f.type));

  const toggle = (k) => setVisibleFields((p) => p.includes(k) ? p.filter((x) => x !== k) : [...p, k]);

  const submit = async () => {
    if (visibility === "password" && password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setBusy(true);
    try {
      const body = {
        visibility,
        include_media: includeMedia,
        include_relationships: includeRels,
        expires_at: fromDateInput(expires),
      };
      if (visibility === "password") body.password = password;
      if (restrict) body.visible_fields = visibleFields; // may be []
      await api.post(`/records/${record.id}/shares`, body);
      toast.success("Share link created");
      onCreated?.();
      onOpenChange(false);
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="create-share-dialog">
        <DialogHeader>
          <DialogTitle>New share link</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-sm">Visibility</Label>
            <Select value={visibility} onValueChange={setVisibility}>
              <SelectTrigger data-testid="share-visibility"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="public">Public — anyone with the link</SelectItem>
                <SelectItem value="password">Password protected — anyone with the link + password</SelectItem>
                <SelectItem value="org_only">Organization only — must be signed in</SelectItem>
                <SelectItem value="private">Private — creator + admins only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {visibility === "password" && (
            <div>
              <Label className="text-sm">Password <span className="text-muted-foreground text-xs">(min 8 chars)</span></Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                placeholder="At least 8 characters"
                autoComplete="new-password"
                data-testid="share-password"
              />
            </div>
          )}

          <div>
            <Label className="text-sm">Expires on <span className="text-muted-foreground text-xs">(optional)</span></Label>
            <DatePicker
              value={expires || null}
              onChange={(v) => setExpires(v || "")}
              testId="share-expires"
            />
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={includeMedia} onCheckedChange={setIncludeMedia} data-testid="share-include-media" />
              Include media
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={includeRels} onCheckedChange={setIncludeRels} data-testid="share-include-rels" />
              Include relationships
            </label>
          </div>

          <div className="pt-1">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={restrict} onCheckedChange={setRestrict} data-testid="share-restrict" />
              Restrict visible fields
            </label>
            {restrict && (
              <div className="mt-2 rounded-md border border-border p-2 bg-muted/20">
                <div className="text-[11px] font-mono uppercase text-muted-foreground mb-1">
                  Fields to expose <span className="normal-case font-sans">(empty = title/record # only)</span>
                </div>
                {nonSensitive.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No exposable fields on this entity.</div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {nonSensitive.map((f) => {
                      const on = visibleFields.includes(f.key);
                      return (
                        <button
                          key={f.key}
                          type="button"
                          onClick={() => toggle(f.key)}
                          className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                            on
                              ? "bg-primary text-primary-foreground border-primary"
                              : "bg-white text-foreground border-border hover:border-primary/60"
                          }`}
                          data-testid={`share-field-${f.key}`}
                        >
                          {f.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="share-create-submit">
            {busy ? "Creating…" : "Create link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
