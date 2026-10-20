import type { AssetType } from "@/api/types";

export interface WatchlistItem {
  symbol: string;
  name: string;
  assetType: AssetType;
  addedAt: string;
}

export function parseWatchlist(raw: string | null): WatchlistItem[] {
  const parsed: unknown = raw ? JSON.parse(raw) : [];
  if (!Array.isArray(parsed)) return [];
  const seen = new Set<string>();
  return parsed.filter((item): item is WatchlistItem => {
    if (!item || typeof item.symbol !== "string" || !/^[A-Z0-9^][A-Z0-9.^=_-]{0,19}$/.test(item.symbol)
        || typeof item.name !== "string" || !["stock", "crypto"].includes(item.assetType)
        || typeof item.addedAt !== "string" || !Number.isFinite(Date.parse(item.addedAt))) return false;
    const key = `${item.assetType}:${item.symbol}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 100);
}

export function createOrderedWriter(write: (value: string) => Promise<void>) {
  let tail = Promise.resolve();
  return (value: string): Promise<void> => {
    const result = tail.then(() => write(value));
    tail = result.catch(() => {});
    return result;
  };
}
