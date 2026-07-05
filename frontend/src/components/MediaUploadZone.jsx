import { useRef, useState } from "react";
import { Upload, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { humanBytes } from "@/components/StorageQuotaBar";

/**
 * Drag-drop upload zone. Fires `onUploaded(mediaDocs[])` after each successful
 * batch. If `recordId`/`fieldKey`/`role` are passed, they're sent as multipart
 * fields so the server attaches on write.
 */
export function MediaUploadZone({
  recordId, fieldKey, role = "field",
  accept = "image/*,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.*,text/plain,video/mp4",
  multiple = true, className = "",
  onUploaded, testIdPrefix = "upload",
  label = "Drop files here or click to upload",
  hint = "PNG · JPG · WEBP · PDF · DOC · MP4  ·  ≤ 25 MB each",
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  const doUpload = async (files) => {
    if (!files || !files.length) return;
    setBusy(true);
    try {
      const fd = new FormData();
      Array.from(files).forEach((f) => fd.append("files", f));
      if (recordId) fd.append("record_id", recordId);
      if (fieldKey) fd.append("field_key", fieldKey);
      if (role) fd.append("role", role);
      const r = await api.post("/media/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const bytes = r.data.reduce((n, m) => n + (m.size || 0), 0);
      toast.success(`Uploaded ${r.data.length} file${r.data.length === 1 ? "" : "s"} · ${humanBytes(bytes)}`);
      onUploaded && onUploaded(r.data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "quota_exceeded") {
        toast.error(`Quota exceeded — you have ${humanBytes(detail.quota_bytes - detail.used_bytes)} left, incoming ${humanBytes(detail.incoming_bytes)}.`);
      } else {
        toast.error(extractErrorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    setDragging(false);
    doUpload(e.dataTransfer.files);
  };

  return (
    <div
      className={`relative border-2 border-dashed rounded-lg transition-colors ${dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 bg-muted/20"} ${className}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      data-testid={`${testIdPrefix}-zone`}
    >
      <input
        ref={inputRef} type="file" multiple={multiple} accept={accept} className="hidden"
        onChange={(e) => { doUpload(e.target.files); e.target.value = ""; }}
        data-testid={`${testIdPrefix}-input`}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="w-full py-8 px-6 flex flex-col items-center gap-2 disabled:opacity-60"
        data-testid={`${testIdPrefix}-trigger`}
      >
        {busy ? (
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        ) : (
          <Upload className="w-6 h-6 text-muted-foreground" />
        )}
        <div className="text-sm font-medium">{busy ? "Uploading…" : label}</div>
        <div className="text-xs text-muted-foreground">{hint}</div>
      </button>
    </div>
  );
}
