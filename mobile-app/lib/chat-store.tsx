import React, { createContext, useCallback, useContext, useReducer, type ReactNode } from "react";
import type { ChatMessage, MessageContentType } from "@/shared/types";

// ── State ───────────────────────────────────────────────────────────────────

interface ChatState {
  messages: ChatMessage[];
  isTyping: boolean;
}

const initialState: ChatState = {
  messages: [],
  isTyping: false,
};

// ── Actions ─────────────────────────────────────────────────────────────────

type ChatAction =
  | { type: "ADD_MESSAGE"; message: ChatMessage }
  | { type: "UPDATE_MESSAGE"; id: string; updates: Partial<ChatMessage> }
  | { type: "SET_TYPING"; isTyping: boolean }
  | { type: "CLEAR" };

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.message] };
    case "UPDATE_MESSAGE":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.id ? { ...m, ...action.updates } : m,
        ),
      };
    case "SET_TYPING":
      return { ...state, isTyping: action.isTyping };
    case "CLEAR":
      return initialState;
    default:
      return state;
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────────

let _counter = 0;
function makeId(): string {
  return `msg_${Date.now()}_${++_counter}`;
}

// ── Context ─────────────────────────────────────────────────────────────────

interface ChatContextValue {
  messages: ChatMessage[];
  isTyping: boolean;
  sendTextMessage: (text: string) => Promise<void>;
  sendAttachment: (opts: {
    contentType: MessageContentType;
    uri: string;
    fileName?: string;
    fileSize?: number;
    mimeType?: string;
    duration?: number;
    text?: string;
  }) => Promise<void>;
  clearChat: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

// ── API call ────────────────────────────────────────────────────────────────

function getApiBase(): string {
  // Set EXPO_PUBLIC_API_BASE_URL in your .env to point to your Timmy dashboard
  // e.g. EXPO_PUBLIC_API_BASE_URL=http://192.168.1.100:8000
  const envBase = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (envBase) return envBase.replace(/\/+$/, "");
  // Fallback for web: derive from window location (same host, port 8000)
  if (typeof window !== "undefined" && window.location) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  // Default: Timmy dashboard on localhost
  return "http://127.0.0.1:8000";
}

const API_BASE = getApiBase();

async function callChatAPI(
  messages: Array<{ role: string; content: string | Array<Record<string, unknown>> }>,
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => res.statusText);
    throw new Error(`Chat API error: ${errText}`);
  }
  const data = await res.json();
  return data.reply ?? data.text ?? "...";
}

async function uploadFile(
  uri: string,
  fileName: string,
  mimeType: string,
): Promise<string> {
  const formData = new FormData();
  formData.append("file", {
    uri,
    name: fileName,
    type: mimeType,
  } as unknown as Blob);

  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Upload failed");
  const data = await res.json();
  return data.url;
}

// ── Provider ────────────────────────────────────────────────────────────────

export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, initialState);

  const sendTextMessage = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        contentType: "text",
        text,
        timestamp: Date.now(),
      };
      dispatch({ type: "ADD_MESSAGE", message: userMsg });
      dispatch({ type: "SET_TYPING", isTyping: true });

      try {
        // Build conversation context (last 20 messages)
        const recent = [...state.messages, userMsg].slice(-20);
        const apiMessages = recent
          .filter((m) => m.contentType === "text" && m.text)
          .map((m) => ({ role: m.role, content: m.text! }));

        const reply = await callChatAPI(apiMessages);
        const assistantMsg: ChatMessage = {
          id: makeId(),
          role: "assistant",
          contentType: "text",
          text: reply,
          timestamp: Date.now(),
        };
        dispatch({ type: "ADD_MESSAGE", message: assistantMsg });
      } catch (err: unknown) {
        const errorText = err instanceof Error ? err.message : "Something went wrong";
        dispatch({
          type: "ADD_MESSAGE",
          message: {
            id: makeId(),
            role: "assistant",
            contentType: "text",
            text: `Sorry, I couldn't process that: ${errorText}`,
            timestamp: Date.now(),
          },
        });
      } finally {
        dispatch({ type: "SET_TYPING", isTyping: false });
      }
    },
    [state.messages],
  );

  const sendAttachment = useCallback(
    async (opts: {
      contentType: MessageContentType;
      uri: string;
      fileName?: string;
      fileSize?: number;
      mimeType?: string;
      duration?: number;
      text?: string;
    }) => {
      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        contentType: opts.contentType,
        uri: opts.uri,
        fileName: opts.fileName,
        fileSize: opts.fileSize,
        mimeType: opts.mimeType,
        duration: opts.duration,
        text: opts.text,
        timestamp: Date.now(),
      };
      dispatch({ type: "ADD_MESSAGE", message: userMsg });
      dispatch({ type: "SET_TYPING", isTyping: true });

      try {
        // Upload file to server
        const remoteUrl = await uploadFile(
          opts.uri,
          opts.fileName ?? "attachment",
          opts.mimeType ?? "application/octet-stream",
        );
        dispatch({ type: "UPDATE_MESSAGE", id: userMsg.id, updates: { remoteUrl } });

        // Build message for LLM
        let content: string | Array<Record<string, unknown>>;
        if (opts.contentType === "image") {
          content = [
            { type: "text", text: opts.text || "I'm sending you an image." },
            { type: "image_url", image_url: { url: remoteUrl } },
          ];
        } else if (opts.contentType === "voice") {
          content = [
            { type: "text", text: "I'm sending you a voice message. Please transcribe and respond." },
            { type: "file_url", file_url: { url: remoteUrl, mime_type: opts.mimeType ?? "audio/m4a" } },
          ];
        } else {
          content = `I'm sharing a file: ${opts.fileName ?? "file"} (${formatBytes(opts.fileSize ?? 0)})`;
        }

        const apiMessages = [{ role: "user", content }];
        const reply = await callChatAPI(apiMessages);

        dispatch({
          type: "ADD_MESSAGE",
          message: {
            id: makeId(),
            role: "assistant",
            contentType: "text",
            text: reply,
            timestamp: Date.now(),
          },
        });
      } catch (err: unknown) {
        const errorText = err instanceof Error ? err.message : "Upload failed";
        dispatch({
          type: "ADD_MESSAGE",
          message: {
            id: makeId(),
            role: "assistant",
            contentType: "text",
            text: `I had trouble processing that attachment: ${errorText}`,
            timestamp: Date.now(),
          },
        });
      } finally {
        dispatch({ type: "SET_TYPING", isTyping: false });
      }
    },
    [],
  );

  const clearChat = useCallback(() => {
    dispatch({ type: "CLEAR" });
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages: state.messages,
        isTyping: state.isTyping,
        sendTextMessage,
        sendAttachment,
        clearChat,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}

// ── Utils ───────────────────────────────────────────────────────────────────

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
