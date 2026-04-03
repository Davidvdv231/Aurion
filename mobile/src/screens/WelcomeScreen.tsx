import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { useAuth } from "@/context/AuthContext";
import { theme } from "@/theme/theme";

export function WelcomeScreen() {
  const { enterAsGuest } = useAuth();

  return (
    <View style={styles.screen}>
      <View style={styles.hero}>
        <Text style={styles.eyebrow}>Aurion MVP</Text>
        <Text style={styles.title}>Forecast markets with context, not certainty.</Text>
        <Text style={styles.subtitle}>
          Short-term trend indication, banded forecasts and confidence tiers.
          No guarantees, no financial advice.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Guest mode</Text>
        <Text style={styles.cardBody}>
          No account required. Explore forecasts, save a watchlist, and see how the models work.
        </Text>
        <Pressable onPress={enterAsGuest} style={({ pressed }) => [styles.button, pressed && styles.pressed]}>
          <Text style={styles.buttonText}>Continue as guest</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    justifyContent: "space-between",
    backgroundColor: theme.colors.background,
    padding: theme.space.xl,
  },
  hero: {
    gap: theme.space.md,
    paddingTop: 36,
  },
  eyebrow: {
    color: theme.colors.accent,
    fontSize: theme.fontSizes.sm,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: 36,
    fontWeight: "900",
    lineHeight: 42,
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.md,
    lineHeight: 22,
  },
  card: {
    gap: theme.space.md,
    padding: theme.space.lg,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  cardTitle: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.lg,
    fontWeight: "800",
  },
  cardBody: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.md,
    lineHeight: 22,
  },
  button: {
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.md,
    paddingVertical: 14,
    alignItems: "center",
  },
  pressed: {
    opacity: 0.92,
  },
  buttonText: {
    color: theme.colors.background,
    fontWeight: "800",
  },
});
