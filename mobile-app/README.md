# Timmy Chat — Mobile App

A sleek mobile chat interface for Timmy, the sovereign AI agent. Built with **Expo SDK 54**, **React Native**, **TypeScript**, and **NativeWind** (Tailwind CSS).

## Features

- **Text Chat** — Send and receive messages with Timmy's full personality
- **Voice Messages** — Record and send voice notes via the mic button; playback with waveform UI
- **Image Sharing** — Take photos or pick from library; full-screen image viewer
- **File Attachments** — Send any document via the system file picker
- **Dark Arcane Theme** — Deep purple/indigo palette matching the Timmy Time dashboard

## Screenshots

The app is a single-screen chat interface with:
- Header showing Timmy's status and a clear-chat button
- Message list with distinct user (teal) and Timmy (dark surface) bubbles
- Input bar with attachment (+), text field, and mic/send button
- Empty state with Timmy branding when no messages exist

## Project Structure

```
mobile-app/
├── app/                    # Expo Router screens
│   ├── _layout.tsx         # Root layout with providers
│   └── (tabs)/
│       ├── _layout.tsx     # Tab layout (hidden — single screen)
│       └── index.tsx       # Main chat screen
├── components/
│   ├── chat-bubble.tsx     # Message bubble (text, image, voice, file)
│   ├── chat-header.tsx     # Header with Timmy status
│   ├── chat-input.tsx      # Input bar (text, mic, attachments)
│   ├── empty-chat.tsx      # Empty state welcome screen
│   ├── image-viewer.tsx    # Full-screen image modal
│   └── typing-indicator.tsx # Animated dots while Timmy responds
├── lib/
│   └── chat-store.tsx      # React Context chat state + API calls
├── server/
│   └── chat.ts             # Server-side chat handler with Timmy's prompt
├── shared/
│   └── types.ts            # ChatMessage type definitions
├── assets/images/          # App icons (custom generated)
├── theme.config.js         # Color tokens (dark arcane palette)
├── tailwind.config.js      # Tailwind/NativeWind configuration
└── tests/
    └── chat.test.ts        # Unit tests
```

## Setup

### Prerequisites

- Node.js 18+
- pnpm 9+
- Expo CLI (`npx expo`)
- iOS Simulator or Android Emulator (or physical device with Expo Go)

### Install Dependencies

```bash
cd mobile-app
pnpm install
```

### Run the App

```bash
# Start the Expo dev server
npx expo start

# Or run on specific platform
npx expo start --ios
npx expo start --android
npx expo start --web
```

### Backend

The chat API endpoint (`server/chat.ts`) requires an LLM backend. The `invokeLLM` function should be wired to your preferred provider:

- **Local Ollama** — Point to `http://localhost:11434` for local inference
- **OpenAI-compatible API** — Any API matching the OpenAI chat completions format

The system prompt in `server/chat.ts` contains Timmy's full personality, agent roster, and behavioral rules ported from the dashboard's `prompts.py`.

## Timmy's Personality

Timmy is a sovereign AI agent — grounded in Christian faith, powered by Bitcoin economics, committed to digital sovereignty. He speaks plainly, acts with intention, and never ends responses with generic chatbot phrases. His agent roster includes Echo, Mace, Forge, Seer, Helm, Quill, Pixel, Lyra, and Reel.

## Theme

The app uses a dark arcane color palette:

| Token | Color | Usage |
|-------|-------|-------|
| `primary` | `#7c3aed` | Accent, user bubbles |
| `background` | `#080412` | Screen background |
| `surface` | `#110a20` | Cards, Timmy bubbles |
| `foreground` | `#e8e0f0` | Primary text |
| `muted` | `#6b5f7d` | Secondary text |
| `border` | `#1e1535` | Dividers |
| `success` | `#22c55e` | Status indicator |
| `error` | `#ff4455` | Recording state |

## License

Same as the parent Timmy Time Dashboard project.
