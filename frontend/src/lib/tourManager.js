/**
 * Phase 7 Sub-pass B — Tour runner.
 *
 * Loads shepherd.js on demand, wraps Tour instances with:
 *   - user-preference persistence (completed_tours[] via PATCH /auth/me/preferences)
 *   - dismissable "Don't show again" behavior
 *   - a `useAutoTour(key)` hook that pages call to trigger a tour on mount
 *     if the current user hasn't already completed/dismissed it.
 *
 * Exposes:
 *   startTour(key)            — start a tour by id (from lib/tours.js)
 *   useAutoTour(key)          — mount hook, auto-starts if not completed
 *   markTourComplete(id)      — mark tour done on the server
 *   resetToursForUser()       — clear completed_tours (dev/settings helper)
 */
import { useEffect } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { TOURS, tourById } from "@/lib/tours";

let _shepherdModulePromise = null;
async function loadShepherd() {
  if (_shepherdModulePromise) return _shepherdModulePromise;
  _shepherdModulePromise = (async () => {
    const mod = await import("shepherd.js");
    await import("shepherd.js/dist/css/shepherd.css");
    return mod.default || mod;
  })();
  return _shepherdModulePromise;
}

async function persistCompleted(tourId) {
  try {
    await api.patch("/auth/me/preferences", { completed_tours: [tourId] });
  } catch {
    /* silent — persistence failure shouldn't crash the UI */
  }
}

let _activeTour = null;

export async function startTour(key, { onFinish } = {}) {
  const spec = tourById(key);
  if (!spec) return;
  const Shepherd = await loadShepherd();

  // Dispose any prior tour
  if (_activeTour) {
    try { _activeTour.complete(); } catch { /* noop */ }
    _activeTour = null;
  }

  const tour = new Shepherd.Tour({
    useModalOverlay: true,
    defaultStepOptions: {
      cancelIcon: { enabled: true },
      scrollTo: { behavior: "smooth", block: "center" },
      classes: "ubos-tour-step",
    },
    exitOnEsc: true,
  });

  window.__ubosTour = tour;
  _activeTour = tour;

  for (const step of spec.steps) {
    tour.addStep({
      id: step.id,
      title: step.title,
      text: step.text,
      attachTo: step.attachTo,
      buttons: step.buttons,
      when: step.when,
    });
  }

  const finish = (dismissed) => {
    persistCompleted(spec.id);
    _activeTour = null;
    if (typeof onFinish === "function") onFinish({ dismissed });
    if (!dismissed) {
      toast.success("Tour complete — you can revisit it any time from the ? menu.");
    }
  };
  tour.on("complete", () => finish(false));
  tour.on("cancel",   () => finish(true));

  tour.start();
  return tour;
}

/** Page-level hook. Starts the tour on mount if the user hasn't completed it. */
export function useAutoTour(key) {
  const { user, refreshMe } = useAuth();
  useEffect(() => {
    if (!user || !key) return;
    const spec = tourById(key);
    if (!spec) return;
    const completed = user?.preferences?.completed_tours || [];
    if (completed.includes(spec.id)) return;
    // Delay so the page's DOM (and the elements we'll attach to) has settled.
    const timer = setTimeout(() => {
      startTour(key, { onFinish: () => refreshMe().catch(() => {}) });
    }, 700);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?._id, key]);
}

export async function markTourComplete(key) {
  const spec = tourById(key);
  if (!spec) return;
  await persistCompleted(spec.id);
}

export async function resetToursForUser() {
  // Server-side reset: overwrite with empty list
  await api.patch("/auth/me/preferences", { completed_tours: [] });
}

/** For the "Take the tour" menu entries. */
export const AVAILABLE_TOURS = Object.entries(TOURS).map(([key, spec]) => ({
  key, id: spec.id, label: spec.label,
}));
