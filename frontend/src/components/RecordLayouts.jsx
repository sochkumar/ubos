import { Link } from "react-router-dom";
import { Pencil, Trash2, MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function formatCellValue(field, value) {
  if (value === null || value === undefined || value === "") return "—";
  switch (field.type) {
    case "boolean": return value ? "Yes" : "No";
    case "currency":
      return typeof value === "number"
        ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value)
        : value;
    case "multi_select": return Array.isArray(value) ? value.join(", ") : String(value);
    case "longtext":
    case "richtext":
      return typeof value === "string" && value.length > 60 ? value.slice(0, 60) + "…" : value;
    default: return String(value);
  }
}

function CategoriesInline({ record, catsById }) {
  const first = record.category_ids?.[0] && catsById[record.category_ids[0]];
  if (!first) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span className="text-xs" title={first.path_names?.join(" › ")}>
      {first.name}
      {record.category_ids.length > 1 && (
        <span className="text-muted-foreground"> +{record.category_ids.length - 1}</span>
      )}
    </span>
  );
}

function TagsInline({ record, tagsById, max = 3 }) {
  const ids = record.tag_ids || [];
  return (
    <div className="flex flex-wrap gap-1">
      {ids.slice(0, max).map((tid) => {
        const t = tagsById[tid];
        if (!t) return null;
        return (
          <span key={tid}
            className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
            style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}>
            {t.name}
          </span>
        );
      })}
      {ids.length > max && <span className="text-[10px] text-muted-foreground">+{ids.length - max}</span>}
    </div>
  );
}

