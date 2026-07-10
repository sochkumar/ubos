import { useEffect, useState } from "react";
import {
  Copy, Link as LinkIcon, Lock, Share2, ShieldOff, Trash2, Users, Plus,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { DatePicker } from "@/components/DatePicker";

function toDateInput(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
  } catch { return ""; }
}
function fromDateInput(v) {
  if (!v) return null;
  const [y, m, d] = v.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 23, 59, 59)).toISOString();
}

/** ViewShareDialog — creates & manages public / password / org-only view shares. */
export function ViewShareDialog({ open, onOpenChange, view, fields, onChanged }) {
  const [shares, setShares] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const load = async () => {
    if (!view) return;
    setLoading(true);
    try {
      const r = await api.get(`/views/${view.id}/shares`);
      setShares(r.data || []);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally { setLoading(false); }
  };
  useEffect(() => { if (open && view) load(); /* eslint-disable-next-line */ }, [open, view]);

  const copyLink = async (url) => {
    try { await navigator.clipboard.writeText(url); toast.success("Public URL copied"); }
    catch { toast.error("Couldn't copy"); }
  };
  const revoke = async (s) => {
    if (!window.confirm("Revoke this public link? The URL will stop working immediately.")) return;
    try { await api.post(`/shares/${s.id}/revoke`); toast.success("Link revoked"); await load(); onChanged?.(); }
    catch (e) { toast.error(extractErrorMessage(e)); }
  };
  const remove = async (s) => {
    if (!window.confirm("Permanently delete this share?")) return;
    try { await api.delete(`/shares/${s.id}`); toast.success("Share deleted"); await load(); onChanged?.(); }
    catch (e) { toast.error(extractErrorMessage(e)); }
  };

  if (!view) return null;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl" data-testid="view-share-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Share2 className="w-4 h-4 text-primary" /> Share view — {view.name}
            </DialogTitle>
          </DialogHeader>
          <div className="py-2 space-y-3">
            <Button
              size="sm" onClick={() => setCreateOpen(true)}
              data-testid="new-view-share-btn"
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" /> New public link
            </Button>
            <div className="space-y-2 max-h-[380px] overflow-y-auto" data-testid="view-shares-list">
              {loading ? (
                <div className="text-xs text-muted-foreground">Loading shares…</div>
              ) : shares.length === 0 ? (
                <div className="text-xs text-muted-foreground">
                  No public links yet. Create one to share this view outside the workspace.
                </div>
              ) : (
                shares.map((s) => (
                  <ViewShareRow key={s.id} share={s} onCopy={copyLink} onRevoke={revoke} onDelete={remove} />
                ))
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CreateViewShareDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        view={view}
        fields={fields}
        onCreated={() => { load(); onChanged?.(); }}
      />
    </>
  );
}

function ViewShareRow({ share, onCopy, onRevoke, onDelete }) {
  const revoked = !!share.revoked_at;
  return (
    <div
      className={`rounded border ${revoked ? "border-border/60 opacity-60" : "border-border"} bg-white p-2.5`}
      data-testid={`view-share-row-${share.token}`}
    >
      <div className="flex items-center gap-1.5 mb-1 flex-wrap">
        <Badge variant="secondary" className="text-[9px] font-mono uppercase">{share.visibility}</Badge>
        {share.has_password && (
          <Badge className="bg-amber-100 text-amber-800 border-transparent text-[9px] inline-flex items-center gap-0.5">
            <Lock className="w-2.5 h-2.5" /> password
          </Badge>
        )}
        {share.visible_columns?.length ? (
          <Badge className="text-[9px] border-transparent bg-muted text-muted-foreground">
            {share.visible_columns.length} column{share.visible_columns.length === 1 ? "" : "s"}
          </Badge>
        ) : null}
        {revoked && <Badge className="bg-destructive/15 text-destructive border-transparent text-[9px]">revoked</Badge>}
        <div className="ml-auto text-[10px] font-mono text-muted-foreground">
          {share.view_count || 0} views
        </div>
      </div>
      <div className="flex items-center gap-1">
        <a
          href={share.public_url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-xs font-mono truncate text-primary hover:underline flex-1"
          data-testid={`view-share-url-${share.token}`}
        >
          {share.public_url}
        </a>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onCopy(share.public_url)}
          data-testid={`view-share-copy-${share.token}`}>
          <Copy className="w-3.5 h-3.5" />
        </Button>
        {!revoked && (
          <Button variant="ghost" size="icon" className="h-7 w-7 text-amber-700" onClick={() => onRevoke(share)}
            data-testid={`view-share-revoke-${share.token}`} title="Revoke">
            <ShieldOff className="w-3.5 h-3.5" />
          </Button>
        )}
        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => onDelete(share)}
          data-testid={`view-share-delete-${share.token}`}>
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}

function CreateViewShareDialog({ open, onOpenChange, view, fields, onCreated }) {
  const [visibility, setVisibility] = useState("public");
  const [expires, setExpires] = useState("");
  const [password, setPassword] = useState("");
  const [includeMedia, setIncludeMedia] = useState(false);
  const [includeRels, setIncludeRels] = useState(false);
  const [restrictColumns, setRestrictColumns] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setVisibility("public");
      setExpires("");
      setPassword("");
      setIncludeMedia(false);
      setIncludeRels(false);
      // Default to the view's visible_fields when opening
      const seed = view?.visible_fields || [];
      setRestrictColumns(seed.length > 0);
      setVisibleColumns(seed);
    }
  }, [open, view]);

  const nonSensitive = (fields || []).filter(
    (f) => !f.sensitive && !["image", "file", "relation", "richtext"].includes(f.type),
  );

  const toggleCol = (key) => {
    setVisibleColumns((p) => p.includes(key) ? p.filter((x) => x !== key) : [...p, key]);
  };

  const submit = async () => {
    if (visibility === "password" && password.length < 8) {
      toast.error("Password must be at least 8 characters"); return;
    }
    setBusy(true);
    try {
      const body = {
        visibility,
        include_media: includeMedia,
        include_relationships: includeRels,
        expires_at: fromDateInput(expires),
      };
      if (visibility === "password") body.password = password;
      if (restrictColumns) body.visible_columns = visibleColumns;
      await api.post(`/views/${view.id}/shares`, body);
      toast.success("View share created");
      onCreated?.();
      onOpenChange(false);
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="create-view-share-dialog">
        <DialogHeader>
          <DialogTitle>New view share</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-sm">Visibility</Label>
            <Select value={visibility} onValueChange={setVisibility}>
              <SelectTrigger data-testid="view-share-visibility"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="public">Public — anyone with the link</SelectItem>
                <SelectItem value="password">Password protected</SelectItem>
                <SelectItem value="org_only">Organization only — must be signed in</SelectItem>
                <SelectItem value="private">Private — creator + admins only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {visibility === "password" && (
            <div>
              <Label className="text-sm">Password (min 8 chars)</Label>
              <Input
                type="password" value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password" placeholder="At least 8 characters"
                data-testid="view-share-password"
              />
            </div>
          )}

          <div>
            <Label className="text-sm">Expires on (optional)</Label>
            <DatePicker
              value={expires || null}
              onChange={(v) => setExpires(v || "")}
              testId="view-share-expires"
            />
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={includeMedia} onCheckedChange={setIncludeMedia} data-testid="view-share-media" />
              Include media
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={includeRels} onCheckedChange={setIncludeRels} data-testid="view-share-rels" />
              Include relationships
            </label>
          </div>

          <div className="pt-1">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={restrictColumns} onCheckedChange={setRestrictColumns} data-testid="view-share-restrict-cols" />
              Restrict which columns are visible
            </label>
            {restrictColumns && (
              <div className="mt-2 rounded-md border border-border p-2 bg-muted/20">
                <div className="text-[11px] font-mono uppercase text-muted-foreground mb-1">
                  Columns to expose <span className="normal-case font-sans">(empty = title/item # only)</span>
                </div>
                {nonSensitive.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No exposable fields on this entity.</div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {nonSensitive.map((f) => {
                      const on = visibleColumns.includes(f.key);
                      return (
                        <button
                          key={f.key} type="button"
                          onClick={() => toggleCol(f.key)}
                          className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                            on ? "bg-primary text-primary-foreground border-primary"
                               : "bg-white text-foreground border-border hover:border-primary/60"
                          }`}
                          data-testid={`view-share-col-${f.key}`}
                        >
                          {f.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="view-share-submit">
            {busy ? "Creating…" : "Create link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


/** ViewCollaboratorsDialog — internal per-user sharing. */
export function ViewCollaboratorsDialog({ open, onOpenChange, view, onChanged }) {
  const [collabs, setCollabs] = useState([]);
  const [members, setMembers] = useState([]);
  const [selectedUser, setSelectedUser] = useState("");
  const [permission, setPermission] = useState("view");
  const [loading, setLoading] = useState(true);
  const { activeOrgId } = useAuth();

  const load = async () => {
    if (!view) return;
    setLoading(true);
    try {
      const [c, m] = await Promise.all([
        api.get(`/views/${view.id}/collaborators`),
        api.get(`/orgs/${activeOrgId}/members`),
      ]);
      setCollabs(c.data || []);
      setMembers(m.data || []);
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (open && view) load(); /* eslint-disable-next-line */ }, [open, view]);

  const availableMembers = members.filter(
    (m) => !collabs.some((c) => c.user_id === m.user_id) && m.user_id !== view?.user_id,
  );

  const add = async () => {
    if (!selectedUser) return;
    try {
      await api.post(`/views/${view.id}/collaborators`, {
        user_id: selectedUser, permission,
      });
      toast.success("Collaborator added");
      setSelectedUser("");
      await load();
      onChanged?.();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const updatePerm = async (uid, perm) => {
    try {
      await api.patch(`/views/${view.id}/collaborators/${uid}`, { permission: perm });
      toast.success("Permission updated");
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const removeCollab = async (uid) => {
    if (!window.confirm("Remove this collaborator?")) return;
    try {
      await api.delete(`/views/${view.id}/collaborators/${uid}`);
      toast.success("Collaborator removed");
      await load();
      onChanged?.();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  if (!view) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="view-collab-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" /> People with access — {view.name}
          </DialogTitle>
        </DialogHeader>
        <div className="py-2 space-y-4">
          {/* Add row */}
          {availableMembers.length > 0 && (
            <div className="flex items-end gap-2" data-testid="view-collab-add-row">
              <div className="flex-1">
                <Label className="text-xs">Add member</Label>
                <Select value={selectedUser} onValueChange={setSelectedUser}>
                  <SelectTrigger data-testid="view-collab-user"><SelectValue placeholder="Select member…" /></SelectTrigger>
                  <SelectContent>
                    {availableMembers.map((m) => (
                      <SelectItem key={m.user_id} value={m.user_id}>
                        {m.name || m.email}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-[120px]">
                <Label className="text-xs">Permission</Label>
                <Select value={permission} onValueChange={setPermission}>
                  <SelectTrigger data-testid="view-collab-perm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="view">View</SelectItem>
                    <SelectItem value="edit">Edit</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" disabled={!selectedUser} onClick={add} data-testid="view-collab-add-btn">
                Add
              </Button>
            </div>
          )}

          <div className="rounded-lg border border-border">
            <div className="px-3 py-2 border-b border-border text-[10px] font-mono uppercase text-muted-foreground">
              Collaborators ({collabs.length})
            </div>
            {loading ? (
              <div className="p-3 text-xs text-muted-foreground">Loading…</div>
            ) : collabs.length === 0 ? (
              <div className="p-3 text-xs text-muted-foreground">
                No collaborators yet. Add a workspace member above to give them access.
              </div>
            ) : (
              <ul className="divide-y divide-border" data-testid="view-collab-list">
                {collabs.map((c) => (
                  <li key={c.user_id} className="px-3 py-2 flex items-center gap-2" data-testid={`view-collab-row-${c.user.email || c.user_id}`}>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{c.user.name || c.user.email || c.user_id}</div>
                      <div className="text-xs text-muted-foreground font-mono truncate">{c.user.email}</div>
                    </div>
                    <Select
                      value={c.permission}
                      onValueChange={(v) => updatePerm(c.user_id, v)}
                    >
                      <SelectTrigger className="h-7 w-[90px] text-xs" data-testid={`view-collab-perm-${c.user_id}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="view">View</SelectItem>
                        <SelectItem value="edit">Edit</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => removeCollab(c.user_id)}
                      data-testid={`view-collab-remove-${c.user_id}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
