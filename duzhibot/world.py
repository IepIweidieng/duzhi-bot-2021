import random
from copy import deepcopy
from functools import partial, reduce
from typing import Callable, List, Optional, OrderedDict, Tuple, cast

import linebot.models as lm
from transitions.core import Event

from fsm_utils import (EventData, State_t, TransDictSpec_t, TransList_t, add_resetters, get_state_names,
                       get_transitions, resolve_initial)

trig_lambda = "λ"

# State hierarchy: {world: {area_*: {domain_*: {domain_*: {...}...}...}...}}
# (area = top-level domain)
# Cross-domain transitions: wrap_*


def is_dst(dst: str, ev: EventData) -> bool:
    return ev.kwargs["dst"] == dst


DomainDict = OrderedDict[str, State_t]


def _reach_from(dd: DomainDict, src: str = "init", cmd: str = "cmd_reach") -> TransList_t:
    return [*(cast(TransDictSpec_t, {
        "trigger": cmd,
        "source": src,
        "dest": resolve_initial(v, k),
        "conditions": partial(is_dst, k),
    }) for k, v in dd.items())]


def _go_back_to(dd: DomainDict, src: str = "init") -> TransList_t:
    return [["cmd_go_back",
             [resolve_initial(v, k) for k, v in dd.items()],
             src]]


def _bidirect_reach(dd: DomainDict, src: str = "init", reach_cmd: str = "cmd_reach") -> TransList_t:
    return [*_reach_from(dd, src, reach_cmd), *_go_back_to(dd, src)]


_switch_sts = ["off", "on"]


def _switch(
        name: str,
        stnamef: Callable[[str, str], str] = lambda name, st: st,
        inv: bool = False,
        sts: List[str] = _switch_sts,
) -> TransList_t:
    return sum((
        [cast(TransDictSpec_t, {
            "trigger": f"cmd_{cmd}",
            "source": stnamef(name, st),
            "dest": stnamef(name, dst),
            "conditions": partial(is_dst, name),
        }) for cmd, dst in [
            ("close", sts[False != inv]),
            ("open", sts[True != inv]),
            ("switch", sts[not bool(k) != inv]),
        ]] for k, st in enumerate(sts)), []
    )


def _auto_shut(name: str, init: bool = False) -> State_t:
    return {
        "name": name,
        "states": _switch_sts,
        "transitions": _switch(name),
        "initial": _switch_sts[init],
    }


def check_usernick(ev: EventData) -> bool:
    nick: Optional[str] = ev.kwargs.get("nick")
    if nick is None:
        nick = ""  # TODO: get the user's nickname from the database
    if nick.strip() == "":
        ev.kwargs["reply"](lm.TextSendMessage(
            text=f"'{nick}' 是空白的，是錯誤的使用者暱稱。"))
        return False
    ...  # TODO: save the user's nickname to the database
    return True


def check_hello(ev: EventData) -> bool:
    cmd_name: str = ev.kwargs["cmd_name"]
    dst: List[str] = ev.args
    if len(dst) == 1 and dst[0].strip().lower() in ["world", "world!"]:
        return True
    ev.kwargs["reply"](lm.TextSendMessage(
        text=f"{cmd_name} {' '.join(dst)}"))
    return False


area_init = {
    "name": "init",
    "states": ["init", "registered"],
    "transitions": [
        {"trigger": "cmd_register",
            "source": "*",
            "dest": "registered",
            "conditions": check_usernick},
    ],
    "initial": "init",
}
wrap_init = [
    {"trigger": "cmd_hello",
        "source": "init__registered",
        "dest": "room_off__init",
        "conditions": check_hello},
    *([trig, "init__registered", "hell__hell"]
        for trig in ["cmd_hell", "kill", "force_kill"]),
]

_sts_chair = _sts_room = _switch_sts
_cmds_chair = ["stand", "sit"]


def get_expected_chair_act(ev: EventData) -> None:
    res = random.choice(_cmds_chair)
    ev.model.chair_expected = res
    ev.kwargs["reply"](lm.TextSendMessage(
        text="你坐啊。" if res == "stand" else "你起來啊。"))


def chair_should(act: str, ev: EventData) -> bool:
    return ev.model.chair_expected == act


