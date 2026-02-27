"""Tests for reward model scoring in the swarm learner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from swarm.learner import (
    RewardScore,
    get_reward_scores,
    score_output,
)


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path):
    """Point the learner at a temporary database."""
    db = tmp_path / "learner_test.db"
    with patch("swarm.learner.DB_PATH", db):
        yield


class TestScoreOutput:
    """Test the score_output function."""

    def test_returns_none_when_disabled(self):
        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = False
            result = score_output("task-1", "agent-1", "do X", "done X")
        assert result is None

    def test_returns_none_when_no_model(self):
        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = ""
            with patch(
                "infrastructure.models.registry.model_registry"
            ) as mock_reg:
                mock_reg.get_reward_model.return_value = None
                result = score_output("task-1", "agent-1", "do X", "done X")
        assert result is None

    def test_positive_scoring(self):
        """All votes return GOOD → score = 1.0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "GOOD"}

        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = "test-model"
            mock_s.reward_model_votes = 3
            mock_s.ollama_url = "http://localhost:11434"

            with patch("requests.post", return_value=mock_response):
                result = score_output("task-1", "agent-1", "do X", "done X")

        assert result is not None
        assert result.score == 1.0
        assert result.positive_votes == 3
        assert result.negative_votes == 0
        assert result.total_votes == 3
        assert result.model_used == "test-model"

    def test_negative_scoring(self):
        """All votes return BAD → score = -1.0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "BAD"}

        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = "test-model"
            mock_s.reward_model_votes = 3
            mock_s.ollama_url = "http://localhost:11434"

            with patch("requests.post", return_value=mock_response):
                result = score_output("task-1", "agent-1", "do X", "bad output")

        assert result is not None
        assert result.score == -1.0
        assert result.negative_votes == 3

    def test_mixed_scoring(self):
        """2 GOOD + 1 BAD → score ≈ 0.33."""
        responses = []
        for text in ["GOOD", "GOOD", "BAD"]:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": text}
            responses.append(resp)

        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = "test-model"
            mock_s.reward_model_votes = 3
            mock_s.ollama_url = "http://localhost:11434"

            with patch("requests.post", side_effect=responses):
                result = score_output("task-1", "agent-1", "do X", "ok output")

        assert result is not None
        assert abs(result.score - (1 / 3)) < 0.01
        assert result.positive_votes == 2
        assert result.negative_votes == 1

    def test_uses_registry_reward_model(self):
        """Falls back to registry reward model when setting is empty."""
        mock_model = MagicMock()
        mock_model.path = "registry-reward-model"
        mock_model.format = MagicMock()
        mock_model.format.value = "ollama"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "GOOD"}

        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = ""
            mock_s.reward_model_votes = 1
            mock_s.ollama_url = "http://localhost:11434"

            with patch(
                "infrastructure.models.registry.model_registry"
            ) as mock_reg:
                mock_reg.get_reward_model.return_value = mock_model

                with patch("requests.post", return_value=mock_response):
                    result = score_output("task-1", "agent-1", "do X", "ok")

        assert result is not None
        assert result.model_used == "registry-reward-model"


class TestGetRewardScores:
    """Test retrieving historical reward scores."""

    def test_empty_history(self):
        scores = get_reward_scores()
        assert scores == []

    def test_scores_persisted(self):
        """Scores from score_output are retrievable."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "GOOD"}

        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = "test-model"
            mock_s.reward_model_votes = 1
            mock_s.ollama_url = "http://localhost:11434"

            with patch("requests.post", return_value=mock_response):
                score_output("task-1", "agent-1", "do X", "done X")

        scores = get_reward_scores()
        assert len(scores) == 1
        assert scores[0]["task_id"] == "task-1"
        assert scores[0]["agent_id"] == "agent-1"
        assert scores[0]["score"] == 1.0

    def test_filter_by_agent(self):
        """Filter scores by agent_id."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "GOOD"}

        with patch("swarm.learner._settings") as mock_s:
            mock_s.reward_model_enabled = True
            mock_s.reward_model_name = "test-model"
            mock_s.reward_model_votes = 1
            mock_s.ollama_url = "http://localhost:11434"

            with patch("requests.post", return_value=mock_response):
                score_output("task-1", "agent-1", "task A", "output A")
                score_output("task-2", "agent-2", "task B", "output B")

        agent1_scores = get_reward_scores(agent_id="agent-1")
        assert len(agent1_scores) == 1
        assert agent1_scores[0]["agent_id"] == "agent-1"


class TestRewardScoreDataclass:
    """Test RewardScore construction."""

    def test_create_score(self):
        score = RewardScore(
            score=0.5,
            positive_votes=3,
            negative_votes=1,
            total_votes=4,
            model_used="test-model",
        )
        assert score.score == 0.5
        assert score.total_votes == 4
