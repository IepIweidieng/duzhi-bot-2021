# Copyright 2022 Iweidieng Iep
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

""" fsm_utils
    Utilities for defining FSMs.
"""

from typing import (Callable, Dict, List, Literal, Optional, Sequence, Union,
                    cast)

from transitions.extensions import GraphMachine, HierarchicalGraphMachine
from transitions.extensions.nesting import NestedState

_sep = NestedState.separator = '__'

# customize the graphic styling
for attrs in ["hierarchical_machine_attributes", "machine_attributes"]:
    getattr(GraphMachine, attrs).update(
        rankdir="LR",  # arranging left-to-right
        nodesep="0.32",  # default: 0.25
        pad="0.222,0.111",  # default: 0.0555
    )


# Types

State_t = Union[str, "Config_t"]
TransCond_t = Union[str, Callable[..., Union[bool, None]]]
TransFunc_t = Union[TransCond_t, List[TransCond_t], Literal["*", "=", None]]
TransDictSpec_t = Dict[str, TransFunc_t]
TransListSpec_t = List[Union[TransFunc_t, List[TransFunc_t]]]
Trans_t = TransSpec_t = Union[TransDictSpec_t, TransListSpec_t]
TransList_t = Union[
    List[TransDictSpec_t],
    List[TransListSpec_t],
    List[Trans_t]
]
Config_t = Dict[str, Union[List["State_t"], TransList_t, List[str], str]]

Visit_t = Callable[[Optional[str], Optional[Config_t], int], None]


# Functions

def get_children(config: Config_t) -> Optional[List[State_t]]:
    """ Return all non-nested states in `config`. """
    res = config.get("children", config.get("states"))
    assert ((isinstance(res, list)
             and all(not isinstance(v, list) for v in res))
            or res is None)
    return cast(Optional[List[State_t]], res)


def get_transitions(config: Config_t) -> List[Trans_t]:
    """ Return the non-nested transitions in `config`. """
    res = config.setdefault("transitions", [])
    assert isinstance(res, list)
    return cast(List[Trans_t], res)


def visit_states(config: Config_t, f: Visit_t, depth: int = 0) -> None:
    """ Visit all (nested) states in `config` and invoke `f` on them:
        f(state name, state object if it has any children).
        `depth` is the distance from the root state.
    """
    name = config.get("name")
    assert (isinstance(name, (str, type(None)))
            and (name is not None or depth == 0))
    sub = get_children(config)
    # visit self
    if sub is None:
        f(name, None, depth)
        return
    f(name, config, depth)
    # visit children
    depth += 1
    for s in sub:
        if isinstance(s, dict):
            visit_states(s, f, depth)
        else:
            f(s, None, depth)


def ignore_transitions(config: Config_t, ign: Sequence[str], dest: Literal["=", None]) -> None:
    """ Add transitions to `config` for ignoring triggers in `ign_list`.
        `dest` should be either `"="` (reflexive) or `None` (internal).
    """
    def f(name: Optional[str], state: Optional[Config_t], depth: int) -> None:
        if state is None:
            return
        get_transitions(state).extend([token, "*", dest] for token in ign)
    visit_states(config, f)


def add_resetters(config: Config_t, names: Sequence[str], dest: str) -> None:
    """ Add transitions to `config` for resetting. """
    states: List[str] = []
    path: List[str] = []
    plen: List[int] = [0]

    def f(name: Optional[str], state: Optional[Config_t], depth: int) -> None:
        if depth > 0:
            assert name is not None
            if depth > plen[0]:
                path.append(name)
                plen[0] += 1
            else:
                path[depth - 1] = name
            states.append(_sep.join(path[:depth]))

    visit_states(config, f)
    get_transitions(config).extend([name, states, dest] for name in names)
