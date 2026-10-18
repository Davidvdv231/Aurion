import React from "react";
import { Pressable, Text, View } from "react-native";

import { makeStyles } from "@/theme/theme";

interface TextToggleProps<T extends string> {
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
  labels?: Record<T, string>;
  accessibilityLabel: string;
  size?: "regular" | "small";
}

// Words, not pills: the active option is underlined, the rest stay quiet.
export function TextToggle<T extends string>({
  options,
  value,
  onChange,
  labels,
  accessibilityLabel,
  size = "regular",
}: TextToggleProps<T>) {
  const styles = useStyles();
  const withSeparator = options.length === 2;

  return (
    <View style={styles.group} accessibilityRole="radiogroup" accessibilityLabel={accessibilityLabel}>
      {options.map((option, index) => {
        const selected = option === value;
        return (
          <React.Fragment key={option}>
            {withSeparator && index > 0 ? (
              <Text style={[styles.separator, size === "small" && styles.small]} aria-hidden>
                /
              </Text>
            ) : null}
            <Pressable
              onPress={() => onChange(option)}
              accessibilityRole="radio"
              accessibilityState={{ selected, checked: selected }}
              hitSlop={6}
              style={({ pressed }) => [styles.option, selected && styles.optionActive, pressed && styles.pressed]}
            >
              <Text style={[styles.label, size === "small" && styles.small, selected && styles.labelActive]}>
                {labels ? labels[option] : option}
              </Text>
            </Pressable>
          </React.Fragment>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  group: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    columnGap: theme.space.sm,
    rowGap: theme.space.xs,
  },
  option: {
    paddingVertical: 4,
    paddingHorizontal: 2,
    borderBottomWidth: 2,
    borderBottomColor: "transparent",
  },
  optionActive: {
    borderBottomColor: theme.colors.ink,
  },
  pressed: {
    backgroundColor: theme.colors.hover,
  },
  label: {
    ...theme.text.body,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  labelActive: {
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink,
  },
  small: {
    ...theme.text.fine,
  },
  separator: {
    ...theme.text.body,
    fontFamily: theme.fonts.sans,
    color: theme.colors.rule,
  },
}));
