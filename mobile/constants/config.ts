import { Platform } from 'react-native';

// In development: override with your local machine IP.
// In production: set EXPO_PUBLIC_API_URL in your build environment.
const DEV_HOST = Platform.OS === 'web' ? 'localhost' : '10.44.160.140';

const IS_PRODUCTION = process.env.EXPO_PUBLIC_ENV === 'production';

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL
  ?? `http://${DEV_HOST}:8000/api/`;

// Always use wss:// in production; ws:// is only acceptable in local dev.
export const WS_BASE_URL = process.env.EXPO_PUBLIC_WS_URL
  ?? (IS_PRODUCTION ? `wss://${DEV_HOST}:8000` : `ws://${DEV_HOST}:8000`);

export const SENTRY_DSN = process.env.EXPO_PUBLIC_SENTRY_DSN ?? '';
