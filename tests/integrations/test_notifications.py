"""Tests for notifications/push.py — push notification system."""

from notifications.push import PushNotifier


def test_notify_creates_notification():
    notifier = PushNotifier(native_enabled=False)
    n = notifier.notify("Test", "Hello world", "system")
    assert n.title == "Test"
    assert n.message == "Hello world"
    assert n.category == "system"
    assert n.read is False


def test_notify_increments_id():
    notifier = PushNotifier(native_enabled=False)
    n1 = notifier.notify("A", "msg1")
    n2 = notifier.notify("B", "msg2")
    assert n2.id > n1.id


def test_recent_returns_latest_first():
    notifier = PushNotifier(native_enabled=False)
    notifier.notify("First", "1")
    notifier.notify("Second", "2")
    recent = notifier.recent(limit=2)
    assert recent[0].title == "Second"
    assert recent[1].title == "First"


def test_recent_filter_by_category():
    notifier = PushNotifier(native_enabled=False)
    notifier.notify("Swarm", "joined", "swarm")
    notifier.notify("System", "boot", "system")
    swarm_only = notifier.recent(category="swarm")
    assert all(n.category == "swarm" for n in swarm_only)


def test_unread_count():
    notifier = PushNotifier(native_enabled=False)
    notifier.notify("A", "1")
    notifier.notify("B", "2")
    assert notifier.unread_count() == 2


def test_mark_read():
    notifier = PushNotifier(native_enabled=False)
    n = notifier.notify("Read me", "msg")
    assert notifier.mark_read(n.id) is True
    assert notifier.unread_count() == 0


def test_mark_read_nonexistent():
    notifier = PushNotifier(native_enabled=False)
    assert notifier.mark_read(9999) is False


def test_mark_all_read():
    notifier = PushNotifier(native_enabled=False)
    notifier.notify("A", "1")
    notifier.notify("B", "2")
    count = notifier.mark_all_read()
    assert count == 2
    assert notifier.unread_count() == 0


def test_clear():
    notifier = PushNotifier(native_enabled=False)
    notifier.notify("A", "1")
    notifier.clear()
    assert notifier.recent() == []


def test_listener_called():
    notifier = PushNotifier(native_enabled=False)
    received = []
    notifier.add_listener(lambda n: received.append(n))
    notifier.notify("Event", "happened")
    assert len(received) == 1
    assert received[0].title == "Event"


def test_max_history():
    notifier = PushNotifier(max_history=5, native_enabled=False)
    for i in range(10):
        notifier.notify(f"N{i}", f"msg{i}")
    assert len(notifier.recent(limit=100)) == 5
