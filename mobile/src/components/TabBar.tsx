import React from "react";
import { Pressable, Text, View } from "react-native";
import type { BottomTabBarProps } from "@react-navigation/bottom-tabs";

import { makeStyles } from "@/theme/theme";

// Text tabs under a hairline; the active tab carries a rule on top instead of a tinted icon.
export function TabBar({ state, descriptors, navigation, insets }: BottomTabBarProps) {
  const styles = useStyles();
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 8) }]} accessibilityRole="tablist">
      {state.routes.map((route, index) => {
        const focused = state.index === index;
        const { options } = descriptors[route.key];
        const label = typeof options.title === "string" ? options.title : route.name;
        const onPress = () => {
          const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) {
            navigation.navigate(route.name, route.params);
          }
        };
        return (
          <Pressable
            key={route.key}
            onPress={onPress}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
            style={({ pressed }) => [styles.tab, focused && styles.tabActive, pressed && styles.pressed]}
          >
            <Text style={[styles.label, focused && styles.labelActive]}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  bar: {
    flexDirection: "row",
    gap: theme.space.xl,
    paddingHorizontal: theme.gutter,
    borderTopWidth: 1,
    borderTopColor: theme.colors.grid,
    backgroundColor: theme.colors.surface,
  },
  tab: {
    minHeight: 48,
    justifyContent: "center",
    borderTopWidth: 2,
    borderTopColor: "transparent",
    marginTop: -1,
  },
  tabActive: {
    borderTopColor: theme.colors.ink,
  },
  pressed: {
    opacity: 0.6,
  },
  label: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  labelActive: {
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink,
  },
}));
