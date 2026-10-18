import React from "react";
import { Text, View } from "react-native";

import { makeStyles } from "@/theme/theme";

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function SectionHeader({ title, subtitle, action }: SectionHeaderProps) {
  const styles = useStyles();
  return (
    <View style={styles.row}>
      <View style={styles.textWrap}>
        <Text style={styles.title} accessibilityRole="header">
          {title}
        </Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {action}
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
    gap: theme.space.md,
  },
  textWrap: {
    flex: 1,
    gap: 2,
  },
  title: {
    ...theme.text.small,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
  },
  subtitle: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
}));
