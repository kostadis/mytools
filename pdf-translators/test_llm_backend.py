"""Tests for the provider-agnostic completion backend (llm_backend.py).

The shared transport libs (claudelib / dgxlib) are mocked, so these run without
network access or an API key. They verify:
  * the two backend constructors set kind / supports_batch / anthropic_client
  * Backend.complete threads args to the right lib and returns (text, stop_reason)
  * stop-reason normalisation collapses to "max_tokens" vs "stop" in both libs
"""

from unittest.mock import patch

import llm_backend as lb
import claudelib
import dgxlib


# --- constructors -----------------------------------------------------------

def test_anthropic_backend_shape():
    with patch.object(claudelib, "make_client", return_value="CLIENT"):
        b = lb.anthropic_backend()
    assert b.kind == "claude"
    assert b.supports_batch is True
    assert b.anthropic_client == "CLIENT"


def test_dgx_backend_shape():
    with patch.object(dgxlib, "make_client", return_value="DGXCLIENT"):
        b = lb.dgx_backend("http://host:8001/v1")
    assert b.kind == "dgx"
    assert b.supports_batch is False
    assert b.anthropic_client is None


# --- complete() threads to the right lib ------------------------------------

def test_anthropic_complete_delegates_to_claudelib():
    with patch.object(claudelib, "make_client", return_value="CLIENT"), \
         patch.object(claudelib, "call_api_full",
                      return_value=("text-out", "stop")) as mock_full:
        b = lb.anthropic_backend()
        out = b.complete("SYS", "USER", "model-x", 1234)
    assert out == ("text-out", "stop")
    mock_full.assert_called_once_with("CLIENT", "SYS", "USER", "model-x", 1234)


def test_dgx_complete_delegates_with_thinking_false():
    with patch.object(dgxlib, "make_client", return_value="DGXCLIENT"), \
         patch.object(dgxlib, "call_api_full",
                      return_value=("dgx-text", "max_tokens")) as mock_full:
        b = lb.dgx_backend("http://host:8001/v1")
        out = b.complete("SYS", "USER", "Qwen/Qwen3.5", 999)
    assert out == ("dgx-text", "max_tokens")
    # thinking is forced off so <think> traces never pollute the JSON output.
    mock_full.assert_called_once_with("DGXCLIENT", "SYS", "USER", "Qwen/Qwen3.5",
                                      999, thinking=False)


# --- stop-reason normalisation (the one distinction call_claude needs) ------

def test_claudelib_normalises_stop_reason():
    assert claudelib._norm_stop_reason("max_tokens") == "max_tokens"
    assert claudelib._norm_stop_reason("end_turn") == "stop"
    assert claudelib._norm_stop_reason("stop_sequence") == "stop"
    assert claudelib._norm_stop_reason(None) == "stop"


def test_dgxlib_normalises_finish_reason():
    # OpenAI/vLLM truncation is "length"; everything else collapses to "stop".
    assert dgxlib.client._norm_finish_reason("length") == "max_tokens"
    assert dgxlib.client._norm_finish_reason("stop") == "stop"
    assert dgxlib.client._norm_finish_reason("tool_calls") == "stop"
    assert dgxlib.client._norm_finish_reason(None) == "stop"
