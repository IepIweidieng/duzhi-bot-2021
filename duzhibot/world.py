from copy import deepcopy
from typing import Callable, List, OrderedDict, Tuple, cast

from fsm_utils import (State_t, TransDictSpec_t, TransList_t, get_transitions,
                       resolve_initial)

state_glob = "S"
transition_lambda = "λ"

# State hierarchy: {world: {area_*: {domain_*: {domain_*: {...}...}...}...}}
# (area = top-level domain)
# Cross-domain transitions: wrap_*

DomainDict = OrderedDict[str, State_t]


def _reach_from(dd: DomainDict, src: str = "init", cmd: str = "cmd_reach") -> TransList_t:
    return [*(cast(TransDictSpec_t, {
        "trigger": cmd,
        "source": src,
        "dest": resolve_initial(v, k),
        "conditions": f"is_dst_{k}",
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
         "conditions": f"will_{cmd}_{name}",
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


area_init = {
    "name": "init",
    "states": ["init", "registered"],
    "transitions": [
        {"trigger": "cmd_register",
            "source": "*",
            "dest": "registered",
            "conditions": "check_usernick"},
    ],
    "initial": "init",
}
wrap_init = [
    {"trigger": "cmd_hello",
        "source": "init__registered",
        "dest": "room_off__init",
        "conditions": "check_hello"},
]

_sts_chair = _sts_room = _switch_sts
_cmds_chair = ["stand", "sit"]

doms_chair_st = DomainDict(
    standed="standed",
    sat="sat",
)
domain_chair = {
    "name": "chair",
    "states": [
        *({"name": name,
            "states": [*doms_chair_st.values()],
            "initial": "standed"
           } for name in ["init", *_sts_chair, "wrong"]),
    ],
    "transitions": [
        *sum(([
            ["cmd_sit", f"on__{dom}", "init__sat"],
            ["cmd_sit", f"off__{dom}", "wrong__sat"],
            ["cmd_stand", f"on__{dom}", "wrong__standed"],
            ["cmd_stand", f"off__{dom}", "init__standed"],
            *({"trigger": transition_lambda,
                "source": f"init__{dom}",
                "dest": f"{st}__{dom}",
                "conditions": f"should_{_cmds_chair[::-1][m]}",
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
            transition_lambda,
            f"room_{st}__chair__wrong__{dom}",
            f"hell__chair__{dom}",
        ] for dom in doms_chair_st.keys()),
        ["cmd_go_back", f"room_{st}__chair__off__standed", f"room_{st}__init"],
    ] for st in _sts_room
    ), []),
]

domain_drawer = {
    "name": "drawer",
    "states": [
        *(f"try{k}" for k in range(4)),
        "open",
    ],
    "transitions": [
        *({"trigger": "cmd_input",
            "source": f"try{k}",
            "dest": f"try{k + 1}",
            "unless": "check_desk_pw"
           } for k in range(3)),
        {"trigger": "cmd_input",
            "source": [f"try{k}" for k in range(3)],
            "dest": "open",
            "conditions": "check_desk_pw"},
    ],
    "initial": "try0",
}
wrap_drawer = [
    [transition_lambda, [
        f"room_{st_room}__desk__drawer__try3"
        for st_room in _sts_room
    ], "hell__drawer"],
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
        "conditions": "is_dst_lobby"
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
        "conditions": f"is_dst_{area}",
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
        "conditions": f"is_dst_{dst}",
     } for dom, dst, init in [
        ("door", "hall", "init"),
        ("doorer", "square", "init"),
    ]
]

_sts_sq = ["circle", "triangle", "square"]
_path_sq = [*zip(["init", *_sts_sq[:-1]], _sts_sq)]
_src_sq = OrderedDict[str, str]((v, k) for k, v in _path_sq)
_dst_sq = OrderedDict[str, str]((k, v) for k, v in _path_sq)

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
            "conditions": "check_body_temperature",
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
        [transition_lambda, "square", "init"],
        # school
        {"trigger": "cmd_yes",
            "source": "school",
            "dest": "init",
            "conditions": "check_inroll"},
        ["cmd_no", "school", "init"],
    ],
    "initial": "init",
}
""" AKA. overworld """
wrap_square = [
    [transition_lambda, "square__lobby", "lobby__init"],
    *({"trigger": f"cmd_go_to",
        "source": f"square__{dom}",
        "dest": f"{dst}__{init}",
        "conditions": f"is_dst_{dst}",
       } for dom, dst, init in [
        ("init", "maze", "m0__0"),
    ]),
    ["cmd_triangle", [
        f"square__{src}" for src in [
            s for s, d in _path_sq if d != "triangle"]
    ], "hell__illuminati"],
]

# TODO: design a proper maze layout
_mz_dim = (10, 10)
area_maze = {
    "name": "maze",
    "states": [
        *(f"m{r}__{c}" for c in range(_mz_dim[0]) for r in range(_mz_dim[1])),
        "m13__37",
        "mt199__37",
        state_glob,
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
        {"trigger": transition_lambda,
            "source": "mt199__37",
            "dest": state_glob,
            "after": "do_mt19937"},
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
    hacker="hacker",
)
area_hell = {
    "name": "hell",
    "states": ["fini", *doms_hell.values()],
    "transitions": [
        [transition_lambda, [
            k for k in doms_hell.keys() if k != "force_killed"
        ], "fini"],
    ],
    "initial": "hacker",
}
""" AKA. gameover """
wrap_hell = [
    [transition_lambda, "hell__force_killed", "init__init"],  # Hard reset
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

# Resetters
_resetters_map = OrderedDict[str, Tuple[str, TransDictSpec_t]](
    hell=("cmd_go_to", {"conditions": "is_dst_hell"}),
    killed=("kill", {}),
    force_killed=("force_kill", {}),
)
# ignore resetters for special states
get_transitions(area_init).extend([
    ["cmd_go_to", "*", None],
    ["kill", "init", None],
    ["force_kill", "init", None],
])

world = {
    "name": "world",
    "states": [*doms_world.values(), state_glob],
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
        # cross-area resetters
        *({"trigger": trggr,
            "source": state_glob,
            "dest": f"hell__{st}",
            **kwargs,
           } for st, (trggr, kwargs) in _resetters_map.items()),
    ],
    "initial": "init__init",
}

state_invalid = "hell__hacker"
