import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Boxes, Plus, Trash2, Layers, ListChecks } from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { toast } from "sonner";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";

const slugify = (s) =>
  s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^[^a-z]+/, "")
    .slice(0, 64);

export default function EntityTypesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name_singular: "",
    name_plural: "",
    key: "",
    description: "",
  });
  const [keyTouched, setKeyTouched] = useState(false);
  const nav = useNavigate();

  const load = async () => {
    try {
      const r = await api.get("/entity-types");
      setItems(r.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const resetForm = () => {
    setForm({ name_singular: "", name_plural: "", key: "", description: "" });
    setKeyTouched(false);
  };

  const submit = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post("/entity-types", form);
      toast.success(`Entity type '${form.name_singular}' created`);
      setOpen(false);
      resetForm();
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const remove = async (et) => {
    if (!window.confirm(`Delete entity type "${et.name_plural}"?\nThis will soft-delete all its fields and records.`))
      return;
    try {
      await api.delete(`/entity-types/${et.id}`);
      toast.success("Deleted");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  return (
    <>
      <PageHeader
        title="Entity Types"
        subtitle="Define the shapes of the things your business tracks."
        breadcrumbs={[{ label: "UBOS" }, { label: "Entity Types" }]}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="new-entity-type-btn">
                <Plus className="w-4 h-4 mr-1.5" /> New entity type
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg" data-testid="entity-type-dialog">
              <form onSubmit={submit}>
                <DialogHeader>
                  <DialogTitle>Create entity type</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="name_singular">Singular name</Label>
                      <Input
                        id="name_singular"
                        data-testid="input-name-singular"
                        value={form.name_singular}
                        onChange={(e) => {
                          const v = e.target.value;
                          setForm((f) => ({
                            ...f,
                            name_singular: v,
                            key: keyTouched ? f.key : slugify(v),
                          }));
                        }}
                        placeholder="Product"
                        required
                      />
                    </div>
                    <div>
                      <Label htmlFor="name_plural">Plural name</Label>
                      <Input
                        id="name_plural"
                        data-testid="input-name-plural"
                        value={form.name_plural}
                        onChange={(e) =>
                          setForm((f) => ({ ...f, name_plural: e.target.value }))
                        }
                        placeholder="Products"
                        required
                      />
                    </div>
                  </div>
                  <div>
                    <Label htmlFor="key">
                      Key <span className="font-mono text-muted-foreground text-xs">(a-z, 0-9, _)</span>
                    </Label>
                    <Input
                      id="key"
                      data-testid="input-key"
                      value={form.key}
                      onChange={(e) => {
                        setKeyTouched(true);
                        setForm((f) => ({ ...f, key: slugify(e.target.value) }));
                      }}
                      placeholder="products"
                      required
                      className="font-mono"
                    />
                  </div>
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Textarea
                      id="description"
                      data-testid="input-description"
                      value={form.description}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, description: e.target.value }))
                      }
                      rows={2}
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={creating} data-testid="submit-entity-type">
                    {creating ? "Creating…" : "Create"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={Boxes}
            title="No entity types yet"
            description="Create your first entity type — a shape for the things your business tracks (products, machines, contracts, clients, anything)."
            action={
              <div className="flex gap-2">
                <Button onClick={() => setOpen(true)} data-testid="empty-new-entity-type">
                  <Plus className="w-4 h-4 mr-1.5" /> New entity type
                </Button>
              </div>
            }
            testId="entity-types-empty"
          />
        ) : (
          <div
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
            data-testid="entity-types-grid"
          >
            {items.map((et) => (
              <Card
                key={et.id}
                className="group border-border hover:border-primary/40 transition-colors"
                data-testid={`entity-card-${et.key}`}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <CardTitle className="truncate">{et.name_plural}</CardTitle>
                      <CardDescription className="font-mono text-xs">
                        {et.key}
                      </CardDescription>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(et)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 text-muted-foreground hover:text-destructive"
                      data-testid={`delete-entity-${et.key}`}
                      aria-label="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pb-3 min-h-[42px]">
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {et.description || (
                      <span className="italic opacity-70">No description</span>
                    )}
                  </p>
                </CardContent>
                <CardFooter className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => nav(`/entity-types/${et.id}/fields`)}
                    data-testid={`fields-btn-${et.key}`}
                  >
                    <Layers className="w-3.5 h-3.5 mr-1.5" /> Fields
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => nav(`/entity-types/${et.id}/records`)}
                    data-testid={`records-btn-${et.key}`}
                  >
                    <ListChecks className="w-3.5 h-3.5 mr-1.5" /> Records
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </PageBody>
    </>
  );
}
