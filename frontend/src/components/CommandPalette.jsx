import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search as SearchIcon, Database, Boxes, FolderTree, Tag as TagIcon,
  Image as ImageIcon, FileText, X, Command,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const KIND_ICONS = {
  record: Database,
  entity_type: Boxes,
  category: FolderTree,
  tag: TagIcon,
  media: ImageIcon,
};

const KIND_LABELS = {
  record: "Record",
  entity_type: "Collection",
  category: "Category",
  tag: "Tag",
  media: "File",
};

const RECENT_KEY = "ubos.search.recent";

function loadRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.slice(0, 5) : [];
  } catch { return []; }
}
function pushRecent(q) {
  if (!q || !q.trim()) return;
  const prev = loadRecent().filter((x) => x !== q);
  const next = [q, ...prev].slice(0, 5);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* quota */ }
}

export function CommandPalette({ open, onOpenChange }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [tookMs, setTookMs] = useState(0);
  const [totals, setTotals] = useState({});
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [recent, setRecent] = useState(loadRecent());
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const debounceRef = useRef(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setResults([]);
      setActiveIndex(0);
      setRecent(loadRecent());
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) {
      setResults([]);
      setTotals({});
      setTookMs(0);
      setLoading(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await api.get("/search", { params: { q, limit: 20 } });
        setResults(r.data.results || []);
        setTotals(r.data.totals || {});
        setTookMs(r.data.took_ms || 0);
        setActiveIndex(0);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    }, 200);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, open]);

  const openResult = useCallback((r, { newTab } = {}) => {
    if (!r) return;
    pushRecent(q);
    let path = null;
    if (r.kind === "record") path = `/records/${r.id}`;
    else if (r.kind === "entity_type") path = `/entity-types/${r.id}/records`;
    else if (r.kind === "category") path = `/entity-types/${r.entity_type_id || r.breadcrumb?.[0]?.path?.split("/")[2] || ""}/categories`;
    else if (r.kind === "tag") path = r.breadcrumb?.[1]?.path || null;
    else if (r.kind === "media") path = "/media";
    if (!path) return;
    if (newTab) window.open(path, "_blank");
    else {
      navigate(path);
      onOpenChange(false);
    }
  }, [q, navigate, onOpenChange]);

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, Math.max(0, results.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      openResult(results[activeIndex], { newTab: e.metaKey || e.ctrlKey });
    } else if (e.key === "Escape") {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-2xl p-0 gap-0 top-[20%] translate-y-0 overflow-hidden"
        data-testid="command-palette"
      >
        <div className="flex items-center px-4 border-b border-border">
          <SearchIcon className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search items, collections, categories, tags, files…"
            className="flex-1 h-14 px-3 bg-transparent border-0 outline-none text-sm placeholder:text-muted-foreground"
            data-testid="palette-input"
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 rounded border border-border bg-muted/40 px-1.5 h-5 text-[10px] font-mono text-muted-foreground">
            ESC
          </kbd>
        </div>

        <div className="max-h-[420px] overflow-y-auto">
          {!q.trim() && recent.length > 0 && (
            <div className="p-2" data-testid="palette-recent">
              <div className="px-2 py-1 text-[10px] font-mono uppercase text-muted-foreground">Recent</div>
              {recent.map((r) => (
                <button
                  key={r}
                  onClick={() => setQ(r)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/60 text-left text-sm"
                  data-testid={`palette-recent-${r}`}
                >
                  <SearchIcon className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="truncate">{r}</span>
                </button>
              ))}
            </div>
          )}

          {!q.trim() && recent.length === 0 && (
            <div className="p-8 text-center text-sm text-muted-foreground">
              Type to search across your workspace.
              <div className="mt-2 text-xs">
                Items · Collections · Categories · Tags · Files
              </div>
            </div>
          )}

          {q.trim() && results.length === 0 && !loading && (
            <div className="p-8 text-center text-sm text-muted-foreground" data-testid="palette-no-results">
              No results for <b className="text-foreground">&quot;{q}&quot;</b>
              <div className="mt-3 text-xs">
                Try different keywords, or check spelling.
              </div>
            </div>
          )}

          {q.trim() && loading && results.length === 0 && (
            <div className="p-8 text-center text-xs text-muted-foreground">Searching…</div>
          )}

          {results.length > 0 && (
            <ul className="py-1" data-testid="palette-results">
              {results.map((r, i) => {
                const Icon = KIND_ICONS[r.kind] || FileText;
                const active = i === activeIndex;
                return (
                  <li key={`${r.kind}:${r.id}`}>
                    <button
                      onClick={() => openResult(r)}
                      onMouseEnter={() => setActiveIndex(i)}
                      className={`w-full flex items-start gap-3 px-3 py-2.5 text-left transition-colors ${active ? "bg-primary/10" : "hover:bg-muted/40"}`}
                      data-testid={`palette-result-${i}`}
                    >
                      <div className={`w-8 h-8 rounded flex items-center justify-center shrink-0 ${active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <div className="text-sm font-medium truncate">{r.title}</div>
                          {r.subtitle && <div className="text-xs text-muted-foreground font-mono truncate">· {r.subtitle}</div>}
                        </div>
                        {r.breadcrumb?.length > 0 && (
                          <div className="text-xs text-muted-foreground truncate mt-0.5">
                            {r.breadcrumb.map((b) => b.label).join(" › ")}
                          </div>
                        )}
                        {r.snippet && (
                          <div className="text-xs text-muted-foreground/80 truncate mt-0.5">
                            {r.snippet}
                          </div>
                        )}
                      </div>
                      <Badge variant="secondary" className="shrink-0 text-[9px] uppercase font-mono">
                        {KIND_LABELS[r.kind] || r.kind}
                      </Badge>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="border-t border-border px-3 py-2 flex items-center justify-between text-[11px] text-muted-foreground bg-muted/20">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1"><kbd className="rounded border border-border bg-white px-1 text-[10px] font-mono">↑</kbd><kbd className="rounded border border-border bg-white px-1 text-[10px] font-mono">↓</kbd> navigate</span>
            <span className="inline-flex items-center gap-1"><kbd className="rounded border border-border bg-white px-1 text-[10px] font-mono">↵</kbd> open</span>
            <span className="inline-flex items-center gap-1 hidden sm:inline-flex"><kbd className="rounded border border-border bg-white px-1 text-[10px] font-mono">⌘↵</kbd> new tab</span>
          </div>
          <div className="flex items-center gap-2">
            {q.trim() && (
              <button
                onClick={() => { navigate(`/search?q=${encodeURIComponent(q)}`); onOpenChange(false); }}
                className="text-primary hover:underline"
                data-testid="palette-view-all"
              >
                View all results →
              </button>
            )}
            {tookMs > 0 && <span className="font-mono">{tookMs}ms</span>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Global keyboard hook — mount once at the top of the app tree.
 * Returns [open, setOpen] tuple so components can also open the palette.
 */
export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const handler = (e) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  return [open, setOpen];
}
