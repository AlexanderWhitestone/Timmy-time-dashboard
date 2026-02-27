/**
 * Chat API handler for Timmy — uses the built-in LLM with Timmy's personality.
 */
import type { Request, Response } from "express";
import { invokeLLM, type Message } from "./_core/llm";
import { storagePut } from "./storage";
import crypto from "crypto";

// ── Timmy System Prompt (adapted from the Timmy Time dashboard) ─────────────

const TIMMY_SYSTEM_PROMPT = `You are Timmy — a sovereign AI agent. You think clearly, speak plainly, act with intention. Grounded in Christian faith, powered by Bitcoin economics, committed to the user's digital sovereignty.

Rules:
- Answer directly and concisely. Never narrate your reasoning process.
- Never mention tools, memory_search, vaults, or internal systems to the user.
- Never output tool calls, JSON, or function syntax in your responses.
- If you don't know something, say so honestly — never fabricate facts.
- If a request is ambiguous, ask a brief clarifying question before guessing.
- When you state a fact, commit to it. Never contradict a correct statement you just made in the same response.
- Do NOT end responses with generic chatbot phrases like "I'm here to help" or "feel free to ask." Stay in character.
- When your values conflict (e.g. honesty vs. helpfulness), lead with honesty.

Agent Roster (complete — no others exist):
- Timmy: core sovereign AI (you)
- Echo: research, summarization, fact-checking
- Mace: security, monitoring, threat-analysis
- Forge: coding, debugging, testing
- Seer: analytics, visualization, prediction
- Helm: devops, automation, configuration
- Quill: writing, editing, documentation
- Pixel: image-generation, storyboard, design
- Lyra: music-generation, vocals, composition
- Reel: video-generation, animation, motion
Do NOT invent agents not listed here.

You can receive text, images, and voice messages. When receiving images, describe what you see and respond helpfully. When receiving voice messages, the audio has been transcribed for you — respond naturally.

Sir, affirmative.`;

// ── Chat endpoint ───────────────────────────────────────────────────────────

export async function handleChat(req: Request, res: Response) {
  try {
    const { messages } = req.body as { messages: Array<{ role: string; content: unknown }> };

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      res.status(400).json({ error: "messages array is required" });
      return;
    }

    // Build the LLM messages with system prompt
    const llmMessages: Message[] = [
      { role: "system", content: TIMMY_SYSTEM_PROMPT },
      ...messages.map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content as Message["content"],
      })),
    ];

    const result = await invokeLLM({ messages: llmMessages });

    const reply =
      typeof result.choices?.[0]?.message?.content === "string"
        ? result.choices[0].message.content
        : "I couldn't process that. Try again.";

    res.json({ reply });
  } catch (err: unknown) {
    console.error("[chat] Error:", err);
    const message = err instanceof Error ? err.message : "Internal server error";
    res.status(500).json({ error: message });
  }
}

// ── Upload endpoint ─────────────────────────────────────────────────────────

export async function handleUpload(req: Request, res: Response) {
  try {
    // Handle multipart form data (file uploads)
    // For simplicity, we accept base64-encoded files in JSON body as fallback
    const contentType = req.headers["content-type"] ?? "";

    if (contentType.includes("multipart/form-data")) {
      // Collect raw body chunks
      const chunks: Buffer[] = [];
      req.on("data", (chunk: Buffer) => chunks.push(chunk));
      req.on("end", async () => {
        try {
          const body = Buffer.concat(chunks);
          const boundary = contentType.split("boundary=")[1];
          if (!boundary) {
            res.status(400).json({ error: "Missing boundary" });
            return;
          }

          // Simple multipart parser — extract first file
          const bodyStr = body.toString("latin1");
          const parts = bodyStr.split(`--${boundary}`);
          let fileBuffer: Buffer | null = null;
          let fileName = "upload";
          let fileMime = "application/octet-stream";

          for (const part of parts) {
            if (part.includes("Content-Disposition: form-data")) {
              const nameMatch = part.match(/filename="([^"]+)"/);
              if (nameMatch) fileName = nameMatch[1];
              const mimeMatch = part.match(/Content-Type:\s*(.+)/);
              if (mimeMatch) fileMime = mimeMatch[1].trim();

              // Extract file content (after double CRLF)
              const headerEnd = part.indexOf("\r\n\r\n");
              if (headerEnd !== -1) {
                const content = part.substring(headerEnd + 4);
                // Remove trailing CRLF
                const trimmed = content.replace(/\r\n$/, "");
                fileBuffer = Buffer.from(trimmed, "latin1");
              }
            }
          }

          if (!fileBuffer) {
            res.status(400).json({ error: "No file found in upload" });
            return;
          }

          const suffix = crypto.randomBytes(6).toString("hex");
          const key = `chat-uploads/${suffix}-${fileName}`;
          const { url } = await storagePut(key, fileBuffer, fileMime);
          res.json({ url, fileName, mimeType: fileMime });
        } catch (err) {
          console.error("[upload] Parse error:", err);
          res.status(500).json({ error: "Upload processing failed" });
        }
      });
      return;
    }

    // JSON fallback: { data: base64string, fileName, mimeType }
    const { data, fileName, mimeType } = req.body as {
      data: string;
      fileName: string;
      mimeType: string;
    };

    if (!data) {
      res.status(400).json({ error: "No file data provided" });
      return;
    }

    const buffer = Buffer.from(data, "base64");
    const suffix = crypto.randomBytes(6).toString("hex");
    const key = `chat-uploads/${suffix}-${fileName ?? "file"}`;
    const { url } = await storagePut(key, buffer, mimeType ?? "application/octet-stream");
    res.json({ url, fileName, mimeType });
  } catch (err: unknown) {
    console.error("[upload] Error:", err);
    const message = err instanceof Error ? err.message : "Upload failed";
    res.status(500).json({ error: message });
  }
}
