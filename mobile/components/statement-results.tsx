import { StyleSheet, Text, View } from "react-native";

import {
  MetricCard,
  SectionCard,
  SectionTitle,
  sharedStyles,
} from "@/components/ui";
import { formatInr, formatLongDate, formatShortDate } from "@/lib/format";
import { theme } from "@/lib/theme";
import type {
  InsightSeverity,
  StatementAction,
  StatementAnalysisResponse,
  StatementLeakInsight,
} from "@/lib/types";

const categoryEmoji: Record<string, string> = {
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

const severityStyles: Record<
  InsightSeverity,
  { backgroundColor: string; textColor: string; borderColor: string }
> = {
  low: {
    backgroundColor: theme.colors.successSoft,
    textColor: theme.colors.success,
    borderColor: "#c4ecdf",
  },
  medium: {
    backgroundColor: theme.colors.warningSoft,
    textColor: "#9b5a0a",
    borderColor: "#ffd9b5",
  },
  high: {
    backgroundColor: theme.colors.dangerSoft,
    textColor: theme.colors.danger,
    borderColor: "#f0b2b6",
  },
};

function SeverityBadge({ severity }: { severity: InsightSeverity }) {
  const config = severityStyles[severity];
  return (
    <View
      style={[
        styles.severityBadge,
        { backgroundColor: config.backgroundColor, borderColor: config.borderColor },
      ]}
    >
      <Text style={[styles.severityText, { color: config.textColor }]}>{severity}</Text>
    </View>
  );
}

function ActionCard({ action }: { action: StatementAction }) {
  return (
    <View style={styles.actionCard}>
      <View style={styles.spaceBetween}>
        <View style={styles.flexOne}>
          <Text style={styles.cardTitle}>{action.title}</Text>
          <Text style={styles.cardBody}>{action.description}</Text>
        </View>
        <SeverityBadge severity={action.priority} />
      </View>
      <View style={styles.actionMetaRow}>
        <Text style={styles.metaLabel}>{action.action_type.replace(/_/g, " ")}</Text>
        <Text style={styles.savingsValue}>Save up to {formatInr(action.estimated_monthly_savings)}</Text>
      </View>
    </View>
  );
}

function LeakCard({ insight }: { insight: StatementLeakInsight }) {
  return (
    <View style={styles.actionCard}>
      <View style={styles.spaceBetween}>
        <View style={styles.flexOne}>
          <Text style={styles.cardTitle}>{insight.title}</Text>
          <Text style={styles.cardBody}>{insight.rationale}</Text>
        </View>
        <SeverityBadge severity={insight.severity} />
      </View>
      <View style={styles.actionMetaRow}>
        <Text style={styles.metaLabel}>
          {insight.category
            ? `${categoryEmoji[insight.category]} ${insight.category}`
            : insight.merchant || "Spend signal"}
        </Text>
        <Text style={styles.amountValue}>{formatInr(insight.amount)}</Text>
      </View>
      <Text style={styles.tipBox}>{insight.suggested_action}</Text>
    </View>
  );
}

export function StatementResults({ result }: { result: StatementAnalysisResponse }) {
  const previewTransactions = result.transactions.slice(0, 18);

  return (
    <View style={styles.container}>
      <View style={[sharedStyles.wrap, styles.metricGrid]}>
        <MetricCard
          label="Total Spend"
          value={formatInr(result.summary.total_spent)}
          subtext={`${result.summary.transaction_count} transactions from ${formatShortDate(result.summary.period_start)} to ${formatShortDate(result.summary.period_end)}`}
          accent="primary"
        />
        <MetricCard
          label="Potential Savings"
          value={formatInr(result.summary.potential_monthly_savings)}
          subtext="Estimated monthly upside from suggested actions"
          accent="success"
        />
        <MetricCard
          label="Recurring Spend"
          value={formatInr(result.summary.recurring_spend)}
          subtext={`${result.recurring_payments.length} recurring charges detected`}
          accent="warning"
        />
        <MetricCard
          label="Top Category"
          value={
            result.summary.top_category
              ? `${categoryEmoji[result.summary.top_category]} ${result.summary.top_category}`
              : "No signal"
          }
          subtext={`Parser: ${result.parser_used}${result.llm_enhanced ? " • AI summary on" : ""}`}
          accent="accent"
        />
      </View>

      <SectionCard>
        <SectionTitle title="AI Summary" subtitle={result.file_name} />
        <Text style={styles.summaryText}>{result.assistant_summary}</Text>
        {result.warnings.length ? (
          <View style={styles.warningColumn}>
            {result.warnings.map((warning) => (
              <View key={warning} style={styles.warningBox}>
                <Text style={styles.warningText}>{warning}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </SectionCard>

      <SectionCard>
        <SectionTitle
          title="Suggested Actions"
          subtitle={`${result.suggested_actions.length} recommendations`}
        />
        {result.suggested_actions.length ? (
          <View style={styles.stack}>
            {result.suggested_actions.map((action) => (
              <ActionCard
                key={`${action.title}-${action.merchant ?? action.category ?? "none"}`}
                action={action}
              />
            ))}
          </View>
        ) : (
          <Text style={styles.emptyText}>No actions suggested from this file.</Text>
        )}
      </SectionCard>

      <SectionCard>
        <SectionTitle title="Leak Signals" subtitle={`${result.leak_insights.length} flagged`} />
        {result.leak_insights.length ? (
          <View style={styles.stack}>
            {result.leak_insights.map((insight) => (
              <LeakCard
                key={`${insight.title}-${insight.merchant ?? insight.category ?? "none"}`}
                insight={insight}
              />
            ))}
          </View>
        ) : (
          <Text style={styles.emptyText}>No leak signals were confidently detected.</Text>
        )}
      </SectionCard>

      <SectionCard>
        <SectionTitle
          title="Recurring Payments"
          subtitle={`${result.recurring_payments.length} found`}
        />
        {result.recurring_payments.length ? (
          <View style={styles.stack}>
            {result.recurring_payments.map((item) => (
              <View key={`${item.merchant}-${item.last_seen}`} style={styles.recurringCard}>
                <View style={styles.spaceBetween}>
                  <View style={styles.flexOne}>
                    <Text style={styles.cardTitle}>{item.merchant}</Text>
                    <Text style={styles.cardBody}>
                      {categoryEmoji[item.category]} {item.category} • {item.cadence}
                    </Text>
                  </View>
                  <View style={styles.alignEnd}>
                    <Text style={styles.amountValue}>{formatInr(item.monthly_estimate)}</Text>
                    <Text style={styles.metaLabel}>{Math.round(item.confidence * 100)}% confidence</Text>
                  </View>
                </View>
                <Text style={styles.cardBody}>{item.reason}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.emptyText}>No recurring payments were confidently detected.</Text>
        )}
      </SectionCard>

      <SectionCard>
        <SectionTitle
          title="Extracted Transactions"
          subtitle={`Previewing ${previewTransactions.length} rows`}
        />
        <Text style={styles.cashflowText}>
          Net cashflow {result.summary.net_cashflow >= 0 ? "+" : "-"}
          {formatInr(Math.abs(result.summary.net_cashflow))}
        </Text>
        {previewTransactions.length ? (
          <View style={styles.stack}>
            {previewTransactions.map((transaction) => (
              <View
                key={`${transaction.date}-${transaction.description}-${transaction.signed_amount}`}
                style={styles.transactionRow}
              >
                <View style={styles.flexOne}>
                  <Text style={styles.transactionTitle}>
                    {transaction.merchant || transaction.description}
                  </Text>
                  <Text style={styles.transactionMeta}>
                    {formatLongDate(transaction.date)} • {categoryEmoji[transaction.category]} {transaction.category}
                  </Text>
                  <Text style={styles.transactionDescription}>{transaction.description}</Text>
                </View>
                <Text
                  style={[
                    styles.transactionAmount,
                    transaction.type === "debit" ? styles.debitText : styles.creditText,
                  ]}
                >
                  {transaction.type === "debit" ? "-" : "+"}
                  {formatInr(transaction.amount)}
                </Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.emptyText}>No parsed transactions to preview.</Text>
        )}
      </SectionCard>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 18,
  },
  metricGrid: {
    gap: 12,
  },
  severityBadge: {
    borderWidth: 1,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignSelf: "flex-start",
  },
  severityText: {
    fontSize: 12,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  actionCard: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: 14,
    gap: 12,
    backgroundColor: theme.colors.surface,
  },
  recurringCard: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: 14,
    gap: 10,
    backgroundColor: theme.colors.surfaceMuted,
  },
  spaceBetween: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 12,
  },
  flexOne: {
    flex: 1,
    gap: 6,
  },
  alignEnd: {
    alignItems: "flex-end",
    gap: 4,
  },
  cardTitle: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  cardBody: {
    color: theme.colors.mutedText,
    fontSize: 14,
    lineHeight: 20,
  },
  actionMetaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
  },
  metaLabel: {
    color: theme.colors.subtleText,
    fontSize: 12,
    textTransform: "capitalize",
  },
  savingsValue: {
    color: theme.colors.success,
    fontSize: 13,
    fontWeight: "700",
  },
  amountValue: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "700",
  },
  tipBox: {
    backgroundColor: theme.colors.surfaceMuted,
    color: theme.colors.text,
    fontSize: 13,
    lineHeight: 19,
    borderRadius: theme.radius.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  summaryText: {
    color: theme.colors.text,
    fontSize: 15,
    lineHeight: 24,
  },
  warningColumn: {
    gap: 10,
  },
  warningBox: {
    borderWidth: 1,
    borderColor: "#ffd9b5",
    backgroundColor: theme.colors.warningSoft,
    borderRadius: theme.radius.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  warningText: {
    color: "#9b5a0a",
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
  },
  stack: {
    gap: 12,
  },
  emptyText: {
    color: theme.colors.mutedText,
    fontSize: 14,
  },
  cashflowText: {
    color: theme.colors.mutedText,
    fontSize: 13,
  },
  transactionRow: {
    flexDirection: "row",
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.divider,
    paddingBottom: 12,
  },
  transactionTitle: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  transactionMeta: {
    color: theme.colors.subtleText,
    fontSize: 12,
  },
  transactionDescription: {
    color: theme.colors.mutedText,
    fontSize: 12,
  },
  transactionAmount: {
    fontSize: 14,
    fontWeight: "800",
  },
  debitText: {
    color: theme.colors.danger,
  },
  creditText: {
    color: theme.colors.success,
  },
});
