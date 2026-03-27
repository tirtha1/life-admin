import { Ionicons } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { formatMoney, getFriendlyDueDate } from "@/lib/format";
import { theme } from "@/lib/theme";
import type { Bill, BillStatus } from "@/lib/types";

const billTypeEmoji: Record<string, string> = {
  electricity: "⚡",
  water: "💧",
  gas: "🔥",
  internet: "🌐",
  phone: "📱",
  credit_card: "💳",
  insurance: "🛡",
  subscription: "📺",
  rent: "🏠",
  other: "📄",
};

const statusConfig: Record<
  BillStatus,
  { label: string; backgroundColor: string; textColor: string }
> = {
  detected: { label: "Detected", backgroundColor: "#eef1f5", textColor: "#58657a" },
  extracted: { label: "Extracted", backgroundColor: "#fff4e2", textColor: "#915a0f" },
  review_required: { label: "Needs Review", backgroundColor: "#fff0df", textColor: "#b56100" },
  confirmed: { label: "Confirmed", backgroundColor: "#e6f0ff", textColor: "#1d5ecc" },
  reminded: { label: "Reminded", backgroundColor: "#efe7ff", textColor: "#6c3bcf" },
  paid: { label: "Paid", backgroundColor: "#e8f7f2", textColor: "#15775f" },
  cancelled: { label: "Cancelled", backgroundColor: "#eef1f5", textColor: "#6f7a8a" },
  failed: { label: "Failed", backgroundColor: "#ffe9ea", textColor: "#ca404d" },
};

export function BillStatusBadge({ status }: { status: BillStatus }) {
  const config = statusConfig[status];
  return (
    <View style={[styles.statusBadge, { backgroundColor: config.backgroundColor }]}>
      <Text style={[styles.statusText, { color: config.textColor }]}>{config.label}</Text>
    </View>
  );
}

export function BillCard({
  bill,
  onPress,
}: {
  bill: Bill;
  onPress: () => void;
}) {
  const due = getFriendlyDueDate(bill.due_date);
  const amount =
    bill.amount != null ? formatMoney(bill.amount, bill.currency) : "Amount unknown";

  const toneStyle = bill.is_overdue
    ? styles.cardOverdue
    : bill.needs_review
      ? styles.cardReview
      : null;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, toneStyle, pressed && styles.cardPressed]}
    >
      <View style={styles.topRow}>
        <View style={styles.providerRow}>
          <Text style={styles.emoji}>{billTypeEmoji[bill.bill_type] || "📄"}</Text>
          <View style={styles.providerDetails}>
            <Text style={styles.provider}>{bill.provider}</Text>
            <Text style={styles.billType}>{bill.bill_type.replace(/_/g, " ")}</Text>
          </View>
        </View>
        <BillStatusBadge status={bill.status} />
      </View>

      <View style={styles.bottomRow}>
        <View style={styles.metaColumn}>
          <View
            style={[
              styles.duePill,
              due.tone === "danger"
                ? styles.duePillDanger
                : due.tone === "warning"
                  ? styles.duePillWarning
                  : styles.duePillNeutral,
            ]}
          >
            <Ionicons
              name={due.tone === "neutral" ? "time-outline" : "alert-circle-outline"}
              size={14}
              color={
                due.tone === "danger"
                  ? theme.colors.danger
                  : due.tone === "warning"
                    ? theme.colors.warning
                    : theme.colors.mutedText
              }
            />
            <Text
              style={[
                styles.dueText,
                due.tone === "danger"
                  ? styles.dueTextDanger
                  : due.tone === "warning"
                    ? styles.dueTextWarning
                    : styles.dueTextNeutral,
              ]}
            >
              {due.label}
            </Text>
          </View>
          {bill.email_subject ? (
            <Text numberOfLines={1} style={styles.emailSubject}>
              {bill.email_subject}
            </Text>
          ) : null}
        </View>

        <View style={styles.amountColumn}>
          <Text style={styles.amount}>{amount}</Text>
          {bill.needs_review ? (
            <Text style={styles.reviewFlag}>Needs manual review</Text>
          ) : null}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    padding: 16,
    gap: 14,
    ...theme.shadow,
  },
  cardPressed: {
    opacity: 0.9,
  },
  cardOverdue: {
    borderColor: "#f5b9bf",
    backgroundColor: "#fff8f8",
  },
  cardReview: {
    borderColor: "#ffd7ae",
    backgroundColor: "#fffdfa",
  },
  topRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  providerRow: {
    flexDirection: "row",
    gap: 12,
    flex: 1,
  },
  emoji: {
    fontSize: 26,
  },
  providerDetails: {
    flex: 1,
    gap: 4,
  },
  provider: {
    color: theme.colors.text,
    fontSize: 17,
    fontWeight: "700",
  },
  billType: {
    color: theme.colors.mutedText,
    fontSize: 13,
    textTransform: "capitalize",
  },
  statusBadge: {
    borderRadius: theme.radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  statusText: {
    fontSize: 11,
    fontWeight: "700",
  },
  bottomRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: 12,
  },
  metaColumn: {
    flex: 1,
    gap: 10,
  },
  duePill: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: theme.radius.pill,
  },
  duePillNeutral: {
    backgroundColor: theme.colors.surfaceMuted,
  },
  duePillWarning: {
    backgroundColor: theme.colors.warningSoft,
  },
  duePillDanger: {
    backgroundColor: theme.colors.dangerSoft,
  },
  dueText: {
    fontSize: 12,
    fontWeight: "600",
  },
  dueTextNeutral: {
    color: theme.colors.mutedText,
  },
  dueTextWarning: {
    color: "#995804",
  },
  dueTextDanger: {
    color: theme.colors.danger,
  },
  emailSubject: {
    color: theme.colors.subtleText,
    fontSize: 12,
  },
  amountColumn: {
    alignItems: "flex-end",
    gap: 8,
  },
  amount: {
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: "800",
  },
  reviewFlag: {
    color: "#9d5d08",
    fontSize: 12,
    fontWeight: "700",
  },
});
