import { Ionicons } from "@expo/vector-icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Alert, Platform, StyleSheet, Text, View } from "react-native";

import {
  ActionButton,
  AppScreen,
  ErrorBanner,
  InfoBanner,
  InputField,
  ScreenHeader,
  SectionCard,
  SectionTitle,
} from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { formatApiError, useApi } from "@/lib/api";
import { useAppConfig } from "@/lib/config";
import { theme } from "@/lib/theme";

export default function SettingsScreen() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { apiBaseUrl, defaultApiBaseUrl, setApiBaseUrl, resetConfig } = useAppConfig();
  const { user, token, logout } = useAuth();

  const [draftApiUrl, setDraftApiUrl] = useState(apiBaseUrl);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  useEffect(() => {
    setDraftApiUrl(apiBaseUrl);
  }, [apiBaseUrl]);

  const healthMutation = useMutation({
    mutationFn: api.healthApi.check,
  });

  async function handleSave() {
    try {
      await setApiBaseUrl(draftApiUrl);
      queryClient.clear();
      setLastSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
      Alert.alert("Saved", "API URL updated.");
    } catch (error) {
      Alert.alert("Save failed", formatApiError(error));
    }
  }

  async function handleReset() {
    try {
      await resetConfig();
      queryClient.clear();
      setLastSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
      Alert.alert("Reset", "API URL reset to default.");
    } catch (error) {
      Alert.alert("Reset failed", formatApiError(error));
    }
  }

  async function handleLogout() {
    Alert.alert(
      "Sign out",
      "This will revoke your Gmail access and sign you out. You can sign back in at any time.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Sign out",
          style: "destructive",
          onPress: async () => {
            try {
              // Best-effort server-side revocation (ignore errors)
              await api.healthApi.check().catch(() => {});
              await fetch(`${apiBaseUrl}/api/v1/auth/logout`, {
                method: "POST",
                headers: {
                  Authorization: `Bearer ${token}`,
                },
              }).catch(() => {});
            } finally {
              queryClient.clear();
              await logout();
            }
          },
        },
      ],
    );
  }

  async function handleDeleteAccount() {
    Alert.alert(
      "Delete account",
      "This permanently deletes all your bills, transactions, and data. This cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete everything",
          style: "destructive",
          onPress: () => {
            Alert.alert(
              "Are you sure?",
              "All data will be permanently deleted.",
              [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Yes, delete",
                  style: "destructive",
                  onPress: async () => {
                    try {
                      await fetch(`${apiBaseUrl}/api/v1/auth/account`, {
                        method: "DELETE",
                        headers: {
                          Authorization: `Bearer ${token}`,
                        },
                      }).catch(() => {});
                    } finally {
                      queryClient.clear();
                      await logout();
                    }
                  },
                },
              ],
            );
          },
        },
      ],
    );
  }

  const connectionHint =
    Platform.OS === "android"
      ? "Android emulator usually needs http://10.0.2.2:8000. A real device needs your laptop's LAN IP."
      : "iOS simulator can often use localhost. A real device still needs your laptop's LAN IP.";

  return (
    <AppScreen>
      <ScreenHeader
        eyebrow="Settings"
        title="Account & connection"
        description={`Signed in as ${user?.email ?? "unknown"}`}
      />

      <SectionCard>
        <SectionTitle title="API Connection" subtitle="Dev setup" />
        <InputField
          label="API Base URL"
          value={draftApiUrl}
          onChangeText={setDraftApiUrl}
          placeholder="http://10.0.2.2:8000"
          helper={connectionHint}
        />
        <View style={styles.buttonColumn}>
          <ActionButton
            label="Save URL"
            icon={<Ionicons name="save-outline" size={18} color="#ffffff" />}
            onPress={handleSave}
            fullWidth
          />
          <ActionButton
            label="Reset to Default"
            tone="secondary"
            icon={<Ionicons name="refresh-outline" size={18} color={theme.colors.text} />}
            onPress={handleReset}
            fullWidth
          />
        </View>
      </SectionCard>

      {lastSavedAt ? <InfoBanner message={`Settings updated at ${lastSavedAt}.`} /> : null}

      <SectionCard>
        <SectionTitle title="Connection Check" subtitle="Health endpoint" />
        <ActionButton
          label={healthMutation.isPending ? "Testing…" : "Test API Connection"}
          tone="secondary"
          icon={<Ionicons name="pulse-outline" size={18} color={theme.colors.text} />}
          onPress={() => healthMutation.mutate()}
          loading={healthMutation.isPending}
          fullWidth
        />
        {healthMutation.isSuccess ? (
          <InfoBanner
            tone="success"
            message={`API responded: ${JSON.stringify(healthMutation.data)}`}
          />
        ) : null}
        {healthMutation.error ? <ErrorBanner message={formatApiError(healthMutation.error)} /> : null}
      </SectionCard>

      <SectionCard>
        <SectionTitle title="Detected API URL" subtitle="Auto-filled on first launch" />
        <View style={styles.detailColumn}>
          <View>
            <Text style={styles.detailLabel}>URL</Text>
            <Text style={styles.detailValue}>{defaultApiBaseUrl}</Text>
          </View>
        </View>
      </SectionCard>

      <SectionCard>
        <SectionTitle title="Account" subtitle="Google connection" />
        <ActionButton
          label="Sign out"
          tone="secondary"
          icon={<Ionicons name="log-out-outline" size={18} color={theme.colors.text} />}
          onPress={handleLogout}
          fullWidth
        />
        <ActionButton
          label="Delete account & data"
          tone="danger"
          icon={<Ionicons name="trash-outline" size={18} color={theme.colors.danger} />}
          onPress={handleDeleteAccount}
          fullWidth
        />
      </SectionCard>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  buttonColumn: {
    gap: 10,
  },
  detailColumn: {
    gap: 14,
  },
  detailLabel: {
    color: theme.colors.subtleText,
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 4,
  },
  detailValue: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "600",
  },
});
