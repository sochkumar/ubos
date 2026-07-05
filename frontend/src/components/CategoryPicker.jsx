import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { ChevronDown, X, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";

/** Multi-select category picker with tree browse. */
export function CategoryPicker({ entityTypeId, value = [], onChange, testIdPrefix = "cat-picker" }) {
  const [tree, setTree] = useState([]);
  const [flat, setFlat] = useState({});
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!entityTypeId) return;
    api.get(`/entity-types/${entityTypeId}/categories`).then((r) => {
      setTree(r.data);
      const map = {};
      const walk = (nodes) => nodes.forEach((n) => {
        map[n.id] = n;
        if (n.children) walk(n.children);
      });
      walk(r.data);
      setFlat(map);
    }).catch(() => {});
  }, [entityTypeId]);

  const toggle = (id) => {
    if (value.includes(id)) onChange(value.filter((x) => x !== id));
    else onChange([...value, id]);
  };

  const renderNode = (n, depth) => (
    <div key={n.id}>
      <label
        className="flex items-center gap-2 px-2 py-1 rounded hover:bg-muted cursor-pointer text-sm"
        style={{ paddingLeft: 8 + depth * 14 }}
      >
        <input
          type="checkbox"
          checked={value.includes(n.id)}
          onChange={() => toggle(n.id)}
          data-testid={`${testIdPrefix}-toggle-${n.slug}`}
        />
        <span className="flex-1 truncate">{n.name}</span>
      </label>
      {n.children?.map((c) => renderNode(c, depth + 1))}
    </div>
  );

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map((id) => {
          const n = flat[id];
          if (!n) return null;
          return (
            <Badge
              key={id} variant="secondary"
              className="gap-1 pr-1"
              data-testid={`${testIdPrefix}-chip-${n.slug}`}
              title={n.path_names?.join(" › ")}
            >
              <span>{n.name}</span>
              <button
                type="button" onClick={() => toggle(id)}
                className="hover:text-destructive"
                aria-label="Remove"
              >
                <X className="w-3 h-3" />
              </button>
            </Badge>
          );
        })}
      </div>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button" variant="outline" size="sm"
            data-testid={`${testIdPrefix}-open`}
          >
            <ChevronDown className="w-3.5 h-3.5 mr-1" />
            {value.length ? `${value.length} selected` : "Pick categories"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[300px] max-h-[320px] overflow-y-auto p-1" align="start">
          {tree.length === 0 ? (
            <div className="text-xs text-muted-foreground p-3">No categories yet.</div>
          ) : (
            tree.map((n) => renderNode(n, 0))
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}

/** Category filter (single-select) — includes descendants when filtering. */
export function CategoryFilter({ entityTypeId, value, onChange, testId = "cat-filter" }) {
  const [tree, setTree] = useState([]);
  const [flat, setFlat] = useState({});
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!entityTypeId) return;
    api.get(`/entity-types/${entityTypeId}/categories`).then((r) => {
      setTree(r.data);
      const map = {};
      const walk = (nodes) => nodes.forEach((n) => {
        map[n.id] = n;
        if (n.children) walk(n.children);
      });
      walk(r.data);
      setFlat(map);
    }).catch(() => {});
  }, [entityTypeId]);

  const renderNode = (n, depth) => (
    <div key={n.id}>
      <button
        type="button"
        className={`w-full text-left flex items-center gap-1 px-2 py-1.5 rounded text-sm hover:bg-muted ${
          value === n.id ? "bg-primary/10 text-primary font-medium" : ""
        }`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => { onChange(n.id); setOpen(false); }}
        data-testid={`${testId}-option-${n.slug}`}
      >
        <ChevronRight className="w-3 h-3 opacity-40" />
        <span>{n.name}</span>
      </button>
      {n.children?.map((c) => renderNode(c, depth + 1))}
    </div>
  );

  const selected = value && flat[value];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" data-testid={testId}>
          {selected ? (selected.path_names?.join(" › ") || selected.name) : "All categories"}
          <ChevronDown className="w-3.5 h-3.5 ml-1.5 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] max-h-[320px] overflow-y-auto p-1" align="start">
        <button
          type="button"
          className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-muted"
          onClick={() => { onChange(null); setOpen(false); }}
          data-testid={`${testId}-clear`}
        >
          All categories
        </button>
        <div className="h-px bg-border my-1" />
        {tree.map((n) => renderNode(n, 0))}
      </PopoverContent>
    </Popover>
  );
}
