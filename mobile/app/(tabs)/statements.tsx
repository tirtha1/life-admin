import { Ionicons } from "@expo/vector-icons";
import { useMutation } from "@tanstack/react-query";
import * as DocumentPicker from "expo-document-picker";
import { StyleSheet, Text, View } from "react-native";
import { useState } from "react";

import { StatementResults } from "@/components/statement-results";
import {
  ActionButton,
  AppScreen,
  ErrorBanner,
  InfoBanner,
  ScreenHeader,
  SectionCard,
  sharedStyles,
} from "@/components/ui";
import { formatApiError, useApi } from "@/lib/api";
import { theme } from "@/lib/theme";

export default function StatementsScreen() {
  const api = useApi();
  const [selectedFile, setSelectedFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);

  const analysisMutation = useMutation({
    mutationFn: api.statementsApi.analyze,
  });

  async function handlePickFile() {
    const result = await DocumentPicker.getDocumentAsync({
      type: ["application/pdf", "text/csv", "text/comma-separated-values", "application/vnd.ms-excel"],
      multiple: false,
      copyToCacheDirectory: true,
    });

    if (!result.canceled) {
      setSelectedFile(result.assets[0] ?? null);
    }
  }

  function handleAnalyze() {
    if (!selectedFile) {
      return;
    }

    analysisMutation.mutate({
      uri: selectedFile.uri,
      name: selectedFile.name,
      mimeType: selectedFile.mimeType,
    });
  }

  return (
    <AppScreen>
      <ScreenHeader
        eyebrow="Statement Analyzer"
        title="Turn a raw statement into actions"
        description="Upload a PDF or CSV bank statement, extract structured transactions, detect leaks, and get practical next steps from the same analysis engine you already built."
      />

      <SectionCard style={styles.heroCard}>
        <View style={[sharedStyles.row, sharedStyles.gap12]}>
          <View style={styles.uploadIcon}>
            <Ionicons name="cloud-upload-outline" size={22} color={theme.colors.warning} />
          </View>
          <View style={styles.flexOne}>
            <Text style={styles.heroTitle}>Analyze a statement</Text>
            <Text style={styles.heroBody}>
              Works best with files that include date, description, and amount or debit/credit columns.
            </Text>
          </View>
        </View>

        <View style={styles.fileBox}>
          <Ionicons
            name={selectedFile?.name.toLowerCase().endsWith(".pdf") ? "document-text-outline" : "grid-outline"}
            size={22}
            color={theme.colors.primary}
          />
          <View style={styles.flexOne}>
            <Text style={styles.fileName}>
              {selectedFile ? selectedFile.name : "Choose a CSV or PDF file"}
            </Text>
            <Text style={styles.fileHelp}>
              Demo-friendly flow: upload, parse, inspect recurring charges, and show actions.
            </Text>
          </View>
        </View>

        <View style={[sharedStyles.row, styles.buttonRow]}>
          <ActionButton
            label="Choose File"
            tone="secondary"
            icon={<Ionicons name="folder-open-outline" size={18} color={theme.colors.text} />}
            onPress={handlePickFile}
          />
          <ActionButton
            label={analysisMutation.isPending ? "Analyzing…" : "Analyze"}
            icon={<Ionicons name="sparkles-outline" size={18} color="#ffffff" />}
            onPress={handleAnalyze}
            disabled={!selectedFile}
            loading={analysisMutation.isPending}
          />
        </View>
      </SectionCard>

      {selectedFile ? (
        <InfoBanner message={`Ready to analyze ${selectedFile.name}`} />
      ) : null}

      {analysisMutation.error ? <ErrorBanner message={formatApiError(analysisMutation.error)} /> : null}

      {analysisMutation.data ? <StatementResults result={analysisMutation.data} /> : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  heroCard: {
    backgroundColor: "#fff9ef",
    borderColor: "#f3d7a7",
  },
  uploadIcon: {
    width: 48,
    height: 48,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.warningSoft,
  },
  flexOne: {
    flex: 1,
    gap: 6,
  },
  heroTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "700",
  },
  heroBody: {
    color: theme.colors.mutedText,
    fontSize: 14,
    lineHeight: 21,
  },
  fileBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: "#ffffff",
    borderRadius: theme.radius.md,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  fileName: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  fileHelp: {
    color: theme.colors.subtleText,
    fontSize: 12,
    lineHeight: 18,
  },
  buttonRow: {
    gap: 10,
    flexWrap: "wrap",
  },
});
