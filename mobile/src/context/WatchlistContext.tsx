import React, { createContext, useContext, useEffect, useState } from "react";

import type { AssetType } from "@/api/types";
import { createAsyncStorageAdapter } from "@/storage/storage";

export interface WatchlistItem {
  symbol: string;
  name: string;
  assetType: AssetType;
  addedAt: string;
}

interface WatchlistContextValue {
  items: WatchlistItem[];
  ready: boolean;
  isSaved: (symbol: string) => boolean;
  toggle: (item: Omit<WatchlistItem, "addedAt">) => Promise<void>;
  remove: (symbol: string) => Promise<void>;
  clear: () => Promise<void>;
}

const key = "watchlist-v1";
const storage = createAsyncStorageAdapter();
const WatchlistContext = createContext<WatchlistContextValue | null>(null);

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    storage
      .getItem(key)
      .then((value) => {
        if (!value) {
          setReady(true);
          return;
        }
        setItems(JSON.parse(value) as WatchlistItem[]);
        setReady(true);
      })
      .catch(() => setReady(true));
  }, []);

  const persist = async (nextItems: WatchlistItem[]) => {
    setItems(nextItems);
    await storage.setItem(key, JSON.stringify(nextItems));
  };

  const value: WatchlistContextValue = {
    items,
    ready,
    isSaved: (symbol: string) => items.some((item) => item.symbol === symbol),
    toggle: async (item) => {
      const exists = items.some((entry) => entry.symbol === item.symbol);
      if (exists) {
        await persist(items.filter((entry) => entry.symbol !== item.symbol));
        return;
      }
      await persist([
        ...items,
        {
          ...item,
          addedAt: new Date().toISOString(),
        },
      ]);
    },
    remove: async (symbol) => {
      await persist(items.filter((entry) => entry.symbol !== symbol));
    },
    clear: async () => {
      await persist([]);
    },
  };

  return <WatchlistContext.Provider value={value}>{children}</WatchlistContext.Provider>;
}

export function useWatchlist() {
  const value = useContext(WatchlistContext);
  if (!value) {
    throw new Error("useWatchlist must be used within WatchlistProvider");
  }
  return value;
}
