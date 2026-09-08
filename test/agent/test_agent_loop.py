from __future__ import annotations

from agent.loop import AgentConfig, AgentLoop
from agent.tools.base import BaseTool, ToolMeta
from agent.tools.registry import ToolRegistry


class _EchoTool(BaseTool):
    meta = ToolMeta(
        name="echo",
        description="Return a stable fixture result.",
        is_readonly=True,
    )

    def execute(self, **unused: str) -> str:
        del unused
        return self._ok({"value": "ready"})


class _DecisionTool(BaseTool):
    meta = ToolMeta(
        name="decide",
        description="Return a stable decision fixture.",
        is_readonly=False,
    )

    def execute(self, **unused: str) -> str:
        del unused
        return self._ok({"decision": "HOLD"})


class _ScriptedAgentLoop(AgentLoop):
    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__(AgentConfig(max_iterations=5))
        self._scripted_registry = registry
        self._responses = [
            (
                "",
                [{"id": "call-1", "name": "echo", "args": {"ticker": "AAPL"}}],
            ),
            (
                "",
                [{"id": "call-2", "name": "echo", "args": {"ticker": "AAPL"}}],
            ),
            ("decision submitted", []),
        ]

    def _get_registry(self) -> ToolRegistry:
        return self._scripted_registry

    def _call_model_streaming(
        self,
        messages,
        tools,
        iteration,
        executor=None,
    ):
        del messages, tools, iteration
        content, tool_calls = self._responses.pop(0)
        for index, tool_call in enumerate(tool_calls):
            if executor is not None:
                executor.submit(index, tool_call)
            yield "tool_use_end", {"index": index, "tool_call": tool_call}
        return content, tool_calls, None


class _DuplicateWithAnswerAgentLoop(_ScriptedAgentLoop):
    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__(registry)
        self._responses = [
            (
                "",
                [{"id": "call-1", "name": "echo", "args": {"ticker": "AAPL"}}],
            ),
            (
                "Use the cached result.",
                [{"id": "call-2", "name": "echo", "args": {"ticker": "AAPL"}}],
            ),
        ]


class _MixedDuplicateAgentLoop(_ScriptedAgentLoop):
    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__(registry)
        self._responses = [
            (
                "",
                [{"id": "call-1", "name": "echo", "args": {"ticker": "AAPL"}}],
            ),
            (
                "",
                [
                    {
                        "id": "call-2",
                        "name": "echo",
                        "args": {"ticker": "AAPL"},
                    },
                    {
                        "id": "call-3",
                        "name": "decide",
                        "args": {"ticker": "AAPL"},
                    },
                ],
            ),
            ("Decision complete.", []),
        ]


def test_agent_loop_reprompts_after_duplicate_only_tool_call() -> None:
    # Given: a model reads once, repeats the same read, then can finish.
    registry = ToolRegistry(allowed_tools=frozenset({"echo"}))
    registry.register(_EchoTool())
    loop = _ScriptedAgentLoop(registry)

    # When: the second iteration contains no new tool after deduplication.
    result = loop.run("Make one decision", session_id="duplicate-recovery")

    # Then: the loop reprompts and reaches the third response instead of ending blank.
    assert result["iterations"] == 3
    assert result["messages"][-1]["content"] == "decision submitted"
    assert any(
        message.get("role") == "user"
        and "already completed" in str(message.get("content"))
        for message in result["messages"]
    )


def test_agent_loop_preserves_answer_on_duplicate_tool_call() -> None:
    # Given: a model includes a usable final answer beside a repeated read call.
    registry = ToolRegistry(allowed_tools=frozenset({"echo"}))
    registry.register(_EchoTool())
    loop = _DuplicateWithAnswerAgentLoop(registry)

    # When: deduplication removes the repeated tool call.
    result = loop.run("Answer from one read", session_id="duplicate-with-answer")

    # Then: the answer remains terminal instead of triggering another iteration.
    assert result["iterations"] == 2
    assert result["messages"][-1]["content"] == "Use the cached result."
    assert not any(
        message.get("role") == "user"
        and "already completed" in str(message.get("content"))
        for message in result["messages"]
    )


def test_agent_loop_maps_mixed_duplicate_results_by_original_index() -> None:
    # Given: a streamed turn repeats one read before a new decision tool.
    registry = ToolRegistry(allowed_tools=frozenset({"echo", "decide"}))
    registry.register(_EchoTool())
    registry.register(_DecisionTool())
    loop = _MixedDuplicateAgentLoop(registry)

    # When: deduplication removes only the first streamed call.
    result = loop.run("Read then decide", session_id="mixed-duplicate")

    # Then: the decision tool receives its own original-index result.
    decision_messages = [
        message
        for message in result["messages"]
        if message.get("role") == "tool" and message.get("name") == "decide"
    ]
    assert len(decision_messages) == 1
    assert '"decision": "HOLD"' in decision_messages[0]["content"]
