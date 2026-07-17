import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  Search as SearchIcon, Database, Boxes, FolderTree, Tag as TagIcon,
  Image as ImageIcon, FileText, Filter, X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useTabTitle } from "@/lib/tabs";

const KIND_ICONS = {
  record: Database,
  entity_type: Boxes,
  category: FolderTree,
  tag: TagIcon,
  media: ImageIcon,
};

const KIND_LABELS = {
  record: "Item",
  entity_type: "Collection",
  category: "Category",
  tag: "Tag",
  media: "File",
};

const ALL_KINDS = ["record", "entity_type", "category", "tag", "media"];

// URL-facing plural form ↔ internal singular Kind.  Spec uses plural in the
// `types=` query string, so we normalize on read/write.
const URL_TO_KIND = {
  records: "record",
  entity_types: "entity_type",
  categories: "category",
  tags: "tag",
  media: "media",
  // Also accept singular for backwards-compat with older links
  record: "record",
  entity_type: "entity_type",
  category: "category",
  tag: "tag",
};
const KIND_TO_URL = {
  record: "items",
  entity_type: "entity_types",
  category: "categories",
  tag: "tags",
  media: "media",
};

export default function SearchPage() {
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();

  useTabTitle("Search", "search");

  const q = sp.get("q") || "";
  // Parse `types=` from URL — supports both singular + plural tokens, dedupes
  const kindsParam = (sp.get("types") || "")
    .split(",")
    .map((t) => URL_TO_KIND[t.trim().toLowerCase()])
    .filter(Boolean);
  const kinds = kindsParam.length ? Array.from(new Set(kindsParam)) : ALL_KINDS;
  const etIds = (sp.get("entity_type") || "").split(",").filter(Boolean);

  const [inputVal, setInputVal] = useState(q);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Sync local input with URL param (e.g. on back/forward)
  useEffect(() => { setInputVal(q); }, [q]);

  useEffect(() => {
    let cancelled = false;
    if (!q.trim()) { setData(null); return; }
    setLoading(true);
    const params = { q, limit: 20 };
    if (kinds.length && kinds.length < ALL_KINDS.length) {
      // Send plural forms — backend accepts both, spec says plural
      params.types = kinds.map((k) => KIND_TO_URL[k]).join(",");
    }
    if (etIds.length) params.entity_type_ids = etIds.join(",");
    api.get("/search", { params })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [q, sp.toString()]);

  const submitQuery = (val) => {
    const next = new URLSearchParams(sp);
    if (val) next.set("q", val); else next.delete("q");
    setSp(next);
  };

  const toggleKind = (k) => {
    let next = kinds.includes(k) ? kinds.filter((x) => x !== k) : [...kinds, k];
    if (next.length === 0) next = ALL_KINDS;
    const np = new URLSearchParams(sp);
    if (next.length === ALL_KINDS.length) np.delete("types");
    else np.set("types", next.map((k2) => KIND_TO_URL[k2]).join(","));
    setSp(np);
  };

  const toggleEntityType = (id) => {
    const next = etIds.includes(id) ? etIds.filter((x) => x !== id) : [...etIds, id];
    const np = new URLSearchParams(sp);
    if (next.length === 0) np.delete("entity_type");
    else np.set("entity_type", next.join(","));
    setSp(np);
  };

  const clearFilters = () => {
    const np = new URLSearchParams();
    if (q) np.set("q", q);
    setSp(np);
  };

  const openResult = (r) => {
    if (r.kind === "record") navigate(`/records/${r.id}`);
    else if (r.kind === "entity_type") navigate(`/entity-types/${r.id}/records`);
    else if (r.kind === "category" || r.kind === "tag") {
      const path = r.breadcrumb?.[1]?.path || r.breadcrumb?.[0]?.path;
      if (path) navigate(path);
    } else if (r.kind === "media") navigate("/media");
  };

  const kindsFacet = data?.facets?.kinds || [];
  const etFacet = data?.facets?.entity_types || [];
  const results = data?.results || [];

  return (
    <div className="max-w-6xl mx-auto p-6" data-testid="search-page">
      {/* Search input */}
      <div className="mb-6">
        <div className="relative">
          <SearchIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <form onSubmit={(e) => { e.preventDefault(); submitQuery(inputVal); }}>
            <Input
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Search anything…"
              className="pl-9 h-11 text-base"
              autoFocus
              data-testid="search-page-input"
            />
          </form>
        </div>
        {q && (
          <div className="mt-2 text-xs text-muted-foreground">
            {loading ? "Searching…" : (
              <>
                {results.length > 0 ? (
                  <span>Showing {results.length} of {Object.values(data?.totals || {}).reduce((a, b) => a + b, 0)} results</span>
                ) : "No results"}
                {data?.took_ms > 0 && <span className="ml-2 font-mono">· {data.took_ms}ms</span>}
              </>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[220px,1fr] gap-6">
        {/* Sidebar facets */}
        <aside className="space-y-5" data-testid="search-facets">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-mono uppercase text-muted-foreground">Filters</div>
              {(kinds.length !== ALL_KINDS.length || etIds.length > 0) && (
                <button onClick={clearFilters} className="text-[10px] text-primary hover:underline" data-testid="search-clear-filters">
                  Clear
                </button>
              )}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium mb-2">Type</div>
            <div className="space-y-1.5">
              {ALL_KINDS.map((k) => {
                const facet = kindsFacet.find((f) => f.kind === k);
                const on = kinds.includes(k);
                const Icon = KIND_ICONS[k];
                return (
                  <label
                    key={k}
                    className="flex items-center gap-2 text-sm cursor-pointer hover:text-primary"
                    data-testid={`search-facet-kind-${k}`}
                  >
                    <Checkbox checked={on} onCheckedChange={() => toggleKind(k)} />
                    <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="flex-1">{KIND_LABELS[k]}</span>
                    <span className="text-xs text-muted-foreground font-mono">{facet?.count ?? 0}</span>
                  </label>
                );
              })}
            </div>
          </div>

          {etFacet.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-2">Collection</div>
              <div className="space-y-1.5">
                {etFacet.map((f) => (
                  <label
                    key={f.id}
                    className="flex items-center gap-2 text-sm cursor-pointer hover:text-primary"
                    data-testid={`search-facet-et-${f.id}`}
                  >
                    <Checkbox
                      checked={etIds.includes(f.id)}
                      onCheckedChange={() => toggleEntityType(f.id)}
                    />
                    <span className="flex-1 truncate">{f.name}</span>
                    <span className="text-xs text-muted-foreground font-mono">{f.count}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* Results */}
        <main data-testid="search-results">
          {!q.trim() && (
            <div className="rounded-lg border border-dashed border-border p-12 text-center">
              <SearchIcon className="w-8 h-8 text-muted-foreground/60 mx-auto mb-3" />
              <div className="text-sm text-muted-foreground">
                Type a query to search across your workspace.
              </div>
            </div>
          )}
          {q.trim() && results.length === 0 && !loading && (
            <div className="rounded-lg border border-dashed border-border p-12 text-center" data-testid="search-empty">
              <div className="text-sm">No results for <b>&quot;{q}&quot;</b>.</div>
              <div className="mt-2 text-xs text-muted-foreground">Try different keywords or remove filters.</div>
            </div>
          )}
          <div className="space-y-2">
            {results.map((r) => {
              const Icon = KIND_ICONS[r.kind] || FileText;
              return (
                <button
                  key={`${r.kind}:${r.id}`}
                  onClick={() => openResult(r)}
                  className="w-full text-left rounded-lg border border-border bg-white p-4 hover:border-primary/60 hover:shadow-sm transition-all"
                  data-testid={`search-result-${r.kind}-${r.id}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-md bg-muted flex items-center justify-center shrink-0">
                      <Icon className="w-4 h-4 text-muted-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <div className="text-base font-medium truncate">{r.title}</div>
                        {r.subtitle && <div className="text-xs text-muted-foreground font-mono truncate">{r.subtitle}</div>}
                        <Badge variant="secondary" className="ml-auto text-[9px] uppercase font-mono">{KIND_LABELS[r.kind]}</Badge>
                      </div>
                      {r.breadcrumb?.length > 0 && (
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {r.breadcrumb.map((b) => b.label).join(" › ")}
                        </div>
                      )}
                      {r.snippet && (
                        <div className="text-sm text-muted-foreground mt-1.5 line-clamp-2">{r.snippet}</div>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}
