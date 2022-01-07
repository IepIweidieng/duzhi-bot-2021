import logging
from functools import partial
from typing import Any, Callable, List, Optional, Union

import linebot.models as lm
from flask import request, g as fg

import parse
import world
from fsm_utils import EventData, HierarchicalGraphMachine, MachineCtxMngable

_LOGGER = logging.getLogger(__name__)


def is_going_to(state: str, ev: EventData) -> bool:
    return ev.args[0] == state


def on_enter(state: str, ev: EventData) -> None:
    _LOGGER.info(f"I'm entering {state}")
    ev.kwargs["reply"](lm.TextSendMessage(text=f"Trigger {state}"))
    ev.model.go_back()


def on_exit(state: str, ev: EventData) -> None:
    _LOGGER.info(f"Leaving {state}")


_configs = {
    "title": "Main Machine",
    **world.world,
    "auto_transitions": False,
    "show_conditions": True,
    "send_event": True,
}
world_initial = _configs["initial"]
world_state_invalid = world.state_invalid
world_machine = HierarchicalGraphMachine(model=None, **_configs)


class WorldModel(MachineCtxMngable):
    Msg_t = Union[lm.SendMessage, List[lm.SendMessage]]
    Reply_t = Callable[[Msg_t], None]

    state: Union[partial, Any]
    trigger: Union[partial, Any]

    def __init__(self, initial: Optional[str] = None) -> None:
        if initial is not None:  # Ensure `initial` is valid
            try:
                world_machine.get_state(initial)
            except ValueError:
                initial = world_state_invalid
        self._initial = initial

    def exec(self, event: lm.Event, reply: Reply_t) -> bool:
        """ Parse `event` and try to trigger `self` with the parsing result.
            Return whether the parsed command is valid and available.
        """
        triggers = world_machine.get_triggers(self.state)
        cmd, args, kwargs = parse.parse(event.message.text)
        res = (
            cmd in triggers
            and self.trigger(cmd, *args, **kwargs, event=event, reply=reply))

        # Allow only lambda transitions which appear alone for deterministic
        resk = res
        while resk:
            triggers = world_machine.get_triggers(self.state)
            if triggers.count(world.trig_lambda) != len(triggers):
                break
            resk = self.trigger(
                world.trig_lambda, event=event, reply=reply)

        # Fallback message
        if not res:
            _LOGGER.info(f"{fg.rqst_root_url}/img/huisha-v2.png")
            reply([
                lm.ImageSendMessage(
                    original_content_url=f"{request.root_url}/img/huisha-v2.png",
                ),
                lm.TextSendMessage(
                    text="無此命令……請用 `/help` 査看可用命令。",
                    quick_reply=lm.QuickReply([lm.QuickReplyButton(
                        action=lm.MessageAction(label="/help", text="/help"))],
                    )),
            ])

        return res
