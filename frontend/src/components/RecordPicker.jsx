import { useEffect, useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

/**
 * Picker for choosing one/many records of a given entity_type.
 *
 * Props:
 *  - open, onOpenChange
 *  - entityTypeId — entity type to pick from
 *  - excludeIds — array of ids already linked (rendered disabled)
 *  - multiple — allow multi-select?
 *  - title
 *  - onPick(ids[]) — called with the selected record ids on submit
 */
export function RecordPicker({
  open, onOpenChange, entityTypeId, excludeIds = [], multiple = true,
  title = "Pick records", onPick,
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const excluded = useMemo(() => new Set(excludeIds), [excludeIds]);

  useEffect(() => {
    if (!open || !entityTypeId) return;
    setLoading(true);
    api.post(`/entity-types/${entityTypeId}/records/search`, {
      q: q || null, limit: 100,
    }).then((r) => setItems(r.data.items || []))
      .finally(() => setLoading(false));
  }, [open, entityTypeId, q]);

  useEffect(() => {
    if (!open) setSelected(new Set());
  }, [open]);

  const toggle = (id) => {
    if (excluded.has(id)) return;
    setSelected((s) => {
      if (!multiple) return new Set([id]);
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const submit = () => {
    onPick && onPick([...selected]);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col" data-testid="record-picker">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search…" className="pl-8 h-9"
            data-testid="record-picker-search" />
        </div>
        <div className="flex-1 overflow-y-auto space-y-1 min-h-[200px]">
          {loading ? (
            <div className="text-sm text-muted-foreground py-6 text-center">Loading…</div>
          ) : items.length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">No matches</div>
          ) : items.map((r) => {
            const isExcluded = excluded.has(r.id);
            const isSelected = selected.has(r.id);
            return (
              <button key={r.id} type="button"
                disabled={isExcluded}
                onClick={() => toggle(r.id)}
                className={`w-full text-left flex items-center gap-2 px-2 py-2 rounded-md transition-colors ${isExcluded ? "opacity-40 cursor-not-allowed" : "hover:bg-muted"} ${isSelected ? "bg-primary/10" : ""}`}
                data-testid={`picker-row-${r.record_number}`}>
                {multiple && (
                  <Checkbox checked={isSelected} onCheckedChange={() => toggle(r.id)} disabled={isExcluded} />
                )}
                <div className="font-mono text-[10px] text-primary w-24 shrink-0">{r.record_number}</div>
                <div className="flex-1 min-w-0 text-sm truncate">{r.title || "—"}</div>
                {isExcluded && <span className="text-[10px] font-mono text-muted-foreground">already linked</span>}
              </button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={selected.size === 0} data-testid="record-picker-submit">
            {multiple ? `Link ${selected.size} record${selected.size === 1 ? "" : "s"}` : "Link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
