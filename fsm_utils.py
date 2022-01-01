# Copyright 2022 Iweidieng Iep
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

""" fsm_utils
    Helper functions for defining FSMs.
"""

from typing import Callable, Dict, List, Literal, Optional, Sequence

from transitions.extensions.nesting import NestedState

_sep = NestedState.separator = '__'

Visit_t = Callable[[Optional[str], Optional[Dict], int], None]


def visit_states(config: Dict, f: Visit_t, depth: int = 0) -> None:
    """ Visit all (nested) states in `config` and invoke `f` on them:
        f(state name, state object if it has any children).
    """
    name: Optional[str] = config.get("name")
    assert name is not None or depth == 0
    sub: List = config.get("children", config.get("states"))
    if sub is None:
        f(name, None, depth)
        return
    f(name, config, depth)
    for s in sub:
        if isinstance(s, dict):
            visit_states(s, f, depth + 1)
        else:
            f(s, None, depth)


def ignore_transitions(config: Dict, ign: Sequence, dest: Optional[Literal["="]]) -> None:
    """ Add transitions to `config` for ignoring triggers in `ign_list`.
        `dest` should be either `"="` (reflexive) or `None` (internal).
    """
    def f(name: Optional[str], state: Optional[Dict], depth: int) -> None:
        if state is None:
            return
        trans: List = state.setdefault("transitions", [])
        trans.extend([token, "*", dest] for token in ign)
    visit_states(config, f)


def add_resetters(config: Dict, names: Sequence, dest: str) -> None:
    """ Add transitions to `config` for resetting. """
    states: List[str] = []
    path: List[str] = []
    plen: List[int] = [0]

    def f(name: Optional[str], state: Optional[Dict], depth: int) -> None:
        if name is not None:
            if depth >= plen[0]:
                path.append(name)
                plen[0] += 1
            else:
                path[depth] = name
            states.append(_sep.join(path[:depth + 1]))

    visit_states(config, f)
    trans: List = config.setdefault("transitions", [])
    trans.extend([name, states, dest] for name in names)
