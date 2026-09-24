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
