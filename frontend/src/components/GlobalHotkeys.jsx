import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Keyboard } from "lucide-react";
import { useHotkeys, HOTKEY_META } from "@/hooks/useHotkeys";
import { api } from "@/lib/api";

const GROUPS = [
  {
    title: "Navigation",
    items: [
      { keys: ["g", "d"], label: "Go to Dashboard" },
      { keys: ["g", "r"], label: "Go to Records (current or first entity type)" },
      { keys: ["g", "s"], label: "Go to Search" },
      { keys: ["g", "m"], label: "Go to Media" },
    ],
  },
  {
    title: "Actions",
    items: [
      { keys: ["n"], label: "New record (on records list)" },
      { keys: ["e"], label: "Focus edit on record detail" },
    ],
  },
  {
    title: "Search / Palette",
    items: [
      { keys: [`${HOTKEY_META}`, "K"], label: "Open command palette" },
      { keys: [`${HOTKEY_META}`, "/"], label: "Open keyboard shortcuts" },
    ],
  },
  {
    title: "Misc",
    items: [
      { keys: ["?"], label: "Open this help panel" },
      { keys: ["Esc"], label: "Close any modal, drawer, or popover" },
    ],
  },
];

function Key({ children }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 text-[11px] font-mono rounded border border-border bg-muted/40 text-foreground/80">
      {children}
    </kbd>
  );
}

/** Registers the global hotkeys and mounts the shortcuts help dialog. */
export function GlobalHotkeys() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);

  useHotkeys("mod+/", () => setOpen(true));
  useHotkeys("?", () => setOpen(true));
  useHotkeys("g d", () => nav("/dashboard"));
  useHotkeys("g s", () => nav("/search"));
  useHotkeys("g m", () => nav("/media"));
  useHotkeys("g r", async () => {
    try {
      const r = await api.get("/entity-types");
      const first = (r.data || [])[0];
      if (first) nav(`/entity-types/${first.id}/records`);
      else nav("/entity-types");
    } catch {
      nav("/entity-types");
    }
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-lg" data-testid="shortcuts-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="w-4 h-4" />
            Keyboard shortcuts
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2 max-h-[500px] overflow-y-auto">
          {GROUPS.map((g) => (
            <section key={g.title} data-testid={`shortcut-group-${g.title.toLowerCase()}`}>
              <div className="text-[10px] font-mono uppercase text-muted-foreground mb-2 tracking-wider">
                {g.title}
              </div>
              <ul className="rounded-md border border-border divide-y divide-border overflow-hidden">
                {g.items.map((it, i) => (
                  <li key={i} className="px-3 py-2 flex items-center justify-between text-sm">
                    <span className="text-foreground/90">{it.label}</span>
                    <span className="flex items-center gap-1">
                      {it.keys.map((k, j) => (
                        <span key={j} className="flex items-center gap-1">
                          {j > 0 && <span className="text-muted-foreground text-xs">then</span>}
                          <Key>{k}</Key>
                        </span>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <div className="text-[10px] text-muted-foreground text-center pt-1">
            Shortcuts are disabled while typing in an input.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
