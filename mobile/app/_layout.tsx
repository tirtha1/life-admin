import { DefaultTheme, ThemeProvider } from "@react-navigation/native";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Redirect, Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { AuthProvider, useAuth } from "@/lib/auth";
import { AppConfigProvider, useAppConfig } from "@/lib/config";
import { theme } from "@/lib/theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

const navigationTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: theme.colors.background,
    card: theme.colors.surface,
    border: theme.colors.border,
    primary: theme.colors.primary,
    text: theme.colors.text,
  },
};

function LoadingShell({ message }: { message?: string }) {
  return (
    <View style={styles.loadingShell}>
      <ActivityIndicator size="large" color={theme.colors.primary} />
      <Text style={styles.loadingTitle}>Life Admin AI</Text>
      <Text style={styles.loadingCopy}>{message ?? "Loading…"}</Text>
    </View>
  );
}

function RootNavigator() {
  const { isReady } = useAppConfig();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  if (!isReady || authLoading) {
    return <LoadingShell message="Restoring your session…" />;
  }

  return (
    <>
      <ThemeProvider value={navigationTheme}>
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: theme.colors.background },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="bills/[id]" options={{ headerShown: false }} />
          <Stack.Screen name="login" options={{ headerShown: false }} />
        </Stack>
      </ThemeProvider>
      <StatusBar style="dark" />
      {/* Route guard: redirect to login when not authenticated */}
      {!isAuthenticated && <Redirect href="/login" />}
    </>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <QueryClientProvider client={queryClient}>
        <AppConfigProvider>
          <AuthProvider>
            <RootNavigator />
          </AuthProvider>
        </AppConfigProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  loadingShell: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 28,
    backgroundColor: theme.colors.background,
    gap: 10,
  },
  loadingTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "700",
  },
  loadingCopy: {
    color: theme.colors.mutedText,
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
  },
});
