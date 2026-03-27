import { Ionicons } from "@expo/vector-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";

import { BillCard } from "@/components/bill-card";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  ErrorBanner,
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
import type { SyncResult } from "@/lib/types";

export default function DashboardScreen() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { apiConfigKey } = useAppConfig();
  const [syncPollUntil, setSyncPollUntil] = useState<number | null>(null);

  function getSyncRefetchInterval() {
    if (syncPollUntil && Date.now() < syncPollUntil) {
      return 5_000;
    }
    return 30_000;
  }

  const statsQuery = useQuery({
    queryKey: ["bills", "stats", apiConfigKey],
    queryFn: api.billsApi.stats,
    refetchInterval: getSyncRefetchInterval,
  });

  const urgentBillsQuery = useQuery({
    queryKey: ["bills", "extracted", apiConfigKey],
    queryFn: () => api.billsApi.list({ status: "extracted", limit: 5 }),
    refetchInterval: getSyncRefetchInterval,
  });

  const reviewBillsQuery = useQuery({
    queryKey: ["bills", "review_required", apiConfigKey],
    queryFn: () => api.billsApi.list({ status: "review_required", limit: 5 }),
    refetchInterval: getSyncRefetchInterval,
  });

  const syncMutation = useMutation({
    mutationFn: api.ingestionApi.sync,
    onSuccess: (_result: SyncResult) => {
      setSyncPollUntil(Date.now() + 60_000);
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const agentMutation = useMutation({
    mutationFn: api.billsApi.runAllPending,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const isRefreshing =
    statsQuery.isRefetching || urgentBillsQuery.isRefetching || reviewBillsQuery.isRefetching;

  const stats = statsQuery.data;
  const urgentBills = urgentBillsQuery.data ?? [];
  const reviewBills = reviewBillsQuery.data ?? [];
  const hasError = statsQuery.error || urgentBillsQuery.error || reviewBillsQuery.error;

  async function handleRefresh() {
    await Promise.all([
      statsQuery.refetch(),
      urgentBillsQuery.refetch(),
      reviewBillsQuery.refetch(),
    ]);
  }

  return (
    <AppScreen refreshing={isRefreshing} onRefresh={handleRefresh}>
      <ScreenHeader
        eyebrow="Life Admin AI"
        title="Dashboard"
        description="Your mobile command center for bills, Gmail sync, agent actions, and what needs attention right now."
        actions={
          <>
            <ActionButton
              label={agentMutation.isPending ? "Running…" : "Run Agent"}
              icon={<Ionicons name="sparkles-outline" size={18} color="#ffffff" />}
              onPress={() => agentMutation.mutate()}
              loading={agentMutation.isPending}
            />
            <ActionButton
              label={syncMutation.isPending ? "Syncing…" : "Sync Gmail"}
              tone="secondary"
              icon={<Ionicons name="refresh-outline" size={18} color={theme.colors.text} />}
              onPress={() => syncMutation.mutate()}
              loading={syncMutation.isPending}
            />
          </>
        }
      />

      {syncMutation.isSuccess && syncMutation.data ? (
        <InfoBanner
          tone="success"
          message={`${syncMutation.data.message}. New bills will keep appearing while the ingestion worker finishes.`}
        />
      ) : null}

      {agentMutation.isSuccess && agentMutation.data ? (
        <InfoBanner
          message={`Agent reviewed ${agentMutation.data.length} pending bills and refreshed the queue.`}
        />
      ) : null}

      {syncMutation.error ? <ErrorBanner message={formatApiError(syncMutation.error)} /> : null}
      {agentMutation.error ? <ErrorBanner message={formatApiError(agentMutation.error)} /> : null}
      {hasError ? <ErrorBanner message={formatApiError(hasError)} /> : null}

      {stats ? (
        <View style={[sharedStyles.wrap, styles.metricGrid]}>
          <MetricCard
            label="Total Due"
            value={formatInr(stats.total_due_amount)}
            subtext={`${stats.total} bills in the system`}
            accent="primary"
          />
          <MetricCard
            label="Overdue"
            value={`${stats.overdue}`}
            subtext="Needs immediate attention"
            accent="warning"
          />
          <MetricCard
            label="Paid"
            value={`${stats.paid}`}
            subtext="Marked done recently"
            accent="success"
          />
          <MetricCard
            label="Needs Review"
            value={`${stats.needs_review}`}
            subtext="Flagged for manual follow-up"
            accent="accent"
          />
        </View>
      ) : (
        <SectionCard>
          <Text style={styles.loadingText}>Loading bill stats…</Text>
        </SectionCard>
      )}

      {urgentBills.length > 0 ? (
        <SectionCard>
          <SectionTitle title="Recent Bills" subtitle={`${urgentBills.length} shown`} />
          <View style={styles.listColumn}>
            {urgentBills.map((bill) => (
              <BillCard
                key={bill.id}
                bill={bill}
                onPress={() => router.push({ pathname: "/bills/[id]", params: { id: bill.id } })}
              />
            ))}
          </View>
        </SectionCard>
      ) : null}

      {reviewBills.length > 0 ? (
        <SectionCard>
          <SectionTitle title="Needs Review" subtitle={`${reviewBills.length} flagged`} />
          <View style={styles.listColumn}>
            {reviewBills.map((bill) => (
              <BillCard
                key={bill.id}
                bill={bill}
                onPress={() => router.push({ pathname: "/bills/[id]", params: { id: bill.id } })}
              />
            ))}
          </View>
        </SectionCard>
      ) : null}

      {urgentBills.length === 0 && reviewBills.length === 0 && stats && !statsQuery.isLoading ? (
        <EmptyState
          title="All clear"
          description="No extracted or review-required bills are waiting. Pull to refresh or sync Gmail to look for new items."
        />
      ) : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  metricGrid: {
    gap: 12,
  },
  listColumn: {
    gap: 12,
  },
  loadingText: {
    color: theme.colors.mutedText,
    fontSize: 15,
  },
});
