import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles, Trash2, TrendingUp, TrendingDown, IndianRupee } from "lucide-react";
import { transactionsApi } from "@/services/api";
import type { Transaction, TransactionCategory } from "@/types";
import { format, parseISO } from "date-fns";

// ─── Constants ───────────────────────────────────────────────────────────────

const CATEGORY_EMOJI: Record<TransactionCategory | string, string> = {
  food: "🍔",
  transport: "🚗",
  shopping: "🛍️",
  entertainment: "🎬",
  utilities: "💡",
  healthcare: "🏥",
  education: "📚",
  travel: "✈️",
  subscriptions: "🔄",
  other: "💸",
};

const CATEGORY_COLOR: Record<TransactionCategory | string, string> = {
  food: "bg-orange-500",
  transport: "bg-blue-500",
  shopping: "bg-purple-500",
  entertainment: "bg-pink-500",
  utilities: "bg-yellow-500",
  healthcare: "bg-red-500",
  education: "bg-indigo-500",
  travel: "bg-teal-500",
  subscriptions: "bg-gray-500",
  other: "bg-slate-400",
};

function formatINR(amount: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(amount);
}

// ─── Transaction row ──────────────────────────────────────────────────────────

function TransactionRow({
  txn,
  onDelete,
}: {
  txn: Transaction;
  onDelete: (id: number) => void;
}) {
  const emoji = CATEGORY_EMOJI[txn.category] || "💸";
  const isDebit = txn.type === "debit";

  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 group">
      <span className="text-2xl w-9 text-center">{emoji}</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 truncate">
          {txn.merchant || "Unknown merchant"}
        </p>
        <p className="text-xs text-gray-500">
          {format(parseISO(txn.date), "dd MMM yyyy")}
          {txn.source && <span className="ml-2 text-gray-400">via {txn.source}</span>}
        </p>
      </div>
      <div className="text-right">
        <p className={`font-semibold ${isDebit ? "text-red-600" : "text-green-600"}`}>
          {isDebit ? "−" : "+"}₹{formatINR(txn.amount)}
        </p>
        <p className="text-xs text-gray-400 capitalize">{txn.category}</p>
      </div>
      <button
        onClick={() => onDelete(txn.id)}
        className="opacity-0 group-hover:opacity-100 p-1 rounded text-gray-400 hover:text-red-500 transition-all"
        title="Delete"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}

// ─── Category bar ─────────────────────────────────────────────────────────────

