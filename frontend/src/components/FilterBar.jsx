import { useState } from "react";
import { Plus, X, ArrowUpDown, ArrowUp, ArrowDown, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { OP_LABELS, opsForField, needsValue, isRangeOp, isListOp } from "@/lib/filterOps";
import { DatePicker, DateTimePicker } from "@/components/DatePicker";

const SYSTEM_FIELDS = [
  { key: "title", label: "Title", type: "text" },
  { key: "record_number", label: "Record #", type: "text" },
  { key: "created_at", label: "Created", type: "datetime" },
  { key: "updated_at", label: "Updated", type: "datetime" },
];

function fieldDefsWithSystem(fields) {
  return [...SYSTEM_FIELDS, ...fields.map((f) => ({ key: f.key, label: f.label, type: f.type, config: f.config }))];
}

function ValueInput({ field, op, value, onChange }) {
  const isDate = field.type === "date";
  const isDT = field.type === "datetime";

  if (isRangeOp(op)) {
    const [lo, hi] = Array.isArray(value) ? value : ["", ""];
    if (isDate) {
      return (
        <div className="flex items-center gap-1.5">
          <div className="w-[150px]">
            <DatePicker value={lo ?? null} onChange={(v) => onChange([v, hi])}
              testId="filter-value-lo" placeholder="from" />
          </div>
          <span className="text-xs text-muted-foreground">→</span>
          <div className="w-[150px]">
            <DatePicker value={hi ?? null} onChange={(v) => onChange([lo, v])}
              testId="filter-value-hi" placeholder="to" />
          </div>
        </div>
      );
    }
    if (isDT) {
      return (
        <div className="flex items-center gap-1.5">
          <div className="w-[180px]">
            <DateTimePicker value={lo ?? null} onChange={(v) => onChange([v, hi])}
              testId="filter-value-lo" placeholder="from" />
          </div>
          <span className="text-xs text-muted-foreground">→</span>
          <div className="w-[180px]">
            <DateTimePicker value={hi ?? null} onChange={(v) => onChange([lo, v])}
              testId="filter-value-hi" placeholder="to" />
          </div>
        </div>
      );
    }
    const type = (field.type === "number" || field.type === "currency") ? "number" : "text";
    return (
      <div className="flex items-center gap-1.5">
        <Input value={lo ?? ""} type={type} placeholder="from"
          onChange={(e) => onChange([e.target.value, hi])}
          data-testid="filter-value-lo" className="h-8 text-xs" />
        <span className="text-xs text-muted-foreground">→</span>
        <Input value={hi ?? ""} type={type} placeholder="to"
          onChange={(e) => onChange([lo, e.target.value])}
          data-testid="filter-value-hi" className="h-8 text-xs" />
      </div>
    );
  }
  if (isListOp(op)) {
    // dropdown / multi_select: show configured options as multi-check
    const opts = (field.config?.options || []).map((o) => typeof o === "string" ? { value: o, label: o } : o);
    const selected = Array.isArray(value) ? value : [];
    const toggle = (v) => onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
    if (opts.length) {
      return (
        <div className="flex flex-wrap gap-1.5 max-w-[240px]">
          {opts.map((o) => {
            const on = selected.includes(o.value);
            return (
              <button
                type="button" key={o.value}
                onClick={() => toggle(o.value)}
                className={`text-xs px-2 py-1 rounded-full border transition-colors ${on ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted"}`}
                data-testid={`filter-opt-${o.value}`}
              >{o.label}</button>
            );
          })}
        </div>
      );
    }
    return (
      <Input
        value={Array.isArray(value) ? value.join(", ") : ""}
        placeholder="comma-separated"
        onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
        className="h-8 text-xs" data-testid="filter-value-list"
      />
    );
  }
  if (field.type === "boolean") {
    return (
      <Select value={String(value ?? "true")} onValueChange={(v) => onChange(v === "true")}>
        <SelectTrigger className="h-8 text-xs w-24" data-testid="filter-value-bool">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">true</SelectItem>
          <SelectItem value="false">false</SelectItem>
        </SelectContent>
      </Select>
    );
  }
  if (field.type === "dropdown" && (field.config?.options || []).length) {
    const opts = field.config.options.map((o) => typeof o === "string" ? { value: o, label: o } : o);
    return (
      <Select value={value ?? ""} onValueChange={onChange}>
        <SelectTrigger className="h-8 text-xs w-40" data-testid="filter-value-dd">
          <SelectValue placeholder="value" />
        </SelectTrigger>
        <SelectContent>
          {opts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    );
  }
  if (field.type === "date") {
    return (
      <div className="w-[180px]">
        <DatePicker value={value ?? null} onChange={onChange} testId="filter-value" />
      </div>
    );
  }
  if (field.type === "datetime") {
    return (
      <div className="w-[220px]">
        <DateTimePicker value={value ?? null} onChange={onChange} testId="filter-value" />
      </div>
    );
  }
  const type =
    field.type === "number" || field.type === "currency" ? "number"
    : field.type === "email" ? "email"
    : field.type === "url" ? "url"
    : "text";
  return (
    <Input value={value ?? ""} type={type}
      onChange={(e) => {
        if (type === "number") onChange(e.target.value === "" ? "" : Number(e.target.value));
        else onChange(e.target.value);
      }}
      className="h-8 text-xs" data-testid="filter-value" />
  );
}

function AddFilterPopover({ fields, onAdd }) {
  const [open, setOpen] = useState(false);
  const [fkey, setFkey] = useState(null);
  const [op, setOp] = useState(null);
  const [value, setValue] = useState("");
  const all = fieldDefsWithSystem(fields);
  const fdef = all.find((f) => f.key === fkey);
  const validOps = fdef ? opsForField(fdef.type) : [];

  const reset = () => { setFkey(null); setOp(null); setValue(""); };
  const commit = () => {
    if (!fkey || !op) return;
    onAdd({ field: fkey, op, value: needsValue(op) ? value : null });
    setOpen(false);
    reset();
  };

  return (
    <Popover open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs" data-testid="add-filter-btn">
          <Plus className="w-3 h-3 mr-1" /> Add filter
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[380px] p-3 space-y-2" align="start">
        <div>
          <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1">Field</div>
          <Select value={fkey || ""} onValueChange={(v) => { setFkey(v); setOp(null); setValue(""); }}>
            <SelectTrigger className="h-8 text-xs" data-testid="filter-field">
              <SelectValue placeholder="Pick a field" />
            </SelectTrigger>
            <SelectContent className="max-h-[280px]">
              {all.map((f) => (
                <SelectItem key={f.key} value={f.key} data-testid={`filter-field-opt-${f.key}`}>
                  {f.label} <span className="text-[10px] font-mono text-muted-foreground ml-1">{f.type}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {fdef && (
          <div>
            <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1">Operator</div>
            <Select value={op || ""} onValueChange={setOp}>
              <SelectTrigger className="h-8 text-xs" data-testid="filter-op">
                <SelectValue placeholder="Operator" />
              </SelectTrigger>
              <SelectContent>
                {validOps.map((o) => (
                  <SelectItem key={o} value={o} data-testid={`filter-op-${o}`}>{OP_LABELS[o] || o}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {fdef && op && needsValue(op) && (
          <div>
            <div className="text-[10px] font-mono uppercase text-muted-foreground mb-1">Value</div>
            <ValueInput field={fdef} op={op} value={value} onChange={setValue} />
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button size="sm" disabled={!fkey || !op} onClick={commit} data-testid="filter-apply">Apply</Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function SortPopover({ fields, sort, onChange }) {
  const [open, setOpen] = useState(false);
  const all = fieldDefsWithSystem(fields);
  const [tmp, setTmp] = useState(sort || []);
  const addSort = () => setTmp([...tmp, { field: "created_at", dir: "desc" }]);
  const setDir = (i, d) => setTmp(tmp.map((s, j) => j === i ? { ...s, dir: d } : s));
  const setField = (i, f) => setTmp(tmp.map((s, j) => j === i ? { ...s, field: f } : s));
  const remove = (i) => setTmp(tmp.filter((_, j) => j !== i));
  const apply = () => { onChange(tmp); setOpen(false); };

  return (
    <Popover open={open} onOpenChange={(v) => { setOpen(v); if (v) setTmp(sort || []); }}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs" data-testid="sort-btn">
          <ArrowUpDown className="w-3 h-3 mr-1" /> Sort {sort?.length ? `· ${sort.length}` : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[380px] p-3 space-y-2" align="start">
        {tmp.length === 0 && (
          <p className="text-xs text-muted-foreground py-2">No sort — records default to newest first.</p>
        )}
        {tmp.map((s, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <Select value={s.field} onValueChange={(v) => setField(i, v)}>
              <SelectTrigger className="h-8 text-xs flex-1" data-testid={`sort-field-${i}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-[280px]">
                {all.map((f) => (
                  <SelectItem key={f.key} value={f.key}>{f.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="icon" variant="outline"
              className="h-8 w-8"
              onClick={() => setDir(i, s.dir === "asc" ? "desc" : "asc")}
              data-testid={`sort-dir-${i}`}
            >
              {s.dir === "asc" ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />}
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={() => remove(i)} data-testid={`sort-remove-${i}`}>
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        ))}
        <div className="flex justify-between items-center pt-1">
          <Button size="sm" variant="outline" onClick={addSort} data-testid="sort-add"><Plus className="w-3 h-3 mr-1" /> Add sort</Button>
          <Button size="sm" onClick={apply} data-testid="sort-apply">Apply</Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function FilterChip({ chip, allFields, onRemove }) {
  const fdef = allFields.find((f) => f.key === chip.field);
  const label = fdef?.label || chip.field;
  const opLabel = OP_LABELS[chip.op] || chip.op;
  let valStr = "";
  if (needsValue(chip.op)) {
    if (Array.isArray(chip.value)) valStr = chip.value.join(isRangeOp(chip.op) ? " → " : ", ");
    else if (chip.value === true || chip.value === false) valStr = String(chip.value);
    else valStr = String(chip.value ?? "");
  }
  return (
    <Badge variant="secondary" className="gap-1 pr-1 font-normal" data-testid={`filter-chip-${chip.field}`}>
      <span className="font-medium">{label}</span>
      <span className="text-muted-foreground">{opLabel}</span>
      {valStr && <span className="font-mono text-[10px] max-w-[140px] truncate">{valStr}</span>}
      <button type="button" className="hover:text-destructive" onClick={onRemove} aria-label="Remove filter">
        <X className="w-3 h-3" />
      </button>
    </Badge>
  );
}

export function FilterBar({ fields, filters, sort, onFiltersChange, onSortChange }) {
  const allFields = fieldDefsWithSystem(fields);
  const removeAt = (i) => onFiltersChange(filters.filter((_, j) => j !== i));
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[10px] font-mono uppercase text-muted-foreground">Filters</span>
      {filters.map((c, i) => (
        <FilterChip key={i} chip={c} allFields={allFields} onRemove={() => removeAt(i)} />
      ))}
      <AddFilterPopover fields={fields} onAdd={(f) => onFiltersChange([...filters, f])} />
      <span className="mx-1 text-border">·</span>
      <SortPopover fields={fields} sort={sort} onChange={onSortChange} />
    </div>
  );
}
