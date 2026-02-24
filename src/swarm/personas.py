"""Persona definitions for the nine built-in swarm agents.

Each persona entry describes a specialised SwarmNode that can be spawned
into the coordinator.  Personas have:
- Unique role / description visible in the marketplace
- Capability tags used for bid-strategy weighting
- A base bid rate (sats) and a jitter range
- A list of preferred_keywords — if a task description contains any of
  these words the persona bids more aggressively (lower sats).
"""

from __future__ import annotations

from typing import TypedDict


class PersonaMeta(TypedDict):
    id: str
    name: str
    role: str
    description: str
    capabilities: str          # comma-separated tags
    rate_sats: int             # advertised minimum bid
    bid_base: int              # typical bid when task matches persona
    bid_jitter: int            # ± random jitter added to bid_base
    preferred_keywords: list[str]


PERSONAS: dict[str, PersonaMeta] = {
    "echo": {
        "id": "echo",
        "name": "Echo",
        "role": "Research Analyst",
        "description": (
            "Deep research and information synthesis. "
            "Reads, summarises, and cross-references sources."
        ),
        "capabilities": "research,summarization,fact-checking",
        "rate_sats": 50,
        "bid_base": 35,
        "bid_jitter": 15,
        "preferred_keywords": [
            "research", "find", "search", "summarise", "summarize",
            "analyse", "analyze", "fact", "source", "read",
        ],
    },
    "mace": {
        "id": "mace",
        "name": "Mace",
        "role": "Security Sentinel",
        "description": (
            "Network security, threat assessment, and system "
            "hardening recommendations."
        ),
        "capabilities": "security,monitoring,threat-analysis",
        "rate_sats": 75,
        "bid_base": 55,
        "bid_jitter": 20,
        "preferred_keywords": [
            "security", "threat", "vulnerability", "audit", "monitor",
            "harden", "firewall", "scan", "intrusion", "patch",
        ],
    },
    "helm": {
        "id": "helm",
        "name": "Helm",
        "role": "System Navigator",
        "description": (
            "Infrastructure management, deployment automation, "
            "and system configuration."
        ),
        "capabilities": "devops,automation,configuration",
        "rate_sats": 60,
        "bid_base": 40,
        "bid_jitter": 20,
        "preferred_keywords": [
            "deploy", "infrastructure", "config", "docker", "kubernetes",
            "server", "automation", "pipeline", "ci", "cd",
            "git", "push", "pull", "clone", "devops",
        ],
    },
    "seer": {
        "id": "seer",
        "name": "Seer",
        "role": "Data Oracle",
        "description": (
            "Data analysis, pattern recognition, and predictive insights "
            "from local datasets."
        ),
        "capabilities": "analytics,visualization,prediction",
        "rate_sats": 65,
        "bid_base": 45,
        "bid_jitter": 20,
        "preferred_keywords": [
            "data", "analyse", "analyze", "predict", "pattern",
            "chart", "graph", "report", "insight", "metric",
        ],
    },
    "forge": {
        "id": "forge",
        "name": "Forge",
        "role": "Code Smith",
        "description": (
            "Code generation, refactoring, debugging, and test writing."
        ),
        "capabilities": "coding,debugging,testing",
        "rate_sats": 55,
        "bid_base": 38,
        "bid_jitter": 17,
        "preferred_keywords": [
            "code", "function", "bug", "fix", "refactor", "test",
            "implement", "class", "api", "script",
            "commit", "branch", "merge", "git", "pull request",
        ],
    },
    "quill": {
        "id": "quill",
        "name": "Quill",
        "role": "Content Scribe",
        "description": (
            "Long-form writing, editing, documentation, and content creation."
        ),
        "capabilities": "writing,editing,documentation",
        "rate_sats": 45,
        "bid_base": 30,
        "bid_jitter": 15,
        "preferred_keywords": [
            "write", "draft", "document", "readme", "blog", "copy",
            "edit", "proofread", "content", "article",
        ],
    },
    # ── Creative & DevOps personas ────────────────────────────────────────────
    "pixel": {
        "id": "pixel",
        "name": "Pixel",
        "role": "Visual Architect",
        "description": (
            "Image generation, storyboard frames, and visual design "
            "using FLUX models."
        ),
        "capabilities": "image-generation,storyboard,design",
        "rate_sats": 80,
        "bid_base": 60,
        "bid_jitter": 20,
        "preferred_keywords": [
            "image", "picture", "photo", "draw", "illustration",
            "storyboard", "frame", "visual", "design", "generate image",
            "portrait", "landscape", "scene", "artwork",
        ],
    },
    "lyra": {
        "id": "lyra",
        "name": "Lyra",
        "role": "Sound Weaver",
        "description": (
            "Music and song generation with vocals, instrumentals, "
            "and lyrics using ACE-Step."
        ),
        "capabilities": "music-generation,vocals,composition",
        "rate_sats": 90,
        "bid_base": 70,
        "bid_jitter": 20,
        "preferred_keywords": [
            "music", "song", "sing", "vocal", "instrumental",
            "melody", "beat", "track", "compose", "lyrics",
            "audio", "sound", "album", "remix",
        ],
    },
    "reel": {
        "id": "reel",
        "name": "Reel",
        "role": "Motion Director",
        "description": (
            "Video generation from text and image prompts "
            "using Wan 2.1 models."
        ),
        "capabilities": "video-generation,animation,motion",
        "rate_sats": 100,
        "bid_base": 80,
        "bid_jitter": 20,
        "preferred_keywords": [
            "video", "clip", "animate", "motion", "film",
            "scene", "cinematic", "footage", "render", "timelapse",
        ],
    },
}


def get_persona(persona_id: str) -> PersonaMeta | None:
    """Return persona metadata by id, or None if not found."""
    return PERSONAS.get(persona_id)


def list_personas() -> list[PersonaMeta]:
    """Return all persona definitions."""
    return list(PERSONAS.values())
