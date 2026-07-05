import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth";
import { RequireAuth, RequireGuest } from "@/components/RequireAuth";

import AppLayout from "@/layouts/AppLayout";
import AuthLayout from "@/layouts/AuthLayout";

import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import ForgotPasswordPage from "@/pages/auth/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/auth/ResetPasswordPage";
import GoogleCallbackPage from "@/pages/auth/GoogleCallbackPage";

import OnboardingPage from "@/pages/OnboardingPage";
import EntityTypesPage from "@/pages/EntityTypesPage";
import FieldsPage from "@/pages/FieldsPage";
import RecordsPage from "@/pages/RecordsPage";
import RecordDetailPage from "@/pages/RecordDetailPage";
import ProfilePage from "@/pages/settings/ProfilePage";
import OrgSettingsPage from "@/pages/settings/OrgSettingsPage";
import MembersPage from "@/pages/settings/MembersPage";
import AuditLogPage from "@/pages/settings/AuditLogPage";
import ComingSoonPage from "@/pages/ComingSoonPage";
import CategoriesPage from "@/pages/CategoriesPage";
import TagsPage from "@/pages/TagsPage";
import RelationshipsPage from "@/pages/RelationshipsPage";
import TemplatesPage from "@/pages/TemplatesPage";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* Public auth routes */}
            <Route element={<AuthLayout />}>
              <Route
                path="/login"
                element={
                  <RequireGuest>
                    <LoginPage />
                  </RequireGuest>
                }
              />
              <Route
                path="/register"
                element={
                  <RequireGuest>
                    <RegisterPage />
                  </RequireGuest>
                }
              />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
            </Route>

            {/* Standalone (no chrome) */}
            <Route path="/auth/google/callback" element={<GoogleCallbackPage />} />
            <Route
              path="/onboarding"
              element={
                <RequireAuth>
                  <OnboardingPage />
                </RequireAuth>
              }
            />

            {/* Authed shell */}
            <Route
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route path="/" element={<Navigate to="/entity-types" replace />} />
              <Route path="/entity-types" element={<EntityTypesPage />} />
              <Route path="/entity-types/:id/fields" element={<FieldsPage />} />
              <Route path="/entity-types/:id/records" element={<RecordsPage />} />
              <Route path="/records/:id" element={<RecordDetailPage />} />
              <Route path="/entity-types/:id/categories" element={<CategoriesPage />} />
              <Route path="/entity-types/:id/tags" element={<TagsPage />} />
              <Route path="/entity-types/:id/relationships" element={<RelationshipsPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route
                path="/dashboard"
                element={<ComingSoonPage title="Dashboard" phase="Phase 4" description="Charts, KPIs, and quick actions across your workspace." />}
              />
              <Route path="/settings/organization" element={<OrgSettingsPage />} />
              <Route path="/settings/members" element={<MembersPage />} />
              <Route path="/settings/audit-log" element={<AuditLogPage />} />
              <Route path="/settings/profile" element={<ProfilePage />} />
              <Route path="*" element={<Navigate to="/entity-types" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster
        position="top-right"
        richColors
        toastOptions={{ classNames: { toast: "font-sans" } }}
      />
    </div>
  );
}

export default App;
