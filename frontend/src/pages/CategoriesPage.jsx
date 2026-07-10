import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Trash2, FolderTree, MoveRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { toast } from "sonner";
import { EmptyState, PageBody, PageHeader } from "@/components/PageChrome";
import { CategoryTree } from "@/components/CategoryTreeNode";

function flatten(tree, out = []) {
  for (const n of tree) {
    out.push(n);
    if (n.children && n.children.length) flatten(n.children, out);
  }
  return out;
}

export default function CategoriesPage() {
  const { id: etId } = useParams();
  const nav = useNavigate();
  const [et, setEt] = useState(null);
  const [tree, setTree] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [addParent, setAddParent] = useState(null);
  const [newName, setNewName] = useState("");
  const [confirmDel, setConfirmDel] = useState(null);
  const [cascade, setCascade] = useState(false);

  const flat = useMemo(() => flatten(tree), [tree]);

  const load = async () => {
    try {
      const [etRes, catsRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get(`/entity-types/${etId}/categories`),
      ]);
      setEt(etRes.data);
      setTree(catsRes.data);
      if (selected) {
        const fresh = flatten(catsRes.data).find((n) => n.id === selected.id);
        setSelected(fresh || null);
      }
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [etId]);

  const openAdd = (parent) => {
    setAddParent(parent);
    setNewName("");
    setAddOpen(true);
  };

  const createCat = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/entity-types/${etId}/categories`, {
        name: newName, parent_id: addParent?.id || null,
      });
      setAddOpen(false);
      toast.success("Category created");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const saveDetail = async (patch) => {
    if (!selected) return;
    try {
      const r = await api.patch(`/categories/${selected.id}`, patch);
      toast.success("Saved");
      setSelected({ ...selected, ...r.data });
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const move = async (newParentId) => {
    if (!selected) return;
    try {
      await api.post(`/categories/${selected.id}/move`, { new_parent_id: newParentId || null });
      toast.success("Moved");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const doDelete = async () => {
    if (!confirmDel) return;
    try {
      await api.delete(`/categories/${confirmDel.id}`, { params: { cascade } });
      toast.success(cascade ? "Category + descendants deleted" : "Category deleted (children reparented)");
      setConfirmDel(null); setCascade(false);
      if (selected?.id === confirmDel.id) setSelected(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const onDragStart = (e, node) => {
    e.dataTransfer.setData("application/x-cat", node.id);
    e.dataTransfer.effectAllowed = "move";
  };
  const onDrop = async (e, target) => {
    e.preventDefault();
    const sourceId = e.dataTransfer.getData("application/x-cat");
    if (!sourceId || sourceId === target.id) return;
    try {
      await api.post(`/categories/${sourceId}/move`, { new_parent_id: target.id });
      toast.success("Moved");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };
  const onRootDrop = async (e) => {
    e.preventDefault();
    const sourceId = e.dataTransfer.getData("application/x-cat");
    if (!sourceId) return;
    try {
      await api.post(`/categories/${sourceId}/move`, { new_parent_id: null });
      toast.success("Moved to root");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Categories` : "Categories"}
        subtitle="Hierarchical taxonomy. Drag a node onto another to make it a child; drop on the empty rail to move to root."
        breadcrumbs={[
          { label: "My Data", to: "/entity-types" },
          { label: et?.name_plural || "…" },
          { label: "Categories" },
        ]}
        actions={
          <Button onClick={() => openAdd(null)} data-testid="new-root-category-btn">
            <Plus className="w-4 h-4 mr-1.5" /> New root category
          </Button>
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : tree.length === 0 ? (
          <EmptyState
            icon={FolderTree}
            title="No categories yet"
            description="Create a category tree to group items — e.g. Furniture > Chairs > Ergonomic."
            action={<Button onClick={() => openAdd(null)}><Plus className="w-4 h-4 mr-1.5" /> New root category</Button>}
          />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,320px)_1fr] gap-6">
            <div
              className="rounded-lg border border-border bg-white p-2 min-h-[300px]"
              onDragOver={(e) => e.preventDefault()}
              onDrop={onRootDrop}
              data-testid="cat-tree"
            >
              <CategoryTree
                tree={tree}
                selectedId={selected?.id}
                onSelect={setSelected}
                onAddChild={openAdd}
                onDelete={setConfirmDel}
                onDragStart={onDragStart}
                onDrop={onDrop}
              />
            </div>
            <div>
              {selected ? (
                <DetailPanel
                  key={selected.id}
                  node={selected} flat={flat}
                  onSave={saveDetail} onMove={move}
                />
              ) : (
                <EmptyState
                  icon={FolderTree}
                  title="Pick a category"
                  description="Select a node in the tree to edit its details or move it."
                />
              )}
            </div>
          </div>
        )}
      </PageBody>

      {/* Add dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent data-testid="new-category-dialog">
          <form onSubmit={createCat}>
            <DialogHeader>
              <DialogTitle>
                {addParent ? `New subcategory under "${addParent.name}"` : "New root category"}
              </DialogTitle>
            </DialogHeader>
            <div className="py-4">
              <Label htmlFor="cat-name">Name</Label>
              <Input
                id="cat-name" autoFocus value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required data-testid="input-category-name"
              />
            </div>
            <DialogFooter>
              <Button variant="ghost" type="button" onClick={() => setAddOpen(false)}>Cancel</Button>
              <Button type="submit" data-testid="submit-category">Create</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={!!confirmDel} onOpenChange={(v) => !v && setConfirmDel(null)}>
        <DialogContent data-testid="delete-category-dialog">
          <DialogHeader>
            <DialogTitle>Delete "{confirmDel?.name}"?</DialogTitle>
          </DialogHeader>
          <div className="py-3 space-y-3">
            <label className="flex items-start gap-2 cursor-pointer text-sm">
              <input
                type="checkbox" className="mt-1"
                checked={cascade} onChange={(e) => setCascade(e.target.checked)}
                data-testid="cascade-checkbox"
              />
              <span>
                <b>Cascade</b> — also delete all descendants and remove them from records.
                Otherwise children are reparented to this category's parent.
              </span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDel(null)}>Cancel</Button>
            <Button variant="destructive" onClick={doDelete} data-testid="confirm-delete-category">Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DetailPanel({ node, flat, onSave, onMove }) {
  const [name, setName] = useState(node.name);
  const [description, setDescription] = useState(node.description || "");
  const [color, setColor] = useState(node.color || "");
  const [newParent, setNewParent] = useState(node.parent_id || "__root__");

  // Valid move targets = flat categories minus self + descendants
  const targets = flat.filter(
    (n) => !n.path?.includes(node.id),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Category details</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>Path</Label>
          <p className="text-xs font-mono text-muted-foreground mt-1">
            {node.path_names?.join(" › ")}
          </p>
        </div>
        <div>
          <Label htmlFor="d-name">Name</Label>
          <Input id="d-name" value={name} onChange={(e) => setName(e.target.value)} data-testid="detail-name" />
        </div>
        <div>
          <Label htmlFor="d-desc">Description</Label>
          <Textarea id="d-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </div>
        <div>
          <Label htmlFor="d-color">Color</Label>
          <Input id="d-color" value={color} onChange={(e) => setColor(e.target.value)} placeholder="#0f766e" />
        </div>
        <Button
          onClick={() => onSave({ name, description, color: color || null })}
          data-testid="save-category-detail"
        >
          Save changes
        </Button>

        <div className="pt-4 border-t border-border">
          <Label>Move to…</Label>
          <div className="flex gap-2 mt-1.5">
            <Select value={newParent} onValueChange={setNewParent}>
              <SelectTrigger data-testid="move-parent-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__root__">(root)</SelectItem>
                {targets.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.path_names?.join(" › ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={() => onMove(newParent === "__root__" ? null : newParent)}
              data-testid="move-category-btn"
            >
              <MoveRight className="w-4 h-4 mr-1.5" /> Move
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
