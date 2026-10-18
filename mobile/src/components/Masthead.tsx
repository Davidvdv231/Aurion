import React from "react";
import { Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { makeStyles } from "@/theme/theme";

// The wordmark row at the top of each tab, closed off by a hairline like the web masthead.
export function Masthead({ action }: { action?: React.ReactNode }) {
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.masthead, { paddingTop: insets.top + 14 }]}>
      <Text style={styles.wordmark} accessibilityRole="header">
        Aurion
      </Text>
      <Text style={styles.tagline} numberOfLines={1}>
        Price forecasts with honest ranges
      </Text>
      {action}
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  masthead: {
    flexDirection: "row",
    alignItems: "baseline",
    gap: theme.space.lg,
    paddingBottom: theme.space.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  wordmark: {
    fontSize: 18,
    lineHeight: 24,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
    letterSpacing: -0.2,
  },
  tagline: {
    ...theme.text.small,
    flex: 1,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
}));
