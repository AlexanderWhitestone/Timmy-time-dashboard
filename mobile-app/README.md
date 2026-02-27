# Timmy Chat — Mobile App

A mobile chat interface for Timmy, the sovereign AI agent. Built with **Expo SDK 54**, **React Native**, **TypeScript**, and **NativeWind** (Tailwind CSS).

## Features

- **Text Chat** — Send and receive messages with Timmy's full personality
- **Voice Messages** — Record and send voice notes via the mic button; playback with waveform UI
- **Image Sharing** — Take photos or pick from library; full-screen image viewer
- **File Attachments** — Send any document via the system file picker
- **Dark Arcane Theme** — Deep purple/indigo palette matching the Timmy Time dashboard

## Architecture

The mobile app is a **thin client** — all AI processing happens on the Timmy dashboard backend (FastAPI + Ollama). The app communicates over two REST endpoints:

```
Mobile App  ──POST /api/chat──►  FastAPI Dashboard  ──►  Ollama (local LLM)
            ──POST /api/upload──►  File storage
            ──GET  /api/chat/history──►  Chat history
```

No separate Node.js server is needed. Just point the app at your running Timmy dashboard.

## Project Structure

```
mobile-app/
├── app/                    # Expo Router screens
│   ├── _layout.tsx         # Root layout with providers
│   └── (tabs)/
│       └── index.tsx       # Main chat screen
├── components/
│   ├── chat-bubble.tsx     # Message bubble (text, image, voice, file)
│   ├── chat-header.tsx     # Header with Timmy status
│   ├── chat-input.tsx      # Input bar (text, mic, attachments)
│   ├── empty-chat.tsx      # Empty state welcome screen
│   ├── image-viewer.tsx    # Full-screen image modal
│   └── typing-indicator.tsx # Animated dots while Timmy responds
├── lib/
│   ├── chat-store.tsx      # React Context chat state + API calls
│   └── _core/theme.ts      # Color palette definitions
├── shared/
│   └── types.ts            # ChatMessage type definitions
├── hooks/
│   ├── use-colors.ts       # Current theme color palette hook
│   └── use-color-scheme.ts # System color scheme detection
├── constants/
│   └── theme.ts            # Theme re-exports
└── tests/
    └── chat.test.ts        # Unit tests
```

## Setup

### Prerequisites

- Node.js 18+
- pnpm 9+
- Expo CLI (`npx expo`)
- iOS Simulator or Android Emulator (or physical device with Expo Go)
- **Timmy dashboard running** (provides the chat API)

### Install & Run

```bash
cd mobile-app
pnpm install

# Set your Timmy dashboard URL (your computer's IP on the local network)
export EXPO_PUBLIC_API_BASE_URL=http://192.168.1.100:8000

# Start the app
npx expo start --ios     # iPhone simulator
npx expo start --android # Android emulator
npx expo start --web     # Browser preview
```

### Backend

The app connects to the Timmy Time dashboard backend. Make sure it's running:

```bash
# From the project root
make dev
# Dashboard starts on http://localhost:8000
```

The mobile app calls these endpoints on the dashboard:
- `POST /api/chat` — Send messages, get Timmy's replies
- `POST /api/upload` — Upload images/files/voice recordings
- `GET /api/chat/history` — Retrieve chat history
- `DELETE /api/chat/history` — Clear chat

## Theme

Dark arcane palette:

| Token | Color | Usage |
|-------|-------|-------|
| `primary` | `#a855f7` | Accent, user bubbles |
| `background` | `#080412` | Screen background |
| `surface` | `#110820` | Cards, Timmy bubbles |
| `foreground` | `#ede0ff` | Primary text |
| `muted` | `#6b4a8a` | Secondary text |
| `border` | `#3b1a5c` | Dividers |
| `success` | `#00e87a` | Status indicator |
| `error` | `#ff4455` | Recording state |

## License

Same as the parent Timmy Time Dashboard project.
