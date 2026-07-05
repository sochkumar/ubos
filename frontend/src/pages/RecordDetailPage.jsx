import { useEffect, useState, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft, Pencil, Trash2, Paperclip, GitBranch, History, Info,
  MessageSquare, RotateCcw, Sparkles, QrCode,
} from "lucide-react";
import { api } from "@/lib/api";
import { extractErrorMessage, extractFieldErrors } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { DynamicField } from "@/components/DynamicField";
import { CategoryPicker } from "@/components/CategoryPicker";
import { TagCombobox } from "@/components/TagCombobox";
import { formatCellValue } from "@/components/RecordLayouts";
import { AttachmentsPanel } from "@/components/AttachmentsPanel";
import { RelationshipsPanel } from "@/components/RelationshipsPanel";
import { ShareAndPrintPanel } from "@/components/ShareAndPrintPanel";

function initialValues(fields, existing) {
  const v = {};
  fields.forEach((f) => {
    if (existing && existing.fields && existing.fields[f.key] !== undefined) {
      v[f.key] = existing.fields[f.key];
    } else if (f.type === "multi_select") v[f.key] = [];
    else if (f.type === "boolean") v[f.key] = false;
    else v[f.key] = "";
  });
  return v;
}

function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function ActivityIcon({ type }) {
  const map = {
    created: Sparkles,
    updated: Pencil,
    deleted: Trash2,
    comment: MessageSquare,
    restored: RotateCcw,
  };
  const I = map[type] || Info;
  return <I className="w-3.5 h-3.5" />;
}

