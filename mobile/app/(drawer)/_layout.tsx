import { useState, useCallback, useEffect, useRef } from "react";
import { View, Platform, AppState, AppStateStatus, BackHandler } from "react-native";
import { Tabs, useFocusEffect, router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import { getUnreadCount, registerDevice } from "../../api/notifications";
import { getUnreadSummary } from "../../api/conversations";
import { on } from "../../utils/eventBus";
import { COLORS, FONTS } from "../../constants/theme";
import { getFinancialSummary } from "../../api/activity";
import LockScreen from "../../components/app/LockScreen";
import { consumeLockSuppression } from "../../utils/lockSuppress";

/** Sessions idle for longer than this are locked on return. */
const LOCK_AFTER_MS = 10_000; // 10 seconds

// expo-notifications is NOT imported at the top level — doing so causes
// DevicePushTokenAutoRegistration.fx.js to run as a module-load side-effect,
// which crashes in Expo Go (push removed in SDK 53). We require() it lazily
// inside the functions that use it, only when not in Expo Go.
const IS_EXPO_GO = Constants.appOwnership === "expo";

// Remote push needs Firebase/FCM on Android: a google-services.json plus the
// expo-notifications config plugin. Until that's wired up, calling
// getDevicePushTokenAsync() hits an uninitialised FirebaseApp and crashes the
// release build *natively* — which JS try/catch cannot stop. So gate the whole
// push subsystem behind an explicit flag that stays off until Firebase exists.
// Flip EXPO_PUBLIC_PUSH_ENABLED=true (and ship google-services.json) to enable.
const PUSH_ENABLED = process.env.EXPO_PUBLIC_PUSH_ENABLED === "true";

/**
 * Request notification permission, fetch the native FCM/APNS device token,
 * and register it with the WEPL backend so the server can send real-time
 * payment and governance alerts directly via Firebase (Issue 19).
 *
 * Uses getDevicePushTokenAsync() to get the raw platform token (FCM on Android,
 * APNS on iOS) rather than the Expo push token, which would route through
 * Expo's servers and requires a managed Expo project ID.
 *
 * Fails silently — push is an enhancement, not a core requirement.
 */
async function registerPushToken() {
  // Expo Go does not support device push tokens since SDK 53, and without
  // Firebase configured the native FCM call crashes the build — skip both.
  // The module is never required here so its side-effects never run.
  if (IS_EXPO_GO || !PUSH_ENABLED) return;

  try {
    // Lazy require — only loads the module in real builds, never in Expo Go.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Notifications = require("expo-notifications");

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "WEPL Notifications",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#1A5C38",
      });
    }

    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;
    if (existing !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== "granted") return;

    const tokenData = await Notifications.getDevicePushTokenAsync();
    const platform  = Platform.OS === "ios" ? "ios" : "android";
    await registerDevice(tokenData.data as string, platform);
  } catch {
    // Permission denied or network error — push remains unavailable.
  }
}

function TabIcon({ name, focused, dot }: { name: any; focused: boolean; dot?: boolean }) {
  return (
    <View>
      <Ionicons
        name={focused ? name : `${name}-outline`}
        size={23}
        color={focused ? COLORS.primary : COLORS.textMuted}
      />
      {dot && (
        <View style={{
          position: "absolute", top: -1, right: -3,
          width: 8, height: 8, borderRadius: 4,
          backgroundColor: COLORS.success,
          borderWidth: 1.5, borderColor: COLORS.white,
        }} />
      )}
    </View>
  );
}

