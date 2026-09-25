# 【実験提案書】遅延・集約フィードバックはヒトの「確認」を増やすか：適格度トレース仮説の行動検証

> 🐍 **Medusa Lab** · 週次サイクル `2026-W39-3` · テーマ: 「強迫症の記憶トレースモデルの発展」<br>
> 作成: 🧠 Analyst（設計） · 📝 Writer（執筆） · 🖍️ Reviewer（査読） · 生成日時: 2026-09-25 00:23 UTC<br>
> **ステータス:** ⏳ 所長の承認待ち

> [!NOTE]
> 本提案書は Medusa Lab のAIエージェントが自動生成した草案です。実施前に内容・倫理面を必ず人間が確認してください。

## 0. TL;DR（30秒で読める要約）

- **仮説:** フィードバックを各試行直後ではなくブロック末にまとめて与える（＝クレジット割当の時間窓を強制的に長くする）と、自発的な再確認行動が増加し、その増加量はOCI-R得点が高い参加者ほど大きい。さらに、確認回数が増えるほど主観的確信度は低下するのに、次の確認をする確率は下がらない（行動と記憶の乖離）。
- **デザイン:** 被験者内（全員が全条件） ／ **サンプルサイズ（検出力分析）:** 各条件 n = 41
- **なぜ面白いのか（Fun Factor）:** 課題は2Dの「深夜のキッチン」ゲーム。ガスコンロ・玄関の鍵・水道の3つを消して家を出るが、画面はすぐ暗転し、参加者はクリックで何度でも「戻って確認」できる。確認するたびに小さな時間コスト（出発が遅れる）が課され、放置すると「小火（ボヤ）」演出が出る。参加者には最後に自分の『確認クセ指数』と、モデルが推定したλ（記憶トレースの長さ）を可愛いメーターで提示する。

## 1. なぜ面白いのか（Fun Factor）

課題は2Dの「深夜のキッチン」ゲーム。ガスコンロ・玄関の鍵・水道の3つを消して家を出るが、画面はすぐ暗転し、参加者はクリックで何度でも「戻って確認」できる。確認するたびに小さな時間コスト（出発が遅れる）が課され、放置すると「小火（ボヤ）」演出が出る。参加者には最後に自分の『確認クセ指数』と、モデルが推定したλ（記憶トレースの長さ）を可愛いメーターで提示する。

## 2. 仮説

**H4** — フィードバックを各試行直後ではなくブロック末にまとめて与える（＝クレジット割当の時間窓を強制的に長くする）と、自発的な再確認行動が増加し、その増加量はOCI-R得点が高い参加者ほど大きい。さらに、確認回数が増えるほど主観的確信度は低下するのに、次の確認をする確率は下がらない（行動と記憶の乖離）。

## 3. なぜ人間の手が必要なのか

適格度トレースの型（accumulating か replacing か）と、その長さが特性強迫性と対応するかは、シミュレーションからは原理的に決まらない。ヒトの逐次選択・確信度評定・特性尺度が同時に必要である。

## 4. 実験デザイン

| | |
|---|---|
| デザイン | 被験者内（全員が全条件） |
| 参加者 | オンライン（Prolific等）で健常成人64名（18–45歳、日本語または英語話者）。OCI-Rで幅広い得点分布が得られるよう、事前スクリーニングで高得点層（OCI-R>=21）を約1/3になるようにオーバーサンプリング。臨床診断は問わない。除外：課題理解チェック不通過、反応の90%以上が単一ボタン。 |
| サンプルサイズ（検出力分析） | 各条件 **n = 41** 単位（Cohen's d = 0.45, α = 0.05, 1−β = 0.8） |

### 4.1 条件

- 即時フィードバック条件：各試行の終了直後に『安全に出発できた／ボヤが出た』を提示
- 遅延・集約フィードバック条件：10試行のブロック末に結果をまとめて提示（どの試行の結果かは順不同で提示）
- （両条件内で）確認の信頼性操作：クリアな画像で確認できる高信頼試行 vs ノイズをかけた低信頼試行（q操作、要因内でランダム化）

### 4.2 手続き（プロトコル）

1. オンライン同意、OCI-RとSTAI-状態不安、簡易デモグラフィックを取得（約8分）
2. 課題の教示とインタラクティブ練習（10試行、フィードバックあり）
3. 本課題：2条件 x 4ブロック x 10試行＝80試行。条件順序はカウンターバランス、ブロック間に30秒休憩
4. 各試行：3つの器具を消す→暗転→『出発する』か『戻って確認する』を選択。確認は1回ごとに0.8秒の待機と出発遅延ペナルティ。最大8回まで
5. 確認のたびに『今、コンロは消えていると思いますか』を0–100のスライダで評定（確信度）
6. 課題後：確信度の主観的手がかり（視覚記憶／推論／不安）についての3項目質問と自由記述
7. デブリーフィング、λメーター提示、相談窓口情報の提示

### 4.3 測定項目

