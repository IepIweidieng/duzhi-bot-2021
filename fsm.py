from inspect import cleandoc
from logging import Logger
from typing import Any, Callable, Dict, List, OrderedDict, Union

import linebot.models as lm

import parse
from fsm_utils import HierarchicalGraphMachine, add_resetters, get_states

# Hierarchy: {world: {area: {domain...}...}}

DomainDict = OrderedDict[str, Union[str, dict]]
Trans_t = Union[Dict[str, Any], List[Union[str, List[str]]]]


def _get_go_to(dd: DomainDict, src: str = "init") -> List[Trans_t]:
    return [*({"trigger": "cmd_go_to", "source": src, "dest": dest,
               "conditions": f"is_going_to_{dest}",
            } for dest in dd.keys())]


def _get_go_back(dd: DomainDict, src: str = "init") -> List[Trans_t]:
    return [["cmd_go_back", [*dd.keys()], src]]


def _get_go(dd: DomainDict, src: str = "init") -> List[Trans_t]:
    return [*_get_go_to(dd, src), *_get_go_back(dd, src)]


area_init = {
    "name": "init",
    "states": ["init", "registered"],
    "transitions": [
        {"trigger": "cmd_register", "source": "*", "dest": "registered",
         "conditions": "user_rename"},
    ],
    "initial": "init",
}

_sts_chair = ["stand", "sat"]

domain_chair = {
    "name": "chair",
    "states": [
        *sum(([f"init_{st}", f"wrong_{st}"] for st in _sts_chair), []),
        *({"name": name, "states": _sts_chair,
            "initial": "stand"} for name in ["on", "off"]),
    ],
    "transitions": [
        ["cmd_sit", "on", "init_sat"],
        ["cmd_sit", "off", "wrong_sit"],
        *([cmd, "on", "wrong"] for cmd in ["cmd_stand", "cmd_go_back"]),
        ["cmd_stand", "off", "init_stand"],
        *({"trigger": "lambda", "source": f"init_{st}", "dest": st,
           "conditions": f"should_{st}"
           } for st in _sts_chair),
    ],
    "initial": "init_stand",
}

domain_drawer = {
    "name": "drawer",
    "states": [
        *(f"try{k}" for k in range(4)),
        "open",
    ],
    "transitions": [
        *({"trigger": "cmd_input",
            "source": f"try{k}", "dest": f"try{k + 1}",
            "unless": "is_deskpw_correct"
          } for k in range(3)),
        {"trigger": "cmd_input",
            "source": [f"try{k}" for k in range(3)], "dest": "open",
            "conditions": "is_deskpw_correct"},
    ],
    "initial": "try0",
}

domains_desk = DomainDict(
    computer="computer",
    drawer=domain_drawer,
)

domain_desk = {
    "name": "desk",
    "states": ["init", *domains_desk.values()],
    "transitions": [
        *_get_go(domains_desk),
    ],
    "initial": "init",
}

domains_room = DomainDict(
    window="window",
    door="door",
    chair=domain_chair,
    desk=domain_desk,
)

area_room_off = {
    "name": "room_off",
    "states": ["init", *domains_room.values()],
    "transitions": [
        *_get_go(domains_room),
    ],
    "initial": "init",
}

area_room_on = {**area_room_off}
area_room_on["name"] = "room_on"

domains_lobby = DomainDict(
    door="door",
    doorer="doorer",
    clock="clock",
    vending_machine="vending_machine",
    engine_room="engine_room",
)

area_lobby = {
    "name": "lobby",
    "states": ["init", *domains_lobby.values()],
    "transitions": [
        *_get_go(domains_lobby),
    ],
    "initial": "init",
}

domains_square = DomainDict(
    lobby="lobby",
    hospital="hospital",
    restaurant="restaurant",
    school="school",
)

area_square = {
    "name": "square",
    "states": ["init", *domains_square.values()],
    "transitions": [
        *_get_go(domains_square),
    ],
    "initial": "init",
}
""" AKA. overworld """

area_maze = {
    "name": "maze",
    "states": [
        *(f"maze{k}" for k in range(100)),
        "maze1337",
    ],
    "transitions": [
        ["cmd_plugh", "*", "maze0"],
    ],
    "initial": "maze0",
}

domains_hell = DomainDict(
    door="door",
    chair_stand="chair_stand",
    chair_sat="chair_sat",
    desk="desk",
    illuminati="illuminati",
    fall="fall",
    killed="killed",
    hell="hell",
    hacker="hacker",
)

area_hell = {
    "name": "hell",
    "states": ["fini", *domains_hell.values()],
    "transitions": [
        *_get_go_to(domains_hell, "hell"),
        ["lambda", [*domains_hell.keys()], "fini"],
    ],
    "initial": "hell",
}
""" AKA. gameover """

domains_world = DomainDict(
    init=area_init,
    room_off=area_room_off,
    room_on=area_room_on,
    lobby=area_lobby,
    square=area_square,
    maze=area_maze,
    hell=area_hell,
)

world = {
    "name": "world",
    "states": [*domains_world.values()],
    "transitions": [
        ["lambda", [
            f"room_{st}__chair__wrong" for st in ["on", "off"]
        ], "hell__chair"],
    ],
    "initial": "init",
}
add_resetters(world, ["cmd_go_to"], "hell__hell",
              conditions="is_going_to_hell")
add_resetters(world, ["kill"], "hell__killed")
add_resetters(world, ["resuscitated"], "init__registered")
add_resetters(world, ["force_killed"], "init__init")


class TocMachine(HierarchicalGraphMachine):
    Msg_t = Union[lm.SendMessage, List[lm.SendMessage]]
    Reply_t = Callable[[Msg_t], None]

    configs = {
        **world,
        "auto_transitions": False,
        "show_conditions": True,
    }

    def __init__(self, logger: Logger, **machine_configs) -> None:
        super().__init__(**{**TocMachine.configs, **machine_configs})
        self.logger = logger

    for k in [*sum(([*domains.keys()] for domains in [
        domains_desk, domains_room, domains_lobby, domains_square, domains_hell
    ]), []), "hell"]:
        exec(cleandoc(f"""
        def is_going_to_{k}(self, args: List[str], event: lm.Event, reply: Reply_t) -> bool:
            return args[0] == "{k}"
        """))

    for k in get_states(world):
        exec(cleandoc(f"""
        def on_enter_{k}(self, args: List[str], event: lm.Event, reply: Reply_t) -> None:
            self.logger.info("I'm entering {k}")
            reply(lm.TextSendMessage(text="Trigger {k}"))
            self.go_back()

        def on_exit_{k}(self) -> None:
            self.logger.info("Leaving {k}")
        """))

    def exec(self, event: lm.Event, reply: Reply_t) -> bool:
        """ Parse `event` and try to trigger `self` with the parsing result.
            Return whether the parsed command is valid and available.
        """
        triggers = self.get_triggers(self.state)
        cmd, args = parse.parse(event.message.text)
        if f"cmd_{cmd}" in triggers:
            if self.trigger(cmd, args, event, reply):
                return True
        reply(lm.TextSendMessage(text="Not Entering any State"))
        return False
