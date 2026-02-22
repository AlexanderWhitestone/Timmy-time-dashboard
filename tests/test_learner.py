"""Tests for swarm.learner — outcome tracking and adaptive bid intelligence."""

import pytest


@pytest.fixture(autouse=True)
def tmp_learner_db(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.learner.DB_PATH", db_path)
    yield db_path


# ── keyword extraction ───────────────────────────────────────────────────────

def test_extract_keywords_strips_stop_words():
    from swarm.learner import _extract_keywords
    kws = _extract_keywords("please research the security vulnerability")
    assert "please" not in kws
    assert "the" not in kws
    assert "research" in kws
    assert "security" in kws
    assert "vulnerability" in kws


def test_extract_keywords_ignores_short_words():
    from swarm.learner import _extract_keywords
    kws = _extract_keywords("do it or go")
    assert kws == []


def test_extract_keywords_lowercases():
    from swarm.learner import _extract_keywords
    kws = _extract_keywords("Deploy Kubernetes Cluster")
    assert "deploy" in kws
    assert "kubernetes" in kws
    assert "cluster" in kws


# ── record_outcome ───────────────────────────────────────────────────────────

def test_record_outcome_stores_data():
    from swarm.learner import record_outcome, get_metrics
    record_outcome("t1", "agent-a", "fix the bug", 30, won_auction=True)
    m = get_metrics("agent-a")
    assert m.total_bids == 1
    assert m.auctions_won == 1


def test_record_outcome_with_failure():
    from swarm.learner import record_outcome, get_metrics
    record_outcome("t2", "agent-b", "deploy server", 50, won_auction=True, task_succeeded=False)
    m = get_metrics("agent-b")
    assert m.tasks_failed == 1
    assert m.success_rate == 0.0


def test_record_outcome_losing_bid():
    from swarm.learner import record_outcome, get_metrics
    record_outcome("t3", "agent-c", "write docs", 80, won_auction=False)
    m = get_metrics("agent-c")
    assert m.total_bids == 1
    assert m.auctions_won == 0


# ── record_task_result ───────────────────────────────────────────────────────

def test_record_task_result_updates_success():
    from swarm.learner import record_outcome, record_task_result, get_metrics
    record_outcome("t4", "agent-d", "analyse data", 40, won_auction=True)
    updated = record_task_result("t4", "agent-d", succeeded=True)
    assert updated == 1
    m = get_metrics("agent-d")
    assert m.tasks_completed == 1
    assert m.success_rate == 1.0


def test_record_task_result_updates_failure():
    from swarm.learner import record_outcome, record_task_result, get_metrics
    record_outcome("t5", "agent-e", "deploy kubernetes", 60, won_auction=True)
    record_task_result("t5", "agent-e", succeeded=False)
    m = get_metrics("agent-e")
    assert m.tasks_failed == 1
    assert m.success_rate == 0.0


def test_record_task_result_no_match_returns_zero():
    from swarm.learner import record_task_result
    updated = record_task_result("no-task", "no-agent", succeeded=True)
    assert updated == 0


# ── get_metrics ──────────────────────────────────────────────────────────────

def test_metrics_empty_agent():
    from swarm.learner import get_metrics
    m = get_metrics("ghost")
    assert m.total_bids == 0
    assert m.win_rate == 0.0
    assert m.success_rate == 0.0
    assert m.keyword_wins == {}


def test_metrics_win_rate():
    from swarm.learner import record_outcome, get_metrics
    record_outcome("t10", "agent-f", "research topic", 30, won_auction=True)
    record_outcome("t11", "agent-f", "research other", 40, won_auction=False)
    record_outcome("t12", "agent-f", "find sources", 35, won_auction=True)
    record_outcome("t13", "agent-f", "summarize report", 50, won_auction=False)
    m = get_metrics("agent-f")
    assert m.total_bids == 4
    assert m.auctions_won == 2
    assert m.win_rate == pytest.approx(0.5)


def test_metrics_keyword_tracking():
    from swarm.learner import record_outcome, record_task_result, get_metrics
    record_outcome("t20", "agent-g", "research security vulnerability", 30, won_auction=True)
    record_task_result("t20", "agent-g", succeeded=True)
    record_outcome("t21", "agent-g", "research market trends", 30, won_auction=True)
    record_task_result("t21", "agent-g", succeeded=False)
    m = get_metrics("agent-g")
    assert m.keyword_wins.get("research", 0) == 1
    assert m.keyword_wins.get("security", 0) == 1
    assert m.keyword_failures.get("research", 0) == 1
    assert m.keyword_failures.get("market", 0) == 1


def test_metrics_avg_winning_bid():
    from swarm.learner import record_outcome, get_metrics
    record_outcome("t30", "agent-h", "task one", 20, won_auction=True)
    record_outcome("t31", "agent-h", "task two", 40, won_auction=True)
    record_outcome("t32", "agent-h", "task three", 100, won_auction=False)
    m = get_metrics("agent-h")
    assert m.avg_winning_bid == pytest.approx(30.0)


# ── get_all_metrics ──────────────────────────────────────────────────────────

def test_get_all_metrics_empty():
    from swarm.learner import get_all_metrics
    assert get_all_metrics() == {}


def test_get_all_metrics_multiple_agents():
    from swarm.learner import record_outcome, get_all_metrics
    record_outcome("t40", "alice", "fix bug", 20, won_auction=True)
    record_outcome("t41", "bob", "write docs", 30, won_auction=False)
    all_m = get_all_metrics()
    assert "alice" in all_m
    assert "bob" in all_m
    assert all_m["alice"].auctions_won == 1
    assert all_m["bob"].auctions_won == 0


# ── suggest_bid ──────────────────────────────────────────────────────────────

def test_suggest_bid_returns_base_when_insufficient_data():
    from swarm.learner import suggest_bid
    result = suggest_bid("new-agent", "research something", 50)
    assert result == 50


def test_suggest_bid_lowers_on_low_win_rate():
    from swarm.learner import record_outcome, suggest_bid
    # Agent loses 9 out of 10 auctions → very low win rate → should bid lower
    for i in range(9):
        record_outcome(f"loss-{i}", "loser", "generic task description", 50, won_auction=False)
    record_outcome("win-0", "loser", "generic task description", 50, won_auction=True)
    bid = suggest_bid("loser", "generic task description", 50)
    assert bid < 50


def test_suggest_bid_raises_on_high_win_rate():
    from swarm.learner import record_outcome, suggest_bid
    # Agent wins all auctions → high win rate → should bid higher
    for i in range(5):
        record_outcome(f"win-{i}", "winner", "generic task description", 30, won_auction=True)
    bid = suggest_bid("winner", "generic task description", 30)
    assert bid > 30


def test_suggest_bid_backs_off_on_poor_success():
    from swarm.learner import record_outcome, record_task_result, suggest_bid
    # Agent wins but fails tasks → should bid higher to avoid winning
    for i in range(4):
        record_outcome(f"fail-{i}", "failer", "deploy server config", 40, won_auction=True)
        record_task_result(f"fail-{i}", "failer", succeeded=False)
    bid = suggest_bid("failer", "deploy server config", 40)
    assert bid > 40


def test_suggest_bid_leans_in_on_keyword_strength():
    from swarm.learner import record_outcome, record_task_result, suggest_bid
    # Agent has strong track record on "security" keyword
    for i in range(4):
        record_outcome(f"sec-{i}", "sec-agent", "audit security vulnerability", 50, won_auction=True)
        record_task_result(f"sec-{i}", "sec-agent", succeeded=True)
    bid = suggest_bid("sec-agent", "check security audit", 50)
    assert bid < 50


def test_suggest_bid_never_below_one():
    from swarm.learner import record_outcome, suggest_bid
    for i in range(5):
        record_outcome(f"cheap-{i}", "cheapo", "task desc here", 1, won_auction=False)
    bid = suggest_bid("cheapo", "task desc here", 1)
    assert bid >= 1


# ── learned_keywords ─────────────────────────────────────────────────────────

def test_learned_keywords_empty():
    from swarm.learner import learned_keywords
    assert learned_keywords("nobody") == []


def test_learned_keywords_ranked_by_net():
    from swarm.learner import record_outcome, record_task_result, learned_keywords
    # "security" → 3 wins, 0 failures = net +3
    # "deploy" → 1 win, 2 failures = net -1
    for i in range(3):
        record_outcome(f"sw-{i}", "ranker", "audit security scan", 30, won_auction=True)
        record_task_result(f"sw-{i}", "ranker", succeeded=True)
    record_outcome("dw-0", "ranker", "deploy docker container", 40, won_auction=True)
    record_task_result("dw-0", "ranker", succeeded=True)
    for i in range(2):
        record_outcome(f"df-{i}", "ranker", "deploy kubernetes cluster", 40, won_auction=True)
        record_task_result(f"df-{i}", "ranker", succeeded=False)

    kws = learned_keywords("ranker")
    kw_map = {k["keyword"]: k for k in kws}
    assert kw_map["security"]["net"] > 0
    assert kw_map["deploy"]["net"] < 0
    # security should rank above deploy
    sec_idx = next(i for i, k in enumerate(kws) if k["keyword"] == "security")
    dep_idx = next(i for i, k in enumerate(kws) if k["keyword"] == "deploy")
    assert sec_idx < dep_idx
