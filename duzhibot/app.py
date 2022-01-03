import logging
import multiprocessing as mp
import os
import sys
from contextlib import AbstractContextManager
from typing import cast

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file
from flask.logging import default_handler
from flask.typing import ResponseReturnValue
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage
from linebot.models.sources import SourceUser

import file
import parse
from db import User, db
from fsm import WorldModel, world_machine
from fsm_utils import MachineCtxMngable, machine_ctx_mnger

load_dotenv()


class _App(Flask):
    def run(self, *args, **kwargs) -> None:
        if not self.debug or os.getenv('WERKZEUG_RUN_MAIN') == 'true':
            with self.app_context():
                _init()
        return super().run(*args, **kwargs)


app = _App(__name__, static_url_path="")

_LOGGER_ROOT = logging.getLogger()
_LOGGER_ROOT.addHandler(default_handler)
_LOGGER_ROOT.setLevel(app.logger.getEffectiveLevel())


def _url_to_path(url: str) -> str:
    """ Return the path on the file system for the relative URL `url`. """
    return os.path.join("static", url)


tmp_url = "tmp"
""" The relative URL for temporary contents. """
tmp_dir = _url_to_path(tmp_url)
""" The path on the file system for temporary file contents. """


# get required variables from your environment
def _require_env(env: str) -> str:
    res = os.getenv(env)
    if res is None:
        app.logger.critical(f"Specify {env} as environment variable.")
        sys.exit(1)
    return res


channel_secret = _require_env("LINE_CHANNEL_SECRET")
channel_access_token = _require_env("LINE_CHANNEL_ACCESS_TOKEN")

# connect to the database
database_url = _require_env("DATABASE_URL")
# Workaround for the URL scheme
# See https://help.heroku.com/ZKNTJQSK/why-is-sqlalchemy-1-4-x-not-connecting-to-heroku-postgres
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
db.init_app(app)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)


@app.route("/callback", methods=["POST"])
def callback() -> ResponseReturnValue:
    signature = request.headers["X-Line-Signature"]
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # handle webhook body
    try:
        handler.handle(body, signature)
    except LineBotApiError as e:
        app.logger.exception(
            "Got exception from LINE Messaging API", exc_info=e)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        app.logger.exception("Got exception from handler", exc_info=e)

    return cast(ResponseReturnValue, "OK")


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event: MessageEvent) -> None:
    if not isinstance(event.source, SourceUser):
        return

    msgs = []

    def reply(msg: WorldModel.Msg_t) -> None:
        msgs.extend(msg if isinstance(msg, list) else (msg,))

    user = User.from_user_id(event.source.user_id)
    app.logger.info(f"Loaded data for user {user.user_id}: {user.state}")

    model = user.load_machine_model()
    with machine_ctx_mnger(world_machine, model):
        model.exec(event, reply)
        user.save_machine_model(model)
        app.logger.info(f"Saved data for user {user.user_id}: {user.state}")

    if len(msgs):
        line_bot_api.reply_message(event.reply_token, msgs[-5:])


@app.route("/show-fsm", methods=["GET"])
def show_fsm() -> ResponseReturnValue:
    return send_file("img/show-fsm.png", mimetype="image/png")


def draw_fsm(path: str, model_mnger: AbstractContextManager) -> None:
    with model_mnger as model:
        model.get_graph().draw(path, prog="dot", format="png")


def _init() -> None:
    """ Codes to run when app.run() is invoked. """
    file.mkdir(tmp_dir)

    def tasks_async() -> None:
        """ Async tasks to run without blocking. """
        draw_fsm("img/show-fsm.png",
                 machine_ctx_mnger(world_machine, WorldModel()))
        draw_fsm("img/show-fsm-lexer.png", parse._LexModel())
        draw_fsm("img/show-fsm-parser.png", parse._ParseModel())

    mp.Process(target=tasks_async, daemon=True).start()


def main():
    port = int(os.environ.get("PORT", 8000))
    if _LOGGER_ROOT.getEffectiveLevel() > logging.INFO:
        _LOGGER_ROOT.setLevel(logging.INFO)
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
