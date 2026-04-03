"""Regression tests for traceback-rich MCP tool errors.

Issue #289: when QA/evaluate crashed unexpectedly, callers only received the
exception message without a traceback, which made root-cause diagnosis slow.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ouroboros.mcp.tools.evaluation_handlers import EvaluateHandler
from ouroboros.mcp.tools.qa import QAHandler


@pytest.mark.asyncio
async def test_qa_handler_returns_traceback_on_unexpected_exception() -> None:
    """QA handler should surface a traceback in the returned MCPToolError."""
    handler = QAHandler()

    with patch(
        "ouroboros.mcp.tools.qa.create_llm_adapter",
        side_effect=RuntimeError("cannot assign to field 'content'"),
    ):
        result = await handler.handle(
            {
                "artifact": "print('hi')",
                "quality_bar": "Output should be valid Python.",
            }
        )

    assert result.is_err
    error_text = str(result.error)
    assert "QA evaluation failed:" in error_text
    assert "Traceback:" in error_text
    assert "cannot assign to field 'content'" in error_text
    assert "RuntimeError" in error_text


@pytest.mark.asyncio
async def test_evaluate_handler_returns_traceback_on_unexpected_exception() -> None:
    """Evaluate handler should surface a traceback in the returned MCPToolError."""
    handler = EvaluateHandler()

    with patch(
        "ouroboros.mcp.tools.evaluation_handlers.create_llm_adapter",
        side_effect=RuntimeError("cannot assign to field 'content'"),
    ):
        result = await handler.handle(
            {
                "session_id": "sess-289",
                "artifact": "stub artifact",
            }
        )

    assert result.is_err
    error_text = str(result.error)
    assert "Evaluation failed:" in error_text
    assert "Traceback:" in error_text
    assert "cannot assign to field 'content'" in error_text
    assert "RuntimeError" in error_text
