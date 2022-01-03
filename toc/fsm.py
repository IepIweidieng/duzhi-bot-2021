import logging
from functools import partial
from inspect import cleandoc
from typing import Any, Callable, List, Optional, Union

import linebot.models as lm

import parse
from fsm_utils import GraphMachine, MachineCtxMngable

_LOGGER = logging.getLogger(__name__)

_configs = {
    "states": ["user", "state1", "state2"],
    "transitions": [
        {
            "trigger": "advance",
            "source": "user",
            "dest": "state1",
            "conditions": "is_going_to_state1",
        },
        {
            "trigger": "advance",
            "source": "user",
            "dest": "state2",
            "conditions": "is_going_to_state2",
        },
        {"trigger": "go_back", "source": ["state1", "state2"],
            "dest": "user"},
    ],
    "initial": "user",
    "auto_transitions": False,
    "show_conditions": True,
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

    for k in [1, 2]:
        exec(cleandoc(f"""
        def is_going_to_state{k}(self, args: List[str], event: lm.Event, reply: Reply_t) -> bool:
            return args[0] == "state{k}"

        def on_enter_state{k}(self, args: List[str], event: lm.Event, reply: Reply_t) -> None:
            _LOGGER.info("I'm entering state{k}")
            reply(lm.TextSendMessage(text="Trigger state{k}"))
            self.go_back()

        def on_exit_state{k}(self) -> None:
            _LOGGER.info("Leaving state{k}")
        """))

    def exec(self, event: lm.Event, reply: Reply_t) -> bool:
        """ Parse `event` and try to trigger `self` with the parsing result.
            Return whether the parsed command is valid and available.
        """
        triggers = toc_machine.get_triggers(self.state)
        cmd, args = parse.parse(event.message.text)
        if cmd in triggers:
            if self.trigger(cmd, args, event, reply):
                return True
        reply(lm.TextSendMessage(text="Not Entering any State"))
        return False
