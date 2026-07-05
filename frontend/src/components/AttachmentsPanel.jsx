import { useEffect, useState } from "react";
import { Trash2, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { MediaThumb, useMediaFileUrl } from "@/components/MediaThumb";
import { MediaUploadZone } from "@/components/MediaUploadZone";
import { humanBytes } from "@/components/StorageQuotaBar";

function Row({ media, onRemove }) {
  const url = useMediaFileUrl(media);
  return (
    <div className="flex items-center gap-3 border border-border rounded-md p-2.5 bg-white" data-testid={`attach-item-${media.id}`}>
      <MediaThumb media={media} size={44} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{media.filename}</div>
        <div className="text-[11px] font-mono text-muted-foreground">
          {media.mime} · {humanBytes(media.size)}
        </div>
      </div>
      {url && (
        <a href={url} target="_blank" rel="noreferrer"
          className="text-sm text-primary hover:underline px-2"
          data-testid={`attach-download-${media.id}`}>
          Download
        </a>
      )}
      <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive"
        onClick={onRemove} data-testid={`attach-remove-${media.id}`}>
        <Trash2 className="w-4 h-4" />
      </Button>
    </div>
  );
}

export function AttachmentsPanel({ record }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    if (!record?.id) return;
    setLoading(true);
    try {
      const r = await api.get("/media", {
        params: { record_id: record.id, limit: 100 },
      });
      // filter to role=attachment
      const only = (r.data.items || []).filter((m) =>
        (m.attached_to || []).some(
          (a) => a.record_id === record.id && a.role === "attachment",
        ),
      );
      setItems(only);
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [record?.id]);

  const remove = async (m) => {
    if (!window.confirm(`Remove ${m.filename} from this record's attachments?`)) return;
    try {
      await api.post(`/media/${m.id}/detach`, {
        record_id: record.id, role: "attachment",
      });
      toast.success("Detached");
      load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  return (
    <div className="space-y-3">
      <MediaUploadZone
        recordId={record?.id} role="attachment"
        onUploaded={() => load()}
        testIdPrefix="attach-upload"
        label="Drop files here or click to upload"
        hint="Any allowed file type · ≤ 25 MB each"
      />
      {loading ? (
        <p className="text-sm text-muted-foreground py-4 text-center">Loading…</p>
      ) : items.length === 0 ? (
        <div className="text-center py-8 space-y-2">
          <Paperclip className="w-8 h-8 mx-auto text-muted-foreground/60" />
          <p className="text-sm text-muted-foreground">No attachments yet.</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {items.map((m) => (
            <Row key={m.id} media={m} onRemove={() => remove(m)} />
          ))}
        </div>
      )}
    </div>
  );
}
