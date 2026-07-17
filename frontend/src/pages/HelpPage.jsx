/**
 * Phase 7 Sub-pass B — Help center.
 *
 * Public route (`/help`) — no auth required.
 * Two sections:
 *   1. Glossary — searchable A→Z dictionary of app-specific terms
 *   2. How-to articles — 6 short guides for common tasks
 *
 * Every glossary term supports deep-linking via `?term=<slug>` so we can
 * put a `?` icon next to any jargon word in the app and pop the reader
 * straight to the matching entry.
 */
import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  BookOpen, ChevronRight, Compass, LayoutGrid, Search as SearchIcon,
  ArrowLeft, Boxes, Layers, Tag as TagIcon, Users, Printer, Upload,
  Share2, Loader2,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/* ───────────────────── glossary ───────────────────── */
const GLOSSARY = [
  { slug: "collection", term: "Collection",
    body: "A collection is a shape that describes one kind of thing your business tracks — Products, Machines, Customers, Contracts. Each collection has its own fields. Some industries call these 'Menu Sections', 'Categories', 'Ranges'." },
  { slug: "item", term: "Item",
    body: "An item (also called a record) is one row in a collection. If your collection is Products, each item is one product. Every item has a record number (like PRO-000123), a title, and the field values you set on the collection." },
  { slug: "field", term: "Field",
    body: "A field is one column of data on a collection. Fields have types — text, number, currency, date, dropdown, image, and 8 more. You add fields to a collection in Setup → Fields." },
  { slug: "category", term: "Category",
    body: "Categories are a hierarchy you build to organize items. A Furniture collection might have Chair → Dining Chair. Categories are per-collection and can nest as deep as you like." },
  { slug: "tag", term: "Tag",
    body: "Tags are colored labels you stick on items for cross-cutting filtering — Featured, Discontinued, Reorder. Tags can be org-wide or scoped to a specific collection." },
  { slug: "view", term: "View",
    body: "A view is a saved combination of filters + sort + layout on a collection (or on All Items). Views are one-click to reapply and can be shared with your workspace." },
  { slug: "workspace", term: "Workspace / Organization",
    body: "A workspace is your isolated tenant. Data in one workspace is invisible to any other. You can have multiple workspaces (e.g. two shops) with different teams." },
  { slug: "all-items", term: "All Items",
    body: "The cross-collection browse view. Shows every item from every collection in one filterable list — useful for 'anything updated today' searches." },
  { slug: "tabs", term: "Tabs",
    body: "Chrome-style tabs inside the app. Ctrl/⌘-click any link to open it in a new tab. Cmd+T for new tab, Cmd+W to close, Cmd+Shift+T to reopen." },
  { slug: "template", term: "Starter Pack",
    body: "A pre-built bundle of collections + fields + sample data (Bakery, Furniture, Jewellery, etc.). Applied from onboarding or Setup → Starter Packs." },
  { slug: "role", term: "Role",
    body: "Each member of your workspace has a role: owner, admin, editor, or viewer. Roles control which actions the user can perform (read, edit, delete, invite, etc.)." },
  { slug: "share-link", term: "Share link",
    body: "A public read-only URL for a single item. Optionally password-protected or expiring. Useful for showing a product to a customer without giving them an account." },
];

