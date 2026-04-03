import type { AssetType } from "@/api/types";

export type RootStackParamList = {
  Main: undefined;
  AssetDetail: { symbol: string; assetType: AssetType; name?: string };
};

export type MainTabParamList = {
  Home: undefined;
  Watchlist: undefined;
};
