# Copyright 2026 The RPent Authors.
"""Run the RPent CLI with a native SDK capability that guides the live model."""

from dataclasses import replace

from pydantic_ai import ModelRequest, ModelResponse, RunContext, ToolCallPart
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models import ModelRequestContext

from rpent.cli.main import main
from rpent.planner.base import build_planner
from rpent.utils.logging import get_output_dir


class ExerciseTools(AbstractCapability):
    """Request each advertised tool once, leaving the model to generate its call."""

    def __init__(self):
        self.attempted: set[str] = set()

    async def before_model_request(
        self, ctx: RunContext, request_context: ModelRequestContext
    ) -> ModelRequestContext:
        messages = request_context.messages
        for message in messages:
            if isinstance(message, ModelResponse):
                self.attempted.update(
                    part.tool_name
                    for part in message.parts
                    if isinstance(part, ToolCallPart)
                )
        params = request_context.model_request_parameters
        available = [tool.name for tool in params.function_tools]
        # Observe first, write before reading, and leave episode resets until last.
        first = (
            "view_env_state",
            "list_dir",
            "write_text_file",
            "read_text_file",
            "read_image",
            "segment",
            "sample_world_xyz",
            "query_world_map",
            "pi0_doubled",
            "lingbot_act",
            "pi05_act",
            "rldx_skill",
            "vpp2_act",
            "awomo05_act",
        )
        ordered = [*first, *(name for name in available if name != "reset"), "reset"]
        name = next(
            (n for n in ordered if n in available and n not in self.attempted),
            "finish",
        )
        # Keep the original assignment and the latest tool result (including its
        # images). Whole-episode image history can exceed the model's context.
        recent = messages if len(messages) <= 3 else [messages[0], *messages[-2:]]
        instruction = (
            f"Call {name} using its schema and the bounded test inputs. "
            "Set max_chunks, chunks and n_action_steps to 1 when offered."
        )
        if name == "read_image":
            images = sorted(get_output_dir().glob("*.png/00.png"))
            if images:
                instruction += f" Read {images[0].parent.name} at step 0."

        last = recent[-1]
        if not isinstance(last, ModelRequest):
            raise RuntimeError("Expected an SDK request following the tool result")
        return replace(
            request_context,
            messages=[
                *recent[:-1],
                replace(last, parts=[*last.parts, UserPromptPart(instruction)]),
            ],
            model_request_parameters=replace(
                params,
                allow_text_output=False,
                function_tools=[] if name == "finish" else params.function_tools,
            ),
            model_settings={
                **(request_context.model_settings or {}),
                "parallel_tool_calls": False,
                "tool_choice": "none" if name == "finish" else [name],
            },
        )


def guided_planner(*args, **kwargs):
    planner = build_planner(*args, **kwargs)
    planner.capabilities = (ExerciseTools(),)
    return planner


if __name__ == "__main__":
    raise SystemExit(main(planner_factory=guided_planner))
