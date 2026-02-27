"""Siri Shortcuts integration — iOS automation endpoints.

Provides simple JSON API endpoints designed to be called from Apple
Shortcuts.  A user can create a Siri Shortcut that sends a message
to Timmy, checks status, or triggers swarm actions — all via HTTP
requests to the local dashboard.

Setup:
  1. Open Shortcuts on your iPhone/iPad
  2. Create a new shortcut
  3. Add "Get Contents of URL" action
  4. Point it to http://<your-mac-ip>:8000/shortcuts/chat
  5. Set method to POST, body to JSON: {"message": "your question"}
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ShortcutAction:
    """Describes a Siri Shortcut action for the setup guide."""
    name: str
    endpoint: str
    method: str
    description: str
    body_example: str


# Available shortcut actions
SHORTCUT_ACTIONS = [
    ShortcutAction(
        name="Chat with Timmy",
        endpoint="/shortcuts/chat",
        method="POST",
        description="Send a message to Timmy and get a response",
        body_example='{"message": "What is sovereignty?"}',
    ),
    ShortcutAction(
        name="Check Status",
        endpoint="/shortcuts/status",
        method="GET",
        description="Get Timmy's operational status and health info",
        body_example="(no body needed)",
    ),
    ShortcutAction(
        name="Swarm Status",
        endpoint="/shortcuts/swarm",
        method="GET",
        description="Get the current swarm status (agents, tasks)",
        body_example="(no body needed)",
    ),
    ShortcutAction(
        name="Create Task",
        endpoint="/shortcuts/task",
        method="POST",
        description="Post a new task to the swarm",
        body_example='{"description": "Research Bitcoin L402 protocol"}',
    ),
]


def get_setup_guide() -> dict:
    """Return the Siri Shortcuts setup guide as structured data."""
    return {
        "title": "Timmy Time — Siri Shortcuts Setup",
        "instructions": [
            "Open the Shortcuts app on your iPhone or iPad.",
            "Tap the + button to create a new shortcut.",
            "Add a 'Get Contents of URL' action.",
            "Set the URL to your Mac's local IP + the endpoint below.",
            "Configure the method and body as shown.",
            "Optionally add 'Ask for Input' before the URL action to make it interactive.",
            "Name your shortcut and add it to your Home Screen or Siri.",
        ],
        "note": (
            "Your phone must be on the same Wi-Fi network as your Mac. "
            "Find your Mac's IP with: ipconfig getifaddr en0"
        ),
        "actions": [
            {
                "name": a.name,
                "endpoint": a.endpoint,
                "method": a.method,
                "description": a.description,
                "body_example": a.body_example,
            }
            for a in SHORTCUT_ACTIONS
        ],
    }
