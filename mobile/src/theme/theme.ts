// Aurion reads like a research note: warm grays, hairline rules, and one accent kept for the forecast.
// The palette mirrors frontend/styles.css so the web app and the mobile app look like one product.
import { Platform, StyleSheet, useColorScheme } from "react-native";

export type Scheme = "light" | "dark";

const light = {
  surface: "#fcfcfb",
  hover: "#f0efec",
  ink: "#0b0b0b",
  ink2: "#52514e",
  ink3: "#6f6d68",
  grid: "#e1e0d9",
  rule: "#c3c2b7",
  up: "#006300",
  down: "#d03b3b",
  warning: "#fab219",
  warningWash: "rgba(250, 178, 25, 0.12)",
  errorWash: "rgba(208, 59, 59, 0.08)",
  buttonBg: "#0b0b0b",
  buttonFg: "#fcfcfb",
  accent: "#eb6834",
  chartHistory: "#6f6d68",
  chartForecast: "#eb6834",
  chartBand: "rgba(235, 104, 52, 0.1)",
};

const dark: typeof light = {
  surface: "#1a1a19",
  hover: "#242422",
  ink: "#f0efec",
  ink2: "#c3c2b7",
  ink3: "#8f8d86",
  grid: "#2c2c2a",
  rule: "#383835",
  up: "#0ca30c",
  down: "#e66767",
  warning: "#fab219",
  warningWash: "rgba(250, 178, 25, 0.1)",
  errorWash: "rgba(230, 103, 103, 0.1)",
  buttonBg: "#f0efec",
  buttonFg: "#1a1a19",
  accent: "#d95926",
  chartHistory: "#8f8d86",
  chartForecast: "#d95926",
  chartBand: "rgba(217, 89, 38, 0.12)",
};

export type ThemeColors = typeof light;

// Each weight is its own family so Android never synthesizes bold on top of a custom font.
// The web build gets a system fallback in case the font files fail to load.
function family(name: string, fallback: string) {
  return Platform.OS === "web" ? `${name}, ${fallback}` : name;
}

const SANS_FALLBACK = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO_FALLBACK = 'ui-monospace, "SFMono-Regular", Menlo, monospace';

export const fonts = {
  sans: family("IBMPlexSans_400Regular", SANS_FALLBACK),
  sansMedium: family("IBMPlexSans_500Medium", SANS_FALLBACK),
  sansSemiBold: family("IBMPlexSans_600SemiBold", SANS_FALLBACK),
  mono: family("IBMPlexMono_400Regular", MONO_FALLBACK),
  monoMedium: family("IBMPlexMono_500Medium", MONO_FALLBACK),
};

const shared = {
  fonts,
  space: { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 40 },
  gutter: 20,
  radius: 2,
  hairline: StyleSheet.hairlineWidth,
  text: {
    fine: { fontSize: 13, lineHeight: 18 },
    small: { fontSize: 14, lineHeight: 20 },
    body: { fontSize: 16, lineHeight: 24 },
    lead: { fontSize: 18, lineHeight: 26 },
  },
};

export const themes = {
  light: { scheme: "light" as Scheme, colors: light, ...shared },
  dark: { scheme: "dark" as Scheme, colors: dark, ...shared },
};

export type Theme = typeof themes.light;

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? themes.dark : themes.light;
}

type NamedStyles = Parameters<typeof StyleSheet.create>[0];

// Styles are built once per color scheme and cached, so components keep the StyleSheet pattern.
export function makeStyles<S extends NamedStyles>(factory: (theme: Theme) => S) {
  const cache: Partial<Record<Scheme, Readonly<S>>> = {};
  return function useStyles(): Readonly<S> {
    const theme = useTheme();
    return (cache[theme.scheme] ??= StyleSheet.create(factory(theme)));
  };
}
