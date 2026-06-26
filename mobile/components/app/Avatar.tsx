import { View, Text, Image, StyleSheet } from "react-native";
import { RADIUS, avatarColorFor, initialsFor } from "../../constants/theme";

type Props = {
  name: string;
  uri?: string | null;
  size?: number;
  /** null = status hidden (opted out), true = online, false = offline */
  isOnline?: boolean | null;
};

export default function Avatar({ name, uri, size = 46, isOnline }: Props) {
  const palette  = avatarColorFor(name || "?");
  const fontSize = Math.max(12, size * 0.4);
  const dotSize  = Math.max(8, size * 0.22);

  const avatarEl = uri
    ? <Image source={{ uri }} style={{ width: size, height: size, borderRadius: RADIUS.full }} />
    : (
      <View style={[styles.box, { width: size, height: size, borderRadius: RADIUS.full, backgroundColor: palette.bg }]}>
        <Text style={{ fontSize, fontWeight: "700", color: palette.text }}>
          {initialsFor(name)}
        </Text>
      </View>
    );

  // Only show the dot if is_online is explicitly true or false (not null = opted out)
  if (isOnline === null || isOnline === undefined) {
    return avatarEl;
  }

  return (
    <View style={{ width: size, height: size }}>
      {avatarEl}
      <View
        style={[
          styles.dot,
          {
            width:  dotSize,
            height: dotSize,
            borderRadius: dotSize / 2,
            bottom: 0,
            right:  0,
            backgroundColor: isOnline ? "#22C55E" : "#94A3B8",
            borderWidth: Math.max(1.5, dotSize * 0.2),
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  box: { justifyContent: "center", alignItems: "center", overflow: "hidden" },
  dot: {
    position: "absolute",
    borderColor: "#fff",
  },
});
