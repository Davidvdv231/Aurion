import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme/theme";

export function SplashScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.logo}>
        <Text style={styles.logoText}>A</Text>
      </View>
      <Text style={styles.title}>Aurion</Text>
      <Text style={styles.subtitle}>Market intelligence loading</Text>
      <ActivityIndicator color={theme.colors.accent} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    gap: theme.space.md,
    backgroundColor: theme.colors.background,
    padding: theme.space.xl,
  },
  logo: {
    width: 92,
    height: 92,
    borderRadius: 28,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  logoText: {
    color: theme.colors.accent,
    fontSize: 28,
    fontWeight: "900",
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: 28,
    fontWeight: "900",
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.md,
  },
});
