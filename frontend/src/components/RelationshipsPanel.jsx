import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, X, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { RecordPicker } from "@/components/RecordPicker";

/**
 * Renders all relationship groups for a record and lets the user link/unlink.
 */
export function RelationshipsPanel({ record, onChanged }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [picker, setPicker] = useState(null);

  const load = async () => {
    if (!record?.id) return;
    setLoading(true);
    try {
      const r = await api.get(`/records/${record.id}/relationships`);
      setGroups(r.data.groups || []);
    } catch (e) { toast.error(extractErrorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [record?.id]);

  const unlink = async (grp, target_id) => {
    if (!window.confirm("Remove this link?")) return;
    try {
      await api.delete(`/records/${record.id}/relationships/${target_id}`, {
        params: { rel_def_id: grp.rel_def_id },
      });
      toast.success("Unlinked");
      load();
      onChanged && onChanged();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const link = async (grp, ids) => {
    let ok = 0, err = 0;
    for (const target of ids) {
      try {
        await api.post(`/records/${record.id}/relationships`, {
          rel_def_id: grp.rel_def_id, target_record_id: target,
        });
        ok++;
      } catch (e) {
        err++;
        const msg = e?.response?.data?.detail;
        if (typeof msg === "string") toast.error(msg);
      }
    }
    if (ok) toast.success(`Linked ${ok} record${ok === 1 ? "" : "s"}`);
    if (!ok && err) toast.error("No items were linked");
    load();
    onChanged && onChanged();
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground py-6 text-center">Loading…</p>;
  }
  if (groups.length === 0) {
    return (
      <div className="text-center py-10 space-y-2">
        <GitBranch className="w-8 h-8 mx-auto text-muted-foreground/60" />
        <p className="text-sm text-muted-foreground">
          No relationships defined for this record's type yet.
        </p>
        <p className="text-xs text-muted-foreground">
          Define links from a collection's <span className="font-mono">Open → Links</span> button first.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {groups.map((grp) => (
        <Card key={`${grp.rel_def_id}:${grp.direction}`} data-testid={`rel-group-${grp.rel_def_id}-${grp.direction}`}>
          <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-sm flex items-center gap-2">
                {grp.label}
                <Badge variant="secondary" className="text-[10px]">{grp.items.length}</Badge>
                <span className="text-[10px] font-mono text-muted-foreground">{grp.cardinality}</span>
              </CardTitle>
              {grp.target_entity_type_name && (
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Linked {grp.target_entity_type_name}
                </p>
              )}
            </div>
            <Button size="sm" variant="outline" onClick={() => setPicker(grp)}
              data-testid={`rel-add-${grp.rel_def_id}-${grp.direction}`}>
              <Plus className="w-3.5 h-3.5 mr-1" /> Add
            </Button>
          </CardHeader>
          <CardContent>
            {grp.items.length === 0 ? (
              <p className="text-xs text-muted-foreground">No {grp.label.toLowerCase()} yet.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {grp.items.map((it) => (
                  <div key={it.id}
                    className="group inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-border bg-white hover:border-primary/40 transition-colors"
                    data-testid={`rel-item-${it.id}`}>
                    <Link to={`/records/${it.id}`} className="flex items-center gap-1.5 text-sm">
                      <span className="font-mono text-[10px] text-primary">{it.record_number}</span>
                      <span className="max-w-[180px] truncate">{it.title || "—"}</span>
                    </Link>
                    <button type="button" onClick={() => unlink(grp, it.id)}
                      className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                      data-testid={`rel-remove-${it.id}`}
                      aria-label="Unlink">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {picker && (
        <RecordPicker
          open={!!picker}
          onOpenChange={(v) => !v && setPicker(null)}
          entityTypeId={picker.target_entity_type_id}
          excludeIds={picker.items.map((i) => i.id)}
          multiple={picker.cardinality !== "one_to_one"}
          title={`Add ${picker.label}`}
          onPick={(ids) => link(picker, ids)}
        />
      )}
    </div>
  );
}
