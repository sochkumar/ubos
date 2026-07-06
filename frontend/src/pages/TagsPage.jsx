import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Plus, Tag as TagIcon, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { EmptyState, PageBody, PageHeader } from "@/components/PageChrome";

export default function TagsPage() {
  const { id: etId } = useParams();
  const [et, setEt] = useState(null);
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", color: "", entity_type_scoped: true });
  const [q, setQ] = useState("");

  const load = async () => {
    try {
      const [etRes, tagRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get("/tags", { params: { entity_type_id: etId } }),
      ]);
      setEt(etRes.data);
      setTags(tagRes.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [etId]);

  const createTag = async (e) => {
    e.preventDefault();
    try {
      await api.post("/tags", {
        name: form.name,
        entity_type_id: form.entity_type_scoped ? etId : null,
        color: form.color || null,
      });
      toast.success("Tag created");
      setOpen(false);
      setForm({ name: "", color: "", entity_type_scoped: true });
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const remove = async (t) => {
    if (!window.confirm(`Delete tag "${t.name}"? It will be removed from ${t.usage_count} record(s).`)) return;
    try {
      await api.delete(`/tags/${t.id}`);
      toast.success("Tag deleted");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const filtered = q ? tags.filter((t) => t.name.toLowerCase().includes(q.toLowerCase())) : tags;

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Tags` : "Tags"}
        subtitle="Lightweight labels for records. Tags can be entity-scoped or org-wide."
        breadcrumbs={[
          { label: "My Data", to: "/entity-types" },
          { label: et?.name_plural || "…" },
          { label: "Tags" },
        ]}
        actions={
          <div className="flex gap-2">
            <Input placeholder="Filter…" className="w-[200px]" value={q} onChange={(e) => setQ(e.target.value)} data-testid="tag-filter" />
            <Button onClick={() => setOpen(true)} data-testid="new-tag-btn"><Plus className="w-4 h-4 mr-1.5" /> New tag</Button>
          </div>
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={TagIcon}
            title={q ? "No tags match" : "No tags yet"}
            description={q ? "Try a different filter." : "Create your first tag to start labeling records."}
            action={!q && <Button onClick={() => setOpen(true)}><Plus className="w-4 h-4 mr-1.5" /> New tag</Button>}
          />
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tag</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Usage</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((t) => (
                  <TableRow key={t.id} data-testid={`tag-row-${t.slug}`}>
                    <TableCell>
                      <span
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
                      >
                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: t.color || "#0d9488" }} />
                        {t.name}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="font-mono text-[10px]">
                        {t.entity_type_id ? "entity" : "org-wide"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {t.usage_count} record{t.usage_count === 1 ? "" : "s"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() => remove(t)} data-testid={`delete-tag-${t.slug}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </PageBody>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="new-tag-dialog">
          <form onSubmit={createTag}>
            <DialogHeader>
              <DialogTitle>New tag</DialogTitle>
            </DialogHeader>
            <div className="py-4 space-y-4">
              <div>
                <Label>Name</Label>
                <Input
                  autoFocus required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  data-testid="input-tag-name"
                />
              </div>
              <div>
                <Label>Color (optional)</Label>
                <Input
                  placeholder="#0d9488" value={form.color}
                  onChange={(e) => setForm({ ...form, color: e.target.value })}
                />
              </div>
              <label className="flex items-center gap-3 text-sm cursor-pointer">
                <Switch
                  checked={form.entity_type_scoped}
                  onCheckedChange={(v) => setForm({ ...form, entity_type_scoped: v })}
                  data-testid="tag-scope-switch"
                />
                <div>
                  <div className="font-medium">Scope to {et?.name_plural || "this Collection"}</div>
                  <p className="text-[11px] text-muted-foreground">
                    Off = tag is available across every Collection in this workspace.
                  </p>
                </div>
              </label>
            </div>
            <DialogFooter>
              <Button variant="ghost" type="button" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" data-testid="submit-tag">Create</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
