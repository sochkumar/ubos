import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth";
import { TerminologyProvider } from "@/lib/terminology";
import { RequireAuth, RequireGuest } from "@/components/RequireAuth";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { GlobalHotkeys } from "@/components/GlobalHotkeys";

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
import LabelPresetsPage from "@/pages/settings/LabelPresetsPage";
import TerminologyPage from "@/pages/settings/TerminologyPage";
import ComingSoonPage from "@/pages/ComingSoonPage";
import CategoriesPage from "@/pages/CategoriesPage";
import TagsPage from "@/pages/TagsPage";
import RelationshipsPage from "@/pages/RelationshipsPage";
import TemplatesPage from "@/pages/TemplatesPage";
import MediaPage from "@/pages/MediaPage";
import PublicRecordPage from "@/pages/PublicRecordPage";
import PublicViewPage from "@/pages/PublicViewPage";
import PublicViewRecordPage from "@/pages/PublicViewRecordPage";
import DashboardPage from "@/pages/DashboardPage";
import SearchPage from "@/pages/SearchPage";
import AcceptInvitationPage from "@/pages/AcceptInvitationPage";

/** Small wrapper — per-page ErrorBoundary so a broken page keeps sidebar/topbar. */
function Page({ name, children }) {
  return (
    <ErrorBoundary name={name} variant="page" key={name}>
      {children}
    </ErrorBoundary>
  );
}

function App() {
  return (
    <ErrorBoundary name="root" variant="fullscreen">
      <div className="App">
        <BrowserRouter>
          <AuthProvider>
            <GlobalHotkeys />
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
              <Route path="/s/:token" element={<PublicRecordPage />} />
              <Route path="/v/:token" element={<PublicViewPage />} />
              <Route path="/v/:token/r/:record_id" element={<PublicViewRecordPage />} />
              <Route path="/invitations/:token/accept" element={<AcceptInvitationPage />} />
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
                    <TerminologyProvider>
                      <AppLayout />
                    </TerminologyProvider>
                  </RequireAuth>
                }
              >
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Page name="Dashboard"><DashboardPage /></Page>} />
                <Route path="/search" element={<Page name="Search"><SearchPage /></Page>} />
                <Route path="/entity-types" element={<Page name="EntityTypes"><EntityTypesPage /></Page>} />
                <Route path="/entity-types/:id/fields" element={<Page name="Fields"><FieldsPage /></Page>} />
                <Route path="/entity-types/:id/records" element={<Page name="Records"><RecordsPage /></Page>} />
                <Route path="/records/:id" element={<Page name="RecordDetail"><RecordDetailPage /></Page>} />
                <Route path="/entity-types/:id/categories" element={<Page name="Categories"><CategoriesPage /></Page>} />
                <Route path="/entity-types/:id/tags" element={<Page name="Tags"><TagsPage /></Page>} />
                <Route path="/entity-types/:id/relationships" element={<Page name="Relationships"><RelationshipsPage /></Page>} />
                <Route path="/templates" element={<Page name="Templates"><TemplatesPage /></Page>} />
                <Route path="/media" element={<Page name="Media"><MediaPage /></Page>} />
                <Route path="/settings/organization" element={<Page name="OrgSettings"><OrgSettingsPage /></Page>} />
                <Route path="/settings/members" element={<Page name="Members"><MembersPage /></Page>} />
                <Route path="/settings/terminology" element={<Page name="Terminology"><TerminologyPage /></Page>} />
                <Route path="/settings/audit-log" element={<Page name="AuditLog"><AuditLogPage /></Page>} />
                <Route path="/settings/label-presets" element={<Page name="LabelPresets"><LabelPresetsPage /></Page>} />
                <Route path="/settings/profile" element={<Page name="Profile"><ProfilePage /></Page>} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
        <Toaster
          position="top-right"
          richColors
          expand
          toastOptions={{
            classNames: { toast: "font-sans" },
            duration: 4000,
          }}
        />
      </div>
    </ErrorBoundary>
  );
}

export default App;
