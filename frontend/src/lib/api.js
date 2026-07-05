import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

// Phase 0: no auth yet — but we still send X-Org-Id so the tenant plumbing
// is exercised end-to-end from day one.
const DEFAULT_ORG_ID = "demo-org";

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
    "X-Org-Id": DEFAULT_ORG_ID,
  },
});

// Convenience: pull server-side validation error map ({fields.<key>: msg})
export function extractFieldErrors(err) {
  const data = err?.response?.data;
  if (data?.detail?.errors && typeof data.detail.errors === "object") {
    return data.detail.errors;
  }
  return null;
}

export function extractErrorMessage(err) {
  const data = err?.response?.data;
  if (typeof data?.detail === "string") return data.detail;
  if (data?.detail?.errors) {
    const first = Object.values(data.detail.errors)[0];
    if (first) return first;
  }
  if (Array.isArray(data?.detail)) {
    return data.detail.map((d) => d.msg).join(", ");
  }
  return err?.message || "Something went wrong";
}
