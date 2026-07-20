import { FilePieChart } from "lucide-react";
import { ReportGenerator } from "../../lib/core/ReportGenerator";

export default function Reports() {
  return (
    <div className="mx-auto h-full max-w-4xl overflow-y-auto px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <FilePieChart size={22} style={{ color: "var(--blue)" }} />
            Asset Reports
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
            Generate structured condition reports with dynamic failure frequency plots
            and download them as publication-ready PDFs.
          </p>
        </div>
      </div>

      <ReportGenerator />
    </div>
  );
}
