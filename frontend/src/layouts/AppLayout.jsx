import { useEffect, useState } from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";
import { Boxes, Layers, ListChecks, Database, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { api, extractErrorMessage } from "@/lib/api";

const NAV = [
  { to: "/entity-types", label: "Entity Types", icon: Boxes },
];

export default function AppLayout() {
  const [seeding, setSeeding] = useState(false);
  const [health, setHealth] = useState(null);
  const location = useLocation();

  useEffect(() => {
    api
      .get("/health")
      .then((r) => setHealth(r.data.status))
      .catch(() => setHealth("down"));
  }, []);

  const runSeed = async () => {
    setSeeding(true);
    try {
      const r = await api.post("/dev/seed-demo");
      const created = r.data?.created_records ?? 0;
      toast.success(`Demo seed complete · ${created} sample records created`);
      // Reload to reflect newly-seeded data
      window.location.assign("/entity-types");
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background" data-testid="app-shell">
      {/* Sidebar */}
      <aside
        className="w-[240px] shrink-0 border-r border-border bg-white flex flex-col"
        data-testid="app-sidebar"
      >
        <div className="px-5 pt-6 pb-5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
              <Database className="w-4 h-4" strokeWidth={2.25} />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">UBOS</div>
              <div className="text-[11px] text-muted-foreground font-mono">
                phase 0 · poc
              </div>
            </div>
          </div>
        </div>

        <Separator />

        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                data-testid={`nav-${item.to.replace(/\//g, "").trim() || "home"}`}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-foreground/80 hover:bg-muted"
                }`}
              >
                <Icon className="w-4 h-4" strokeWidth={2} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border">
          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            onClick={runSeed}
            disabled={seeding}
            data-testid="seed-demo-btn"
          >
            <Sparkles className="w-4 h-4" />
            {seeding ? "Seeding…" : "Load demo data"}
          </Button>
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground font-mono px-1">
            <span>org: demo-org</span>
            <span
              className={`inline-flex items-center gap-1 ${
                health === "ok" ? "text-emerald-700" : "text-amber-700"
              }`}
              data-testid="health-status"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  health === "ok" ? "bg-emerald-600" : "bg-amber-500"
                }`}
              />
              {health === "ok" ? "api up" : health || "…"}
            </span>
          </div>
        </div>
      </aside>

      {/* Content */}
      <main className="flex-1 min-w-0 overflow-auto" data-testid="app-content">
        <Outlet />
      </main>
    </div>
  );
}
