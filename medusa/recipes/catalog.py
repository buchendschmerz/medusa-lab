"""The recipe catalogue (content). Foundational references are the canonical sources of each model."""

from __future__ import annotations

from ..models import LiteratureItem, ModelParameter
from . import HumanIdeaTemplate, HypothesisTemplate, Recipe


def T(ja: str, en: str) -> dict[str, str]:  # noqa: N802 - tiny DSL
    return {"ja": ja, "en": en}


def L(ja: list[str], en: list[str]) -> dict[str, list[str]]:  # noqa: N802
    return {"ja": ja, "en": en}


def ref(key: str, title: str, authors: list[str], year: int, venue: str, doi: str = "", url: str = "") -> LiteratureItem:
    return LiteratureItem(key=key, title=title, authors=authors, year=year, venue=venue, doi=doi,
                          url=url or (f"https://doi.org/{doi}" if doi else ""), source="foundational",
                          foundational=True)


# ---------------------------------------------------------------------------- hypothesis criteria
def _num(m: dict, key: str) -> float:
    value = m[key]
    if value is None:
        raise ValueError(key)
    return float(value)


def _between(value: float, lo: float, hi: float, slack: float) -> str:
    if lo <= value <= hi:
        return "supported"
    if lo - slack <= value <= hi + slack:
        return "partially supported"
    return "not supported"


def ng_scaling(m: dict) -> tuple[str, str]:
    a = _num(m, "alpha_complete")
    return _between(a, 1.3, 1.6, 0.25), f"fitted exponent {a:.2f} vs. the expected 1.3-1.6 (mean field: 1.5)"


def ng_topology(m: dict) -> tuple[str, str]:
    lower_memory = _num(m, "peak_exponent_small_world") < _num(m, "peak_exponent_complete")
    slower = _num(m, "t_per_agent_small_world_maxN") > _num(m, "t_per_agent_complete_maxN")
    verdict = "supported" if lower_memory and slower else ("partially supported" if lower_memory or slower else "not supported")
    return verdict, (f"peak-memory exponent {m['peak_exponent_small_world']} (small-world) vs {m['peak_exponent_complete']}"
                     f" (complete); time per agent {m['t_per_agent_small_world_maxN']} vs {m['t_per_agent_complete_maxN']}")


def bc_rule(m: dict) -> tuple[str, str]:
    err = _num(m, "mean_abs_error_vs_theory")
    verdict = "supported" if err < 0.75 else ("partially supported" if err < 1.5 else "not supported")
    return verdict, f"mean deviation from floor(1/(2 epsilon)) is {err:.2f} clusters"


def bc_consensus(m: dict) -> tuple[str, str]:
    eps = m.get("consensus_threshold_epsilon")
    if eps is None:
        return "not supported", "no epsilon in the sweep produced a single cluster"
    return "supported", f"a single cluster emerges from epsilon = {eps}"


def sir_threshold(m: dict) -> tuple[str, str]:
    t = m.get("threshold_beta_er")
    final = _num(m, "final_size_er_max_beta")
    if t is None:
        return "not supported", "no large outbreak in the sweep"
    return ("supported" if final > 0.5 else "partially supported"), f"outbreaks exceed 10% from beta = {t}; final size {final:.2f} at the largest beta"


def sir_heterogeneity(m: dict) -> tuple[str, str]:
    er, ba = m.get("threshold_beta_er"), m.get("threshold_beta_ba")
    if er is None or ba is None:
        return "inconclusive", "a threshold was not reached on both networks"
    verdict = "supported" if ba < er else ("partially supported" if ba == er else "not supported")
    return verdict, f"threshold beta {ba} (scale-free) vs {er} (random); theory {m.get('theory_beta_c_ba')} vs {m.get('theory_beta_c_er')}"


def ku_onset(m: dict) -> tuple[str, str]:
    onset, kc = m.get("onset_coupling_sim"), _num(m, "critical_coupling_theory")
    if onset is None:
        return "not supported", "no synchronisation observed in the sweep"
    verdict = _between(float(onset), kc - 0.4, kc + 0.4, 0.4)
    return verdict, f"onset at K = {onset} vs theoretical K_c = {kc:.2f}"


def ku_strong(m: dict) -> tuple[str, str]:
    r = _num(m, "r_at_max_K")
    return ("supported" if r > 0.9 else "partially supported" if r > 0.7 else "not supported"), f"r = {r:.2f} at the strongest coupling"


def pd_spatial(m: dict) -> tuple[str, str]:
    c = _num(m, "cooperation_at_min_b")
    return ("supported" if c > 0.5 else "partially supported" if c > 0.2 else "not supported"), f"{c:.0%} cooperators at the lowest temptation (well-mixed: 0%)"


def pd_collapse(m: dict) -> tuple[str, str]:
    collapse, chaos = m.get("collapse_b"), m.get("cooperation_chaotic_regime")
    ok_collapse = collapse is not None and float(collapse) >= 1.95
    ok_chaos = chaos is not None and 0.15 <= float(chaos) <= 0.5
    verdict = "supported" if ok_collapse and ok_chaos else ("partially supported" if ok_collapse or ok_chaos else "not supported")
    return verdict, f"collapse at b = {collapse}; cooperation {chaos} for 1.8 <= b <= 2.0"


def sch_mild(m: dict) -> tuple[str, str]:
    s = _num(m, "segregation_at_tau_0_3")
    return ("supported" if s > 0.7 else "partially supported" if s > 0.6 else "not supported"), f"like-neighbour share {s:.2f} at tau = 0.3 (random: 0.50)"


def sch_churn(m: dict) -> tuple[str, str]:
    tau = m.get("tau_persistent_dissatisfaction")
    if tau is None:
        return "not supported", "every threshold in the sweep settled"
    return ("supported" if float(tau) <= 0.8 else "partially supported"), f"more than 20% of agents stay unhappy from tau = {tau}"


def zipf_rule(m: dict) -> tuple[str, str]:
    err = _num(m, "mean_abs_error_z")
    return ("supported" if err < 0.15 else "partially supported" if err < 0.3 else "not supported"), f"mean |z - (1 - alpha)| = {err:.3f}"


def zipf_fit(m: dict) -> tuple[str, str]:
    r2 = _num(m, "mean_fit_r2")
    return ("supported" if r2 > 0.9 else "partially supported" if r2 > 0.8 else "not supported"), f"mean log-log R^2 = {r2:.3f}"


COMMON_ETHICS = L(
    ["インフォームド・コンセントを取得し、途中離脱の自由を保証する",
     "個人を特定できる情報は収集しない（匿名IDのみ）",
     "所属機関の研究倫理審査（IRB）の要否を事前に確認する"],
    ["Obtain informed consent and guarantee the right to withdraw at any time",
     "Collect no personally identifying information (anonymous IDs only)",
     "Check with your institution whether ethics (IRB) review is required"],
)