doms_chair_st = DomainDict(
    standed="standed",
    sat="sat",
)
domain_chair = {
    "name": "chair",
    "states": [
        *({"name": name,
            "states": [*doms_chair_st.values()],
            "initial": "standed",
            "on_enter": [get_expected_chair_act] if name == "init" else [],
           } for name in ["init", *_sts_chair, "wrong"]),
    ],
    "transitions": [
        *sum(([
            ["cmd_sit", f"on__{dom}", "init__sat"],
            ["cmd_sit", f"off__{dom}", "wrong__sat"],
            ["cmd_stand", f"on__{dom}", "wrong__standed"],
            ["cmd_stand", f"off__{dom}", "init__standed"],
            *({"trigger": trig_lambda,
                "source": f"init__{dom}",
                "dest": f"{st}__{dom}",
                "conditions": partial(chair_should, {_cmds_chair[::-1][m]}),
               } for m, st in enumerate(_sts_chair[::-1])),
        ] for dom in doms_chair_st.keys()
        ), []),
        ["cmd_go_back", "on__standed", "wrong__standed"],
    ],
    "initial": "init__standed",
}
wrap_chair = [
    *sum(([
        *([
            trig_lambda,
            f"room_{st}__chair__wrong__{dom}",
            f"hell__chair__{dom}",
        ] for dom in doms_chair_st.keys()),
        ["cmd_go_back", f"room_{st}__chair__off__standed", f"room_{st}__init"],
    ] for st in _sts_room
    ), []),
]

# The password for drawer
draw_pw_tbl = []
DRAWER_PW = str(reduce(
    lambda x, y: x * y,
    (v for v in range(1, 10)
        if (not draw_pw_tbl.clear() if not v >> 1
            else all(v % d for d in draw_pw_tbl)
                and f"{draw_pw_tbl.append(v)}")),
) << 1)[:-1]


def check_drawer_pw(ev: EventData) -> bool:
    pw: str = ev.kwargs["input"]
    return pw == DRAWER_PW


domain_drawer = {
    "name": "drawer",
    "states": [
        *(f"try{k}" for k in range(4)),
        "open",
    ],
    "transitions": [
        {"trigger": "cmd_input",
            "source": [f"try{k}" for k in range(3)],
            "dest": "open",
            "conditions": check_drawer_pw},
        *({"trigger": "cmd_input",
            "source": f"try{k}",
            "dest": f"try{k + 1}",
            "unless": check_drawer_pw,
           } for k in range(3)),
    ],
    "initial": "try0",
}
wrap_drawer = [
    [trig_lambda, [
        f"room_{st_room}__desk__drawer__try3"
        for st_room in _sts_room
    ], "hell__drawer"],
    [trig_lambda, [
        f"room_{st_room}__desk__drawer__open"
        for st_room in _sts_room
    ], "hell__finale"],
]

doms_desk = DomainDict(
    computer="computer",
    drawer=domain_drawer,
)

domain_desk = {
    "name": "desk",
    "states": ["init", *doms_desk.values()],
    "transitions": [
        *_bidirect_reach(doms_desk),
    ],
    "initial": "init",
}

doms_room = DomainDict(
    window="window",
    door="door",
    chair=domain_chair,
    desk=domain_desk,
)

area_room_off = {
    "name": "room_off",
    "states": ["init", *doms_room.values()],
    "transitions": [
        *_reach_from(doms_room),
        # Going back from `domain_chair` is handled differently
        *_go_back_to(
            DomainDict((k, v) for k, v in doms_room.items() if k != "chair")),
    ],
    "initial": "init",
}

area_room_on = deepcopy(area_room_off)
area_room_on["name"] = "room_on"
wrap_room = [
    *({"trigger": "cmd_go_to",
        "source": f"room_{st}__door",
        "dest": "lobby__init" if st == "on" else "hell__door",
        "conditions": partial(is_dst, "lobby"),
       } for st in _sts_room),
    *sum((_switch(dom, (lambda dom, st: f"room_{st}__{dom}"), inv)
          for dom, inv in [("door", False), ("window", True)]),
         []),
]

