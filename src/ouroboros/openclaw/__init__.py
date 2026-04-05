"""OpenClaw-facing channel workflow primitives.

These modules provide the stateful orchestration layer needed for
message-based runtimes such as OpenClaw/Discord to drive the existing
Ouroboros interview -> seed -> execution pipeline.
"""

from ouroboros.openclaw.adapter import (
    OpenClawAdapterResponse,
    OpenClawWorkflowAdapter,
)
from ouroboros.openclaw.contracts import (
    OpenClawChannelEvent,
    OpenClawWorkflowCommand,
)
from ouroboros.openclaw.ux import ParsedChannelCommand, parse_channel_command
from ouroboros.openclaw.workflow import (
    ChannelRef,
    ChannelRepoRegistry,
    ChannelWorkflowManager,
    ChannelWorkflowRecord,
    ChannelWorkflowRequest,
    EntryPointDetection,
    WorkflowEntryPoint,
    WorkflowStage,
    detect_entry_point,
    render_channel_summary,
    render_result_message,
    render_stage_message,
)

__all__ = [
    "ChannelRef",
    "ChannelRepoRegistry",
    "ChannelWorkflowManager",
    "ChannelWorkflowRecord",
    "ChannelWorkflowRequest",
    "EntryPointDetection",
    "OpenClawAdapterResponse",
    "OpenClawChannelEvent",
    "OpenClawWorkflowAdapter",
    "OpenClawWorkflowCommand",
    "ParsedChannelCommand",
    "WorkflowEntryPoint",
    "WorkflowStage",
    "detect_entry_point",
    "parse_channel_command",
    "render_channel_summary",
    "render_result_message",
    "render_stage_message",
]
