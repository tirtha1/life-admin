import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Receipt,
  AlertCircle,
  CheckCircle,
  Clock,
  RefreshCw,
  Zap,
  Bot,
  Loader2,
} from "lucide-react";
import { billsApi, ingestionApi } from "@/services/api";
import BillCard from "@/components/BillCard";
import type { SyncResult } from "@/types";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  sub,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color: string;
  sub?: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
        </div>
        <div className={`p-3 rounded-xl ${color}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [syncPollUntil, setSyncPollUntil] = useState<number | null>(null);

  const getSyncRefetchInterval = () => {
    if (syncPollUntil && Date.now() < syncPollUntil) {
      return 5_000;
    }
    return false;
  };

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["bills", "stats"],
    queryFn: billsApi.stats,
    refetchInterval: () => getSyncRefetchInterval() || 30_000,
  });

  const { data: urgentBills } = useQuery({
    queryKey: ["bills", "extracted"],
    queryFn: () => billsApi.list({ status: "extracted", limit: 5 }),
    refetchInterval: getSyncRefetchInterval,
  });

  const { data: reviewBills } = useQuery({
    queryKey: ["bills", "review_required"],
    queryFn: () => billsApi.list({ status: "review_required", limit: 5 }),
    refetchInterval: getSyncRefetchInterval,
  });

  const syncMutation = useMutation({
    mutationFn: ingestionApi.sync,
    onSuccess: (_result: SyncResult) => {
      setSyncPollUntil(Date.now() + 60_000);
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const agentMutation = useMutation({
    mutationFn: billsApi.runAllPending,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const formatCurrency = (amount: number) =>
    `INR ${amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">
            Your AI-powered life admin overview
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => agentMutation.mutate()}
            disabled={agentMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors"
          >
            {agentMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Bot className="w-4 h-4" />
            )}
            Run Agent
          </button>
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {syncMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Sync Gmail
          </button>
        </div>
      </div>

      {syncMutation.data && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-800">
          {syncMutation.data.message}. New bills will appear after the ingestion
          worker finishes processing.
        </div>
      )}

      {statsLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl border h-28 animate-pulse" />
          ))}
        </div>
      ) : stats ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total Due"
            value={formatCurrency(stats.total_due_amount)}
            icon={Receipt}
            color="bg-blue-100 text-blue-600"
            sub={`${stats.total} bills total`}
          />
          <StatCard
            label="Overdue"
            value={stats.overdue}
            icon={AlertCircle}
            color="bg-red-100 text-red-600"
            sub="Needs immediate attention"
          />
          <StatCard
            label="Paid"
            value={stats.paid}
            icon={CheckCircle}
            color="bg-green-100 text-green-600"
            sub="This month"
          />
          <StatCard
            label="Needs Review"
            value={stats.needs_review}
            icon={Zap}
            color="bg-purple-100 text-purple-600"
            sub="Flagged for review"
          />
        </div>
      ) : null}

      {urgentBills && urgentBills.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-blue-700 mb-3 flex items-center gap-2">
            <Clock className="w-5 h-5" />
            Recent Bills
          </h2>
          <div className="grid gap-3">
            {urgentBills.map((bill) => (
              <BillCard key={bill.id} bill={bill} />
            ))}
          </div>
        </section>
      )}

      {reviewBills && reviewBills.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-orange-700 mb-3 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            Needs Review
          </h2>
          <div className="grid gap-3">
            {reviewBills.map((bill) => (
              <BillCard key={bill.id} bill={bill} />
            ))}
          </div>
        </section>
      )}

      {reviewBills?.length === 0 && urgentBills?.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-300" />
          <p className="text-lg font-medium text-gray-600">All clear!</p>
          <p className="text-sm">
            No pending or overdue bills. Sync Gmail to check for new ones.
          </p>
        </div>
      )}
    </div>
  );
}
