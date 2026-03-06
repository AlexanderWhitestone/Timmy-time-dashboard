"""Tests for inter-agent messaging system."""

from timmy_serve.inter_agent import AgentMessage, InterAgentMessenger, messenger


class TestAgentMessage:
    def test_defaults(self):
        msg = AgentMessage()
        assert msg.from_agent == ""
        assert msg.to_agent == ""
        assert msg.content == ""
        assert msg.message_type == "text"
        assert msg.replied is False
        assert msg.id  # UUID should be generated
        assert msg.timestamp  # timestamp should be generated

    def test_custom_fields(self):
        msg = AgentMessage(
            from_agent="seer", to_agent="forge",
            content="hello", message_type="command",
        )
        assert msg.from_agent == "seer"
        assert msg.to_agent == "forge"
        assert msg.content == "hello"
        assert msg.message_type == "command"


class TestInterAgentMessenger:
    def setup_method(self):
        self.m = InterAgentMessenger(max_queue_size=100)

    def test_send_and_receive(self):
        msg = self.m.send("seer", "forge", "build this")
        assert msg.from_agent == "seer"
        assert msg.to_agent == "forge"
        received = self.m.receive("forge")
        assert len(received) == 1
        assert received[0].content == "build this"

    def test_receive_empty(self):
        assert self.m.receive("nobody") == []

    def test_pop(self):
        self.m.send("a", "b", "first")
        self.m.send("a", "b", "second")
        msg = self.m.pop("b")
        assert msg.content == "first"
        msg2 = self.m.pop("b")
        assert msg2.content == "second"
        assert self.m.pop("b") is None

    def test_pop_empty(self):
        assert self.m.pop("nobody") is None

    def test_pop_all(self):
        self.m.send("a", "b", "one")
        self.m.send("a", "b", "two")
        msgs = self.m.pop_all("b")
        assert len(msgs) == 2
        assert self.m.receive("b") == []

    def test_pop_all_empty(self):
        assert self.m.pop_all("nobody") == []

    def test_broadcast(self):
        # Set up queues for agents
        self.m.send("setup", "forge", "init")
        self.m.send("setup", "echo", "init")
        self.m.pop_all("forge")
        self.m.pop_all("echo")

        count = self.m.broadcast("seer", "alert")
        assert count == 2
        assert len(self.m.receive("forge")) == 1
        assert len(self.m.receive("echo")) == 1

    def test_broadcast_excludes_sender(self):
        self.m.send("setup", "seer", "init")
        self.m.pop_all("seer")
        count = self.m.broadcast("seer", "hello")
        assert count == 0  # no other agents

    def test_history(self):
        self.m.send("a", "b", "msg1")
        self.m.send("b", "a", "msg2")
        history = self.m.history(limit=50)
        assert len(history) == 2

    def test_history_limit(self):
        for i in range(10):
            self.m.send("a", "b", f"msg{i}")
        assert len(self.m.history(limit=3)) == 3

    def test_clear_specific_agent(self):
        self.m.send("a", "b", "hello")
        self.m.send("a", "c", "world")
        self.m.clear("b")
        assert self.m.receive("b") == []
        assert len(self.m.receive("c")) == 1

    def test_clear_all(self):
        self.m.send("a", "b", "hello")
        self.m.send("a", "c", "world")
        self.m.clear()
        assert self.m.receive("b") == []
        assert self.m.receive("c") == []
        assert self.m.history() == []

    def test_module_singleton(self):
        assert isinstance(messenger, InterAgentMessenger)
