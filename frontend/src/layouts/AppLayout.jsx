import { useCallback, useEffect, useState } from "react";
import { Outlet, NavLink, useLocation, useNavigate, Link } from "react-router-dom";
import {
  Boxes, Database, Home, Settings, Users, Activity,
  Search, ChevronDown, ChevronsUpDown, LogOut, Plus, Check,
  User as UserIcon, Building2, ImageIcon, Gift, Wrench, Layout,
  Link as LinkIcon, Bell, Sparkles, Tag as TagIcon, FolderTree,
  ArrowLeftRight, Type, Compass,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { useTerminology } from "@/lib/terminology";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { CommandPalette, useCommandPalette } from "@/components/CommandPalette";
import { InstallAppMenuItem } from "@/components/InstallAppMenuItem";
import { TabBar } from "@/components/TabBar";
import { useTabs } from "@/lib/tabs";
import { useHotkeys } from "@/hooks/useHotkeys";
import { Keyboard, Printer } from "lucide-react";

// Sidebar nav groups — labels are resolved live via t() inside the render.
// Each item declares its stable `key` (used for testid + t() lookup) alongside
// its `to` path and default label (fallback if t() misses).
const NAV_GROUPS = [
  {
    label: "Workspace",
    items: [
      { key: "nav.dashboard", to: "/dashboard",    fallback: "Home",           icon: Home,      testid: "nav-dashboard" },
      { key: "nav.data",      to: "/entity-types", fallback: "My Data",        icon: Boxes,     testid: "nav-my-data",   hasChildren: true },
      { key: "nav.browse",    to: "/browse",       fallback: "All Items",      icon: Compass,   testid: "nav-all-items" },
      { key: "nav.media",     to: "/media",        fallback: "Files",          icon: ImageIcon, testid: "nav-files" },
      { key: "nav.templates", to: "/templates",    fallback: "Starter Packs",  icon: Gift,      testid: "nav-starter-packs" },
      { key: "nav.search",    to: "/search",       fallback: "Search",         icon: Search,    testid: "nav-search" },
    ],
  },
  {
    label: "Setup",
    items: [
      { key: "settings.labels",  to: "/settings/label-presets",  fallback: "Label Presets", icon: Printer,    testid: "nav-label-presets" },
    ],
  },
  {
    label: "Settings",
    items: [
      { key: "settings.org",         to: "/settings/organization", fallback: "Organization",     icon: Building2, testid: "nav-organization" },
      { key: "settings.members",     to: "/settings/members",      fallback: "Team & Roles",     icon: Users,     testid: "nav-team" },
      { key: "settings.terminology", to: "/settings/terminology",  fallback: "Terminology",      icon: Type,      testid: "nav-terminology" },
      { key: "settings.audit",       to: "/settings/audit-log",    fallback: "Activity",         icon: Activity,  testid: "nav-activity" },
      { key: "settings.profile",     to: "/settings/profile",      fallback: "Profile",          icon: UserIcon,  testid: "nav-profile" },
    ],
  },
];

export default function AppLayout() {
  const { user, orgs, activeOrgId, activeRole, logout, switchOrg, refreshMe } = useAuth();
  const { t } = useTerminology();
  const location = useLocation();
  const nav = useNavigate();
  const [seeding, setSeeding] = useState(false);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [orgMenuOpen, setOrgMenuOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useCommandPalette();
  const [collections, setCollections] = useState([]);

  // ── Multi-tab hotkeys (Phase 8) ──
  const {
    tabs, activeIndex, openTab, closeTab, activateTab, reopenLastClosed,
    nextTab, prevTab, jumpTo,
  } = useTabs();
  useHotkeys("mod+t", () => openTab("/dashboard", { switchTo: true }));
  useHotkeys("mod+w", () => {
    const active = tabs[activeIndex];
    if (active && tabs.length > 1) closeTab(active.id);
  }, [tabs, activeIndex]);
  useHotkeys("mod+shift+t", () => reopenLastClosed());
  useHotkeys("mod+tab",       () => nextTab(), [nextTab]);
  useHotkeys("mod+shift+tab", () => prevTab(), [prevTab]);
  useHotkeys("mod+1", () => jumpTo(1));
  useHotkeys("mod+2", () => jumpTo(2));
  useHotkeys("mod+3", () => jumpTo(3));
  useHotkeys("mod+4", () => jumpTo(4));
  useHotkeys("mod+5", () => jumpTo(5));
  useHotkeys("mod+6", () => jumpTo(6));
  useHotkeys("mod+7", () => jumpTo(7));
  useHotkeys("mod+8", () => jumpTo(8));
  useHotkeys("mod+9", () => jumpTo(9));

  const activeOrg = orgs.find((o) => o.id === activeOrgId) || orgs[0];

  // Load collections for the "My Data" sub-tree. Refetches whenever the
  // active org changes; refresh on window focus so freshly-created
  // collections appear without a full reload.
  const loadCollections = useCallback(async () => {
    if (!activeOrgId) return;
    try {
      const r = await api.get("/entity-types");
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setCollections(list);
    } catch {
      setCollections([]);
    }
  }, [activeOrgId]);

  useEffect(() => { loadCollections(); }, [loadCollections]);
  useEffect(() => {
    const onFocus = () => loadCollections();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [loadCollections]);

  const runSeed = async () => {
    setSeeding(true);
    try {
      const r = await api.post("/dev/seed-demo");
      toast.success(`Sample data loaded · ${r.data.created_records} demo items added`);
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
                  // Prefer the translated label; fall back to the hard-coded
                  // fallback when the key isn't in the vocabulary (avoids
                  // rendering raw dot-notation keys in the sidebar).
                  const translated = t(item.key);
                  const label = (translated && translated !== item.key) ? translated : item.fallback;
                  const active = location.pathname.startsWith(item.to);
                  const dtid = item.testid || `nav-${item.to.replace(/\//g, "-").replace(/^-+/, "")}`;
                  const base = "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors";
                  return (
                    <div key={item.to}>
                      <NavLink
                        to={item.to}
                        data-testid={dtid}
                        className={
                          active
                            ? `${base} bg-primary/10 text-primary font-medium`
                            : `${base} text-foreground/80 hover:bg-muted`
                        }
                      >
                        <Icon className="w-4 h-4" strokeWidth={2} />
                        <span>{label}</span>
                      </NavLink>

                      {/* Dynamic collection sub-tree under "My Data" */}
                      {item.hasChildren && collections.length > 0 && (
                        <div className="ml-6 mt-0.5 space-y-0.5 border-l border-border/50 pl-2" data-testid="sidebar-collections-list">
                          {collections.slice(0, 12).map((c) => {
                            const subActive = location.pathname === `/entity-types/${c.id}/records`;
                            return (
                              <NavLink
                                key={c.id}
                                to={`/entity-types/${c.id}/records`}
                                data-testid={`sidebar-collection-${c.key}`}
                                className={
                                  subActive
                                    ? `${base} py-1 text-primary font-medium bg-primary/5`
                                    : `${base} py-1 text-foreground/70 hover:bg-muted`
                                }
                              >
                                <span
                                  className="w-1.5 h-1.5 rounded-full shrink-0"
                                  style={{ backgroundColor: c.color || "#0d9488" }}
                                />
                                <span className="truncate text-[13px]">
                                  {c.name_plural || c.name_singular || c.key}
                                </span>
                              </NavLink>
                            );
                          })}
                          {collections.length > 12 && (
                            <div className="px-3 py-0.5 text-[11px] text-muted-foreground italic">
                              +{collections.length - 12} more…
                            </div>
                          )}
                          <NavLink
                            to="/entity-types?new=1"
                            data-testid="sidebar-add-collection"
                            className={`${base} py-1 text-[13px] text-muted-foreground hover:text-primary hover:bg-muted`}
                          >
                            <Plus className="w-3 h-3" />
                            <span>{t("collection.new") || "Add new Collection"}</span>
                          </NavLink>
                        </div>
                      )}
                    </div>
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
            {seeding ? "Loading…" : "Load sample data"}
          </Button>
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground font-mono px-1">
            <span className="truncate" title={activeOrg?.name}>
              {activeOrg?.name || ""}
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

          {/* Global search — opens the ⌘K palette */}
          <div className="relative flex-1 max-w-md ml-3">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="w-full h-9 pl-8 pr-16 flex items-center rounded-md border border-transparent bg-muted/40 text-sm text-muted-foreground hover:border-border hover:bg-muted/60 transition-colors text-left"
              data-testid="global-search-trigger"
            >
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2" />
              <span className="truncate">Search anything…</span>
              <kbd className="ml-auto hidden sm:inline-flex items-center gap-0.5 rounded border border-border bg-white px-1.5 h-5 text-[10px] font-mono">
                ⌘K
              </kbd>
            </button>
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
                <DropdownMenuItem
                  onSelect={() => {
                    // Dispatch a keydown "?" so GlobalHotkeys opens the dialog.
                    window.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
                  }}
                  data-testid="menu-shortcuts"
                >
                  <Keyboard className="w-4 h-4 mr-2" /> Keyboard shortcuts
                </DropdownMenuItem>
                <InstallAppMenuItem />
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
        <TabBar />
        <main className="flex-1 min-w-0 overflow-auto" data-testid="app-content">
          <Outlet />
        </main>
      </div>

      {/* Global cmd+K palette */}
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
