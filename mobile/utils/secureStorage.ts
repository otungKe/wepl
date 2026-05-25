/**
 * Secure storage wrapper.
 *
 * JWT tokens and phone numbers are stored in expo-secure-store, which uses
 * Android Keystore on Android and iOS Keychain on iOS. Plain AsyncStorage is
 * plaintext on-disk and readable by any process with ADB access on rooted devices.
 *
 * Non-sensitive keys (e.g. UI timestamps) should continue to use AsyncStorage directly.
 */
import * as SecureStore from "expo-secure-store";
import AsyncStorage from "@react-native-async-storage/async-storage";

// Keys that must be stored securely
const SECURE_KEYS = new Set(["access", "refresh", "phone", "name"]);

export async function getItem(key: string): Promise<string | null> {
  if (SECURE_KEYS.has(key)) {
    return SecureStore.getItemAsync(key);
  }
  return AsyncStorage.getItem(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  if (SECURE_KEYS.has(key)) {
    await SecureStore.setItemAsync(key, value);
  } else {
    await AsyncStorage.setItem(key, value);
  }
}

export async function removeItem(key: string): Promise<void> {
  if (SECURE_KEYS.has(key)) {
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