function ActivityRow({ act, fieldsByKey }) {
  const t = act.type;
  const detail = act.payload || {};
  const diff = detail.diff || {};
  const changedKeys = Object.keys(diff);
  return (
    <div className="flex gap-3 py-3 border-b border-border last:border-b-0">
      <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
        <ActivityIcon type={t} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm">
          <span className="font-medium">{act.actor_name || "System"}</span>
          <span className="text-muted-foreground"> · {t}</span>
          {detail.bulk && <Badge variant="secondary" className="ml-2 text-[10px]">bulk</Badge>}
        </div>
        <div className="text-[11px] font-mono text-muted-foreground">{formatDate(act.ts)}</div>
        {t === "comment" && (
          <div className="mt-1.5 bg-muted/40 rounded-md px-3 py-2 text-sm whitespace-pre-wrap">{detail.text}</div>
        )}
        {t === "updated" && changedKeys.length > 0 && (
          <div className="mt-1.5 space-y-1">
            {changedKeys.slice(0, 6).map((k) => {
              const fd = fieldsByKey[k];
              const label = fd?.label || k;
              const before = diff[k]?.before;
              const after = diff[k]?.after;
              return (
                <div key={k} className="text-xs flex items-baseline gap-1.5 flex-wrap">
                  <span className="font-medium">{label}</span>
                  <span className="line-through text-muted-foreground/70 max-w-[220px] truncate">{String(before ?? "—")}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="text-foreground max-w-[220px] truncate">{String(after ?? "—")}</span>
                </div>
              );
            })}
            {changedKeys.length > 6 && (
              <div className="text-[11px] text-muted-foreground">+{changedKeys.length - 6} more field changes</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function VersionDiffDialog({ record, version, fieldsByKey, onClose, onRestore }) {
  if (!version) return null;
  const currentFields = record?.fields || {};
  const snapFields = version.snapshot?.fields || {};
  const allKeys = Array.from(new Set([...Object.keys(currentFields), ...Object.keys(snapFields)]));
  const changed = allKeys.filter((k) => JSON.stringify(currentFields[k]) !== JSON.stringify(snapFields[k]));

  return (
    <Dialog open={!!version} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Version v{version.version_number}
            <span className="ml-3 text-xs font-mono text-muted-foreground">
              {formatDate(version.changed_at)} · {version.actor_name || "—"}
            </span>
          </DialogTitle>
        </DialogHeader>
        {changed.length === 0 ? (
          <p className="text-sm text-muted-foreground">This version is identical to the current record.</p>
        ) : (
          <div className="rounded-md border border-border overflow-hidden">
            <div className="grid grid-cols-[1fr,1fr] bg-muted/40 px-4 py-2 text-[10px] font-mono uppercase text-muted-foreground">
              <div>This version</div>
              <div>Current</div>
            </div>
            <div className="divide-y divide-border">
              {changed.map((k) => {
                const fd = fieldsByKey[k];
                const label = fd?.label || k;
                return (
                  <div key={k} className="grid grid-cols-[1fr,1fr] px-4 py-2 text-xs">
                    <div>
                      <div className="text-[10px] font-mono text-muted-foreground">{label}</div>
                      <div className="text-red-700/80 line-through max-w-full break-words">
                        {fd ? formatCellValue(fd, snapFields[k]) : String(snapFields[k] ?? "—")}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-mono text-muted-foreground">{label}</div>
                      <div className="text-green-700 max-w-full break-words">
                        {fd ? formatCellValue(fd, currentFields[k]) : String(currentFields[k] ?? "—")}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button onClick={onRestore} disabled={changed.length === 0} data-testid="version-restore-btn">
            <RotateCcw className="w-4 h-4 mr-1.5" /> Restore this version
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function RecordDetailPage() {
  const { id: rid } = useParams();
  const nav = useNavigate();
  const [rec, setRec] = useState(null);
  const [et, setEt] = useState(null);
  const [fields, setFields] = useState([]);
  const [tagsById, setTagsById] = useState({});
  const [catsById, setCatsById] = useState({});
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");

  // Activity
  const [activity, setActivity] = useState([]);
  const [comment, setComment] = useState("");

  // Versions
  const [versions, setVersions] = useState([]);
  const [openVersion, setOpenVersion] = useState(null);

  // Edit
  const [editOpen, setEditOpen] = useState(false);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [recCats, setRecCats] = useState([]);
  const [recTags, setRecTags] = useState([]);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const r = await api.get(`/records/${rid}`);
      setRec(r.data);
      const et_id = r.data.entity_type_id;
      const [etR, flR, tagR, catR] = await Promise.all([
        api.get(`/entity-types/${et_id}`),
        api.get(`/entity-types/${et_id}/fields`),
        api.get("/tags", { params: { entity_type_id: et_id } }),
        api.get(`/entity-types/${et_id}/categories`, { params: { flat: true } }),
      ]);
      setEt(etR.data);
      setFields(flR.data);
      setTagsById(Object.fromEntries(tagR.data.map((t) => [t.id, t])));
      setCatsById(Object.fromEntries(catR.data.map((c) => [c.id, c])));
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally { setLoading(false); }
  };

  const loadActivity = async () => {
    try {
      const r = await api.get(`/records/${rid}/activity`, { params: { limit: 100 } });
      setActivity(r.data.items || []);
    } catch (e) { /* ignore */ }
  };

  const loadVersions = async () => {
    try {
      const r = await api.get(`/records/${rid}/versions`, { params: { limit: 100 } });
      setVersions(r.data.items || []);
    } catch (e) { /* ignore */ }
  };

  useEffect(() => { load(); loadActivity(); loadVersions(); }, [rid]);

  const fieldsByKey = useMemo(() => Object.fromEntries(fields.map((f) => [f.key, f])), [fields]);

  const openEdit = () => {
    setValues(initialValues(fields, rec));
    setRecCats(rec.category_ids || []);
    setRecTags(rec.tag_ids || []);
    setErrors({});
    setEditOpen(true);
  };
  const setField = (key, v) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    if (errors[`fields.${key}`]) {
      setErrors((p) => { const n = { ...p }; delete n[`fields.${key}`]; return n; });
    }
  };
  const submitEdit = async (e) => {
    e.preventDefault();
    setSaving(true); setErrors({});
    const clean = {};
    fields.forEach((f) => {
      const v = values[f.key];
      if (v === "" || v === undefined) return;
      clean[f.key] = v;
    });
    try {
      const r = await api.patch(`/records/${rid}`, { fields: clean, category_ids: recCats, tag_ids: recTags });
      setRec(r.data);
      toast.success("Record updated");
      setEditOpen(false);
      loadActivity(); loadVersions();
    } catch (err) {
      const fe = extractFieldErrors(err);
      if (fe) { setErrors(fe); toast.error("Please fix errors below"); }
      else toast.error(extractErrorMessage(err));
    } finally { setSaving(false); }
  };

  const postComment = async () => {
    if (!comment.trim()) return;
    try {
      await api.post(`/records/${rid}/activity`, { text: comment.trim() });
      setComment("");
      loadActivity();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const restore = async () => {
    if (!openVersion) return;
    try {
      const r = await api.post(`/records/${rid}/versions/${openVersion.version_number}/restore`, { reason: "manual" });
      setRec(r.data);
      toast.success(`Restored to v${openVersion.version_number}`);
      setOpenVersion(null);
      loadActivity(); loadVersions();
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  const deleteRec = async () => {
    if (!window.confirm(`Delete record ${rec.record_number}?`)) return;
    try {
      await api.delete(`/records/${rid}`);
      toast.success("Deleted");
      nav(`/entity-types/${rec.entity_type_id}/records`);
    } catch (e) { toast.error(extractErrorMessage(e)); }
  };

  if (loading) {
    return <PageBody><div className="text-sm text-muted-foreground">Loading…</div></PageBody>;
  }
  if (!rec) {
    return <EmptyState icon={Info} title="Record not found" description="It may have been deleted or you don't have access." />;
  }

  const catList = (rec.category_ids || []).map((id) => catsById[id]).filter(Boolean);
  const tagList = (rec.tag_ids || []).map((id) => tagsById[id]).filter(Boolean);

  return (
    <>
      <PageHeader
        title={rec.title || rec.record_number}
        subtitle={<span className="font-mono">{rec.record_number} · v{rec.version || 1}</span>}
        breadcrumbs={[
          { label: "Entity Types", to: "/entity-types" },
          { label: et?.name_plural || "…", to: `/entity-types/${rec.entity_type_id}/records` },
          { label: "Records", to: `/entity-types/${rec.entity_type_id}/records` },
          { label: rec.record_number },
        ]}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => nav(`/entity-types/${rec.entity_type_id}/records`)} data-testid="back-btn">
              <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
            </Button>
            <Button variant="outline" onClick={openEdit} data-testid="detail-edit-btn">
              <Pencil className="w-4 h-4 mr-1.5" /> Edit
            </Button>
            <Button variant="outline" onClick={deleteRec} className="text-destructive hover:text-destructive" data-testid="detail-delete-btn">
              <Trash2 className="w-4 h-4 mr-1.5" /> Delete
            </Button>
          </div>
        }
      />
      <PageBody>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr,320px] gap-6">
          <div>
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList data-testid="detail-tabs">
                <TabsTrigger value="overview" data-testid="tab-overview"><Info className="w-3.5 h-3.5 mr-1.5" /> Overview</TabsTrigger>
                <TabsTrigger value="activity" data-testid="tab-activity"><MessageSquare className="w-3.5 h-3.5 mr-1.5" /> Activity {activity.length > 0 && <span className="ml-1 text-[10px] font-mono">({activity.length})</span>}</TabsTrigger>
                <TabsTrigger value="versions" data-testid="tab-versions"><History className="w-3.5 h-3.5 mr-1.5" /> Versions {versions.length > 0 && <span className="ml-1 text-[10px] font-mono">({versions.length})</span>}</TabsTrigger>
                <TabsTrigger value="attachments" data-testid="tab-attachments"><Paperclip className="w-3.5 h-3.5 mr-1.5" /> Attachments</TabsTrigger>
                <TabsTrigger value="relationships" data-testid="tab-relationships"><GitBranch className="w-3.5 h-3.5 mr-1.5" /> Relationships</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="mt-4">
                <Card>
                  <CardHeader><CardTitle className="text-base">Fields</CardTitle></CardHeader>
                  <CardContent>
                    {fields.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No fields defined yet.</p>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {fields.map((f) => (
                          <div key={f.id} data-testid={`overview-field-${f.key}`}>
                            <div className="text-[10px] font-mono uppercase text-muted-foreground">{f.label}</div>
                            <div className="text-sm break-words">
                              {formatCellValue(f, rec.fields?.[f.key])}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {rec.description && (
                      <div className="mt-4 pt-4 border-t border-border">
                        <div className="text-[10px] font-mono uppercase text-muted-foreground">Description</div>
                        <div className="text-sm whitespace-pre-wrap mt-1">{rec.description}</div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="activity" className="mt-4 space-y-4">
                <Card>
                  <CardContent className="pt-4">
                    <div className="flex gap-2">
                      <Textarea value={comment} onChange={(e) => setComment(e.target.value)}
                        placeholder="Add a comment…" rows={2}
                        data-testid="comment-input" />
                      <Button onClick={postComment} disabled={!comment.trim()} data-testid="comment-submit">Post</Button>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    {activity.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-6 text-center">No activity yet.</p>
                    ) : (
                      <div className="divide-y-0" data-testid="activity-timeline">
                        {activity.map((a) => (
                          <ActivityRow key={a.id} act={a} fieldsByKey={fieldsByKey} />
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="versions" className="mt-4">
                <Card>
                  <CardContent className="pt-4">
                    {versions.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-6 text-center">No version history yet.</p>
                    ) : (
                      <div className="divide-y divide-border" data-testid="version-list">
                        {versions.map((v) => (
                          <button
                            key={v.id}
                            onClick={() => setOpenVersion(v)}
                            className="w-full text-left flex items-center gap-3 py-3 hover:bg-muted/40 px-2 -mx-2 rounded"
                            data-testid={`version-row-v${v.version_number}`}
                          >
                            <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                              <History className="w-3.5 h-3.5" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-medium">Version v{v.version_number}</div>
                              <div className="text-[11px] font-mono text-muted-foreground">
                                {formatDate(v.changed_at)} · {v.actor_name || "—"}
                                {v.reason && <span className="ml-2">({v.reason})</span>}
                              </div>
                            </div>
                            <Button variant="ghost" size="sm" className="h-7">Compare</Button>
                          </button>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="attachments" className="mt-4">
                <AttachmentsPanel record={rec} />
              </TabsContent>

              <TabsContent value="relationships" className="mt-4">
                <RelationshipsPanel record={rec} />
              </TabsContent>
            </Tabs>
          </div>

          {/* Right rail */}
          <aside className="space-y-4">
            <ShareAndPrintPanel record={rec} fields={fields} />

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Metadata</CardTitle></CardHeader>
              <CardContent className="text-sm space-y-2">
                <div>
                  <div className="text-[10px] font-mono uppercase text-muted-foreground">Created</div>
                  <div>{formatDate(rec.created_at)}</div>
                </div>
                <div>
                  <div className="text-[10px] font-mono uppercase text-muted-foreground">Updated</div>
                  <div>{formatDate(rec.updated_at)}</div>
                </div>
                <div>
                  <div className="text-[10px] font-mono uppercase text-muted-foreground">Version</div>
                  <div>v{rec.version || 1}</div>
                </div>
                {rec.qr_payload && (
                  <div>
                    <div className="text-[10px] font-mono uppercase text-muted-foreground flex items-center gap-1">
                      <QrCode className="w-3 h-3" /> QR payload
                    </div>
                    <div className="text-[11px] font-mono break-all text-muted-foreground" data-testid="qr-payload">{rec.qr_payload}</div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Categories</CardTitle></CardHeader>
              <CardContent>
                {catList.length === 0 ? (
                  <p className="text-xs text-muted-foreground">None</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {catList.map((c) => (
                      <Badge key={c.id} variant="secondary" data-testid={`detail-cat-${c.slug}`}>{c.name}</Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Tags</CardTitle></CardHeader>
              <CardContent>
                {tagList.length === 0 ? (
                  <p className="text-xs text-muted-foreground">None</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {tagList.map((t) => (
                      <span key={t.id} className="text-xs px-2 py-0.5 rounded-full font-medium"
                        style={{ backgroundColor: (t.color || "#0d9488") + "1a", color: t.color || "#0d9488" }}
                        data-testid={`detail-tag-${t.slug}`}>{t.name}</span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </aside>
        </div>
      </PageBody>

      <VersionDiffDialog
        record={rec}
        version={openVersion}
        fieldsByKey={fieldsByKey}
        onClose={() => setOpenVersion(null)}
        onRestore={restore}
      />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[92vh] overflow-y-auto">
          <form onSubmit={submitEdit}>
            <DialogHeader>
              <DialogTitle>Edit record <span className="font-mono text-xs text-primary ml-1">{rec.record_number}</span></DialogTitle>
            </DialogHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
              {fields.map((f) => (
                <div key={f.id}
                  className={f.type === "longtext" || f.type === "richtext" || f.type === "multi_select" ? "md:col-span-2" : ""}>
                  <DynamicField field={f} value={values[f.key]}
                    onChange={(v) => setField(f.key, v)}
                    error={errors[`fields.${f.key}`]} />
                </div>
              ))}
              <div className="md:col-span-2 pt-2 border-t border-border">
                <Label className="text-sm">Categories</Label>
                <CategoryPicker entityTypeId={rec.entity_type_id} value={recCats} onChange={setRecCats} testIdPrefix="detail-cat-picker" />
              </div>
              <div className="md:col-span-2">
                <Label className="text-sm">Tags</Label>
                <TagCombobox entityTypeId={rec.entity_type_id} value={recTags} onChange={setRecTags} testIdPrefix="detail-tag-picker" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={saving} data-testid="detail-edit-submit">
                {saving ? "Saving…" : "Save changes"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
