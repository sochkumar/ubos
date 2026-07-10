/**
 * Phase 8 — TabBar (visual layer for the multi-tab workspace).
 *
 * Renders the ordered list of tabs from `useTabs()`, drag-reorderable via
 * @dnd-kit, with:
 *   - active tab highlighted
 *   - close button per tab (X)
 *   - + button at the end to open a fresh Dashboard tab
 *   - truncation to 20 chars with tooltip on hover
 *   - icon per tab from Lucide (falls back to Circle)
 *
 * Purely presentational — all state lives in TabsProvider.
 */
import * as React from "react";
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors,
} from "@dnd-kit/core";
import {
  SortableContext, horizontalListSortingStrategy, useSortable, arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Activity, Boxes, Building2, Compass, FolderTree, Gift, GitBranch,
  Home, Image as ImageIcon, Layers, Loader2, Package, Plus, Printer,
  Search, Sparkles, Tag as TagIcon, Type, User as UserIcon, Users,
  X, Circle,
} from "lucide-react";
import { useTabs, MAX_TABS } from "@/lib/tabs";

const ICONS = {
  "home": Home, "compass": Compass, "search": Search, "image": ImageIcon,
  "gift": Gift, "boxes": Boxes, "layers": Layers, "folder-tree": FolderTree,
  "tag": TagIcon, "git-branch": GitBranch, "package": Package,
  "building-2": Building2, "users": Users, "type": Type, "activity": Activity,
  "printer": Printer, "user": UserIcon, "sparkles": Sparkles,
  "loader-2": Loader2,
};

function TabIcon({ name, spin }) {
  const Ico = ICONS[name] || Circle;
  return <Ico className={`w-3.5 h-3.5 shrink-0 ${spin ? "animate-spin" : ""}`} strokeWidth={2} />;
}

function truncate(s, n = 20) {
  if (!s) return "";
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function SortableTab({ tab, active, onActivate, onClose }) {
  const {
    attributes, listeners, setNodeRef, transform, transition, isDragging,
  } = useSortable({ id: tab.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      className={`group flex items-center gap-1.5 pl-2.5 pr-1 h-8 rounded-t-md cursor-pointer select-none border-x border-t transition-colors ${
        active
          ? "bg-white border-border text-foreground"
          : "bg-muted/40 border-transparent text-muted-foreground hover:bg-muted/70 hover:text-foreground"
      }`}
      title={`${tab.title}\n${tab.path}`}
      data-testid={`tab-item-${tab.id}`}
      data-active={active ? "true" : "false"}
    >
      <div
        className="flex items-center gap-1.5 min-w-0 max-w-[180px]"
        onClick={() => onActivate(tab.id)}
        {...listeners}
      >
        <TabIcon name={tab.icon} spin={tab.icon === "loader-2"} />
        <span className="truncate text-[13px] font-medium">{truncate(tab.title, 20)}</span>
      </div>
      <button
        type="button"
        aria-label="Close tab"
        data-testid={`tab-close-${tab.id}`}
        className="opacity-0 group-hover:opacity-100 hover:bg-muted rounded p-0.5 shrink-0 transition-opacity"
        onClick={(e) => {
          e.stopPropagation();
          onClose(tab.id);
        }}
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

export function TabBar() {
  const { tabs, activeId, activateTab, closeTab, reorderTabs, openTab } = useTabs();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const onDragEnd = React.useCallback((e) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    reorderTabs(active.id, over.id);
  }, [reorderTabs]);

  const canOpen = tabs.length < MAX_TABS;

  return (
    <div
      className="flex items-end gap-0.5 px-3 pt-2 border-b border-border bg-muted/20 h-11 shrink-0 overflow-x-auto"
      data-testid="tab-bar"
    >
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={tabs.map((t) => t.id)} strategy={horizontalListSortingStrategy}>
          {tabs.map((t) => (
            <SortableTab
              key={t.id}
              tab={t}
              active={t.id === activeId}
              onActivate={activateTab}
              onClose={closeTab}
            />
          ))}
        </SortableContext>
      </DndContext>
      <button
        type="button"
        aria-label="New tab"
        data-testid="tab-new-btn"
        disabled={!canOpen}
        onClick={() => openTab("/dashboard", { switchTo: true })}
        className={`ml-1 h-8 w-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors ${
          !canOpen ? "opacity-40 cursor-not-allowed" : ""
        }`}
        title={canOpen ? "Open new tab" : `Tab limit reached (${MAX_TABS})`}
      >
        <Plus className="w-4 h-4" />
      </button>
    </div>
  );
}
