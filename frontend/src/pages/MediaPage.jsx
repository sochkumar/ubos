import { useEffect, useMemo, useState } from "react";
import {
  Upload, Trash2, FolderKanban, X, Download, ExternalLink, Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { useTerminology, t as tPure } from "@/lib/terminology";
import { PageBody, PageHeader, EmptyState } from "@/components/PageChrome";
import { MediaUploadZone } from "@/components/MediaUploadZone";
import { StorageQuotaBar, humanBytes } from "@/components/StorageQuotaBar";
import { MediaThumb, useMediaFileUrl, iconForMime } from "@/components/MediaThumb";

const MIME_GROUPS = [
  { key: "image/", label: "Images" },
  { key: "application/pdf", label: "PDF" },
  { key: "application/", label: "Documents" },
  { key: "video/", label: "Video" },
];

function MediaDrawer({ mediaId, onClose, onDeleted }) {
  const [media, setMedia] = useState(null);
  const [loading, setLoading] = useState(true);
  const url = useMediaFileUrl(media);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!mediaId) return;
    setLoading(true);
    api.get(`/media/${mediaId}`).then((r) => setMedia(r.data))
      .catch((e) => toast.error(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }, [mediaId]);

  if (!mediaId) return null;

  const del = async (cascade) => {
    setDeleting(true);
    try {
      await api.delete(`/media/${mediaId}`, { params: cascade ? { cascade: true } : {} });
      toast.success(tPure("media.deleted_toast"));
      onDeleted && onDeleted(mediaId);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.code === "media_in_use" && !cascade) {
        if (window.confirm(`This file is attached to ${d.attached_to?.length || 0} item(s). Detach and delete anyway?\n\nThis action cannot be undone.`)) {
          return del(true);
        }
      } else toast.error(extractErrorMessage(e));
    } finally { setDeleting(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex" data-testid="media-drawer">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-[480px] bg-white border-l border-border overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold truncate flex-1 mr-3" title={media?.filename}>{media?.filename || "…"}</h3>
          <Button variant="ghost" size="icon" onClick={onClose} data-testid="media-drawer-close">
            <X className="w-4 h-4" />
          </Button>
        </div>
        {loading || !media ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin inline mr-2" /> Loading…
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border border-border bg-muted/30 aspect-video flex items-center justify-center overflow-hidden">
              {media.mime?.startsWith("image/") && url ? (
                <img src={url} alt={media.filename} className="max-w-full max-h-full object-contain" />
              ) : media.mime?.startsWith("video/") && url ? (
                <video src={url} controls className="max-w-full max-h-full" />
              ) : media.mime === "application/pdf" && url ? (
                <embed src={url} type="application/pdf" className="w-full h-full" />
              ) : (
                <MediaThumb media={media} size={200} />
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Type</div>
                <div>{media.mime}</div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Size</div>
                <div>{humanBytes(media.size)}</div>
              </div>
              {media.width ? (
                <div>
                  <div className="text-[10px] font-mono uppercase text-muted-foreground">Dimensions</div>
                  <div>{media.width} × {media.height}</div>
                </div>
              ) : null}
              <div>
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Uploaded</div>
                <div>{new Date(media.created_at).toLocaleString()}</div>
              </div>
            </div>

            {url && (
              <a href={url} target="_blank" rel="noreferrer"
                 className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
                 data-testid="media-drawer-download">
                <Download className="w-4 h-4" /> Download
              </a>
            )}

            <div>
              <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1.5">
                Used in {media.attached_to?.length || 0} record{media.attached_to?.length === 1 ? "" : "s"}
              </div>
              {media.attached_to?.length ? (
                <div className="space-y-1.5">
                  {media.attached_to.map((a, i) => (
                    <Link key={i} to={`/records/${a.record_id}`}
                          className="flex items-center gap-2 text-sm p-2 rounded-md border border-border hover:bg-muted/40"
                          data-testid={`media-attached-${a.record_id}`}>
                      <span className="font-mono text-[10px] text-primary">{a.record_number || "REC"}</span>
                      <span className="truncate flex-1">{a.record_title || "record"}</span>
                      <Badge variant="secondary" className="text-[9px]">{a.role}{a.field_key ? `·${a.field_key}` : ""}</Badge>
                      <ExternalLink className="w-3.5 h-3.5 opacity-50" />
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Not attached to any record.</p>
              )}
            </div>

            <div className="pt-4 border-t border-border">
              <Button variant="outline" onClick={() => del(false)} disabled={deleting}
                className="w-full text-destructive hover:text-destructive"
                data-testid="media-drawer-delete">
                <Trash2 className="w-4 h-4 mr-1.5" />
                {deleting ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MediaPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [mimeFilter, setMimeFilter] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [openId, setOpenId] = useState(null);
  const [storage, setStorage] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (q) params.q = q;
      if (mimeFilter) params.mime = mimeFilter.endsWith("/") ? mimeFilter + "*" : mimeFilter;
      const [mediaRes, storageRes] = await Promise.all([
        api.get("/media", { params }),
        api.get("/media/storage"),
      ]);
      setItems(mediaRes.data.items || []);
      setTotal(mediaRes.data.total || 0);
      setStorage(storageRes.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [q, mimeFilter]);

  const toggleSel = (id) => setSelected((s) => {
    const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });
  const clearSel = () => setSelected(new Set());

  const bulkDelete = async () => {
    if (!window.confirm(`Delete ${selected.size} file(s)?\nAttached files will be detached first. This action cannot be undone.`)) return;
    let ok = 0, fail = 0;
    for (const id of selected) {
      try {
        await api.delete(`/media/${id}`, { params: { cascade: true } });
        ok++;
      } catch { fail++; }
    }
    toast.success(`Deleted ${ok}${fail ? ` (${fail} failed)` : ""}`);
    clearSel(); load();
  };

  return (
    <>
      <PageHeader
        title="Files"
        subtitle={`${total} file${total === 1 ? "" : "s"} in this workspace`}
        breadcrumbs={[{ label: "Files" }]}
        actions={<div className="w-56"><StorageQuotaBar data={storage} compact /></div>}
      />
      <PageBody className="space-y-4">
        <MediaUploadZone onUploaded={load} testIdPrefix="media-upload" />

        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Search filename…" value={q}
            onChange={(e) => setQ(e.target.value)}
            className="h-8 text-sm max-w-xs"
            data-testid="media-search"
          />
          <div className="flex items-center gap-1.5">
            {MIME_GROUPS.map((g) => {
              const on = mimeFilter === g.key;
              return (
                <button key={g.key}
                  onClick={() => setMimeFilter(on ? null : g.key)}
                  className={`text-xs px-2 py-1 rounded-full border transition-colors ${on ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted"}`}
                  data-testid={`media-filter-${g.label.toLowerCase()}`}>
                  {g.label}
                </button>
              );
            })}
          </div>
        </div>

        {selected.size > 0 && (
          <div className="sticky top-0 z-10 flex items-center gap-2 bg-primary text-primary-foreground p-2 rounded-md" data-testid="media-bulk-bar">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <div className="flex-1" />
            <Button variant="ghost" size="sm" className="text-primary-foreground hover:bg-white/10"
              onClick={bulkDelete} data-testid="media-bulk-delete">
              <Trash2 className="w-3.5 h-3.5 mr-1" /> Delete
            </Button>
            <Button variant="ghost" size="icon" className="text-primary-foreground hover:bg-white/10"
              onClick={clearSel}><X className="w-4 h-4" /></Button>
          </div>
        )}

        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : items.length === 0 ? (
          <EmptyState icon={FolderKanban} title="No files yet"
            description="Upload files, images, and documents. They'll show up here and become referenceable from any item." />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {items.map((m) => {
              const attached = (m.attached_to || []).length;
              return (
                <Card key={m.id} className="group cursor-pointer relative hover:shadow-md transition-shadow"
                      data-testid={`media-tile-${m.id}`}
                      onClick={() => setOpenId(m.id)}>
                  <div className="absolute top-2 left-2 z-10" onClick={(e) => { e.stopPropagation(); toggleSel(m.id); }}>
                    <Checkbox checked={selected.has(m.id)} onCheckedChange={() => toggleSel(m.id)}
                      className="bg-white/90 border-border"
                      data-testid={`media-select-${m.id}`} />
                  </div>
                  {attached > 0 && (
                    <Badge className="absolute top-2 right-2 z-10 text-[9px] px-1.5" variant="secondary">
                      × {attached}
                    </Badge>
                  )}
                  <div className="aspect-square p-2 flex items-center justify-center">
                    <MediaThumb media={m} size={140} />
                  </div>
                  <CardContent className="p-2 pt-0">
                    <div className="text-xs font-medium truncate" title={m.filename}>{m.filename}</div>
                    <div className="text-[10px] font-mono text-muted-foreground">{humanBytes(m.size)}</div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </PageBody>
      {openId && (
        <MediaDrawer mediaId={openId} onClose={() => setOpenId(null)}
          onDeleted={() => { setOpenId(null); load(); }} />
      )}
    </>
  );
}
