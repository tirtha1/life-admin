import { useState, type ElementType, type FormEvent } from "react";
import axios from "axios";
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  BadgeIndianRupee,
  FileSpreadsheet,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  Wallet,
} from "lucide-react";
import { statementsApi } from "@/services/api";
import type {
  InsightSeverity,
  StatementAction,
  StatementAnalysisResponse,
  StatementLeakInsight,
  TransactionCategory,
} from "@/types";
import { format, parseISO } from "date-fns";

const CATEGORY_EMOJI: Record<TransactionCategory | string, string> = {
  food: "🍔",
  transport: "🚕",
  shopping: "🛍️",
  entertainment: "🎬",
  utilities: "💡",
  healthcare: "🏥",
  education: "📚",
  travel: "✈️",
  subscriptions: "🔁",
  other: "💸",
};

const SEVERITY_STYLES: Record<InsightSeverity, string> = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-rose-50 text-rose-700 border-rose-200",
};

function formatINR(amount: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(amount);
}

function StatCard({
  label,
  value,
  subtext,
  icon: Icon,
}: {
  label: string;
  value: string;
  subtext: string;
  icon: ElementType;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-400">{label}</p>
          <p className="text-3xl font-bold text-gray-900 mt-2">{value}</p>
          <p className="text-sm text-gray-500 mt-2">{subtext}</p>
        </div>
        <div className="rounded-2xl bg-gray-100 p-3 text-gray-700">
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}

function SeverityBadge({ value }: { value: InsightSeverity }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold capitalize ${SEVERITY_STYLES[value]}`}>
      {value}
    </span>
  );
}

function ActionCard({ action }: { action: StatementAction }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-gray-900">{action.title}</h3>
          <p className="text-sm text-gray-600 mt-2 leading-6">{action.description}</p>
        </div>
        <SeverityBadge value={action.priority} />
      </div>
      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-gray-500 capitalize">{action.action_type.replace(/_/g, " ")}</span>
        <span className="font-semibold text-emerald-700">
          Save up to INR {formatINR(action.estimated_monthly_savings)}
        </span>
      </div>
    </div>
  );
}

function LeakCard({ insight }: { insight: StatementLeakInsight }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-gray-900">{insight.title}</h3>
          <p className="text-sm text-gray-600 mt-2 leading-6">{insight.rationale}</p>
        </div>
        <SeverityBadge value={insight.severity} />
      </div>
      <div className="mt-4 flex items-center justify-between gap-3 text-sm">
        <span className="text-gray-500">
          {insight.category ? `${CATEGORY_EMOJI[insight.category]} ${insight.category}` : insight.merchant || "Spend signal"}
        </span>
        <span className="font-semibold text-gray-900">INR {formatINR(insight.amount)}</span>
      </div>
      <p className="mt-3 rounded-xl bg-gray-50 px-3 py-2 text-sm text-gray-700">
        {insight.suggested_action}
      </p>
    </div>
  );
}

export default function StatementAnalyzer() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const analysisMutation = useMutation({
    mutationFn: statementsApi.analyze,
  });

  const result = analysisMutation.data;
  const errorMessage = (() => {
    if (!analysisMutation.error) return null;
    if (axios.isAxiosError(analysisMutation.error)) {
      return String(analysisMutation.error.response?.data?.detail || analysisMutation.error.message);
    }
    return "Something went wrong while analyzing the statement.";
  })();

  const handleAnalyze = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedFile) return;
    analysisMutation.mutate(selectedFile);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <section className="rounded-[28px] border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-emerald-50 p-6 md:p-8 shadow-sm">
        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-white/80 px-4 py-2 text-sm font-medium text-amber-700 border border-amber-200">
              <Sparkles className="w-4 h-4" />
              Upload bank statement to detect waste and suggest next actions
            </div>
            <h1 className="mt-5 text-3xl md:text-4xl font-bold tracking-tight text-gray-900">
              Turn a raw statement into a practical money-saving plan.
            </h1>
            <p className="mt-4 text-base md:text-lg leading-7 text-gray-600 max-w-2xl">
              Drop in a CSV or PDF statement and the app will extract transactions, group spend patterns,
              flag leaks like subscriptions or delivery overspend, and turn them into actions you can actually take.
            </p>
            <div className="mt-6 flex flex-wrap gap-3 text-sm text-gray-700">
              <span className="rounded-full bg-white px-3 py-1.5 border border-gray-200">CSV + PDF upload</span>
              <span className="rounded-full bg-white px-3 py-1.5 border border-gray-200">Recurring charge detection</span>
              <span className="rounded-full bg-white px-3 py-1.5 border border-gray-200">Budget suggestions</span>
            </div>
          </div>

          <form onSubmit={handleAnalyze} className="rounded-[24px] border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="rounded-2xl bg-amber-100 p-3 text-amber-700">
                <Upload className="w-5 h-5" />
              </div>
              <div>
                <h2 className="font-semibold text-gray-900">Analyze a statement</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Works best with `date`, `description`, and `amount` or `debit` / `credit` columns.
                </p>
              </div>
            </div>

            <label className="mt-5 block rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-4 cursor-pointer hover:border-amber-300 hover:bg-amber-50/40 transition-colors">
              <input
                type="file"
                accept=".csv,.pdf"
                className="hidden"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
              />
              <div className="flex items-center gap-3">
                {selectedFile?.name.toLowerCase().endsWith(".pdf") ? (
                  <FileText className="w-5 h-5 text-amber-700" />
                ) : (
                  <FileSpreadsheet className="w-5 h-5 text-emerald-700" />
                )}
                <div>
                  <p className="font-medium text-gray-900">
                    {selectedFile ? selectedFile.name : "Choose a CSV or PDF file"}
                  </p>
                  <p className="text-sm text-gray-500 mt-1">
                    Demo-friendly flow: upload, parse, inspect leaks, and show recommended actions.
                  </p>
                </div>
              </div>
            </label>

            <button
              type="submit"
              disabled={!selectedFile || analysisMutation.isPending}
              className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-2xl bg-gray-900 px-4 py-3 text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-60 transition-colors"
            >
              {analysisMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              {analysisMutation.isPending ? "Analyzing statement..." : "Analyze statement"}
            </button>
          </form>
        </div>
      </section>

      {errorMessage && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </div>
      )}

      {result && (
        <AnalysisResults result={result} />
      )}
    </div>
  );
}

function AnalysisResults({ result }: { result: StatementAnalysisResponse }) {
  const previewTransactions = result.transactions.slice(0, 18);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Spend"
          value={`INR ${formatINR(result.summary.total_spent)}`}
          subtext={`${result.summary.transaction_count} transactions from ${format(parseISO(result.summary.period_start), "dd MMM")} to ${format(parseISO(result.summary.period_end), "dd MMM")}`}
          icon={Wallet}
        />
        <StatCard
          label="Potential Savings"
          value={`INR ${formatINR(result.summary.potential_monthly_savings)}`}
          subtext="Estimated monthly upside from the suggested actions"
          icon={BadgeIndianRupee}
        />
        <StatCard
          label="Recurring Spend"
          value={`INR ${formatINR(result.summary.recurring_spend)}`}
          subtext={`${result.recurring_payments.length} recurring charges detected`}
          icon={ArrowUpRight}
        />
        <StatCard
          label="Top Category"
          value={result.summary.top_category ? `${CATEGORY_EMOJI[result.summary.top_category]} ${result.summary.top_category}` : "No signal"}
          subtext={`Parser: ${result.parser_used}${result.llm_enhanced ? " • AI summary on" : ""}`}
          icon={Sparkles}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-6">
          <section className="rounded-[24px] border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-2 text-gray-900">
              <Sparkles className="w-5 h-5 text-amber-600" />
              <h2 className="font-semibold">AI summary</h2>
            </div>
            <p className="mt-4 text-base leading-7 text-gray-700">{result.assistant_summary}</p>
            {result.warnings.length > 0 && (
              <div className="mt-5 space-y-2">
                {result.warnings.map((warning) => (
                  <div key={warning} className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{warning}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Suggested actions</h2>
              <span className="text-sm text-gray-500">{result.suggested_actions.length} recommendations</span>
            </div>
            <div className="space-y-4">
              {result.suggested_actions.map((action) => (
                <ActionCard key={`${action.title}-${action.merchant ?? action.category ?? "none"}`} action={action} />
              ))}
            </div>
          </section>
        </div>

        <div className="space-y-6">
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Leak signals</h2>
              <span className="text-sm text-gray-500">{result.leak_insights.length} flagged</span>
            </div>
            <div className="space-y-4">
              {result.leak_insights.map((insight) => (
                <LeakCard key={`${insight.title}-${insight.merchant ?? insight.category ?? "none"}`} insight={insight} />
              ))}
            </div>
          </section>

          <section className="rounded-[24px] border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Recurring payments</h2>
              <span className="text-sm text-gray-500">{result.recurring_payments.length} found</span>
            </div>
            {result.recurring_payments.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500">No recurring payments were confidently detected from this file.</p>
            ) : (
              <div className="mt-4 space-y-3">
                {result.recurring_payments.map((item) => (
                  <div key={`${item.merchant}-${item.last_seen}`} className="rounded-2xl bg-gray-50 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-medium text-gray-900">{item.merchant}</p>
                        <p className="text-sm text-gray-500 mt-1">
                          {CATEGORY_EMOJI[item.category]} {item.category} • {item.cadence}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-gray-900">INR {formatINR(item.monthly_estimate)}</p>
                        <p className="text-xs text-gray-500 mt-1">{Math.round(item.confidence * 100)}% confidence</p>
                      </div>
                    </div>
                    <p className="mt-3 text-sm text-gray-600">{item.reason}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <section className="rounded-[24px] border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-gray-100 px-5 py-4 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-gray-900">Extracted transactions</h2>
            <p className="text-sm text-gray-500 mt-1">Previewing the first {previewTransactions.length} rows from {result.file_name}</p>
          </div>
          <span className="text-sm text-gray-500">
            Net cashflow: {result.summary.net_cashflow >= 0 ? "+" : "-"}INR {formatINR(Math.abs(result.summary.net_cashflow))}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-500">
              <tr>
                <th className="px-5 py-3 font-medium">Date</th>
                <th className="px-5 py-3 font-medium">Description</th>
                <th className="px-5 py-3 font-medium">Category</th>
                <th className="px-5 py-3 font-medium text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {previewTransactions.map((txn) => (
                <tr key={`${txn.date}-${txn.description}-${txn.signed_amount}`} className="hover:bg-gray-50">
                  <td className="px-5 py-3 text-gray-600">{format(parseISO(txn.date), "dd MMM yyyy")}</td>
                  <td className="px-5 py-3">
                    <p className="font-medium text-gray-900">{txn.merchant || txn.description}</p>
                    <p className="text-xs text-gray-500 mt-1 truncate">{txn.description}</p>
                  </td>
                  <td className="px-5 py-3 text-gray-600">
                    {CATEGORY_EMOJI[txn.category]} {txn.category}
                  </td>
                  <td className={`px-5 py-3 text-right font-semibold ${txn.type === "debit" ? "text-rose-600" : "text-emerald-600"}`}>
                    {txn.type === "debit" ? "-" : "+"}INR {formatINR(txn.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