area_hall = {
    "name": "hall",
    "states": ["init"],
    "initial": "init",
}
wrap_hall = [
    {"trigger": "cmd_go_to_room" if area == "room" else "cmd_go_to",
        "source": "hall__init",
        "dest": f"{dst}__init",
        "conditions": partial(is_dst, area),
     } for area, dst in [
        ("room", "room_on"),
        ("lobby", "lobby"),
    ]
]

doms_lobby = DomainDict(
    door=_auto_shut("door"),
    doorer=_auto_shut("doorer"),
    clock="clock",
    vending_machine="vending_machine",
    engine_room="engine_room",
)
area_lobby = {
    "name": "lobby",
    "states": ["init", *doms_lobby.values()],
    "transitions": [
        *_bidirect_reach(doms_lobby),
    ],
    "initial": "init",
}
wrap_lobby = [
    {"trigger": f"cmd_go_to",
        "source": f"lobby__{dom}",
        "dest": f"{dst}__{init}",
        "conditions": partial(is_dst, dst),
     } for dom, dst, init in [
        ("door__on", "hall", "init"),
        ("doorer__on", "square", "init"),
    ]
]

_sts_sq = ["circle", "triangle", "square"]
_path_sq = [*zip(["init", *_sts_sq[:-1]], _sts_sq)]
_src_sq = OrderedDict[str, str]((v, k) for k, v in _path_sq)
_dst_sq = OrderedDict[str, str]((k, v) for k, v in _path_sq)


def check_body_temperature(dst: str, ev: EventData) -> bool:
    # Simulate a forehead temporature measurement
    tp = random.normalvariate(36.8, 0.7)
    res = tp < 37.5 - 0.05  # Detected as not fever
    ev.kwargs["reply"](lm.TextSendMessage(
        text=f"額溫：{tp:.1f}℃ —— "
        f"{'passed' if res else 'not passed' if dst != 'hospital' else '1922'}",
    ))
    return res


_TUITION_FEE = 32768


def check_inroll(ev: EventData) -> bool:
    if not ...:  # TODO: check wealth
        ev.kwargs["reply"](lm.TextSendMessage(
            text=f"餘額不足：δ{...}/δ{_TUITION_FEE}……"))
        return False
    ...  # TODO: update wealth
    return True


doms_square = DomainDict(
    lobby="lobby",
    hospital="hospital",
    restaurant="restaurant",
    school="school",
)
doms_square_chkpt = DomainDict(
    ((f"{k}_chkpt", f"{k}_chkpt") for k in doms_square.keys()),
)
area_square = {
    "name": "square",
    "states": [
        "init",
        *doms_square_chkpt.values(),
        *doms_square.values(),
        *_sts_sq,
    ],
    "transitions": [
        *_bidirect_reach(doms_square_chkpt, reach_cmd="cmd_go_to"),
        *_go_back_to(doms_square),
        # checkpoints
        *({"trigger": "cmd_check_body_temperature",
            "source": f"{dom}_chkpt",
            "dest": dom,
            "conditions": partial(check_body_temperature, dom),
           } for dom in doms_square.keys()),
        # hospital alias
        ["cmd_go_east", "init", "hospital_chkpt"],
        # square
        *([f"cmd_{dst}",
            src,
            dst if _dst_sq[src] == dst
            else _dst_sq["init"] if dst == _dst_sq["init"]
            else "init"
           ] for src in _dst_sq.keys()
          for dst in [v for v in _sts_sq if v != "triangle"]),
        ["cmd_triangle", _src_sq["triangle"], "triangle"],
        [trig_lambda, "square", "init"],
        # school
        {"trigger": "cmd_yes",
            "source": "school",
            "dest": "init",
            "conditions": check_inroll},
        ["cmd_no", "school", "init"],
    ],
    "initial": "init",
}
""" AKA. overworld """
wrap_square = [
    [trig_lambda, "square__lobby", "lobby__init"],
    *({"trigger": f"cmd_go_to",
        "source": f"square__{dom}",
        "dest": f"{dst}__{init}",
        "conditions": partial(is_dst, dst),
       } for dom, dst, init in [
        ("init", "maze", "m0__0"),
    ]),
    ["cmd_triangle", [
        f"square__{src}" for src in [
            s for s, d in _path_sq if d != "triangle"]
    ], "hell__illuminati"],
]

