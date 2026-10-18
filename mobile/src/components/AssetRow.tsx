import React from "react";
import { Pressable, Text, View } from "react-native";

import { makeStyles } from "@/theme/theme";

interface AssetRowProps {
  symbol: string;
  name: string;
  meta?: string;
  onPress: () => void;
  trailing?: React.ReactNode;
}

export function AssetRow({ symbol, name, meta, onPress, trailing }: AssetRowProps) {
  const styles = useStyles();
  return (
    <View style={styles.row}>
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={`Open the forecast for ${symbol}, ${name}`}
        style={({ pressed }) => [styles.main, pressed && styles.pressed]}
      >
        <Text style={styles.symbol}>{symbol}</Text>
        <Text style={styles.name} numberOfLines={1}>
          {name}
        </Text>
        {meta ? <Text style={styles.meta}>{meta}</Text> : null}
      </Pressable>
      {trailing}
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  row: {
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  main: {
    flex: 1,
    flexDirection: "row",
    alignItems: "baseline",
    gap: theme.space.md,
    minHeight: 48,
    paddingVertical: theme.space.md,
  },
  pressed: {
    backgroundColor: theme.colors.hover,
  },
  symbol: {
    ...theme.text.body,
    fontFamily: theme.fonts.monoMedium,
    color: theme.colors.ink,
    minWidth: 80,
  },
  name: {
    ...theme.text.small,
    flex: 1,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  meta: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
}));
