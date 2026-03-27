import { Ionicons } from "@expo/vector-icons";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { useAuth } from "@/lib/auth";
import { useAppConfig } from "@/lib/config";
import { theme } from "@/lib/theme";

// Required for iOS — completes the auth session when the browser redirects back.
WebBrowser.maybeCompleteAuthSession();

export default function LoginScreen() {
  const { login } = useAuth();
  const { apiBaseUrl } = useAppConfig();
  const [loading, setLoading] = useState(false);

  async function signInWithGoogle() {
    setLoading(true);
    try {
      // The deep-link URL this app instance is reachable at.
      // In Expo Go: exp://192.168.x.x:8081/--/callback
      // In a dev/production build: lifeadminai://callback
      const appRedirect = Linking.createURL("callback");
      const scheme = appRedirect.split("://")[0]; // "exp" or "lifeadminai"

      // Ask the backend to generate the Google auth URL.
      // It encodes appRedirect in the OAuth state so it can redirect back here.
      const startRes = await fetch(
        `${apiBaseUrl}/api/v1/auth/mobile-start?app_redirect=${encodeURIComponent(appRedirect)}`,
      );
      if (!startRes.ok) {
        const body = (await startRes.json()) as { detail?: string };
        throw new Error(body.detail ?? "Failed to start sign-in");
      }
      const { auth_url } = (await startRes.json()) as { auth_url: string };

      // Open Google consent in a system browser.
      // openAuthSessionAsync closes automatically when it sees a redirect to scheme://.
      const result = await WebBrowser.openAuthSessionAsync(auth_url, `${scheme}://`);

      if (result.type === "cancel" || result.type === "dismiss") {
        return; // User closed the browser — no error needed
      }
      if (result.type !== "success") {
        throw new Error("Sign-in was not completed");
      }

      // Backend redirected to: appRedirect?token=JWT  (or ?error=auth_failed)
      const parsed = Linking.parse(result.url);
      const params = parsed.queryParams ?? {};

      if (params["error"]) {
        throw new Error("Google sign-in failed. Please try again.");
      }

      const token = params["token"];
      if (!token || typeof token !== "string") {
        throw new Error("No token received from server");
      }

      await login(token);
      // Root layout reacts to isAuthenticated and redirects to tabs automatically
    } catch (err) {
      Alert.alert(
        "Sign-in failed",
        err instanceof Error ? err.message : "Something went wrong. Try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.logoArea}>
        <View style={styles.iconCircle}>
          <Ionicons name="card-outline" size={44} color={theme.colors.primary} />
        </View>
        <Text style={styles.title}>Life Admin AI</Text>
        <Text style={styles.subtitle}>
          Bills, transactions, and spending — found and managed automatically.
        </Text>
      </View>

      <TouchableOpacity
        style={[styles.googleButton, loading && styles.googleButtonDisabled]}
        onPress={() => !loading && signInWithGoogle()}
        disabled={loading}
        activeOpacity={0.85}
      >
        {loading ? (
          <ActivityIndicator size="small" color="#ffffff" />
        ) : (
          <>
            <Ionicons name="logo-google" size={20} color="#ffffff" />
            <Text style={styles.googleButtonText}>Continue with Google</Text>
          </>
        )}
      </TouchableOpacity>

      <Text style={styles.disclaimer}>
        By signing in you grant read-only access to your Gmail so Life Admin can find bills and
        transactions. Your refresh token is stored encrypted on the server — your phone only holds
        a short-lived app token.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    paddingHorizontal: 28,
    justifyContent: "center",
    gap: 24,
  },
  logoArea: {
    alignItems: "center",
    gap: 14,
    marginBottom: 8,
  },
  iconCircle: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: theme.colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  title: {
    fontSize: 30,
    fontWeight: "800",
    color: theme.colors.text,
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 16,
    color: theme.colors.mutedText,
    textAlign: "center",
    lineHeight: 24,
  },
  googleButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.primary,
    paddingVertical: 17,
    borderRadius: theme.radius.md,
    gap: 10,
    ...theme.shadow,
  },
  googleButtonDisabled: {
    opacity: 0.5,
  },
  googleButtonText: {
    color: "#ffffff",
    fontSize: 17,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  disclaimer: {
    color: theme.colors.subtleText,
    fontSize: 12,
    textAlign: "center",
    lineHeight: 18,
    paddingHorizontal: 8,
  },
});
