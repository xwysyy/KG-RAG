"""Shared pytest configuration."""

import pytest


@pytest.fixture
def sample_user_id():
    return "test-user-001"