# ============================================================================ naming game
NAMING_GAME = Recipe(
    id="naming_game",
    title="Naming Game model of lexical convention formation",
    title_ja="ネーミングゲーム（語彙の慣習形成モデル）",
    field="computational linguistics / language evolution",
    keywords=("language", "linguist", "word", "vocabular", "lexic", "convention", "naming",
              "dialect", "slang", "neologism", "emoji", "communicat", "social norm",
              "言語", "言葉", "単語", "語彙", "新語", "造語", "方言", "流行語", "若者言葉", "慣習", "規範",
              "命名", "ネーミング", "合意", "コミュニケーション", "絵文字", "スラング", "ことば"),
    search_terms=("naming game language convergence", "emergence of linguistic conventions social network",
                  "semiotic dynamics shared vocabulary agents", "neologism diffusion social media"),
    summary="Agents negotiate names for an object through pairwise interactions until a shared convention emerges.",
    summary_ja="エージェント同士がペアで呼び名を交渉し、誰も決めていない共通語（慣習）が自然に生まれる過程のモデル。",
    background=("Shared vocabularies can emerge without central coordination, as first shown by agent-based "
                "language games \\citep{steels1995selforganizing}. The minimal Naming Game captures this "
                "self-organisation with a sharp transition towards consensus and a characteristic "
                "$N^{3/2}$ scaling of the convergence time in well-mixed populations "
                "\\citep{baronchelli2006sharp}. Contact topology strongly affects the dynamics "
                "\\citep{dallasta2006nonequilibrium}, and experiments with human groups confirm that "
                "conventions emerge spontaneously in networked populations \\citep{centola2015spontaneous}."),
    mechanism=("Each agent holds an inventory of candidate names. At every step a random speaker utters a name "
               "from its inventory (inventing a new one if empty) to a random neighbour. If the hearer already "
               "knows the name, the interaction succeeds and both agents discard all competing names; otherwise "
               "the hearer adds the name to its inventory."),
    equations=(r"N_w(t) = \sum_{i=1}^{N} |\mathcal{I}_i(t)|",
               r"t_{\mathrm{conv}} \sim N^{\alpha}, \quad \alpha_{\mathrm{MF}} = 3/2",
               r"N_w^{\max} \sim N^{\beta}, \quad \beta_{\mathrm{MF}} = 3/2"),
    assumptions=("Agents have unbounded memory and no preference among names.",
                 "Interactions are pairwise, random and sequential.",
                 "A single object (meaning) is being named; there is no homonymy."),
    parameters=(ModelParameter("population", "N", "number of agents", 256, [32, 64, 128, 256]),
                ModelParameter("sw_degree", "k", "degree of the small-world ring lattice", 6),
                ModelParameter("sw_rewire", "p", "Watts-Strogatz rewiring probability", 0.1)),
    observables=("convergence time t_conv (interactions until global consensus)",
                 "peak number of words N_w^max stored in the population",
                 "communicative success rate S(t)"),
    hypotheses=(
        HypothesisTemplate(
            statement="In a well-mixed population the time to lexical consensus grows super-linearly with "
                      "population size, with an exponent close to the mean-field value 3/2.",
            rationale="Every agent must first accumulate and then prune competing names; the pruning phase "
                      "slows down as the population grows.",
            predictions=("log t_conv is linear in log N with slope between 1.3 and 1.6",
                         "all runs reach consensus"),
            independent_variable="population size N", dependent_variable="convergence time t_conv", evaluate=ng_scaling),
        HypothesisTemplate(
            statement="Local small-world contact structure lowers the peak lexical memory but slows the final "
                      "agreement compared with a well-mixed population.",
            rationale="Local interactions create competing domains that coarsen slowly, while each agent only "
                      "meets a few names.",
            predictions=("peak memory per agent is lower on the small-world network",
                         "convergence time per agent is higher on the small-world network"),
            independent_variable="network topology", dependent_variable="convergence time and peak memory", evaluate=ng_topology),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("オンライン・ネーミングゲーム実験：つながり方で「新語の合意」は速くなるか",
                "Online naming-game experiment: does network structure speed up agreement on new words?"),
        hypothesis=T("誰とでも話せる集団（完全混合）は、近所としか話さない集団（スモールワールド）より早く呼び名の合意に達する。",
                     "Groups in which everyone can talk to everyone reach a shared name faster than groups "
                     "restricted to local small-world contacts."),
        why_human=T("モデルのエージェントは記憶も好みも持たない。実際の人間は覚えやすさ・面白さ・評判で語を選ぶため、"
                    "予測が人間集団でも成り立つかは人間で確かめるしかない。",
                    "Model agents have no memory limits or taste. People pick words for memorability, humour and "
                    "reputation, so only human groups can test whether the prediction holds."),
        fun_factor=T("見知らぬ図形に名前を付け合うだけで、数分後には誰も決めていない「共通語」が生まれる瞬間を目撃できる。"
                     "新語・流行語の誕生を実験室で再現！",
                     "Watch a shared word appear out of nothing within minutes — the birth of slang, in the lab."),
        design_type="between",
        participants=T("オンライン参加者を12人1グループに編成（グループ単位で分析）",
                       "Online participants in groups of 12 (the group is the unit of analysis)"),
        conditions=L(["完全混合：毎ラウンド相手をランダムに割り当て", "スモールワールド：固定の近傍（次数4）＋10%の遠距離リンク"],
                     ["Well-mixed: random partner every round", "Small-world: fixed neighbours (degree 4) plus 10% long-range links"]),
        procedure=L(["同意取得と練習ラウンド（約2分）",
                     "抽象図形を1枚提示し、ペアで同時に名前を入力（最大25ラウンド）",
                     "一致したら両者に得点、不一致なら相手の語を表示",
                     "終了後、選んだ語の理由を自由記述で回答"],
                    ["Consent and a practice round (about 2 minutes)",
                     "Show one abstract shape; pairs type a name simultaneously (up to 25 rounds)",
                     "Matching names earn points; otherwise the partner's word is revealed",
                     "Free-text question on why the chosen word was used"]),
        measures=L(["合意に至るまでのラウンド数（主要指標）", "各時点でのグループ内の語彙数", "一致率の推移"],
                   ["Rounds until group consensus (primary outcome)", "Number of distinct words over time",
                    "Success rate over rounds"]),
        analysis_plan=T("グループ単位で合意到達ラウンドを条件間比較（Welchのt検定、両側α=0.05）。補助的に生存時間分析。"
                        "主要指標・除外基準（途中離脱者のいるグループは除外）を事前登録する。",
                        "Compare rounds-to-consensus between conditions at the group level (Welch t-test, two-sided "
                        "alpha = 0.05), with survival analysis as a secondary analysis. Pre-register the outcome and "
                        "exclusion rules (groups with drop-outs are excluded)."),
        effect_size_d=1.2,
        ethics=COMMON_ETHICS,
        materials=L(["オンライン実験基盤（oTree など）", "著作権フリーの抽象図形セット", "参加者募集サービス"],
                    ["An online experiment platform (e.g. oTree)", "Copyright-free abstract shapes",
                     "A participant recruitment service"]),
        duration=T("準備2週間・実施1週間・分析1週間", "2 weeks preparation, 1 week data collection, 1 week analysis"),
        cost=T("1人あたり約300円（15分）", "about USD 2-3 per participant (15 minutes)"),
        risks=L(["途中離脱でグループが崩れる → 待機要員を確保", "既存の単語の流用 → 抽象図形で統制"],
                ["Drop-outs break groups -> recruit stand-by participants", "Re-use of existing words -> abstract stimuli"]),
        link=T("今週のシミュレーションでは、完全混合での合意時間がスモールワールドより大幅に短いと予測された。"
               "グループ規模と条件はこの予測を直接検証できるよう設計した。",
               "This week's simulation predicts much faster consensus in well-mixed groups than on small-world "
               "networks; group size and conditions are chosen to test exactly this."),
    ),),
    references=(
        ref("steels1995selforganizing", "A self-organizing spatial vocabulary", ["Luc Steels"], 1995,
            "Artificial Life 2(3):319-332"),
        ref("baronchelli2006sharp", "Sharp transition towards shared vocabularies in multi-agent systems",
            ["Andrea Baronchelli", "Maddalena Felici", "Vittorio Loreto", "Emanuele Caglioti", "Luc Steels"],
            2006, "Journal of Statistical Mechanics: Theory and Experiment, P06014",
            doi="10.1088/1742-5468/2006/06/P06014"),
        ref("dallasta2006nonequilibrium", "Nonequilibrium dynamics of language games on complex networks",
            ["Luca Dall'Asta", "Andrea Baronchelli", "Alain Barrat", "Vittorio Loreto"], 2006,
            "Physical Review E 74, 036105"),
        ref("centola2015spontaneous",
            "The spontaneous emergence of conventions: An experimental study of cultural evolution",
            ["Damon Centola", "Andrea Baronchelli"], 2015, "PNAS 112(7):1989-1994",
            doi="10.1073/pnas.1418838112"),
    ),
    open_problems=("How does the structure of real (online) social networks change how fast new words become "
                   "conventions?",
                   "Do human groups follow the N^{3/2} consensus-time scaling predicted for well-mixed naming games?",
                   "How much lexical memory do speakers need during the negotiation phase?"),
    discussion=("The scaling exponent quantifies how costly it is for larger communities to agree on a convention.",
                "Sparse local contacts trade memory load against speed: agents juggle fewer names but "
                "competing local conventions survive longer.",
                "Online platforms that reshuffle contacts behave more like well-mixed populations, which predicts "
                "faster adoption of neologisms."),
    limitations=("The minimal Naming Game ignores meaning, memory decay and prestige-biased imitation.",
                 "Population sizes are small; asymptotic exponents may differ from the fitted finite-size values.",
                 "A single topology per class (complete graph, one small-world ensemble) was studied."),
    script="naming_game.py",
    sweep_key="sizes",
    headline=T("集団が大きくなるほど、共通語ができるまでの時間は人数の増え方以上に長くなる", "consensus takes disproportionately longer as the group grows"),
    sweep_parameter="population",
    params={"sizes": [32, 64, 128, 256], "replicates": 5},
    quick_params={"sizes": [16, 32, 64], "replicates": 3},
)

