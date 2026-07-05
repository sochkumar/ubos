/**
 * Normalize FastAPI + custom error responses into a single human-readable string.
 * - Handles our own `{detail: {errors: {"fields.<k>": msg}}}` shape
 * - Handles FastAPI 422 `{detail: [{msg, loc, ...}]}`
 * - Handles plain `{detail: "..."}`
 */
export function extractErrorMessage(err) {
  const data = err?.response?.data;
  if (!data) return err?.message || "Something went wrong";
  const detail = data.detail;
  if (typeof detail === "string") return detail;
  if (detail?.errors && typeof detail.errors === "object") {
    const first = Object.values(detail.errors)[0];
    if (first) return String(first);
  }
  // {detail: {code:"...", detail:"..."}} → prefer inner detail
  if (detail && typeof detail === "object" && typeof detail.detail === "string") {
    return detail.detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(", ");
  }
  if (detail && typeof detail.msg === "string") return detail.msg;
  if (typeof data === "string") return data;
  return err?.message || "Something went wrong";
}

/** Return the map of field-path → message, or null if not a validation error. */
export function extractFieldErrors(err) {
  const errs = err?.response?.data?.detail?.errors;
  return errs && typeof errs === "object" ? errs : null;
}

/**
 * Centralized axios error handler (Phase 6-A).
 *
 * Uses sonner toasts for user-visible feedback and routes to /login on session
 * expiry. Non-toast alternatives (formCtx.setFieldErrors) can be plugged in
 * for form contexts. Returns the extracted message string so callers may also
 * inline it if they wish.
 *
 * Options:
 *   silent: skip the toast (still returns the message)
 *   formCtx: { setFieldErrors(map) } → for 422 field-level surfacing
 *   context: short label for the failing action (e.g. "save record") — added
 *            to certain generic messages ("Couldn't save record — try again")
 */
import { toast as _toast } from "sonner";

const DUP_KEY = "ubos:last-error";
const DUP_WINDOW_MS = 1500;

function _dedupe(kind, message) {
  try {
    const now = Date.now();
    const raw = sessionStorage.getItem(DUP_KEY);
    if (raw) {
      const prev = JSON.parse(raw);
      if (prev.k === kind && prev.m === message && (now - prev.t) < DUP_WINDOW_MS) {
        return true;
      }
    }
    sessionStorage.setItem(DUP_KEY, JSON.stringify({ k: kind, m: message, t: now }));
  } catch { /* ignore storage failures */ }
  return false;
}

export function handleApiError(err, opts = {}) {
  const { silent, formCtx, context } = opts;
  const status = err?.response?.status ?? 0;
  const detail = err?.response?.data?.detail;
  const code = (detail && typeof detail === "object") ? detail.code : null;
  const message = extractErrorMessage(err);
  const isNetwork = !err?.response && !!err?.message;

  const emit = (kind, text, options = {}) => {
    if (silent) return;
    if (_dedupe(kind, text)) return;
    const durations = { success: 3000, info: 4000, error: 6000 };
    const opts = { duration: durations[kind] || 4000, ...options };
    if (kind === "error") _toast.error(text, opts);
    else if (kind === "success") _toast.success(text, opts);
    else _toast(text, opts);
  };

  // Network / timeout
  if (isNetwork || err?.code === "ECONNABORTED") {
    emit("error", "Connection issue — check your internet and retry.");
    return message;
  }

  switch (status) {
    case 401: {
      // If auth-refresh already tried and failed, the axios interceptor will
      // redirect. We surface a short toast so users understand why.
      const isRefreshFail = err?.config?._retriedRefresh === true;
      if (isRefreshFail) {
        emit("error", "Session expired — sign in again.");
        try {
          const cur = `${window.location.pathname}${window.location.search}`;
          if (!/^\/login/.test(cur)) {
            window.location.assign(`/login?next=${encodeURIComponent(cur)}`);
          }
        } catch { /* location assign guard */ }
      } else {
        emit("error", message || "Not authorized");
      }
      return message;
    }
    case 403:
      emit("error", message || "You don't have permission for this action.");
      return message;
    case 404:
      emit("error", message || "Not found.");
      return message;
    case 409:
      emit("error", message || "Conflict — please refresh and try again.");
      return message;
    case 410:
      emit("error", message || "This link is no longer valid.");
      return message;
    case 413:
      emit("error", "File too large — check storage limits.", {
        action: {
          label: "Storage",
          onClick: () => { window.location.assign("/settings/organization"); },
        },
      });
      return message;
    case 422: {
      const fieldErrors = extractFieldErrors(err);
      if (fieldErrors && formCtx?.setFieldErrors) {
        formCtx.setFieldErrors(fieldErrors);
        // No toast — errors show inline
        return message;
      }
      emit("error", message || "Validation error.");
      return message;
    }
    case 429: {
      const retryAfter = err?.response?.headers?.["retry-after"];
      const hint = retryAfter ? ` Try again in ${retryAfter}s.` : "";
      emit("error", `Too many requests.${hint}`);
      return message;
    }
    case 500:
    case 502:
    case 503:
    case 504:
      emit("error", `Server error — please try again in a moment.${context ? ` (${context})` : ""}`);
      console.error("[UBOS 5xx]", context || err?.config?.url, err);
      return message;
    default:
      emit("error", message || "Something went wrong");
      return message;
  }
}

