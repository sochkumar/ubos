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
import { UserPlus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PageBody, PageHeader } from "@/components/PageChrome";

const ROLE_ORDER = ["owner", "admin", "editor", "viewer"];

export default function MembersPage() {
  const { activeOrgId, activeRole, user: me } = useAuth();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const canManage = ["owner", "admin"].includes(activeRole);

  const load = async () => {
    try {
      const r = await api.get(`/orgs/${activeOrgId}/members`);
      setMembers(r.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (activeOrgId) load();
  }, [activeOrgId]);

  const changeRole = async (m, role_name) => {
    try {
      await api.patch(`/orgs/${activeOrgId}/members/${m.id}`, { role_name });
      toast.success(`${m.email} is now ${role_name}`);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const remove = async (m) => {
    if (!window.confirm(`Remove ${m.email} from this organization?`)) return;
    try {
      await api.delete(`/orgs/${activeOrgId}/members/${m.id}`);
      toast.success("Member removed");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  return (
    <>
      <PageHeader
        title="Members"
        subtitle="Who has access to this workspace, and what they can do."
        breadcrumbs={[{ label: "Settings" }, { label: "Members" }]}
        actions={
          <Button variant="outline" disabled data-testid="invite-users-btn">
            <UserPlus className="w-4 h-4 mr-1.5" />
            Invite users
            <span className="ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
              phase 5
            </span>
          </Button>
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden">
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
                            <Badge variant="secondary" className="ml-2 text-[10px]">
                              you
                            </Badge>
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground font-mono">
                          {m.email}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {canManage && m.user_id !== me?.id ? (
                        <Select
                          value={m.role}
                          onValueChange={(v) => changeRole(m, v)}
                        >
                          <SelectTrigger
                            className="w-[130px] h-8"
                            data-testid={`role-select-${m.email}`}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ROLE_ORDER.map((r) => (
                              <SelectItem key={r} value={r} data-testid={`role-option-${m.email}-${r}`}>
                                {r}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge className="bg-primary/10 text-primary border-transparent">
                          {m.role}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="capitalize">
                        {m.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {canManage && m.user_id !== me?.id && (
                        <Button
                          variant="ghost"
                          size="icon"
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
        )}
      </PageBody>
    </>
  );
}
