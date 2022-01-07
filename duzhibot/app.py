import logging
import multiprocessing as mp
import os
import shutil
import sys
from contextlib import AbstractContextManager
from typing import Optional, cast

from dotenv import load_dotenv
from flask import Blueprint, Flask, abort
from flask import g as fg
from flask import jsonify, request, send_file
from flask.logging import default_handler
from flask.typing import ResponseReturnValue
from flask.wrappers import Response
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage
from linebot.models.sources import SourceUser
from werkzeug.utils import redirect, send_from_directory

import file
import parse
from db import User, db
from fsm import WorldModel, world_machine
from fsm_utils import machine_ctx_mnger

load_dotenv()


_LOGGER_ROOT = logging.getLogger()
_LOGGER_ROOT.addHandler(default_handler)


class App(Flask):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("static_url_path", "")
        super().__init__(*args, **kwargs)
        _LOGGER_ROOT.setLevel(self.logger.getEffectiveLevel())
        self.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
        init_db(self)

    def run(self, *args, **kwargs) -> None:
        if not self.debug or os.getenv('WERKZEUG_RUN_MAIN') == 'true':
            with self.app_context():
                _init()
        return super().run(*args, **kwargs)


bp = Blueprint("bp", __name__)


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
        _LOGGER_ROOT.critical(f"Specify {env} as environment variable.")
        sys.exit(1)
    return res


channel_secret = _require_env("LINE_CHANNEL_SECRET")
channel_access_token = _require_env("LINE_CHANNEL_ACCESS_TOKEN")


def init_db(app: Flask) -> None:
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


@bp.route("/callback", methods=["POST"])
def callback() -> ResponseReturnValue:
    signature = request.headers["X-Line-Signature"]
    # get request body as text
    body = request.get_data(as_text=True)
    _LOGGER_ROOT.info(f"Request body: {body}")

    # handle webhook body
    try:
        handler.handle(body, signature)
    except LineBotApiError as e:
        _LOGGER_ROOT.exception(
            "Got exception from LINE Messaging API", exc_info=e)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        _LOGGER_ROOT.exception("Got exception from handler", exc_info=e)

    return cast(ResponseReturnValue, "OK")


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event: MessageEvent) -> None:
    if not isinstance(event.source, SourceUser):
        return

    msgs = []

    def reply(msg: WorldModel.Msg_t) -> None:
        msgs.extend(msg if isinstance(msg, list) else (msg,))

    user = User.from_user_id(event.source.user_id)
    _LOGGER_ROOT.info(f"Loaded data for user {user.user_id}: {user.state}")

    model = user.load_machine_model()
    with machine_ctx_mnger(world_machine, model):
        model.exec(event, reply)
        user.save_machine_model(model)
        _LOGGER_ROOT.info(f"Saved data for user {user.user_id}: {user.state}")

    if len(msgs):
        line_bot_api.reply_message(event.reply_token, msgs[-5:])


@bp.route("/show-fsm", methods=["GET"])
def show_fsm() -> ResponseReturnValue:
    return send_file("img/show-fsm.png", mimetype="image/png")


def draw_fsm(path: str, model_mnger: AbstractContextManager) -> None:
    with model_mnger as model:
        model.get_graph().draw(path, prog="dot", format="png")


def _init() -> None:
    """ Codes to run when app.run() is invoked. """
    file.mkdir(tmp_dir)
    file.mkdir(_url_to_path("img"))

    def tasks_async() -> None:
        """ Async tasks to run without blocking. """
        # prepare the images for serving
        shutil.copytree("img", _url_to_path("img"), dirs_exist_ok=True)
        img = {
            "main": "img/show-fsm.png",
            "lexer": "img/show-fsm-lexer.png",
            "parser": "img/show-fsm-parser.png",
        }
        # draw the FSM diagrams
        draw_fsm(img["main"], machine_ctx_mnger(world_machine, WorldModel()))
        draw_fsm(img["lexer"], parse._LexModel())
        draw_fsm(img["parser"], parse._ParseModel())
        for f in img.values():
            shutil.copy2(f, _url_to_path("img"))

    mp.Process(target=tasks_async, daemon=True).start()


@bp.before_request
def before_request() -> Optional[ResponseReturnValue]:
    if not request.is_secure:
        # For ngrok
        fg.rqst_url = request.url.replace("http://", "https://", 1)
        fg.rqst_root_url = (
            request.root_url.replace('http://', 'https://', 1).rstrip('/'))


@bp.route("/<path:path>")
def send_static_content(path: str) -> ResponseReturnValue:
    return send_from_directory("static", path, request.environ)

def main(app: Flask) -> None:
    port = int(os.environ.get("PORT", 8000))
    if _LOGGER_ROOT.getEffectiveLevel() > logging.INFO:
        _LOGGER_ROOT.setLevel(logging.INFO)
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main(App(__name__, static_url_path=""))