function CategoryBar({
  category,
  total,
  percentage,
  count,
}: {
  category: string;
  total: number;
  percentage: number;
  count: number;
}) {
  const color = CATEGORY_COLOR[category] || "bg-slate-400";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="font-medium text-gray-700 capitalize">
          {CATEGORY_EMOJI[category]} {category}
          <span className="text-gray-400 font-normal ml-1">({count})</span>
        </span>
        <span className="text-gray-900 font-semibold">₹{formatINR(total)}</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${Math.max(percentage, 2)}%` }}
        />
      </div>
      <p className="text-xs text-gray-400 text-right">{percentage}%</p>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Transactions() {
  const [days, setDays] = useState(30);
  const [showInsights, setShowInsights] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const qc = useQueryClient();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["spend-stats", days],
    queryFn: () => transactionsApi.stats(days),
    refetchInterval: 60_000,
  });

  const { data: transactions, isLoading: txnsLoading } = useQuery({
    queryKey: ["transactions", days, categoryFilter],
    queryFn: () =>
      transactionsApi.list({
        limit: 100,
        ...(categoryFilter !== "all" && { category: categoryFilter }),
        date_from: new Date(Date.now() - days * 86400000).toISOString().slice(0, 10),
      }),
    refetchInterval: 60_000,
  });

  const { data: insights, isLoading: insightsLoading, refetch: fetchInsights } = useQuery({
    queryKey: ["insights", days],
    queryFn: () => transactionsApi.insights(days),
    enabled: showInsights,
    staleTime: 300_000,
  });

  const syncMutation = useMutation({
    mutationFn: transactionsApi.sync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["spend-stats"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => transactionsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["spend-stats"] });
    },
  });

  const debits = transactions?.filter((t) => t.type === "debit") ?? [];
  const credits = transactions?.filter((t) => t.type === "credit") ?? [];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Spending Tracker</h1>
          <p className="text-gray-500 text-sm mt-1">
            UPI, bank debits &amp; payment app transactions from Gmail
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Period selector */}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>

          {/* Insights toggle */}
          <button
            onClick={() => {
              setShowInsights((v) => !v);
              if (!showInsights) fetchInsights();
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            AI Insights
          </button>

          {/* Sync */}
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? "animate-spin" : ""}`} />
            {syncMutation.isPending ? "Syncing…" : "Sync Gmail"}
          </button>
        </div>
      </div>

      {/* Sync result banner */}
      {syncMutation.isSuccess && syncMutation.data && (
        <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg text-sm">
          Synced {syncMutation.data.emails_scanned} emails — found{" "}
          <strong>{syncMutation.data.transactions_new}</strong> new transactions
          {syncMutation.data.transactions_skipped > 0 &&
            `, ${syncMutation.data.transactions_skipped} already stored`}
        </div>
      )}

      {/* AI Insights panel */}
      {showInsights && (
        <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-5 h-5 text-purple-600" />
            <h2 className="font-semibold text-purple-900">AI Spending Insights</h2>
          </div>
          {insightsLoading ? (
            <p className="text-purple-600 text-sm animate-pulse">Analysing your spending…</p>
          ) : (
            <ul className="space-y-2">
              {insights?.insights.map((insight, i) => (
                <li key={i} className="flex gap-2 text-sm text-purple-800">
                  <span className="mt-0.5 text-purple-400">•</span>
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Stat cards */}
      {statsLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl p-5 border border-gray-200 animate-pulse h-24" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl p-5 border border-gray-200">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">This Month</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">
              ₹{formatINR(stats?.total_this_month ?? 0)}
            </p>
          </div>
          <div className="bg-white rounded-xl p-5 border border-gray-200">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Today</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">
              ₹{formatINR(stats?.total_today ?? 0)}
            </p>
          </div>
          <div className="bg-white rounded-xl p-5 border border-gray-200">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">This Week</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">
              ₹{formatINR(stats?.total_this_week ?? 0)}
            </p>
          </div>
          <div className="bg-white rounded-xl p-5 border border-gray-200">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Transactions</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">
              {stats?.transaction_count ?? 0}
            </p>
            {stats?.top_merchant && (
              <p className="text-xs text-gray-400 mt-1 truncate">Top: {stats.top_merchant}</p>
            )}
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-3 gap-6">
        {/* Category breakdown */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <h2 className="font-semibold text-gray-900">By Category</h2>
          {statsLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-8 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : stats?.category_breakdown.length === 0 ? (
            <p className="text-gray-400 text-sm">No spend data yet.</p>
          ) : (
            <div className="space-y-4">
              {stats?.category_breakdown.map((c) => (
                <CategoryBar
                  key={c.category}
                  category={c.category}
                  total={c.total}
                  percentage={c.percentage}
                  count={c.count}
                />
              ))}
            </div>
          )}
        </div>

        {/* Transaction list */}
        <div className="md:col-span-2 bg-white rounded-xl border border-gray-200 overflow-hidden">
          {/* Filters */}
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2 flex-wrap">
            <h2 className="font-semibold text-gray-900 mr-2">Transactions</h2>
            {["all", "food", "transport", "shopping", "entertainment", "utilities", "other"].map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${
                  categoryFilter === cat
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {cat === "all" ? "All" : `${CATEGORY_EMOJI[cat]} ${cat}`}
              </button>
            ))}
          </div>

          {txnsLoading ? (
            <div className="divide-y divide-gray-100">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="px-4 py-3 flex gap-3 items-center">
                  <div className="w-9 h-9 bg-gray-100 rounded-full animate-pulse" />
                  <div className="flex-1 space-y-1">
                    <div className="h-4 bg-gray-100 rounded animate-pulse w-40" />
                    <div className="h-3 bg-gray-100 rounded animate-pulse w-24" />
                  </div>
                  <div className="h-5 bg-gray-100 rounded animate-pulse w-20" />
                </div>
              ))}
            </div>
          ) : transactions?.length === 0 ? (
            <div className="p-10 text-center">
              <IndianRupee className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No transactions yet</p>
              <p className="text-gray-400 text-sm mt-1">
                Click "Sync Gmail" to fetch your bank &amp; UPI alerts.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 max-h-[480px] overflow-y-auto">
              {transactions?.map((txn) => (
                <TransactionRow
                  key={txn.id}
                  txn={txn}
                  onDelete={(id) => deleteMutation.mutate(id)}
                />
              ))}
            </div>
          )}

          {/* Debit / credit summary footer */}
          {transactions && transactions.length > 0 && (
            <div className="border-t border-gray-100 px-4 py-3 flex gap-6 text-sm bg-gray-50">
              <span className="flex items-center gap-1 text-red-600">
                <TrendingDown className="w-4 h-4" />
                <strong>{debits.length}</strong> debits
              </span>
              <span className="flex items-center gap-1 text-green-600">
                <TrendingUp className="w-4 h-4" />
                <strong>{credits.length}</strong> credits
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Daily spend timeline */}
      {stats && stats.daily_spend.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-900 mb-4">Daily Spend</h2>
          <div className="flex items-end gap-1 h-28 overflow-x-auto pb-2">
            {[...stats.daily_spend].reverse().map((d) => {
              const max = Math.max(...stats.daily_spend.map((x) => x.total));
              const heightPct = max > 0 ? (d.total / max) * 100 : 0;
              return (
                <div
                  key={d.date}
                  className="flex flex-col items-center gap-1 group min-w-[28px]"
                  title={`${d.date}: ₹${formatINR(d.total)}`}
                >
                  <div
                    className="w-5 bg-blue-500 rounded-t hover:bg-blue-600 transition-colors"
                    style={{ height: `${Math.max(heightPct, 4)}%` }}
                  />
                  <span className="text-[9px] text-gray-400 rotate-45 origin-left whitespace-nowrap">
                    {format(parseISO(d.date), "dd/MM")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