# ============================================================================ bounded confidence
BOUNDED_CONFIDENCE = Recipe(
    id="bounded_confidence",
    title="Deffuant-Weisbuch bounded-confidence model of opinion dynamics",
    title_ja="有限信頼（バウンデッド・コンフィデンス）意見力学モデル",
    field="computational social science / opinion dynamics",
    keywords=("opinion", "polariz", "polaris", "echo chamber", "filter bubble", "consensus", "belief",
              "attitude", "politic", "election", "debate", "persua", "toleran",
              "意見", "世論", "分断", "二極化", "分極化", "エコーチェンバー", "フィルターバブル", "合意形成",
              "信念", "態度", "政治", "選挙", "議論", "説得", "寛容"),
    search_terms=("bounded confidence opinion dynamics", "opinion polarization agent-based model",
                  "echo chambers social media opinion dynamics", "Deffuant model clusters"),
    summary="Agents only listen to opinions within a confidence bound and move towards them; tolerance controls "
            "whether a population reaches consensus or splits into factions.",
    summary_ja="自分と近い意見だけに耳を傾けて歩み寄るエージェント集団。許容範囲の広さで合意か分断かが決まる。",
    background=("Bounded-confidence models formalise the idea that people are only influenced by opinions "
                "reasonably close to their own \\citep{deffuant2000mixing,hegselmann2002opinion}. They are a "
                "cornerstone of the statistical physics of social dynamics \\citep{castellano2009statistical} and "
                "echo classic findings on latitudes of acceptance in social judgement "
                "\\citep{sherif1961social}."),
    mechanism=("Opinions are real numbers in [0, 1]. At each step two random agents meet; if their opinions differ "
               "by less than the confidence bound epsilon, both move towards each other by a fraction mu of the "
               "difference. Otherwise nothing happens."),
    equations=(r"x_i \leftarrow x_i + \mu (x_j - x_i), \quad x_j \leftarrow x_j + \mu (x_i - x_j) \quad \text{if } |x_i - x_j| < \varepsilon",
               r"n_{\text{clusters}} \approx \left\lfloor \frac{1}{2\varepsilon} \right\rfloor"),
    assumptions=("Opinions are continuous and one-dimensional.", "Interactions are random pairwise encounters.",
                 "The confidence bound is the same for every agent."),
    parameters=(ModelParameter("epsilon", "\\varepsilon", "confidence bound (tolerance)", 0.2,
                               [0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]),
                ModelParameter("mu", "\\mu", "convergence parameter", 0.5),
                ModelParameter("agents", "N", "number of agents", 400)),
    observables=("number of major opinion clusters", "share of agents in the largest cluster"),
    hypotheses=(
        HypothesisTemplate(
            statement="The number of surviving opinion clusters decreases with the confidence bound, following "
                      "the rule of thumb floor(1/(2 epsilon)).",
            rationale="Agents further apart than epsilon never interact, so the opinion space fragments into "
                      "regions of width about 2 epsilon.",
            predictions=("cluster count close to 1/(2 epsilon) for small epsilon", "a single cluster for large epsilon"),
            independent_variable="confidence bound epsilon", dependent_variable="number of opinion clusters", evaluate=bc_rule),
        HypothesisTemplate(
            statement="There is a critical tolerance above which the population reaches consensus.",
            rationale="Once the interval of mutual influence spans the whole opinion space, no stable factions remain.",
            predictions=("the largest cluster contains almost everyone above the threshold",),
            independent_variable="confidence bound epsilon", dependent_variable="share of the largest cluster", evaluate=bc_consensus),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("意見の「許容範囲 ε」を測る：メッセージの距離と態度変化",
                "Measuring the human confidence bound: message distance and attitude change"),
        hypothesis=T("自分の意見から離れすぎたメッセージほど態度変化は小さくなる（有限の許容範囲 ε が存在する）。",
                     "Messages too far from one's own view change attitudes less: people have a finite confidence bound."),
        why_human=T("モデルの ε は仮定値にすぎない。人間の許容範囲の大きさと形（急なしきい値か、なだらかか）はデータでしか測れない。",
                    "Epsilon is an assumption in the model; the size and shape of the human acceptance region "
                    "can only be measured."),
        fun_factor=T("「どれだけ違う意見なら聞く耳を持てるか」を数値化。自分の ε を知るとSNSの見え方が変わるかも。",
                     "Put a number on how different an opinion can be before you stop listening."),
        design_type="within",
        participants=T("一般成人のオンライン参加者（個人単位）", "Adult online participants (individual level)"),
        conditions=L(["メッセージ距離：事前意見から ±1・±2・±3・±4 段階（7件法上）", "話題：身近な論点2つ（例：在宅勤務、キャッシュレス）"],
                     ["Message distance: 1-4 scale points away from the participant's prior view (7-point scale)",
                      "Two everyday topics (e.g. remote work, cashless payment)"]),
        procedure=L(["事前態度を7件法で測定", "距離を操作した短い意見文をランダム順に読む", "直後に態度を再測定",
                     "最後に意見文の説得力を評価し、事後説明を受ける"],
                    ["Measure prior attitudes (7-point scale)", "Read short opinion texts at manipulated distances in random order",
                     "Re-measure attitudes immediately", "Rate persuasiveness; debriefing"]),
        measures=L(["態度変化量（メッセージ方向を正に符号化）", "意見文の受容度・説得力評価", "事前態度の確信度"],
                   ["Attitude change towards the message (primary)", "Acceptance and persuasiveness ratings",
                    "Confidence in the prior attitude"]),
        analysis_plan=T("混合効果モデル（参加者ランダム切片）で態度変化〜距離を推定し、変化が0になる距離を ε の推定値とする。"
                        "主要検定：距離1と距離4の対応のあるt検定（α=0.05）。",
                        "Mixed-effects model (random intercepts per participant) of attitude change on distance; "
                        "the distance where change reaches zero estimates epsilon. Primary test: paired t-test of "
                        "distance 1 vs 4 (alpha = 0.05)."),
        effect_size_d=0.5,
        ethics=L(["政治的に過度に敏感でない話題を選ぶ", "事後説明で意見文が作成物であることを伝える",
                  "同意取得・匿名化・倫理審査の確認"],
                 ["Avoid highly sensitive political topics", "Debrief that the texts were constructed",
                  "Consent, anonymisation and ethics review"]),
        materials=L(["オンライン調査ツール", "距離を事前評定で較正した意見文セット"],
                    ["An online survey tool", "A calibrated set of opinion texts"]),
        duration=T("準備2週間・実施1週間", "2 weeks preparation, 1 week data collection"),
        cost=T("1人あたり約200円（10分）", "about USD 1.5 per participant (10 minutes)"),
        risks=L(["極端な意見の人の天井効果 → 事前態度で層別", "要求特性 → カバーストーリーを用いる"],
                ["Ceiling effects for extreme views -> stratify by prior attitude", "Demand characteristics -> cover story"]),
        link=T("シミュレーションでは ε が一定値を下回ると意見が複数の派閥に分裂した。実験で推定した人間の ε をモデルに代入すれば、"
               "どの程度の分断が起こりうるかを予測できる。",
               "The simulation shows fragmentation below a critical epsilon; plugging the measured human epsilon "
               "into the model predicts how much polarisation to expect."),
    ),),
    references=(
        ref("deffuant2000mixing", "Mixing beliefs among interacting agents",
            ["Guillaume Deffuant", "David Neau", "Frederic Amblard", "Gerard Weisbuch"], 2000,
            "Advances in Complex Systems 3:87-98"),
        ref("hegselmann2002opinion", "Opinion dynamics and bounded confidence: models, analysis and simulation",
            ["Rainer Hegselmann", "Ulrich Krause"], 2002, "Journal of Artificial Societies and Social Simulation 5(3)",
            url="https://www.jasss.org/5/3/2.html"),
        ref("castellano2009statistical", "Statistical physics of social dynamics",
            ["Claudio Castellano", "Santo Fortunato", "Vittorio Loreto"], 2009, "Reviews of Modern Physics 81:591-646",
            doi="10.1103/RevModPhys.81.591"),
        ref("sherif1961social", "Social Judgment: Assimilation and Contrast Effects in Communication and Attitude Change",
            ["Muzafer Sherif", "Carl I. Hovland"], 1961, "Yale University Press"),
    ),
    open_problems=("How large is the human confidence bound, and does it differ across topics?",
                   "Do recommender systems that narrow exposure act like a smaller effective confidence bound?",
                   "Which interventions merge opinion clusters once they have formed?"),
    discussion=("Tolerance acts as a control parameter: small changes near the critical value switch the "
                "population between consensus and fragmentation.",
                "Minor clusters of 'extremists' can persist even when most agents agree.",
                "Platform design that limits cross-cutting exposure effectively reduces epsilon."),
    limitations=("Opinions are one-dimensional and all agents share the same epsilon.",
                 "No stubborn agents, media sources or network structure were modelled.",
                 "Cluster counts depend on the minimum-size threshold used to ignore tiny groups."),
    script="bounded_confidence.py",
    sweep_key="epsilons",
    headline=T("意見の許容範囲が少し狭まるだけで、集団は複数の派閥に分裂する", "a small drop in tolerance splits the population into several factions"),
    sweep_parameter="epsilon",
    params={"replicates": 5},
    quick_params={"agents": 150, "steps_per_agent": 120, "replicates": 3,
                  "epsilons": [0.05, 0.1, 0.15, 0.25, 0.35, 0.5]},
)

