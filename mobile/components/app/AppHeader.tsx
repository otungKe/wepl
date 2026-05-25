import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS } from "../../constants/theme";

type Props = {
  title: string;
  variant?: "green" | "light";
  leading?: "back" | "none";
  onBack?: () => void;
  rightIcon?: "search" | "more" | "bell" | null;
  onRightPress?: () => void;
  rightExtra?: React.ReactNode;
};

export default function AppHeader({
  title,
  variant = "green",
  leading = "none",
  onBack,
  rightIcon = null,
  onRightPress,
  rightExtra,
}: Props) {
  const green = variant === "green";

  const handleLeading = () => {
    if (leading === "back") {
      if (onBack) onBack();
      else router.back();
    }
  };

  return (
    <View style={[styles.bar, green ? styles.barGreen : styles.barLight]}>
      {leading === "back" ? (
        <TouchableOpacity style={styles.iconBtn} onPress={handleLeading}>
          <Ionicons
            name="chevron-back"
            size={22}
            color={green ? COLORS.white : COLORS.text}
          />
        </TouchableOpacity>
      ) : (
        <View style={styles.iconBtn} />
      )}

      <Text
        style={[styles.title, green ? styles.titleWhite : styles.titleDark]}
        numberOfLines={1}
      >
        {title}
      </Text>

      <View style={styles.rightCluster}>
        {rightExtra}
        {rightIcon ? (
          <TouchableOpacity style={styles.iconBtn} onPress={onRightPress}>
            <Ionicons
              name={
                rightIcon === "bell"
                  ? "notifications-outline"
                  : rightIcon === "search"
                  ? "search-outline"
                  : "ellipsis-vertical"
              }
              size={20}
              color={green ? COLORS.white : COLORS.text}
            />
          </TouchableOpacity>
        ) : (
          <View style={styles.iconBtn} />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "center",
    paddingTop: 8,
    paddingBottom: 12,
    paddingHorizontal: 4,
  },
  barGreen: { backgroundColor: COLORS.primary },
  barLight: {
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },

  iconBtn: { width: 44, height: 44, justifyContent: "center", alignItems: "center" },

  title: {
    flex: 1,
    fontSize: FONTS.lg,
    fontWeight: "700",
    letterSpacing: -0.2,
    marginLeft: 2,
  },
  titleWhite: { color: COLORS.white },
  titleDark:  { color: COLORS.text },

  rightCluster: { flexDirection: "row", alignItems: "center" },
});
