import React from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Composable React error boundary. Three visual modes:
 *   variant="fullscreen"  → full-page fallback with reload button (used at root)
 *   variant="page"        → inline card, keeps sidebar/topbar visible
 *   variant="widget"      → small inline block so a single dashboard tile can fail
 *                           without wrecking the page
 *
 * Never rethrows — logs to console and posthog if available.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error("[UBOS ErrorBoundary]", this.props.name || "unnamed", error, info);
    try {
      window.posthog?.captureException?.(error, { boundary: this.props.name });
    } catch { /* posthog optional */ }
  }
  reset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };
  render() {
    if (!this.state.hasError) return this.props.children;

    const variant = this.props.variant || "page";
    const isDev = process.env.NODE_ENV !== "production";
    const stack = isDev ? String(this.state.error?.stack || this.state.error) : null;

    if (variant === "fullscreen") {
      return (
        <div className="min-h-screen bg-gradient-to-b from-white to-muted/30 flex items-center justify-center px-4"
          data-testid="error-boundary-root">
          <div className="max-w-md w-full rounded-lg border border-border bg-white p-8 text-center">
            <div className="w-12 h-12 mx-auto rounded-full bg-destructive/10 flex items-center justify-center mb-4">
              <AlertTriangle className="w-6 h-6 text-destructive" />
            </div>
            <h1 className="text-lg font-semibold">Something went wrong</h1>
            <p className="text-sm text-muted-foreground mt-1">
              UBOS ran into an unexpected error. Reloading should get you back on your feet.
            </p>
            <Button
              className="mt-6"
              onClick={() => window.location.reload()}
              data-testid="error-boundary-reload"
            >
              <RefreshCcw className="w-4 h-4 mr-2" /> Reload the app
            </Button>
            {stack && (
              <pre className="mt-6 text-[10px] font-mono text-left bg-muted/40 p-3 rounded overflow-auto max-h-[240px] text-muted-foreground">
                {stack}
              </pre>
            )}
          </div>
        </div>
      );
    }

    if (variant === "widget") {
      return (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs"
          data-testid="error-boundary-widget">
          <div className="flex items-center gap-2 font-medium text-destructive">
            <AlertTriangle className="w-3.5 h-3.5" />
            {this.props.name || "Widget"} couldn&apos;t render
          </div>
          <button
            type="button"
            onClick={this.reset}
            className="mt-1 text-[11px] underline text-destructive/80 hover:text-destructive"
          >
            Try again
          </button>
        </div>
      );
    }

    // page
    return (
      <div className="p-6" data-testid="error-boundary-page">
        <div className="max-w-lg rounded-lg border border-destructive/30 bg-destructive/5 p-6">
          <div className="flex items-center gap-2 font-medium text-destructive">
            <AlertTriangle className="w-4 h-4" /> Something broke on this page
          </div>
          <p className="text-sm text-muted-foreground mt-2">
            You can navigate to another page in the sidebar, or try again.
          </p>
          <div className="mt-4 flex gap-2">
            <Button variant="outline" onClick={this.reset} data-testid="error-boundary-retry">
              <RefreshCcw className="w-4 h-4 mr-1.5" /> Try again
            </Button>
          </div>
          {stack && (
            <pre className="mt-4 text-[10px] font-mono bg-muted/40 p-3 rounded overflow-auto max-h-[240px] text-muted-foreground">
              {stack}
            </pre>
          )}
        </div>
      </div>
    );
  }
}
