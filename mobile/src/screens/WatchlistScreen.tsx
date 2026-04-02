import React, { useMemo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { demoMarketCards } from "@/data/demoAssets";
import { useWatchlist } from "@/context/WatchlistContext";
import { theme } from "@/theme/theme";
import { SectionHeader } from "@/components/SectionHeader";

export function WatchlistScreen() {
  const { items, clear, remove, ready } = useWatchlist();

  const hydrated = useMemo(
    () =>
      items.map((item) => ({
        ...item,
        match:
          demoMarketCards.find((card) => card.symbol === item.symbol) ||
          ({ symbol: item.symbol, name: item.name, price: 0, changePct: 0, confidence: 0.5, trend: "neutral" } as const),
      })),
    [items],
  );

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <SectionHeader
        title="Watchlist"
        subtitle={ready ? "Locally stored favorites for quick access." : "Loading local storage..."}
        action={
          <Pressable onPress={clear} style={styles.clearButton}>
            <Text style={styles.clearText}>Clear</Text>
          </Pressable>
        }
      />

      {hydrated.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyTitle}>No favorites yet</Text>
          <Text style={styles.emptyText}>
            Save assets from the detail screen to build a local watchlist. This abstraction can later be synced.
          </Text>
        </View>
      ) : (
        hydrated.map((entry) => (
          <View key={entry.symbol} style={styles.row}>
            <View>
              <Text style={styles.symbol}>{entry.symbol}</Text>
              <Text style={styles.name}>{entry.name}</Text>
            </View>
            <View style={styles.rowActions}>
              <Text style={styles.meta}>{entry.match.trend}</Text>
              <Pressable onPress={() => remove(entry.symbol)} style={styles.removeButton}>
                <Text style={styles.removeText}>Remove</Text>
              </Pressable>
            </View>
          </View>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  content: {
    padding: theme.space.xl,
    gap: theme.space.lg,
    paddingBottom: 48,
  },
  clearButton: {
    paddingHorizontal: theme.space.md,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  clearText: {
    color: theme.colors.textPrimary,
    fontWeight: "700",
  },
  emptyCard: {
    gap: theme.space.sm,
    padding: theme.space.lg,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  emptyTitle: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.lg,
    fontWeight: "800",
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    lineHeight: 20,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: theme.space.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  symbol: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.md,
    fontWeight: "800",
  },
  name: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
  },
  rowActions: {
    alignItems: "flex-end",
    gap: 8,
  },
  meta: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    textTransform: "uppercase",
    fontWeight: "700",
  },
  removeButton: {
    paddingHorizontal: theme.space.md,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: theme.colors.dangerSoft,
  },
  removeText: {
    color: theme.colors.textPrimary,
    fontWeight: "700",
  },
});

