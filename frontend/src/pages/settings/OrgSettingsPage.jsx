import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PageBody, PageHeader } from "@/components/PageChrome";
import { StorageQuotaBar, humanBytes } from "@/components/StorageQuotaBar";

export default function OrgSettingsPage() {
  const { activeOrgId, activeRole, refreshMe } = useAuth();
  const [org, setOrg] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const canManage = ["owner", "admin"].includes(activeRole);

  const [storage, setStorage] = useState(null);
  const [quotaMB, setQuotaMB] = useState("");
  const [savingQuota, setSavingQuota] = useState(false);

  const loadAll = async () => {
    if (!activeOrgId) return;
    try {
      const [oRes, sRes] = await Promise.all([
        api.get(`/orgs/${activeOrgId}`),
        api.get(`/media/storage`),
      ]);
      setOrg(oRes.data);
      setName(oRes.data.name);
      setStorage(sRes.data);
      setQuotaMB(Math.round(sRes.data.quota_bytes / (1024 * 1024)));
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };
  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, [activeOrgId]);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.patch(`/orgs/${activeOrgId}`, { name });
      setOrg(r.data);
      toast.success("Saved");
      await refreshMe();
    } catch (err) { toast.error(extractErrorMessage(err)); }
    finally { setBusy(false); }
  };

  const saveQuota = async () => {
    const bytes = Math.round(Number(quotaMB) * 1024 * 1024);
    if (!bytes) return toast.error("Enter a valid quota in MB");
    setSavingQuota(true);
    try {
      await api.patch(`/orgs/${activeOrgId}/storage-quota`, {
        storage_quota_bytes: bytes,
      });
      toast.success("Storage quota updated");
      loadAll();
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setSavingQuota(false); }
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
                <Input value={name} onChange={(e) => setName(e.target.value)}
                  disabled={!canManage} data-testid="input-org-name" />
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

        <Card data-testid="storage-panel">
          <CardHeader>
            <CardTitle className="text-lg">Storage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <StorageQuotaBar data={storage} />
            {storage && (
              <div className="text-xs text-muted-foreground font-mono">
                Max single file upload: {humanBytes(storage.max_upload_bytes)}
              </div>
            )}
            <div className="flex items-end gap-3 max-w-md">
              <div className="flex-1">
                <Label>Quota (MB)</Label>
                <Input type="number" min="100" value={quotaMB}
                  disabled={!canManage}
                  onChange={(e) => setQuotaMB(e.target.value)}
                  data-testid="input-storage-quota" />
                <p className="text-xs text-muted-foreground mt-1">
                  Range: 100 MB – 100 GB (102,400 MB)
                </p>
              </div>
              <Button onClick={saveQuota} disabled={!canManage || savingQuota}
                data-testid="submit-storage-quota">
                {savingQuota ? "Saving…" : "Update"}
              </Button>
            </div>
            <div>
              <Link to="/media" className="text-sm text-primary hover:underline"
                data-testid="link-manage-media">
                Manage in Media Library →
              </Link>
            </div>
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
