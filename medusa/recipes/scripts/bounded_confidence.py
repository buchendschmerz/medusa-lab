"""Deffuant-Weisbuch bounded-confidence opinion dynamics.

Random pairs whose opinions differ by less than the confidence bound epsilon move towards
each other by a fraction mu. We sweep epsilon and count the surviving opinion clusters;
mean-field theory predicts roughly floor(1 / (2 epsilon)) major clusters.
"""

import math
import random

import medusa_sim as sim

n = int(sim.param("agents", 400))
steps_per_agent = int(sim.param("steps_per_agent", 250))
mu = float(sim.param("mu", 0.5))
epsilons = [float(e) for e in sim.param("epsilons", [0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5])]
replicates = int(sim.param("replicates", 5))
minor = float(sim.param("minor_cluster_share", 0.02))
sim.seed(sim.param("seed", 20260922))
rng = random.Random(sim.param("seed", 20260922))


def clusters(opinions, gap):
    xs = sorted(opinions)
    groups = [[xs[0]]]
    for x in xs[1:]:
        if x - groups[-1][-1] > gap:
            groups.append([x])
        else:
            groups[-1].append(x)
    return groups


def run(eps):
    x = [rng.random() for _ in range(n)]
    for _ in range(steps_per_agent * n):
        i = rng.randrange(n)
        j = rng.randrange(n - 1)
        if j >= i:
            j += 1
        d = x[j] - x[i]
        if -eps < d < eps:
            x[i] += mu * d
            x[j] -= mu * d
    groups = clusters(x, 1e-3)
    major = [g for g in groups if len(g) >= minor * n]
    largest = max(len(g) for g in groups) / n
    spread = max(x) - min(x)
    return len(major), largest, spread


rows = []
for idx, eps in enumerate(epsilons):
    counts, largest, spread = [], [], []
    for _ in range(replicates):
        c, big, sp = run(eps)
        counts.append(c)
        largest.append(big)
        spread.append(sp)
    m, lo, hi = sim.mean_ci(counts)
    lm, llo, lhi = sim.mean_ci(largest)
    theory = max(1, math.floor(1 / (2 * eps)))
    rows.append([eps, m, lo, hi, theory, lm, llo, lhi, sum(spread) / len(spread)])
    sim.progress((idx + 1) / len(epsilons) * 0.95, f"epsilon={eps}")

sim.save_table("clusters", ["epsilon", "clusters", "clusters_lo", "clusters_hi", "theory", "largest",
                            "largest_lo", "largest_hi", "spread"], rows)

# consensus threshold: smallest epsilon whose mean cluster count is ~1
consensus_eps = next((r[0] for r in rows if r[1] <= 1.05), None)
errors = [abs(r[1] - r[4]) for r in rows]
sim.metric("consensus_threshold_epsilon", consensus_eps, "smallest epsilon reaching a single opinion cluster")
sim.metric("mean_abs_error_vs_theory", round(sum(errors) / len(errors), 3), "|clusters - floor(1/(2 eps))|, averaged")
sim.metric("clusters_at_min_epsilon", round(rows[0][1], 2), f"major clusters at epsilon={epsilons[0]}")
sim.metric("largest_share_at_min_epsilon", round(rows[0][5], 3), "share of agents in the largest cluster")
sim.figure("fig_clusters", "clusters", "epsilon", ["clusters", "theory"], lower=["clusters_lo"],
           upper=["clusters_hi"], labels=["simulation", "1/(2 epsilon) rule"],
           xlabel="Confidence bound $\\varepsilon$", ylabel="Number of major opinion clusters",
           caption=f"Opinion clusters after {steps_per_agent} interactions per agent (mean, 95\\% CI, "
                   f"{replicates} runs, N={n}).")
sim.figure("fig_largest", "clusters", "epsilon", ["largest"], lower=["largest_lo"], upper=["largest_hi"],
           labels=["largest cluster"], xlabel="Confidence bound $\\varepsilon$",
           ylabel="Share of agents in the largest cluster",
           caption="Size of the dominant opinion group as tolerance increases.")
sim.finding(f"The number of opinion clusters falls from {rows[0][1]:.1f} at epsilon={epsilons[0]} to "
            f"{rows[-1][1]:.1f} at epsilon={epsilons[-1]}.")
if consensus_eps is not None:
    sim.finding(f"A single consensus cluster emerges once epsilon >= {consensus_eps}.")
sim.finding(f"The simple 1/(2 epsilon) rule deviates from the simulated cluster count by "
            f"{sum(errors) / len(errors):.2f} clusters on average.")
sim.finish(summary="Bounded-confidence dynamics: clusters ~ 1/(2 epsilon); consensus above a tolerance threshold.")
