import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";

/**
 * Flat tree renderer. Walks the tree once into a flat list of visible rows
 * (respecting collapsed state), then renders a single list. Avoids recursive
 * JSX which trips the babel-loader stack in some setups.
 */
export function CategoryTree({
  tree,
  selectedId,
  onSelect,
  onAddChild,
  onDelete,
  onDragStart,
  onDrop,
}) {
  const [collapsed, setCollapsed] = useState({});

  const rows = [];
  const walk = (nodes, depth) => {
    for (const n of nodes) {
      const has = n.children && n.children.length > 0;
      const isCollapsed = !!collapsed[n.id];
      rows.push({ node: n, depth, has, collapsed: isCollapsed });
      if (has && !isCollapsed) walk(n.children, depth + 1);
    }
  };
  walk(tree, 0);

  return (
    <div>
      {rows.map(({ node, depth, has, collapsed: c }) => (
        <div
          key={node.id}
          className={"group flex items-center gap-1 px-2 py-1.5 rounded-md text-sm cursor-pointer transition-colors " +
            (selectedId === node.id ? "bg-primary/10 text-primary" : "hover:bg-muted")}
          style={{ paddingLeft: 8 + depth * 16 }}
          onClick={() => onSelect(node)}
          draggable
          onDragStart={(e) => onDragStart(e, node)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => onDrop(e, node)}
          data-testid={"cat-node-" + node.slug}
        >
          {has ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setCollapsed((p) => ({ ...p, [node.id]: !p[node.id] }));
              }}
              className="w-4 h-4 flex items-center justify-center text-muted-foreground"
            >
              {c ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          ) : (
            <span className="w-4 h-4" />
          )}
          <span className="flex-1 truncate">{node.name}</span>
          <span className="text-[10px] font-mono text-muted-foreground opacity-60">
            {node.record_count}
          </span>
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-primary p-1"
            onClick={(e) => { e.stopPropagation(); onAddChild(node); }}
            data-testid={"cat-add-child-" + node.slug}
            aria-label="Add subcategory"
          >
            <Plus className="w-3 h-3" />
          </button>
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive p-1"
            onClick={(e) => { e.stopPropagation(); onDelete(node); }}
            data-testid={"cat-delete-" + node.slug}
            aria-label="Delete"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
