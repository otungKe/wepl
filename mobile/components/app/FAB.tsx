import { TouchableOpacity, StyleSheet, View, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { COLORS, RADIUS } from "../../constants/theme";

type IconName = keyof typeof Ionicons.glyphMap;

const ICON_MAP: Record<string, IconName> = {
  add:   "add",
  plus:  "add",
  check: "checkmark",
  arrow: "arrow-forward",
  chat:  "chatbubble",
};

type Props = {
  icon?: keyof typeof ICON_MAP;
  onPress: () => void;
  disabled?: boolean;
  /** Show a spinner in-place instead of the icon while an async action is in flight */
  loading?: boolean;
  /** Extra bottom offset in px — pass the tab bar height when inside a tab screen */
  tabBarOffset?: number;
};

export default function FAB({ icon = "add", onPress, disabled, loading = false, tabBarOffset = 0 }: Props) {
  const { bottom } = useSafeAreaInsets();

  return (
    <View style={[styles.wrap, { bottom: 20 + bottom + tabBarOffset }]} pointerEvents="box-none">
      <TouchableOpacity
        style={[styles.btn, (disabled || loading) && styles.disabled]}
        onPress={onPress}
        disabled={disabled || loading}
        activeOpacity={0.85}
        accessibilityRole="button"
      >
        {loading
          ? <ActivityIndicator color={COLORS.white} size="small" />
          : <Ionicons name={ICON_MAP[icon] ?? "add"} size={28} color={COLORS.white} />
        }
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    right: 20,
  },
  btn: {
    width: 60,
    height: 60,
    borderRadius: RADIUS.full,
    backgroundColor: COLORS.primary,
    justifyContent: "center",
    alignItems: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.22,
    shadowRadius: 8,
    elevation: 6,
  },
  disabled: { backgroundColor: COLORS.primaryLight, opacity: 0.7 },
});
