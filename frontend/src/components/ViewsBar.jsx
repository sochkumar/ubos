import { useState, useEffect } from "react";
import {
  Bookmark, Star, Trash2, Save, Copy, Share2, Plus, Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";

export function ViewsBar({
  entityTypeId,
  activeViewId, onSelectView,
  currentState,        // { layout, q, category_id, tag_ids, filters, sort, visible_fields }
  canShare,            // owner/admin?
}) {
  const [views, setViews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [popOpen, setPopOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveShared, setSaveShared] = useState(false);

  const load = async () => {
    try {
      const r = await api.get(`/entity-types/${entityTypeId}/views`);
      setViews(r.data);
    } catch (e) { /* ignore */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [entityTypeId]);

  const active = views.find((v) => v.id === activeViewId);

  const saveNew = async () => {
    if (!saveName.trim()) return;
    try {
      const body = {
        name: saveName.trim(),
        layout: currentState.layout,
        q: currentState.q || null,
        category_ids: currentState.category_id ? [currentState.category_id] : [],
        tag_ids: currentState.tag_ids || [],
        filters: currentState.filters || [],
        sort: currentState.sort || [],
        visible_fields: currentState.visible_fields || [],
        is_shared: saveShared,
      };
      const r = await api.post(`/entity-types/${entityTypeId}/views`, body);
      toast.success(`View "${r.data.name}" saved`);
      setSaveOpen(false);
      setSaveName(""); setSaveShared(false);
      await load();
      onSelectView(r.data.id);
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const updateActive = async () => {
    if (!active) return;
    try {
      const body = {
        layout: currentState.layout,
        q: currentState.q || null,
        category_ids: currentState.category_id ? [currentState.category_id] : [],
        tag_ids: currentState.tag_ids || [],
        filters: currentState.filters || [],
        sort: currentState.sort || [],
        visible_fields: currentState.visible_fields || [],
      };
      await api.patch(`/views/${active.id}`, body);
      toast.success("View updated");
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const remove = async (v) => {
    if (!window.confirm(`Delete view "${v.name}"?`)) return;
    try {
      await api.delete(`/views/${v.id}`);
      toast.success("View deleted");
      if (activeViewId === v.id) onSelectView(null);
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const duplicate = async (v) => {
    try {
      const r = await api.post(`/views/${v.id}/duplicate`);
      toast.success(`Duplicated as "${r.data.name}"`);
      await load();
      onSelectView(r.data.id);
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const setDefault = async (v) => {
    try {
      await api.post(`/views/${v.id}/set-default`);
      toast.success("Default view set");
      await load();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  return (
    <div className="flex items-center gap-2">
      <Popover open={popOpen} onOpenChange={setPopOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 gap-1.5" data-testid="views-picker">
            <Bookmark className="w-3.5 h-3.5" />
            <span className="max-w-[160px] truncate">{active ? active.name : "All records"}</span>
            {active?.is_shared && <Share2 className="w-3 h-3 opacity-60" />}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[320px] p-1">
          <button
            className={`w-full flex items-center gap-2 text-left px-2 py-1.5 rounded text-sm hover:bg-muted ${!activeViewId ? "bg-primary/10 text-primary font-medium" : ""}`}
            onClick={() => { onSelectView(null); setPopOpen(false); }}
            data-testid="view-option-all"
          >
            <Bookmark className="w-3.5 h-3.5 opacity-50" />
            All records
          </button>
          <div className="h-px bg-border my-1" />
          {loading ? (
            <div className="text-xs text-muted-foreground p-3">Loading…</div>
          ) : views.length === 0 ? (
            <div className="text-xs text-muted-foreground p-3">No saved views yet.</div>
          ) : views.map((v) => (
            <div key={v.id} className={`group flex items-center gap-1 px-2 py-1.5 rounded text-sm hover:bg-muted ${v.id === activeViewId ? "bg-primary/10" : ""}`}>
              <button className="flex-1 text-left flex items-center gap-2 min-w-0"
                onClick={() => { onSelectView(v.id); setPopOpen(false); }}
                data-testid={`view-option-${v.id}`}
              >
                {v.is_default ? <Star className="w-3.5 h-3.5 text-amber-500 shrink-0" /> : <Bookmark className="w-3.5 h-3.5 opacity-50 shrink-0" />}
                <span className={`truncate ${v.id === activeViewId ? "font-medium text-primary" : ""}`}>{v.name}</span>
                {v.is_shared && <Badge variant="secondary" className="text-[9px] px-1.5 h-4 shrink-0">shared</Badge>}
              </button>
              <div className="hidden group-hover:flex items-center">
                <Button size="icon" variant="ghost" className="h-6 w-6" title="Duplicate" onClick={(e) => { e.stopPropagation(); duplicate(v); }} data-testid={`view-dup-${v.id}`}>
                  <Copy className="w-3 h-3" />
                </Button>
                <Button size="icon" variant="ghost" className="h-6 w-6" title="Set default" onClick={(e) => { e.stopPropagation(); setDefault(v); }} data-testid={`view-default-${v.id}`}>
                  <Star className="w-3 h-3" />
                </Button>
                <Button size="icon" variant="ghost" className="h-6 w-6 text-muted-foreground hover:text-destructive" title="Delete"
                  onClick={(e) => { e.stopPropagation(); remove(v); }} data-testid={`view-del-${v.id}`}>
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            </div>
          ))}
        </PopoverContent>
      </Popover>

      {active ? (
        <Button variant="ghost" size="sm" onClick={updateActive} className="h-8" data-testid="view-update-btn">
          <Save className="w-3.5 h-3.5 mr-1" /> Update
        </Button>
      ) : (
        <Button variant="ghost" size="sm" onClick={() => setSaveOpen(true)} className="h-8" data-testid="view-save-btn">
          <Plus className="w-3.5 h-3.5 mr-1" /> Save as view
        </Button>
      )}

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Save current view</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="view-name">Name</Label>
              <Input id="view-name" value={saveName} onChange={(e) => setSaveName(e.target.value)}
                placeholder="e.g. Out of stock chairs" data-testid="view-save-name" />
            </div>
            {canShare && (
              <div className="flex items-center gap-2">
                <Switch checked={saveShared} onCheckedChange={setSaveShared} data-testid="view-save-shared" />
                <Label className="text-sm">Share with the whole workspace</Label>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSaveOpen(false)}>Cancel</Button>
            <Button onClick={saveNew} disabled={!saveName.trim()} data-testid="view-save-submit">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