export function TableLayout({ records, columns, selected, onToggle, onToggleAll, catsById, tagsById, onEdit, onDelete }) {
  const allSelected = records.length > 0 && records.every((r) => selected.has(r.id));
  return (
    <div className="rounded-lg border border-border bg-white overflow-hidden" data-testid="layout-table">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={allSelected}
                onCheckedChange={onToggleAll}
                data-testid="select-all"
              />
            </TableHead>
            <TableHead className="w-28">Record #</TableHead>
            {columns.map((c) => <TableHead key={c.id}>{c.label}</TableHead>)}
            <TableHead>Category</TableHead>
            <TableHead>Tags</TableHead>
            <TableHead className="text-right w-32">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {records.map((r) => (
            <TableRow key={r.id} data-testid={`record-row-${r.record_number}`}>
              <TableCell>
                <Checkbox
                  checked={selected.has(r.id)}
                  onCheckedChange={() => onToggle(r.id)}
                  data-testid={`select-${r.record_number}`}
                />
              </TableCell>
              <TableCell className="font-mono text-xs">
                <Link to={`/records/${r.id}`} className="text-primary hover:underline" data-testid={`open-record-${r.record_number}`}>
                  {r.record_number}
                </Link>
              </TableCell>
              {columns.map((c) => (
                <TableCell key={c.id} className="max-w-[220px] truncate">
                  {formatCellValue(c, r.fields?.[c.key])}
                </TableCell>
              ))}
              <TableCell><CategoriesInline record={r} catsById={catsById} /></TableCell>
              <TableCell><TagsInline record={r} tagsById={tagsById} /></TableCell>
              <TableCell className="text-right">
                <div className="inline-flex gap-1">
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(r)} data-testid={`edit-record-${r.record_number}`}><Pencil className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => onDelete(r)} data-testid={`delete-record-${r.record_number}`}><Trash2 className="w-4 h-4" /></Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function GalleryLayout({ records, columns, selected, onToggle, catsById, tagsById, onEdit }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3" data-testid="layout-gallery">
      {records.map((r) => (
        <Card key={r.id} className="group relative hover:shadow-md transition-shadow" data-testid={`gallery-card-${r.record_number}`}>
          <div className="absolute top-2 left-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
            <Checkbox checked={selected.has(r.id)} onCheckedChange={() => onToggle(r.id)}
              className="bg-white/90 border-border" data-testid={`select-${r.record_number}`} />
          </div>
          <div className="aspect-video bg-gradient-to-br from-primary/5 via-muted to-muted/50 flex items-center justify-center text-6xl font-bold text-primary/20 font-mono select-none">
            #{r.record_number.replace("REC-", "")}
          </div>
          <CardHeader className="pb-2">
            <CardTitle className="text-base truncate">
              <Link to={`/records/${r.id}`} className="hover:underline" data-testid={`open-record-${r.record_number}`}>
                {r.title || r.record_number}
              </Link>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 pb-3 space-y-1.5">
            {columns.slice(0, 2).map((c) => (
              <div key={c.id} className="text-xs">
                <span className="text-muted-foreground">{c.label}: </span>
                <span>{formatCellValue(c, r.fields?.[c.key])}</span>
              </div>
            ))}
            <TagsInline record={r} tagsById={tagsById} max={4} />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function GridLayout({ records, columns, selected, onToggle, catsById, tagsById, onEdit }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2" data-testid="layout-grid">
      {records.map((r) => (
        <Link
          key={r.id}
          to={`/records/${r.id}`}
          className="group border border-border rounded-lg bg-white p-3 hover:border-primary/50 hover:shadow-sm transition-all relative"
          data-testid={`grid-card-${r.record_number}`}
        >
          <div className="absolute top-1.5 left-1.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle(r.id); }}>
            <Checkbox checked={selected.has(r.id)} onCheckedChange={() => onToggle(r.id)} className="bg-white/90 border-border" data-testid={`select-${r.record_number}`} />
          </div>
          <div className="font-mono text-[10px] text-primary">{r.record_number}</div>
          <div className="text-sm font-medium mt-1 truncate">{r.title || "—"}</div>
          <TagsInline record={r} tagsById={tagsById} max={2} />
        </Link>
      ))}
    </div>
  );
}

export function CardLayout({ records, columns, selected, onToggle, catsById, tagsById, onEdit }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="layout-card">
      {records.map((r) => (
        <Card key={r.id} className="hover:shadow-md transition-shadow relative" data-testid={`card-card-${r.record_number}`}>
          <div className="absolute top-3 left-3 z-10">
            <Checkbox checked={selected.has(r.id)} onCheckedChange={() => onToggle(r.id)} data-testid={`select-${r.record_number}`} />
          </div>
          <CardHeader className="pb-2 pl-10">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="font-mono text-[10px] text-primary">{r.record_number}</div>
                <CardTitle className="text-base truncate">
                  <Link to={`/records/${r.id}`} className="hover:underline" data-testid={`open-record-${r.record_number}`}>
                    {r.title || "—"}
                  </Link>
                </CardTitle>
              </div>
              <CategoriesInline record={r} catsById={catsById} />
            </div>
          </CardHeader>
          <CardContent className="pl-10 pt-0 space-y-2">
            <div className="grid grid-cols-2 gap-2 text-xs">
              {columns.slice(0, 4).map((c) => (
                <div key={c.id} className="min-w-0">
                  <div className="text-muted-foreground text-[10px] font-mono uppercase">{c.label}</div>
                  <div className="truncate">{formatCellValue(c, r.fields?.[c.key])}</div>
                </div>
              ))}
            </div>
            <TagsInline record={r} tagsById={tagsById} max={5} />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function ListLayout({ records, columns, selected, onToggle, catsById, tagsById, onEdit, onDelete }) {
  return (
    <div className="divide-y divide-border rounded-lg border border-border bg-white overflow-hidden" data-testid="layout-list">
      {records.map((r) => (
        <div key={r.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/40" data-testid={`list-item-${r.record_number}`}>
          <Checkbox checked={selected.has(r.id)} onCheckedChange={() => onToggle(r.id)} data-testid={`select-${r.record_number}`} />
          <div className="font-mono text-xs text-primary w-24 shrink-0">{r.record_number}</div>
          <div className="flex-1 min-w-0">
            <Link to={`/records/${r.id}`} className="font-medium text-sm truncate block hover:underline" data-testid={`open-record-${r.record_number}`}>
              {r.title || "—"}
            </Link>
            {columns[0] && (
              <div className="text-xs text-muted-foreground truncate">
                {formatCellValue(columns[0], r.fields?.[columns[0].key])}
              </div>
            )}
          </div>
          <div className="hidden md:block"><TagsInline record={r} tagsById={tagsById} max={3} /></div>
          <div className="hidden lg:block w-40"><CategoriesInline record={r} catsById={catsById} /></div>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(r)} data-testid={`edit-record-${r.record_number}`}><Pencil className="w-4 h-4" /></Button>
        </div>
      ))}
    </div>
  );
}

export const LAYOUTS = [
  { key: "table", label: "Table" },
  { key: "gallery", label: "Gallery" },
  { key: "grid", label: "Grid" },
  { key: "card", label: "Card" },
  { key: "list", label: "List" },
];

export function RecordsLayoutRenderer({ layout, ...props }) {
  switch (layout) {
    case "gallery": return <GalleryLayout {...props} />;
    case "grid": return <GridLayout {...props} />;
    case "card": return <CardLayout {...props} />;
    case "list": return <ListLayout {...props} />;
    case "table":
    default: return <TableLayout {...props} />;
  }
}
