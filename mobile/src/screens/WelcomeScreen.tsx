import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Masthead } from "@/components/Masthead";
import { useAuth } from "@/context/AuthContext";
import { makeStyles } from "@/theme/theme";

export function WelcomeScreen() {
  const { enterAsGuest } = useAuth();
  const styles = useStyles();
  const insets = useSafeAreaInsets();

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 32 }]}
    >
      <Masthead />

      <View style={styles.body}>
        <Text style={styles.title} accessibilityRole="header">
          Forecast markets with context, not certainty.
        </Text>
        <Text style={styles.paragraph}>
          You get a price path with a range around it. The range matters as much as the line: a wide
          range means the model is unsure, and Aurion will not hide that.
        </Text>
        <Text style={styles.paragraph}>
          The ML analog model only answers when it beats a simple statistical baseline on recent
          history. When it doesn't, you see the baseline instead, together with the reason.
        </Text>

        <View style={styles.actions}>
          <Pressable
            onPress={enterAsGuest}
            accessibilityRole="button"
            style={({ pressed }) => [styles.button, pressed && styles.pressed]}
          >
            <Text style={styles.buttonText}>Continue as guest</Text>
            <Text style={styles.buttonText} aria-hidden>
              {"→"}
            </Text>
          </Pressable>
          <Text style={styles.fine}>No account needed. Your watchlist stays on this device.</Text>
        </View>
      </View>

      <Text style={styles.colophon}>
        Aurion provides market analysis, not financial advice. Forecasts are statistical estimates, and
        past performance does not guarantee future results.
      </Text>
    </ScrollView>
  );
}

const useStyles = makeStyles((theme) => ({
  screen: {
    flex: 1,
    backgroundColor: theme.colors.surface,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: theme.gutter,
  },
  body: {
    flex: 1,
    gap: theme.space.lg,
    paddingTop: theme.space.xxl,
    paddingBottom: theme.space.xxl,
  },
  title: {
    fontSize: 32,
    lineHeight: 38,
    letterSpacing: -0.6,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
    marginBottom: theme.space.sm,
  },
  paragraph: {
    ...theme.text.body,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  actions: {
    marginTop: theme.space.xl,
    gap: theme.space.md,
  },
  button: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    minHeight: 48,
    paddingHorizontal: 22,
    borderRadius: theme.radius,
    backgroundColor: theme.colors.buttonBg,
  },
  pressed: {
    opacity: 0.85,
  },
  buttonText: {
    ...theme.text.body,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.buttonFg,
  },
  fine: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  colophon: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
    paddingTop: theme.space.lg,
    borderTopWidth: 1,
    borderTopColor: theme.colors.grid,
  },
}));
