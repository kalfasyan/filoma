"""Tests for the top-level ``filoma.ask()`` convenience.

All tests are fully mocked: no live LLM, no network. The point is to verify
the ergonomic surface (auto-instantiation against ``cwd`` or a given path,
correct forwarding to ``FilarakiAgent.run()``).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import filoma


class _StubAgent:
    """Records calls made to ``run()``."""

    def __init__(self, working_dir: str):
        self.default_working_dir = working_dir
        self.run_calls: list = []

    def run(self, prompt, message_history=None):
        self.run_calls.append({"prompt": prompt, "message_history": message_history})
        return MagicMock(output=f"stub-response-for:{prompt}")


def test_ask_uses_cwd_by_default(monkeypatch):
    captured: dict = {}

    def fake_get_agent(model=None, working_dir=None):
        captured["model"] = model
        captured["working_dir"] = working_dir
        return _StubAgent(working_dir=working_dir or "")

    monkeypatch.setattr("filoma.filaraki.get_agent", fake_get_agent)

    result = filoma.ask("hello")

    assert captured["working_dir"] == os.getcwd()
    assert captured["model"] is None
    assert result.output == "stub-response-for:hello"


def test_ask_passes_path_through(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_get_agent(model=None, working_dir=None):
        captured["working_dir"] = working_dir
        return _StubAgent(working_dir=working_dir or "")

    monkeypatch.setattr("filoma.filaraki.get_agent", fake_get_agent)

    filoma.ask("hi", path=str(tmp_path))

    assert captured["working_dir"] == str(tmp_path)


def test_ask_forwards_model_and_message_history(monkeypatch):
    captured_get: dict = {}
    stub_holder: dict = {}

    def fake_get_agent(model=None, working_dir=None):
        captured_get["model"] = model
        agent = _StubAgent(working_dir=working_dir or "")
        stub_holder["agent"] = agent
        return agent

    monkeypatch.setattr("filoma.filaraki.get_agent", fake_get_agent)

    history = [{"role": "user", "content": "previous turn"}]
    filoma.ask("follow-up", model="ollama:qwen2.5:14b", message_history=history)

    assert captured_get["model"] == "ollama:qwen2.5:14b"
    assert stub_holder["agent"].run_calls == [
        {"prompt": "follow-up", "message_history": history}
    ]


def test_ask_is_in_public_surface():
    assert "ask" in filoma.__all__
    assert callable(filoma.ask)
