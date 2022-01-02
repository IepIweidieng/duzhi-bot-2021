import os
import sys

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file
from flask.typing import ResponseReturnValue
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage
from linebot.models.sources import SourceUser

import file
from db import User, db
from fsm import TocMachine

load_dotenv()

app = Flask(__name__, static_url_path="")


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

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event: MessageEvent) -> None:
    if not isinstance(event.source, SourceUser):
        return

    msgs = []

    def reply(msg: TocMachine.Msg_t) -> None:
        msgs.extend(msg if isinstance(msg, list) else (msg,))

    user = User.from_user_id(event.source.user_id)
    app.logger.info(f"Loaded data for user {user.user_id}: {user.state}")
    machine = user.load_machine(app.logger)
    machine.exec(event, reply)
    user.save_machine(machine)
    app.logger.info(f"Saved data for user {user.user_id}: {user.state}")

    if len(msgs):
        line_bot_api.reply_message(event.reply_token, msgs[-5:])


@app.route("/show-fsm", methods=["GET"])
def show_fsm() -> ResponseReturnValue:
    url = "fsm.png"
    path = _url_to_path(url)
    graph = TocMachine(app.logger).get_graph()
    for node in graph.iternodes():
        if node.attr["label"] in []:

    graph.draw(path, prog="dot", format="png")
    return send_file(path, mimetype="image/png")


if __name__ == "__main__":
    port = os.environ.get("PORT", 8000)
    file.mkdir(tmp_dir)
    app.run(host="0.0.0.0", port=port, debug=True)
