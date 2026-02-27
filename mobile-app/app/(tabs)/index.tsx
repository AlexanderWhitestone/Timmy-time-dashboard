import { useCallback, useRef, useState } from "react";
import { FlatList, KeyboardAvoidingView, Platform, StyleSheet, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { ChatHeader } from "@/components/chat-header";
import { ChatBubble } from "@/components/chat-bubble";
import { ChatInput } from "@/components/chat-input";
import { TypingIndicator } from "@/components/typing-indicator";
import { ImageViewer } from "@/components/image-viewer";
import { EmptyChat } from "@/components/empty-chat";
import { useChat } from "@/lib/chat-store";
import { useColors } from "@/hooks/use-colors";
import { createAudioPlayer, setAudioModeAsync } from "expo-audio";
import type { ChatMessage } from "@/shared/types";

export default function ChatScreen() {
  const { messages, isTyping } = useChat();
  const colors = useColors();
  const flatListRef = useRef<FlatList>(null);
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);

  const handlePlayVoice = useCallback(async (msg: ChatMessage) => {
    if (!msg.uri) return;
    try {
      if (playingVoiceId === msg.id) {
        setPlayingVoiceId(null);
        return;
      }
      await setAudioModeAsync({ playsInSilentMode: true });
      const player = createAudioPlayer({ uri: msg.uri });
      player.play();
      setPlayingVoiceId(msg.id);
      // Auto-reset after estimated duration
      const dur = (msg.duration ?? 5) * 1000;
      setTimeout(() => {
        setPlayingVoiceId(null);
        player.remove();
      }, dur + 500);
    } catch (err) {
      console.warn("Voice playback error:", err);
      setPlayingVoiceId(null);
    }
  }, [playingVoiceId]);

  const renderItem = useCallback(
    ({ item }: { item: ChatMessage }) => (
      <ChatBubble
        message={item}
        onImagePress={setViewingImage}
        onPlayVoice={handlePlayVoice}
        isPlayingVoice={playingVoiceId === item.id}
      />
    ),
    [playingVoiceId, handlePlayVoice],
  );

  const keyExtractor = useCallback((item: ChatMessage) => item.id, []);

  return (
    <ScreenContainer edges={["top", "left", "right"]} containerClassName="bg-background">
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        <ChatHeader />

        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          contentContainerStyle={styles.listContent}
          style={{ flex: 1, backgroundColor: colors.background }}
          onContentSizeChange={() => {
            flatListRef.current?.scrollToEnd({ animated: true });
          }}
          ListFooterComponent={isTyping ? <TypingIndicator /> : null}
          ListEmptyComponent={!isTyping ? <EmptyChat /> : null}
          showsVerticalScrollIndicator={false}
        />

        <ChatInput />
      </KeyboardAvoidingView>

      <ImageViewer uri={viewingImage} onClose={() => setViewingImage(null)} />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  listContent: {
    paddingVertical: 12,
  },
});
