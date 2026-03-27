import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { BillCard } from "@/components/bill-card";
import {
  AppScreen,
  EmptyState,
  ErrorBanner,
  FilterChip,
  InputField,
  ScreenHeader,
  SectionCard,
} from "@/components/ui";
import { formatApiError, useApi } from "@/lib/api";
import { useAppConfig } from "@/lib/config";
import { theme } from "@/lib/theme";
import type { BillStatus } from "@/lib/types";

const STATUS_TABS: { label: string; value: BillStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Extracted", value: "extracted" },
  { label: "Needs Review", value: "review_required" },
  { label: "Confirmed", value: "confirmed" },
  { label: "Reminded", value: "reminded" },
  { label: "Paid", value: "paid" },
];

export default function BillsScreen() {
  const api = useApi();
  const { apiConfigKey } = useAppConfig();
  const [statusFilter, setStatusFilter] = useState<BillStatus | "all">("all");
  const [search, setSearch] = useState("");

  const billsQuery = useQuery({
    queryKey: ["bills", "list", statusFilter, apiConfigKey],
    queryFn: () =>
      api.billsApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      }),
  });

  const query = search.trim().toLowerCase();
  const filteredBills = (billsQuery.data ?? []).filter((bill) => {
    if (!query) {
      return true;
    }
    return (
      bill.provider.toLowerCase().includes(query) ||
      bill.bill_type.toLowerCase().includes(query) ||
      bill.email_subject?.toLowerCase().includes(query)
    );
  });

  return (
    <AppScreen refreshing={billsQuery.isRefetching} onRefresh={() => billsQuery.refetch()}>
      <ScreenHeader
        eyebrow="Bills"
        title="Every bill in one place"
        description={`${billsQuery.data?.length ?? 0} bills synced from your current system, filterable by status and searchable by provider.`}
      />

      <InputField
        label="Search"
        placeholder="Search bills, bill types, or email subjects"
        value={search}
        onChangeText={setSearch}
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabRow}>
        {STATUS_TABS.map((tab) => (
          <FilterChip
            key={tab.value}
            label={tab.label}
            active={statusFilter === tab.value}
            onPress={() => setStatusFilter(tab.value)}
          />
        ))}
      </ScrollView>

      {billsQuery.error ? <ErrorBanner message={formatApiError(billsQuery.error)} /> : null}

      {billsQuery.isLoading ? (
        <SectionCard>
          <Text style={styles.helperText}>Loading bills…</Text>
        </SectionCard>
      ) : filteredBills.length > 0 ? (
        <View style={styles.listColumn}>
          {filteredBills.map((bill) => (
            <BillCard
              key={bill.id}
              bill={bill}
              onPress={() => router.push({ pathname: "/bills/[id]", params: { id: bill.id } })}
            />
          ))}
        </View>
      ) : (
        <EmptyState
          title="No bills found"
          description={
            statusFilter === "all"
              ? "Try syncing Gmail or changing your search."
              : "That status filter is empty right now."
          }
        />
      )}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  tabRow: {
    gap: 10,
    paddingRight: 18,
  },
  helperText: {
    color: theme.colors.mutedText,
    fontSize: 15,
  },
  listColumn: {
    gap: 12,
  },
});
