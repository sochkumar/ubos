import { useState } from "react";
import { Trash2, FolderTree, Tag as TagIcon, Edit, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { CategoryPicker } from "@/components/CategoryPicker";
import { TagCombobox } from "@/components/TagCombobox";
import { DynamicField } from "@/components/DynamicField";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";
import { BULK_ALLOWED_FIELD_TYPES } from "@/lib/filterOps";

export function BulkToolbar({ etId, selectedIds, onDone, onClear, fields }) {
  const [catOpen, setCatOpen] = useState(false);
  const [tagOpen, setTagOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  const [cats, setCats] = useState([]);
  const [catMode, setCatMode] = useState("add");
  const [tags, setTags] = useState([]);
  const [tagMode, setTagMode] = useState("add");
  const [fkey, setFkey] = useState(null);
  const [fval, setFval] = useState("");
  const [saving, setSaving] = useState(false);

  const editableFields = fields.filter((f) => BULK_ALLOWED_FIELD_TYPES.has(f.type));
  const activeField = editableFields.find((f) => f.key === fkey);

  const run = async (action, payload) => {
    setSaving(true);
    try {
      const r = await api.post(`/entity-types/${etId}/records/bulk`,
        { ids: selectedIds, action, payload });
      const { updated, skipped } = r.data;
      toast.success(`${updated} updated${skipped ? `, ${skipped} skipped` : ""}`);
      onDone();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally { setSaving(false); }
  };

  const doAssignCats = async () => { await run("assign_categories", { mode: catMode, category_ids: cats }); setCatOpen(false); setCats([]); };
  const doAssignTags = async () => { await run("assign_tags", { mode: tagMode, tag_ids: tags }); setTagOpen(false); setTags([]); };
  const doEditField = async () => {
    if (!fkey) return;
    let v = fval;
    if (v === "") v = null;
    await run("update_field", { field_key: fkey, value: v });
    setEditOpen(false); setFkey(null); setFval("");
  };
  const doDelete = async () => { await run("delete", {}); setDelOpen(false); };

  return (
    <div className="sticky top-0 z-20 -mx-8 px-8 py-2 bg-primary text-primary-foreground border-b border-primary/30 flex items-center gap-2 shadow-sm" data-testid="bulk-toolbar">
      <span className="text-sm font-medium">
        {selectedIds.length} selected
      </span>
      <div className="flex-1" />
      <Button variant="ghost" size="sm" className="h-8 text-primary-foreground hover:bg-white/10" onClick={() => setCatOpen(true)} data-testid="bulk-cats-btn">
        <FolderTree className="w-3.5 h-3.5 mr-1" /> Categories
      </Button>
      <Button variant="ghost" size="sm" className="h-8 text-primary-foreground hover:bg-white/10" onClick={() => setTagOpen(true)} data-testid="bulk-tags-btn">
        <TagIcon className="w-3.5 h-3.5 mr-1" /> Tags
      </Button>
      <Button variant="ghost" size="sm" className="h-8 text-primary-foreground hover:bg-white/10" onClick={() => setEditOpen(true)} data-testid="bulk-edit-btn">
        <Edit className="w-3.5 h-3.5 mr-1" /> Edit field
      </Button>
      <Button variant="ghost" size="sm" className="h-8 text-primary-foreground hover:bg-white/10" onClick={() => setDelOpen(true)} data-testid="bulk-del-btn">
        <Trash2 className="w-3.5 h-3.5 mr-1" /> Delete
      </Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-primary-foreground hover:bg-white/10" onClick={onClear} data-testid="bulk-clear-btn">
        <X className="w-4 h-4" />
      </Button>

      {/* Categories */}
      <Dialog open={catOpen} onOpenChange={setCatOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Assign categories to {selectedIds.length} records</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-sm">Mode</Label>
              <Select value={catMode} onValueChange={setCatMode}>
                <SelectTrigger data-testid="bulk-cat-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="add">Add to existing</SelectItem>
                  <SelectItem value="remove">Remove from existing</SelectItem>
                  <SelectItem value="replace">Replace all</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">Categories</Label>
              <CategoryPicker entityTypeId={etId} value={cats} onChange={setCats} testIdPrefix="bulk-cat" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCatOpen(false)}>Cancel</Button>
            <Button onClick={doAssignCats} disabled={saving} data-testid="bulk-cat-submit">Apply</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tags */}
      <Dialog open={tagOpen} onOpenChange={setTagOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Assign tags to {selectedIds.length} records</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-sm">Mode</Label>
              <Select value={tagMode} onValueChange={setTagMode}>
                <SelectTrigger data-testid="bulk-tag-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="add">Add to existing</SelectItem>
                  <SelectItem value="remove">Remove from existing</SelectItem>
                  <SelectItem value="replace">Replace all</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">Tags</Label>
              <TagCombobox entityTypeId={etId} value={tags} onChange={setTags} testIdPrefix="bulk-tag" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setTagOpen(false)}>Cancel</Button>
            <Button onClick={doAssignTags} disabled={saving} data-testid="bulk-tag-submit">Apply</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit field */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Bulk edit field on {selectedIds.length} records</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {editableFields.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No editable field types on this entity. richtext, multi_select, image, file and relation are not supported in Bulk Edit.
              </p>
            ) : (
              <>
                <div>
                  <Label className="text-sm">Field</Label>
                  <Select value={fkey || ""} onValueChange={(v) => { setFkey(v); setFval(""); }}>
                    <SelectTrigger data-testid="bulk-edit-field"><SelectValue placeholder="Choose a field" /></SelectTrigger>
                    <SelectContent>
                      {editableFields.map((f) => (
                        <SelectItem key={f.key} value={f.key}>
                          {f.label} <span className="text-[10px] font-mono text-muted-foreground ml-1">{f.type}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {activeField && (
                  <DynamicField field={activeField} value={fval} onChange={setFval} error={null} />
                )}
                <p className="text-xs text-muted-foreground">
                  Records that fail validation for this field will be skipped.
                </p>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
            <Button onClick={doEditField} disabled={saving || !fkey} data-testid="bulk-edit-submit">Apply</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete */}
      <Dialog open={delOpen} onOpenChange={setDelOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Delete {selectedIds.length} records?</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">
            This soft-deletes the records and updates category / tag usage counts. Records may be recoverable in the future via version history.
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDelOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={doDelete} disabled={saving} data-testid="bulk-del-submit">Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
