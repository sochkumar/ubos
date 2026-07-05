import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // { message, dev_reset_url }
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("/auth/forgot-password", { email });
      setDone(res.data);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div data-testid="forgot-done">
        <h1 className="text-2xl font-semibold tracking-tight">Check your inbox</h1>
        <p className="text-sm text-muted-foreground mt-1.5">{done.message}</p>
        {done.dev_reset_url && (
          <div className="mt-6 rounded-md border border-dashed border-amber-400 bg-amber-50 p-4">
            <p className="text-[11px] font-mono uppercase text-amber-800 mb-1.5">
              Dev mode — copy this reset link
            </p>
            <code
              className="block text-xs break-all text-amber-900"
              data-testid="dev-reset-url"
            >
              {done.dev_reset_url}
            </code>
          </div>
        )}
        <p className="mt-8 text-center text-sm text-muted-foreground">
          <Link to="/login" className="text-primary hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div data-testid="forgot-page">
      <h1 className="text-2xl font-semibold tracking-tight">Reset your password</h1>
      <p className="text-sm text-muted-foreground mt-1.5">
        Enter your email and we&apos;ll send a reset link.
      </p>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email" type="email" required autoComplete="email"
            data-testid="input-email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy} data-testid="submit-forgot">
          {busy ? "Sending…" : "Send reset link"}
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
