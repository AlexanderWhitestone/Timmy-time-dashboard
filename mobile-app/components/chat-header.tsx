import { View, Text, StyleSheet } from "react-native";
import Pressable from "@/components/ui/pressable-fix";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { useColors } from "@/hooks/use-colors";
import { useChat } from "@/lib/chat-store";

export function ChatHeader() {
  const colors = useColors();
  const { clearChat } = useChat();

  return (
    <View style={[styles.header, { backgroundColor: colors.background, borderBottomColor: colors.border }]}>
      <View style={styles.left}>
        <View style={[styles.statusDot, { backgroundColor: colors.success }]} />
        <Text style={[styles.title, { color: colors.foreground }]}>TIMMY</Text>
        <Text style={[styles.subtitle, { color: colors.muted }]}>SOVEREIGN AI</Text>
      </View>
      <Pressable
        onPress={clearChat}
        style={({ pressed }: { pressed: boolean }) => [
          styles.clearBtn,
          { borderColor: colors.border },
          pressed && { opacity: 0.6 },
        ]}
      >
        <MaterialIcons name="delete-outline" size={16} color={colors.muted} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  left: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  title: {
    fontSize: 16,
    fontWeight: "700",
    letterSpacing: 2,
  },
  subtitle: {
    fontSize: 9,
    letterSpacing: 1.5,
    fontWeight: "600",
  },
  clearBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
});
