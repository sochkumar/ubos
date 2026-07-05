import { PageHeader, PageBody, EmptyState } from "@/components/PageChrome";
import { LayoutDashboard } from "lucide-react";

export default function ComingSoonPage({ title, phase = "Phase 2", description }) {
  return (
    <>
      <PageHeader
        title={title}
        subtitle={`Planned for ${phase}.`}
        breadcrumbs={[{ label: title }]}
      />
      <PageBody>
        <EmptyState
          icon={LayoutDashboard}
          title={`${title} — Coming in ${phase}`}
          description={description || "This surface is on the roadmap. In the meantime, you can build entity types, fields, and records under Data."}
        />
      </PageBody>
    </>
  );
}
