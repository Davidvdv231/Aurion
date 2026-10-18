import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";

import { AssetRow } from "@/components/AssetRow";
import { Masthead } from "@/components/Masthead";
import { SectionHeader } from "@/components/SectionHeader";
import { useWatchlist } from "@/context/WatchlistContext";
import type { MainTabParamList, RootStackParamList } from "@/navigation/types";
import { defaultEngineFor } from "@/services/marketService";
import { makeStyles } from "@/theme/theme";

type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabParamList, "Watchlist">,
  NativeStackScreenProps<RootStackParamList>
>;

export function WatchlistScreen({ navigation }: Props) {
  const { items, clear, remove, ready } = useWatchlist();
  const styles = useStyles();

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Masthead />

      <View style={styles.section}>
        <SectionHeader
          title="Watchlist"
          subtitle={ready ? "Saved on this device." : "Loading saved assets..."}
          action={
            items.length > 0 ? (
              <Pressable onPress={clear} accessibilityRole="button" hitSlop={8} style={styles.quietButton}>
                <Text style={styles.quietText}>Clear all</Text>
              </Pressable>
            ) : undefined
          }
        />

        <View style={styles.list}>
          {items.length === 0 ? (
            <Text style={styles.empty}>
              Nothing saved yet. Open a forecast and choose Add to watchlist.
            </Text>
          ) : (
            items.map((item) => (
              <AssetRow
                key={item.symbol}
                symbol={item.symbol}
                name={item.name}
                meta={item.assetType === "crypto" ? "Crypto" : "Stock"}
                onPress={() =>
                  navigation.navigate("AssetDetail", {
                    symbol: item.symbol,
                    assetType: item.assetType,
                    name: item.name,
                    engine: defaultEngineFor(item.assetType),
                  })
                }
                trailing={
                  <Pressable
                    onPress={() => remove(item.symbol)}
                    accessibilityRole="button"
                    accessibilityLabel={`Remove ${item.symbol} from the watchlist`}
                    hitSlop={8}
                    style={styles.remove}
                  >
                    <Text style={styles.removeText}>Remove</Text>
                  </Pressable>
                }
              />
            ))
          )}
        </View>
      </View>
    </ScrollView>
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
  section: {
    paddingTop: theme.space.xl,
    gap: theme.space.md,
  },
  list: {
    borderTopWidth: 1,
    borderTopColor: theme.colors.ink,
  },
  empty: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
    paddingVertical: theme.space.md,
  },
  quietButton: {
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: theme.space.md,
    borderWidth: 1,
    borderColor: theme.colors.rule,
    borderRadius: theme.radius,
  },
  quietText: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  remove: {
    paddingVertical: theme.space.sm,
    paddingLeft: theme.space.md,
  },
  removeText: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
    textDecorationLine: "underline",
    textDecorationColor: theme.colors.rule,
  },
}));
