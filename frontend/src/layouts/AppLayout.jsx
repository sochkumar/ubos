import { useState } from "react";
import { Outlet, NavLink, useLocation, useNavigate, Link } from "react-router-dom";
import {
  Boxes, Database, LayoutDashboard, Settings, Users, Shield,
  Search, ChevronDown, ChevronsUpDown, LogOut, Plus, Check,
  User as UserIcon, Building2, FolderKanban, Layers, Tags,
  ListChecks, GitBranch, Bell, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";

// Sidebar nav groups
const NAV_GROUPS = [
  {
    label: "Overview",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, soon: "Phase 4" },
    ],
  },
  {
    label: "Data",
    items: [
      { to: "/entity-types", label: "Entity Types", icon: Boxes },
    ],
  },
  {
    label: "Config",
    items: [
      { to: "/templates", label: "Templates", icon: FolderKanban },
      { to: "/config/views", label: "Views", icon: ListChecks, soon: "Phase 3" },
    ],
  },
  {
    label: "Settings",
    items: [
      { to: "/settings/organization", label: "Organization", icon: Building2 },
      { to: "/settings/members", label: "Users & Roles", icon: Users },
      { to: "/settings/audit-log", label: "Audit Log", icon: Shield },
      { to: "/settings/profile", label: "Profile", icon: UserIcon },
    ],
  },
];

