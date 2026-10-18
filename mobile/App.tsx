import React, { useMemo } from "react";
import { View } from "react-native";
import { DarkTheme, DefaultTheme, NavigationContainer, type Theme as NavigationTheme } from "@react-navigation/native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import { IBMPlexMono_400Regular } from "@expo-google-fonts/ibm-plex-mono/400Regular";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono/500Medium";
import { IBMPlexSans_400Regular } from "@expo-google-fonts/ibm-plex-sans/400Regular";
import { IBMPlexSans_500Medium } from "@expo-google-fonts/ibm-plex-sans/500Medium";
import { IBMPlexSans_600SemiBold } from "@expo-google-fonts/ibm-plex-sans/600SemiBold";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AuthProvider } from "@/context/AuthContext";
import { WatchlistProvider } from "@/context/WatchlistContext";
import { RootNavigator } from "@/navigation/RootNavigator";
import { useTheme } from "@/theme/theme";

export default function App() {
  const theme = useTheme();
  // Only the five cuts the UI uses are bundled; a failed load falls back to the system font.
  const [fontsLoaded, fontError] = useFonts({
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexMono_400Regular,
    IBMPlexMono_500Medium,
  });

  const navigationTheme = useMemo<NavigationTheme>(() => {
    const base = theme.scheme === "dark" ? DarkTheme : DefaultTheme;
    return {
      ...base,
      colors: {
        ...base.colors,
        background: theme.colors.surface,
        card: theme.colors.surface,
        text: theme.colors.ink,
        border: theme.colors.grid,
        primary: theme.colors.ink,
        notification: theme.colors.accent,
      },
      fonts: {
        regular: { fontFamily: theme.fonts.sans, fontWeight: "400" },
        medium: { fontFamily: theme.fonts.sansMedium, fontWeight: "500" },
        bold: { fontFamily: theme.fonts.sansSemiBold, fontWeight: "600" },
        heavy: { fontFamily: theme.fonts.sansSemiBold, fontWeight: "600" },
      },
    };
  }, [theme]);

  if (!fontsLoaded && !fontError) {
    return <View style={{ flex: 1, backgroundColor: theme.colors.surface }} />;
  }

  return (
    <ErrorBoundary>
      <SafeAreaProvider>
        <AuthProvider>
          <WatchlistProvider>
            <NavigationContainer theme={navigationTheme}>
              <StatusBar style={theme.scheme === "dark" ? "light" : "dark"} />
              <RootNavigator />
            </NavigationContainer>
          </WatchlistProvider>
        </AuthProvider>
      </SafeAreaProvider>
    </ErrorBoundary>
  );
}
