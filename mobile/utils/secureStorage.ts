/**
 * Secure storage wrapper.
 *
 * JWT tokens and phone numbers are stored in expo-secure-store on native
 * (Android Keystore / iOS Keychain). On web, expo-secure-store is unavailable
 * so all keys fall back to AsyncStorage.
 *
 * Non-sensitive keys (e.g. UI timestamps) should continue to use AsyncStorage directly.
 */
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import AsyncStorage from "@react-native-async-storage/async-storage";

// expo-secure-store only works on native (Android / iOS)
const isNative = Platform.OS !== "web";

// Keys that must be stored securely on native
const SECURE_KEYS = new Set(["access", "refresh", "phone", "name"]);

export async function getItem(key: string): Promise<string | null> {
  if (isNative && SECURE_KEYS.has(key)) {
    return SecureStore.getItemAsync(key);
  }
  return AsyncStorage.getItem(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  if (isNative && SECURE_KEYS.has(key)) {
    await SecureStore.setItemAsync(key, value);
  } else {
    await AsyncStorage.setItem(key, value);
  }
}

export async function removeItem(key: string): Promise<void> {
  if (isNative && SECURE_KEYS.has(key)) {
    await SecureStore.deleteItemAsync(key);
  } else {
    await AsyncStorage.removeItem(key);
  }
}

/** Remove multiple keys — handles mixed secure/insecure keys. */
export async function multiRemove(keys: string[]): Promise<void> {
  await Promise.all(keys.map(removeItem));
}

/** Get multiple values — returns same shape as AsyncStorage.multiGet. */
export async function multiGet(
  keys: string[]
): Promise<[string, string | null][]> {
  const values = await Promise.all(keys.map((k) => getItem(k)));
  return keys.map((k, i) => [k, values[i]]);
}