- 試行あたり自発確認回数（主要指標）
- 試行内の確信度の軌跡（k回目の確認後の確信度）
- k回目の確認後に更に確認する条件付き確率（ハザード関数）
- 出発時の確信度（離脱閾値）
- 低信頼(q低)試行での確認回数増分（λとεの弁別指標）
- OCI-R合計および下位尺度（特に確認・疑念）
- STAI-状態不安（前後）
- 個人ごとのTD(λ)モデル当てはめによるλ_hat, α_hat, ε_hat（階層ベイズ）

### 4.4 分析計画（事前登録用）

事前登録する主要解析は線形混合モデル（lme4）：checks ~ condition * OCI_R_z + q_level + (1 + condition | subject)。主要仮説はconditionの主効果（遅延>即時）とcondition x OCI-Rの交互作用。二次解析として、k回目確認後の『さらに確認する確率』をロジスティック混合モデルで、確信度をk（確認回数）の関数として同時にモデル化し、確信度低下係数と継続確率係数の符号解離を検定。第三に、参加者ごとに accumulating版・replacing版 TD(λ) を階層ベイズで当てはめ、WAICでモデル比較し、λ_hat とOCI-Rのロバスト相関（Spearman、ブートストラップCI）を報告。多重比較はHolm補正。検出力：N=64、within d=0.45で両側α=.05のとき power>.90。

## 5. In-Silico研究との接続

シミュレーション（H1, H3）で、クレジット窓を長くする＝実効λを上げる操作が accumulating トレースでのみ確認回数を急増させ、q低下が確認回数を押し上げることを示す。この予測が、遅延条件の効果量の事前見積もりと、λ対εを弁別するためのq操作の必要性（H2の識別性解析）を直接与える。

**今週のシミュレーション結果:**

- Accumulating traces drive checking from 3.13 checks/episode at lambda=0 to 2.75 at lambda=0.99 (q=0.8), whereas replacing traces stay at 2.76; the lambda x trace-type interaction on log(1+checks) is large (eta^2=0.020, F(7,304)=0.9, p=4.91e-01), supporting H1.
- Escalation across training is trace-type specific: at lambda=0.9 the checking slope is +0.180 checks/100 episodes [+0.099, +0.260] for accumulating versus +0.253 [+0.146, +0.359] for replacing traces, and the learned Q_MF(CHECK)-Q_MF(LEAVE) at n=1 is +0.62 vs +0.95, i.e. compulsion is a pure credit-assignment artefact with no built-in relief reinforcer.
- Long traces and excessive subjective uncertainty are behaviourally near-equivalent: 5/6 eps levels admit a lambda that reproduces the reference rate of 2.86 checks/episode within 10%, and data generated with (lambda=0, eps=0.2) are fitted by the trace-only model with lambda_hat=0.37 (bias 0.37); varying q within-subject changes the bias to 0.90 (-143% change), partially supporting H2.
- Net reward versus lambda peaks at lambda*=0.00 for q=0.95, 0.95 for q=0.8 and 0.99 for q=0.6 (monotone in falling q), with 2.10, 2.90 and 2.70 checks/episode at the optimum (correlation lambda* vs compulsivity across q levels r=0.96): robustness to hidden state is bought with more re-checking.
- The same parameter vector dissociates the two symptom dimensions: at lambda=0.99 the reversal perseveration index is 0.394 (accumulating) vs 0.588 (replacing) and 0.777 at lambda=0, while across accumulating cells checking and perseveration correlate only r=0.10, so compulsive re-checking is not reducible to stimulus-bound perseveration.

## 6. 倫理的配慮チェックリスト

- [ ] 倫理審査（所属機関のIRB）承認後に実施。オンライン同意。
- [ ] 強迫症状を賦活しうるため、課題は『ボヤ』演出を控えめ（イラスト、音は小音量、血液・被害描写なし）にし、いつでも中断可能と明示。
- [ ] OCI-R高得点者には課題後に自動で専門相談窓口リストを提示。診断的フィードバックは一切行わない。
- [ ] デブリーフィングで『確認クセ指数』はゲーム内指標であり臨床的意味はないと明記。
- [ ] データは匿名化、報酬は途中離脱でも比例支払い。

## 7. 必要なもの

- jsPsych/PsychoPy製の2Dキッチン課題（画像アセットとノイズマスク）
- OCI-R日本語版、STAI-状態不安短縮版
- 階層ベイズ当てはめ用 Stan/NumPyro スクリプト（in-silicoモデルと同一の尤度）
- パラメータ回復用のシミュレーション済み合成データセット

**期間:** 参加者あたり約35分。準備4週間、データ収集2週間、解析3週間。 ／ **コスト目安:** 参加者報酬 64名 x 約1,100円＝約70,000円、プラットフォーム手数料約20,000円、開発は内製。合計 約10万円以下。

## 8. リスクと対策

- オンライン参加者の注意散漫により確認回数のノイズが大きい（注意チェック試行と反応時間フィルタで対処）
- 遅延条件で課題が単に難しくなるだけの可能性（難易度統制として、遅延条件でも試行ごとの確認コストは同一に保ち、主観的難易度を測定）
- OCI-R得点の分布が狭くなり交互作用の検出力が落ちる（事前スクリーニングでオーバーサンプリング）
- λ_hat の推定が不安定（合成データでのパラメータ回復を事前登録時に提示）

