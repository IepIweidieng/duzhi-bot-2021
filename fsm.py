from logging import Logger
from typing import Callable, List, Union

import linebot.models as lm
from transitions.extensions import GraphMachine


class TocMachine(GraphMachine):
    Msg_t = Union[lm.SendMessage, List[lm.SendMessage]]
    Reply_t = Callable[[Msg_t], None]

    configs = {
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

    def __init__(self, logger: Logger, **machine_configs) -> None:
        self.machine = GraphMachine(
            model=self, **{**TocMachine.configs, **machine_configs})
        self.logger = logger

    def is_going_to_state1(self, event: lm.Event, reply: Reply_t) -> bool:
        text = event.message.text
        return text.lower() == "go to state1"

    def is_going_to_state2(self, event: lm.Event, reply: Reply_t) -> bool:
        text = event.message.text
        return text.lower() == "go to state2"

    def on_enter_state1(self, event: lm.Event, reply: Reply_t) -> None:
        self.logger.info("I'm entering state1")
        reply(lm.TextSendMessage(text="Trigger state1"))
        self.go_back()

    def on_exit_state1(self) -> None:
        self.logger.info("Leaving state1")

    def on_enter_state2(self, event: lm.Event, reply: Reply_t) -> None:
        self.logger.info("I'm entering state2")
        reply(lm.TextSendMessage(text="Trigger state2"))
        self.go_back()

    def on_exit_state2(self) -> None:
        self.logger.info("Leaving state2")
