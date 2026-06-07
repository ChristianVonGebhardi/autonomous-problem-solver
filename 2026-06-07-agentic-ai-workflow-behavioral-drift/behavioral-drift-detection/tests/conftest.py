"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_tool_sequence():
    return ["search", "retrieve", "classify", "respond"]


@pytest.fixture
def sample_steps():
    return [
        {
            "span_id": "s1",
            "run_id": "r1",
            "workflow_id": "w1",
            "step_index": 0,
            "tool_name": "search",
            "start_time": 1700000000.0,
            "end_time": 1700000001.0,
            "duration_ms": 1000.0,
            "output_text": "Found 5 relevant billing policy documents",
            "confidence": 0.91,
            "retrieved_chunks": [],
            "metadata": {},
            "error": None,
        },
        {
            "span_id": "s2",
            "run_id": "r1",
            "workflow_id": "w1",
            "step_index": 1,
            "tool_name": "retrieve",
            "start_time": 1700000001.0,
            "end_time": 1700000002.0,
            "duration_ms": 1000.0,
            "output_text": "Retrieved policy document: refund within 30 days",
            "confidence": 0.87,
            "retrieved_chunks": ["abc123"],
            "metadata": {},
            "error": None,
        },
        {
            "span_id": "s3",
            "run_id": "r1",
            "workflow_id": "w1",
            "step_index": 2,
            "tool_name": "respond",
            "start_time": 1700000002.0,
            "end_time": 1700000003.0,
            "duration_ms": 1000.0,
            "output_text": "Explained refund policy to the customer",
            "confidence": 0.89,
            "retrieved_chunks": [],
            "metadata": {},
            "error": None,
        },
    ]