import { useEffect, useState } from "react";
import { X, Download } from "lucide-react";
import { api } from "@/lib/api";
import { MediaThumb, useMediaFileUrl } from "@/components/MediaThumb";
import { MediaUploadZone } from "@/components/MediaUploadZone";
import { humanBytes } from "@/components/StorageQuotaBar";

function FileRow({ media, onRemove }) {
  const url = useMediaFileUrl(media);
  return (
    <div className="flex items-center gap-3 border border-border rounded-md p-2 bg-white" data-testid={`file-item-${media.id}`}>
      <MediaThumb media={media} size={40} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{media.filename}</div>
        <div className="text-[11px] font-mono text-muted-foreground">
          {media.mime} · {humanBytes(media.size)}
        </div>
      </div>
      {url && (
        <a href={url} target="_blank" rel="noreferrer"
           className="text-primary hover:underline p-1.5"
           title="Download"
           data-testid={`file-download-${media.id}`}>
          <Download className="w-4 h-4" />
        </a>
      )}
      <button type="button" onClick={onRemove}
        className="text-muted-foreground hover:text-destructive p-1.5"
        aria-label="Remove"
        data-testid={`file-remove-${media.id}`}>
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export function FileFieldRenderer({ field, value, onChange, error }) {
  const multiple = !!(field.config || {}).multiple;
  const values = normalize(value, multiple);
  const [mediaById, setMediaById] = useState({});

  useEffect(() => {
    const ids = values.map((v) => v.media_id).filter((id) => !mediaById[id]);
    if (!ids.length) return;
    api.get(`/media?limit=200`).then((r) => {
      const map = { ...mediaById };
      r.data.items.forEach((m) => { if (ids.includes(m.id)) map[m.id] = m; });
      setMediaById(map);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(values.map((v) => v.media_id))]);

  const handleUploaded = (docs) => {
    docs.forEach((m) => setMediaById((prev) => ({ ...prev, [m.id]: m })));
    if (multiple) onChange([...values, ...docs.map((m) => ({ media_id: m.id }))]);
    else onChange({ media_id: docs[0].id });
  };
  const remove = (idx) => {
    if (multiple) onChange(values.filter((_, i) => i !== idx));
    else onChange(null);
  };

  const canAddMore = multiple ? (!field.config?.max_count || values.length < field.config.max_count) : values.length === 0;
  const allowed = (field.config?.allowed_mimes || []).join(",") || undefined;

  return (
    <div data-testid={`field-${field.key}`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <label className="text-sm font-medium">
          {field.label}
          {field.required && <span className="text-destructive ml-1">*</span>}
        </label>
        <span className="text-[10px] font-mono text-muted-foreground uppercase">
          file{multiple ? " · multi" : ""}
        </span>
      </div>

      {values.length > 0 && (
        <div className="space-y-1.5 mb-2">
          {values.map((v, i) => {
            const m = mediaById[v.media_id] || { id: v.media_id, filename: "…", mime: "application/octet-stream", size: 0 };
            return <FileRow key={`${v.media_id}-${i}`} media={m} onRemove={() => remove(i)} />;
          })}
        </div>
      )}
      {canAddMore && (
        <MediaUploadZone
          fieldKey={field.key} role="field"
          accept={allowed}
          multiple={multiple}
          onUploaded={handleUploaded}
          testIdPrefix={`upload-${field.key}`}
          label={values.length ? "Add more" : "Drop file here or click to upload"}
          hint={allowed || "Any allowed file type"}
        />
      )}
      {error ? <p className="text-xs text-destructive mt-1.5" data-testid={`error-${field.key}`}>{error}</p>
        : field.help_text ? <p className="text-xs text-muted-foreground mt-1.5">{field.help_text}</p> : null}
    </div>
  );
}

function normalize(v, multiple) {
  if (!v) return [];
  const list = Array.isArray(v) ? v : [v];
  return list.filter((x) => x && (x.media_id || typeof x === "string"))
    .map((x) => (typeof x === "string" ? { media_id: x } : x))
    .slice(0, multiple ? undefined : 1);
}