# ============================================================================ SIR on networks
SIR_NETWORK = Recipe(
    id="sir_network",
    title="SIR contagion on random and scale-free networks",
    title_ja="ネットワーク上のSIR伝播モデル（情報・感染の拡散）",
    field="network science / social contagion",
    keywords=("epidemi", "disease", "infect", "virus", "spread", "diffusion", "contagi", "rumor", "rumour",
              "viral", "misinformation", "fake news", "cascade", "adoption", "word of mouth",
              "感染", "伝染", "疫学", "ウイルス", "拡散", "普及", "伝播", "噂", "デマ", "口コミ", "バズ",
              "情報拡散", "フェイクニュース", "流行"),
    search_terms=("SIR model complex networks epidemic threshold", "information diffusion social network contagion",
                  "rumor spreading model networks", "epidemic spreading scale-free networks"),
    summary="Items (diseases, rumours, innovations) spread along contacts and die out; network heterogeneity "
            "controls the epidemic threshold.",
    summary_ja="人から人へ伝わっては収束する「拡散」のモデル。つながり方の偏りが大流行のしきい値を左右する。",
    background=("Compartmental SIR models date back to \\citet{kermack1927contribution}. On networks the "
                "epidemic threshold depends on the degree distribution \\citep{newman2002spread}, and in "
                "scale-free networks \\citep{barabasi1999emergence} it can become vanishingly small "
                "\\citep{pastorsatorras2001epidemic}. The same framework is widely used for rumours and "
                "information cascades."),
    mechanism=("Nodes are susceptible (S), infected/spreading (I) or recovered (R). In each discrete step, every "
               "infected node transmits to each susceptible neighbour with probability beta and then recovers "
               "with probability gamma. We compare an Erdos-Renyi random graph with a Barabasi-Albert "
               "scale-free graph of the same mean degree."),
    equations=(r"P(S_j \to I_j) = 1 - (1-\beta)^{m_j(t)}",
               r"T = \frac{\beta}{\beta + \gamma - \beta\gamma}, \qquad T_c = \frac{\langle k \rangle}{\langle k^2 \rangle - \langle k \rangle}"),
    assumptions=("Transmission and recovery probabilities are homogeneous.", "The contact network is static.",
                 "Recovered nodes are permanently immune (or have lost interest)."),
    parameters=(ModelParameter("beta", "\\beta", "transmission probability per contact and step", 0.05,
                               [0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.1, 0.13, 0.16, 0.2]),
                ModelParameter("gamma", "\\gamma", "recovery probability per step", 0.2),
                ModelParameter("mean_degree", "\\langle k\\rangle", "mean degree", 6),
                ModelParameter("nodes", "N", "number of nodes", 1000)),
    observables=("final outbreak size", "peak prevalence", "epidemic threshold"),
    hypotheses=(
        HypothesisTemplate(
            statement="Outbreak size shows a threshold in the transmission probability: below it contagion stays "
                      "local, above it a finite share of the population is reached.",
            rationale="Each spreader must on average create more than one new spreader for global cascades.",
            predictions=("final size near zero for small beta", "sharp rise above the threshold"),
            independent_variable="transmission probability beta", dependent_variable="final outbreak size", evaluate=sir_threshold),
        HypothesisTemplate(
            statement="Scale-free contact networks have a lower epidemic threshold than random networks with the "
                      "same mean degree.",
            rationale="Hubs with many contacts amplify transmission, raising <k^2>/<k>.",
            predictions=("the scale-free outbreak exceeds 10% at smaller beta than the random network",),
            independent_variable="network heterogeneity", dependent_variable="epidemic threshold", evaluate=sir_heterogeneity),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("噂はどこまで届く？ 無害なメッセージの転送チェーン実験",
                "How far does a message travel? A forwarding-chain experiment with harmless content"),
        hypothesis=T("転送のしやすさ（β）が一定値を超えると、メッセージの到達範囲が急激に広がる（しきい値現象）。",
                     "Above a critical forwarding probability the reach of a message rises sharply."),
        why_human=T("現実の人は内容・相手・タイミングで転送を判断する。モデルの一定の β がどれほど妥当かは、実際の転送行動を測らなければ分からない。",
                    "Real people decide to forward based on content, audience and timing; only observed behaviour "
                    "can tell whether a constant beta is a good approximation."),
        fun_factor=T("「バズる／バズらない」の境目を自分たちの手で観測できる。",
                     "Observe the tipping point between a message that fizzles and one that goes viral."),
        design_type="between",
        participants=T("研究室・大学の協力者ネットワーク（初期拡散者＝シード単位）",
                       "Volunteers in a lab/campus network (the seed spreader is the unit)"),
        conditions=L(["高シェア性メッセージ（ユーモア・有用性あり）", "低シェア性メッセージ（中立的なお知らせ）"],
                     ["High-shareability message (useful, humorous)", "Low-shareability message (neutral notice)"]),
        procedure=L(["各条件でシード（初期拡散者）をランダムに選ぶ", "追跡用リンク付きの無害なメッセージを送り、転送は任意と伝える",
                     "7日間、クリックと転送を匿名IDで記録", "最後に転送した／しなかった理由を尋ねる"],
                    ["Randomly pick seed spreaders per condition", "Send a harmless message with a tracking link; forwarding is optional",
                     "Log clicks and forwards with anonymous IDs for 7 days", "Ask why people did or did not forward"]),
        measures=L(["到達人数（最終規模、主要指標）", "受信者ごとの転送確率＝β の推定", "拡散の世代数・速度"],
                   ["Final reach (primary)", "Per-recipient forwarding probability (estimate of beta)",
                    "Number of generations and speed"]),
        analysis_plan=T("条件間で最終到達規模を比較（Mann–WhitneyのU検定）。転送をロジスティック回帰でモデル化して β を推定し、"
                        "ネットワーク上のSIRモデルの予測と比較する。",
                        "Compare final reach between conditions (Mann-Whitney U). Estimate beta with a logistic "
                        "model of forwarding and compare with the network SIR prediction."),
        effect_size_d=0.6,
        ethics=L(["内容は無害で事実に基づくものに限る（デマを流さない）", "追跡は匿名IDのみ・個人情報は取得しない",
                  "受信者は事前同意していないため、倫理審査を必ず受ける", "目的の掲示とオプトアウト手段を用意する"],
                 ["Harmless, factual content only (never spread misinformation)", "Anonymous IDs only",
                  "Recipients have not consented in advance: formal ethics review is mandatory",
                  "Publish the study purpose and offer an opt-out"]),
        materials=L(["リンク追跡ツール（匿名化設定）", "メッセージ文面2種（事前評定済み）"],
                    ["A privacy-preserving link tracker", "Two pre-rated message texts"]),
        duration=T("準備3週間（倫理審査含む）・実施1週間", "3 weeks preparation (incl. ethics review), 1 week field phase"),
        cost=T("ほぼ無料（ツール利用料のみ）", "nearly free (tool fees only)"),
        risks=L(["受信者のプライバシー懸念 → 匿名化と即時オプトアウト", "拡散が研究外に広がる → 有効期限付きリンク"],
                ["Privacy concerns -> anonymisation and instant opt-out", "Spread beyond the study -> expiring links"]),
        link=T("シミュレーションでは、スケールフリー型のつながりではランダム型より低い転送確率で大規模拡散が起きた。"
               "実測した転送確率を代入し、現実の人間関係がしきい値の上か下かを判定する。",
               "The simulation shows large cascades at lower beta on scale-free networks; the measured forwarding "
               "probability tells whether real contact networks are above or below the threshold."),
    ),),
    references=(
        ref("kermack1927contribution", "A contribution to the mathematical theory of epidemics",
            ["William O. Kermack", "Anderson G. McKendrick"], 1927, "Proceedings of the Royal Society A 115:700-721",
            doi="10.1098/rspa.1927.0118"),
        ref("pastorsatorras2001epidemic", "Epidemic spreading in scale-free networks",
            ["Romualdo Pastor-Satorras", "Alessandro Vespignani"], 2001, "Physical Review Letters 86:3200-3203",
            doi="10.1103/PhysRevLett.86.3200"),
        ref("newman2002spread", "Spread of epidemic disease on networks", ["Mark E. J. Newman"], 2002,
            "Physical Review E 66, 016128", doi="10.1103/PhysRevE.66.016128"),
        ref("barabasi1999emergence", "Emergence of scaling in random networks",
            ["Albert-Laszlo Barabasi", "Reka Albert"], 1999, "Science 286:509-512", doi="10.1126/science.286.5439.509"),
    ),
    open_problems=("What is the effective transmission probability of everyday information in real social networks?",
                   "How do hubs (influencers) change the threshold for information cascades?",
                   "Which targeted interventions most efficiently stop harmful cascades?"),
    discussion=("Heterogeneous contact patterns make large cascades possible at low per-contact transmission.",
                "Near the threshold outbreak sizes are highly variable, so single observations are poor predictors.",
                "Interventions targeting hubs are disproportionately effective on scale-free networks."),
    limitations=("Transmission is memoryless and homogeneous; real sharing decisions are content-dependent.",
                 "Networks are synthetic and static.", "Finite size smooths the theoretical threshold."),
    script="sir_network.py",
    sweep_key="betas",
    headline=T("ハブ（人気者）がいるネットワークでは、低い転送確率でも大規模な拡散が起こる", "networks with hubs allow large cascades even at low sharing probability"),
    sweep_parameter="beta",
    params={"replicates": 12},
    quick_params={"nodes": 400, "replicates": 6, "betas": [0.01, 0.03, 0.05, 0.08, 0.13, 0.2]},
)

