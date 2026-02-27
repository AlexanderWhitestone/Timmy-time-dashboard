import { useMemo } from "react";
import { Text, View, StyleSheet, Image, Platform } from "react-native";
import Pressable from "@/components/ui/pressable-fix";
import { useColors } from "@/hooks/use-colors";
import type { ChatMessage } from "@/shared/types";
import { formatBytes, formatDuration } from "@/lib/chat-store";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";

interface ChatBubbleProps {
  message: ChatMessage;
  onImagePress?: (uri: string) => void;
  onPlayVoice?: (message: ChatMessage) => void;
  isPlayingVoice?: boolean;
}

export function ChatBubble({ message, onImagePress, onPlayVoice, isPlayingVoice }: ChatBubbleProps) {
  const colors = useColors();
  const isUser = message.role === "user";

  // Stable waveform bar heights based on message id
  const waveHeights = useMemo(() => {
    let seed = 0;
    for (let i = 0; i < message.id.length; i++) seed = (seed * 31 + message.id.charCodeAt(i)) | 0;
    return Array.from({ length: 12 }, (_, i) => {
      seed = (seed * 16807 + i * 1013) % 2147483647;
      return 4 + (seed % 15);
    });
  }, [message.id]);

  const bubbleStyle = [
    styles.bubble,
    {
      backgroundColor: isUser ? colors.primary : colors.surface,
      borderColor: isUser ? colors.primary : colors.border,
      alignSelf: isUser ? "flex-end" as const : "flex-start" as const,
    },
  ];

  const textColor = isUser ? "#fff" : colors.foreground;
  const mutedColor = isUser ? "rgba(255,255,255,0.6)" : colors.muted;

  const timeStr = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      {!isUser && (
        <View style={[styles.avatar, { backgroundColor: colors.primary }]}>
          <Text style={styles.avatarText}>T</Text>
        </View>
      )}
      <View style={bubbleStyle}>
        {message.contentType === "text" && (
          <Text style={[styles.text, { color: textColor }]}>{message.text}</Text>
        )}

        {message.contentType === "image" && (
          <Pressable
            onPress={() => message.uri && onImagePress?.(message.uri)}
            style={({ pressed }) => [pressed && { opacity: 0.8 }]}
          >
            <Image
              source={{ uri: message.uri }}
              style={styles.image}
              resizeMode="cover"
            />
            {message.text ? (
              <Text style={[styles.text, { color: textColor, marginTop: 6 }]}>
                {message.text}
              </Text>
            ) : null}
          </Pressable>
        )}

        {message.contentType === "voice" && (
          <Pressable
            onPress={() => onPlayVoice?.(message)}
            style={({ pressed }) => [styles.voiceRow, pressed && { opacity: 0.7 }]}
          >
            <MaterialIcons
              name={isPlayingVoice ? "pause" : "play-arrow"}
              size={24}
              color={textColor}
            />
            <View style={[styles.waveform, { backgroundColor: isUser ? "rgba(255,255,255,0.3)" : colors.border }]}>
              {waveHeights.map((h, i) => (
                <View
                  key={i}
                  style={[
                    styles.waveBar,
                    {
                      height: h,
                      backgroundColor: textColor,
                      opacity: 0.6,
                    },
                  ]}
                />
              ))}
            </View>
            <Text style={[styles.duration, { color: mutedColor }]}>
              {formatDuration(message.duration ?? 0)}
            </Text>
          </Pressable>
        )}

        {message.contentType === "file" && (
          <View style={styles.fileRow}>
            <MaterialIcons name="insert-drive-file" size={28} color={textColor} />
            <View style={styles.fileInfo}>
              <Text style={[styles.fileName, { color: textColor }]} numberOfLines={1}>
                {message.fileName ?? "File"}
              </Text>
              <Text style={[styles.fileSize, { color: mutedColor }]}>
                {formatBytes(message.fileSize ?? 0)}
              </Text>
            </View>
          </View>
        )}

        <Text style={[styles.time, { color: mutedColor }]}>{timeStr}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    marginBottom: 8,
    paddingHorizontal: 12,
    alignItems: "flex-end",
  },
  rowUser: {
    justifyContent: "flex-end",
  },
  rowAssistant: {
    justifyContent: "flex-start",
  },
  avatar: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 8,
  },
  avatarText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 14,
  },
  bubble: {
    maxWidth: "78%",
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  text: {
    fontSize: 15,
    lineHeight: 21,
  },
  time: {
    fontSize: 10,
    marginTop: 4,
    textAlign: "right",
  },
  image: {
    width: 220,
    height: 180,
    borderRadius: 10,
  },
  voiceRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    minWidth: 160,
  },
  waveform: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    height: 24,
    borderRadius: 4,
    paddingHorizontal: 4,
  },
  waveBar: {
    width: 3,
    borderRadius: 1.5,
  },
  duration: {
    fontSize: 12,
    minWidth: 32,
  },
  fileRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  fileInfo: {
    flex: 1,
  },
  fileName: {
    fontSize: 14,
    fontWeight: "600",
  },
  fileSize: {
    fontSize: 11,
    marginTop: 2,
  },
});
