import React, { createContext, useContext, useEffect, useRef, useState } from "react";

import type { AssetType } from "@/api/types";
import { createAsyncStorageAdapter } from "@/storage/storage";
import { createOrderedWriter, parseWatchlist, type WatchlistItem } from "@/storage/watchlist";
export type { WatchlistItem } from "@/storage/watchlist";

interface WatchlistContextValue {
  items: WatchlistItem[];
  ready: boolean;
  error: string | null;
  isSaved: (symbol: string, assetType?: AssetType) => boolean;
  toggle: (item: Omit<WatchlistItem, "addedAt">) => Promise<void>;
  remove: (symbol: string, assetType?: AssetType) => Promise<void>;
  clear: () => Promise<void>;
}

const key = "watchlist-v1";
const storage = createAsyncStorageAdapter();
const write = createOrderedWriter(value => storage.setItem(key, value));
const WatchlistContext = createContext<WatchlistContextValue | null>(null);

export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currentItems = useRef<WatchlistItem[]>([]);

  useEffect(() => {
    let active = true;
    storage
      .getItem(key)
      .then((value) => {
        if (!active) return;
        currentItems.current = parseWatchlist(value);
        setItems(currentItems.current);
      })
      .catch(() => { if (active) setError("Saved watchlist could not be loaded."); })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);

  const persist = async (nextItems: WatchlistItem[]) => {
    if (!ready) return;
    if (nextItems.length > 100) { setError("Watchlist is full. Remove an asset first."); return; }
    currentItems.current = nextItems;
    setItems(nextItems);
    try {
      await write(JSON.stringify(nextItems));
      setError(null);
    } catch {
      setError("Watchlist changes are available for this session, but could not be saved.");
    }
  };

  const value: WatchlistContextValue = {
    items,
    ready,
    error,
    isSaved: (symbol, assetType) => items.some((item) => item.symbol === symbol && (!assetType || item.assetType === assetType)),
    toggle: async (item) => {
      const latest = currentItems.current;
      const exists = latest.some((entry) => entry.symbol === item.symbol && entry.assetType === item.assetType);
      if (exists) {
        await persist(latest.filter((entry) => entry.symbol !== item.symbol || entry.assetType !== item.assetType));
        return;
      }
      await persist([
        ...latest,
        {
          ...item,
          addedAt: new Date().toISOString(),
        },
      ]);
    },
    remove: async (symbol, assetType) => {
      await persist(currentItems.current.filter((entry) => entry.symbol !== symbol || (assetType && entry.assetType !== assetType)));
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
