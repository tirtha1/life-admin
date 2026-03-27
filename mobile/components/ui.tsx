import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { theme } from "@/lib/theme";

type AppScreenProps = {
  children: ReactNode;
  contentContainerStyle?: StyleProp<ViewStyle>;
  refreshing?: boolean;
  onRefresh?: () => void;
};

type ActionButtonProps = {
  label: string;
  onPress?: () => void;
  icon?: ReactNode;
  tone?: "primary" | "secondary" | "success" | "danger" | "muted";
  disabled?: boolean;
  loading?: boolean;
  fullWidth?: boolean;
};

type MetricCardProps = {
  label: string;
  value: string;
  subtext?: string;
  accent?: "primary" | "accent" | "success" | "warning";
};

type FilterChipProps = {
  label: string;
  active?: boolean;
  onPress?: () => void;
};

type InputFieldProps = TextInputProps & {
  label: string;
  helper?: string;
};

const buttonToneStyles = {
  primary: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
    textColor: "#ffffff",
  },
  secondary: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    textColor: theme.colors.text,
  },
  success: {
    backgroundColor: theme.colors.success,
    borderColor: theme.colors.success,
    textColor: "#ffffff",
  },
  danger: {
    backgroundColor: theme.colors.danger,
    borderColor: theme.colors.danger,
    textColor: "#ffffff",
  },
  muted: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    textColor: theme.colors.mutedText,
  },
};

const accentColors = {
  primary: theme.colors.primarySoft,
  accent: theme.colors.accentSoft,
  success: theme.colors.successSoft,
  warning: theme.colors.warningSoft,
};

export function AppScreen({
  children,
  contentContainerStyle,
  refreshing = false,
  onRefresh,
}: AppScreenProps) {
  return (
    <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={[styles.contentContainer, contentContainerStyle]}
        refreshControl={
          onRefresh ? (
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={theme.colors.primary}
            />
          ) : undefined
        }
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function ScreenHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <View style={styles.headerShell}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text style={styles.screenTitle}>{title}</Text>
      <Text style={styles.screenDescription}>{description}</Text>
      {actions ? <View style={styles.headerActions}>{actions}</View> : null}
    </View>
  );
}