# ============================================================================ Kuramoto
KURAMOTO = Recipe(
    id="kuramoto",
    title="Kuramoto model of collective synchronisation",
    title_ja="蔵本モデル（集団同期）",
    field="nonlinear dynamics / collective behaviour",
    keywords=("synchron", "rhythm", "oscillat", "clap", "applause", "circadian", "firefl",
              "music", "beat", "danc", "heartbeat", "neural oscillation", "coordinat",
              "同期", "同調", "リズム", "拍手", "手拍子", "概日", "体内時計", "ホタル", "音楽", "ダンス",
              "振動子", "脳波", "心拍", "足並み", "一体感"),
    search_terms=("Kuramoto model synchronization transition", "collective synchronization human groups",
                  "coupled oscillators applause synchronization", "interpersonal synchrony coupling"),
    summary="Oscillators with different natural frequencies synchronise once coupling exceeds a critical value.",
    summary_ja="固有のリズムを持つ振動子が互いに影響し合い、結合が臨界値を超えると一斉に同期する現象のモデル。",
    background=("The Kuramoto model is the paradigmatic description of spontaneous synchronisation "
                "\\citep{kuramoto1984chemical,strogatz2000kuramoto,acebron2005kuramoto}. Its phase transition "
                "has been linked to phenomena ranging from flashing fireflies to the rhythmic applause of "
                "concert audiences \\citep{neda2000sound}."),
    mechanism=("Each oscillator has a phase theta_i and a natural frequency omega_i drawn from a Gaussian. All "
               "oscillators feel the mean field of the population with strength K. The order parameter r "
               "measures the degree of synchrony (0 incoherent, 1 perfect synchrony)."),
    equations=(r"\frac{d\theta_i}{dt} = \omega_i + K r \sin(\psi - \theta_i)",
               r"r e^{i\psi} = \frac{1}{N} \sum_{j=1}^{N} e^{i\theta_j}",
               r"K_c = \frac{2}{\pi g(0)} = \sigma \sqrt{8/\pi}"),
    assumptions=("All-to-all (mean-field) coupling.", "Gaussian distribution of natural frequencies.",
                 "No noise or delays."),
    parameters=(ModelParameter("coupling", "K", "coupling strength", 2.0,
                               [0.0, 0.4, 0.8, 1.2, 1.4, 1.6, 1.8, 2.0, 2.4, 2.8, 3.2, 4.0]),
                ModelParameter("sigma", "\\sigma", "spread of natural frequencies", 1.0),
                ModelParameter("oscillators", "N", "number of oscillators", 150)),
    observables=("time-averaged order parameter r", "onset coupling of synchrony"),
    hypotheses=(
        HypothesisTemplate(
            statement="Synchrony emerges abruptly once the coupling strength exceeds the critical value "
                      "K_c = sigma * sqrt(8/pi).",
            rationale="Below K_c the mean field is too weak to entrain oscillators with different frequencies.",
            predictions=("r stays near the 1/sqrt(N) noise floor for K < K_c", "r rises steeply above K_c"),
            independent_variable="coupling strength K", dependent_variable="order parameter r", evaluate=ku_onset),
        HypothesisTemplate(
            statement="Above the transition the degree of synchrony keeps increasing with coupling and approaches "
                      "the mean-field curve sqrt(1 - K_c/K).",
            rationale="Stronger coupling recruits oscillators with more extreme natural frequencies.",
            predictions=("r exceeds 0.9 at K = 4",),
            independent_variable="coupling strength K", dependent_variable="order parameter r", evaluate=ku_strong),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("みんなで手拍子：他者の音の聞こえ方で「同期の相転移」は起こるか",
                "Group clapping: does hearing others trigger a synchronisation transition?"),
        hypothesis=T("他者の手拍子がよく聞こえる（結合 K が強い）ほど、ある臨界値で集団の手拍子が急に揃う。",
                     "As others' clapping becomes more audible (stronger coupling K), group clapping synchronises "
                     "abruptly at a critical level."),
        why_human=T("人間はテンポを予測・修正する複雑な運動制御を持つ。単純な位相振動子モデルが人間集団を説明できるかは実測が必要。",
                    "Humans predict and correct tempo with complex motor control; whether a phase-oscillator model "
                    "describes a human group requires measurement."),
        fun_factor=T("コンサートの拍手が自然に揃うあの瞬間を実験室で再現。スマホのマイクでも相転移が測れる。",
                     "Recreate the moment a concert hall starts clapping in unison — measurable with phone microphones."),
        design_type="within",
        participants=T("8人1グループ（グループ単位で分析）", "Groups of 8 (group is the unit of analysis)"),
        conditions=L(["ヘッドホンで聞こえる他者の手拍子音量：0%・25%・50%・75%・100%", "テンポの指示なしで開始"],
                     ["Audibility of the others' clapping via headphones: 0, 25, 50, 75, 100%", "No tempo instruction"]),
        procedure=L(["各参加者の単独での手拍子テンポを測定（固有振動数の推定）", "音量条件をランダム順で各60秒実施",
                     "各条件の後に「揃っていた感」を評定"],
                    ["Record each participant's solo clapping tempo (natural frequency)",
                     "Run each audibility condition for 60 s in random order", "Rate the felt togetherness after each"]),
        measures=L(["秩序パラメータ r（手拍子の位相の揃い具合、主要指標）", "テンポのばらつき", "主観的な一体感"],
                   ["Order parameter r of clap phases (primary)", "Tempo dispersion", "Felt togetherness"]),
        analysis_plan=T("r を目的変数とする混合効果モデル。音量に対してロジスティック曲線を当てはめ臨界値を推定。"
                        "主要検定：0% と 100% の対応のあるt検定（α=0.05）。",
                        "Mixed-effects model of r; fit a logistic curve over audibility to locate the transition. "
                        "Primary test: paired t-test 0% vs 100% (alpha = 0.05)."),
        effect_size_d=1.0,
        ethics=L(["聴覚に負担のない音量上限を設定する", "同意取得・匿名化", "録音データは解析後に削除"],
                 ["Cap the headphone volume", "Consent and anonymisation", "Delete raw audio after analysis"]),
        materials=L(["ヘッドホン×8とミキサー（またはオンライン会議の音声ルーティング）", "録音用マイク", "位相解析スクリプト（Python）"],
                    ["8 headphones and a mixer (or routed conference audio)", "Microphones", "A phase-analysis script (Python)"]),
        duration=T("準備1週間・実施1週間", "1 week preparation, 1 week sessions"),
        cost=T("1人あたり約500円（30分）＋機材", "about USD 4 per participant (30 minutes) plus equipment"),
        risks=L(["リズム感の個人差が大きい → 単独テンポで統制", "音響遅延 → 有線接続を使用"],
                ["Large individual differences -> control for solo tempo", "Audio latency -> wired setup"]),
        link=T("シミュレーションでは結合 K が臨界値 K_c≈1.6σ を超えると r が急上昇した。単独テンポのばらつき σ を測れば、"
               "人間集団の臨界結合をモデルから予測して実測と比べられる。",
               "The simulation places the transition at K_c = 1.6 sigma; measuring the spread of solo tempi "
               "predicts where a human group should lock in."),
    ),),
    references=(
        ref("kuramoto1984chemical", "Chemical Oscillations, Waves, and Turbulence", ["Yoshiki Kuramoto"], 1984,
            "Springer"),
        ref("strogatz2000kuramoto",
            "From Kuramoto to Crawford: exploring the onset of synchronization in populations of coupled oscillators",
            ["Steven H. Strogatz"], 2000, "Physica D 143:1-20"),
        ref("acebron2005kuramoto", "The Kuramoto model: A simple paradigm for synchronization phenomena",
            ["Juan A. Acebron", "Luis L. Bonilla", "Conrad J. Perez Vicente", "Felix Ritort", "Renato Spigler"],
            2005, "Reviews of Modern Physics 77:137-185", doi="10.1103/RevModPhys.77.137"),
        ref("neda2000sound", "The sound of many hands clapping",
            ["Zoltan Neda", "Erzsebet Ravasz", "Yves Brechet", "Tamas Vicsek", "Albert-Laszlo Barabasi"], 2000,
            "Nature 403:849-850"),
    ),
    open_problems=("Do human groups show a genuine synchronisation phase transition as coupling increases?",
                   "How do delays and noise in human perception shift the critical coupling?",
                   "Why does synchrony in audiences repeatedly form and dissolve?"),
    discussion=("The transition is sharp even for modest populations, supporting a phase-transition view of "
                "collective rhythm.", "Heterogeneity of natural tempi sets the coupling needed for synchrony.",
                "Finite populations fluctuate around the mean-field curve near the transition."),
    limitations=("All-to-all coupling ignores spatial or social structure.", "No transmission delays or noise.",
                 "Euler integration with a fixed step introduces small numerical errors."),
    script="kuramoto.py",
    sweep_key="couplings",
    headline=T("結びつきがある臨界値を超えた瞬間に、集団のリズムは一斉に揃う", "a group suddenly synchronises once coupling crosses a critical value"),
    sweep_parameter="coupling",
    params={"replicates": 3},
    quick_params={"oscillators": 80, "steps": 600, "replicates": 3, "couplings": [0.0, 0.8, 1.4, 1.8, 2.4, 3.2]},
)

