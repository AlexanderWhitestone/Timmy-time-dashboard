import { useCallback, useRef, useState } from "react";
import {
  View,
  TextInput,
  StyleSheet,
  Platform,
  ActionSheetIOS,
  Alert,
  Keyboard,
} from "react-native";
import Pressable from "@/components/ui/pressable-fix";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { useColors } from "@/hooks/use-colors";
import { useChat } from "@/lib/chat-store";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import {
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from "expo-audio";
import * as Haptics from "expo-haptics";

export function ChatInput() {
  const colors = useColors();
  const { sendTextMessage, sendAttachment, isTyping } = useChat();
  const [text, setText] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const inputRef = useRef<TextInput>(null);

  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(audioRecorder);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setText("");
    Keyboard.dismiss();
    if (Platform.OS !== "web") {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    sendTextMessage(trimmed);
  }, [text, sendTextMessage]);

  // ── Attachment sheet ────────────────────────────────────────────────────

  const handleAttachment = useCallback(() => {
    if (Platform.OS !== "web") {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }

    const options = ["Take Photo", "Choose from Library", "Choose File", "Cancel"];
    const cancelIndex = 3;

    if (Platform.OS === "ios") {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex: cancelIndex },
        (idx) => {
          if (idx === 0) takePhoto();
          else if (idx === 1) pickImage();
          else if (idx === 2) pickFile();
        },
      );
    } else {
      // Android / Web fallback
      Alert.alert("Attach", "Choose an option", [
        { text: "Take Photo", onPress: takePhoto },
        { text: "Choose from Library", onPress: pickImage },
        { text: "Choose File", onPress: pickFile },
        { text: "Cancel", style: "cancel" },
      ]);
    }
  }, []);

  const takePhoto = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "Camera access is required to take photos.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      quality: 0.8,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      sendAttachment({
        contentType: "image",
        uri: asset.uri,
        fileName: asset.fileName ?? "photo.jpg",
        fileSize: asset.fileSize,
        mimeType: asset.mimeType ?? "image/jpeg",
      });
    }
  };

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.8,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      sendAttachment({
        contentType: "image",
        uri: asset.uri,
        fileName: asset.fileName ?? "image.jpg",
        fileSize: asset.fileSize,
        mimeType: asset.mimeType ?? "image/jpeg",
      });
    }
  };

  const pickFile = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: "*/*",
        copyToCacheDirectory: true,
      });
      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];
        sendAttachment({
          contentType: "file",
          uri: asset.uri,
          fileName: asset.name,
          fileSize: asset.size,
          mimeType: asset.mimeType ?? "application/octet-stream",
        });
      }
    } catch (err) {
      console.warn("Document picker error:", err);
    }
  };

  // ── Voice recording ───────────────────────────────────────────────────

  const startRecording = async () => {
    try {
      const { granted } = await requestRecordingPermissionsAsync();
      if (!granted) {
        Alert.alert("Permission needed", "Microphone access is required for voice messages.");
        return;
      }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setIsRecording(true);
      if (Platform.OS !== "web") {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      }
    } catch (err) {
      console.warn("Recording start error:", err);
    }
  };

  const stopRecording = async () => {
    try {
      await audioRecorder.stop();
      setIsRecording(false);
      if (Platform.OS !== "web") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      const uri = audioRecorder.uri;
      if (uri) {
        const duration = recorderState.durationMillis ? recorderState.durationMillis / 1000 : 0;
        sendAttachment({
          contentType: "voice",
          uri,
          fileName: "voice_message.m4a",
          mimeType: "audio/m4a",
          duration,
        });
      }
    } catch (err) {
      console.warn("Recording stop error:", err);
      setIsRecording(false);
    }
  };

  const handleMicPress = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [isRecording]);

  const hasText = text.trim().length > 0;

  return (
    <View style={[styles.container, { backgroundColor: colors.background, borderTopColor: colors.border }]}>
      {/* Attachment button */}
      <Pressable
        onPress={handleAttachment}
        style={({ pressed }: { pressed: boolean }) => [
          styles.iconBtn,
          { backgroundColor: colors.surface },
          pressed && { opacity: 0.6 },
        ]}
        disabled={isTyping}
      >
        <MaterialIcons name="add" size={22} color={colors.muted} />
      </Pressable>

      {/* Text input */}
      <TextInput
        ref={inputRef}
        value={text}
        onChangeText={setText}
        placeholder={isRecording ? "Recording..." : "Message Timmy..."}
        placeholderTextColor={colors.muted}
        style={[
          styles.input,
          {
            backgroundColor: colors.surface,
            color: colors.foreground,
            borderColor: colors.border,
          },
        ]}
        multiline
        maxLength={4000}
        returnKeyType="default"
        editable={!isRecording && !isTyping}
        onSubmitEditing={handleSend}
        blurOnSubmit={false}
      />

      {/* Send or Mic button */}
      {hasText ? (
        <Pressable
          onPress={handleSend}
          style={({ pressed }: { pressed: boolean }) => [
            styles.sendBtn,
            { backgroundColor: colors.primary },
            pressed && { transform: [{ scale: 0.95 }], opacity: 0.9 },
          ]}
          disabled={isTyping}
        >
          <MaterialIcons name="send" size={20} color="#fff" />
        </Pressable>
      ) : (
        <Pressable
          onPress={handleMicPress}
          style={({ pressed }: { pressed: boolean }) => [
            styles.sendBtn,
            {
              backgroundColor: isRecording ? colors.error : colors.surface,
            },
            pressed && { transform: [{ scale: 0.95 }], opacity: 0.9 },
          ]}
          disabled={isTyping}
        >
          <MaterialIcons
            name={isRecording ? "stop" : "mic"}
            size={20}
            color={isRecording ? "#fff" : colors.primary}
          />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 8,
    borderTopWidth: 1,
  },
  iconBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
  input: {
    flex: 1,
    minHeight: 38,
    maxHeight: 120,
    borderRadius: 19,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 8,
    fontSize: 15,
    lineHeight: 20,
  },
  sendBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
});
