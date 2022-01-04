from contextlib import suppress
from logging import Logger
from typing import Any, NamedTuple, Type, cast

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import load_only
from sqlalchemy.orm.exc import NoResultFound, ObjectDeletedError

from fsm import TocMachine

db = SQLAlchemy()


class _User(cast(Type, db.Model)):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Text, unique=True, nullable=False)
    state = db.Column(db.Text, nullable=False)


class _Data(NamedTuple):
    id: int
    user_id: str
    state: str

    @classmethod
    def from_model(cls, model: "User") -> "_Data":
        return cls(**{k: getattr(model, k) for k in cls._fields})

    def restore_model(self, model: "User") -> None:
        for k, v in self._asdict().items():
            setattr(model, k, v)


class User():
    _model: _User
    _before: _Data

    def __init__(self, model: _User) -> None:
        self._model = model
        self._before = _Data.from_model(model)

    def __getattribute__(self, __name: str) -> Any:
        if __name in _Data._fields:
            return self._model.__getattribute__(__name)
        return super().__getattribute__(__name)

    def __setattr__(self, __name: str, __value: Any) -> None:
        if __name in _Data._fields:
            return self._model.__setattr__(__name, __value)
        return super().__setattr__(__name, __value)

    @classmethod
    def from_user_id(cls, user_id: str) -> "User":
        with suppress(NoResultFound, ObjectDeletedError):
            return cls(db.session.query(_User)
                       .options(load_only("user_id"))
                       .filter_by(user_id=user_id).one())
        # new user; add user (may fail due to race conditions; just raise)
        with db.session.begin_nested():
            res = cls(
                _User(user_id=user_id, state=TocMachine.configs["initial"]))
            db.session.add(res._model)
            return res

    def load_machine(self, logger: Logger) -> TocMachine:
        return TocMachine(logger, initial=self.state)

    def save_machine(self, machine: TocMachine) -> None:
        try:
            # verify
            self._model = (
                db.session.query(_User)
                .filter_by(**self._before._asdict()).one())
            # update
            self._model.state = machine.state
            self._before = _Data.from_model(self._model)
            db.session.commit()
        except NoResultFound:
            # failed due to race conditions
            db.session.rollback()
            raise
