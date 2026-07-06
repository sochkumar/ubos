/**
 * Vocabulary layer (Phase 7 Sub-pass A).
 *
 * UBOS's backend is intentionally generic (`entity_type`, `record`,
 * `field_definition`, `relationship`, ...). Real users don't think that way —
 * they run bakeries and furniture stores. This module maps the API's dev
 * vocabulary to human-friendly labels the UI actually renders.
 *
 * Two layers:
 *   1. `DEFAULT_TERMS` — friendly defaults shipped with the app.
 *   2. Per-org overrides stored on `organizations.settings.terminology`
 *      (edited from /settings/terminology by admin+).
 *
 * `t()` is the lookup helper. It's pure, cheap, and called on every render.
 *
 *   const { t } = useTerminology();
 *   <h1>{t("collection.plural")}</h1>                       // "Collections"
 *   <Button>{t("record.new", { collectionName: "Product" })}</Button>
 *   // → "Add new Product"
 *
 * NEVER surface schema keys ("entity_type", "field_definition") in the UI.
 * They exist only in the API layer.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";

/* ────────────── Default vocabulary ────────────── */
export const DEFAULT_TERMS = {
  // ── Structural ──
  "collection.singular": "Collection",
  "collection.plural": "Collections",
  "collection.new": "Add new Collection",
  "collection.help": "A type of thing you're tracking",

  "record.singular": "Item",           // overridden by collection.name_singular
  "record.plural": "Items",
  "record.new": "Add new",             // suffix with collectionName at render
  "record.help": "A single thing you're tracking",

  "field.singular": "Field",
  "field.plural": "Fields",
  "field.help": "A piece of info you track for each item",

  "category.singular": "Category",
  "category.plural": "Categories",

  "tag.singular": "Tag",
  "tag.plural": "Tags",

  "link.singular": "Link",
  "link.plural": "Links",
  "link.help": "How items connect to each other",

  "view.singular": "View",
  "view.plural": "Views",

  "share.public": "Public link",
  "share.password": "Protected link",
  "share.org_only": "Team-only link",

  "role.owner": "Owner",
  "role.admin": "Admin",
  "role.editor": "Editor",
  "role.viewer": "Viewer",

  "audit": "Activity",
  "import": "Import",
  "export": "Export",

  "sensitive_field": "Private field",
  "sensitive_field.help": "Hidden from public share links",

  // ── Sections / navigation ──
  "nav.data": "My Data",
  "nav.workspace": "Workspace",
  "nav.setup": "Setup",
  "nav.settings": "Settings",
  "nav.dashboard": "Home",
  "nav.search": "Search",
  "nav.media": "Files",
  "nav.templates": "Starter Packs",

  // ── Verbs (buttons / CTAs) ──
  "action.add": "Add",
  "action.create": "Create",
  "action.share": "Share",
  "action.link_records": "Link to other data",
  "action.print_labels": "Print labels",
  "action.customize": "Customize",
  "action.use_template": "Use this starter pack",

  // ── Settings-page nav labels ──
  "settings.org": "Organization",
  "settings.members": "Team & Roles",
  "settings.terminology": "Terminology",
  "settings.audit": "Activity",
  "settings.profile": "Profile",
  "settings.labels": "Label Presets",
};

/* ────────────── Core resolver ────────────── */

/** Pure lookup. Called by both the hook path and any non-React caller. */
export function t(key, ctx = {}, overrides = {}) {
  const raw = overrides[key] ?? DEFAULT_TERMS[key] ?? key;

  const cn = ctx.collectionName;
  const cp = ctx.collectionPlural;

  // Context-aware overrides — when we know the current collection, render
  // record.* in that domain's language ("Add new Product" > "Add new Item").
  if (cn) {
    if (key === "record.singular") return cn;
    if (key === "record.plural") return cp || `${cn}s`;
    if (key === "record.new") return `Add new ${cn}`;
  }
  return raw;
}

/* ────────────── React context ────────────── */

const EMPTY = {};

const TerminologyContext = createContext({
  overrides: EMPTY,
  t: (key, ctx) => t(key, ctx, EMPTY),
  saveOverrides: async () => {},
  resetOverrides: async () => {},
  loading: false,
});

/**
 * Provider. Loads `settings.terminology` from the active org and exposes
 * a bound `t()` + save/reset helpers.
 *
 * Kept intentionally lightweight — a single `/api/orgs/:id` fetch per
 * active org, cached until the org changes.
 */
export function TerminologyProvider({ children }) {
  const { activeOrgId } = useAuth();
  const [overrides, setOverrides] = useState(EMPTY);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (orgId) => {
    if (!orgId) {
      setOverrides(EMPTY);
      return;
    }
    setLoading(true);
    try {
      const r = await api.get(`/orgs/${orgId}`);
      const term = (r.data?.settings?.terminology) || EMPTY;
      setOverrides(term);
    } catch {
      setOverrides(EMPTY);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(activeOrgId);
  }, [activeOrgId, load]);

  const boundT = useCallback(
    (key, ctx = {}) => t(key, ctx, overrides),
    [overrides],
  );

  const saveOverrides = useCallback(
    async (next) => {
      if (!activeOrgId) return;
      // Deep-merge is done server-side by PATCH /orgs/:id — we send only the
      // terminology key. To clear a single override, send an empty string.
      await api.patch(`/orgs/${activeOrgId}`, {
        settings: { terminology: next },
      });
      setOverrides(next);
    },
    [activeOrgId],
  );

  const resetOverrides = useCallback(async () => {
    await saveOverrides({});
  }, [saveOverrides]);

  const value = useMemo(
    () => ({ overrides, t: boundT, saveOverrides, resetOverrides, loading }),
    [overrides, boundT, saveOverrides, resetOverrides, loading],
  );

  return (
    <TerminologyContext.Provider value={value}>
      {children}
    </TerminologyContext.Provider>
  );
}

/** Hook for components. */
export function useTerminology() {
  return useContext(TerminologyContext);
}

/** Grouping for the /settings/terminology editor. */
export const TERM_GROUPS = [
  {
    label: "Structural",
    hint: "The core building blocks of your workspace.",
    keys: [
      "collection.singular", "collection.plural", "collection.new", "collection.help",
      "record.singular", "record.plural", "record.new", "record.help",
      "field.singular", "field.plural", "field.help",
      "category.singular", "category.plural",
      "tag.singular", "tag.plural",
      "link.singular", "link.plural", "link.help",
      "view.singular", "view.plural",
      "sensitive_field", "sensitive_field.help",
    ],
  },
  {
    label: "Navigation",
    hint: "Sidebar section names.",
    keys: [
      "nav.dashboard", "nav.data", "nav.setup", "nav.settings",
      "nav.search", "nav.media", "nav.templates", "nav.workspace",
    ],
  },
  {
    label: "Verbs",
    hint: "Buttons and call-to-action labels.",
    keys: [
      "action.add", "action.create", "action.share",
      "action.link_records", "action.print_labels",
      "action.customize", "action.use_template",
    ],
  },
  {
    label: "Sharing & roles",
    hint: "Labels around share links and team roles.",
    keys: [
      "share.public", "share.password", "share.org_only",
      "role.owner", "role.admin", "role.editor", "role.viewer",
    ],
  },
  {
    label: "Settings",
    hint: "Section labels shown in the settings menu.",
    keys: [
      "settings.org", "settings.members", "settings.terminology",
      "settings.audit", "settings.profile", "settings.labels",
    ],
  },
];
