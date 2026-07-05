import { useEffect, useState } from "react";
import { Send, X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * AfterImportNudge — small dismissable card shown when the user has completed
 * a large (≥50 rows) import recently. Opens the invite modal on click.
 */
export function AfterImportNudge({ onInviteClick }) {
  const [state, setState] = useState({ show: false, rows: 0, loaded: false });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get("/nudges/invite-after-import");
        if (!cancelled) setState({ show: !!r.data.show, rows: r.data.rows || 0, loaded: true });
      } catch {
        if (!cancelled) setState({ show: false, rows: 0, loaded: true });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const dismiss = async () => {
    setState((s) => ({ ...s, show: false }));
    try {
      await api.post("/users/me/dismissed-prompts", { prompt_key: "invite_after_import" });
    } catch {
      /* not fatal */
    }
  };

  if (!state.show) return null;

  return (
    <div
      className="rounded-lg border border-primary/30 bg-primary/5 p-4 flex items-start gap-3 mb-4"
      data-testid="after-import-nudge"
    >
      <div className="w-9 h-9 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0 mt-0.5">
        <Send className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium">
          You just imported {state.rows.toLocaleString()} records — invite a teammate to help manage them.
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          Share the workload. Invitations expire in 7 days by default.
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Button
            size="sm"
            onClick={onInviteClick}
            data-testid="nudge-invite-btn"
          >
            <Send className="w-3.5 h-3.5 mr-1.5" /> Invite by email
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={dismiss}
            data-testid="nudge-dismiss-btn"
          >
            Dismiss
          </Button>
        </div>
      </div>
      <button
        type="button"
        onClick={dismiss}
        className="p-1 text-muted-foreground hover:text-foreground"
        aria-label="Dismiss"
        data-testid="nudge-dismiss-x"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
