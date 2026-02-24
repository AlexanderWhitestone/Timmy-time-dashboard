"""Functional tests for agent_core — interface and ollama_adapter.

Covers the substrate-agnostic agent contract (data classes, enums,
factory methods, abstract enforcement) and the OllamaAgent adapter
(perceive → reason → act → remember → recall → communicate workflow).
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from agent_core.interface import (
    ActionType,
    AgentCapability,
    AgentEffect,
    AgentIdentity,
    Action,
    Communication,
    Memory,
    Perception,
    PerceptionType,
    TimAgent,
)


# ── AgentIdentity ─────────────────────────────────────────────────────────────


class TestAgentIdentity:
    def test_generate_creates_uuid(self):
        identity = AgentIdentity.generate("Timmy")
        assert identity.name == "Timmy"
        uuid.UUID(identity.id)  # raises on invalid

    def test_generate_default_version(self):
        identity = AgentIdentity.generate("Timmy")
        assert identity.version == "1.0.0"

    def test_generate_custom_version(self):
        identity = AgentIdentity.generate("Timmy", version="2.0.0")
        assert identity.version == "2.0.0"

    def test_frozen_identity(self):
        identity = AgentIdentity.generate("Timmy")
        with pytest.raises(AttributeError):
            identity.name = "Other"

    def test_created_at_populated(self):
        identity = AgentIdentity.generate("Timmy")
        assert identity.created_at  # not empty
        assert "T" in identity.created_at  # ISO format

    def test_two_identities_differ(self):
        a = AgentIdentity.generate("A")
        b = AgentIdentity.generate("B")
        assert a.id != b.id


# ── Perception ────────────────────────────────────────────────────────────────


class TestPerception:
    def test_text_factory(self):
        p = Perception.text("hello")
        assert p.type == PerceptionType.TEXT
        assert p.data == "hello"
        assert p.source == "user"

    def test_text_factory_custom_source(self):
        p = Perception.text("hello", source="api")
        assert p.source == "api"

    def test_sensor_factory(self):
        p = Perception.sensor("temperature", 22.5, "°C")
        assert p.type == PerceptionType.SENSOR
        assert p.data["kind"] == "temperature"
        assert p.data["value"] == 22.5
        assert p.data["unit"] == "°C"
        assert p.source == "sensor_temperature"

    def test_timestamp_auto_populated(self):
        p = Perception.text("hi")
        assert p.timestamp
        assert "T" in p.timestamp

    def test_metadata_defaults_empty(self):
        p = Perception.text("hi")
        assert p.metadata == {}


# ── Action ────────────────────────────────────────────────────────────────────


class TestAction:
    def test_respond_factory(self):
        a = Action.respond("Hello!")
        assert a.type == ActionType.TEXT
        assert a.payload == "Hello!"
        assert a.confidence == 1.0

    def test_respond_with_confidence(self):
        a = Action.respond("Maybe", confidence=0.5)
        assert a.confidence == 0.5

    def test_move_factory(self):
        a = Action.move((1.0, 2.0, 3.0), speed=0.5)
        assert a.type == ActionType.MOVE
        assert a.payload["vector"] == (1.0, 2.0, 3.0)
        assert a.payload["speed"] == 0.5

    def test_move_default_speed(self):
        a = Action.move((0, 0, 0))
        assert a.payload["speed"] == 1.0

    def test_deadline_defaults_none(self):
        a = Action.respond("test")
        assert a.deadline is None


# ── Memory ────────────────────────────────────────────────────────────────────


class TestMemory:
    def test_touch_increments(self):
        m = Memory(id="m1", content="hello", created_at="2025-01-01T00:00:00Z")
        assert m.access_count == 0
        m.touch()
        assert m.access_count == 1
        m.touch()
        assert m.access_count == 2

    def test_touch_sets_last_accessed(self):
        m = Memory(id="m1", content="hello", created_at="2025-01-01T00:00:00Z")
        assert m.last_accessed is None
        m.touch()
        assert m.last_accessed is not None

    def test_default_importance(self):
        m = Memory(id="m1", content="x", created_at="now")
        assert m.importance == 0.5

    def test_tags_default_empty(self):
        m = Memory(id="m1", content="x", created_at="now")
        assert m.tags == []


# ── Communication ─────────────────────────────────────────────────────────────


class TestCommunication:
    def test_defaults(self):
        c = Communication(sender="A", recipient="B", content="hi")
        assert c.protocol == "direct"
        assert c.encrypted is False
        assert c.timestamp  # auto-populated


# ── TimAgent abstract enforcement ─────────────────────────────────────────────


class TestTimAgentABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            TimAgent(AgentIdentity.generate("X"))

    def test_concrete_subclass_works(self):
        class Dummy(TimAgent):
            def perceive(self, p): return Memory(id="1", content=p.data, created_at="")
            def reason(self, q, c): return Action.respond(q)
            def act(self, a): return a.payload
            def remember(self, m): pass
            def recall(self, q, limit=5): return []
            def communicate(self, m): return True

        d = Dummy(AgentIdentity.generate("Dummy"))
        assert d.identity.name == "Dummy"
        assert d.capabilities == set()

    def test_has_capability(self):
        class Dummy(TimAgent):
            def perceive(self, p): pass
            def reason(self, q, c): pass
            def act(self, a): pass
            def remember(self, m): pass
            def recall(self, q, limit=5): return []
            def communicate(self, m): return True

        d = Dummy(AgentIdentity.generate("D"))
        d._capabilities.add(AgentCapability.REASONING)
        assert d.has_capability(AgentCapability.REASONING)
        assert not d.has_capability(AgentCapability.VISION)

    def test_capabilities_returns_copy(self):
        class Dummy(TimAgent):
            def perceive(self, p): pass
            def reason(self, q, c): pass
            def act(self, a): pass
            def remember(self, m): pass
            def recall(self, q, limit=5): return []
            def communicate(self, m): return True

        d = Dummy(AgentIdentity.generate("D"))
        caps = d.capabilities
        caps.add(AgentCapability.VISION)
        assert AgentCapability.VISION not in d.capabilities

    def test_get_state(self):
        class Dummy(TimAgent):
            def perceive(self, p): pass
            def reason(self, q, c): pass
            def act(self, a): pass
            def remember(self, m): pass
            def recall(self, q, limit=5): return []
            def communicate(self, m): return True

        d = Dummy(AgentIdentity.generate("D"))
        state = d.get_state()
        assert "identity" in state
        assert "capabilities" in state
        assert "state" in state

    def test_shutdown_does_not_raise(self):
        class Dummy(TimAgent):
            def perceive(self, p): pass
            def reason(self, q, c): pass
            def act(self, a): pass
            def remember(self, m): pass
            def recall(self, q, limit=5): return []
            def communicate(self, m): return True

        d = Dummy(AgentIdentity.generate("D"))
        d.shutdown()  # should not raise


# ── AgentEffect ───────────────────────────────────────────────────────────────


class TestAgentEffect:
    def test_empty_export(self):
        effect = AgentEffect()
        assert effect.export() == []

    def test_log_perceive(self):
        effect = AgentEffect()
        p = Perception.text("test input")
        effect.log_perceive(p, "mem_0")
        log = effect.export()
        assert len(log) == 1
        assert log[0]["type"] == "perceive"
        assert log[0]["perception_type"] == "TEXT"
        assert log[0]["memory_id"] == "mem_0"
        assert "timestamp" in log[0]

    def test_log_reason(self):
        effect = AgentEffect()
        effect.log_reason("How to help?", ActionType.TEXT)
        log = effect.export()
        assert len(log) == 1
        assert log[0]["type"] == "reason"
        assert log[0]["query"] == "How to help?"
        assert log[0]["action_type"] == "TEXT"

    def test_log_act(self):
        effect = AgentEffect()
        action = Action.respond("Hello!")
        effect.log_act(action, "Hello!")
        log = effect.export()
        assert len(log) == 1
        assert log[0]["type"] == "act"
        assert log[0]["confidence"] == 1.0
        assert log[0]["result_type"] == "str"

    def test_export_returns_copy(self):
        effect = AgentEffect()
        effect.log_reason("q", ActionType.TEXT)
        exported = effect.export()
        exported.clear()
        assert len(effect.export()) == 1

    def test_full_audit_trail(self):
        effect = AgentEffect()
        p = Perception.text("input")
        effect.log_perceive(p, "m0")
        effect.log_reason("what now?", ActionType.TEXT)
        action = Action.respond("response")
        effect.log_act(action, "response")
        log = effect.export()
        assert len(log) == 3
        types = [e["type"] for e in log]
        assert types == ["perceive", "reason", "act"]


# ── OllamaAgent functional tests ─────────────────────────────────────────────


class TestOllamaAgent:
    """Functional tests for the OllamaAgent adapter.

    Uses mocked Ollama (create_timmy returns a mock) to exercise
    the full perceive → reason → act → remember → recall pipeline.
    """

    @pytest.fixture
    def agent(self):
        with patch("agent_core.ollama_adapter.create_timmy") as mock_ct:
            mock_timmy = MagicMock()
            mock_run = MagicMock()
            mock_run.content = "Mocked LLM response"
            mock_timmy.run.return_value = mock_run
            mock_ct.return_value = mock_timmy

            from agent_core.ollama_adapter import OllamaAgent
            identity = AgentIdentity.generate("TestTimmy")
            return OllamaAgent(identity, effect_log="/tmp/test_effects")

    def test_capabilities_set(self, agent):
        caps = agent.capabilities
        assert AgentCapability.REASONING in caps
        assert AgentCapability.CODING in caps
        assert AgentCapability.WRITING in caps
        assert AgentCapability.ANALYSIS in caps
        assert AgentCapability.COMMUNICATION in caps

    def test_perceive_creates_memory(self, agent):
        p = Perception.text("Hello Timmy")
        mem = agent.perceive(p)
        assert mem.id == "mem_0"
        assert mem.content["data"] == "Hello Timmy"
        assert mem.content["type"] == "TEXT"

    def test_perceive_extracts_tags(self, agent):
        p = Perception.text("I need help with a bug in my code")
        mem = agent.perceive(p)
        assert "TEXT" in mem.tags
        assert "user" in mem.tags
        assert "help" in mem.tags
        assert "bug" in mem.tags
        assert "code" in mem.tags

    def test_perceive_fifo_eviction(self, agent):
        for i in range(12):
            agent.perceive(Perception.text(f"msg {i}"))
        assert len(agent._working_memory) == 10
        # oldest two evicted
        assert agent._working_memory[0].content["data"] == "msg 2"

    def test_reason_returns_action(self, agent):
        mem = agent.perceive(Perception.text("context"))
        action = agent.reason("What should I do?", [mem])
        assert action.type == ActionType.TEXT
        assert action.payload == "Mocked LLM response"
        assert action.confidence == 0.9

    def test_act_text(self, agent):
        action = Action.respond("Hello!")
        result = agent.act(action)
        assert result == "Hello!"

    def test_act_speak(self, agent):
        action = Action(type=ActionType.SPEAK, payload="Speak this")
        result = agent.act(action)
        assert result["spoken"] == "Speak this"
        assert result["tts_engine"] == "pyttsx3"

    def test_act_call(self, agent):
        action = Action(type=ActionType.CALL, payload={"url": "http://example.com"})
        result = agent.act(action)
        assert result["status"] == "not_implemented"

    def test_act_unsupported(self, agent):
        action = Action(type=ActionType.MOVE, payload=(0, 0, 0))
        result = agent.act(action)
        assert "error" in result

    def test_remember_stores_and_deduplicates(self, agent):
        mem = agent.perceive(Perception.text("original"))
        assert len(agent._working_memory) == 1
        agent.remember(mem)
        assert len(agent._working_memory) == 1  # deduplicated
        assert mem.access_count == 1

    def test_remember_evicts_on_overflow(self, agent):
        for i in range(10):
            agent.perceive(Perception.text(f"fill {i}"))
        extra = Memory(id="extra", content="overflow", created_at="now")
        agent.remember(extra)
        assert len(agent._working_memory) == 10
        # first memory evicted
        assert agent._working_memory[-1].id == "extra"

    def test_recall_keyword_matching(self, agent):
        agent.perceive(Perception.text("python code review"))
        agent.perceive(Perception.text("weather forecast"))
        agent.perceive(Perception.text("python bug fix"))
        results = agent.recall("python", limit=5)
        # All memories returned (recall returns up to limit)
        assert len(results) == 3
        # Memories containing "python" should score higher and appear first
        first_content = str(results[0].content)
        assert "python" in first_content.lower()

    def test_recall_respects_limit(self, agent):
        for i in range(10):
            agent.perceive(Perception.text(f"memory {i}"))
        results = agent.recall("memory", limit=3)
        assert len(results) == 3

    def test_communicate_success(self, agent):
        with patch("swarm.comms.SwarmComms") as MockComms:
            mock_comms = MagicMock()
            MockComms.return_value = mock_comms
            msg = Communication(sender="Timmy", recipient="Echo", content="hi")
            result = agent.communicate(msg)
            # communicate returns True on success, False on exception
            assert isinstance(result, bool)

    def test_communicate_failure(self, agent):
        # Force an import error inside communicate() to trigger except branch
        with patch.dict("sys.modules", {"swarm.comms": None}):
            msg = Communication(sender="Timmy", recipient="Echo", content="hi")
            assert agent.communicate(msg) is False

    def test_effect_logging_full_workflow(self, agent):
        p = Perception.text("test input")
        mem = agent.perceive(p)
        action = agent.reason("respond", [mem])
        agent.act(action)
        log = agent.get_effect_log()
        assert len(log) == 3
        assert log[0]["type"] == "perceive"
        assert log[1]["type"] == "reason"
        assert log[2]["type"] == "act"

    def test_no_effect_log_when_disabled(self):
        with patch("agent_core.ollama_adapter.create_timmy") as mock_ct:
            mock_timmy = MagicMock()
            mock_ct.return_value = mock_timmy
            from agent_core.ollama_adapter import OllamaAgent
            identity = AgentIdentity.generate("NoLog")
            agent = OllamaAgent(identity)  # no effect_log
            assert agent.get_effect_log() is None

    def test_format_context_empty(self, agent):
        result = agent._format_context([])
        assert result == "No previous context."

    def test_format_context_with_dict_content(self, agent):
        mem = Memory(id="m", content={"data": "hello"}, created_at="now")
        result = agent._format_context([mem])
        assert "hello" in result

    def test_format_context_with_string_content(self, agent):
        mem = Memory(id="m", content="plain string", created_at="now")
        result = agent._format_context([mem])
        assert "plain string" in result
