try:
    import unzip_requirements
except ImportError:
    pass

import logging
import os
from xmlrpc.client import SYSTEM_ERROR
from slack_bolt import App
import openai
import boto3
import time

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = 'lambda-chatbot-app-history'

table = dynamodb.Table(TABLE_NAME)

COMMAND = os.environ["SLACK_COMMAND"]
MODEL = os.environ["OPENAI_MODEL"]
SYSTEM_CONTENT = "You are an excellent assistant."
MAX_HISTORY = 20
OPENAI_API_TIMEOUT = 50

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
    # リスナーの処理を 3 秒以内に完了
    logging.debug(body)
    ack()


def process_request(respond, body):
    # メンションのメッセージに対して返信する
    logging.debug(body)

    ts = body["event"]["ts"]
    prompt = body["event"]["text"]
    channel_id = body["event"]["channel"]
    user_id = body["event"]["user"]
    answer = send_prompt(user_id, prompt)
    post_message(channel_id, ts, f"<@{user_id}> {answer}")


def post_message(channel_id, thread_td, message):
    # スレッドに対してメッセージを返信する
    try:
        result = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_td,
            text=message,
            reply_broadcast = True
        )
    except Exception as e:
        logging.error("Error sending postMessage event: {}".format(e))

def send_prompt(user_id, prompt=''):
    # 対話履歴と最新のメンションの内容からプロンプトを作成してチャットモデルに送信する

	# promptがない場合
    if not prompt:
        return

    answer = ''

    try:        
        # 24時間前のUnix Time
        one_day_ago = int(time.time()) - 24 * 60 * 60

        # dynamoDBにプロンプトを保存
        items = [
            {
                'id': user_id,
                'timestamp': int(time.time()),
                'role': 'user',
                'content': prompt
            }
        ]

        # dynamoDBから過去履歴を取得
        response = table.query(
            KeyConditionExpression="id = :id and #ts >= :timestamp",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={
                ":id": user_id,
                ":timestamp": one_day_ago
            },
            ScanIndexForward=False, 
            Limit=MAX_HISTORY
        )

        # 過去履歴からメッセージを生成
        messages = [{"role": "system", "content": SYSTEM_CONTENT}]
        for item in response['Items']:
            messages.append({"role": item["role"], "content": item["content"]})

        messages.append({"role": "user", "content": prompt})

        # 回答を生成
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            temperature=0,
            timeout = OPENAI_API_TIMEOUT
        )
        answer = response['choices'][0]['message']['content']

        # dynamoDBに回答を挿入
        items.append({
            'id': user_id,
            'timestamp': int(time.time()),
            'role': 'assistant',
            'content': answer
        })
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    except Exception as e:
        answer = f"例外が発生しました: {str(e)}"

    return answer

# メンションに反応するように設定
app.event("app_mention")(ack=respond_to_slack_within_3_seconds, lazy=[process_request])

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