"""Minimal Naming Game (Baronchelli et al. 2006) on a complete graph vs a small-world network.

Each interaction: a random speaker utters a word from its inventory (inventing one if the
inventory is empty) to a random neighbour. Success -> both keep only that word; failure ->
the hearer adds the word. We measure the time to global consensus and the peak number of
words in the population, sweeping the population size N.
"""

import random

import medusa_sim as sim

sizes = [int(n) for n in sim.param("sizes", [32, 64, 128, 256])]
replicates = int(sim.param("replicates", 5))
k = int(sim.param("sw_degree", 6))
p_rewire = float(sim.param("sw_rewire", 0.1))
series_n = int(sim.param("series_n", sizes[-1]))
max_steps_factor = int(sim.param("max_steps_factor", 400))
sim.seed(sim.param("seed", 20260921))


def small_world(n, degree, p, rng):
    """Watts-Strogatz ring lattice (degree even) with rewiring probability p."""
    half = max(1, degree // 2)
    adj = [set() for _ in range(n)]
    for i in range(n):
        for d in range(1, half + 1):
            j = (i + d) % n
            adj[i].add(j)
            adj[j].add(i)
    for i in range(n):
        for d in range(1, half + 1):
            j = (i + d) % n
            if rng.random() < p and j in adj[i]:
                candidates = [c for c in range(n) if c != i and c not in adj[i]]
                if candidates:
                    new = rng.choice(candidates)
                    adj[i].discard(j)
                    adj[j].discard(i)
                    adj[i].add(new)
                    adj[new].add(i)
    return [sorted(a) for a in adj]


def run(n, topology, rng, record=False):
    neighbours = small_world(n, k, p_rewire, rng) if topology == "small_world" else None
    inventories = [set() for _ in range(n)]
    total_words = 0
    counts = {}  # word -> number of agents holding it
    next_word = 0
    peak_words = 0
    successes = []
    series = []
    window = max(50, n)
    step = 0
    max_steps = max_steps_factor * n * int(n ** 0.5 + 1)
    while step < max_steps:
        step += 1
        speaker = rng.randrange(n)
        if neighbours is None:
            hearer = rng.randrange(n - 1)
            if hearer >= speaker:
                hearer += 1
        else:
            hearer = rng.choice(neighbours[speaker])
        inv_s = inventories[speaker]
        if not inv_s:
            word = next_word
            next_word += 1
            inv_s.add(word)
            counts[word] = 1
            total_words += 1
        else:
            word = rng.choice(tuple(inv_s)) if len(inv_s) > 1 else next(iter(inv_s))
        inv_h = inventories[hearer]
        if word in inv_h:
            for agent_inv in (inv_s, inv_h):
                for w in agent_inv:
                    counts[w] -= 1
                    if counts[w] == 0:
                        del counts[w]
                total_words -= len(agent_inv)
                agent_inv.clear()
                agent_inv.add(word)
                counts[word] = counts.get(word, 0) + 1
                total_words += 1
            successes.append(1)
        else:
            inv_h.add(word)
            counts[word] = counts.get(word, 0) + 1
            total_words += 1
            successes.append(0)
        if total_words > peak_words:
            peak_words = total_words
        if record and step % max(1, n // 4) == 0:
            recent = successes[-window:]
            series.append((step / n, sum(recent) / len(recent)))
        if len(counts) == 1 and total_words == n:
            break
    converged = len(counts) == 1 and total_words == n
    return step, peak_words, converged, series


rng = random.Random(sim.param("seed", 20260921))
rows = []
fits = {}
total_jobs = len(sizes) * 2
done = 0
for topology in ("complete", "small_world"):
    xs, ys, peaks = [], [], []
    for n in sizes:
        times, peak_list, conv = [], [], 0
        for _ in range(replicates):
            t, peak, converged, _series = run(n, topology, rng)
            times.append(t / n)  # time per agent ("sweeps")
            peak_list.append(peak / n)
            conv += int(converged)
        m, lo, hi = sim.mean_ci(times)
        pm, plo, phi = sim.mean_ci(peak_list)
        rows.append([n, topology == "small_world", m, lo, hi, pm, plo, phi, conv / replicates])
        xs.append(n)
        ys.append(m * n)
        peaks.append(pm * n)
        done += 1
        sim.progress(done / total_jobs * 0.85, f"{topology} N={n}")
    c, alpha, r2 = sim.loglog_fit(xs, ys)
    c2, beta, r2b = sim.loglog_fit(xs, peaks)
    fits[topology] = (alpha, r2, beta, r2b)

# reshape into one table with a column per topology (pgfplots-friendly)
by_n = {}
for n, sw, m, lo, hi, pm, plo, phi, conv in rows:
    key = "sw" if sw else "mf"
    by_n.setdefault(n, {})[key] = (m, lo, hi, pm, plo, phi, conv)
table = []
for n in sizes:
    mf, sw = by_n[n]["mf"], by_n[n]["sw"]
    table.append([n, mf[0], mf[1], mf[2], sw[0], sw[1], sw[2], mf[3], sw[3], mf[6], sw[6]])
sim.save_table("convergence", ["N", "t_mf", "t_mf_lo", "t_mf_hi", "t_sw", "t_sw_lo", "t_sw_hi",
                               "peak_mf", "peak_sw", "conv_mf", "conv_sw"], table)

series_rows = []
_, _, _, s_mf = run(series_n, "complete", rng, record=True)
_, _, _, s_sw = run(series_n, "small_world", rng, record=True)
length = min(len(s_mf), len(s_sw))
step_keep = max(1, length // 120)
for i in range(0, length, step_keep):
    series_rows.append([s_mf[i][0], s_mf[i][1], s_sw[i][1]])
sim.save_table("success", ["t", "success_mf", "success_sw"], series_rows)

alpha_mf, r2_mf, beta_mf, _ = fits["complete"]
alpha_sw, r2_sw, beta_sw, _ = fits["small_world"]
sim.metric("alpha_complete", round(alpha_mf, 3), "exponent of convergence time t_conv ~ N^alpha (complete graph)")
sim.metric("alpha_small_world", round(alpha_sw, 3), "exponent of t_conv ~ N^alpha (small-world network)")
sim.metric("r2_complete", round(r2_mf, 3), "R^2 of the log-log fit (complete graph)")
sim.metric("peak_exponent_complete", round(beta_mf, 3), "exponent of peak memory N_w^max ~ N^beta")
sim.metric("peak_exponent_small_world", round(beta_sw, 3), "exponent of peak memory (small-world)")
last = table[-1]
sim.metric("t_per_agent_complete_maxN", round(last[1], 2), "convergence time per agent at the largest N")
sim.metric("t_per_agent_small_world_maxN", round(last[4], 2), "convergence time per agent at the largest N (SW)")
sim.metric("consensus_rate", round(min(min(r[9], r[10]) for r in table), 3), "fraction of runs that reached consensus")

sim.figure("fig_convergence", "convergence", "N", ["t_mf", "t_sw"], lower=["t_mf_lo", "t_sw_lo"],
           upper=["t_mf_hi", "t_sw_hi"], labels=["complete graph", "small-world"],
           xlabel="Population size $N$", ylabel="Convergence time per agent $t_{conv}/N$", logx=True, logy=True,
           caption="Time to lexical consensus per agent versus population size (mean and 95\\% CI over "
                   f"{replicates} runs).")
sim.figure("fig_success", "success", "t", ["success_mf", "success_sw"], labels=["complete graph", "small-world"],
           xlabel="Interactions per agent", ylabel="Communicative success rate",
           caption=f"Success rate of interactions over time for $N={series_n}$ (sliding window).")
sim.finding(f"On the complete graph, convergence time grows as N^{alpha_mf:.2f} (R^2={r2_mf:.2f}); "
            "the mean-field prediction is N^1.5.")
sim.finding(f"On the small-world network the fitted exponent is {alpha_sw:.2f}, and the peak memory grows as "
            f"N^{beta_sw:.2f} versus N^{beta_mf:.2f} on the complete graph.")
sim.finding(f"At N={sizes[-1]}, consensus took {last[1]:.1f} interactions per agent on the complete graph and "
            f"{last[4]:.1f} on the small-world network.")
sim.finish(summary=f"Naming game: t_conv ~ N^{alpha_mf:.2f} (complete) vs N^{alpha_sw:.2f} (small-world).")
