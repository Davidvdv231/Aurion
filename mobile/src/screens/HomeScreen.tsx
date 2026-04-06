import React, { useEffect, useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import type { AssetType, ForecastEngine, TickerItem } from "@/api/types";
import { demoMarketCards, demoTickers } from "@/data/demoAssets";
import { MarketCard } from "@/components/MarketCard";
import { SectionHeader } from "@/components/SectionHeader";
import { theme } from "@/theme/theme";
import { searchAssets } from "@/services/marketService";

interface HomeScreenProps {
  navigation: any;
}

export function HomeScreen({ navigation }: HomeScreenProps) {
  const [query, setQuery] = useState("");
  const [assetType, setAssetType] = useState<AssetType>("stock");
  const [engine, setEngine] = useState<ForecastEngine>("ml");
  const [results, setResults] = useState<TickerItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;

    if (!query.trim()) {
      setResults([]);
      return;
    }

    setLoading(true);
    const timer = setTimeout(() => {
      searchAssets(query.trim(), assetType)
        .then((items) => {
          if (mounted) {
            setResults(items);
          }
        })
        .catch(() => {
          if (mounted) {
            const needle = query.trim().toUpperCase();
            setResults(
              demoTickers.filter((item) => item.asset_type === assetType && item.symbol.includes(needle)),
            );
          }
        })
        .finally(() => {
          if (mounted) {
            setLoading(false);
          }
        });
    }, 220);

    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, [assetType, query]);

  const topCards = demoMarketCards.filter((item) => item.assetType === assetType);
  const openAsset = (symbol: string, name: string) => {
    const payload = { symbol, assetType, name, engine };
    const parentNavigation = navigation.getParent?.();
    if (parentNavigation) {
      parentNavigation.navigate("AssetDetail", payload);
      return;
    }
    navigation.navigate("AssetDetail", payload);
  };

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.content}
      data={results}
      keyExtractor={(item) => item.symbol}
      ListHeaderComponent={
        <View style={styles.header}>
          <Text style={styles.kicker}>Guest mode</Text>
          <Text style={styles.title}>Forecast markets with a modern mobile workflow.</Text>
          <Text style={styles.subtitle}>
            Short-term forecasts, trend indication and confidence scores. No certainty claims.
          </Text>

          <View style={styles.toggleRow}>
            <Pressable
              onPress={() => setAssetType("stock")}
              style={[styles.toggle, assetType === "stock" && styles.toggleActive]}
            >
              <Text style={styles.toggleText}>Stocks</Text>
            </Pressable>
            <Pressable
              onPress={() => setAssetType("crypto")}
              style={[styles.toggle, assetType === "crypto" && styles.toggleActive]}
            >
              <Text style={styles.toggleText}>Crypto</Text>
            </Pressable>
          </View>

          <View style={styles.toggleRow}>
            {(["ml", "stat"] as const).map((eng) => (
              <Pressable
                key={eng}
                onPress={() => setEngine(eng)}
                style={[styles.toggle, engine === eng && styles.toggleActive]}
              >
                <Text style={styles.toggleText}>
                  {eng === "ml" ? "ML" : "Stat"}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.searchCard}>
            <Text style={styles.searchLabel}>Search symbol</Text>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder={assetType === "stock" ? "AAPL, MSFT, NVDA" : "BTC, ETH, SOL"}
              placeholderTextColor={theme.colors.textMuted}
              style={styles.searchInput}
            />
            <Text style={styles.searchHint}>{loading ? "Searching backend..." : "Live API first, demo fallback second."}</Text>
          </View>

          <SectionHeader
            title="Market highlights"
            subtitle="Handpicked cards that work as the first navigation surface."
          />
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={topCards}
            keyExtractor={(item) => item.symbol}
            contentContainerStyle={styles.horizontalList}
            renderItem={({ item }) => (
              <MarketCard
                symbol={item.symbol}
                name={item.name}
                price={`$${item.price.toFixed(2)}`}
                change={`${item.changePct > 0 ? "+" : ""}${item.changePct.toFixed(2)}%`}
                confidence={`${Math.round(item.confidence * 100)}% confidence`}
                tone={item.trend}
                onPress={() => openAsset(item.symbol, item.name)}
              />
            )}
          />

          <SectionHeader title="Search results" subtitle="Tap an asset to open the detail page." />
        </View>
      }
      renderItem={({ item }) => (
        <Pressable onPress={() => openAsset(item.symbol, item.name)} style={({ pressed }) => [styles.resultRow, pressed && styles.resultPressed]}>
          <View>
            <Text style={styles.resultSymbol}>{item.symbol}</Text>
            <Text style={styles.resultName}>{item.name}</Text>
          </View>
          <Text style={styles.resultMeta}>{item.exchange}</Text>
        </Pressable>
      )}
      ListEmptyComponent={
        query.trim() ? <Text style={styles.empty}>No matches. Try another symbol or switch asset class.</Text> : null
      }
      refreshControl={
        <RefreshControl
          refreshing={false}
          onRefresh={() => {
            setQuery("");
          }}
          tintColor={theme.colors.accent}
        />
      }
    />
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
    paddingBottom: 40,
  },
  header: {
    gap: theme.space.lg,
  },
  kicker: {
    color: theme.colors.accent,
    fontSize: theme.fontSizes.sm,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: 32,
    fontWeight: "900",
    lineHeight: 38,
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.md,
    lineHeight: 22,
  },
  toggleRow: {
    flexDirection: "row",
    gap: theme.space.sm,
    flexWrap: "wrap",
  },
  toggle: {
    borderRadius: 999,
    paddingHorizontal: theme.space.md,
    paddingVertical: 10,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  toggleActive: {
    backgroundColor: theme.colors.accentSoft,
  },
  toggleText: {
    color: theme.colors.textPrimary,
    fontWeight: "700",
  },
  searchCard: {
    gap: theme.space.sm,
    padding: theme.space.md,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  searchLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    fontWeight: "700",
  },
  searchInput: {
    backgroundColor: theme.colors.surfaceElevated,
    color: theme.colors.textPrimary,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: theme.space.md,
    paddingVertical: 14,
  },
  searchHint: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
  },
  horizontalList: {
    gap: theme.space.md,
    paddingVertical: theme.space.sm,
  },
  resultRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: theme.space.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  resultPressed: {
    opacity: 0.72,
  },
  resultSymbol: {
    color: theme.colors.textPrimary,
    fontWeight: "800",
    fontSize: theme.fontSizes.md,
  },
  resultName: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
  },
  resultMeta: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
  },
  empty: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    paddingVertical: theme.space.sm,
  },
});
