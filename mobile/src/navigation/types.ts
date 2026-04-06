import type { AssetType, ForecastEngine } from "@/api/types";

export type RootStackParamList = {
  Welcome: undefined;
  Main: undefined;
  AssetDetail: { symbol: string; assetType: AssetType; name?: string; engine?: ForecastEngine };
};

export type MainTabParamList = {
  Home: undefined;
  Watchlist: undefined;
};
