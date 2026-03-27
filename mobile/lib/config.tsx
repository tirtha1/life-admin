import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const API_URL_KEY = "life_admin_api_base_url";

type AppConfigContextValue = {
  isReady: boolean;
  apiBaseUrl: string;
  defaultApiBaseUrl: string;
  setApiBaseUrl: (value: string) => Promise<void>;
  resetConfig: () => Promise<void>;
};

const AppConfigContext = createContext<AppConfigContextValue | undefined>(undefined);

function stripTrailingSlash(value: string) {
  return value.trim().replace(/\/+$/, "");
}

function resolveExpoHost() {
  const expoGoHost =
    (Constants.expoGoConfig as { debuggerHost?: string } | null)?.debuggerHost ?? null;
  if (expoGoHost) {
    return expoGoHost.split(":")[0] ?? null;
  }

  const expoConfig = Constants.expoConfig as { hostUri?: string } | null;
  if (expoConfig?.hostUri) {
    return expoConfig.hostUri.split(":")[0] ?? null;
  }

  const manifestHost =
    ((Constants as unknown as { manifest2?: { extra?: { expoClient?: { hostUri?: string } } } })
      .manifest2?.extra?.expoClient?.hostUri as string | undefined) ?? undefined;
  if (manifestHost) {
    return manifestHost.split(":")[0] ?? null;
  }

  return null;
}

function getDefaultApiBaseUrl() {
  const envApiUrl = process.env.EXPO_PUBLIC_API_URL;
  if (envApiUrl) {
    return stripTrailingSlash(envApiUrl);
  }

  const expoHost = resolveExpoHost();
  if (expoHost) {
    return `http://${expoHost}:8000`;
  }

  if (Platform.OS === "android") {
    return "http://10.0.2.2:8000";
  }

  return "http://localhost:8000";
}

export function AppConfigProvider({ children }: { children: ReactNode }) {
  const defaultApiBaseUrl = getDefaultApiBaseUrl();
  const [isReady, setIsReady] = useState(false);
  const [apiBaseUrl, setApiBaseUrlState] = useState(defaultApiBaseUrl);

  useEffect(() => {
    let isMounted = true;

    async function loadConfig() {
      const storedApiBaseUrl = await SecureStore.getItemAsync(API_URL_KEY);
      if (!isMounted) return;
      if (storedApiBaseUrl) {
        setApiBaseUrlState(stripTrailingSlash(storedApiBaseUrl));
      }
      setIsReady(true);
    }

    loadConfig().catch(() => {
      if (isMounted) setIsReady(true);
    });

    return () => {
      isMounted = false;
    };
  }, []);

  async function setApiBaseUrl(value: string) {
    const normalized = stripTrailingSlash(value) || defaultApiBaseUrl;
    setApiBaseUrlState(normalized);
    if (normalized === defaultApiBaseUrl) {
      await SecureStore.deleteItemAsync(API_URL_KEY);
      return;
    }
    await SecureStore.setItemAsync(API_URL_KEY, normalized);
  }

  async function resetConfig() {
    setApiBaseUrlState(defaultApiBaseUrl);
    await SecureStore.deleteItemAsync(API_URL_KEY);
  }

  return (
    <AppConfigContext.Provider
      value={{ isReady, apiBaseUrl, defaultApiBaseUrl, setApiBaseUrl, resetConfig }}
    >
      {children}
    </AppConfigContext.Provider>
  );
}

export function useAppConfig() {
  const context = useContext(AppConfigContext);
  if (!context) {
    throw new Error("useAppConfig must be used inside AppConfigProvider");
  }
  return context;
}
