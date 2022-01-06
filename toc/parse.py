# Copyright 2022 Iweidieng Iep
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

""" parse
    FSM-based lexer and parser for interpretting text messages.
"""

import itertools
import re
from functools import partial
from typing import (Any, Callable, Dict, Iterator, List, NamedTuple, Optional,
                    OrderedDict, Tuple, Type, Union, cast)

from fsm_utils import (EventData, HierarchicalGraphMachine, MachineCtxMnger,
                       Tags, add_resetters, add_state_features,
                       ignore_transitions)

# Token definitions

_cmd_token_defs: Dict[str, List[Tuple[str, Type]]] = {
    "TStr": [("value", str), ("suffix", str)],
    "TCmd": [("value", str)],
    "TQuoted": [("value", str)],
    "TWord": [("value", str)],
    "TNewline": [],
    "TIndent": [("value", List[Tuple[str, int]])],
    "TSpace": [],
}

Token_t = Tuple
token_classes: Dict[str, Type[Token_t]] = {}
for name, fields in _cmd_token_defs.items():
    cls = token_classes[name] = NamedTuple(name, fields)
    exec(f"""{name} = cls""")


# Lexer

def _consecutive_count(text: str) -> List[Tuple[str, int]]:
    """ Return a list of (the repeated character, the repeated length)
        for every instance of consecutive characters in str `text`.
    """
    return [(k, sum(1 for _ in itg)) for k, itg in itertools.groupby(text)]


def _repr_indent(indent: TIndent) -> str:
    """ Return a `str` representing the `TIndent` token `indent`. """
    return "_".join(f"x{ord(k):x}n{l}" for k, l in indent.value)


def _repr(token: Token_t) -> Optional[str]:
    """ Return a `str` representing the token `token` if needed. """
    value = getattr(token, "value", None)
    return str(value) if value is not None else None


XformElem_t = Callable[..., Optional[Any]]
Xform_t = Callable[..., Optional[Tuple]]
Repr_t = Callable[[Tuple], Optional[str]]


def _xform(*xforms: XformElem_t) -> Xform_t:
    """ Return a composited function of the arguments. """
    def resf(*args) -> Optional[Tuple]:
        for f in xforms:
            args = f(*args)
            if args is None:  # Halt the transformation
                break
        return args
    return resf


PatSpec = NamedTuple(
    "PatSpec", cond=str, pat=re.Pattern, xform=Xform_t, repr=Optional[Repr_t],
)

token_specs = OrderedDict[str, PatSpec](
    TStr=PatSpec(
        "*", re.compile(r'"((?:\\.|[^"\\])+)"(\w*)', re.DOTALL),
        _xform(), _repr),
    TCmd=PatSpec("*", re.compile(r"/([\w$]+[?!]?)"), _xform(), _repr),
    TQuoted=PatSpec("*", re.compile(r"'(\S+)'?"), _xform(), _repr),
    TWord=PatSpec("*", re.compile(r"(\S+)"),
                  _xform(lambda x: (x.lower(),)), _repr),  # Case insensitive
    TNewline=PatSpec("*", re.compile(r"\s*\n"), _xform(), None),
    TIndent=PatSpec(
        "beg", re.compile(r"((?:(?!\n)\s)+)"),
        _xform(_consecutive_count, lambda *x: (x,)), _repr_indent),
    TSpace=PatSpec("mid", re.compile(r"(?:(?!\n)\s)+"), _xform(), None),
)
""" The pattern for tokens. Should be tried in order. """
for ttype, spec in token_specs.items():
    assert spec.pat.groups == len(getattr(token_classes[ttype], "_fields"))

_lex_machine_configs = {
    "title": "Lexer Machine",
    "states": ["beg", "mid"],
    "transitions": [
        ["TNewline", "*", "beg"],
        *([name, "*", "mid"]
            for name in token_classes.keys() if name not in ["TNewline"]),
    ],
    "initial": "beg",
    "auto_transitions": False,
    "show_conditions": True,
}
add_resetters(_lex_machine_configs, ["reset"], "beg")

_lex_machine = HierarchicalGraphMachine(**_lex_machine_configs)


