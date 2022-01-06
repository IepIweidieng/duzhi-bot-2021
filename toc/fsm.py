import logging
from functools import partial
from typing import Any, Callable, List, Optional, Union

import linebot.models as lm

import parse
from fsm_utils import EventData, GraphMachine, MachineCtxMngable

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
    "states": [
        "user",
        {
            "name": "state1",
            "on_enter": partial(on_enter, "state1"),
            "on_exit": partial(on_exit, "state1"),
        },
        {
            "name": "state2",
            "on_enter": partial(on_enter, "state2"),
            "on_exit": partial(on_exit, "state2"),
        },
    ],
    "transitions": [
        {
            "trigger": "advance",
            "source": "user",
            "dest": "state1",
            "conditions": partial(is_going_to, "state1"),
        },
        {
            "trigger": "advance",
            "source": "user",
            "dest": "state2",
            "conditions": partial(is_going_to, "state2"),
        },
        {"trigger": "go_back", "source": ["state1", "state2"],
            "dest": "user"},
    ],
    "initial": "user",
    "auto_transitions": False,
    "show_conditions": True,
    "send_event": True,
}
toc_initial = _configs["initial"]
toc_state_invalid = toc_initial
toc_machine = GraphMachine(model=None, **_configs)


class TocModel(MachineCtxMngable):
    Msg_t = Union[lm.SendMessage, List[lm.SendMessage]]
    Reply_t = Callable[[Msg_t], None]

    state: Union[partial, Any]
    trigger: Union[partial, Any]

    def __init__(self, initial: Optional[str] = None) -> None:
        if initial is not None:  # Ensure `initial` is valid
            try:
                toc_machine.get_state(initial)
            except ValueError:
                initial = toc_state_invalid
        self._initial = initial

    def exec(self, event: lm.Event, reply: Reply_t) -> bool:
        """ Parse `event` and try to trigger `self` with the parsing result.
            Return whether the parsed command is valid and available.
        """
        triggers = toc_machine.get_triggers(self.state)
        cmd, args = parse.parse(event.message.text)
        if cmd in triggers:
            if self.trigger(cmd, *args, event=event, reply=reply):
                return True
        reply(lm.TextSendMessage(text="Not Entering any State"))
        return False
