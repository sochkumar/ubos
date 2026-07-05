import { useState, useMemo } from "react";
import { Calendar as CalendarIcon, X, Clock } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/* Cross-browser date & datetime pickers (Phase 6-A).
 * Replaces native <input type="date/datetime-local"> which renders
 * inconsistently across Firefox, Safari, and Chromium. */

function parseYmd(v) {
  if (!v) return null;
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if (isNaN(d.getTime())) return null;
  return d;
}
function toYmd(d) {
  if (!d) return "";
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function formatLocaleDate(d) {
  if (!d) return "";
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(d);
  } catch {
    return toYmd(d);
  }
}

/**
 * DatePicker — controlled. `value` and `onChange` speak ISO YYYY-MM-DD strings
 * (or null). Uses shadcn Calendar under a Popover.
 */
export function DatePicker({
  value, onChange, id, testId, placeholder = "Pick a date",
  disabled = false, minDate, maxDate, required,
}) {
  const [open, setOpen] = useState(false);
  const parsed = useMemo(() => parseYmd(value), [value]);
  const label = parsed ? formatLocaleDate(parsed) : "";

  const handleSelect = (d) => {
    if (!d) {
      onChange(null);
      return;
    }
    // Normalize to UTC midnight (matches ISO YYYY-MM-DD serialization).
    const utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    onChange(toYmd(utc));
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          id={id}
          data-testid={testId}
          disabled={disabled}
          className={cn(
            "w-full h-10 px-3 rounded-md border border-input bg-transparent text-sm",
            "flex items-center gap-2 justify-between text-left",
            "hover:border-primary/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
            !parsed && "text-muted-foreground",
            disabled && "opacity-50 cursor-not-allowed",
          )}
        >
          <span className="flex items-center gap-2 flex-1 truncate">
            <CalendarIcon className="w-4 h-4 text-muted-foreground shrink-0" />
            <span className="truncate">{label || placeholder}</span>
          </span>
          {parsed && !required && !disabled && (
            <span
              role="button"
              tabIndex={-1}
              className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                onChange(null);
              }}
              aria-label="Clear date"
              data-testid={testId ? `${testId}-clear` : "date-clear"}
            >
              <X className="w-3.5 h-3.5" />
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0" data-testid={testId ? `${testId}-popover` : "date-popover"}>
        <Calendar
          mode="single"
          selected={parsed}
          onSelect={handleSelect}
          initialFocus
          fromDate={minDate}
          toDate={maxDate}
        />
        <div className="flex items-center justify-between border-t border-border p-2 gap-2">
          <Button
            variant="ghost" size="sm" className="text-xs h-7"
            onClick={() => handleSelect(new Date())}
            data-testid={testId ? `${testId}-today` : "date-today"}
          >
            Today
          </Button>
          {parsed && !required && (
            <Button
              variant="ghost" size="sm" className="text-xs h-7 text-destructive"
              onClick={() => { onChange(null); setOpen(false); }}
              data-testid={testId ? `${testId}-clear-btn` : "date-clear-btn"}
            >
              Clear
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * DateTimePicker — value/onChange are ISO datetime strings.
 * On save we serialize as UTC ISO ("YYYY-MM-DDTHH:MM:00.000Z") so backend
 * datetime coercion stays timezone-explicit.
 */
export function DateTimePicker({
  value, onChange, id, testId, placeholder = "Pick date & time",
  disabled = false, required,
}) {
  const [open, setOpen] = useState(false);

  const parsed = useMemo(() => {
    if (!value) return null;
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }, [value]);

  const timeVal = useMemo(() => {
    if (!parsed) return "";
    // Show in the user's local timezone for editing
    const h = String(parsed.getHours()).padStart(2, "0");
    const m = String(parsed.getMinutes()).padStart(2, "0");
    return `${h}:${m}`;
  }, [parsed]);

  const label = useMemo(() => {
    if (!parsed) return "";
    try {
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium", timeStyle: "short",
      }).format(parsed);
    } catch {
      return parsed.toISOString();
    }
  }, [parsed]);

  const commit = (d) => {
    if (!d) { onChange(null); return; }
    onChange(d.toISOString());
  };

  const handleDay = (d) => {
    if (!d) { commit(null); return; }
    const base = parsed || new Date();
    // Keep the existing time-of-day if present, else default 09:00
    const nd = new Date(
      d.getFullYear(), d.getMonth(), d.getDate(),
      parsed ? base.getHours() : 9,
      parsed ? base.getMinutes() : 0,
      0, 0,
    );
    commit(nd);
  };

  const handleTime = (e) => {
    const [hh, mm] = (e.target.value || "").split(":").map((s) => Number(s));
    if (Number.isNaN(hh) || Number.isNaN(mm)) return;
    const base = parsed || new Date();
    const nd = new Date(
      base.getFullYear(), base.getMonth(), base.getDate(),
      hh, mm, 0, 0,
    );
    commit(nd);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          id={id}
          data-testid={testId}
          disabled={disabled}
          className={cn(
            "w-full h-10 px-3 rounded-md border border-input bg-transparent text-sm",
            "flex items-center gap-2 justify-between text-left",
            "hover:border-primary/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
            !parsed && "text-muted-foreground",
            disabled && "opacity-50 cursor-not-allowed",
          )}
        >
          <span className="flex items-center gap-2 flex-1 truncate">
            <CalendarIcon className="w-4 h-4 text-muted-foreground shrink-0" />
            <span className="truncate">{label || placeholder}</span>
          </span>
          {parsed && !required && !disabled && (
            <span
              role="button"
              tabIndex={-1}
              className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                onChange(null);
              }}
              aria-label="Clear datetime"
              data-testid={testId ? `${testId}-clear` : "dt-clear"}
            >
              <X className="w-3.5 h-3.5" />
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0" data-testid={testId ? `${testId}-popover` : "dt-popover"}>
        <Calendar
          mode="single"
          selected={parsed}
          onSelect={handleDay}
          initialFocus
        />
        <div className="border-t border-border p-2 flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <Input
            type="time"
            value={timeVal}
            onChange={handleTime}
            className="h-8 text-sm"
            data-testid={testId ? `${testId}-time` : "dt-time-input"}
          />
          <Button
            variant="ghost" size="sm" className="text-xs h-8 shrink-0"
            onClick={() => { commit(new Date()); setOpen(false); }}
            data-testid={testId ? `${testId}-now` : "dt-now"}
          >
            Now
          </Button>
          {parsed && !required && (
            <Button
              variant="ghost" size="sm" className="text-xs h-8 shrink-0 text-destructive"
              onClick={() => { onChange(null); setOpen(false); }}
              data-testid={testId ? `${testId}-clear-btn` : "dt-clear-btn"}
            >
              Clear
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
