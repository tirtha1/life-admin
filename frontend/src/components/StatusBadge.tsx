import clsx from "clsx";
import type { BillStatus } from "@/types";

const STATUS_CONFIG: Record<BillStatus, { label: string; className: string }> = {
  detected:        { label: "Detected",     className: "bg-gray-100 text-gray-600" },
  extracted:       { label: "Extracted",    className: "bg-yellow-100 text-yellow-800" },
  review_required: { label: "Needs Review", className: "bg-orange-100 text-orange-800" },
  confirmed:       { label: "Confirmed",    className: "bg-blue-100 text-blue-800" },
  reminded:        { label: "Reminded",     className: "bg-indigo-100 text-indigo-800" },
  paid:            { label: "Paid",         className: "bg-green-100 text-green-800" },
  cancelled:       { label: "Cancelled",    className: "bg-gray-100 text-gray-500" },
  failed:          { label: "Failed",       className: "bg-red-100 text-red-800" },
};

export function StatusBadge({ status }: { status: BillStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.extracted;
  return (
    <span className={clsx("px-2.5 py-0.5 rounded-full text-xs font-medium", config.className)}>
      {config.label}
    </span>
  );
}
