import { useState, useCallback, useEffect } from "react";
import { View } from "react-native";
import { Tabs, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getUnreadCount } from "../../api/notifications";
import { getUnreadSummary } from "../../api/conversations";
import { on } from "../../utils/eventBus";
import { COLORS, FONTS } from "../../constants/theme";

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
  const [unread, setUnread] = useState(false);
  const [unreadChats, setUnreadChats] = useState(false);

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
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: COLORS.white,
          borderTopColor: COLORS.divider,
          borderTopWidth: 1,
          elevation: 0,
          shadowOpacity: 0,
          height: 56 + insets.bottom,
          paddingBottom: insets.bottom + 4,
          paddingTop: 6,
        },
        tabBarActiveTintColor: COLORS.primary,
        tabBarInactiveTintColor: COLORS.textMuted,
        tabBarLabelStyle: {
          fontSize: FONTS.xs,
          fontWeight: "600",
          marginTop: 2,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        listeners={{ tabPress: () => setUnreadChats(false) }}
        options={{
          title: "Communities",
          tabBarIcon: ({ focused }) => <TabIcon name="people" focused={focused} dot={unreadChats} />,
        }}
      />
      <Tabs.Screen
        name="contributions"
        options={{
          title: "Contributions",
          tabBarIcon: ({ focused }) => <TabIcon name="wallet" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="notifications"
        listeners={{ tabPress: () => setUnread(false) }}
        options={{
          title: "Alerts",
          tabBarIcon: ({ focused }) => <NotifIcon focused={focused} unread={unread} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ focused }) => <TabIcon name="person" focused={focused} />,
        }}
      />
      {/* hidden from tab bar */}
      <Tabs.Screen name="reports"      options={{ href: null }} />
      <Tabs.Screen name="transactions" options={{ href: null }} />
      <Tabs.Screen name="invite"       options={{ href: null }} />
      <Tabs.Screen name="settings"     options={{ href: null }} />
    </Tabs>
  );
}