# ============================================================================ spatial prisoner's dilemma
SPATIAL_PD = Recipe(
    id="spatial_pd",
    title="Spatial Prisoner's Dilemma (Nowak-May lattice)",
    title_ja="空間囚人のジレンマ（協力の進化）",
    field="evolutionary game theory / cooperation",
    keywords=("cooperat", "altruis", "trust", "reciproc", "prisoner", "public good", "free rid",
              "game theor", "social dilemma", "commons", "reputation", "collective action",
              "協力", "利他", "信頼", "互恵", "囚人のジレンマ", "公共財", "フリーライダー", "ただ乗り",
              "ゲーム理論", "社会的ジレンマ", "共有地", "評判", "助け合い"),
    search_terms=("spatial prisoner's dilemma cooperation lattice", "network reciprocity evolution of cooperation",
                  "cooperation experiments networks humans", "evolutionary game theory spatial structure"),
    summary="Local interactions on a lattice let clusters of cooperators survive temptations that would wipe "
            "them out in a well-mixed population.",
    summary_ja="格子上で近所とだけ付き合うと、全体では不利なはずの協力者が「かたまり」で生き残る——協力の進化モデル。",
    background=("Why cooperation persists despite incentives to defect is a central question of evolutionary "
                "theory \\citep{axelrod1981evolution}. \\citet{nowak1992evolutionary} showed that spatial structure "
                "alone can sustain cooperators in the Prisoner's Dilemma, one of the 'five rules' for the evolution "
                "of cooperation \\citep{nowak2006five}. Experiments with humans on dynamic networks report related "
                "effects \\citep{rand2011dynamic}."),
    mechanism=("Players occupy the sites of a periodic square lattice and are either cooperators or defectors. "
               "Each round every player plays the weak Prisoner's Dilemma (R = 1, T = b, S = P = 0) with its eight "
               "neighbours and itself, then adopts the strategy of the highest-scoring player in its neighbourhood."),
    equations=(r"\begin{pmatrix} R & S \\ T & P \end{pmatrix} = \begin{pmatrix} 1 & 0 \\ b & 0 \end{pmatrix}",
               r"\Pi_i = \sum_{j \in \mathcal{N}(i) \cup \{i\}} \pi(s_i, s_j)",
               r"s_i(t+1) = s_{k^*}(t), \quad k^* = \arg\max_{k \in \mathcal{N}(i) \cup \{i\}} \Pi_k(t)"),
    assumptions=("Deterministic imitate-the-best updating.", "Synchronous updates on a periodic lattice.",
                 "Weak Prisoner's Dilemma payoffs with temptation b."),
    parameters=(ModelParameter("temptation", "b", "temptation to defect", 1.6,
                               [1.05, 1.15, 1.25, 1.35, 1.45, 1.55, 1.65, 1.75, 1.85, 1.95, 2.05]),
                ModelParameter("lattice", "L", "lattice side length", 30)),
    observables=("long-run share of cooperators",),
    hypotheses=(
        HypothesisTemplate(
            statement="Spatial structure sustains a substantial share of cooperators for moderate temptations, "
                      "whereas defection takes over in a well-mixed population.",
            rationale="Clusters of cooperators earn more from mutual cooperation than defectors at their boundary.",
            predictions=("cooperation above 50% for b < 1.6", "zero cooperation in the well-mixed baseline"),
            independent_variable="temptation b", dependent_variable="share of cooperators", evaluate=pd_spatial),
        HypothesisTemplate(
            statement="Cooperation declines in steps as the temptation grows and collapses beyond b = 2.",
            rationale="Discrete neighbourhood payoffs create thresholds at which cluster boundaries become unstable.",
            predictions=("roughly 30% cooperators in the 1.8-2.0 range", "cooperation below 5% for b > 2"),
            independent_variable="temptation b", dependent_variable="share of cooperators", evaluate=pd_collapse),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("近所づきあいは協力を生むか？ 固定近傍 vs シャッフルの囚人のジレンマ実験",
                "Do stable neighbours breed cooperation? Fixed vs shuffled partners in a PD experiment"),
        hypothesis=T("同じ相手と繰り返し関わる局所的な相互作用（固定近傍）では、毎回相手が入れ替わる条件より協力率が高く保たれる。",
                     "Stable local partners sustain more cooperation than partners reshuffled every round."),
        why_human=T("モデルのエージェントは「最も得した隣人を真似る」だけ。人間は評判・罰・感情で協力を決めるため、"
                    "空間構造の効果が人間でも残るかは実験でしか分からない。",
                    "Model agents just imitate the best neighbour; people use reputation, punishment and emotion, so "
                    "only experiments tell whether spatial structure still helps."),
        fun_factor=T("「情けは人のためならず」はネットワーク次第？ 小さな社会を作って協力の盛衰を観察できる。",
                     "Build a tiny society and watch cooperation rise and fall with its structure."),
        design_type="between",
        participants=T("12人1グループ（グループ単位で分析）", "Groups of 12 (group is the unit of analysis)"),
        conditions=L(["固定近傍：格子状に配置し毎ラウンド同じ4人と対戦", "シャッフル：毎ラウンド相手をランダムに入れ替え"],
                     ["Fixed neighbours: lattice with the same 4 partners every round", "Shuffled: new random partners each round"]),
        procedure=L(["ルール説明と理解度確認クイズ", "囚人のジレンマを30ラウンド（誘惑 b は中程度に設定）",
                     "各ラウンド後に相手の選択と自分の得点を表示", "終了後に戦略を自由記述"],
                    ["Instructions and a comprehension quiz", "30 rounds of the PD (moderate temptation b)",
                     "Feedback on partners' choices and own payoff after each round", "Free-text strategy report"]),
        measures=L(["後半15ラウンドの平均協力率（主要指標）", "最高得点の隣人を真似た割合"],
                   ["Mean cooperation in rounds 16-30 (primary)", "Rate of imitating the best-scoring neighbour"]),
        analysis_plan=T("グループ単位の後半協力率を条件間で比較（Welchのt検定、α=0.05）。個人レベルの模倣をロジスティック回帰で分析。",
                        "Compare group-level late-round cooperation between conditions (Welch t-test, alpha = 0.05); "
                        "analyse individual imitation with logistic regression."),
        effect_size_d=1.0,
        ethics=L(["欺瞞（ディセプション）を用いない", "報酬は得点に応じて支払い、上限を明示", "同意取得・匿名化・倫理審査の確認"],
                 ["No deception", "Pay according to points with a stated cap", "Consent, anonymisation, ethics review"]),
        materials=L(["oTree 等のオンライン実験基盤", "成果報酬の予算"], ["An online experiment platform (e.g. oTree)",
                                                         "A budget for performance-based pay"]),
        duration=T("準備2週間・実施2週間", "2 weeks preparation, 2 weeks sessions"),
        cost=T("1人あたり約600円（30分・成果報酬込み）", "about USD 5 per participant (30 minutes incl. bonus)"),
        risks=L(["理解不足による無作為な選択 → 理解度クイズで除外", "グループ内の途中離脱 → ボットで代替しない（除外）"],
                ["Random choices from confusion -> exclude failed quizzes", "Drop-outs -> exclude groups (no bots)"]),
        link=T("シミュレーションでは空間構造があると誘惑 b が約1.8を超えても協力者が約3割残った。実験の利得をこの領域に設定し、"
               "人間でも協力者の「かたまり」が生き残るかを検証する。",
               "The simulation keeps about 30% cooperators even at b around 1.8; payoffs are set to this regime to "
               "test whether cooperative clusters survive among humans."),
    ),),
    references=(
        ref("nowak1992evolutionary", "Evolutionary games and spatial chaos", ["Martin A. Nowak", "Robert M. May"],
            1992, "Nature 359:826-829", doi="10.1038/359826a0"),
        ref("axelrod1981evolution", "The evolution of cooperation", ["Robert Axelrod", "William D. Hamilton"], 1981,
            "Science 211:1390-1396", doi="10.1126/science.7466396"),
        ref("nowak2006five", "Five rules for the evolution of cooperation", ["Martin A. Nowak"], 2006,
            "Science 314:1560-1563", doi="10.1126/science.1133755"),
        ref("rand2011dynamic", "Dynamic social networks promote cooperation in experiments with humans",
            ["David G. Rand", "Samuel Arbesman", "Nicholas A. Christakis"], 2011, "PNAS 108(48):19193-19198"),
    ),
    open_problems=("Does network reciprocity survive when humans use reputation and punishment?",
                   "How robust are cooperative clusters to noise in strategy updating?",
                   "Which structures of online communities favour prosocial behaviour?"),
    discussion=("Cooperators survive by forming compact clusters whose interior earns more than defectors at the edge.",
                "The decline of cooperation with temptation is stepwise because payoff comparisons involve discrete "
                "neighbour counts.", "In the 1.8-2.0 range cooperators and defectors coexist in ever-changing patterns."),
    limitations=("Deterministic imitation without noise is a strong idealisation of human learning.",
                 "Results are for one lattice size and a fixed initial share of defectors.",
                 "No reputation, punishment or partner choice."),
    script="spatial_pd.py",
    sweep_key="temptations",
    headline=T("近所とだけ付き合う社会では、裏切りが得でも協力者のかたまりが生き残る", "cooperators survive in local clusters even when defection pays"),
    sweep_parameter="temptation",
    params={"replicates": 3},
    quick_params={"lattice": 18, "generations": 30, "burn_in": 15, "replicates": 3,
                  "temptations": [1.05, 1.35, 1.65, 1.85, 2.05]},
)

