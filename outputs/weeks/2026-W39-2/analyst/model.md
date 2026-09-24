# Analyst report — LLMはオノマトペを接地・創発できるか

The theme maps onto the Naming Game model of lexical convention formation (matched terms: language). Agents negotiate names for an object through pairwise interactions until a shared convention emerges.

## Model: Naming Game model of lexical convention formation

Each agent holds an inventory of candidate names. At every step a random speaker utters a name from its inventory (inventing a new one if empty) to a random neighbour. If the hearer already knows the name, the interaction succeeds and both agents discard all competing names; otherwise the hearer adds the name to its inventory.

### Equations

$$ N_w(t) = \sum_{i=1}^{N} |\mathcal{I}_i(t)| $$
$$ t_{\mathrm{conv}} \sim N^{\alpha}, \quad \alpha_{\mathrm{MF}} = 3/2 $$
$$ N_w^{\max} \sim N^{\beta}, \quad \beta_{\mathrm{MF}} = 3/2 $$

### Assumptions

- Agents have unbounded memory and no preference among names.
- Interactions are pairwise, random and sequential.
- A single object (meaning) is being named; there is no homonymy.

### Parameters

| name | symbol | description | default | sweep |
|---|---|---|---|---|
| population | $N$ | number of agents | 256 | 32, 64, 128, 256 |
| sw_degree | $k$ | degree of the small-world ring lattice | 6 |  |
| sw_rewire | $p$ | Watts-Strogatz rewiring probability | 0.1 |  |

## Hypotheses

- **H1** [in_silico] In a well-mixed population the time to lexical consensus grows super-linearly with population size, with an exponent close to the mean-field value 3/2.
- **H2** [in_silico] Local small-world contact structure lowers the peak lexical memory but slows the final agreement compared with a well-mixed population.
- **H3** [human] 誰とでも話せる集団（完全混合）は、近所としか話さない集団（スモールワールド）より早く呼び名の合意に達する。
- **H4** [human] 人々はミクロな行動ルールが生むマクロな結果（集団が大きくなるほど、共通語ができるまでの時間は人数の増え方以上に長くなる）を系統的に読み違える。

## Human experiment ideas

- **E1** オンライン・ネーミングゲーム実験：つながり方で「新語の合意」は速くなるか (n = 12 per condition, d = 1.2)
- **E2** 直感 vs シミュレーション：人はミクロなルールからマクロな帰結を予測できるか (n = 64 per condition, d = 0.5)