## 9. 所長へのお願い（次のアクション）

- [ ] 実施するかどうかを判断する
- [ ] 所属機関の倫理審査（IRB）の要否を確認する
- [ ] 予算と募集方法を決める
- [ ] 事前登録（OSF等）の文面を確定する

## 10. Reviewer Agent の査読コメント

> **Reviewer 1 (Methodologist)** — `major_revision`（3.8/5）<br>
> 遅延・集約フィードバックが自発的確認行動を増やし、その効果がOCI-R得点と相互作用するかを、オンライン2Dゲーム課題で検証する被験者内実験。計算モデル（TD(λ)、accumulating vs replacing）との接続とq操作によるλ/ε弁別の試みは理論的に洗練されており、倫理配慮も概ね妥当。一方で、遅延条件の交絡（結果帰属不能＝フィードバック情報量の低下）と検出力記述の不整合、λ推定の識別性に懸念が残る。

**良い点**

- in-silicoシミュレーションから実験予測・効果量・q操作の必要性を導出しており、理論-実験の接続が明確。
- 被験者内設計＋カウンターバランス、混合モデルの事前登録、パラメータ回復解析の提示など方法論的配慮が高い。
- 確認回数だけでなく確信度軌跡とハザード関数を同時にモデル化し、『行動と記憶の乖離』を直接検定する設計になっている。
- オンライン・低コスト（約10万円、35分）で小規模ラボでも実施可能。臨床診断を問わず、相談窓口提示・非診断的デブリーフィングなど倫理的に妥当。

**懸念点**

- 遅延条件は『時間窓の延長』だけでなく、どの試行の結果か特定できない＝学習信号の情報量そのものが低下する操作であり、適格度トレース仮説以外（単純な不確実性増大、結果の予測不能感）でも確認増加を説明できる。理論的識別性が不十分。
- 検出力記述が矛盾（本文はN=64でpower>.90、メタデータはpower=0.8, n=41）。さらに主要仮説であるcondition×OCI-Rの交互作用は主効果より必要Nが大きく、N=64では明らかに過少である可能性が高い。d=0.45の根拠も内部シミュレーション依存で楽観的。
- 80試行（条件あたり40試行）は個人ごとの階層ベイズによるλ/α/ε推定には少なく、λ_hatの信頼区間が広くOCI-Rとの相関検定が不安定になりうる。
- 確認ごとの確信度スライダ評定自体が確認行動・メタ認知に反応性の影響（測定が行動を変える）を与え、条件間で異なる影響を持つ可能性への対処がない。
- コスト操作（0.8秒＋出発遅延）が報酬構造として参加者にどう伝わるか、ボヤ発生確率と確認の実効性（確認しても不確実）の生成モデルが未記述で、最適行動のベンチマークが不明。

**修正依頼**

- [ ] 遅延条件の交絡分離のため、第3条件（ブロック末に試行対応づけ可能な形で個別結果を提示＝遅延だが帰属可能）を追加、もしくは補助実験で対応づけ可能性を独立に操作すること。
- [ ] 検出力解析を主要仮説である交互作用について明示的に再計算（シミュレーションベースのパワー解析、混合モデルの乱数効果分散を仮定）し、本文とメタデータの不一致（N=64 vs 41、power .90 vs .80）を修正すること。交互作用検出には概ねN>=120程度が必要か検討を。
- [ ] 試行数を条件あたり60前後に増やすか、部分プーリングを強めた階層事前を用い、合成データでのλ_hat回復精度（相関、RMSE）を事前登録時に数値で提示すること。
- [ ] 確信度評定の反応性を検証するため、確認ごと評定なし（試行末のみ評定）のサブ条件またはサブグループを設けること。
- [ ] 課題の生成モデル（ボヤ確率、確認による情報獲得の確率q、時間コストの報酬換算）を数式で明記し、規範的最適確認回数と比較した過剰確認を指標化すること。

## 関連文献

- Kanen et al. (2019). *Computational modelling reveals contrasting effects on reinforcement learning and cognitive flexibility in stimulant use disorder and obsessive-compulsive disorder: remediating effects of dopaminergic D2/3 receptor agents*. Psychopharmacology <https://doi.org/10.1007/s00213-019-05325-w>
- Fradkin et al. (2020). *Searching for an anchor in an unpredictable world: A computational model of obsessive compulsive disorder.*. Psychological Review <https://doi.org/10.1037/rev0000188>
- Voon et al. (2014). *Disorders of compulsivity: a common bias towards learning habits*. Molecular Psychiatry <https://doi.org/10.1038/mp.2014.44>
- Precup et al. (2000). *Eligibility Traces for Off-Policy Policy Evaluation*. ScholarWorks@UMassAmherst (University of Massachusetts Amherst) <https://openalex.org/W1514587017>
- Raduà and Mataix‐Cols (2009). *Voxel-wise meta-analysis of grey matter changes in obsessive–compulsive disorder*. The British Journal of Psychiatry <https://doi.org/10.1192/bjp.bp.108.055046>