export function SectionCard({
  children,
  style,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <View style={styles.sectionTitleRow}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

export function MetricCard({ label, value, subtext, accent = "primary" }: MetricCardProps) {
  return (
    <View style={[styles.metricCard, { backgroundColor: accentColors[accent] }]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
      {subtext ? <Text style={styles.metricSubtext}>{subtext}</Text> : null}
    </View>
  );
}

export function ActionButton({
  label,
  onPress,
  icon,
  tone = "primary",
  disabled = false,
  loading = false,
  fullWidth = false,
}: ActionButtonProps) {
  const toneStyle = buttonToneStyles[tone];
  return (
    <Pressable
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [
        styles.buttonBase,
        fullWidth && styles.buttonFullWidth,
        {
          backgroundColor: toneStyle.backgroundColor,
          borderColor: toneStyle.borderColor,
          opacity: disabled || loading ? 0.55 : pressed ? 0.88 : 1,
        },
      ]}
    >
      {loading ? (
        <ActivityIndicator color={toneStyle.textColor} size="small" />
      ) : (
        <>
          {icon ? <View style={styles.buttonIcon}>{icon}</View> : null}
          <Text style={[styles.buttonText, { color: toneStyle.textColor }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

export function FilterChip({ label, active = false, onPress }: FilterChipProps) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.filterChip,
        active ? styles.filterChipActive : styles.filterChipInactive,
        pressed && styles.filterChipPressed,
      ]}
    >
      <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{label}</Text>
    </Pressable>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <SectionCard style={styles.emptyCard}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyDescription}>{description}</Text>
    </SectionCard>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <View style={styles.errorBanner}>
      <Text style={styles.errorText}>{message}</Text>
    </View>
  );
}

export function InfoBanner({
  message,
  tone = "primary",
}: {
  message: string;
  tone?: "primary" | "success" | "warning";
}) {
  const toneMap = {
    primary: {
      backgroundColor: theme.colors.primarySoft,
      borderColor: "#c7ddff",
      textColor: theme.colors.primaryPressed,
    },
    success: {
      backgroundColor: theme.colors.successSoft,
      borderColor: "#c4ecdf",
      textColor: theme.colors.success,
    },
    warning: {
      backgroundColor: theme.colors.warningSoft,
      borderColor: "#ffd9b5",
      textColor: "#9b5a0a",
    },
  };

  return (
    <View
      style={[
        styles.infoBanner,
        {
          backgroundColor: toneMap[tone].backgroundColor,
          borderColor: toneMap[tone].borderColor,
        },
      ]}
    >
      <Text style={[styles.infoText, { color: toneMap[tone].textColor }]}>{message}</Text>
    </View>
  );
}

export function InputField({ label, helper, multiline, ...props }: InputFieldProps) {
  return (
    <View style={styles.fieldShell}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        {...props}
        multiline={multiline}
        style={[styles.input, multiline ? styles.inputMultiline : null, props.style]}
        placeholderTextColor={theme.colors.subtleText}
        autoCapitalize="none"
        autoCorrect={false}
      />
      {helper ? <Text style={styles.fieldHelper}>{helper}</Text> : null}
    </View>
  );
}

export const sharedStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
  },
  wrap: {
    flexDirection: "row",
    flexWrap: "wrap",
  },
  gap8: {
    gap: 8,
  },
  gap10: {
    gap: 10,
  },
  gap12: {
    gap: 12,
  },
  gap16: {
    gap: 16,
  },
  mutedText: {
    color: theme.colors.mutedText,
  },
});

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  scrollView: {
    flex: 1,
  },
  contentContainer: {
    paddingHorizontal: 18,
    paddingBottom: 42,
    gap: 18,
  },
  headerShell: {
    paddingTop: 8,
    gap: 8,
  },
  eyebrow: {
    color: theme.colors.accent,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  screenTitle: {
    color: theme.colors.text,
    fontSize: 30,
    fontWeight: "800",
    letterSpacing: -0.8,
  },
  screenDescription: {
    color: theme.colors.mutedText,
    fontSize: 15,
    lineHeight: 22,
  },
  headerActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    paddingTop: 4,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 18,
    gap: 14,
    ...theme.shadow,
  },
  sectionTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "700",
  },
  sectionSubtitle: {
    color: theme.colors.subtleText,
    fontSize: 13,
    fontWeight: "500",
  },
  metricCard: {
    flex: 1,
    minWidth: 148,
    borderRadius: theme.radius.lg,
    padding: 16,
    gap: 8,
    borderWidth: 1,
    borderColor: "rgba(19, 34, 56, 0.05)",
  },
  metricLabel: {
    color: theme.colors.mutedText,
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  metricValue: {
    color: theme.colors.text,
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: -0.8,
  },
  metricSubtext: {
    color: theme.colors.mutedText,
    fontSize: 13,
    lineHeight: 18,
  },
  buttonBase: {
    minHeight: 48,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
  },
  buttonFullWidth: {
    alignSelf: "stretch",
  },
  buttonIcon: {
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: {
    fontSize: 15,
    fontWeight: "700",
  },
  filterChip: {
    borderRadius: theme.radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
  },
  filterChipActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  filterChipInactive: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
  },
  filterChipPressed: {
    opacity: 0.85,
  },
  filterChipText: {
    color: theme.colors.mutedText,
    fontSize: 13,
    fontWeight: "700",
  },
  filterChipTextActive: {
    color: "#ffffff",
  },
  emptyCard: {
    alignItems: "center",
    paddingVertical: 32,
  },
  emptyTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "700",
  },
  emptyDescription: {
    color: theme.colors.mutedText,
    fontSize: 14,
    lineHeight: 20,
    textAlign: "center",
  },
  errorBanner: {
    borderWidth: 1,
    borderColor: "#f0b2b6",
    backgroundColor: theme.colors.dangerSoft,
    borderRadius: theme.radius.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 20,
  },
  infoBanner: {
    borderWidth: 1,
    borderRadius: theme.radius.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  infoText: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "600",
  },
  fieldShell: {
    gap: 8,
  },
  fieldLabel: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "700",
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surface,
    color: theme.colors.text,
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  inputMultiline: {
    minHeight: 120,
    textAlignVertical: "top",
  },
  fieldHelper: {
    color: theme.colors.subtleText,
    fontSize: 12,
    lineHeight: 18,
  },
});
