import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Plus, GitBranch, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { slugifyKey } from "@/lib/slugify";
import { toast } from "sonner";
import { EmptyState, PageBody, PageHeader } from "@/components/PageChrome";

const emptyForm = () => ({
  to_entity_type_id: "",
  key: "",
  from_label: "",
  to_label: "",
  cardinality: "one_to_many",
  required: false,
  cascade_delete: false,
  description: "",
});

export default function RelationshipsPage() {
  const { id: etId } = useParams();
  const [et, setEt] = useState(null);
  const [allEts, setAllEts] = useState([]);
  const [rels, setRels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [keyTouched, setKeyTouched] = useState(false);

  const load = async () => {
    try {
      const [etRes, allRes, relRes] = await Promise.all([
        api.get(`/entity-types/${etId}`),
        api.get("/entity-types"),
        api.get(`/entity-types/${etId}/relationships`),
      ]);
      setEt(etRes.data);
      setAllEts(allRes.data);
      setRels(relRes.data);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [etId]);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/entity-types/${etId}/relationships`, form);
      toast.success("Relationship created");
      setOpen(false);
      setForm(emptyForm());
      setKeyTouched(false);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete link "${r.from_label}"?\n\nThis action cannot be undone.`)) return;
    try {
      await api.delete(`/relationships/definitions/${r.id}`);
      toast.success("Relationship deleted");
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const targets = allEts.filter((e) => e.id !== etId);
  const nameById = Object.fromEntries(allEts.map((e) => [e.id, e.name_singular]));

  return (
    <>
      <PageHeader
        title={et ? `${et.name_plural} · Relationships` : "Relationships"}
        subtitle="Schema-level definitions. Record-level instances arrive in Phase 3."
        breadcrumbs={[
          { label: "My Data", to: "/entity-types" },
          { label: et?.name_plural || "…" },
          { label: "Relationships" },
        ]}
        actions={
          <Button onClick={() => setOpen(true)} data-testid="new-rel-btn">
            <Plus className="w-4 h-4 mr-1.5" /> Add a Link
          </Button>
        }
      />
      <PageBody>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : rels.length === 0 ? (
          <EmptyState
            icon={GitBranch}
            title="No relationships defined"
            description={`Define how ${et?.name_plural || "these"} connect to other Collections.`}
            action={<Button onClick={() => setOpen(true)}><Plus className="w-4 h-4 mr-1.5" /> Add a Link</Button>}
          />
        ) : (
          <div className="rounded-lg border border-border bg-white overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>From → To</TableHead>
                  <TableHead>Cardinality</TableHead>
                  <TableHead>Flags</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rels.map((r) => (
                  <TableRow key={r.id} data-testid={`rel-row-${r.key}`}>
                    <TableCell className="font-mono text-xs">{r.key}</TableCell>
                    <TableCell className="text-sm">
                      <span className="font-medium">{et?.name_singular}</span>{" "}
                      <span className="text-muted-foreground">→</span>{" "}
                      <span className="font-medium">{nameById[r.to_entity_type_id] || "?"}</span>
                      <div className="text-[11px] text-muted-foreground font-mono mt-0.5">
                        {r.from_label} / {r.to_label}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="font-mono text-[10px]">{r.cardinality}</Badge>
                    </TableCell>
                    <TableCell className="space-x-1">
                      {r.required && <Badge className="bg-primary/10 text-primary border-transparent">required</Badge>}
                      {r.cascade_delete && <Badge className="bg-destructive/10 text-destructive border-transparent">cascade</Badge>}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() => remove(r)} data-testid={`delete-rel-${r.key}`}
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
        <DialogContent className="sm:max-w-lg" data-testid="new-rel-dialog">
          <form onSubmit={create}>
            <DialogHeader>
              <DialogTitle>Add a link between Collections</DialogTitle>
            </DialogHeader>
            <div className="py-4 space-y-4">
              <div>
                <Label>To Collection</Label>
                <Select
                  value={form.to_entity_type_id}
                  onValueChange={(v) => setForm({ ...form, to_entity_type_id: v })}
                >
                  <SelectTrigger data-testid="rel-to-select">
                    <SelectValue placeholder="Choose a Collection" />
                  </SelectTrigger>
                  <SelectContent>
                    {targets.map((t) => (
                      <SelectItem key={t.id} value={t.id} data-testid={`rel-to-option-${t.key}`}>
                        {t.name_singular}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>From label</Label>
                  <Input
                    value={form.from_label}
                    onChange={(e) => {
                      const v = e.target.value;
                      setForm((f) => ({
                        ...f, from_label: v,
                        key: keyTouched ? f.key : slugifyKey(v),
                      }));
                    }}
                    placeholder="Stored at" required
                    data-testid="rel-from-label"
                  />
                </div>
                <div>
                  <Label>To label</Label>
                  <Input
                    value={form.to_label}
                    onChange={(e) => setForm({ ...form, to_label: e.target.value })}
                    placeholder="Stores" required
                    data-testid="rel-to-label"
                  />
                </div>
              </div>
              <div>
                <Label>Key</Label>
                <Input
                  className="font-mono" value={form.key}
                  onChange={(e) => { setKeyTouched(true); setForm({ ...form, key: slugifyKey(e.target.value) }); }}
                  required placeholder="stored_at"
                  data-testid="rel-key"
                />
              </div>
              <div>
                <Label>Cardinality</Label>
                <RadioGroup value={form.cardinality} onValueChange={(v) => setForm({ ...form, cardinality: v })}>
                  {["one_to_one", "one_to_many", "many_to_many"].map((c) => (
                    <label key={c} className="flex items-center gap-2 text-sm font-mono cursor-pointer">
                      <RadioGroupItem value={c} id={`c-${c}`} data-testid={`rel-card-${c}`} />
                      <Label htmlFor={`c-${c}`}>{c}</Label>
                    </label>
                  ))}
                </RadioGroup>
              </div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <Switch checked={form.required} onCheckedChange={(v) => setForm({ ...form, required: v })} data-testid="rel-required" />
                  Required
                </label>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <Switch checked={form.cascade_delete} onCheckedChange={(v) => setForm({ ...form, cascade_delete: v })} data-testid="rel-cascade" />
                  Cascade delete
                </label>
              </div>
            </div>
            <DialogFooter>
              <Button variant="ghost" type="button" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" data-testid="submit-rel">Create</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
