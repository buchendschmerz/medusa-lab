# Analyst report — 強迫症の記憶トレースモデルの発展

I model OCD-like checking as credit assignment with eligibility traces in a partially observable 'did I really turn it off?' MDP, coupled to a Bayesian belief-state module with a subjective state-transition-uncertainty parameter. The same TD(lambda) agent is also run on a probabilistic reversal task so that compulsive re-checking and stimulus-bound perseveration can be read out from one parameter set. This directly builds the missing bridge flagged by Scout: trace decay lambda and trace type (accumulating vs replacing) become the memory-trace substrate of obsessive repetition, while the subjective flip probability epsilon instantiates the Bayesian 'excessive transition uncertainty' account, letting us test whether the two accounts are formally interchangeable. The model is tiny (tabular Q, <=12 states, two toy tasks) and runs in seconds in numpy.

## Model: Trace-Based Checking Agent (TBCA): TD(lambda) with belief-state arbitration in a partially observable checking MDP

An agent must decide whether a hazard (stove) is off. It holds a Bayesian belief b over the hidden binary state, updated by noisy checks and by a subjective flip probability epsilon that represents excessive state-transition uncertainty. Action values combine a one-step model-based belief computation and a model-free TD(lambda) value function over (check-count, belief-bin) states, learned with accumulating or replacing eligibility traces. The identical agent is also run on a two-armed probabilistic reversal task to read out stimulus-bound perseveration, so that compulsive re-checking and perseveration can dissociate within one parameter vector.

### Equations

$$ b_t^{-} = (1-\varepsilon) b_{t-1} + \varepsilon (1 - b_{t-1}) $$
$$ b_t = \frac{P(o_t \mid s=1)\, b_t^{-}}{P(o_t \mid s=1)\, b_t^{-} + P(o_t \mid s=0)\,(1-b_t^{-})}, \quad P(o=1 \mid s=1) = P(o=0 \mid s=0) = q $$
$$ x_t = (\min(n_t, N_{\max}),\ \lfloor b_t K \rfloor), \quad a_t \in \{\mathrm{CHECK}, \mathrm{LEAVE}\} $$
$$ \delta_t = r_t + \gamma \max_{a'} Q_{MF}(x_{t+1}, a') - Q_{MF}(x_t, a_t) $$
$$ e_t(x,a) = \gamma \lambda\, e_{t-1}(x,a) + \mathbb{1}[x = x_t, a = a_t] \quad \text{(accumulating)} $$
$$ e_t(x,a) = \begin{cases} 1 & (x,a) = (x_t,a_t) \\ \gamma \lambda\, e_{t-1}(x,a) & \text{otherwise} \end{cases} \quad \text{(replacing)} $$

### Assumptions

- The hazard's true state is fixed within an episode (true flip probability is zero by default); any perceived instability comes from the agent's subjective epsilon.
- Checks are conditionally independent noisy observations with symmetric reliability q; the agent knows q but may misestimate epsilon.
- The model-based module does only one-step lookahead with the agent's own (possibly wrong) epsilon, so 'model-based' does not mean 'correct'.
- Model-free state representation is the discretised pair (number of checks so far, belief bin); repeated checks at an unchanged belief bin map to the same state-action pair, which is what makes accumulating traces super-credit repetition.
- Rewards: each check costs c; leaving with the hazard on incurs R_dis < 0; leaving safely yields 0. No explicit anxiety-relief reward is added, so compulsion must emerge from credit assignment, not from a built-in reinforcer.
- Arbitration weight w is fixed within a simulated agent (no dynamic arbitration), keeping the parameter count minimal.
- The reversal task uses the same tabular TD(lambda) machinery with stimulus identity as state, so lambda, alpha and trace type are shared across tasks.

### Parameters

| name | symbol | description | default | sweep |
|---|---|---|---|---|
| lam | $\lambda$ | Eligibility trace decay (credit-assignment horizon) | 0.6 | 0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 0.99 |
| trace_type | $\tau$ | Trace variant: 1 = accumulating, 0 = replacing | 1 | 0, 1 |
| alpha | $\alpha$ | TD learning rate | 0.15 | 0.05, 0.15, 0.3 |
| eps_sub | $\varepsilon$ | Subjective state-transition (flip) probability between checks: excessive-uncertainty parameter | 0.05 | 0, 0.02, 0.05, 0.1, 0.2, 0.35 |
| q | $q$ | Reliability of a single check (observation accuracy) | 0.8 | 0.6, 0.7, 0.8, 0.9, 0.95 |
| w_mb | $w$ | Weight on the model-based (belief) value relative to the model-free trace value | 0.5 | 0, 0.25, 0.5, 0.75, 1 |
| beta | $\beta$ | Softmax inverse temperature | 5 | 2, 5, 10 |
| c_check | $c$ | Cost of one check | 0.05 | 0.01, 0.05, 0.2 |
| R_dis | $R_{dis}$ | Penalty for leaving with the hazard on | -10 | -30, -10, -3 |
| gamma | $\gamma$ | Temporal discount factor | 0.95 | 0.9, 0.95, 0.99 |

## Hypotheses

- **H1** [in_silico] Accumulating eligibility traces produce runaway escalation of checking as lambda increases, whereas replacing traces keep checking bounded; i.e. there is a lambda x trace-type interaction on checks per episode.
- **H2** [in_silico] Excessive subjective transition uncertainty (high epsilon) and long accumulating traces (high lambda) are behaviourally near-equivalent generators of over-checking, so fitting a trace model to Bayesian-generated data recovers an inflated lambda and vice versa.
- **H3** [in_silico] Under partial observability, net performance is an inverted-U function of lambda, and the performance-optimal lambda* rises as check reliability q falls — but the checking rate at lambda* rises with it, so robustness to hidden state is bought with pathological re-checking.
- **H4** [human] In humans, lengthening the effective credit-assignment window by delaying and aggregating feedback increases voluntary re-checking, and this increase is larger in individuals with higher self-reported compulsivity (OCI-R); moreover re-checking escalates while subjective confidence falls, dissociating behaviour from memory.

## Human experiment ideas

- **E1** 遅延・集約フィードバックはヒトの「確認」を増やすか：適格度トレース仮説の行動検証 (n = 41 per condition, d = 0.45)
- **E2** 同じ景色をもう一度見るか、違う角度から見るか：累積型トレースと置換型トレースを人で切り分ける (n = 34 per condition, d = 0.5)
