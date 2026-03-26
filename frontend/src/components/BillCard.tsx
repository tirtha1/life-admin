import { formatDistanceToNow, format, parseISO, differenceInDays } from "date-fns";
import { AlertCircle, Clock } from "lucide-react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import type { Bill } from "@/types";
import { StatusBadge } from "./StatusBadge";

const BILL_TYPE_EMOJI: Record<string, string> = {
  electricity: "⚡",
  water: "💧",
  gas: "🔥",
  internet: "🌐",
  phone: "📱",
  credit_card: "💳",
  insurance: "🛡️",
  subscription: "📺",
  rent: "🏠",
  other: "📄",
};

function DueDateChip({ dueDate }: { dueDate: string | null }) {
  if (!dueDate) return <span className="text-xs text-gray-400">No due date</span>;

  const date = parseISO(dueDate);
  const days = differenceInDays(date, new Date());

  let colorClass = "text-gray-600";
  let icon = <Clock className="w-3 h-3" />;

  if (days < 0) {
    colorClass = "text-red-600 font-semibold";
    icon = <AlertCircle className="w-3 h-3" />;
  } else if (days <= 2) {
    colorClass = "text-orange-600 font-semibold";
    icon = <AlertCircle className="w-3 h-3" />;
  } else if (days <= 7) {
    colorClass = "text-yellow-600";
  }

  const label =
    days < 0
      ? `${Math.abs(days)}d overdue`
      : days === 0
      ? "Due today"
      : `Due in ${days}d`;

  return (
    <span className={clsx("flex items-center gap-1 text-xs", colorClass)}>
      {icon}
      {label} · {format(date, "MMM d")}
    </span>
  );
}

export default function BillCard({ bill }: { bill: Bill }) {
  const navigate = useNavigate();
  const emoji = BILL_TYPE_EMOJI[bill.bill_type] ?? "📄";
  const amount = bill.amount != null
    ? `${bill.currency} ${bill.amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
    : "Amount unknown";

  return (
    <div
      onClick={() => navigate(`/bills/${bill.id}`)}
      className={clsx(
        "bg-white rounded-xl border p-4 cursor-pointer transition-all hover:shadow-md hover:border-blue-200",
        bill.is_overdue && "border-red-200 bg-red-50/30",
        bill.needs_review && !bill.is_overdue && "border-orange-200"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left */}
        <div className="flex items-start gap-3 min-w-0">
          <div className="text-2xl flex-shrink-0 mt-0.5">{emoji}</div>
          <div className="min-w-0">
            <div className="font-semibold text-gray-900 truncate">{bill.provider}</div>
            <div className="text-xs text-gray-500 capitalize mt-0.5">
              {bill.bill_type.replace("_", " ")}
            </div>
            <div className="mt-2">
              <DueDateChip dueDate={bill.due_date} />
            </div>
          </div>
        </div>

        {/* Right */}
        <div className="text-right flex-shrink-0">
          <div className="font-bold text-gray-900 text-lg">{amount}</div>
          <div className="mt-1">
            <StatusBadge status={bill.status} />
          </div>
        </div>
      </div>

      {bill.needs_review && (
        <div className="mt-3 flex items-center gap-1.5 text-xs text-orange-700 bg-orange-50 rounded-lg px-3 py-1.5">
          <AlertCircle className="w-3 h-3" />
          Needs manual review
        </div>
      )}

      {bill.email_subject && (
        <div className="mt-2 text-xs text-gray-400 truncate">
          📧 {bill.email_subject}
        </div>
      )}
    </div>
  );
}
