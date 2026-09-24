"""Discrete-time SIR contagion on random (Erdos-Renyi) vs scale-free (Barabasi-Albert) networks.

Each step every infected node transmits to each susceptible neighbour with probability beta and
recovers with probability gamma. We sweep beta and record the final outbreak size; heterogeneous
(scale-free) contact structure lowers the epidemic threshold.
"""

import random

import medusa_sim as sim

n = int(sim.param("nodes", 1000))
mean_degree = int(sim.param("mean_degree", 6))
gamma = float(sim.param("gamma", 0.2))
betas = [float(b) for b in sim.param("betas", [0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.1, 0.13, 0.16, 0.2])]
replicates = int(sim.param("replicates", 12))
seeds_infected = int(sim.param("initial_infected", 5))
sim.seed(sim.param("seed", 20260923))
rng = random.Random(sim.param("seed", 20260923))


def erdos_renyi(size, k):
    p = k / (size - 1)
    adj = [[] for _ in range(size)]
    for i in range(size):
        for j in range(i + 1, size):
            if rng.random() < p:
                adj[i].append(j)
                adj[j].append(i)
    return adj


def barabasi_albert(size, k):
    m = max(1, k // 2)
    adj = [[] for _ in range(size)]
    targets = list(range(m))
    repeated = []
    for new in range(m, size):
        chosen = set()
        while len(chosen) < m:
            chosen.add(rng.choice(repeated) if repeated else rng.choice(targets))
        for t in chosen:
            adj[new].append(t)
            adj[t].append(new)
        repeated.extend(chosen)
        repeated.extend([new] * m)
    return adj


def outbreak(adj, beta):
    state = [0] * n  # 0=S, 1=I, 2=R
    infected = rng.sample(range(n), seeds_infected)
    for i in infected:
        state[i] = 1
    active = list(infected)
    peak = len(active)
    while active:
        new = []
        for i in active:
            for j in adj[i]:
                if state[j] == 0 and rng.random() < beta:
                    state[j] = 1
                    new.append(j)
        still = []
        for i in active:
            if rng.random() < gamma:
                state[i] = 2
            else:
                still.append(i)
        active = still + new
        peak = max(peak, len(active))
    return sum(1 for s in state if s == 2) / n, peak / n


networks = {"er": erdos_renyi(n, mean_degree), "ba": barabasi_albert(n, mean_degree)}
k1 = {name: sum(len(a) for a in adj) / n for name, adj in networks.items()}
k2 = {name: sum(len(a) ** 2 for a in adj) / n for name, adj in networks.items()}

rows = []
for idx, beta in enumerate(betas):
    row = [beta]
    for name in ("er", "ba"):
        finals, peaks = [], []
        for _ in range(replicates):
            f, p = outbreak(networks[name], beta)
            finals.append(f)
            peaks.append(p)
        m, lo, hi = sim.mean_ci(finals)
        row += [m, lo, hi, sum(peaks) / len(peaks)]
    rows.append(row)
    sim.progress((idx + 1) / len(betas) * 0.95, f"beta={beta}")
sim.save_table("outbreak", ["beta", "final_er", "final_er_lo", "final_er_hi", "peak_er",
                            "final_ba", "final_ba_lo", "final_ba_hi", "peak_ba"], rows)


def threshold(col):
    for r in rows:
        if r[col] >= 0.1:
            return r[0]
    return None


# heterogeneous mean-field threshold for SIR: T_c = <k> / (<k^2> - <k>), transmissibility T = beta / (beta + gamma - beta*gamma)
def beta_c(name):
    tc = k1[name] / (k2[name] - k1[name])
    return tc * gamma / (1 - tc + tc * gamma)


sim.metric("threshold_beta_er", threshold(1), "smallest beta with a mean final size >= 10% (random network)")
sim.metric("threshold_beta_ba", threshold(5), "smallest beta with a mean final size >= 10% (scale-free network)")
sim.metric("theory_beta_c_er", round(beta_c("er"), 4), "heterogeneous mean-field threshold (random network)")
sim.metric("theory_beta_c_ba", round(beta_c("ba"), 4), "heterogeneous mean-field threshold (scale-free network)")
sim.metric("final_size_er_max_beta", round(rows[-1][1], 3), "final outbreak size at the largest beta (random)")
sim.metric("final_size_ba_max_beta", round(rows[-1][5], 3), "final outbreak size at the largest beta (scale-free)")
sim.figure("fig_outbreak", "outbreak", "beta", ["final_er", "final_ba"], lower=["final_er_lo", "final_ba_lo"],
           upper=["final_er_hi", "final_ba_hi"], labels=["random (ER)", "scale-free (BA)"],
           xlabel="Transmission probability per contact $\\beta$", ylabel="Final outbreak size (share of nodes)",
           caption=f"Final size of SIR outbreaks ($\\gamma={gamma}$, $N={n}$, $\\langle k\\rangle\\approx{mean_degree}$; "
                   f"mean and 95\\% CI over {replicates} runs).")
sim.figure("fig_peak", "outbreak", "beta", ["peak_er", "peak_ba"], labels=["random (ER)", "scale-free (BA)"],
           xlabel="Transmission probability per contact $\\beta$", ylabel="Peak share of active spreaders",
           caption="Peak prevalence during the outbreak.")
t_er, t_ba = threshold(1), threshold(5)
sim.finding(f"Outbreaks exceed 10% of the population from beta={t_er} on the random network and from "
            f"beta={t_ba} on the scale-free network.")
sim.finding(f"Heterogeneous mean-field theory predicts thresholds of {beta_c('er'):.3f} (random) and "
            f"{beta_c('ba'):.3f} (scale-free).")
sim.finish(summary="SIR contagion: scale-free contact networks spread at lower transmissibility.")
