import { View, Text, StyleSheet } from "react-native";
import { useColors } from "@/hooks/use-colors";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";

export function EmptyChat() {
  const colors = useColors();

  return (
    <View style={styles.container}>
      <View style={[styles.iconCircle, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <MaterialIcons name="chat-bubble-outline" size={40} color={colors.primary} />
      </View>
      <Text style={[styles.title, { color: colors.foreground }]}>TIMMY</Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>SOVEREIGN AI AGENT</Text>
      <Text style={[styles.hint, { color: colors.muted }]}>
        Send a message, voice note, image, or file to get started.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 40,
    gap: 8,
  },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    letterSpacing: 4,
  },
  subtitle: {
    fontSize: 11,
    letterSpacing: 2,
    fontWeight: "600",
  },
  hint: {
    fontSize: 13,
    textAlign: "center",
    marginTop: 12,
    lineHeight: 19,
  },
});
