import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Deployment feature flags from the backend (`GET /api/app-config`).
 * `singleBusiness` tailors the UI to one business: hides industry Starter Packs,
 * sample data, terminology, and the workspace switcher.
 */
const AppConfigContext = createContext({ singleBusiness: false, globalFields: false, ready: false });

export function AppConfigProvider({ children }) {
  const [cfg, setCfg] = useState({ singleBusiness: false, globalFields: false, ready: false });

  useEffect(() => {
    let cancelled = false;
    api.get("/app-config")
      .then((r) => {
        if (cancelled) return;
        setCfg({
          singleBusiness: !!r.data?.single_business,
          globalFields: !!r.data?.global_fields,
          ready: true,
        });
      })
      .catch(() => { if (!cancelled) setCfg((c) => ({ ...c, ready: true })); });
    return () => { cancelled = true; };
  }, []);

  return <AppConfigContext.Provider value={cfg}>{children}</AppConfigContext.Provider>;
}

export function useAppConfig() {
  return useContext(AppConfigContext);
}
