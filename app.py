try:
    import unzip_requirements
except ImportError:
    pass

import logging
import os
from xmlrpc.client import SYSTEM_ERROR
from slack_bolt import App
import openai
import json


COMMAND = '/chat'
MODEL = "gpt-3.5-turbo"
SYSTEM_CONTENT = "あなたは優秀なアシスタントです。"

# OPENAIのAPI KEY
api_key=os.environ["OPENAI_API_KEY"]

# 動作確認用にデバッグレベルのロギングを有効にします
# 本番運用では削除しても構いません
logging.basicConfig(level=logging.DEBUG)


app = App(
    # リクエストの検証に必要な値
    # Settings > Basic Information > App Credentials > Signing Secret で取得可能な値
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    # 上でインストールしたときに発行されたアクセストークン
    # Settings > Install App で取得可能な値
    token=os.environ["SLACK_BOT_TOKEN"],

    # AWS Lamdba では、必ずこの設定を true にしておく必要があります
    process_before_response=True,
)

def respond_to_slack_within_3_seconds(body, ack):
    if body.get("text") is None:
        ack(f":x: Usage: {COMMAND} (prompt here)")
    else:
        title = body["text"]
        ack(f"Accepted! (task: {title})")


def process_request(respond, body):
    
    prompt = body["text"]
    answer = send_prompt(prompt)
    respond(f"{answer}")

def send_prompt(prompt=''):

	# promptがない場合
    if not prompt:
        return

    response = openai.ChatCompletion.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_CONTENT},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    return response['choices'][0]['message']['content']

app.command(COMMAND)(ack=respond_to_slack_within_3_seconds, lazy=[process_request])


if __name__ == "__main__":
    # python app.py のように実行すると開発用 Web サーバーで起動します
    app.start()

# これより以降は AWS Lambda 環境で実行したときのみ実行されます

from slack_bolt.adapter.aws_lambda import SlackRequestHandler

# ロギングを AWS Lambda 向けに初期化します
SlackRequestHandler.clear_all_log_handlers()
logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

# AWS Lambda 環境で実行される関数
def handler(event, context):
    # AWS Lambda 環境のリクエスト情報を app が処理できるよう変換してくれるアダプター
    slack_handler = SlackRequestHandler(app=app)
    # 応答はそのまま AWS Lambda の戻り値として返せます
    return slack_handler.handle(event, context)