import React from "react";
import { ActivityIndicator, Text, View } from "react-native";

import { Masthead } from "@/components/Masthead";
import { makeStyles, useTheme } from "@/theme/theme";

export function SplashScreen() {
  const styles = useStyles();
  const theme = useTheme();
  return (
    <View style={styles.screen}>
      <Masthead />
      <View style={styles.status}>
        <ActivityIndicator size="small" color={theme.colors.ink3} />
        <Text style={styles.text}>Loading your settings</Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  screen: {
    flex: 1,
    paddingHorizontal: theme.gutter,
    backgroundColor: theme.colors.surface,
  },
  status: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.space.sm,
    paddingTop: theme.space.xxl,
  },
  text: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
}));
