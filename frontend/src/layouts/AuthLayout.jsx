import { Outlet, Link } from "react-router-dom";
import { Database } from "lucide-react";

export default function AuthLayout() {
  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      {/* Left panel — brand */}
      <aside className="hidden lg:flex flex-col justify-between p-12 bg-white border-r border-border">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
            <Database className="w-4.5 h-4.5" strokeWidth={2.25} />
          </div>
          <div className="leading-tight">
            <div className="text-base font-semibold tracking-tight">UBOS</div>
            <div className="text-[11px] text-muted-foreground font-mono">
              universal business os
            </div>
          </div>
        </Link>
        <div className="max-w-md space-y-3">
          <h2 className="text-3xl font-semibold tracking-tight leading-tight">
            One workspace.<br />Any business shape.
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Define your own entity types, fields, and records — no code. Everything
            you track, in a place designed for you.
          </p>
          <div className="pt-2 flex flex-wrap gap-2 text-[11px] font-mono text-muted-foreground">
            <span className="px-2 py-1 rounded bg-muted">multi-tenant</span>
            <span className="px-2 py-1 rounded bg-muted">RBAC</span>
            <span className="px-2 py-1 rounded bg-muted">no-code schema</span>
          </div>
        </div>
        <div className="text-[11px] text-muted-foreground font-mono">
          phase 1 · auth + orgs
        </div>
      </aside>

      {/* Right panel — form */}
      <main className="flex flex-col justify-center items-center px-6 py-12">
        <div className="w-full max-w-sm">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