class _LexModel(MachineCtxMnger(_lex_machine)):
    """ A model class for lexing (tokenizing) text message. """
    state: Union[partial, Any]
    trigger: Union[partial, Any]

    def step(self, text: str, idx: int) -> Tuple[int, Optional[Token_t]]:
        """ Return (the index of the next token, a token if a pattern matched)
            from `str` `text` with offset `idx`.
        """
        for ttype, spec in token_specs.items():
            if spec.cond != "*" and self.state != spec.cond:
                continue
            match = spec.pat.match(text[idx:])
            if match is None:
                continue
            res = spec.xform(*match.groups())
            if res is None:
                continue
            self.trigger(ttype)
            return idx + match.end(), token_classes[ttype](*res)
        return idx + 1, None  # Ignore the invalid character


def lex(text: str) -> Iterator[Tuple[int, Token_t]]:
    """ Return an iterator of (tokens, their index) for `str` `text`. """
    with _LexModel() as model:
        idx = 0
        len_text = len(text)
        while idx < len_text:
            idx_nxt, token = model.step(text, idx)
            if token is not None:
                yield idx, token
            idx = idx_nxt


# Parser

@add_state_features(Tags)  # For marking accepted states
class _ParseMachine(HierarchicalGraphMachine):
    pass


def _set_cmd(cmd: str, ev: EventData) -> None:
    cast(_ParseModel, ev.model).cmd = cmd


def _get_arg(ev: EventData) -> None:
    cast(_ParseModel, ev.model).args.append(ev.args[0])


def _get_kwarg(kw: str, ev: EventData) -> None:
    cast(_ParseModel, ev.model).kwargs[kw] = ev.args[0]


_parse_machine_configs = {
    "title": "Parser Machine",
    "states": [
        {"name": "s", "children": [
            {"name": "go", "children": [
                {"name": "to", "children": [
                    {"name": "arg0",
                        "on_enter": [partial(_set_cmd, "advance"), _get_arg],
                        "tags": ["accepted"]},
                ]},
                {"name": "back",
                    "on_enter": [partial(_set_cmd, "go_back")],
                    "tags": ["accepted"]},
            ], "transitions": [
                [token, "to", "to__arg0"]
                for token in ["TStr", "TWord", "TQuoted"]
            ]},
        ], "transitions": [
            ["TWord_to", "go", "go__to"],
            ["TWord_back", "go", "go__back"],
        ]},
    ],
    "transitions": [
        ["TWord_go", "s", "s__go"],
    ],
    "initial": "s",
    "auto_transitions": False,
    "show_conditions": True,
    "show_state_attributes": True,
    "send_event": True,
}
ignore_transitions(
    _parse_machine_configs, ["TNewline", "TIndent", "TSpace"], "=")
add_resetters(_parse_machine_configs, ["reset"], "s", after="__init__")


_parse_machine = _ParseMachine(**_parse_machine_configs)


class _ParseModel(MachineCtxMnger(_parse_machine)):
    """ A model class for parsing text message. """
    state: Union[partial, Any]
    trigger: Union[partial, Any]
    is_accepted: Callable[..., None]

    cmd: Optional[str]
    args: List[Any]
    kwargs: Dict[str, Any]

    def __init__(self, ev: EventData = None) -> None:
        super().__init__()
        self.cmd = None
        self.args = []
        self.kwargs = {}

    def step(self, token: Token_t) -> bool:
        """ Return (is expected here, its value if expected) for token `token`.
        """
        tname = type(token).__name__
        tvalue = getattr(token, "value", None)
        repr = token_specs[tname].repr
        tvalue = repr(token) if repr is not None else None
        avail_triggers = _parse_machine.get_triggers(self.state)
        for trigger in [f"{tname}_{tvalue}", tname][tvalue is None:]:
            if trigger in avail_triggers:
                self.trigger(trigger, tvalue)
                return True
        return False


def parse(text: str) -> Tuple[Optional[str], List[Any], Dict[str, Any]]:
    """ Return (parsed command if valid, parsed arguments) for `str` `text`.
    """
    with _ParseModel() as model:
        # parse and collect arguments
        for _, t in lex(text):
            if not model.step(t):
                break
        if not _parse_machine.get_state(model.state).is_accepted:
            return None, [], {}

        # Get the corresponding command for the parsing result
        return model.cmd, model.args, model.kwargs
