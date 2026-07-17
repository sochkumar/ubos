/**
 * Phase 7 Sub-pass B — Coach mark tours.
 *
 * Uses shepherd.js (~40kb) for guided tours. Each tour is:
 *   { id, steps: [{ id?, title, text, attachTo?, buttons?, when? }] }
 *
 * The `id` is what we persist in `user.preferences.completed_tours[]` so
 * a completed or dismissed tour never re-shows for the same user.
 *
 * Steps `attachTo` uses a CSS selector — we bind to `data-testid` attributes
 * that already exist in the app so the tour code doesn't need special hooks
 * in the page components.
 */

export const TOURS = {
  dashboard: {
    id: "dashboard.intro.v1",
    label: "Dashboard tour",
    steps: [
      {
        id: "welcome",
        title: "Welcome to UBOS 👋",
        text: "This is your <b>Home</b>. It gives you a quick pulse of what's happening in your workspace — recent items, activity, storage, and your collections.",
        buttons: [
          { text: "Skip tour", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.cancel() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "sidebar",
        title: "Your navigation",
        text: "The left sidebar has three sections. <b>Workspace</b> is where you work day-to-day. <b>Setup</b> is for admins configuring things. <b>Settings</b> covers your workspace, team, and profile.",
        attachTo: { element: "[data-testid='nav-my-data']", on: "right" },
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "all-items",
        title: "One place to find everything",
        text: "<b>All Items</b> shows every record across every collection in one browsable feed. Filter by collection, category, or tag — save the view for later.",
        attachTo: { element: "[data-testid='nav-all-items']", on: "right" },
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "tabs",
        title: "Tabs — like Chrome, inside UBOS",
        text: "Every page can be its own tab. Ctrl/⌘-click any link to open it in a new tab without leaving what you're doing. Try Ctrl/⌘+T to open a new tab.",
        attachTo: { element: "[data-testid='tab-bar']", on: "bottom" },
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Got it", action: () => window.__ubosTour?.complete() },
        ],
      },
    ],
  },

  collection: {
    id: "collection.intro.v1",
    label: "Collection tour",
    steps: [
      {
        id: "welcome",
        title: "This is a Collection",
        text: "Every record in this collection lives here. Products, machines, customers — whatever your business tracks. Each row is one <b>item</b>.",
        buttons: [
          { text: "Skip", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.cancel() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "fields",
        title: "Fields shape your records",
        text: "Click <b>Fields</b> in the header (or use the tabs above) to define what data each item captures — text, number, price, image, dropdown, and more.",
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "search",
        title: "Search and filter",
        text: "Use the search box to jump straight to a record, or open the filter bar to slice by category, tag, or field value.",
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "layouts",
        title: "Layouts your way",
        text: "Table, Gallery, Grid, Card, or List — swap layouts to match the moment. Table for scanning, Gallery for visual, Grid for compact.",
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "views",
        title: "Save your favourite view",
        text: "Filtered + sorted + laid out just how you like it? Save it as a <b>view</b>. Come back any time with one click.",
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Got it", action: () => window.__ubosTour?.complete() },
        ],
      },
    ],
  },

  browse: {
    id: "browse.intro.v1",
    label: "All Items tour",
    steps: [
      {
        id: "welcome",
        title: "All Items — everything in one place",
        text: "This view shows records from <b>every</b> collection at once. Great for cross-collection searches like \"anything updated today\" or \"anything tagged Featured\".",
        buttons: [
          { text: "Skip", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.cancel() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "facets",
        title: "Filter across collections",
        text: "The <b>In collection</b>, <b>Category</b>, and <b>Tag</b> filters narrow results across the whole workspace at once.",
        attachTo: { element: "[data-testid='browse-facet-et-trigger']", on: "bottom" },
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "layout",
        title: "Adaptive layouts",
        text: "Switch to Gallery and each collection renders its own priority fields — Products show price + image, Customers show contact info. No config needed.",
        attachTo: { element: "[data-testid='browse-layout-trigger']", on: "bottom" },
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Next", action: () => window.__ubosTour?.next() },
        ],
      },
      {
        id: "save-view",
        title: "Save it as a view",
        text: "Happy with the filter set? Open <b>Views</b> and hit Save. Give it a name and it'll be one click away next time.",
        attachTo: { element: "[data-testid='browse-views-trigger']", on: "bottom" },
        buttons: [
          { text: "Back", classes: "shepherd-button-secondary", action: () => window.__ubosTour?.back() },
          { text: "Got it", action: () => window.__ubosTour?.complete() },
        ],
      },
    ],
  },
};

export function tourById(key) {
  return TOURS[key] || null;
}
