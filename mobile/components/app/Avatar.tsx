import { View, Text, Image, StyleSheet } from "react-native";
import { RADIUS, avatarColorFor, initialsFor } from "../../constants/theme";

type Props = {
  name: string;
  uri?: string | null;
  size?: number;
};

export default function Avatar({ name, uri, size = 46 }: Props) {
  const palette = avatarColorFor(name || "?");
  const fontSize = Math.max(12, size * 0.4);

  if (uri) {
    return <Image source={{ uri }} style={{ width: size, height: size, borderRadius: RADIUS.full }} />;
  }

  return (
    <View
      style={[
        styles.box,
        { width: size, height: size, borderRadius: RADIUS.full, backgroundColor: palette.bg },
      ]}
    >
      <Text style={{ fontSize, fontWeight: "bold", color: palette.text }}>
        {initialsFor(name)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { justifyContent: "center", alignItems: "center", overflow: "hidden" },
});
