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

  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);

  const exportWorkspace = async () => {
    setExporting(true);
    try {
      const r = await api.get("/workspace/export", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data], { type: "application/zip" }));
      const a = document.createElement("a");
      const ts = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `ubos-workspace-${ts}.ubos`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Workspace exported");
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setExporting(false); }
  };

  const importWorkspace = async (file) => {
    if (!file) return;
    if (!window.confirm(
      "Import will REPLACE all data in this workspace with the contents of the file. " +
      "This cannot be undone.\n\nContinue?"
    )) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post("/workspace/import?mode=replace", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const n = Object.values(r.data?.imported || {}).reduce((a, b) => a + (b || 0), 0);
      toast.success(`Workspace imported (${n} items)`);
      loadAll();
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setImporting(false); }
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

        <Card data-testid="workspace-panel">
          <CardHeader>
            <CardTitle className="text-lg">Workspace backup &amp; sharing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Export your entire workspace (collections, fields, categories, tags, items and files)
              to a single <code>.ubos</code> file — for backups, or to move an updated dataset to
              another machine. Importing <b>replaces</b> everything in this workspace with the file.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={exportWorkspace} disabled={exporting} data-testid="workspace-export">
                {exporting ? "Exporting…" : "Export workspace"}
              </Button>
              {canManage && (
                <label className="inline-flex">
                  <Button
                    variant="outline"
                    disabled={importing}
                    data-testid="workspace-import"
                    onClick={(e) => e.currentTarget.nextElementSibling?.click()}
                  >
                    {importing ? "Importing…" : "Import workspace…"}
                  </Button>
                  <input
                    type="file"
                    accept=".ubos,.zip"
                    className="hidden"
                    onChange={(e) => { importWorkspace(e.target.files?.[0]); e.target.value = ""; }}
                  />
                </label>
              )}
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
