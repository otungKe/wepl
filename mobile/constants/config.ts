import Constants from 'expo-constants';
import { Platform } from 'react-native';

// Production builds (EAS) inject EXPO_PUBLIC_API_URL / EXPO_PUBLIC_WS_URL via
// the profile's env block in eas.json, so the branches below are dev-only.
const IS_PRODUCTION = process.env.EXPO_PUBLIC_ENV === 'production';

// In dev, derive the host from the Metro/Expo host the client is already talking
// to (hostUri looks like "192.168.1.5:8081"), so a physical device or emulator
// reaches the dev machine without a hardcoded IP. Web falls back to localhost.
function devHost(): string {
  if (Platform.OS === 'web') return 'localhost';
  const hostUri =
    Constants.expoConfig?.hostUri ?? (Constants as any).expoGoConfig?.debuggerHost;
  return hostUri?.split(':')[0] ?? 'localhost';
}

// axios baseURL includes the trailing /api/ — keep it on any override too.
export const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ?? `http://${devHost()}:8000/api/`;

// Always wss:// in production; ws:// is only acceptable in local dev.
export const WS_BASE_URL =
  process.env.EXPO_PUBLIC_WS_URL ??
  (IS_PRODUCTION ? `wss://${devHost()}:8000` : `ws://${devHost()}:8000`);

export const SENTRY_DSN = process.env.EXPO_PUBLIC_SENTRY_DSN ?? '';
