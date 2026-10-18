import React from "react";
import { Text, View } from "react-native";

import { makeStyles } from "@/theme/theme";

interface NoteProps {
  tone?: "neutral" | "warning" | "error";
  lead?: string;
  children: React.ReactNode;
}

// A ruled aside for fallbacks and warnings; the tone is carried by an icon as well as color.
export function Note({ tone = "neutral", lead, children }: NoteProps) {
  const styles = useStyles();
  return (
    <View
      style={[styles.note, tone === "warning" && styles.warning, tone === "error" && styles.error]}
      accessibilityRole={tone === "neutral" ? undefined : "alert"}
    >
      <Text style={styles.text}>
        {tone === "neutral" ? null : "⚠︎  "}
        {lead ? <Text style={styles.lead}>{lead} </Text> : null}
        {children}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  note: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.rule,
    backgroundColor: theme.colors.hover,
  },
  warning: {
    borderLeftColor: theme.colors.warning,
    backgroundColor: theme.colors.warningWash,
  },
  error: {
    borderLeftColor: theme.colors.down,
    backgroundColor: theme.colors.errorWash,
  },
  text: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink,
  },
  lead: {
    fontFamily: theme.fonts.sansSemiBold,
  },
}));
