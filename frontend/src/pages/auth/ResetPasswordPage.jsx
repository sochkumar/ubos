import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      toast.success("Password updated — please sign in.");
      nav("/login", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="reset-page">
      <h1 className="text-2xl font-semibold tracking-tight">Choose a new password</h1>
      <p className="text-sm text-muted-foreground mt-1.5">
        You&apos;ll be signed out of all other devices.
      </p>
      {!token && (
        <p className="mt-6 text-sm text-destructive">Missing reset token.</p>
      )}
      <form onSubmit={submit} className="mt-8 space-y-4">
        <div>
          <Label htmlFor="password">New password</Label>
          <Input
            id="password" type="password" required autoComplete="new-password"
            data-testid="input-password"
            value={password} onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="confirm">Confirm password</Label>
          <Input
            id="confirm" type="password" required autoComplete="new-password"
            data-testid="input-confirm"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy || !token} data-testid="submit-reset">
          {busy ? "Updating…" : "Update password"}
        </Button>
      </form>
      <p className="mt-8 text-center text-sm text-muted-foreground">
        <Link to="/login" className="text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
