/**
 * Unified type exports
 * Import shared types from this single entry point.
 */

export type * from "../drizzle/schema";
export * from "./_core/errors";

// ── Chat Message Types ──────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant";

export type MessageContentType = "text" | "image" | "file" | "voice";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  contentType: MessageContentType;
  text?: string;
  /** URI for image, file, or voice attachment */
  uri?: string;
  /** Original filename for files */
  fileName?: string;
  /** File size in bytes */
  fileSize?: number;
  /** MIME type for attachments */
  mimeType?: string;
  /** Duration in seconds for voice messages */
  duration?: number;
  /** Remote URL after upload (for images/files/voice sent to server) */
  remoteUrl?: string;
  timestamp: number;
  /** Whether the message is still being generated */
  pending?: boolean;
}
