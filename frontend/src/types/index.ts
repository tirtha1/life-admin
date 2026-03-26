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
  new: number;
  skipped: number;
  failed: number;
}

export interface AgentRunResult {
  bill_id: string;
  action: AgentAction;
  notes: string;
}
