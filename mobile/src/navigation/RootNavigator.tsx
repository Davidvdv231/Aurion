import React from "react";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { HomeScreen } from "@/screens/HomeScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { AssetDetailScreen } from "@/screens/AssetDetailScreen";
import { WatchlistScreen } from "@/screens/WatchlistScreen";
import { SplashScreen } from "@/screens/SplashScreen";
import { useAuth } from "@/context/AuthContext";
import type { MainTabParamList, RootStackParamList } from "@/navigation/types";
import { TabBar } from "@/components/TabBar";

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tabs = createBottomTabNavigator<MainTabParamList>();

function MainTabs() {
  return (
    <Tabs.Navigator screenOptions={{ headerShown: false }} tabBar={(props) => <TabBar {...props} />}>
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Watchlist" component={WatchlistScreen} />
    </Tabs.Navigator>
  );
}

export function RootNavigator() {
  const { status } = useAuth();

  if (status === "loading") {
    return <SplashScreen />;
  }

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {status === "onboarding" ? (
        <Stack.Screen name="Welcome" component={WelcomeScreen} />
      ) : (
        <>
          <Stack.Screen name="Main" component={MainTabs} />
          <Stack.Screen name="AssetDetail" component={AssetDetailScreen} />
        </>
      )}
    </Stack.Navigator>
  );
}
