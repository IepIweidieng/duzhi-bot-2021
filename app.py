import os
import sys

from flask import Flask, jsonify, request, abort, send_file
from flask.typing import ResponseReturnValue
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from fsm import TocMachine

load_dotenv()

app = Flask(__name__, static_url_path="")

machine = TocMachine(app.logger)


# get required variables from your environment
def _require_env(env: str) -> str:
    res = os.getenv(env)
    if res is None:
        app.logger.critical(f"Specify {env} as environment variable.")
        sys.exit(1)
    return res

channel_secret = _require_env("LINE_CHANNEL_SECRET")
channel_access_token = _require_env("LINE_CHANNEL_ACCESS_TOKEN")

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
        app.logger.exception("Got exception from LINE Messaging API", exc_info=e)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event: MessageEvent) -> None:
    app.logger.info(f"FSM state: {machine.state}")

    msgs = []
    def reply(msg: TocMachine.Msg_t) -> None:
        msgs.extend(msg if isinstance(msg, list) else (msg,))

    if not machine.advance(event, reply):
        msgs.append(TextSendMessage(text="Not Entering any State"))
    if len(msgs):
        line_bot_api.reply_message(event.reply_token, msgs[-5:])


@app.route("/show-fsm", methods=["GET"])
def show_fsm() -> ResponseReturnValue:
    machine.get_graph().draw("fsm.png", prog="dot", format="png")
    return send_file("fsm.png", mimetype="image/png")


if __name__ == "__main__":
    port = os.environ.get("PORT", 8000)
    app.run(host="0.0.0.0", port=port, debug=True)
