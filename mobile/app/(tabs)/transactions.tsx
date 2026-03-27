import { Ionicons } from "@expo/vector-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useState } from "react";

import {
  ActionButton,
  AppScreen,
  EmptyState,
  ErrorBanner,
  FilterChip,
  InfoBanner,
  MetricCard,
  ScreenHeader,
  SectionCard,
  SectionTitle,
  sharedStyles,
} from "@/components/ui";
import { formatApiError, useApi } from "@/lib/api";
import { formatInr } from "@/lib/format";
import { useAppConfig } from "@/lib/config";
import { theme } from "@/lib/theme";
import type { Transaction, TransactionCategory } from "@/lib/types";

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

const categoryColors: Record<string, string> = {
  food: "#ef7a3b",
  transport: "#2563eb",
  shopping: "#7c3aed",
  entertainment: "#db2777",
  utilities: "#c97b16",
  healthcare: "#d14343",
  education: "#4f46e5",
  travel: "#0f766e",
  subscriptions: "#64748b",
  other: "#6b7280",
};

const dayOptions = [
  { label: "7D", value: 7 },
  { label: "30D", value: 30 },
  { label: "90D", value: 90 },
];

const filterCategories: (TransactionCategory | "all")[] = [
  "all",
  "food",
  "transport",
  "shopping",
  "entertainment",
  "utilities",
  "subscriptions",
  "other",
];

function TransactionRow({
  transaction,
  onDelete,
}: {
  transaction: Transaction;
  onDelete: (id: number) => void;
}) {
  const isDebit = transaction.type === "debit";

  return (
    <View style={styles.transactionRow}>
      <Text style={styles.transactionEmoji}>{categoryEmoji[transaction.category] || "💸"}</Text>
      <View style={styles.transactionBody}>
        <Text style={styles.transactionMerchant}>
          {transaction.merchant || "Unknown merchant"}
        </Text>
        <Text style={styles.transactionMeta}>
          {format(parseISO(transaction.date), "dd MMM yyyy")}
          {transaction.source ? ` • ${transaction.source}` : ""}
        </Text>
      </View>
      <View style={styles.transactionAmountColumn}>
        <Text style={[styles.transactionAmount, isDebit ? styles.debitText : styles.creditText]}>
          {isDebit ? "-" : "+"}
          {formatInr(transaction.amount)}
        </Text>
        <Text style={styles.transactionCategory}>{transaction.category}</Text>
      </View>
      <Pressable onPress={() => onDelete(transaction.id)} style={styles.deleteButton}>
        <Ionicons name="trash-outline" size={18} color={theme.colors.danger} />
      </Pressable>
    </View>
  );
}

