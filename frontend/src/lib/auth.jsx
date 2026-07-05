import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, tokenStore, setOnAuthLost, resetSessionExpiryGuard } from "@/lib/api";
import { extractErrorMessage } from "@/lib/errors";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState("checking"); // "checking" | "authed" | "guest"
  const [user, setUser] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [activeOrgId, setActiveOrgId] = useState(null);
  const [activeRole, setActiveRole] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const nav = useNavigate();

  const logout = useCallback(async () => {
    try {
      const rt = tokenStore.refresh;
      if (rt) await api.post("/auth/logout", { refresh_token: rt }).catch(() => {});
    } finally {
      tokenStore.clear();
      setUser(null);
      setOrgs([]);
      setActiveOrgId(null);
      setActiveRole(null);
      setPermissions([]);
      setStatus("guest");
      nav("/login");
    }
  }, [nav]);

  useEffect(() => {
    setOnAuthLost(() => {
      tokenStore.clear();
      setStatus("guest");
      setUser(null);
      nav("/login");
    });
  }, [nav]);

  const decodeJwt = (tok) => {
    try {
      const [, b] = tok.split(".");
      return JSON.parse(atob(b.replace(/-/g, "+").replace(/_/g, "/")));
    } catch {
      return {};
    }
  };

  const applyTokens = useCallback(async (data) => {
    tokenStore.set(data);
    // Fresh valid tokens attached — arm the session-expiry guard again so a
    // future 401-then-refresh-fail can fire exactly one toast.
    resetSessionExpiryGuard();
    setActiveOrgId(data.org_id || null);
    setActiveRole(data.role || null);
    setPermissions(data.permissions || []);
    if (data.user) setUser(data.user);
    try {
      const me = await api.get("/auth/me");
      setUser(me.data.user);
      setOrgs(me.data.organizations || []);
      setStatus("authed");
      return me.data;
    } catch (e) {
      setStatus("guest");
      throw e;
    }
  }, []);

  // Bootstrap: if we have a token, load me
  useEffect(() => {
    let cancelled = false;
    const t = tokenStore.access;
    if (!t) {
      setStatus("guest");
      return;
    }
    const claims = decodeJwt(t);
    setActiveOrgId(claims.org_id || null);
    setActiveRole(claims.role || null);
    setPermissions(claims.permissions || []);
    (async () => {
      try {
        const me = await api.get("/auth/me");
        if (cancelled) return;
        setUser(me.data.user);
        setOrgs(me.data.organizations || []);
        setStatus("authed");
      } catch {
        if (cancelled) return;
        tokenStore.clear();
        setStatus("guest");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async ({ email, password }) => {
      const res = await api.post("/auth/login", { email, password });
      await applyTokens(res.data);
      return res.data;
    },
    [applyTokens],
  );

  const register = useCallback(
    async ({ email, password, name }) => {
      const res = await api.post("/auth/register", { email, password, name });
      await applyTokens(res.data);
      return res.data;
    },
    [applyTokens],
  );

  const switchOrg = useCallback(
    async (org_id) => {
      const res = await api.post(`/orgs/${org_id}/switch`);
      await applyTokens(res.data);
      return res.data;
    },
    [applyTokens],
  );

  const refreshMe = useCallback(async () => {
    const me = await api.get("/auth/me");
    setUser(me.data.user);
    setOrgs(me.data.organizations || []);
    return me.data;
  }, []);

  const hasPermission = useCallback((p) => permissions.includes(p), [permissions]);

  const value = {
    status,
    user,
    orgs,
    activeOrgId,
    activeRole,
    permissions,
    login,
    register,
    logout,
    switchOrg,
    refreshMe,
    applyTokens,
    hasPermission,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export { extractErrorMessage };
