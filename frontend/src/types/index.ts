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
