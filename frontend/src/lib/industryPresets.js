/**
 * Phase 7 Sub-pass B — Industry preset registry (frontend).
 *
 * Single source of truth for what appears in:
 *   1. The 3-step onboarding wizard (business-type picker)
 *   2. The "Sample industry presets" dropdown in /settings/terminology
 *
 * Each preset knows:
 *   - a template key (matches a JSON pack in /app/backend/modules/templates/library/)
 *   - what workspace name to suggest by default
 *   - which collections it seeds
 *   - a terminology overlay that turns generic "Collections / Items" into the
 *     industry-friendly nouns (Menu Section / Menu Item, Category / Piece, …)
 *
 * The `terminology` block is ALSO shipped inside each JSON pack so a fresh
 * template application picks it up server-side. This file only mirrors the
 * mapping so users can preview it before choosing, and so the Settings
 * page can re-apply an industry preset later.
 */

export const INDUSTRY_PRESETS = [
  {
    key: "bakery_store",
    emoji: "🥐",
    label: "Bakery / Café / Food",
    tagline: "Menu sections, ingredients, orders, customers",
    suggested_name: "My Bakery",
    collections: ["Menu Sections", "Menu Items", "Ingredients", "Orders", "Customers", "Suppliers"],
    terminology: {
      "collection.singular": "Menu Section",
      "collection.plural":   "Menu Sections",
      "collection.new":      "Add new Menu Section",
      "record.singular":     "Menu Item",
      "record.plural":       "Menu Items",
      "record.new":          "Add new Menu Item",
    },
  },
  {
    key: "jewellery_store",
    emoji: "💎",
    label: "Jewellery Store",
    tagline: "Categories, pieces, materials, hallmarks, customers",
    suggested_name: "Sunny Jewels",
    collections: ["Categories", "Pieces", "Materials", "Customers", "Suppliers"],
    terminology: {
      "collection.singular": "Category",
      "collection.plural":   "Categories",
      "collection.new":      "Add new Category",
      "record.singular":     "Piece",
      "record.plural":       "Pieces",
      "record.new":          "Add new Piece",
    },
  },
  {
    key: "furniture_store",
    emoji: "🛋️",
    label: "Furniture Store",
    tagline: "Product categories, pieces, materials, dimensions",
    suggested_name: "My Furniture Shop",
    collections: ["Categories", "Pieces", "Materials", "Suppliers", "Customers"],
    terminology: {
      "collection.singular": "Category",
      "collection.plural":   "Categories",
      "collection.new":      "Add new Category",
      "record.singular":     "Piece",
      "record.plural":       "Pieces",
      "record.new":          "Add new Piece",
    },
  },
  {
    key: "furnishing_store",
    emoji: "🧵",
    label: "Home Furnishings",
    tagline: "Curtains, cushions, rugs, ranges, fabrics",
    suggested_name: "My Furnishings",
    collections: ["Ranges", "Items", "Fabrics", "Customers"],
    terminology: {
      "collection.singular": "Range",
      "collection.plural":   "Ranges",
      "collection.new":      "Add new Range",
      "record.singular":     "Item",
      "record.plural":       "Items",
      "record.new":          "Add new Item",
    },
  },
  {
    key: "catalog",
    emoji: "🛒",
    label: "General Catalog / Retail",
    tagline: "Categories, products, brands, promotions",
    suggested_name: "My Store",
    collections: ["Categories", "Products", "Brands"],
    terminology: {
      "collection.singular": "Category",
      "collection.plural":   "Categories",
      "record.singular":     "Product",
      "record.plural":       "Products",
    },
  },
  {
    key: "inventory_lite",
    emoji: "📦",
    label: "Inventory / Warehouse",
    tagline: "SKUs, locations, stock movements, suppliers",
    suggested_name: "My Warehouse",
    collections: ["Products", "Locations", "Suppliers"],
    terminology: {
      "record.singular":     "SKU",
      "record.plural":       "SKUs",
    },
  },
  {
    key: "assets",
    emoji: "🏢",
    label: "Assets / Property",
    tagline: "Assets, sites, tenants, maintenance",
    suggested_name: "My Properties",
    collections: ["Assets", "Sites", "Tenants"],
    terminology: {
      "record.singular":     "Asset",
      "record.plural":       "Assets",
    },
  },
  {
    key: "crm_lite",
    emoji: "👥",
    label: "CRM / Contacts",
    tagline: "Contacts, companies, deals, activities",
    suggested_name: "My CRM",
    collections: ["Contacts", "Companies", "Deals"],
    terminology: {
      "collection.singular": "List",
      "collection.plural":   "Lists",
      "record.singular":     "Contact",
      "record.plural":       "Contacts",
    },
  },
];

export function findPresetByKey(key) {
  return INDUSTRY_PRESETS.find((p) => p.key === key) || null;
}
