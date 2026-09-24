{#- Body of the Monday "theme request" Issue (rendered by medusa/notifier.py). -#}
<!-- medusa:theme-request cycle={{ cycle_id }} -->
{% if lang == "ja" %}
## 🐍 {{ director }}、今週の{{ lab_name }}の研究テーマは何にしますか？

おはようございます！ エージェントたちは研究室で待機しています（週 `{{ cycle_id }}`）。
このIssueに **`/theme` で始まるコメント** を書くと、今週の研究サイクルが自動で始まります。
{% else %}
## 🐍 {{ director }}, what should {{ lab_name }} research this week?

Good morning! The agents are waiting in the lab (week `{{ cycle_id }}`).
**Comment on this Issue starting with `/theme`** and this week's research cycle starts automatically.
{% endif %}
{% if dashboard_url %}

![{{ lab_name }} dashboard]({{ dashboard_url }})
{% endif %}

```text
/theme {{ example_theme }}
/keywords {{ example_keywords }}
/mode hybrid
/note {{ "被験者実験のアイデアも多めにお願いします" if lang == "ja" else "Please include playful human-experiment ideas" }}
```

{% if lang == "ja" %}
| コマンド | 必須 | 説明 |
|---|:-:|---|
| `/theme` | ✅ | 研究テーマ（日本語OK。次の行以降に詳しい説明を書いても構いません） |
| `/keywords` | | 文献検索用キーワード（英語推奨・カンマ区切り） |
| `/mode` | | `hybrid`（既定：両方）／ `in-silico`（完全自律で論文まで）／ `human`（人間向け実験提案のみ） |
| `/note` | | エージェントへの補足・要望 |
{% else %}
| Command | Required | Meaning |
|---|:-:|---|
| `/theme` | ✅ | The research theme (add details on the following lines) |
| `/keywords` | | Literature-search keywords (English, comma separated) |
| `/mode` | | `hybrid` (default) / `in-silico` (autonomous paper) / `human` (experiment proposals only) |
| `/note` | | Extra wishes for the agents |
{% endif %}

### 💡 {{ "今週のテーマ候補" if lang == "ja" else "Theme ideas" }}

{% for s in suggestions %}
- {{ s }}
{% endfor %}

### 📊 {{ "前回の研究サイクル" if lang == "ja" else "Last cycle" }}

{{ last_cycle }}

{% if lang == "ja" %}
### 🔄 この後の流れ

1. 🔍 **Scout** が arXiv / OpenAlex で文献を集め、未解決の課題を抽出
2. 🧠 **Analyst** が理論モデルと仮説を構築し、「計算で検証できる仮説」と「人間の手が必要な仮説」に振り分け
3. 💻 **Coder** がサンドボックスでシミュレーションを実行
4. 📝 **Writer** が LaTeX 論文（PDF）と【実験提案書】を執筆
5. 🖍️ **Reviewer** がエージェント間ピアレビューを行い、必要なら改訂
6. 🚀 論文と提案書を Pull Request で{{ director }}にお届けします（進捗はこのIssueのコメントでライブ更新）
{% else %}
### 🔄 What happens next

1. 🔍 **Scout** searches arXiv / OpenAlex and extracts open problems
2. 🧠 **Analyst** builds a model and routes hypotheses to simulation or to human experiments
3. 💻 **Coder** runs the simulation in the sandbox
4. 📝 **Writer** writes the LaTeX paper (PDF) and the experiment proposals
5. 🖍️ **Reviewer** runs inter-agent peer review and requests revisions
6. 🚀 Everything arrives as a Pull Request (live progress is posted on this Issue)
{% endif %}

<sub>🤖 {{ "このIssueは Medusa Lab の weekly_prompt ワークフローが自動作成しました。" if lang == "ja" else "Opened automatically by the Medusa Lab weekly_prompt workflow." }}</sub>
