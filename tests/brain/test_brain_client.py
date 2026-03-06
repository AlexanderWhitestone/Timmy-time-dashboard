"""Tests for brain.client — BrainClient memory + task operations."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brain.client import BrainClient, DEFAULT_RQLITE_URL


class TestBrainClientInit:
    """Test BrainClient initialization."""

    def test_default_url(self):
        client = BrainClient()
        assert client.rqlite_url == DEFAULT_RQLITE_URL

    def test_custom_url(self):
        client = BrainClient(rqlite_url="http://custom:4001")
        assert client.rqlite_url == "http://custom:4001"

    def test_node_id_generated(self):
        client = BrainClient()
        assert client.node_id  # not empty

    def test_custom_node_id(self):
        client = BrainClient(node_id="my-node")
        assert client.node_id == "my-node"

    def test_source_detection(self):
        client = BrainClient()
        assert isinstance(client.source, str)


class TestBrainClientMemory:
    """Test memory operations (remember, recall, get_recent, get_context)."""

    def _make_client(self):
        return BrainClient(rqlite_url="http://test:4001", node_id="test-node")

    async def test_remember_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"last_insert_id": 42}]
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        with patch("brain.client.BrainClient._detect_source", return_value="test"):
            with patch("brain.embeddings.get_embedder") as mock_emb:
                mock_embedder = MagicMock()
                mock_embedder.encode_single.return_value = b"\x00" * 16
                mock_emb.return_value = mock_embedder

                result = await client.remember("test memory", tags=["test"])
                assert result["id"] == 42
                assert result["status"] == "stored"

    async def test_remember_failure_raises(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("brain.embeddings.get_embedder") as mock_emb:
            mock_embedder = MagicMock()
            mock_embedder.encode_single.return_value = b"\x00" * 16
            mock_emb.return_value = mock_embedder

            with pytest.raises(Exception, match="connection refused"):
                await client.remember("fail")

    async def test_recall_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"rows": [
                ["memory content", "test", '{"key": "val"}', 0.1],
            ]}]
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        with patch("brain.embeddings.get_embedder") as mock_emb:
            mock_embedder = MagicMock()
            mock_embedder.encode_single.return_value = b"\x00" * 16
            mock_emb.return_value = mock_embedder

            results = await client.recall("search query")
            assert len(results) == 1
            assert results[0]["content"] == "memory content"
            assert results[0]["metadata"] == {"key": "val"}

    async def test_recall_with_source_filter(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"rows": []}]}
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        with patch("brain.embeddings.get_embedder") as mock_emb:
            mock_embedder = MagicMock()
            mock_embedder.encode_single.return_value = b"\x00" * 16
            mock_emb.return_value = mock_embedder

            results = await client.recall("test", sources=["timmy", "user"])
            assert results == []
            # Check that sources were passed in the SQL
            call_args = client._client.post.call_args
            sql_params = call_args[1]["json"]
            assert "timmy" in sql_params[1] or "timmy" in str(sql_params)

    async def test_recall_error_returns_empty(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock(side_effect=Exception("timeout"))

        with patch("brain.embeddings.get_embedder") as mock_emb:
            mock_embedder = MagicMock()
            mock_embedder.encode_single.return_value = b"\x00" * 16
            mock_emb.return_value = mock_embedder

            results = await client.recall("test")
            assert results == []

    async def test_get_recent_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"rows": [
                [1, "recent memory", "test", '["tag1"]', '{}', "2026-03-06T00:00:00"],
            ]}]
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        memories = await client.get_recent(hours=24, limit=10)
        assert len(memories) == 1
        assert memories[0]["content"] == "recent memory"
        assert memories[0]["tags"] == ["tag1"]

    async def test_get_recent_error_returns_empty(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock(side_effect=Exception("db error"))

        result = await client.get_recent()
        assert result == []

    async def test_get_context(self):
        client = self._make_client()
        client.get_recent = AsyncMock(return_value=[
            {"content": "Recent item 1"},
            {"content": "Recent item 2"},
        ])
        client.recall = AsyncMock(return_value=[
            {"content": "Relevant item 1"},
        ])

        ctx = await client.get_context("test query")
        assert "Recent activity:" in ctx
        assert "Recent item 1" in ctx
        assert "Relevant memories:" in ctx
        assert "Relevant item 1" in ctx


class TestBrainClientTasks:
    """Test task queue operations."""

    def _make_client(self):
        return BrainClient(rqlite_url="http://test:4001", node_id="test-node")

    async def test_submit_task(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"last_insert_id": 7}]
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.submit_task("do something", task_type="shell")
        assert result["id"] == 7
        assert result["status"] == "queued"

    async def test_submit_task_failure_raises(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock(side_effect=Exception("network error"))

        with pytest.raises(Exception, match="network error"):
            await client.submit_task("fail task")

    async def test_claim_task_found(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"rows": [
                [1, "task content", "shell", 5, '{"key": "val"}']
            ]}]
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        task = await client.claim_task(["shell", "general"])
        assert task is not None
        assert task["id"] == 1
        assert task["content"] == "task content"
        assert task["metadata"] == {"key": "val"}

    async def test_claim_task_none_available(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"rows": []}]}
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        task = await client.claim_task(["shell"])
        assert task is None

    async def test_claim_task_error_returns_none(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock(side_effect=Exception("raft error"))

        task = await client.claim_task(["general"])
        assert task is None

    async def test_complete_task(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock()

        # Should not raise
        await client.complete_task(1, success=True, result="done")
        client._client.post.assert_awaited_once()

    async def test_complete_task_failure(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock()

        await client.complete_task(1, success=False, error="oops")
        client._client.post.assert_awaited_once()

    async def test_get_pending_tasks(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"rows": [
                [1, "task 1", "general", 0, '{}', "2026-03-06"],
                [2, "task 2", "shell", 5, '{}', "2026-03-06"],
            ]}]
        }
        mock_response.raise_for_status = MagicMock()
        client._client = MagicMock()
        client._client.post = AsyncMock(return_value=mock_response)

        tasks = await client.get_pending_tasks()
        assert len(tasks) == 2

    async def test_get_pending_tasks_error(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.post = AsyncMock(side_effect=Exception("fail"))

        result = await client.get_pending_tasks()
        assert result == []

    async def test_close(self):
        client = self._make_client()
        client._client = MagicMock()
        client._client.aclose = AsyncMock()

        await client.close()
        client._client.aclose.assert_awaited_once()
