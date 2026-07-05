import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { PageBody, PageHeader } from "@/components/PageChrome";

export default function ProfilePage() {
  const { user } = useAuth();
  const [pw, setPw] = useState({ current: "", new: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const changePassword = async (e) => {
    e.preventDefault();
    setError(null);
    if (pw.new.length < 8) return setError("Password must be at least 8 characters");
    if (pw.new !== pw.confirm) return setError("Passwords do not match");
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current: pw.current, new: pw.new });
      toast.success("Password updated");
      setPw({ current: "", new: "", confirm: "" });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Profile"
        subtitle="Your personal account settings."
        breadcrumbs={[{ label: "Settings" }, { label: "Profile" }]}
      />
      <PageBody className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Account</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Name</Label>
                <Input value={user?.name || ""} readOnly disabled />
              </div>
              <div>
                <Label>Email</Label>
                <Input value={user?.email || ""} readOnly disabled />
              </div>
            </div>
            <p className="text-[11px] font-mono text-muted-foreground">
              editing name is coming in a later phase
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Change password</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={changePassword} className="space-y-4 max-w-md">
              <div>
                <Label htmlFor="current">Current password</Label>
                <Input
                  id="current" type="password" required
                  data-testid="input-current-password"
                  value={pw.current}
                  onChange={(e) => setPw({ ...pw, current: e.target.value })}
                />
              </div>
              <div>
                <Label htmlFor="new">New password</Label>
                <Input
                  id="new" type="password" required
                  data-testid="input-new-password"
                  value={pw.new}
                  onChange={(e) => setPw({ ...pw, new: e.target.value })}
                />
              </div>
              <div>
                <Label htmlFor="confirm">Confirm new password</Label>
                <Input
                  id="confirm" type="password" required
                  data-testid="input-confirm-password"
                  value={pw.confirm}
                  onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={busy} data-testid="submit-change-password">
                {busy ? "Updating…" : "Update password"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </PageBody>
    </>
  );
}
