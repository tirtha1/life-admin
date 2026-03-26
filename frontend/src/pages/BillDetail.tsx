import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import {
  ArrowLeft,
  CheckCircle,
  Bot,
  Loader2,
  Calendar,
  AlertCircle,
} from "lucide-react";
import { billsApi } from "@/services/api";
import { StatusBadge } from "@/components/StatusBadge";

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-3 border-b border-gray-100 last:border-0">
      <span className="text-xs text-gray-400 uppercase tracking-wide">{label}</span>
      <span className="text-gray-900 font-medium">{value || "—"}</span>
    </div>
  );
}

export default function BillDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: bill, isLoading } = useQuery({
    queryKey: ["bills", id],
    queryFn: () => billsApi.get(id!),
    enabled: !!id,
  });

  const markPaidMutation = useMutation({
    mutationFn: () => billsApi.markPaid(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const runAgentMutation = useMutation({
    mutationFn: () => billsApi.runAgent(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bills", id] });
      queryClient.invalidateQueries({ queryKey: ["bills", "stats"] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!bill) {
    return (
      <div className="text-center py-20 text-gray-500">
        <AlertCircle className="w-10 h-10 mx-auto mb-3" />
        Bill not found
      </div>
    );
  }

  const amount =
    bill.amount != null
      ? `${bill.currency} ${bill.amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
      : "Unknown";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-gray-500 hover:text-gray-900 text-sm transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      {/* Header card */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{bill.provider}</h1>
            <p className="text-gray-500 capitalize mt-1">
              {bill.bill_type.replace("_", " ")}
            </p>
          </div>
          <StatusBadge status={bill.status} />
        </div>

        <div className="mt-6 flex items-end gap-2">
          <span className="text-4xl font-bold text-gray-900">{amount}</span>
          <span className="text-gray-400 mb-1 text-sm">{bill.currency}</span>
        </div>

        {bill.due_date && (
          <div className="mt-2 flex items-center gap-2 text-sm text-gray-500">
            <Calendar className="w-4 h-4" />
            Due {format(parseISO(bill.due_date), "MMMM d, yyyy")}
          </div>
        )}

        {bill.needs_review && (
          <div className="mt-4 flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-xl px-4 py-3 text-sm text-orange-800">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            This bill needs manual review.
          </div>
        )}

        {/* Actions */}
        <div className="mt-6 flex gap-3">
          {bill.status !== "paid" && (
            <button
              onClick={() => markPaidMutation.mutate()}
              disabled={markPaidMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {markPaidMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle className="w-4 h-4" />
              )}
              Mark as Paid
            </button>
          )}
          <button
            onClick={() => runAgentMutation.mutate()}
            disabled={runAgentMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {runAgentMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Bot className="w-4 h-4" />
            )}
            Re-run Agent
          </button>
        </div>

        {/* Agent result */}
        {runAgentMutation.data && (
          <div className="mt-4 bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
            <strong>Agent result:</strong> {runAgentMutation.data.action} —{" "}
            {runAgentMutation.data.notes}
          </div>
        )}
      </div>

      {/* Bill details */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-2">Bill Details</h2>
        <div>
          <DetailRow
            label="Extraction Confidence"
            value={
              bill.extraction_confidence != null
                ? `${Math.round(bill.extraction_confidence * 100)}%`
                : null
            }
          />
          <DetailRow label="Recurring" value={bill.is_recurring ? "Yes" : "No"} />
          <DetailRow label="Overdue" value={bill.is_overdue ? "Yes" : "No"} />
        </div>
      </div>

      {/* Email source */}
      {bill.email_subject && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-2">Email Source</h2>
          <div>
            <DetailRow label="Subject" value={bill.email_subject} />
          </div>
        </div>
      )}
    </div>
  );
}
