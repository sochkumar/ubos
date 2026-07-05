import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";

/**
 * Renders a single input for a field_definition.
 *
 * Props:
 *  - field: field_definition object
 *  - value: current value
 *  - onChange(next): update handler
 *  - error: string | null
 */
export function DynamicField({ field, value, onChange, error }) {
  const id = `field-${field.key}`;
  const testId = `input-${field.key}`;

  const label = (
    <div className="flex items-center justify-between gap-2 mb-1.5">
      <Label htmlFor={id} className="text-sm font-medium">
        {field.label}
        {field.required && (
          <span className="text-destructive ml-1" aria-hidden>
            *
          </span>
        )}
      </Label>
      <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wide">
        {field.type}
        {field.unique ? " · unique" : ""}
      </span>
    </div>
  );

  const errNode = error ? (
    <p
      className="text-xs text-destructive mt-1.5"
      data-testid={`error-${field.key}`}
    >
      {error}
    </p>
  ) : field.help_text ? (
    <p className="text-xs text-muted-foreground mt-1.5">{field.help_text}</p>
  ) : null;

  const renderControl = () => {
    switch (field.type) {
      case "longtext":
      case "richtext":
        return (
          <Textarea
            id={id}
            data-testid={testId}
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value)}
            rows={field.type === "richtext" ? 5 : 3}
          />
        );
      case "number":
      case "currency":
        return (
          <Input
            id={id}
            data-testid={testId}
            type="number"
            step="any"
            value={value ?? ""}
            onChange={(e) =>
              onChange(e.target.value === "" ? null : e.target.value)
            }
          />
        );
      case "boolean":
        return (
          <div className="flex items-center gap-2 h-10">
            <Switch
              id={id}
              data-testid={testId}
              checked={!!value}
              onCheckedChange={(v) => onChange(v)}
            />
            <span className="text-sm text-muted-foreground">
              {value ? "Yes" : "No"}
            </span>
          </div>
        );
      case "date":
        return (
          <Input
            id={id}
            data-testid={testId}
            type="date"
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value || null)}
          />
        );
      case "datetime":
        return (
          <Input
            id={id}
            data-testid={testId}
            type="datetime-local"
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value || null)}
          />
        );
      case "dropdown": {
        const options = (field.config?.options || []).map((o) =>
          typeof o === "string" ? { value: o, label: o } : o,
        );
        return (
          <Select
            value={value ?? ""}
            onValueChange={(v) => onChange(v)}
          >
            <SelectTrigger id={id} data-testid={testId}>
              <SelectValue placeholder="Choose an option" />
            </SelectTrigger>
            <SelectContent>
              {options.map((o) => (
                <SelectItem key={o.value} value={o.value} data-testid={`option-${field.key}-${o.value}`}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      }
      case "multi_select": {
        const options = (field.config?.options || []).map((o) =>
          typeof o === "string" ? { value: o, label: o } : o,
        );
        const selected = Array.isArray(value) ? value : [];
        const toggle = (v) => {
          if (selected.includes(v)) onChange(selected.filter((x) => x !== v));
          else onChange([...selected, v]);
        };
        return (
          <div className="grid grid-cols-2 gap-2 rounded-md border border-border p-3" data-testid={testId}>
            {options.length === 0 && (
              <span className="text-xs text-muted-foreground col-span-2">
                No options configured
              </span>
            )}
            {options.map((o) => (
              <label
                key={o.value}
                className="flex items-center gap-2 text-sm cursor-pointer"
              >
                <Checkbox
                  checked={selected.includes(o.value)}
                  onCheckedChange={() => toggle(o.value)}
                  data-testid={`multi-${field.key}-${o.value}`}
                />
                {o.label}
              </label>
            ))}
          </div>
        );
      }
      case "email":
      case "url":
      case "phone":
      case "text":
        return (
          <Input
            id={id}
            data-testid={testId}
            type={
              field.type === "email"
                ? "email"
                : field.type === "url"
                ? "url"
                : field.type === "phone"
                ? "tel"
                : "text"
            }
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        );
      case "image":
      case "file":
      case "relation":
        return (
          <Input
            id={id}
            data-testid={testId}
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value)}
            placeholder={`(${field.type} — Phase 3, stub input)`}
          />
        );
      default:
        return (
          <Input
            id={id}
            data-testid={testId}
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        );
    }
  };

  return (
    <div data-testid={`field-${field.key}`}>
      {label}
      {renderControl()}
      {errNode}
    </div>
  );
}
