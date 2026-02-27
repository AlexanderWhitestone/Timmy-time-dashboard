import { Modal, View, Image, StyleSheet, StatusBar } from "react-native";
import Pressable from "@/components/ui/pressable-fix";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";

interface ImageViewerProps {
  uri: string | null;
  onClose: () => void;
}

export function ImageViewer({ uri, onClose }: ImageViewerProps) {
  if (!uri) return null;

  return (
    <Modal visible animationType="fade" transparent statusBarTranslucent>
      <View style={styles.overlay}>
        <StatusBar barStyle="light-content" />
        <Image source={{ uri }} style={styles.image} resizeMode="contain" />
        <Pressable
          onPress={onClose}
          style={({ pressed }: { pressed: boolean }) => [
            styles.closeBtn,
            pressed && { opacity: 0.6 },
          ]}
        >
          <MaterialIcons name="close" size={28} color="#fff" />
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.95)",
    justifyContent: "center",
    alignItems: "center",
  },
  image: {
    width: "100%",
    height: "80%",
  },
  closeBtn: {
    position: "absolute",
    top: 50,
    right: 20,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center",
  },
});
