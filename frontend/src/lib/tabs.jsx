/**
 * Phase 8 — Multi-tab workspace.
 *
 * Chrome-style tabs INSIDE the app. Every route can be its own tab.
 * Per-session only (sessionStorage — wipes on browser close, survives refresh).
 *
 * Architecture (URL-only, no keep-alive):
 *   - Tabs store `{id, path, title, icon}` — no per-tab component state.
 *   - Switching a tab = `navigate(tab.path)`. React Router mounts fresh.
 *   - The active tab's `path` mirrors `location.pathname + location.search`
 *     one-way (router → tab).
 *   - New-tab intent is captured by a document-level click interceptor that
 *     watches for Ctrl / Cmd / middle-click on internal <a> elements.
 *
 * Public surface:
 *   <TabsProvider>              — mounts context + global click interceptor
 *   useTabs()                   — { tabs, activeId, openTab, closeTab, ... }
 *   useTabTitle(title, icon?)   — page-level hook; updates the active tab's
 *                                 title/icon whenever `title` changes.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

const SESSION_KEY = "ubos.tabs.v1";
const CLOSED_KEY  = "ubos.tabs.closed.v1";
export const MAX_TABS = 20;
export const MAX_CLOSED_HISTORY = 5;

/* ────────────────────── route → default title map ────────────────────── */
// Fires synchronously when a new tab is spawned so tabs never appear empty.
// `useTabTitle` inside a page can override with a dynamic title afterwards.
const ROUTE_TITLES = [
  { re: /^\/dashboard$/,                         title: "Home",          icon: "home" },
  { re: /^\/browse$/,                            title: "All Items",     icon: "compass" },
  { re: /^\/search$/,                            title: "Search",        icon: "search" },
  { re: /^\/media$/,                             title: "Files",         icon: "image" },
  { re: /^\/templates$/,                         title: "Starter Packs", icon: "gift" },
  { re: /^\/entity-types$/,                      title: "My Data",       icon: "boxes" },
  { re: /^\/entity-types\/[^/]+\/records$/,      title: "Items",         icon: "boxes" },
  { re: /^\/entity-types\/[^/]+\/fields$/,       title: "Fields",        icon: "layers" },
  { re: /^\/entity-types\/[^/]+\/categories$/,   title: "Categories",    icon: "folder-tree" },
  { re: /^\/entity-types\/[^/]+\/tags$/,         title: "Tags",          icon: "tag" },
  { re: /^\/entity-types\/[^/]+\/relationships$/,title: "Links",         icon: "git-branch" },
  { re: /^\/records\/[^/]+$/,                    title: "Item",          icon: "package" },
  { re: /^\/settings\/organization$/,            title: "Organization",  icon: "building-2" },
  { re: /^\/settings\/members$/,                 title: "Team & Roles",  icon: "users" },
  { re: /^\/settings\/terminology$/,             title: "Terminology",   icon: "type" },
  { re: /^\/settings\/audit-log$/,               title: "Activity",      icon: "activity" },
  { re: /^\/settings\/label-presets$/,           title: "Label Presets", icon: "printer" },
  { re: /^\/settings\/profile$/,                 title: "Profile",       icon: "user" },
  { re: /^\/onboarding$/,                        title: "Welcome",       icon: "sparkles" },
];

export function defaultTitleFor(path) {
  const p = (path || "/").split("?")[0].split("#")[0];
  for (const t of ROUTE_TITLES) {
    if (t.re.test(p)) return { title: t.title, icon: t.icon };
  }
  return { title: "Loading…", icon: "loader-2" };
}