function NotifIcon({ focused, unread }: { focused: boolean; unread: boolean }) {
  return (
    <View>
      <Ionicons
        name={focused ? "notifications" : "notifications-outline"}
        size={23}
        color={focused ? COLORS.primary : COLORS.textMuted}
      />
      {unread && (
        <View style={{
          position: "absolute", top: -1, right: -3,
          width: 8, height: 8, borderRadius: 4,
          backgroundColor: COLORS.success,
          borderWidth: 1.5, borderColor: COLORS.white,
        }} />
      )}
    </View>
  );
}

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const [unread,       setUnread]       = useState(false);
  const [unreadChats,  setUnreadChats]  = useState(false);
  const [isVerified,   setIsVerified]   = useState<boolean | null>(null); // null = loading

  // ── Session lock ─────────────────────────────────────────────────────────
  const [locked,          setLocked]          = useState(false);
  const backgroundAt      = useRef<number | null>(null);
  const appStateRef       = useRef<AppStateStatus>(AppState.currentState);

  useEffect(() => {
    // On startup: if biometric is saved as enabled but this device has no
    // enrolled biometrics (e.g. new device or wiped enrollment), silently
    // reset the setting so the user is not stuck in a broken state.
    (async () => {
      const bioEnabled = (await AsyncStorage.getItem("biometric_enabled")) === "true";
      if (!bioEnabled) return;
      try {
        const LocalAuth  = await import("expo-local-authentication");
        const hasHardware = await LocalAuth.hasHardwareAsync();
        const isEnrolled  = await LocalAuth.isEnrolledAsync();
        if (!hasHardware || !isEnrolled) {
          await AsyncStorage.setItem("biometric_enabled", "false");
        }
      } catch {}
    })();

    const subscription = AppState.addEventListener(
      "change",
      async (nextState: AppStateStatus) => {
        const prev = appStateRef.current;
        appStateRef.current = nextState;

        if (nextState === "background" || nextState === "inactive") {
          backgroundAt.current = Date.now();
        } else if (nextState === "active" && prev !== "active") {
          const elapsed = backgroundAt.current
            ? Date.now() - backgroundAt.current
            : 0;
          backgroundAt.current = null;

          // Skip the lock if a picker / share sheet / camera caused this
          // background trip — consumeLockSuppression() returns true once
          // then resets so only a single foreground event is exempted.
          if (consumeLockSuppression()) return;

          if (elapsed >= LOCK_AFTER_MS) {
            setLocked(true);
          }
        }
      },
    );

    return () => subscription.remove();
  }, []);

  // ── Hardware back-button guard (Android) ────────────────────────────────
  // Without this, pressing the device back button pops through the navigation
  // stack and can land unverified users on the Communities tab or the welcome
  // screen.  We intercept every back press inside the authenticated shell:
  //   • Unverified: always go to Profile (the only tab they should see)
  //   • Verified:   default behaviour (Expo Router handles it)
  useEffect(() => {
    if (Platform.OS !== "android") return;

    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (isVerified === false) {
        // Redirect to profile instead of popping the navigation stack.
        router.replace("/(drawer)/profile");
        return true; // event consumed — prevents default back
      }
      return false; // let Expo Router handle it normally for verified users
    });

    return () => sub.remove();
  }, [isVerified]);

  // Register FCM token once when the authenticated shell mounts.
  useEffect(() => { registerPushToken(); }, []);

  // Fetch KYC status once on mount to decide which tabs to show.
  useEffect(() => {
    getFinancialSummary()
      .then(s => setIsVerified(s?.kyc_status === "approved"))
      .catch(() => setIsVerified(false));
  }, []);

  // Show foreground notifications as banners and update the unread badge.
  // Only runs in real builds with push enabled — Expo Go and Firebase-less
  // builds skip this so the notifications native module is never touched.
  useEffect(() => {
    if (IS_EXPO_GO || !PUSH_ENABLED) return;

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Notifications = require("expo-notifications");

    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge:  false,
      }),
    });

    const sub = Notifications.addNotificationReceivedListener(() => {
      getUnreadCount().then((n: number) => setUnread(n > 0)).catch(() => {});
    });

    return () => sub.remove();
  }, []);

  useFocusEffect(useCallback(() => {
    getUnreadCount().then((n) => setUnread(n > 0)).catch(() => {});
    getUnreadSummary().then((s) => setUnreadChats(s.total > 0)).catch(() => {});
    const interval = setInterval(() => {
      getUnreadSummary().then((s) => setUnreadChats(s.total > 0)).catch(() => {});
    }, 15000);
    return () => clearInterval(interval);
  }, []));

  useEffect(() => {
    return on('newMessage', () => {
      getUnreadSummary().then(s => setUnreadChats(s.total > 0)).catch(() => {});
    });
  }, []);

  return (
    <>
    {locked && <LockScreen onUnlock={() => setLocked(false)} />}
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: COLORS.white,
          borderTopColor: COLORS.divider,
          borderTopWidth: 1,
          elevation: 0,
          shadowOpacity: 0,
          height: 54 + insets.bottom,
          paddingBottom: insets.bottom + 3,
          paddingTop: 6,
        },
        tabBarActiveTintColor: COLORS.primary,
        tabBarInactiveTintColor: COLORS.textMuted,
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: "500",
          marginTop: 2,
        },
      }}
    >
      {/* Communities — only verified users see this tab */}
      <Tabs.Screen
        name="index"
        listeners={{ tabPress: () => setUnreadChats(false) }}
        options={{
          title: "Communities",
          href: isVerified === true ? undefined : null,
          tabBarIcon: ({ focused }) => <TabIcon name="people" focused={focused} dot={unreadChats} />,
        }}
      />

      {/* Discover — only verified users see this tab */}
      <Tabs.Screen
        name="discover"
        options={{
          title: "Discover",
          href: isVerified === true ? undefined : null,
          tabBarIcon: ({ focused }) => <TabIcon name="compass" focused={focused} />,
        }}
      />

      {/* Hidden utility screens — never in tab bar */}
      <Tabs.Screen name="contributions" options={{ href: null }} />
      <Tabs.Screen name="invite"        options={{ href: null }} />
      <Tabs.Screen name="reports"       options={{ href: null }} />
      <Tabs.Screen name="settings"      options={{ href: null }} />
      <Tabs.Screen name="transactions"  options={{ href: null }} />

      {/* Alerts — only verified users see this tab */}
      <Tabs.Screen
        name="notifications"
        listeners={{ tabPress: () => setUnread(false) }}
        options={{
          title: "Alerts",
          href: isVerified === true ? undefined : null,
          tabBarIcon: ({ focused }) => <NotifIcon focused={focused} unread={unread} />,
        }}
      />

      {/* Profile — always visible */}
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ focused }) => <TabIcon name="person" focused={focused} />,
        }}
      />
    </Tabs>
    </>
  );
}
