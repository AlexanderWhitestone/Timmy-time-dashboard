# Timmy Chat — Mobile App Design

## Overview
A sleek, single-screen chat app for talking to Timmy — the sovereign AI agent from the Timmy Time dashboard. Supports text, voice, image, and file messaging. Dark arcane theme matching Mission Control.

## Screen List

### 1. Chat Screen (Home / Only Screen)
The entire app is a single full-screen chat interface. No tabs, no settings, no extra screens. Just you and Timmy.

### 2. No Other Screens
No settings, no profile, no onboarding. The app opens straight to chat.

## Primary Content and Functionality

### Chat Screen
- **Header**: "TIMMY" title with status indicator (online/offline dot), minimal and clean
- **Message List**: Full-screen scrollable message list (FlatList, inverted)
  - User messages: right-aligned, purple/violet accent bubble
  - Timmy messages: left-aligned, dark surface bubble with avatar initial "T"
  - Image messages: thumbnail preview in bubble, tappable for full-screen
  - File messages: file icon + filename + size in bubble
  - Voice messages: waveform-style playback bar with play/pause + duration
  - Timestamps shown subtly below message groups
- **Input Bar** (bottom, always visible):
  - Text input field (expandable, multi-line)
  - Attachment button (left of input) — opens action sheet: Camera, Photo Library, File
  - Voice record button (right of input, replaces send when input is empty)
  - Send button (right of input, appears when text is entered)
  - Hold-to-record voice: press and hold mic icon, release to send

## Key User Flows

### Text Chat
1. User types message → taps Send
2. Message appears in chat as "sending"
3. Server responds → Timmy's reply appears below

### Voice Message
1. User presses and holds mic button
2. Recording indicator appears (duration + pulsing dot)
3. User releases → voice message sent
4. Timmy responds with text (server processes audio)

### Image Sharing
1. User taps attachment (+) button
2. Action sheet: "Take Photo" / "Choose from Library"
3. Image appears as thumbnail in chat
4. Timmy acknowledges receipt

### File Sharing
1. User taps attachment (+) button → "Choose File"
2. Document picker opens
3. File appears in chat with name + size
4. Timmy acknowledges receipt

## Color Choices (Arcane Dark Theme)

Matching the Timmy Time Mission Control dashboard:

| Token       | Dark Value   | Purpose                        |
|-------------|-------------|--------------------------------|
| background  | #080412     | Deep dark purple-black          |
| surface     | #110820     | Card/bubble background          |
| foreground  | #ede0ff     | Primary text (bright lavender)  |
| muted       | #6b4a8a     | Secondary/timestamp text        |
| primary     | #a855f7     | Accent purple (user bubbles)    |
| border      | #3b1a5c     | Subtle borders                  |
| success     | #00e87a     | Online status, success          |
| warning     | #ffb800     | Amber warnings                  |
| error       | #ff4455     | Error states                    |

## Layout Specifics (Portrait 9:16, One-Handed)

- Input bar pinned to bottom with safe area padding
- Send/mic button on right (thumb-reachable)
- Attachment button on left of input
- Messages fill remaining space above input
- No tab bar — single screen app
- Header is compact (44pt) with just title + status dot
