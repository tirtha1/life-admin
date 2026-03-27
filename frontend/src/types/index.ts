export type BillStatus =
  | "detected"
  | "extracted"
  | "review_required"
  | "confirmed"
  | "reminded"
  | "paid"
  | "cancelled"
  | "failed";

export type BillType =
  | "electricity"
  | "water"
  | "gas"
  | "internet"
  | "phone"
  | "credit_card"
  | "insurance"
  | "subscription"
  | "rent"
  | "other";

export type AgentAction =
  | "pay_now"
  | "remind"
  | "optimize"
  | "escalate"
  | "ignore";

export interface Bill {
  id: string;
  provider: string;
  bill_type: BillType;
  amount: number | null;
  currency: string;
  due_date: string | null;
  status: BillStatus;
  extraction_confidence: number | null;
  is_overdue: boolean;
  is_recurring: boolean;
  needs_review: boolean;
  email_subject?: string | null;
}

export interface BillStats {
  total: number;
  pending: number;
  overdue: number;
  paid: number;
  total_due_amount: number;
  needs_review: number;
}

export interface SyncResult {
  message: string;
  user_id: string;
}

export interface AgentRunResult {
  bill_id: string;
  action: AgentAction;
  notes: string;
}

// ─── Transactions ────────────────────────────────────────────────────────────

export type TransactionType = "debit" | "credit";

export type TransactionCategory =
  | "food"
  | "transport"
  | "shopping"
  | "entertainment"
  | "utilities"
  | "healthcare"
  | "education"
  | "travel"
  | "subscriptions"
  | "other";

export interface Transaction {
  id: number;
  email_id?: string | null;
  amount: number;
  type: TransactionType;
  merchant?: string | null;
  category: TransactionCategory;
  date: string;
  source?: string | null;
  extraction_confidence: number;
}

export interface DailySpend {
  date: string;
  total: number;
  count: number;
}

export interface CategoryBreakdown {
  category: string;
  total: number;
  count: number;
  percentage: number;
}

export interface SpendStats {
  total_this_month: number;
  total_today: number;
  total_this_week: number;
  transaction_count: number;
  daily_spend: DailySpend[];
  category_breakdown: CategoryBreakdown[];
  top_merchant?: string | null;
}

export interface InsightsResponse {
  insights: string[];
  generated_at: string;
}

export interface TransactionSyncResult {
  emails_scanned: number;
  transactions_found: number;
  transactions_new: number;
  transactions_skipped: number;
  errors: number;
}

export type InsightSeverity = "low" | "medium" | "high";

export type StatementActionType =
  | "cancel_subscription"
  | "set_budget"
  | "review_spike"
  | "monitor";

export interface StatementTransaction {
  date: string;
  description: string;
  amount: number;
  signed_amount: number;
  type: TransactionType;
  merchant?: string | null;
  category: TransactionCategory;
}

export interface StatementRecurringPayment {
  merchant: string;
  category: TransactionCategory;
  monthly_estimate: number;
  occurrences: number;
  cadence: string;
  confidence: number;
  last_seen: string;
  reason: string;
}

export interface StatementLeakInsight {
  title: string;
  severity: InsightSeverity;
  amount: number;
  merchant?: string | null;
  category?: TransactionCategory | null;
  rationale: string;
  suggested_action: string;
}

export interface StatementAction {
  title: string;
  priority: InsightSeverity;
  action_type: StatementActionType;
  description: string;
  estimated_monthly_savings: number;
  merchant?: string | null;
  category?: TransactionCategory | null;
}

export interface StatementSummary {
  period_start: string;
  period_end: string;
  transaction_count: number;
  total_spent: number;
  total_income: number;
  net_cashflow: number;
  recurring_spend: number;
  potential_monthly_savings: number;
  top_category?: TransactionCategory | null;
}

export interface StatementAnalysisResponse {
  file_name: string;
  file_type: "csv" | "pdf";
  parser_used: string;
  llm_enhanced: boolean;
  assistant_summary: string;
  warnings: string[];
  summary: StatementSummary;
  recurring_payments: StatementRecurringPayment[];
  leak_insights: StatementLeakInsight[];
  suggested_actions: StatementAction[];
  transactions: StatementTransaction[];
}
