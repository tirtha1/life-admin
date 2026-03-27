import { Ionicons } from "@expo/vector-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { BillStatusBadge } from "@/components/bill-card";
import {
  ActionButton,
  AppScreen,
  ErrorBanner,
  InfoBanner,
  ScreenHeader,
  SectionCard,
} from "@/components/ui";
import { formatApiError, useApi } from "@/lib/api";
import { formatMonthDate, formatMoney } from "@/lib/format";
import { useAppConfig } from "@/lib/config";
import { theme } from "@/lib/theme";

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

export default function BillDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const api = useApi();
  const { apiConfigKey } = useAppConfig();
  const queryClient = useQueryClient();

  const billQuery = useQuery({
    queryKey: ["bills", "detail", id, apiConfigKey],
    queryFn: () => api.billsApi.get(id!),
    enabled: Boolean(id),
  });

  const markPaidMutation = useMutation({
    mutationFn: () => api.billsApi.markPaid(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const runAgentMutation = useMutation({
    mutationFn: () => api.billsApi.runAgent(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bills"] });
    },
  });

  const bill = billQuery.data;

  return (
    <AppScreen refreshing={billQuery.isRefetching} onRefresh={() => billQuery.refetch()}>
      <ActionButton
        label="Back to Bills"
        tone="secondary"
        icon={<Ionicons name="arrow-back-outline" size={18} color={theme.colors.text} />}
        onPress={() => router.back()}
      />

      {bill ? (
        <>
          <ScreenHeader
            eyebrow="Bill Detail"
            title={bill.provider}
            description={`Review the extracted bill data, mark it paid, or re-run the agent on this single item.`}
          />

          <SectionCard>
            <View style={styles.headerRow}>
              <View style={styles.headerMeta}>
                <Text style={styles.billType}>{bill.bill_type.replace(/_/g, " ")}</Text>
                <Text style={styles.amount}>
                  {bill.amount != null ? formatMoney(bill.amount, bill.currency) : "Amount unknown"}
                </Text>
                <Text style={styles.dueDate}>
                  {bill.due_date ? `Due ${formatMonthDate(bill.due_date)}` : "No due date"}
                </Text>
              </View>
              <BillStatusBadge status={bill.status} />
            </View>

            {bill.needs_review ? (
              <InfoBanner message="This bill is flagged for manual review before you trust automation." tone="warning" />
            ) : null}

            <View style={styles.actionRow}>
              {bill.status !== "paid" ? (
                <ActionButton
                  label={markPaidMutation.isPending ? "Marking…" : "Mark as Paid"}
                  tone="success"
                  icon={<Ionicons name="checkmark-circle-outline" size={18} color="#ffffff" />}
                  onPress={() => markPaidMutation.mutate()}
                  loading={markPaidMutation.isPending}
                />
              ) : null}
              <ActionButton
                label={runAgentMutation.isPending ? "Running…" : "Re-run Agent"}
                icon={<Ionicons name="sparkles-outline" size={18} color="#ffffff" />}
                onPress={() => runAgentMutation.mutate()}
                loading={runAgentMutation.isPending}
              />
            </View>

            {runAgentMutation.isSuccess && runAgentMutation.data ? (
              <InfoBanner
                message={`Agent result: ${runAgentMutation.data.action} — ${runAgentMutation.data.notes}`}
              />
            ) : null}
          </SectionCard>

          <SectionCard>
            <Text style={styles.sectionTitle}>Bill Details</Text>
            <DetailRow
              label="Extraction confidence"
              value={
                bill.extraction_confidence != null
                  ? `${Math.round(bill.extraction_confidence * 100)}%`
                  : "Unknown"
              }
            />
            <DetailRow label="Recurring" value={bill.is_recurring ? "Yes" : "No"} />
            <DetailRow label="Overdue" value={bill.is_overdue ? "Yes" : "No"} />
            <DetailRow label="Currency" value={bill.currency} />
          </SectionCard>

          {bill.email_subject ? (
            <SectionCard>
              <Text style={styles.sectionTitle}>Email Source</Text>
              <DetailRow label="Subject" value={bill.email_subject} />
            </SectionCard>
          ) : null}
        </>
      ) : billQuery.isLoading ? (
        <SectionCard>
          <Text style={styles.bodyText}>Loading bill…</Text>
        </SectionCard>
      ) : (
        <SectionCard>
          <Text style={styles.bodyText}>Bill not found.</Text>
        </SectionCard>
      )}

      {billQuery.error ? <ErrorBanner message={formatApiError(billQuery.error)} /> : null}
      {markPaidMutation.error ? <ErrorBanner message={formatApiError(markPaidMutation.error)} /> : null}
      {runAgentMutation.error ? <ErrorBanner message={formatApiError(runAgentMutation.error)} /> : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 12,
  },
  headerMeta: {
    flex: 1,
    gap: 6,
  },
  billType: {
    color: theme.colors.accent,
    fontSize: 13,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  amount: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: "800",
  },
  dueDate: {
    color: theme.colors.mutedText,
    fontSize: 14,
  },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "700",
  },
  detailRow: {
    gap: 6,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.divider,
  },
  detailLabel: {
    color: theme.colors.subtleText,
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  detailValue: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "600",
  },
  bodyText: {
    color: theme.colors.mutedText,
    fontSize: 14,
  },
});
