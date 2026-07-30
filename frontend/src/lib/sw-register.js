/**
 * Service worker registration + update-toast wiring.
 * Called from src/index.js. Guarded behind `serviceWorker in navigator`.
 */
import { toast } from "sonner";

let refreshing = false;

export function registerServiceWorker() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;
  // Skip in dev unless explicitly enabled — CRA hot-reload conflicts with SW
  // caching. Note: env vars are strings, so "0"/"false" must count as disabled
  // (a bare truthy-check treats the string "0" as enabled).
  const swFlag = String(process.env.REACT_APP_ENABLE_SW || "").toLowerCase();
  const swEnabled = ["1", "true", "yes", "on"].includes(swFlag);
  if (process.env.NODE_ENV !== "production" && !swEnabled) return;

  window.addEventListener("load", async () => {
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });

      reg.addEventListener("updatefound", () => {
        const installing = reg.installing;
        if (!installing) return;
        installing.addEventListener("statechange", () => {
          if (
            installing.state === "installed" &&
            navigator.serviceWorker.controller
          ) {
            // A new SW is waiting — surface a subtle reload toast.
            toast("New version available", {
              description: "Reload to use the latest UBOS.",
              duration: Infinity,
              action: {
                label: "Reload",
                onClick: () => {
                  installing.postMessage({ type: "skip-waiting" });
                  reg.waiting?.postMessage({ type: "skip-waiting" });
                },
              },
              closeButton: true,
            });
          }
        });
      });

      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (refreshing) return;
        refreshing = true;
        window.location.reload();
      });
    } catch (e) {
      // Never fail the app because of SW issues.
      // eslint-disable-next-line no-console
      console.warn("[UBOS] service worker registration failed", e);
    }
  });
}
