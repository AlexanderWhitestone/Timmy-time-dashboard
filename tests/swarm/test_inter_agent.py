"""Tests for timmy_serve/inter_agent.py — agent-to-agent messaging."""

from timmy_serve.inter_agent import InterAgentMessenger


def test_send_message():
    m = InterAgentMessenger()
    msg = m.send("alice", "bob", "hello")
    assert msg.from_agent == "alice"
    assert msg.to_agent == "bob"
    assert msg.content == "hello"


def test_receive_messages():
    m = InterAgentMessenger()
    m.send("alice", "bob", "msg1")
    m.send("alice", "bob", "msg2")
    msgs = m.receive("bob")
    assert len(msgs) == 2


def test_pop_message():
    m = InterAgentMessenger()
    m.send("alice", "bob", "first")
    m.send("alice", "bob", "second")
    msg = m.pop("bob")
    assert msg.content == "first"
    remaining = m.receive("bob")
    assert len(remaining) == 1


def test_pop_empty():
    m = InterAgentMessenger()
    assert m.pop("nobody") is None


def test_pop_all():
    m = InterAgentMessenger()
    m.send("a", "b", "1")
    m.send("a", "b", "2")
    msgs = m.pop_all("b")
    assert len(msgs) == 2
    assert m.receive("b") == []


def test_broadcast():
    m = InterAgentMessenger()
    # Create queues by sending initial messages
    m.send("system", "agent1", "init")
    m.send("system", "agent2", "init")
    m.pop_all("agent1")
    m.pop_all("agent2")
    count = m.broadcast("system", "announcement")
    assert count == 2


def test_history():
    m = InterAgentMessenger()
    m.send("a", "b", "1")
    m.send("b", "a", "2")
    history = m.history()
    assert len(history) == 2


def test_clear_specific():
    m = InterAgentMessenger()
    m.send("a", "b", "msg")
    m.clear("b")
    assert m.receive("b") == []


def test_clear_all():
    m = InterAgentMessenger()
    m.send("a", "b", "msg")
    m.clear()
    assert m.history() == []


def test_max_queue_size():
    m = InterAgentMessenger(max_queue_size=3)
    for i in range(5):
        m.send("a", "b", f"msg{i}")
    msgs = m.receive("b")
    assert len(msgs) == 3
    assert msgs[0].content == "msg2"  # oldest dropped
