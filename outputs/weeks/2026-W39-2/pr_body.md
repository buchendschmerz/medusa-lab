## 🐍 Medusa Lab 2026-W39-2 — 研究サイクル完了

**テーマ:** LLMはオノマトペを接地・創発できるか ｜ **モード:** `hybrid` ｜ **LLM:** `offline (llm.provider = offline)`

📄 **論文:** Naming Game model of lexical convention formation: an in-silico study — [PDF](outputs/weeks/2026-W39-2/paper/paper.pdf) · [LaTeX](outputs/weeks/2026-W39-2/paper/paper.tex)
🖍️ **査読判定:** `minor_revision` (3.37/5) · [査読記録](outputs/weeks/2026-W39-2/review/review.md)

📊 **主な結果:**
- On the complete graph, convergence time grows as N^1.39 (R^2=0.97); the mean-field prediction is N^1.5.
- On the small-world network the fitted exponent is 2.09, and the peak memory grows as N^1.01 versus N^1.40 on the complete graph.
- At N=256, consensus took 30.3 interactions per agent on the complete graph and 412.4 on the small-world network.

🧪 **【実験提案書】人間がやると面白い仮説＆実験プロトコル:**
- [E1: オンライン・ネーミングゲーム実験：つながり方で「新語の合意」は速くなるか](outputs/weeks/2026-W39-2/proposals/E1-online-naming-game-experiment-does-netwo.md) — n = 12 / 条件
- [E2: 直感 vs シミュレーション：人はミクロなルールからマクロな帰結を予測できるか](outputs/weeks/2026-W39-2/proposals/E2-intuition-vs-simulation-can-people-fores.md) — n = 64 / 条件

<details><summary>仮説と振り分け</summary>

- **H1** `in_silico` In a well-mixed population the time to lexical consensus grows super-linearly with population size, with an exponent close to the mean-field value 3/2.
- **H2** `in_silico` Local small-world contact structure lowers the peak lexical memory but slows the final agreement compared with a well-mixed population.
- **H3** `human` 誰とでも話せる集団（完全混合）は、近所としか話さない集団（スモールワールド）より早く呼び名の合意に達する。
- **H4** `human` 人々はミクロな行動ルールが生むマクロな結果（集団が大きくなるほど、共通語ができるまでの時間は人数の増え方以上に長くなる）を系統的に読み違える。

</details>

[📑 週次レポート](outputs/weeks/2026-W39-2/report.html) · [成果物フォルダ](outputs/weeks/2026-W39-2/)

> [!IMPORTANT]
> この Pull Request の論文・提案書は Medusa Lab のAIエージェントが自律的に生成したものです。マージ前に所長（人間）が内容・引用・倫理面を確認してください。

<details><summary>🕹️ Lab status</summary>

**テーマ:** LLMはオノマトペを接地・創発できるか ｜ **モード:** `hybrid` ｜ **状態:** 🟢 `DONE` 完了

| | エージェント | 状態 | いまやっていること | 進捗 |
|:-:|:--|:--|:--|:--|
| 🏛️ | **所長**<br><sub>人間</sub> | 👀 `YOUR TURN` 成果の確認待ち | PRで論文と実験提案書をご確認ください | |
| 🔍 | **Scout**<br><sub>論文収集と課題抽出</sub> | 🟢 `DONE` 完了 | 文献4本・課題3件を抽出 | `▰▰▰▰▰▰▰▰▰▰` 100% |
| 🧠 | **Analyst**<br><sub>理論モデル構築と仮説・実験デザイン</sub> | 🟡 `WAITING` 所長待ち | 人間向けの仮説2件は所長の出番です |  |
| 💻 | **Coder**<br><sub>数理・計算シミュレーション</sub> | 🟢 `DONE` 完了 | 計算完了：図2枚・指標8個 | `▰▰▰▰▰▰▰▰▰▰` 100% |
| 📝 | **Writer**<br><sub>LaTeX論文と実験プロトコル執筆</sub> | 🟢 `DONE` 完了 | 査読コメントを反映した提案書2件 | `▰▰▰▰▰▰▰▰▰▰` 100% |
| 🖍️ | **Reviewer**<br><sub>エージェント間ピアレビュー</sub> | 🟢 `DONE` 完了 | 判定: 軽微な修正で採択（3.37/5） | `▰▰▰▰▰▰▰▰▰▰` 100% |

**パイプライン:** ✅ テーマ受付 → ✅ 文献調査 → ✅ 理論・仮説 → ✅ 計算実験 → ✅ 論文・提案 → ✅ 査読 → ✅ 公開

<sub>文献 4 · 仮説(計算+人間) 2+2 · 図 2 · 査読 3.4/5 · 実験提案 2 · 更新 2026-09-24 23:23 UTC</sub>

</details>
