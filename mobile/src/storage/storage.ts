import AsyncStorage from "@react-native-async-storage/async-storage";

export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export function createAsyncStorageAdapter(
  storage: Pick<KeyValueStore, "getItem" | "setItem" | "removeItem"> = AsyncStorage,
) {
  return {
    getItem: (key: string) => storage.getItem(key),
    setItem: (key: string, value: string) => storage.setItem(key, value),
    removeItem: (key: string) => storage.removeItem(key),
  };
}

