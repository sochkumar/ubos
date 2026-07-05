import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PageBody, PageHeader } from "@/components/PageChrome";

export default function OrgSettingsPage() {
  const { activeOrgId, activeRole, refreshMe } = useAuth();
  const [org, setOrg] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const canManage = ["owner", "admin"].includes(activeRole);

  useEffect(() => {
    if (!activeOrgId) return;
    api.get(`/orgs/${activeOrgId}`).then((r) => {
      setOrg(r.data);
      setName(r.data.name);
    }).catch((e) => toast.error(extractErrorMessage(e)));
  }, [activeOrgId]);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.patch(`/orgs/${activeOrgId}`, { name });
      setOrg(r.data);
      toast.success("Saved");
      await refreshMe();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Organization"
        subtitle="Settings that apply to everyone in this workspace."
        breadcrumbs={[{ label: "Settings" }, { label: "Organization" }]}
      />
      <PageBody className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">General</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={save} className="space-y-4 max-w-md">
              <div>
                <Label>Name</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={!canManage}
                  data-testid="input-org-name"
                />
              </div>
              <div>
                <Label>Slug</Label>
                <Input className="font-mono" value={org?.slug || ""} readOnly disabled />
              </div>
              <div className="flex items-center gap-3">
                <Button type="submit" disabled={!canManage || busy} data-testid="submit-org-save">
                  {busy ? "Saving…" : "Save changes"}
                </Button>
                {!canManage && (
                  <span className="text-xs text-muted-foreground">
                    Only owners and admins can edit organization settings.
                  </span>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        <Card className="border-destructive/30">
          <CardHeader>
            <CardTitle className="text-lg text-destructive">Danger zone</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Organization deletion is scheduled for a later phase — for now, contact support.
            </p>
          </CardContent>
        </Card>
      </PageBody>
    </>
  );
}
