from ouroboros.openclaw.contracts import (
    OpenClawChannelEvent,
    OpenClawWorkflowCommand,
)


def test_from_event_builds_message_command() -> None:
    event = OpenClawChannelEvent(
        channel_id="c1",
        guild_id="g1",
        user_id="u1",
        message="work on feature x",
    )

    command = OpenClawWorkflowCommand.from_event(event, repo="/repo/demo")

    assert command.action == "message"
    assert command.channel_id == "c1"
    assert command.guild_id == "g1"
    assert command.user_id == "u1"
    assert command.repo == "/repo/demo"
    assert command.mode == "auto"


def test_set_repo_command_serializes_to_tool_arguments() -> None:
    command = OpenClawWorkflowCommand.set_repo(
        channel_id="c1",
        guild_id="g1",
        repo="/repo/demo",
    )

    assert command.to_tool_arguments() == {
        "action": "set_repo",
        "channel_id": "c1",
        "guild_id": "g1",
        "repo": "/repo/demo",
    }


def test_status_and_poll_commands_are_minimal() -> None:
    status = OpenClawWorkflowCommand.status(channel_id="c1", guild_id="g1")
    poll = OpenClawWorkflowCommand.poll(channel_id="c1", guild_id="g1")

    assert status.to_tool_arguments() == {
        "action": "status",
        "channel_id": "c1",
        "guild_id": "g1",
    }
    assert poll.to_tool_arguments() == {
        "action": "poll",
        "channel_id": "c1",
        "guild_id": "g1",
    }
