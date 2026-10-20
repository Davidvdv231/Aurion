import React, { useEffect, useState } from "react";
import { FlatList, RefreshControl, Text, TextInput, View } from "react-native";

import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";

import type { AssetType, ForecastEngine, TickerItem } from "@/api/types";
import { AssetRow } from "@/components/AssetRow";
import { Masthead } from "@/components/Masthead";
import { Note } from "@/components/Note";
import { SectionHeader } from "@/components/SectionHeader";
import { TextToggle } from "@/components/TextToggle";
import { makeStyles, useTheme } from "@/theme/theme";
import { defaultEngineFor, loadHighlights, searchAssets } from "@/services/marketService";
import { asSentence } from "@/utils/format";
import type { MainTabParamList, RootStackParamList } from "@/navigation/types";

type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabParamList, "Home">,
  NativeStackScreenProps<RootStackParamList>
>;

const ASSET_TYPES: AssetType[] = ["stock", "crypto"];
const ASSET_LABELS: Record<AssetType, string> = { stock: "Stocks", crypto: "Crypto" };
const ENGINES: ForecastEngine[] = ["ml", "stat"];
const ENGINE_LABELS: Record<ForecastEngine, string> = { ml: "ML analog", stat: "Statistical" };

export function HomeScreen({ navigation }: Props) {
  const theme = useTheme();
  const styles = useStyles();
  const [query, setQuery] = useState("");
  const [assetType, setAssetType] = useState<AssetType>("stock");
  const [engine, setEngine] = useState<ForecastEngine>(defaultEngineFor("stock"));
  const [results, setResults] = useState<TickerItem[]>([]);
  const [topAssets, setTopAssets] = useState<TickerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [resultsFallback, setResultsFallback] = useState(false);
  const [resultsMessage, setResultsMessage] = useState("");
  const [highlightsFallback, setHighlightsFallback] = useState(false);
  const [highlightsMessage, setHighlightsMessage] = useState("");

  const selectAssetType = (next: AssetType) => {
    setAssetType(next);
    setEngine(defaultEngineFor(next));
  };

  useEffect(() => {
    let mounted = true;

    if (!query.trim()) {
      setResults([]);
      setResultsFallback(false);
      setLoading(false);
      setResultsMessage("");
      return;
    }

    setLoading(true);
    const timer = setTimeout(() => {
      searchAssets(query.trim(), assetType)
        .then((result) => {
          if (mounted) {
            setResults(result.items);
            setResultsFallback(result.isDemo);
            setResultsMessage(result.reason ?? "");
          }
        })
        .catch(() => {
          if (mounted) {
            setResults([]);
            setResultsFallback(false);
            setResultsMessage("Search is currently unavailable.");
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

  useEffect(() => {
    let mounted = true;

    loadHighlights(assetType)
      .then((result) => {
        if (!mounted) {
          return;
        }
        setTopAssets(result.items);
        setHighlightsFallback(result.isDemo);
        setHighlightsMessage(result.reason ?? "");
      })
      .catch(() => {
        if (!mounted) {
          return;
        }
        setTopAssets([]);
        setHighlightsFallback(false);
        setHighlightsMessage("Top assets are currently unavailable.");
      })
      .finally(() => {
        if (mounted) {
          setRefreshing(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [assetType, reloadKey]);

  const openAsset = (symbol: string, name: string) => {
    const payload = { symbol, assetType, name, engine };
    const parentNavigation = navigation.getParent?.();
    if (parentNavigation) {
      parentNavigation.navigate("AssetDetail", payload);
      return;
    }
    navigation.navigate("AssetDetail", payload);
  };

  const searching = query.trim().length > 0;
  const listTitle = searching ? "Search results" : assetType === "stock" ? "Trending stocks" : "Trending crypto";
  const fallbackNote = searching
    ? resultsFallback
      ? `Showing demo search results. ${asSentence(resultsMessage)}`.trim()
      : resultsMessage && results.length === 0 && !loading
        ? resultsMessage
        : ""
    : highlightsFallback
      ? `Showing demo highlights. ${asSentence(highlightsMessage)}`.trim()
      : highlightsMessage && topAssets.length === 0
        ? highlightsMessage
        : "";

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.content}
      data={searching ? results : topAssets}
      keyExtractor={(item) => item.symbol}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={
        <View>
          <Masthead />

          <View style={styles.query}>
            <View style={styles.controlRow}>
              <Text style={styles.controlLabel}>Market</Text>
              <TextToggle
                options={ASSET_TYPES}
                value={assetType}
                labels={ASSET_LABELS}
                onChange={selectAssetType}
                accessibilityLabel="Market"
              />
            </View>
            <View style={styles.controlRow}>
              <Text style={styles.controlLabel}>Model</Text>
              <TextToggle
                options={ENGINES}
                value={engine}
                labels={ENGINE_LABELS}
                onChange={setEngine}
                accessibilityLabel="Forecast model"
              />
            </View>

            <View style={styles.searchBlock}>
              <Text style={styles.controlLabel}>Symbol</Text>
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder={assetType === "stock" ? "e.g. NVDA" : "e.g. BTC"}
                placeholderTextColor={theme.colors.ink3}
                autoCapitalize="characters"
                autoCorrect={false}
                returnKeyType="search"
                accessibilityLabel="Search by symbol"
                style={styles.searchInput}
              />
              <Text style={styles.searchStatus}>{loading ? "Searching..." : " "}</Text>
            </View>
          </View>

          <View style={styles.listHead}>
            <SectionHeader title={listTitle} />
          </View>
          {fallbackNote ? (
            <View style={styles.noteWrap}>
              <Note tone="warning">{fallbackNote}</Note>
            </View>
          ) : null}
        </View>
      }
      renderItem={({ item }) => (
        <AssetRow
          symbol={item.symbol}
          name={item.name}
          meta={item.exchange}
          onPress={() => openAsset(item.symbol, item.name)}
        />
      )}
      ListEmptyComponent={
        searching && !loading ? (
          <Text style={styles.empty}>No matches. Try another symbol or switch market.</Text>
        ) : undefined
      }
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            setQuery("");
            setReloadKey((key) => key + 1);
          }}
          tintColor={theme.colors.ink3}
          colors={[theme.colors.ink2]}
        />
      }
    />
  );
}

const useStyles = makeStyles((theme) => ({
  screen: {
    flex: 1,
    backgroundColor: theme.colors.surface,
  },
  content: {
    paddingHorizontal: theme.gutter,
    paddingBottom: 48,
  },
  query: {
    paddingTop: theme.space.xl,
    paddingBottom: theme.space.lg,
    gap: theme.space.md,
  },
  controlRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.space.lg,
  },
  controlLabel: {
    ...theme.text.fine,
    width: 64,
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink3,
  },
  searchBlock: {
    marginTop: theme.space.md,
    gap: theme.space.xs,
  },
  searchInput: {
    fontSize: 22,
    lineHeight: 30,
    fontFamily: theme.fonts.monoMedium,
    color: theme.colors.ink,
    paddingVertical: theme.space.xs,
    paddingHorizontal: 0,
    borderBottomWidth: 2,
    borderBottomColor: theme.colors.ink,
  },
  searchStatus: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  listHead: {
    paddingTop: theme.space.sm,
    paddingBottom: theme.space.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.ink,
  },
  noteWrap: {
    paddingVertical: theme.space.md,
  },
  empty: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
    paddingVertical: theme.space.lg,
  },
}));
