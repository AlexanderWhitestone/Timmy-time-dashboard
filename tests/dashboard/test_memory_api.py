"""Tests for the Memory API endpoints.

Verifies that facts can be created, searched, edited, and deleted
through the dashboard memory routes.
"""


def test_memory_page_returns_200(client):
    response = client.get("/memory")
    assert response.status_code == 200
    assert "Memory Browser" in response.text


def test_add_fact_returns_html(client):
    """POST /memory/fact should return HTML partial with the new fact."""
    response = client.post("/memory/fact", data={"fact": "Alexander is the operator"})
    assert response.status_code == 200
    assert "Alexander is the operator" in response.text


def test_add_fact_persists(client):
    """After adding a fact, it should appear on the main memory page."""
    client.post("/memory/fact", data={"fact": "Timmy runs on Qwen"})
    response = client.get("/memory")
    assert response.status_code == 200
    assert "Timmy runs on Qwen" in response.text


def test_memory_search_returns_html(client):
    """POST /memory/search should return HTML partial."""
    response = client.post("/memory/search", data={"query": "test query"})
    assert response.status_code == 200


def test_edit_fact(client):
    """PUT /memory/fact/{id} should update the fact content."""
    # First create a fact
    client.post("/memory/fact", data={"fact": "Original fact"})

    # Get the fact ID from the memory page
    page = client.get("/memory")
    assert "Original fact" in page.text

    # Extract a fact ID from the page (look for fact- pattern)
    import re
    match = re.search(r'id="fact-([^"]+)"', page.text)
    if match:
        fact_id = match.group(1)
        response = client.put(
            f"/memory/fact/{fact_id}",
            json={"content": "Updated fact"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True


def test_delete_fact(client):
    """DELETE /memory/fact/{id} should remove the fact."""
    # Create a fact
    client.post("/memory/fact", data={"fact": "Fact to delete"})

    page = client.get("/memory")
    import re
    match = re.search(r'id="fact-([^"]+)"', page.text)
    if match:
        fact_id = match.group(1)
        response = client.delete(f"/memory/fact/{fact_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True
