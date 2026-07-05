import { useEffect, useState } from "react";
import { FileText, FileSpreadsheet, FileImage, Presentation, Film, Music, File } from "lucide-react";
import { api } from "@/lib/api";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

function makeSignedUrl(pathOrUrl) {
  if (!pathOrUrl) return null;
  if (/^https?:/.test(pathOrUrl)) return pathOrUrl;
  return `${BACKEND}${pathOrUrl}`;
}

export function iconForMime(mime) {
  const m = (mime || "").toLowerCase();
  if (m === "application/pdf") return { Icon: FileText, color: "#dc2626", short: "PDF" };
  if (m.includes("word") || m === "application/msword") return { Icon: FileText, color: "#2563eb", short: "DOC" };
  if (m.includes("sheet") || m.includes("excel")) return { Icon: FileSpreadsheet, color: "#059669", short: "XLS" };
  if (m.includes("presentation") || m.includes("powerpoint")) return { Icon: Presentation, color: "#ea580c", short: "PPT" };
  if (m.startsWith("text/")) return { Icon: FileText, color: "#525252", short: "TXT" };
  if (m.startsWith("video/")) return { Icon: Film, color: "#7c3aed", short: "VID" };
  if (m.startsWith("audio/")) return { Icon: Music, color: "#0891b2", short: "AUD" };
  if (m.startsWith("image/")) return { Icon: FileImage, color: "#0d9488", short: "IMG" };
  return { Icon: File, color: "#6b7280", short: "FILE" };
}

/** Which mimes have a real thumbnail rendered by the backend? */
function hasRenderedThumb(mime) {
  const m = (mime || "").toLowerCase();
  if (m.startsWith("image/") && m !== "image/svg+xml") return true;
  if (m === "application/pdf") return true;
  return false;
}

/** Show a thumbnail — image / rendered PDF preview if available, else colored icon block. */
export function MediaThumb({ media, size = 96, className = "" }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  const wantsThumb = hasRenderedThumb(media?.mime);

  useEffect(() => {
    let cancel = false;
    setUrl(null);
    setFailed(false);
    if (!wantsThumb || !media?.id) return;
    api.get(`/media/${media.id}/thumb`).then((r) => {
      if (cancel) return;
      // Only use the returned URL if the server rendered an actual image.
      // For unrenderable PDFs the endpoint returns image/svg+xml → fall through to icon.
      const rMime = (r.data?.mime || "").toLowerCase();
      if (r.data?.url && rMime.startsWith("image/") && rMime !== "image/svg+xml") {
        setUrl(makeSignedUrl(r.data.url));
      } else {
        setFailed(true);
      }
    }).catch(() => { if (!cancel) setFailed(true); });
    return () => { cancel = true; };
  }, [media?.id, wantsThumb]);

  if (!media) return null;

  if (wantsThumb && !failed && url) {
    return (
      <img
        src={url} alt={media.filename || ""}
        onError={() => setFailed(true)}
        style={{ width: size, height: size }}
        className={`object-cover rounded-md bg-muted ${className}`}
        data-testid={`media-thumb-${media.id}`}
      />
    );
  }
  const { Icon, color, short } = iconForMime(media.mime);
  return (
    <div
      style={{ width: size, height: size, backgroundColor: color + "1a", color }}
      className={`rounded-md flex flex-col items-center justify-center ${className}`}
      data-testid={`media-thumb-${media.id}`}
    >
      <Icon className="w-1/3 h-1/3 mb-1" />
      <span className="text-[10px] font-mono uppercase font-semibold">{short}</span>
    </div>
  );
}

/** Just returns a downloadable/preview URL suitable for <a href>, <img>, <video>, etc. */
export function useMediaFileUrl(media) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let cancel = false;
    if (!media?.id) { setUrl(null); return; }
    api.get(`/media/${media.id}/file`).then((r) => {
      if (!cancel && r.data?.url) setUrl(makeSignedUrl(r.data.url));
    }).catch(() => { if (!cancel) setUrl(null); });
    return () => { cancel = true; };
  }, [media?.id]);
  return url;
}