export default function TransactionsScreen() {
  const api = useApi();
  const { apiConfigKey } = useAppConfig();
  const queryClient = useQueryClient();
  const [days, setDays] = useState(30);
  const [showInsights, setShowInsights] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

  const statsQuery = useQuery({
    queryKey: ["transactions", "stats", days, apiConfigKey],
    queryFn: () => api.transactionsApi.stats(days),
    refetchInterval: 60_000,
  });

  const transactionsQuery = useQuery({
    queryKey: ["transactions", "list", days, categoryFilter, apiConfigKey],
    queryFn: () =>
      api.transactionsApi.list({
        limit: 100,
        ...(categoryFilter !== "all" ? { category: categoryFilter } : {}),
        date_from: new Date(Date.now() - days * 86400000).toISOString().slice(0, 10),
      }),
    refetchInterval: 60_000,
  });

  const insightsQuery = useQuery({
    queryKey: ["transactions", "insights", days, apiConfigKey],
    queryFn: () => api.transactionsApi.insights(days),
    enabled: showInsights,
    staleTime: 300_000,
  });

  const syncMutation = useMutation({
    mutationFn: api.transactionsApi.sync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.transactionsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });

  const transactions = transactionsQuery.data ?? [];
  const debits = transactions.filter((item) => item.type === "debit");
  const credits = transactions.filter((item) => item.type === "credit");

  async function handleRefresh() {
    await Promise.all([
      statsQuery.refetch(),
      transactionsQuery.refetch(),
      showInsights ? insightsQuery.refetch() : Promise.resolve(),
    ]);
  }

  function handleDelete(id: number) {
    Alert.alert("Delete transaction?", "This removes the transaction from the tracker.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => deleteMutation.mutate(id) },
    ]);
  }

  return (
    <AppScreen
      refreshing={statsQuery.isRefetching || transactionsQuery.isRefetching}
      onRefresh={handleRefresh}
    >
      <ScreenHeader
        eyebrow="Spending"
        title="Spending Tracker"
        description="UPI, bank debit, and credit activity synced from Gmail, plus AI insights about where the money is going."
        actions={
          <>
            <ActionButton
              label={showInsights ? "Hide AI" : "AI Insights"}
              tone="secondary"
              icon={<Ionicons name="sparkles-outline" size={18} color={theme.colors.text} />}
              onPress={() => setShowInsights((value) => !value)}
            />
            <ActionButton
              label={syncMutation.isPending ? "Syncing…" : "Sync Gmail"}
              icon={<Ionicons name="refresh-outline" size={18} color="#ffffff" />}
              onPress={() => syncMutation.mutate()}
              loading={syncMutation.isPending}
            />
          </>
        }
      />

      {syncMutation.isSuccess && syncMutation.data ? (
        <InfoBanner
          tone="success"
          message={`Scanned ${syncMutation.data.emails_scanned} emails and added ${syncMutation.data.transactions_new} new transactions.`}
        />
      ) : null}

      {syncMutation.error ? <ErrorBanner message={formatApiError(syncMutation.error)} /> : null}
      {deleteMutation.error ? <ErrorBanner message={formatApiError(deleteMutation.error)} /> : null}
      {statsQuery.error ? <ErrorBanner message={formatApiError(statsQuery.error)} /> : null}
      {transactionsQuery.error ? <ErrorBanner message={formatApiError(transactionsQuery.error)} /> : null}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.controlRow}>
        {dayOptions.map((option) => (
          <FilterChip
            key={option.value}
            label={option.label}
            active={days === option.value}
            onPress={() => setDays(option.value)}
          />
        ))}
      </ScrollView>

      {statsQuery.data ? (
        <View style={[sharedStyles.wrap, styles.metricGrid]}>
          <MetricCard
            label="This Month"
            value={formatInr(statsQuery.data.total_this_month)}
            accent="primary"
          />
          <MetricCard
            label="Today"
            value={formatInr(statsQuery.data.total_today)}
            accent="accent"
          />
          <MetricCard
            label="This Week"
            value={formatInr(statsQuery.data.total_this_week)}
            accent="warning"
          />
          <MetricCard
            label="Transactions"
            value={`${statsQuery.data.transaction_count}`}
            subtext={statsQuery.data.top_merchant ? `Top: ${statsQuery.data.top_merchant}` : undefined}
            accent="success"
          />
        </View>
      ) : (
        <SectionCard>
          <Text style={styles.helperText}>Loading spending stats…</Text>
        </SectionCard>
      )}

      {showInsights ? (
        <SectionCard style={styles.insightCard}>
          <SectionTitle
            title="AI Spending Insights"
            subtitle={insightsQuery.data?.generated_at ? "Fresh analysis" : undefined}
          />
          {insightsQuery.isLoading ? (
            <Text style={styles.helperText}>Analyzing your recent spend…</Text>
          ) : insightsQuery.error ? (
            <ErrorBanner message={formatApiError(insightsQuery.error)} />
          ) : insightsQuery.data?.insights.length ? (
            <View style={styles.listColumn}>
              {insightsQuery.data.insights.map((insight) => (
                <View key={insight} style={styles.bulletRow}>
                  <Text style={styles.bulletDot}>•</Text>
                  <Text style={styles.bulletText}>{insight}</Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.helperText}>No AI insights yet for this period.</Text>
          )}
        </SectionCard>
      ) : null}

      <SectionCard>
        <SectionTitle title="By Category" subtitle={`${statsQuery.data?.category_breakdown.length ?? 0} groups`} />
        {statsQuery.data?.category_breakdown.length ? (
          <View style={styles.listColumn}>
            {statsQuery.data.category_breakdown.map((category) => (
              <View key={category.category} style={styles.categoryRow}>
                <View style={styles.categoryHeader}>
                  <Text style={styles.categoryLabel}>
                    {categoryEmoji[category.category] || "💸"} {category.category}
                  </Text>
                  <Text style={styles.categoryTotal}>{formatInr(category.total)}</Text>
                </View>
                <View style={styles.categoryBarTrack}>
                  <View
                    style={[
                      styles.categoryBarFill,
                      {
                        width: `${Math.max(category.percentage, 4)}%`,
                        backgroundColor: categoryColors[category.category] || theme.colors.primary,
                      },
                    ]}
                  />
                </View>
                <Text style={styles.categoryMeta}>
                  {category.count} transactions • {Math.round(category.percentage)}%
                </Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.helperText}>No categorized spend yet.</Text>
        )}
      </SectionCard>

      <SectionCard>
        <SectionTitle title="Transactions" subtitle={`${transactions.length} rows`} />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.controlRow}>
          {filterCategories.map((category) => (
            <FilterChip
              key={category}
              label={category === "all" ? "All" : `${categoryEmoji[category]} ${category}`}
              active={categoryFilter === category}
              onPress={() => setCategoryFilter(category)}
            />
          ))}
        </ScrollView>

        {transactionsQuery.isLoading ? (
          <Text style={styles.helperText}>Loading transactions…</Text>
        ) : transactions.length ? (
          <>
            <View style={styles.listColumn}>
              {transactions.map((transaction) => (
                <TransactionRow
                  key={transaction.id}
                  transaction={transaction}
                  onDelete={handleDelete}
                />
              ))}
            </View>
            <View style={styles.summaryRow}>
              <Text style={[styles.summaryText, styles.debitText]}>
                {debits.length} debits
              </Text>
              <Text style={[styles.summaryText, styles.creditText]}>
                {credits.length} credits
              </Text>
            </View>
          </>
        ) : (
          <EmptyState
            title="No transactions yet"
            description="Sync Gmail to fetch your bank and UPI alerts into the tracker."
          />
        )}
      </SectionCard>

      {statsQuery.data?.daily_spend.length ? (
        <SectionCard>
          <SectionTitle title="Daily Spend" subtitle="Recent activity" />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.dailyRow}>
            {[...statsQuery.data.daily_spend].reverse().map((day) => {
              const max = Math.max(...statsQuery.data!.daily_spend.map((item) => item.total));
              const height = max > 0 ? Math.max((day.total / max) * 120, 8) : 8;
              return (
                <View key={day.date} style={styles.dayColumn}>
                  <Text style={styles.dayValue}>{formatInr(day.total, false)}</Text>
                  <View style={styles.dayTrack}>
                    <View style={[styles.dayBar, { height }]} />
                  </View>
                  <Text style={styles.dayLabel}>{format(parseISO(day.date), "dd/MM")}</Text>
                </View>
              );
            })}
          </ScrollView>
        </SectionCard>
      ) : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  controlRow: {
    gap: 10,
    paddingRight: 18,
  },
  metricGrid: {
    gap: 12,
  },
  helperText: {
    color: theme.colors.mutedText,
    fontSize: 15,
  },
  insightCard: {
    backgroundColor: "#f6f0ff",
    borderColor: "#decffb",
  },
  listColumn: {
    gap: 12,
  },
  bulletRow: {
    flexDirection: "row",
    gap: 10,
  },
  bulletDot: {
    color: theme.colors.accent,
    fontSize: 18,
    lineHeight: 20,
  },
  bulletText: {
    flex: 1,
    color: theme.colors.text,
    fontSize: 14,
    lineHeight: 21,
  },
  categoryRow: {
    gap: 8,
  },
  categoryHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  categoryLabel: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  categoryTotal: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  categoryBarTrack: {
    height: 12,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.colors.surfaceMuted,
    overflow: "hidden",
  },
  categoryBarFill: {
    height: "100%",
    borderRadius: theme.radius.pill,
  },
  categoryMeta: {
    color: theme.colors.subtleText,
    fontSize: 12,
  },
  transactionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.divider,
  },
  transactionEmoji: {
    fontSize: 26,
  },
  transactionBody: {
    flex: 1,
    gap: 4,
  },
  transactionMerchant: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  transactionMeta: {
    color: theme.colors.subtleText,
    fontSize: 12,
  },
  transactionAmountColumn: {
    alignItems: "flex-end",
    gap: 4,
  },
  transactionAmount: {
    fontSize: 14,
    fontWeight: "800",
  },
  transactionCategory: {
    color: theme.colors.subtleText,
    fontSize: 12,
    textTransform: "capitalize",
  },
  deleteButton: {
    padding: 6,
  },
  debitText: {
    color: theme.colors.danger,
  },
  creditText: {
    color: theme.colors.success,
  },
  summaryRow: {
    flexDirection: "row",
    gap: 20,
    borderTopWidth: 1,
    borderTopColor: theme.colors.divider,
    paddingTop: 12,
  },
  summaryText: {
    fontSize: 13,
    fontWeight: "700",
  },
  dailyRow: {
    gap: 12,
    alignItems: "flex-end",
    paddingRight: 18,
  },
  dayColumn: {
    alignItems: "center",
    width: 52,
    gap: 8,
  },
  dayValue: {
    color: theme.colors.subtleText,
    fontSize: 10,
  },
  dayTrack: {
    width: 26,
    height: 124,
    justifyContent: "flex-end",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
    padding: 2,
  },
  dayBar: {
    width: "100%",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.primary,
  },
  dayLabel: {
    color: theme.colors.subtleText,
    fontSize: 11,
  },
});
