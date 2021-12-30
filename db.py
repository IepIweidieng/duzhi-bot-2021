from logging import Logger
from flask_sqlalchemy import SQLAlchemy

from fsm import TocMachine

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Text, unique=True, nullable=False)
    state = db.Column(db.Text, nullable=False)

    @classmethod
    def from_user_id(cls, user_id: str) -> "User":
        id, _ = db.session.query(cls.id, cls.user_id).filter_by(
            user_id=user_id).first()
        if id is None:  # new user
            user = cls(user_id=user_id, state=TocMachine.configs["initial"])
            db.session.add(user)
            db.session.commit()
            return user
        return db.session.query(cls).get(id)

    def load_machine(self, logger: Logger) -> TocMachine:
        return TocMachine(logger, initial=self.state)

    def save_machine(self, machine: TocMachine) -> None:
        self.state = machine.state
        db.session.commit()
