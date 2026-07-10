import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Copy, Mail, Send, X, Check, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { useAuth } from "@/lib/auth";

const ROLE_OPTIONS = [
  { value: "admin", label: "Admin — manage settings, members, everything" },
  { value: "editor", label: "Editor — create and edit items" },
  { value: "viewer", label: "Viewer — read-only" },
];

const EXPIRY_OPTIONS = [
  { value: 1, label: "1 day" },
  { value: 3, label: "3 days" },
  { value: 7, label: "7 days (default)" },
  { value: 14, label: "14 days" },
  { value: 30, label: "30 days" },
];

/**
 * InviteModal — bulk-invite users to the active org.
 * Supports comma / newline / space separated emails.
 */
export function InviteModal({ open, onOpenChange, onInvited, prefillRole = "editor" }) {
  const { activeOrgId, activeRole } = useAuth();
  const [rawEmails, setRawEmails] = useState("");
  const [role, setRole] = useState(prefillRole);
  const [expires, setExpires] = useState(7);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState(null);

  const canInviteAdmin = activeRole === "owner";
  const roleOptions = canInviteAdmin
    ? ROLE_OPTIONS
    : ROLE_OPTIONS.filter((r) => r.value !== "admin");

  useEffect(() => {
    if (open) {
      setRawEmails("");
      setRole(prefillRole || "editor");
      setExpires(7);
      setResults(null);
    }
  }, [open, prefillRole]);

  const parseEmails = (raw) => {
    return [
      ...new Set(
        (raw || "")
          .split(/[\s,;\n]+/)
          .map((s) => s.trim().toLowerCase())
          .filter(Boolean)
      ),
    ];
  };

  const emails = parseEmails(rawEmails);

  const submit = async () => {
    if (emails.length === 0) {
      toast.error("Enter at least one email address");
      return;
    }
    if (emails.length > 50) {
      toast.error("At most 50 emails per invite batch");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post(`/orgs/${activeOrgId}/invitations`, {
        emails, role_name: role, expires_in_days: expires,
      });
      setResults(res.data.invitations || []);
      const okCount = (res.data.invitations || []).filter(
        (i) => i.status === "pending",
      ).length;
      if (okCount > 0) toast.success(`Sent ${okCount} invitation${okCount === 1 ? "" : "s"}`);
      onInvited?.();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const copyLink = async (url) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Invite URL copied");
    } catch {
      toast.error("Couldn't copy — long-press the link instead");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="invite-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="w-4 h-4 text-primary" /> Invite people
          </DialogTitle>
        </DialogHeader>

        {results === null ? (
          <div className="space-y-4 py-2">
            <div>
              <Label className="text-sm">Email addresses</Label>
              <textarea
                value={rawEmails}
                onChange={(e) => setRawEmails(e.target.value)}
                placeholder={"anna@company.com, bob@company.com\ncarol@company.com"}
                rows={4}
                className="w-full rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 resize-y"
                data-testid="invite-emails-input"
              />
              {emails.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2" data-testid="invite-emails-chips">
                  {emails.slice(0, 12).map((e) => (
                    <span key={e}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-mono">
                      <Mail className="w-3 h-3" /> {e}
                    </span>
                  ))}
                  {emails.length > 12 && (
                    <span className="text-xs text-muted-foreground">+{emails.length - 12} more</span>
                  )}
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-1">
                Separate emails with comma, space, or newline. Up to 50 per batch.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Role</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {roleOptions.map((r) => (
                      <SelectItem key={r.value} value={r.value} data-testid={`invite-role-${r.value}`}>
                        {r.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm">Link expires</Label>
                <Select value={String(expires)} onValueChange={(v) => setExpires(Number(v))}>
                  <SelectTrigger data-testid="invite-expiry-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {EXPIRY_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-2 max-h-[400px] overflow-y-auto space-y-2" data-testid="invite-results">
            {results.map((r, i) => (
              <InviteResultRow key={r.id || r.email || i} result={r} onCopy={copyLink} />
            ))}
          </div>
        )}

        <DialogFooter>
          {results === null ? (
            <>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={submit} disabled={busy || emails.length === 0}
                data-testid="invite-send-btn">
                {busy ? "Sending…" : `Send ${emails.length || ""} invitation${emails.length === 1 ? "" : "s"}`}
              </Button>
            </>
          ) : (
            <Button onClick={() => onOpenChange(false)} data-testid="invite-done-btn">Done</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InviteResultRow({ result, onCopy }) {
  const ok = result.status === "pending";
  const dup = result.code === "duplicate_pending" || result.code === "already_member";
  const provider = result.email_delivery?.provider;
  const providerOk = result.email_delivery?.ok;
  return (
    <div
      className={`rounded-md border p-2.5 flex items-start gap-2 ${
        ok ? "border-emerald-300 bg-emerald-50" : dup ? "border-amber-300 bg-amber-50" : "border-destructive/30 bg-destructive/5"
      }`}
      data-testid={`invite-result-${result.email}`}
    >
      <div className="mt-0.5 shrink-0">
        {ok ? (
          <Check className="w-4 h-4 text-emerald-700" />
        ) : dup ? (
          <AlertCircle className="w-4 h-4 text-amber-700" />
        ) : (
          <X className="w-4 h-4 text-destructive" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{result.email}</div>
        {ok ? (
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            <Badge variant="secondary" className="text-[10px]">{result.role_name}</Badge>
            {provider === "dev" && (
              <Badge className="text-[10px] bg-amber-100 text-amber-800 border-transparent">
                dev mode (no email sent)
              </Badge>
            )}
            {providerOk && provider !== "dev" && (
              <Badge className="text-[10px] bg-emerald-100 text-emerald-800 border-transparent">
                sent via {provider}
              </Badge>
            )}
            <Button
              variant="ghost" size="sm"
              className="ml-auto h-6 px-2 text-xs"
              onClick={() => onCopy(result.accept_url)}
              data-testid={`invite-copy-${result.email}`}
            >
              <Copy className="w-3 h-3 mr-1" /> Copy link
            </Button>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground mt-0.5">
            {result.detail || result.code || "Failed"}
          </div>
        )}
      </div>
    </div>
  );
}
