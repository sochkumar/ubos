import axios from "axios";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

const ACCESS_KEY = "ubos.access_token";
const REFRESH_KEY = "ubos.refresh_token";

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Attach bearer on every request
api.interceptors.request.use((config) => {
  const t = tokenStore.access;
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

// Refresh-on-401 with a single in-flight refresh + queue
let refreshInFlight = null;
let onAuthLostCallback = null;
// Session-expiry guard: exactly one toast + one redirect per expiry event,
// even when many in-flight requests all 401 simultaneously. Reset on any
// successful token attach (i.e. after a fresh login).
let _sessionExpiredNotified = false;

export function setOnAuthLost(cb) {
  onAuthLostCallback = cb;
}

/** Called by the login flow after `tokenStore.set(...)` so the guard resets. */
export function resetSessionExpiryGuard() {
  _sessionExpiredNotified = false;
}

async function performRefresh() {
  const refresh_token = tokenStore.refresh;
  if (!refresh_token) throw new Error("no refresh token");
  const res = await axios.post(
    `${API_BASE}/auth/refresh`,
    { refresh_token },
    { headers: { "Content-Type": "application/json" } },
  );
  tokenStore.set(res.data);
  return res.data;
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { config, response } = error;
    if (
      !response ||
      response.status !== 401 ||
      config?._retried ||
      (config?.url || "").includes("/auth/refresh") ||
      (config?.url || "").includes("/auth/login")
    ) {
      throw error;
    }
    try {
      if (!refreshInFlight) {
        refreshInFlight = performRefresh().finally(() => {
          refreshInFlight = null;
        });
      }
      await refreshInFlight;
      config._retried = true;
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${tokenStore.access}`;
      return api.request(config);
    } catch (e) {
      tokenStore.clear();
      // Mark on the error so handleApiError doesn't re-toast.
      error._retriedRefresh = true;
      if (config) config._retriedRefresh = true;
      // Fire exactly one toast + one redirect per expiry event, regardless of
      // how many parallel requests all 401 at the same time.
      if (!_sessionExpiredNotified) {
        _sessionExpiredNotified = true;
        try {
          toast.error("Session expired — please sign in again.", { duration: 6000 });
        } catch { /* toaster might not be mounted yet */ }
        if (onAuthLostCallback) onAuthLostCallback();
      }
      throw error;
    }
  },
);
