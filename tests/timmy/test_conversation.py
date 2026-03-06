"""Tests for timmy.conversation — conversation context and tool routing."""

import pytest
from timmy.conversation import ConversationContext, ConversationManager


class TestConversationContext:
    """Test ConversationContext dataclass."""

    def test_defaults(self):
        ctx = ConversationContext()
        assert ctx.user_name is None
        assert ctx.current_topic is None
        assert ctx.turn_count == 0

    def test_update_topic(self):
        ctx = ConversationContext()
        ctx.update_topic("Bitcoin price")
        assert ctx.current_topic == "Bitcoin price"
        assert ctx.turn_count == 1

    def test_set_user_name(self):
        ctx = ConversationContext()
        ctx.set_user_name("Alice")
        assert ctx.user_name == "Alice"

    def test_context_summary_empty(self):
        ctx = ConversationContext()
        assert ctx.get_context_summary() == ""

    def test_context_summary_full(self):
        ctx = ConversationContext()
        ctx.set_user_name("Bob")
        ctx.update_topic("coding")
        summary = ctx.get_context_summary()
        assert "Bob" in summary
        assert "coding" in summary
        assert "1" in summary  # turn count


class TestConversationManager:
    """Test ConversationManager."""

    def test_get_context_creates_new(self):
        mgr = ConversationManager()
        ctx = mgr.get_context("session-1")
        assert isinstance(ctx, ConversationContext)

    def test_get_context_returns_same(self):
        mgr = ConversationManager()
        ctx1 = mgr.get_context("s1")
        ctx2 = mgr.get_context("s1")
        assert ctx1 is ctx2

    def test_clear_context(self):
        mgr = ConversationManager()
        mgr.get_context("s1")
        mgr.clear_context("s1")
        # New context should be fresh
        ctx = mgr.get_context("s1")
        assert ctx.turn_count == 0

    def test_clear_nonexistent(self):
        mgr = ConversationManager()
        mgr.clear_context("nope")  # Should not raise


class TestExtractUserName:
    """Test name extraction from messages."""

    def test_my_name_is(self):
        mgr = ConversationManager()
        assert mgr.extract_user_name("My name is Alice") == "Alice"

    def test_i_am(self):
        mgr = ConversationManager()
        assert mgr.extract_user_name("I am Bob") == "Bob"

    def test_call_me(self):
        mgr = ConversationManager()
        assert mgr.extract_user_name("Call me Charlie") == "Charlie"

    def test_im(self):
        mgr = ConversationManager()
        assert mgr.extract_user_name("I'm Dave") == "Dave"

    def test_no_name(self):
        mgr = ConversationManager()
        assert mgr.extract_user_name("What is the weather?") is None

    def test_strips_punctuation(self):
        mgr = ConversationManager()
        assert mgr.extract_user_name("My name is Eve.") == "Eve"


class TestShouldUseTools:
    """Test tool usage detection."""

    def _check(self, message, expected):
        mgr = ConversationManager()
        ctx = ConversationContext()
        assert mgr.should_use_tools(message, ctx) is expected

    def test_search_needs_tools(self):
        self._check("search for Python tutorials", True)

    def test_calculate_needs_tools(self):
        self._check("calculate 2 + 2", True)

    def test_run_command_needs_tools(self):
        self._check("run ls -la", True)

    def test_hello_no_tools(self):
        self._check("hello", False)

    def test_who_are_you_no_tools(self):
        self._check("who are you?", False)

    def test_thanks_no_tools(self):
        self._check("thanks!", False)

    def test_simple_question_no_tools(self):
        self._check("what is Python?", False)

    def test_current_info_needs_tools(self):
        self._check("what is the current price of Bitcoin today?", True)

    def test_ambiguous_defaults_false(self):
        self._check("tell me something interesting", False)

    def test_latest_news_needs_tools(self):
        self._check("what are the latest updates?", True)

    def test_weather_needs_tools(self):
        self._check("weather forecast please", True)
