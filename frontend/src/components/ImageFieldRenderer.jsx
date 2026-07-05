import { useEffect, useState } from "react";
import { X, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { MediaThumb } from "@/components/MediaThumb";
import { MediaUploadZone } from "@/components/MediaUploadZone";

/**
 * DynamicField renderer for `image` field type.
 *
 * value shape: single {media_id} or array of {media_id} depending on
 * `field.config.multiple`.
 *
 * Props: standard DynamicField contract (field, value, onChange, error).
 */
export function ImageFieldRenderer({ field, value, onChange, error }) {
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
    if (multiple) {
      onChange([...values, ...docs.map((m) => ({ media_id: m.id }))]);
    } else {
      onChange({ media_id: docs[0].id });
    }
  };
  const remove = (idx) => {
    if (multiple) {
      onChange(values.filter((_, i) => i !== idx));
    } else {
      onChange(null);
    }
  };
  const setAsMain = (idx) => {
    if (!multiple || idx === 0) return;
    const next = [...values];
    const [v] = next.splice(idx, 1);
    next.unshift(v);
    onChange(next);
  };

  const canAddMore = multiple ? (!field.config?.max_count || values.length < field.config.max_count) : values.length === 0;

  return (
    <div data-testid={`field-${field.key}`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <label className="text-sm font-medium">
          {field.label}
          {field.required && <span className="text-destructive ml-1">*</span>}
        </label>
        <span className="text-[10px] font-mono text-muted-foreground uppercase">
          image{multiple ? " · multi" : ""}
        </span>
      </div>

      {values.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {values.map((v, i) => {
            const m = mediaById[v.media_id];
            return (
              <div key={`${v.media_id}-${i}`} className="relative group" data-testid={`image-item-${field.key}-${i}`}>
                <MediaThumb media={m || { id: v.media_id, mime: "image/jpeg" }} size={96} />
                {multiple && i === 0 && (
                  <span className="absolute top-1 left-1 bg-amber-400 text-white text-[9px] px-1.5 py-0.5 rounded-full font-medium flex items-center gap-0.5">
                    <Star className="w-2.5 h-2.5" /> Main
                  </span>
                )}
                <button type="button" onClick={() => remove(i)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-destructive text-white opacity-0 group-hover:opacity-100 transition-opacity"
                  data-testid={`image-remove-${field.key}-${i}`}
                  aria-label="Remove">
                  <X className="w-3.5 h-3.5 mx-auto" />
                </button>
                {multiple && i > 0 && (
                  <button type="button" onClick={() => setAsMain(i)}
                    className="absolute bottom-1 right-1 text-[9px] bg-white/90 border border-border px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    data-testid={`image-set-main-${field.key}-${i}`}>
                    Set as main
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {canAddMore && (
        <MediaUploadZone
          fieldKey={field.key} role="field"
          accept="image/jpeg,image/png,image/webp,image/gif"
          multiple={multiple}
          onUploaded={handleUploaded}
          testIdPrefix={`upload-${field.key}`}
          label={values.length ? "Add more" : "Drop image here or click to upload"}
          hint="JPG · PNG · WEBP · GIF"
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
