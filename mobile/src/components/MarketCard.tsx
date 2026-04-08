import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme/theme";

interface MarketCardProps {
  symbol: string;
  name: string;
  badge: string;
  meta: string;
  detail: string;
  onPress: () => void;
}

export function MarketCard({ symbol, name, badge, meta, detail, onPress }: MarketCardProps) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.headerRow}>
        <Text style={styles.symbol}>{symbol}</Text>
        <Text style={styles.badge}>{badge}</Text>
      </View>
      <Text style={styles.name}>{name}</Text>
      <Text style={styles.meta}>{meta}</Text>
      <Text style={styles.detail}>{detail}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    width: 190,
    padding: theme.space.md,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: theme.space.sm,
  },
  pressed: {
    transform: [{ scale: 0.98 }],
    opacity: 0.92,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  symbol: {
    color: theme.colors.textPrimary,
    fontWeight: "800",
    fontSize: theme.fontSizes.lg,
  },
  badge: {
    fontSize: theme.fontSizes.xs,
    fontWeight: "700",
    textTransform: "uppercase",
    color: theme.colors.accent,
  },
  name: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.md,
    fontWeight: "700",
  },
  meta: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
  },
  detail: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    lineHeight: 18,
  },
});