/* ───────────────────── how-to articles ───────────────────── */
const HOWTOS = [
  {
    slug: "first-collection", title: "Create your first collection",
    icon: Boxes, minutes: 2,
    body: `
      <ol>
        <li>Open <b>My Data</b> in the sidebar.</li>
        <li>Click <b>Add new Collection</b>. Give it a plural name (e.g. Products) and a singular one (Product).</li>
        <li>Pick an icon and a colour. These show up in badges throughout the app.</li>
        <li>Once created, click into the collection to define its fields, categories, and tags.</li>
      </ol>
      <p>You can rename any collection later — just open it and go to <b>Settings</b>.</p>
    `,
  },
  {
    slug: "import-spreadsheet", title: "Import from a spreadsheet",
    icon: Upload, minutes: 3,
    body: `
      <ol>
        <li>Open the collection you want to import into.</li>
        <li>Click the <b>Import</b> button (top-right of the items list).</li>
        <li>Upload your CSV or Excel file. UBOS will show a preview and let you map spreadsheet columns to collection fields.</li>
        <li>Confirm — imports are dry-run first so you can spot bad rows before writing anything.</li>
      </ol>
      <p>Supported formats: <code>.csv</code>, <code>.xlsx</code>. Max 10,000 rows per import.</p>
    `,
  },
  {
    slug: "share-catalog", title: "Share a public catalog link",
    icon: Share2, minutes: 2,
    body: `
      <ol>
        <li>Open any item you want to share.</li>
        <li>Click the <b>Share</b> button. Pick "Public link".</li>
        <li>Optionally set a password or expiry.</li>
        <li>Copy the URL and send it — anyone with the link can view the item without logging in.</li>
      </ol>
      <p>You can also share a whole collection via <b>Views → Public link</b> (owner/admin only).</p>
    `,
  },
  {
    slug: "print-labels", title: "Print barcode labels",
    icon: Printer, minutes: 2,
    body: `
      <ol>
        <li>Open a collection and select the items you want labels for (checkbox on the left of each row).</li>
        <li>Click <b>Print labels</b> in the toolbar.</li>
        <li>Pick a label preset (Avery 5160, custom, etc.) — or create your own from Settings → Label Presets.</li>
        <li>Preview and print. Barcodes are QR codes that deep-link back to the item in UBOS.</li>
      </ol>
    `,
  },
  {
    slug: "invite-team", title: "Invite teammates",
    icon: Users, minutes: 2,
    body: `
      <ol>
        <li>Go to <b>Settings → Team & Roles</b>.</li>
        <li>Click <b>Invite member</b> and enter their email address.</li>
        <li>Pick a role: owner, admin, editor, or viewer.</li>
        <li>They'll receive an email invite. Once they accept, they'll appear in your team list.</li>
      </ol>
      <p>You can revoke access any time from the same page.</p>
    `,
  },
  {
    slug: "rename-terminology", title: "Speak your own language",
    icon: BookOpen, minutes: 2,
    body: `
      <ol>
        <li>Go to <b>Settings → Terminology</b>.</li>
        <li>Rename any of the app's core nouns — e.g. rename "Collections" to "Menu Sections", "Items" to "Menu Items".</li>
        <li>Or click <b>Apply industry preset</b> to pull in a ready-made mapping (Bakery, Jewellery, Furniture, Furnishing).</li>
        <li>Hit Save. Changes are visible to everyone in your workspace immediately.</li>
      </ol>
    `,
  },
];

