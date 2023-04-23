# slack-chatbot-lambda

AWS Lambda で動作する ChatGPT モデルを使用した Slack Bot 

## 動作環境

* AWS CLI 2.11
* python 3.9
* Serverless Framework 3.29

## デプロイ手順

### 必要なもの

* デプロイするAWSアカウント
* Slact アプリおよび以下の情報
  * Bot User OAuth Token
  * Signing Secret
* OpenAIの API KEY

### デプロイ手順

新規にSlackアプリを作成します。App Manifestには以下の内容を設定します。 
urlは後の手順で変更します。 

```
display_information:
  name: lambda-chatbot-app
features:
  bot_user:
    display_name: chatbot
    always_online: true
oauth_config:
  scopes:
    bot:
      - chat:write
      - chat:write.public
      - app_mentions:read
settings:
  event_subscriptions:
    request_url: https://example.execute-api.us-east-1.amazonaws.com/slack/events
    bot_events:
      - app_mention
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

アプリが作成できたらBot User OAuth TokenおよびSigning Secretをメモしておきます。 

依存モジュールをインストールします。 

```Bash
$ sls plugin install -n serverless-python-requirements
$ npm i -D serverless-dotenv-plugin
```


環境変数にSlackのBot User OAuth Token、Signing Secretおよび OpenAIのAPI Keyを設定します。 

```Bash
$ export SLACK_SIGNING_SECRET=9999999...
$ export SLACK_BOT_TOKEN=xoxb-xxxxx....
$ export OPENAI_API_KEY=xx-xxxxx....
```


アプリケーションをデプロイします。 

```Bash
$ sls deploy
```

生成されたendpointのURLを、SlackアプリのApp ManifestのURLに設定し、アプリをインストールしなおします。 

### 実行方法

slackのチャンネルなどで、botにメンションを付けて質問などを行います 

```
@chatbot 質問内容
```