# ============================================================================ Schelling
SCHELLING = Recipe(
    id="schelling",
    title="Schelling model of residential segregation",
    title_ja="シェリングの分居モデル（住み分けの創発）",
    field="computational social science / urban dynamics",
    keywords=("segregat", "neighborhood", "neighbourhood", "housing", "residen", "urban", "city", "cities",
              "homophil", "gentrif", "migrat", "diversity",
              "分居", "居住", "住み分け", "住み替え", "近所", "都市", "街", "同類性", "類は友を呼ぶ",
              "移住", "多様性", "ジェントリフィケーション", "引っ越し"),
    search_terms=("Schelling segregation model", "residential segregation agent-based model",
                  "homophily preferences segregation", "urban segregation dynamics"),
    summary="Mild individual preferences for similar neighbours add up to strong macro-level segregation.",
    summary_ja="「同じグループの隣人が少しいればいい」という穏やかな好みが、街全体では強い住み分けを生むモデル。",
    background=("\\citet{schelling1971dynamic} demonstrated with a simple grid model that segregation can emerge "
                "from mild individual preferences, a canonical example of the micro-macro gap "
                "\\citep{schelling1978micromotives}. Empirical work has examined whether stated residential "
                "preferences are consistent with the model \\citep{clark1991residential}."),
    mechanism=("Agents of two groups live on a periodic grid with some empty cells. An agent is unhappy if the "
               "share of like neighbours among its occupied neighbours is below tau; unhappy agents move to random "
               "empty cells until everyone is satisfied or a sweep limit is reached."),
    equations=(r"u_i = \mathbf{1}\left[\frac{n_i^{\text{same}}}{n_i^{\text{same}} + n_i^{\text{other}}} \geq \tau\right]",
               r"S = \frac{1}{|A|} \sum_{i \in A} \frac{n_i^{\text{same}}}{n_i^{\text{same}} + n_i^{\text{other}}}"),
    assumptions=("Two equally sized groups with identical thresholds.", "Relocation to random empty cells at no cost.",
                 "Moore neighbourhood on a periodic grid."),
    parameters=(ModelParameter("tau", "\\tau", "tolerance threshold (minimum like share wanted)", 0.3,
                               [0.1, 0.2, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8]),
                ModelParameter("grid", "L", "grid side length", 30),
                ModelParameter("empty_share", "\\rho_0", "share of empty cells", 0.1)),
    observables=("segregation index S (mean like-neighbour share)", "share of unhappy agents"),
    hypotheses=(
        HypothesisTemplate(
            statement="Even mild preferences (tau around 0.3) produce like-neighbour shares far above the 50% "
                      "expected under random mixing.",
            rationale="Each move of an unhappy agent makes other agents in the old neighbourhood more likely to move.",
            predictions=("S above 0.7 at tau = 0.3",),
            independent_variable="tolerance threshold tau", dependent_variable="segregation index S", evaluate=sch_mild),
        HypothesisTemplate(
            statement="Very demanding preferences prevent the city from settling: a large share of agents stays "
                      "unhappy.",
            rationale="When most agents require a large like share, vacancies cannot satisfy everyone.",
            predictions=("more than 20% unhappy agents for tau >= 0.75",),
            independent_variable="tolerance threshold tau", dependent_variable="share of unhappy agents", evaluate=sch_churn),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("理想の近所は？ 住み替えビネット実験で「ゆるい好み」の帰結を測る",
                "What neighbourhood do people want? A relocation vignette experiment"),
        hypothesis=T("一人ひとりの好みは穏やかでも、住み替えの選択を繰り返すと強い住み分けが生じる。",
                     "Mild individual preferences still produce strong segregation through repeated relocation choices."),
        why_human=T("実際の住み替えの好みは価格・通勤・グループ定義など多要因。人間の許容しきい値 τ の分布を測らないとモデルの前提は検証できない。",
                    "Real relocation choices involve price, commute and group identity; the distribution of human "
                    "thresholds must be measured to test the model's premise."),
        fun_factor=T("誰も分断を望んでいないのに街が分かれていく——その逆説を参加型ゲームで体験・計測できる。",
                     "Experience the paradox of a city that segregates although nobody wants it."),
        design_type="between",
        participants=T("一般成人のオンライン参加者（個人単位）", "Adult online participants (individual level)"),
        conditions=L(["近隣構成を色付きマップで表示", "構成を表示せず家賃・通勤時間のみ表示（統制）"],
                     ["Neighbourhood composition shown on a map", "Only rent and commute shown (control)"]),
        procedure=L(["抽象的な2色グループの架空の街で住む場所を選ぶビネット課題を20回", "各回で『引っ越すか・どこへ』を選択",
                     "最後に理想の近隣構成（同グループ割合）を直接質問"],
                    ["20 vignettes: choose a home in a fictional city of two abstract colour groups",
                     "Decide each time whether and where to move", "Directly ask for the ideal neighbourhood composition"]),
        measures=L(["選択から推定したしきい値 τ（主要指標）", "直接質問との乖離", "選択の一貫性"],
                   ["Threshold tau estimated from choices (primary)", "Gap to the stated ideal", "Choice consistency"]),
        analysis_plan=T("条件付きロジットで同グループ割合の効用を推定し τ を算出、条件間の差を検定。推定 τ の分布をモデルに入力して住み分けを予測する。",
                        "Estimate the utility of like-group share with a conditional logit, derive tau, test condition "
                        "differences, and feed the tau distribution back into the model."),
        effect_size_d=0.5,
        ethics=L(["実在の人種・民族ではなく抽象的なグループで実施（差別の助長を避ける）", "事後説明で結果解釈への配慮を伝える",
                  "同意取得・匿名化・倫理審査の確認"],
                 ["Use abstract groups instead of real ethnic categories", "Careful debriefing on interpretation",
                  "Consent, anonymisation, ethics review"]),
        materials=L(["オンライン調査ツール", "ビネット用の地図画像"], ["An online survey tool", "Vignette map images"]),
        duration=T("準備2週間・実施1週間", "2 weeks preparation, 1 week data collection"),
        cost=T("1人あたり約300円（15分）", "about USD 2-3 per participant (15 minutes)"),
        risks=L(["社会的望ましさバイアス → 行動指標（選択）を主要指標に", "抽象化による外的妥当性の低下 → 追加調査で補完"],
                ["Social desirability bias -> behavioural choices as the primary outcome",
                 "Abstraction limits external validity -> follow-up survey"]),
        link=T("シミュレーションでは τ=0.3 でも同種隣人の割合が約7割に達した。推定した τ の分布をモデルに入れ、現実的な好みの下での住み分けの強さを予測する。",
               "The simulation yields about 70% like neighbours even at tau = 0.3; the measured thresholds let the "
               "model predict segregation under realistic preferences."),
    ),),
    references=(
        ref("schelling1971dynamic", "Dynamic models of segregation", ["Thomas C. Schelling"], 1971,
            "Journal of Mathematical Sociology 1(2):143-186"),
        ref("schelling1978micromotives", "Micromotives and Macrobehavior", ["Thomas C. Schelling"], 1978,
            "W. W. Norton"),
        ref("clark1991residential",
            "Residential preferences and neighborhood racial segregation: A test of the Schelling segregation model",
            ["William A. V. Clark"], 1991, "Demography 28(1):1-19"),
    ),
    open_problems=("What is the empirical distribution of residential tolerance thresholds?",
                   "Which policies (e.g. mixed housing) counteract segregation dynamics?",
                   "Does the micro-macro gap also appear in online communities and friend networks?"),
    discussion=("Segregation is an emergent property: individually tolerant agents collectively produce "
                "homogeneous neighbourhoods.", "The relation between tolerance and segregation is strongly "
                "non-linear.", "Very demanding preferences produce churn rather than a stable pattern."),
    limitations=("Only two groups and homogeneous thresholds.", "Moves are free and random rather than utility-based.",
                 "Grid geography ignores housing markets and institutions."),
    script="schelling.py",
    sweep_key="thresholds",
    headline=T("「同じグループの隣人は3割で十分」という穏やかな好みでも、街は強く住み分かれる", "even a mild wish for 30% like neighbours produces strong segregation"),
    sweep_parameter="tau",
    params={"replicates": 4},
    quick_params={"grid": 18, "replicates": 3, "max_sweeps": 30, "thresholds": [0.1, 0.3, 0.5, 0.7, 0.8]},
)

