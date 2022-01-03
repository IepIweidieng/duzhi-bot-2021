import logging
from functools import partial
from typing import Any, Callable, List, Optional, Union, cast

import linebot.models as lm

import parse
import world
from fsm_utils import (EventData, HierarchicalGraphMachine, MachineCtxMngable,
                       get_state_names)

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
        if cmd in triggers:
            if self.trigger(cmd, *args, **kwargs, event=event, reply=reply):
                return True

        reply(lm.TextSendMessage(text="Not Entering any State"))
        return False
