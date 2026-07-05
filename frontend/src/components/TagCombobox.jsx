import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Plus, X, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";

/** Autocomplete combobox for tags with inline "create new". */
export function TagCombobox({ entityTypeId, value = [], onChange, testIdPrefix = "tag-picker" }) {
  const [available, setAvailable] = useState([]); // full list
  const [byId, setById] = useState({});
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      const r = await api.get("/tags", { params: { entity_type_id: entityTypeId || undefined } });
      setAvailable(r.data);
      setById(Object.fromEntries(r.data.map((t) => [t.id, t])));
    } catch (e) { /* ignore */ }
  };
  useEffect(() => { load(); }, [entityTypeId]);

  const filtered = useMemo(() => {
    const lower = q.toLowerCase().trim();
    return available.filter((t) => !value.includes(t.id) &&
      (!lower || t.name.toLowerCase().includes(lower)));
  }, [available, value, q]);

  const exact = q.trim() && !available.find(
    (t) => t.name.toLowerCase() === q.trim().toLowerCase(),
  );

  const add = (tagId) => {
    if (!value.includes(tagId)) onChange([...value, tagId]);
    setQ("");
  };

  const remove = (tagId) => onChange(value.filter((x) => x !== tagId));

  const createInline = async () => {
    try {
      const r = await api.post("/tags", {
        name: q.trim(),
        entity_type_id: entityTypeId || null,
      });
      setById((p) => ({ ...p, [r.data.id]: r.data }));
      setAvailable((p) => [...p, r.data]);
      add(r.data.id);
      toast.success(`Tag '${r.data.name}' created`);
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map((id) => {
          const t = byId[id];
          if (!t) return null;
          return (
            <Badge
              key={id}
              className="gap-1 pr-1 border-transparent"
              style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
              data-testid={`${testIdPrefix}-chip-${t.slug}`}
            >
              <span>{t.name}</span>
              <button type="button" onClick={() => remove(id)} className="hover:text-destructive" aria-label="Remove">
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
            <ChevronDown className="w-3.5 h-3.5 mr-1" /> Add tag
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[280px] p-2" align="start">
          <Input
            placeholder="Search or create…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid={`${testIdPrefix}-search`}
          />
          <div className="mt-2 max-h-[240px] overflow-y-auto space-y-0.5">
            {filtered.map((t) => (
              <button
                key={t.id}
                type="button"
                className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-muted flex items-center gap-2"
                onClick={() => add(t.id)}
                data-testid={`${testIdPrefix}-suggest-${t.slug}`}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: t.color || "#0d9488" }}
                />
                <span>{t.name}</span>
                <span className="ml-auto text-[10px] font-mono text-muted-foreground">
                  {t.usage_count}
                </span>
              </button>
            ))}
            {exact && (
              <button
                type="button"
                className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-primary/10 text-primary flex items-center gap-2"
                onClick={createInline}
                data-testid={`${testIdPrefix}-create`}
              >
                <Plus className="w-3.5 h-3.5" />
                Create "{q.trim()}"
              </button>
            )}
            {filtered.length === 0 && !exact && (
              <div className="text-xs text-muted-foreground px-2 py-3">Type to search or create.</div>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