# TODO: design a proper maze layout

_mz_dim = (4, 4)


def do_mt19937(ev: EventData) -> None:
    """ Randomly pick a destination.
        (not necessarily using the mt19937 algorithm)
    """
    ev.model.mt19937_dst = Tuple(random.randrange(0, v) for v in _mz_dim)


def is_mt19937_dst(pos: Tuple[int, int], ev: EventData) -> bool:
    return ev.model.mt19937_dst == pos


area_maze = {
    "name": "maze",
    "states": [
        *(f"m{r}__{c}" for c in range(_mz_dim[0]) for r in range(_mz_dim[1])),
        "m13__37",
        {
            "name": "mt199",
            "states": [{"name": "37", "on_enter": do_mt19937}],
            "initial": "37",
        },
    ],
    "transitions": [
        *sum(([
            [f"cmd_go_{dir}",
                f"m{r}__{c}",
                f"m{r + dr}__{c + dc}",
             ] for c in range(0 + abs(dc), _mz_dim[1] - abs(dc))
            for r in range(0 + abs(dr), _mz_dim[0] - abs(dr))
        ] for dir, (dr, dc) in [
            ("north", (-1, 0)),
            ("south", (1, 0)),
            ("west", (0, -1)),
            ("east", (0, 1)),
        ]), []),
        ["cmd_go_east", f"m{_mz_dim[0] - 1}__{_mz_dim[1] - 1}", "m13__37"],
        ["cmd_go_south", "m13__37", "mt199__37"],
        *({"trigger": trig_lambda,
            "source": "mt199__37",
            "dest": f"m{r}__{c}",
            "conditions": partial(is_mt19937_dst, (r, c)),
           } for c in range(_mz_dim[0]) for r in range(_mz_dim[1])),
    ],
    "initial": "m0__0",
}
wrap_maze = [
    ["cmd_go_back", "maze__m0__0", "square__init"],
    ["cmd_go_east", "maze__m13__37", "hell__fall"],
]

doms_hell = DomainDict(
    door="door",
    chair__standed="chair__standed",
    chair__sat="chair__sat",
    drawer="drawer",
    illuminati="illuminati",
    fall="fall",
    killed="killed",
    force_killed="force_killed",
    hell="hell",
    finale="finale",
    hacker="hacker",
)
area_hell = {
    "name": "hell",
    "states": ["fini", *doms_hell.values()],
    "transitions": [
        [trig_lambda, [
            k for k in doms_hell.keys() if k != "force_killed"
        ], "fini"],
        {"trigger": "cmd_go_to",
            "source": "fini",
            "dest": "hell",
            "conditions": partial(is_dst, "hell")},
    ],
    "initial": "hacker",
}
""" AKA. gameover """
wrap_hell = [
    [trig_lambda, "hell__force_killed", "init__init"],  # Hard reset
    ["resuscitate", "hell__fini", "init__registered"],
]

doms_world = DomainDict(
    init=area_init,
    room_off=area_room_off,
    room_on=area_room_on,
    hall=area_hall,
    lobby=area_lobby,
    square=area_square,
    maze=area_maze,
    hell=area_hell,
)
world = {
    "name": "world",
    "states": [*doms_world.values()],
    "transitions": [
        *wrap_init,
        *wrap_drawer,
        *wrap_chair,
        *wrap_room,
        *wrap_hall,
        *wrap_lobby,
        *wrap_square,
        *wrap_maze,
        *wrap_hell,
    ],
    "initial": "init__init",
}

# Resetters
_resetters_map = OrderedDict[str, Tuple[str, TransDictSpec_t]](
    hell=("cmd_go_to", {"conditions": partial(is_dst, "hell")}),
    killed=("kill", {}),
    force_killed=("force_kill", {}),
)
_excl = {
    *get_state_names(area_init, base="init"),
    *get_state_names(area_hell, base="hell"),
}
for st, (trggr, kwargs) in _resetters_map.items():
    add_resetters(world, [trggr], f"hell__{st}", excl=_excl, **kwargs)

state_invalid = "hell__hacker"
