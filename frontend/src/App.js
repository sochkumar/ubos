import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import AppLayout from "@/layouts/AppLayout";
import EntityTypesPage from "@/pages/EntityTypesPage";
import FieldsPage from "@/pages/FieldsPage";
import RecordsPage from "@/pages/RecordsPage";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/entity-types" replace />} />
            <Route path="/entity-types" element={<EntityTypesPage />} />
            <Route path="/entity-types/:id/fields" element={<FieldsPage />} />
            <Route path="/entity-types/:id/records" element={<RecordsPage />} />
            <Route
              path="*"
              element={<Navigate to="/entity-types" replace />}
            />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        richColors
        toastOptions={{
          classNames: {
            toast: "font-sans",
          },
        }}
      />
    </div>
  );
}

export default App;