export default function AppLayout() {
  const { user, orgs, activeOrgId, activeRole, logout, switchOrg, refreshMe } = useAuth();
  const location = useLocation();
  const nav = useNavigate();
  const [seeding, setSeeding] = useState(false);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [orgMenuOpen, setOrgMenuOpen] = useState(false);

  const activeOrg = orgs.find((o) => o.id === activeOrgId) || orgs[0];

  const runSeed = async () => {
    setSeeding(true);
    try {
      const r = await api.post("/dev/seed-demo");
      toast.success(`Demo seed complete · ${r.data.created_records} sample records created`);
      window.location.assign("/entity-types");
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setSeeding(false);
    }
  };

  const doSwitchOrg = async (org_id) => {
    if (org_id === activeOrgId) {
      setOrgMenuOpen(false);
      return;
    }
    try {
      await switchOrg(org_id);
      setOrgMenuOpen(false);
      toast.success("Workspace switched");
      window.location.assign("/entity-types");
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const doCreateOrg = async (e) => {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    setCreatingOrg(true);
    try {
      const r = await api.post("/orgs", { name: newOrgName.trim() });
      toast.success(`Created ${r.data.org.name}`);
      // apply new tokens (contains org_id) — reload to hydrate everywhere
      const { tokenStore } = await import("@/lib/api");
      tokenStore.set(r.data);
      await refreshMe();
      setNewOrgName("");
      setOrgMenuOpen(false);
      window.location.assign("/entity-types");
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setCreatingOrg(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background" data-testid="app-shell">
      {/* ────── Sidebar ────── */}
      <aside
        className="w-[240px] shrink-0 border-r border-border bg-white flex flex-col"
        data-testid="app-sidebar"
      >
        <div className="px-5 pt-6 pb-5">
          <Link to="/entity-types" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
              <Database className="w-4 h-4" strokeWidth={2.25} />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">UBOS</div>
              <div className="text-[11px] text-muted-foreground font-mono">
                phase 1
              </div>
            </div>
          </Link>
        </div>

        <Separator />

        <nav className="flex-1 overflow-y-auto p-3 space-y-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground px-3 mb-1.5">
                {group.label}
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active =
                    !item.soon && location.pathname.startsWith(item.to);
                  const soon = !!item.soon;
                  const dtid = `nav-${item.to.replace(/\//g, "-").replace(/^-+/, "")}`;
                  const base = "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors";
                  if (soon) {
                    return (
                      <div
                        key={item.to}
                        className={`${base} text-muted-foreground/70 cursor-not-allowed`}
                        data-testid={`${dtid}-soon`}
                        title={`${item.label} — ${item.soon}`}
                      >
                        <Icon className="w-4 h-4" strokeWidth={2} />
                        <span className="truncate">{item.label}</span>
                        <span className="ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded bg-muted">
                          {item.soon}
                        </span>
                      </div>
                    );
                  }
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      data-testid={dtid}
                      className={
                        active
                          ? `${base} bg-primary/10 text-primary font-medium`
                          : `${base} text-foreground/80 hover:bg-muted`
                      }
                    >
                      <Icon className="w-4 h-4" strokeWidth={2} />
                      <span>{item.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="p-3 border-t border-border">
          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            onClick={runSeed}
            disabled={seeding || !activeOrgId}
            data-testid="seed-demo-btn"
          >
            <Sparkles className="w-4 h-4" />
            {seeding ? "Seeding…" : "Load demo data"}
          </Button>
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground font-mono px-1">
            <span className="truncate" title={activeOrg?.slug}>
              org: {activeOrg?.slug || "—"}
            </span>
            <span className="text-primary">{activeRole || ""}</span>
          </div>
        </div>
      </aside>

      {/* ────── Main column ────── */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Topbar */}
        <div
          className="h-14 border-b border-border bg-white flex items-center gap-3 px-6 shrink-0"
          data-testid="app-topbar"
        >
          {/* Org switcher */}
          <DropdownMenu open={orgMenuOpen} onOpenChange={setOrgMenuOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="h-9 gap-2 -ml-2 pl-2 pr-2 text-sm max-w-[280px]"
                data-testid="org-switcher"
              >
                <div className="w-6 h-6 rounded bg-primary/15 text-primary text-[11px] font-semibold flex items-center justify-center shrink-0">
                  {activeOrg?.name?.slice(0, 1) || "—"}
                </div>
                <span className="truncate font-medium">
                  {activeOrg?.name || "No workspace"}
                </span>
                <ChevronsUpDown className="w-3.5 h-3.5 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[300px]" data-testid="org-menu">
              <DropdownMenuLabel className="text-[10px] font-mono uppercase text-muted-foreground">
                Your workspaces
              </DropdownMenuLabel>
              {orgs.map((o) => (
                <DropdownMenuItem
                  key={o.id}
                  className="flex items-center gap-2 cursor-pointer"
                  onSelect={(e) => {
                    e.preventDefault();
                    doSwitchOrg(o.id);
                  }}
                  data-testid={`org-option-${o.slug}`}
                >
                  <div className="w-5 h-5 rounded bg-primary/15 text-primary text-[10px] font-semibold flex items-center justify-center">
                    {o.name.slice(0, 1)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{o.name}</div>
                    <div className="text-[10px] font-mono text-muted-foreground truncate">
                      {o.slug} · {o.role}
                    </div>
                  </div>
                  {o.id === activeOrgId && (
                    <Check className="w-4 h-4 text-primary" />
                  )}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <div className="p-2">
                <form
                  onSubmit={doCreateOrg}
                  className="flex items-center gap-1.5"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Input
                    value={newOrgName}
                    onChange={(e) => setNewOrgName(e.target.value)}
                    placeholder="New workspace name"
                    className="h-8 text-sm"
                    data-testid="new-org-input"
                  />
                  <Button
                    type="submit"
                    size="sm"
                    className="h-8 shrink-0"
                    disabled={creatingOrg || !newOrgName.trim()}
                    data-testid="submit-new-org"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </Button>
                </form>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Global search (stub) */}
          <div className="relative flex-1 max-w-md ml-3">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search (coming in Phase 2)…"
              className="pl-8 h-9 bg-muted/40 border-transparent"
              disabled
              data-testid="global-search"
            />
          </div>

          <div className="ml-auto flex items-center gap-1">
            <Button
              variant="ghost" size="icon"
              className="h-9 w-9 text-muted-foreground"
              disabled
              data-testid="notifications-btn"
              aria-label="Notifications"
            >
              <Bell className="w-4 h-4" />
            </Button>

            {/* User menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-9 gap-2 px-2" data-testid="user-menu">
                  <div className="w-7 h-7 rounded-full bg-primary/15 text-primary text-xs font-semibold flex items-center justify-center overflow-hidden">
                    {user?.avatar_url ? (
                      <img
                        src={user.avatar_url}
                        alt=""
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      (user?.name || user?.email || "?").slice(0, 1).toUpperCase()
                    )}
                  </div>
                  <ChevronDown className="w-3.5 h-3.5 opacity-60" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-[240px]">
                <div className="px-2 py-2">
                  <div className="text-sm font-medium truncate">{user?.name}</div>
                  <div className="text-[11px] font-mono text-muted-foreground truncate">
                    {user?.email}
                  </div>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => nav("/settings/profile")} data-testid="menu-profile">
                  <UserIcon className="w-4 h-4 mr-2" /> Profile
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => nav("/settings/organization")} data-testid="menu-org">
                  <Settings className="w-4 h-4 mr-2" /> Organization
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={logout}
                  className="text-destructive focus:text-destructive"
                  data-testid="menu-logout"
                >
                  <LogOut className="w-4 h-4 mr-2" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Content */}
        <main className="flex-1 min-w-0 overflow-auto" data-testid="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
