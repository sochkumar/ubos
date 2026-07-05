import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { UserPlus, Trash2, RefreshCw, Copy, ShieldOff, Mail } from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PageBody, PageHeader } from "@/components/PageChrome";
import { InviteModal } from "@/components/InviteModal";

const ROLE_ORDER = ["owner", "admin", "editor", "viewer"];

export default function MembersPage() {
  const { activeOrgId, activeRole, user: me } = useAuth();
  const [members, setMembers] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const canManage = ["owner", "admin"].includes(activeRole);

  const load = async () => {
    try {
      const [membersRes, invRes] = await Promise.all([
        api.get(`/orgs/${activeOrgId}/members`),
        canManage ? api.get(`/orgs/${activeOrgId}/invitations`) : Promise.resolve({ data: [] }),
      ]);
      setMembers(membersRes.data);
      setInvitations(invRes.data || []);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (activeOrgId) load();
    // eslint-disable-next-line
  }, [activeOrgId]);

  const changeRole = async (m, role_name) => {
    try {
      await api.patch(`/orgs/${activeOrgId}/members/${m.id}`, { role_name });
      toast.success(`${m.email} is now ${role_name}`);
      await load();
    } catch (err) { toast.error(extractErrorMessage(err)); }
  };

  const remove = async (m) => {
    if (!window.confirm(`Remove ${m.email} from this organization?`)) return;
    try {
      await api.delete(`/orgs/${activeOrgId}/members/${m.id}`);
      toast.success("Member removed");
      await load();
    } catch (err) { toast.error(extractErrorMessage(err)); }
  };

  const copyLink = async (url) => {
    try { await navigator.clipboard.writeText(url); toast.success("Invite URL copied"); }
    catch { toast.error("Couldn't copy"); }
  };

  const resendInvitation = async (inv) => {
    try {
      await api.post(`/orgs/${activeOrgId}/invitations/${inv.id}/resend`, {});
      toast.success(`Resent invitation to ${inv.email}`);
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };
  const revokeInvitation = async (inv) => {
    if (!window.confirm(`Revoke invitation for ${inv.email}?`)) return;
    try {
      await api.post(`/orgs/${activeOrgId}/invitations/${inv.id}/revoke`);
      toast.success("Invitation revoked");
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };
  const deleteInvitation = async (inv) => {
    if (!window.confirm(`Delete this invitation permanently?`)) return;
    try {
      await api.delete(`/orgs/${activeOrgId}/invitations/${inv.id}`);
      toast.success("Invitation deleted");
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const pendingInvites = invitations.filter((i) => i.status === "pending");
  const otherInvites = invitations.filter((i) => i.status !== "pending");

  return (
    <>
      <PageHeader
        title="Members"
        subtitle="Who has access to this workspace, and what they can do."
        breadcrumbs={[{ label: "Settings" }, { label: "Members" }]}
        actions={
          canManage && (
            <Button onClick={() => setInviteOpen(true)} data-testid="invite-users-btn">
              <UserPlus className="w-4 h-4 mr-1.5" /> Invite users
            </Button>
          )
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : (
          <div className="space-y-6">
            <div className="rounded-lg border border-border bg-white overflow-hidden">
              <div className="px-3 py-2 border-b border-border flex items-center gap-2">
                <div className="text-xs font-mono uppercase text-muted-foreground">Members</div>
                <Badge variant="secondary" className="text-[10px]">{members.length}</Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Member</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {members.map((m) => (
                    <TableRow key={m.id} data-testid={`member-row-${m.email}`}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">
                            {m.name}
                            {m.user_id === me?.id && (
                              <Badge variant="secondary" className="ml-2 text-[10px]">you</Badge>
                            )}
                          </span>
                          <span className="text-xs text-muted-foreground font-mono">{m.email}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {canManage && m.user_id !== me?.id ? (
                          <Select value={m.role} onValueChange={(v) => changeRole(m, v)}>
                            <SelectTrigger className="w-[130px] h-8" data-testid={`role-select-${m.email}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {ROLE_ORDER.map((r) => (
                                <SelectItem key={r} value={r} data-testid={`role-option-${m.email}-${r}`}>{r}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Badge className="bg-primary/10 text-primary border-transparent">{m.role}</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="capitalize">{m.status}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {canManage && m.user_id !== me?.id && (
                          <Button
                            variant="ghost" size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive"
                            onClick={() => remove(m)}
                            data-testid={`remove-member-${m.email}`}
                            aria-label="Remove"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {canManage && (
              <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="pending-invitations-section">
                <div className="px-3 py-2 border-b border-border flex items-center gap-2">
                  <div className="text-xs font-mono uppercase text-muted-foreground">Pending invitations</div>
                  <Badge variant="secondary" className="text-[10px]">{pendingInvites.length}</Badge>
                </div>
                {pendingInvites.length === 0 ? (
                  <div className="p-4 text-xs text-muted-foreground">
                    No pending invitations. Click <b>Invite users</b> to send some.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Email</TableHead>
                        <TableHead>Role</TableHead>
                        <TableHead>Invited by</TableHead>
                        <TableHead>Expires</TableHead>
                        <TableHead>Delivery</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pendingInvites.map((inv) => (
                        <TableRow key={inv.id} data-testid={`invitation-row-${inv.email}`}>
                          <TableCell className="font-mono text-xs">
                            <div className="flex items-center gap-1">
                              <Mail className="w-3 h-3 text-muted-foreground" />
                              {inv.email}
                            </div>
                          </TableCell>
                          <TableCell><Badge variant="secondary">{inv.role_name}</Badge></TableCell>
                          <TableCell className="text-xs text-muted-foreground">{inv.inviter?.name || inv.inviter?.email || "—"}</TableCell>
                          <TableCell className="text-xs">
                            {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString() : "—"}
                          </TableCell>
                          <TableCell>
                            {inv.email_provider === "dev" ? (
                              <Badge className="text-[10px] bg-amber-100 text-amber-800 border-transparent">dev mode</Badge>
                            ) : inv.email_sent ? (
                              <Badge className="text-[10px] bg-emerald-100 text-emerald-800 border-transparent">sent</Badge>
                            ) : (
                              <Badge className="text-[10px] bg-muted text-muted-foreground border-transparent">pending</Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-1">
                              <Button variant="ghost" size="icon" className="h-7 w-7"
                                onClick={() => copyLink(inv.accept_url)}
                                title="Copy invite link"
                                data-testid={`invite-copy-link-${inv.email}`}>
                                <Copy className="w-3.5 h-3.5" />
                              </Button>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-primary"
                                onClick={() => resendInvitation(inv)}
                                title="Resend"
                                data-testid={`invite-resend-${inv.email}`}>
                                <RefreshCw className="w-3.5 h-3.5" />
                              </Button>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-amber-700"
                                onClick={() => revokeInvitation(inv)}
                                title="Revoke"
                                data-testid={`invite-revoke-${inv.email}`}>
                                <ShieldOff className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            )}

            {canManage && otherInvites.length > 0 && (
              <div className="rounded-lg border border-border bg-white overflow-hidden">
                <div className="px-3 py-2 border-b border-border">
                  <div className="text-xs font-mono uppercase text-muted-foreground">History ({otherInvites.length})</div>
                </div>
                <Table>
                  <TableBody>
                    {otherInvites.slice(0, 20).map((inv) => (
                      <TableRow key={inv.id} data-testid={`invitation-history-${inv.email}`}>
                        <TableCell className="font-mono text-xs">{inv.email}</TableCell>
                        <TableCell><Badge variant="secondary" className="text-[10px]">{inv.role_name}</Badge></TableCell>
                        <TableCell>
                          <Badge className={
                            inv.status === "accepted" ? "text-[10px] bg-emerald-100 text-emerald-800 border-transparent" :
                            inv.status === "revoked" ? "text-[10px] bg-destructive/15 text-destructive border-transparent" :
                            "text-[10px] bg-muted text-muted-foreground border-transparent"
                          }>{inv.status}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {(inv.status === "revoked" || inv.status === "expired") && (
                            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                              onClick={() => deleteInvitation(inv)}
                              data-testid={`invite-delete-${inv.email}`}>
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}
      </PageBody>

      <InviteModal
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        onInvited={load}
      />
    </>
  );
}
