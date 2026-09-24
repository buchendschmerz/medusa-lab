# 🐍 Medusa Lab 運用手順書（オンデマンド運用）

このドキュメントは「**普段は止めておき、調べたいときだけ依頼して動かす**」運用のための、
画面項目レベルの設定手順です。専門用語には都度かんたんな説明を付けています。

- お金（AIの利用料）がかかるのは **研究サイクルを 1 回動かしたときだけ** です。止めている間はゼロです。
- 毎週の自動起動は無効化済みです（`.github/workflows/weekly_prompt.yml`）。

---

## ⚠️ 前提：まず PR を main に取り込む（マージ）

GitHub の仕様上、「Run workflow」ボタンや外部からの起動（`repository_dispatch`）は
**ワークフロー定義が既定ブランチ（main）に存在して初めて有効**になります。

1. [PR #1](https://github.com/buchendschmerz/medusa-lab/pull/1) を開く
2. 緑の **「Merge pull request」** → **「Confirm merge」** を押す

これをやらないと、以下の「Run workflow」ボタンや Slack 依頼は表示・動作しません。

---

## 1. AI のカギを登録（ANTHROPIC_API_KEY）＝本番品質に必須

未登録でも動きますが「お試しモード（テンプレート）」になり、内容は簡易版です。
本物の論文品質を出すには Anthropic の API キーを登録します。

### 1-1. API キーを発行
1. <https://console.anthropic.com> にログイン
2. 左メニュー **API Keys** → **Create Key**
3. 表示されたキー（`sk-ant-...`）をコピー（**この画面でしか見られません**）

### 1-2. GitHub に登録
1. リポジトリの **Settings**（上部タブ）→ 左メニュー **Secrets and variables** → **Actions**
2. **New repository secret**
   - **Name**: `ANTHROPIC_API_KEY`
   - **Secret**: さきほどの `sk-ant-...`
3. **Add secret**

> 💡 キーの値はチャットに貼らないでください。「登録しました」とだけ教えていただければ十分です。

---

## 2. 結果を Slack に通知（SLACK_WEBHOOK_URL）

研究の開始・完了を Slack のチャンネルに流します（依頼方法に関わらず共通で使えます）。

### 2-1. Slack で Incoming Webhook を作る
1. <https://api.slack.com/apps> を開く → **Create New App** → **From scratch**
2. **App Name** に `Medusa Lab`、通知先の **Workspace** を選び **Create App**
3. 左メニュー **Incoming Webhooks** → 右上のトグルを **On**
4. 下の **Add New Webhook to Workspace** → 通知したい **チャンネル** を選び **Allow**
5. 生成された **Webhook URL**（`https://hooks.slack.com/services/....`）をコピー

### 2-2. GitHub に登録
1. **Settings → Secrets and variables → Actions → New repository secret**
   - **Name**: `SLACK_WEBHOOK_URL`
   - **Secret**: さきほどの Webhook URL
2. **Add secret**

（Discord を使う場合は同様に `DISCORD_WEBHOOK_URL`。）

### 2-3.（任意）通知にダッシュボード画像を出す
`config.yaml` の `notify.dashboard_url` に、公開画像の URL を入れると通知に画像が付きます。
例（このリポジトリが公開の場合）:
`https://raw.githubusercontent.com/buchendschmerz/medusa-lab/main/outputs/dashboard/lab.gif`

---

## 3. 依頼のかけ方（2 通り）

### 方法 A：GitHub の「Run workflow」ボタン（推奨・トークン不要）

パソコンでもスマホのブラウザでも使えます。追加のカギ（トークン）は不要です。

1. リポジトリ上部の **Actions** タブを開く
2. 左の一覧から **「🧪 Research cycle (研究サイクル)」** を選ぶ
3. 右側の **「Run workflow」** ボタンを押す（ドロップダウンが開く）
4. 入力欄:
   - **研究テーマ（日本語OK）**: 例 `SNSで新語が広まる仕組み`
   - **文献検索キーワード**（任意・英語推奨）: 例 `naming game, language evolution`
   - **mode**: `hybrid`（論文＋人間向け提案の両方）/ `in-silico`（論文のみ）/ `human`（提案のみ）
   - **offline**: チェックを外す（＝本番。AIを使う）
5. 緑の **「Run workflow」** を押す → 数分〜十数分で成果物が **プルリクエスト**として届きます

### 方法 B：Slack から依頼する

**重要**：Slack の Workflow Builder には「任意の URL に HTTP リクエストを送る」標準ステップが
ありません。そのため Slack から GitHub を直接起動するには、次のどちらかの“橋渡し”が必要です。

- **B-1. 自動化ツール経由（おすすめ・非エンジニア向け）**：Make（旧 Integromat）/ Zapier / n8n の
  「HTTP リクエスト（POST）」機能を使う。無料枠でも可能な場合が多い。
- **B-2. Slack 補助アプリ経由**：`Workflow Buddy` という無料アプリを入れると Workflow Builder に
  「Outgoing Webhook（HTTP 送信）」ステップが増える（導入がやや技術的）。

いずれも、最終的に GitHub の以下の API を **POST** で叩きます（この仕組みは配線済みです）。

```
POST https://api.github.com/repos/buchendschmerz/medusa-lab/dispatches
Headers:
  Authorization: Bearer <あなたのトークン>
  Accept: application/vnd.github+json
  X-GitHub-Api-Version: 2022-11-28
Body (JSON):
  {"event_type":"medusa-theme",
   "client_payload":{"theme":"調べたいテーマ","keywords":"naming game","mode":"hybrid"}}
```

#### 手順 B-0：GitHub トークン（PAT）を発行
「外部から GitHub を動かす鍵」です。権限は最小限にします。

1. GitHub 右上のアイコン → **Settings** → 最下部 **Developer settings**
2. **Personal access tokens → Fine-grained tokens** → **Generate new token**
   - **Token name**: `medusa-dispatch`
   - **Expiration**: 90 日など（切れたら再発行）
   - **Repository access**: **Only select repositories** → `buchendschmerz/medusa-lab`
   - **Permissions → Repository permissions → Contents**: **Read and write**
     （※ `dispatches` API は Contents 書き込み権限が必要）
3. **Generate token** → 表示された値（`github_pat_...`）をコピー（**この画面でしか見られません**）

> 💡 このトークンは強力です。チャットに貼らず、下記の自動化ツールの「秘密の変数」欄にだけ入れてください。

#### 手順 B-1：Make.com で Slack → GitHub をつなぐ（画面項目）
1. <https://www.make.com> に登録・ログイン → **Create a new scenario**
2. 最初のモジュール（トリガー）に **Slack** を追加 → イベントは
   **「Watch Public Channel Messages」**（指定チャンネルの新規投稿を監視）
   - Slack アカウントを接続し、依頼用チャンネル（例：`#medusa`）を選択
3. 次のモジュールに **HTTP** を追加 → **「Make a request」**
   - **URL**: `https://api.github.com/repos/buchendschmerz/medusa-lab/dispatches`
   - **Method**: `POST`
   - **Headers**（3 つ追加）:
     - `Authorization` = `Bearer github_pat_...`（B-0 のトークン）
     - `Accept` = `application/vnd.github+json`
     - `X-GitHub-Api-Version` = `2022-11-28`
   - **Body type**: `Raw` / **Content type**: `JSON (application/json)`
   - **Request content**:
     ```json
     {"event_type":"medusa-theme","client_payload":{"theme":"{{1.text}}","mode":"hybrid"}}
     ```
     （`{{1.text}}` は Slack 投稿の本文。Make が自動で差し込みます）
4. 右下 **Save** → 左下のトグルを **ON（スケジュール実行を有効化）**
5. これで、指定チャンネルに「調べたいテーマ」を投稿すると研究が始まります

> Zapier の場合も考え方は同じ：トリガー=「New Message Posted to Channel」、
> アクション=「Webhooks by Zapier → Custom Request（POST）」に上記 URL/ヘッダー/本文を設定。

---

## 4. 動作確認

1. まず **方法 A（GitHub ボタン）** で `offline` にチェックを入れて 1 回実行（無料・お試し）
   → 成果物 PR が作られれば配線 OK
2. 次に `ANTHROPIC_API_KEY` を登録し、`offline` のチェックを外して本番実行 → 論文の質を確認
3. Slack 通知が来るか確認（`SLACK_WEBHOOK_URL` 登録後）
4. Slack 依頼（方法 B）を設定した場合、チャンネルにテーマを投稿してみる

### コマンドで直接テスト（任意・上級）
トークンを使って手元から起動を試す例（`<PAT>` は実際の値に置換）:
```bash
curl -X POST \
  -H "Authorization: Bearer <PAT>" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/buchendschmerz/medusa-lab/dispatches \
  -d '{"event_type":"medusa-theme","client_payload":{"theme":"テスト：新語の拡散","mode":"hybrid"}}'
```
成功すると HTTP 204（本文なし）が返り、Actions に実行が現れます。

---

## 5. 費用と停止

- 課金されるのは **研究サイクル 1 回の実行ごと**（Anthropic API の利用料）。頻度はあなた次第。
- しばらく使わないときは、登録した `ANTHROPIC_API_KEY` を消せば AI 実行は止まります（お試しモードに戻る）。
- 自動起動は既に無効。完全に止めたい場合は Slack 側の自動化シナリオを OFF にすれば依頼経路も止まります。

---

## 6. 困ったとき

| 症状 | 確認ポイント |
|---|---|
| 「Run workflow」ボタンが無い | PR #1 を main にマージしたか（前提章） |
| Slack 依頼が動かない | PAT の権限（Contents: Read and write）、URL/ヘッダーのタイプミス、シナリオが ON か |
| 論文が簡易的 | `ANTHROPIC_API_KEY` が未登録＝お試しモード |
| Slack 通知が来ない | `SLACK_WEBHOOK_URL` の登録、Webhook のチャンネル指定 |
| PR は来たが PDF が無い | Actions のログを確認（LaTeX ビルド失敗時はレポート HTML は生成されます） |
