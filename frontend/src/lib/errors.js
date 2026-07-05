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
