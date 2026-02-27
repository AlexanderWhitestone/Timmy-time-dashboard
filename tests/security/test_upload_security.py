import os
import pytest
from fastapi.testclient import TestClient
from dashboard.app import app
from config import settings

client = TestClient(app)

def test_upload_disallowed_extension():
    """
    Test that uploading a file with a disallowed extension fails.
    """
    malicious_content = b"#!/bin/bash\necho 'Hacked'"
    filename = "test_script.sh"
    
    response = client.post(
        "/api/upload",
        files={"file": (filename, malicious_content, "application/x-sh")}
    )
    
    assert response.status_code == 400
    assert "extension" in response.json()["detail"].lower()

def test_upload_large_file():
    """
    Test that uploading a file exceeding the size limit fails.
    """
    # Create content larger than max_upload_size_mb (default 10MB)
    large_content = b"0" * (settings.max_upload_size_mb * 1024 * 1024 + 1024)
    filename = "large_image.jpg"
    
    response = client.post(
        "/api/upload",
        files={"file": (filename, large_content, "image/jpeg")}
    )
    
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()

def test_upload_valid_file():
    """
    Test that uploading a valid file still works.
    """
    valid_content = b"fake image data"
    filename = "test_image.png"
    
    response = client.post(
        "/api/upload",
        files={"file": (filename, valid_content, "image/png")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    
    # Clean up
    filename_in_storage = data["url"].split("/")[-1]
    upload_path = os.path.join("data", "chat-uploads", filename_in_storage)
    if os.path.exists(upload_path):
        os.remove(upload_path)
