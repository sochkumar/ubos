import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * items = [{ label, to? }]
 * Last item is treated as current (non-link).
 */
export function PageHeader({ title, subtitle, actions, breadcrumbs, testId }) {
  return (
    <div
      className="border-b border-border bg-white px-8 py-5 sticky top-0 z-10 backdrop-blur"
      data-testid={testId || "page-header"}
    >
      {breadcrumbs?.length ? (
        <nav className="flex items-center text-xs text-muted-foreground gap-1 mb-2 font-mono">
          {breadcrumbs.map((b, i) => {
            const last = i === breadcrumbs.length - 1;
            return (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="w-3 h-3 opacity-60" />}
                {b.to && !last ? (
                  <Link
                    to={b.to}
                    className="hover:text-foreground transition-colors"
                    data-testid={`breadcrumb-${i}`}
                  >
                    {b.label}
                  </Link>
                ) : (
                  <span className={last ? "text-foreground" : ""}>
                    {b.label}
                  </span>
                )}
              </span>
            );
          })}
        </nav>
      ) : null}
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1
            className="text-2xl font-semibold tracking-tight text-foreground truncate"
            data-testid="page-title"
          >
            {title}
          </h1>
          {subtitle && (
            <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function PageBody({ children, className = "" }) {
  return (
    <div className={`px-8 py-8 max-w-[1400px] ${className}`}>{children}</div>
  );
}

export function EmptyState({ icon: Icon, title, description, action, testId }) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-white/50 px-8 py-16 text-center"
      data-testid={testId || "empty-state"}
    >
      {Icon && (
        <div className="w-11 h-11 rounded-lg bg-muted flex items-center justify-center mb-4">
          <Icon className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="text-sm text-muted-foreground mt-1.5 max-w-md">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
