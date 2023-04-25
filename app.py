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

    # AWS Lamdba では、必ずこの設定を true にしておく
    process_before_response=True,
)

def respond_to_slack_within_3_seconds(body, ack):
    # リスナーの処理を 3 秒以内に完了
    logging.debug(body)
    ack()


def process_mention(respond, body):
    # メンションのメッセージに対して返信する
    logging.debug(body)
    if "event" not in body:
        return

    # 会話履歴の取得
    thread_ts = body["event"]["ts"]
    if "thread_ts" in body["event"]:
        # スレッドの途中でメンションされた場合
        thread_ts = body["event"]["thread_ts"]
    channel_id = body["event"]["channel"]
    history_id = f"{channel_id}:{thread_ts}"
    history = get_history(history_id)
    if len(history) > 0:
        # 会話履歴がある場合はリプライメッセージ処理で対応(何もしない)
        return 

    start_timestamp = int(time.time())

    # プロンプトの作成
    message = body["event"]["text"]
    user_id = body["event"]["user"]
    prompt = create_prompt([], message)
    
    # 回答の取得とSlackへの送信
    answer = send_prompt(prompt)
    post_message(channel_id, thread_ts, f"<@{user_id}> {answer}")

    # 会話履歴の保存
    save_history(history_id, message, answer, start_timestamp)


def process_message(respond, body):
    # リプライに対して返信する
    if "event" not in body:
        return

    if "thread_ts" not in body["event"]:
        # 親メッセージには反応しない
        return 

    start_timestamp = int(time.time())

    # 会話履歴の取得
    thread_ts =  body["event"]["thread_ts"]
    channel_id = body["event"]["channel"]
    history_id = f"{channel_id}:{thread_ts}"
    history = get_history(history_id)
    if len(history) == 0:
        # 会話履歴がないスレッドには対応しない
        return 

    # プロンプトの作成
    message = body["event"]["text"]
    user_id = body["event"]["user"]
    prompt = create_prompt(history, message)

    # 回答の取得とSlackへの送信
    answer = send_prompt(prompt)
    post_message(channel_id, thread_ts, f"<@{user_id}> {answer}")

    # 会話履歴の保存
    save_history(history_id, message, answer, start_timestamp)


def save_history(history_id, message, answer, start_timestamp):
        # dynamoDBにプロンプトを保存
        items = [
            {
                'id': history_id,
                'timestamp': start_timestamp,
                'role': 'user',
                'content': message
            }
        ]

        # dynamoDBに回答を挿入
        items.append({
            'id': history_id,
            'timestamp': int(time.time()),
            'role': 'assistant',
            'content': answer
        })
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)


def get_history(history_id):
    # 24時間前のUnix Time
    one_day_ago = int(time.time()) - 24 * 60 * 60

    # dynamoDBから過去履歴を取得
    response = table.query(
        KeyConditionExpression="id = :id and #ts >= :timestamp",
        ExpressionAttributeNames={"#ts": "timestamp"},
        ExpressionAttributeValues={
            ":id": history_id,
            ":timestamp": one_day_ago
        },
        ScanIndexForward=False, 
        Limit=MAX_HISTORY
    )
    return response['Items']


def create_prompt(history, message):
    # 過去履歴からメッセージを生成
    messages = [{"role": "system", "content": SYSTEM_CONTENT}]
    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})

    messages.append({"role": "user", "content": message})

    return messages


def post_message(channel_id, thread_ts, message):
    # スレッドに対してメッセージを返信する
    try:
        result = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=message
        )
    except Exception as e:
        logging.error("Error sending postMessage event: {}".format(e))

def send_prompt(messages):
    logging.debug(messages)
    # 対話履歴と最新のメンションの内容からプロンプトを作成してチャットモデルに送信する

    try:        

        # 回答を生成
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            temperature=0,
            timeout = OPENAI_API_TIMEOUT
        )
        answer = response['choices'][0]['message']['content']

 
    except openai.error.Timeout as e:
        answer = f"タイムアウトが発生しました: {str(e)}"

    except Exception as e:
        answer = f"例外が発生しました: {str(e)}"

    return answer

# メンションに反応するように設定
app.event("app_mention")(ack=respond_to_slack_within_3_seconds, lazy=[process_mention])

# メッセージに反応するように設定
app.message()(ack=respond_to_slack_within_3_seconds, lazy=[process_message])

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