/* ────────────────────── session persistence ────────────────────── */
function loadSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_e) { return null; }
}
function saveSession(state) {
  try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(state)); } catch (_e) { /* quota / private-mode — ignore */ }
}
function loadClosed() {
  try {
    const raw = sessionStorage.getItem(CLOSED_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (_e) { return []; }
}
function saveClosed(list) {
  try { sessionStorage.setItem(CLOSED_KEY, JSON.stringify(list)); } catch (_e) { /* ignore */ }
}

const uuid = () =>
  (crypto?.randomUUID?.()) ||
  `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

/* ────────────────────── context ────────────────────── */
const TabsContext = createContext(null);

/**
 * Provider. Owns tabs state, syncs the active tab with the router location,
 * exposes actions, mounts a global click interceptor for new-tab shortcuts,
 * and renders a right-click context menu for internal links.
 */
export function TabsProvider({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname + location.search;

  // ── initial state (from session or new blank tab for current URL) ──
  const [tabs, setTabs] = useState(() => {
    const s = loadSession();
    if (s && Array.isArray(s.tabs) && s.tabs.length > 0) return s.tabs;
    const meta = defaultTitleFor(path);
    return [{
      id: uuid(), path, title: meta.title, icon: meta.icon,
      createdAt: new Date().toISOString(),
    }];
  });
  const [activeId, setActiveId] = useState(() => {
    const s = loadSession();
    if (s?.activeId && s?.tabs?.some((t) => t.id === s.activeId)) return s.activeId;
    return null; // set below by effect
  });
  const [closedStack, setClosedStack] = useState(() => loadClosed());
  const [ctxMenu, setCtxMenu] = useState(null); // {x, y, href}

  // Guarantee active id
  useEffect(() => {
    if (!activeId || !tabs.some((t) => t.id === activeId)) {
      setActiveId(tabs[0]?.id ?? null);
    }
  }, [tabs, activeId]);

  // Persist
  useEffect(() => { saveSession({ tabs, activeId }); }, [tabs, activeId]);
  useEffect(() => { saveClosed(closedStack); }, [closedStack]);

  /**
   * One-way router → active-tab sync. When the URL changes, patch the active
   * tab's `path` and reset title/icon from the route map (until the page
   * calls `useTabTitle` and overrides it).
   */
  useEffect(() => {
    if (!activeId) return;
    setTabs((prev) => {
      let dirty = false;
      const next = prev.map((t) => {
        if (t.id !== activeId) return t;
        if (t.path === path) return t;
        const meta = defaultTitleFor(path);
        dirty = true;
        return { ...t, path, title: meta.title, icon: meta.icon };
      });
      return dirty ? next : prev;
    });
  }, [path, activeId]);

  /* ────── actions ────── */
  const openTab = useCallback((href, { switchTo = true } = {}) => {
    let created = null;
    setTabs((prev) => {
      if (prev.length >= MAX_TABS) {
        toast.error(`Tab limit reached (${MAX_TABS}) — close some tabs first`);
        return prev;
      }
      const meta = defaultTitleFor(href);
      created = {
        id: uuid(), path: href, title: meta.title, icon: meta.icon,
        createdAt: new Date().toISOString(),
      };
      return [...prev, created];
    });
    // The above is not synchronous, but React batches → the next tick has the id.
    // We use a microtask flush.
    Promise.resolve().then(() => {
      if (!created) return;
      if (switchTo) {
        setActiveId(created.id);
        navigate(href);
      }
    });
    return created;
  }, [navigate]);

  const activateTab = useCallback((id) => {
    setTabs((prev) => {
      const t = prev.find((x) => x.id === id);
      if (t && t.path !== (location.pathname + location.search)) {
        // schedule navigate outside setState
        Promise.resolve().then(() => navigate(t.path));
      }
      return prev;
    });
    setActiveId(id);
  }, [navigate, location]);

  const closeTab = useCallback((id) => {
    setTabs((prev) => {
      if (prev.length === 0) return prev;
      const idx = prev.findIndex((t) => t.id === id);
      if (idx === -1) return prev;
      const closing = prev[idx];
      const next = prev.slice(0, idx).concat(prev.slice(idx + 1));

      // Remember closed for reopen (unless it was the default dashboard tab)
      setClosedStack((cs) => {
        const filtered = cs.filter((c) => c.path !== closing.path);
        return [{
          path: closing.path, title: closing.title, icon: closing.icon,
          closedAt: new Date().toISOString(),
        }, ...filtered].slice(0, MAX_CLOSED_HISTORY);
      });

      if (next.length === 0) {
        // Always keep at least one tab. Spawn a fresh Dashboard tab.
        const meta = defaultTitleFor("/dashboard");
        const fresh = {
          id: uuid(), path: "/dashboard", title: meta.title, icon: meta.icon,
          createdAt: new Date().toISOString(),
        };
        setActiveId(fresh.id);
        Promise.resolve().then(() => navigate("/dashboard"));
        return [fresh];
      }

      // If we closed the active tab, activate the neighbor (right, else left).
      if (id === activeId) {
        const neighbor = next[idx] || next[idx - 1] || next[0];
        setActiveId(neighbor.id);
        Promise.resolve().then(() => navigate(neighbor.path));
      }
      return next;
    });
  }, [activeId, navigate]);

  const reopenLastClosed = useCallback(() => {
    setClosedStack((cs) => {
      if (cs.length === 0) return cs;
      const [head, ...rest] = cs;
      // Push the reopened tab (switch to it).
      let created = null;
      setTabs((prev) => {
        if (prev.length >= MAX_TABS) {
          toast.error(`Tab limit reached (${MAX_TABS}) — close some tabs first`);
          return prev;
        }
        const meta = defaultTitleFor(head.path);
        created = {
          id: uuid(), path: head.path,
          title: head.title || meta.title, icon: head.icon || meta.icon,
          createdAt: new Date().toISOString(),
        };
        return [...prev, created];
      });
      Promise.resolve().then(() => {
        if (!created) return;
        setActiveId(created.id);
        navigate(head.path);
      });
      return rest;
    });
  }, [navigate]);

  const reorderTabs = useCallback((fromId, toId) => {
    setTabs((prev) => {
      const from = prev.findIndex((t) => t.id === fromId);
      const to   = prev.findIndex((t) => t.id === toId);
      if (from === -1 || to === -1 || from === to) return prev;
      const next = prev.slice();
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  }, []);

  const updateTitle = useCallback((id, title, icon) => {
    setTabs((prev) => prev.map((t) => {
      if (t.id !== id) return t;
      const nextTitle = title ?? t.title;
      const nextIcon  = icon  ?? t.icon;
      if (nextTitle === t.title && nextIcon === t.icon) return t;
      return { ...t, title: nextTitle, icon: nextIcon };
    }));
  }, []);

  const activeIndex = useMemo(
    () => tabs.findIndex((t) => t.id === activeId),
    [tabs, activeId],
  );

  const jumpTo = useCallback((n) => {
    // 1-indexed
    const t = tabs[n - 1];
    if (t) activateTab(t.id);
  }, [tabs, activateTab]);

  const nextTab = useCallback(() => {
    if (tabs.length < 2) return;
    const idx = activeIndex;
    activateTab(tabs[(idx + 1) % tabs.length].id);
  }, [tabs, activeIndex, activateTab]);

  const prevTab = useCallback(() => {
    if (tabs.length < 2) return;
    const idx = activeIndex;
    activateTab(tabs[(idx - 1 + tabs.length) % tabs.length].id);
  }, [tabs, activeIndex, activateTab]);

  /* ────── global click / auxclick / contextmenu interceptor ────── */
  const openTabRef = useRef(openTab);
  openTabRef.current = openTab;
  useEffect(() => {
    // Find nearest anchor with an internal href; return the pathname+search.
    function internalPath(anchor) {
      if (!anchor) return null;
      const href = anchor.getAttribute("href");
      if (!href) return null;
      if (anchor.target === "_blank") return null;
      if (anchor.dataset.noAppTab === "true") return null;
      // Absolute paths only, or full URLs to same origin
      if (href.startsWith("/")) return href;
      try {
        const u = new URL(href, window.location.origin);
        if (u.origin === window.location.origin) return u.pathname + u.search;
      } catch (_e) { /* not a valid URL — treat as non-internal */ }
      return null;
    }

    const onClick = (e) => {
      if (e.defaultPrevented) return;
      const anchor = e.target?.closest?.("a[href]");
      const p = internalPath(anchor);
      if (!p) return;
      // Ctrl or Cmd click → open in new tab, don't switch
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        e.stopPropagation();
        openTabRef.current(p, { switchTo: false });
      }
    };
    const onAux = (e) => {
      // Middle click
      if (e.button !== 1) return;
      const anchor = e.target?.closest?.("a[href]");
      const p = internalPath(anchor);
      if (!p) return;
      e.preventDefault();
      e.stopPropagation();
      openTabRef.current(p, { switchTo: false });
    };
    const onCtx = (e) => {
      const anchor = e.target?.closest?.("a[href]");
      const p = internalPath(anchor);
      if (!p) return;
      e.preventDefault();
      setCtxMenu({ x: e.clientX, y: e.clientY, href: p });
    };

    document.addEventListener("click", onClick, true);
    document.addEventListener("auxclick", onAux, true);
    document.addEventListener("contextmenu", onCtx, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("auxclick", onAux, true);
      document.removeEventListener("contextmenu", onCtx, true);
    };
  }, []);

  // Dismiss context menu on any click / esc
  useEffect(() => {
    if (!ctxMenu) return;
    const off = () => setCtxMenu(null);
    const esc = (e) => { if (e.key === "Escape") setCtxMenu(null); };
    setTimeout(() => {
      document.addEventListener("click", off, { once: true });
      document.addEventListener("keydown", esc);
    }, 0);
    return () => {
      document.removeEventListener("click", off);
      document.removeEventListener("keydown", esc);
    };
  }, [ctxMenu]);

  const value = useMemo(
    () => ({
      tabs, activeId, activeIndex, closedStack,
      openTab, closeTab, activateTab, reopenLastClosed,
      reorderTabs, updateTitle,
      nextTab, prevTab, jumpTo,
    }),
    [tabs, activeId, activeIndex, closedStack, openTab, closeTab, activateTab,
     reopenLastClosed, reorderTabs, updateTitle, nextTab, prevTab, jumpTo],
  );

  return (
    <TabsContext.Provider value={value}>
      {children}
      {ctxMenu && (
        <div
          data-testid="tab-context-menu"
          style={{ position: "fixed", top: ctxMenu.y, left: ctxMenu.x, zIndex: 9999 }}
          className="min-w-[220px] rounded-md border border-border bg-white shadow-lg py-1 text-sm"
        >
          <button
            type="button"
            data-testid="ctx-open-new-tab"
            className="w-full text-left px-3 py-1.5 hover:bg-muted"
            onClick={(e) => {
              e.stopPropagation();
              openTabRef.current(ctxMenu.href, { switchTo: false });
              setCtxMenu(null);
            }}
          >
            Open in new tab
          </button>
          <button
            type="button"
            data-testid="ctx-open-new-tab-switch"
            className="w-full text-left px-3 py-1.5 hover:bg-muted"
            onClick={(e) => {
              e.stopPropagation();
              openTabRef.current(ctxMenu.href, { switchTo: true });
              setCtxMenu(null);
            }}
          >
            Open in new tab and switch
          </button>
        </div>
      )}
    </TabsContext.Provider>
  );
}

export function useTabs() {
  const ctx = useContext(TabsContext);
  if (!ctx) {
    throw new Error("useTabs must be used inside <TabsProvider>");
  }
  return ctx;
}

/**
 * Page-level hook. Call inside any page that wants to set the tab title.
 * Updates the ACTIVE tab (the tab the router thinks is rendering).
 */
export function useTabTitle(title, icon) {
  const { activeId, updateTitle } = useTabs();
  useEffect(() => {
    if (!activeId || !title) return;
    updateTitle(activeId, title, icon);
  }, [activeId, title, icon, updateTitle]);
}