/* ───────────────────── page ───────────────────── */
export default function HelpPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [selectedTerm, setSelectedTerm] = useState(null);
  const [selectedHow, setSelectedHow] = useState(null);

  // Deep-link support: /help?term=collection
  useEffect(() => {
    const term = params.get("term");
    const how  = params.get("how");
    if (term)  setSelectedTerm(term);
    if (how)   setSelectedHow(how);
  }, [params]);

  const filteredTerms = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return GLOSSARY;
    return GLOSSARY.filter(
      (g) => g.term.toLowerCase().includes(s) || g.body.toLowerCase().includes(s),
    );
  }, [q]);

  const term = selectedTerm ? GLOSSARY.find((g) => g.slug === selectedTerm) : null;
  const how  = selectedHow  ? HOWTOS.find((h) => h.slug === selectedHow)   : null;

  const openTerm = (slug) => {
    setSelectedTerm(slug); setSelectedHow(null);
    setParams({ term: slug }, { replace: true });
  };
  const openHow = (slug) => {
    setSelectedHow(slug); setSelectedTerm(null);
    setParams({ how: slug }, { replace: true });
  };
  const back = () => {
    setSelectedTerm(null); setSelectedHow(null);
    setParams({}, { replace: true });
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20" data-testid="help-page">
      {/* Header */}
      <header className="border-b border-border bg-white/60 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2" data-testid="help-home-link">
            <LayoutGrid className="w-5 h-5 text-primary" />
            <span className="font-semibold tracking-tight">UBOS</span>
          </Link>
          <span className="text-muted-foreground">/</span>
          <span className="font-medium">Help</span>
          <div className="flex-1" />
          <Button asChild variant="outline" size="sm" data-testid="help-back-to-app">
            <Link to="/">Back to app</Link>
          </Button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Detail view */}
        {term && (
          <div data-testid="help-glossary-detail">
            <Button variant="ghost" size="sm" onClick={back} className="mb-3">
              <ArrowLeft className="w-4 h-4 mr-1" /> All terms
            </Button>
            <h1 className="text-3xl font-semibold tracking-tight mb-3">{term.term}</h1>
            <p className="text-[15px] text-foreground/90 leading-relaxed">{term.body}</p>
          </div>
        )}
        {how && (
          <div data-testid="help-how-detail">
            <Button variant="ghost" size="sm" onClick={back} className="mb-3">
              <ArrowLeft className="w-4 h-4 mr-1" /> All articles
            </Button>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
              <how.icon className="w-3.5 h-3.5" /> {how.minutes} min read
            </div>
            <h1 className="text-3xl font-semibold tracking-tight mb-4">{how.title}</h1>
            <div
              className="prose prose-sm max-w-none text-[15px] leading-relaxed [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:space-y-2 [&_b]:font-semibold [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[12px]"
              dangerouslySetInnerHTML={{ __html: how.body }}
            />
          </div>
        )}

        {/* Overview */}
        {!term && !how && (
          <>
            <h1 className="text-4xl font-semibold tracking-tight">Help center</h1>
            <p className="text-muted-foreground mt-1 max-w-2xl">
              Learn how UBOS works, look up any term, or follow a step-by-step guide for common tasks.
            </p>

            {/* Search */}
            <div className="relative mt-6 mb-8 max-w-lg">
              <SearchIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                data-testid="help-search-input"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search glossary…"
                className="pl-9 h-11 text-[15px]"
              />
            </div>

            {/* How-to articles */}
            <section className="mb-10" data-testid="help-howtos-section">
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <BookOpen className="w-4 h-4" /> How-to articles
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {HOWTOS.map((h) => (
                  <button
                    key={h.slug}
                    type="button"
                    onClick={() => openHow(h.slug)}
                    className="text-left border border-border rounded-lg p-4 bg-white hover:border-primary/50 hover:shadow-sm transition-all"
                    data-testid={`help-howto-${h.slug}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <h.icon className="w-4 h-4 text-primary" />
                      </div>
                      <div className="min-w-0">
                        <div className="font-medium text-sm">{h.title}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">{h.minutes} min read</div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-muted-foreground ml-auto shrink-0 mt-1" />
                    </div>
                  </button>
                ))}
              </div>
            </section>

            {/* Glossary */}
            <section data-testid="help-glossary-section">
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <Compass className="w-4 h-4" /> Glossary
              </h2>
              {filteredTerms.length === 0 ? (
                <div className="text-sm text-muted-foreground italic px-4 py-8 text-center">
                  Nothing matches "{q}". Try a different search.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {filteredTerms.map((g) => (
                    <button
                      key={g.slug}
                      type="button"
                      onClick={() => openTerm(g.slug)}
                      className="text-left border border-border rounded-lg p-3 bg-white hover:border-primary/50 hover:shadow-sm transition-all"
                      data-testid={`help-term-${g.slug}`}
                    >
                      <div className="font-medium text-sm">{g.term}</div>
                      <div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                        {g.body}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
