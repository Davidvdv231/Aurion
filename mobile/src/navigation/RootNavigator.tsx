import React from "react";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { HomeScreen } from "@/screens/HomeScreen";
<<<<<<< claude/zealous-kapitsa
import { WelcomeScreen } from "@/screens/WelcomeScreen";
=======
>>>>>>> main
import { AssetDetailScreen } from "@/screens/AssetDetailScreen";
import { WatchlistScreen } from "@/screens/WatchlistScreen";
import type { MainTabParamList, RootStackParamList } from "@/navigation/types";
import { theme } from "@/theme/theme";

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tabs = createBottomTabNavigator<MainTabParamList>();

function MainTabs() {
  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.colors.accent,
        tabBarInactiveTintColor: theme.colors.textMuted,
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.border,
        },
      }}
    >
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Watchlist" component={WatchlistScreen} />
    </Tabs.Navigator>
  );
}

export function RootNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
<<<<<<< claude/zealous-kapitsa
      {status === "onboarding" ? (
        <Stack.Screen name="Welcome" component={WelcomeScreen} />
      ) : (
        <>
          <Stack.Screen name="Main" component={MainTabs} />
          <Stack.Screen name="AssetDetail" component={AssetDetailScreen} />
        </>
      )}
=======
      <Stack.Screen name="Main" component={MainTabs} />
      <Stack.Screen name="AssetDetail" component={AssetDetailScreen} />
>>>>>>> main
    </Stack.Navigator>
  );
}