# ============================================================================ Simon / Zipf
SIMON_ZIPF = Recipe(
    id="simon_zipf",
    title="Simon's rich-get-richer model of Zipf's law",
    title_ja="サイモン・モデル（Zipf則と「富める者はますます富む」）",
    field="quantitative linguistics / complex systems",
    keywords=("zipf", "power law", "power-law", "word frequenc", "frequency distribution", "popularity",
              "rich get richer", "rich-get-richer", "preferential attachment", "citation", "ranking", "long tail",
              "trend", "fashion", "hashtag", "baby name",
              "ジップ", "べき乗則", "べき分布", "頻度", "人気", "富める者", "優先的選択", "引用", "ランキング",
              "ロングテール", "ヒット", "トレンド", "ハッシュタグ", "名前"),
    search_terms=("Zipf's law word frequency model", "Simon model preferential attachment",
                  "rich get richer popularity dynamics", "innovation rate vocabulary growth"),
    summary="Reusing items in proportion to their past frequency, plus occasional innovation, yields Zipf's law.",
    summary_ja="過去によく使われた語ほど再利用され、ときどき新語が生まれる——それだけで Zipf 則が現れるモデル。",
    background=("Word frequencies in natural language follow Zipf's law \\citep{zipf1949human,piantadosi2014zipf}. "
                "\\citet{simon1955class} proposed a rich-get-richer mechanism that generates such skewed "
                "distributions, a mechanism shared by many power laws in nature and society "
                "\\citep{newman2005power}."),
    mechanism=("A text grows token by token. With probability alpha a brand-new word is coined; otherwise the next "
               "token copies a uniformly random earlier token, so words are reused in proportion to their "
               "frequency."),
    equations=(r"P(\text{new word}) = \alpha, \qquad P(\text{reuse } w) = (1-\alpha)\frac{f_w(t)}{t}",
               r"f(r) \propto r^{-z}, \qquad z = 1 - \alpha"),
    assumptions=("Constant innovation rate alpha.", "Reuse proportional to frequency (no forgetting).",
                 "Words are interchangeable apart from their frequency."),
    parameters=(ModelParameter("alpha", "\\alpha", "innovation rate (share of new words)", 0.1,
                               [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4]),
                ModelParameter("tokens", "T", "text length in tokens", 60000)),
    observables=("Zipf exponent z of the rank-frequency distribution", "vocabulary size"),
    hypotheses=(
        HypothesisTemplate(
            statement="The Zipf exponent decreases with the innovation rate, approximately following z = 1 - alpha.",
            rationale="More innovation spreads usage over more words, flattening the rank-frequency curve.",
            predictions=("the fitted exponent decreases monotonically with alpha",),
            independent_variable="innovation rate alpha", dependent_variable="Zipf exponent z", evaluate=zipf_rule),
        HypothesisTemplate(
            statement="Rich-get-richer reuse alone yields a straight rank-frequency line on log-log axes.",
            rationale="Preferential reuse generates scale-free growth of word counts.",
            predictions=("log-log fits of the top ranks with R^2 above 0.9",),
            independent_variable="(none: structural property)", dependent_variable="goodness of the power-law fit", evaluate=zipf_fit),
    ),
    human_ideas=(HumanIdeaTemplate(
        title=T("新語はどれくらい生まれる？ リレー物語の造語ゲームで測るイノベーション率とZipf則",
                "How often do people coin words? A relay-story game measuring innovation and Zipf's law"),
        hypothesis=T("新しい語を作る割合（イノベーション率 α）が高い条件ほど、語彙の頻度分布は平らになる（Zipf指数が小さくなる）。",
                     "Groups that coin new words more often produce flatter frequency distributions (smaller Zipf exponents)."),
        why_human=T("モデルの α は一定の確率。人間の造語は文脈・遊び心・模倣圧に左右され、実際の α はデータを集めないと分からない。",
                    "Alpha is a constant in the model; human word coinage depends on context, play and conformity."),
        fun_factor=T("みんなで物語をつなぎながら造語するだけで、自然言語と同じ「べき乗則」が現れるかを確かめられる。",
                     "See whether a power law emerges from a playful group story."),
        design_type="between",
        participants=T("5人1グループでリレー形式の物語を書く（テキスト単位で分析）",
                       "Groups of 5 write a relay story (each text is the unit)"),
        conditions=L(["創造性奨励：「新しい言葉を自由に作ってOK」", "慣習重視：「なるべく既に出た言葉を使う」"],
                     ["Creativity prompt: 'feel free to invent words'", "Convention prompt: 'reuse words already used'"]),
        procedure=L(["共有ドキュメントで架空世界の出来事を1人3文ずつリレー", "前の文を読んでから書く", "総語数が約3,000語に達するまで継続"],
                    ["Relay-write three sentences each about a fictional world", "Read previous text before writing",
                     "Continue until about 3,000 words"]),
        measures=L(["新規語の出現割合（α の推定、主要指標）", "順位-頻度分布のZipf指数", "語の再利用の偏り"],
                   ["Share of new words (estimate of alpha, primary)", "Zipf exponent", "Concentration of reuse"]),
        analysis_plan=T("テキストごとに α と Zipf 指数を算出し条件間比較（t検定、α=0.05）。α と指数の関係をモデルの予測 z=1−α と比較する。",
                        "Compute alpha and the Zipf exponent per text, compare conditions (t-test, alpha = 0.05) and "
                        "compare the relation with the model prediction z = 1 - alpha."),
        effect_size_d=0.8,
        ethics=L(["不適切な表現のモデレーション", "作成テキストの研究利用について同意を得る", "同意取得・匿名化"],
                 ["Moderate inappropriate content", "Consent for research use of the texts", "Consent and anonymisation"]),
        materials=L(["共有ドキュメント環境", "形態素解析ツール（日本語の場合）"],
                    ["A shared document environment", "A tokenizer (for Japanese text)"]),
        duration=T("準備1週間・実施2週間", "1 week preparation, 2 weeks sessions"),
        cost=T("1人あたり約400円（20分）", "about USD 3 per participant (20 minutes)"),
        risks=L(["テキストが短いと指数推定が不安定 → 語数の下限を設定", "日本語の語の区切り → 形態素解析の基準を事前に固定"],
                ["Short texts give unstable exponents -> minimum length", "Word segmentation -> fix the tokenizer in advance"]),
        link=T("シミュレーションでは α が大きいほど Zipf 指数が 1−α に沿って小さくなった。人間のテキストから推定した α で予測される指数と実測を比べる。",
               "The simulation shows z decreasing along 1 - alpha; human texts provide both alpha and z for a direct test."),
    ),),
    references=(
        ref("simon1955class", "On a class of skew distribution functions", ["Herbert A. Simon"], 1955,
            "Biometrika 42(3/4):425-440", doi="10.1093/biomet/42.3-4.425"),
        ref("zipf1949human", "Human Behavior and the Principle of Least Effort", ["George K. Zipf"], 1949,
            "Addison-Wesley"),
        ref("piantadosi2014zipf", "Zipf's word frequency law in natural language: A critical review and future directions",
            ["Steven T. Piantadosi"], 2014, "Psychonomic Bulletin & Review 21(5):1112-1130"),
        ref("newman2005power", "Power laws, Pareto distributions and Zipf's law", ["Mark E. J. Newman"], 2005,
            "Contemporary Physics 46(5):323-351", doi="10.1080/00107510500052444"),
    ),
    open_problems=("How does the innovation rate of real speakers vary across contexts and communities?",
                   "Do online platforms (hashtags, memes) follow the same rich-get-richer dynamics as language?",
                   "Which deviations from Zipf's law reveal additional cognitive mechanisms?"),
    discussion=("A single parameter, the innovation rate, controls the steepness of the frequency distribution.",
                "Finite texts deviate from the asymptotic exponent, especially for small alpha.",
                "The same mechanism explains skewed popularity in citations, names and online content."),
    limitations=("Reuse ignores meaning, grammar and forgetting.", "Exponents are fitted on the top ranks of finite texts.",
                 "Constant innovation rate over time."),
    script="simon_zipf.py",
    sweep_key="alphas",
    headline=T("新しい言葉を作る割合が高いほど、言葉の使用頻度の偏りは小さくなる", "coining more new words flattens the word-frequency distribution"),
    sweep_parameter="alpha",
    params={"replicates": 4},
    quick_params={"tokens": 15000, "replicates": 3, "alphas": [0.05, 0.1, 0.2, 0.4]},
)

RECIPES: dict[str, Recipe] = {r.id: r for r in (NAMING_GAME, BOUNDED_CONFIDENCE, SIR_NETWORK, KURAMOTO, SPATIAL_PD,
                                                SCHELLING, SIMON_ZIPF)}

# A generic, recipe-independent human study: can people foresee the macro outcome?
INTUITION_IDEA = HumanIdeaTemplate(
    title=T("直感 vs シミュレーション：人はミクロなルールからマクロな帰結を予測できるか",
            "Intuition vs simulation: can people foresee macro outcomes from micro rules?"),
    hypothesis=T("人々はミクロな行動ルールが生むマクロな結果（{prediction}）を系統的に読み違える。",
                 "People systematically mispredict the macro-level outcome of simple micro rules ({prediction})."),
    why_human=T("直感や予測の偏りは人間からしか測れない。モデルの結果を『正解』として使える稀有な機会でもある。",
                "Biases in human intuition can only be measured in humans; the simulation provides a ground truth."),
    fun_factor=T("シミュレーション結果を答えにした予想クイズ。研究室メンバーや友人と点数を競える。",
                 "A prediction quiz whose answer key is the simulation — compete with friends."),
    design_type="between",
    participants=T("一般成人のオンライン参加者（個人単位）", "Adult online participants (individual level)"),
    conditions=L(["ルール説明のみ", "ルール説明＋小規模な例のアニメーション"],
                 ["Rule description only", "Rule description plus a small animated example"]),
    procedure=L(["モデルのミクロなルールを平易な言葉で説明", "マクロな結果を数値で予想し確信度を回答",
                 "正解（シミュレーション結果）を提示し驚き度を評定"],
                ["Explain the model's micro rules in plain language", "Predict the macro outcome and rate confidence",
                 "Reveal the simulated answer and rate surprise"]),
    measures=L(["予測誤差（主要指標）", "確信度と誤差の関係（過信）", "驚き度"],
               ["Prediction error (primary)", "Calibration of confidence", "Surprise"]),
    analysis_plan=T("予測誤差が0と異なるかを1標本t検定、条件間の差をWelchのt検定（α=0.05）で検討する。",
                    "One-sample t-test of prediction error against zero and Welch t-test between conditions (alpha = 0.05)."),
    effect_size_d=0.5,
    ethics=COMMON_ETHICS,
    materials=L(["オンライン調査ツール", "モデルの説明図とアニメーション"], ["An online survey tool", "Explainer graphics and animation"]),
    duration=T("準備1週間・実施1週間", "1 week preparation, 1 week data collection"),
    cost=T("1人あたり約200円（10分）", "about USD 1.5 per participant (10 minutes)"),
    risks=L(["説明が難しすぎる → パイロットで理解度を確認"], ["Explanations too hard -> pilot for comprehension"]),
    link=T("今週の {recipe} の結果（{prediction}）を正解として用いる。",
           "Uses this week's {recipe} results ({prediction}) as the answer key."),
)
