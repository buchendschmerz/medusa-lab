"""Spatial Prisoner's Dilemma (Nowak & May 1992) on a periodic lattice.

Every site plays the weak PD (R=1, T=b, S=P=0) with its 8 neighbours and itself, then copies
the strategy of the best-scoring site in its neighbourhood (synchronous, deterministic update).
We sweep the temptation b and record the long-run share of cooperators, compared with a
well-mixed population where defection always wins.
"""

import random

import medusa_sim as sim

size = int(sim.param("lattice", 30))
generations = int(sim.param("generations", 60))
burn_in = int(sim.param("burn_in", 30))
temptations = [float(b) for b in sim.param("temptations", [1.05, 1.15, 1.25, 1.35, 1.45, 1.55, 1.65, 1.75, 1.85, 1.95, 2.05])]
replicates = int(sim.param("replicates", 3))
initial_defectors = float(sim.param("initial_defectors", 0.1))
sim.seed(sim.param("seed", 20260925))
rng = random.Random(sim.param("seed", 20260925))

offsets = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
neigh = [[((x + dx) % size) * size + (y + dy) % size for dx, dy in offsets]
         for x in range(size) for y in range(size)]
cells = size * size


def run(b):
    coop = [0 if rng.random() < initial_defectors else 1 for _ in range(cells)]
    shares = []
    for g in range(generations):
        payoff = [0.0] * cells
        for i in range(cells):
            c_neighbours = sum(coop[j] for j in neigh[i])
            payoff[i] = c_neighbours * (1.0 if coop[i] else b)
        new = coop[:]
        for i in range(cells):
            best = i
            best_pay = payoff[i]
            for j in neigh[i]:
                if payoff[j] > best_pay:
                    best, best_pay = j, payoff[j]
            new[i] = coop[best]
        coop = new
        if g >= burn_in:
            shares.append(sum(coop) / cells)
    return sum(shares) / len(shares)


rows = []
for idx, b in enumerate(temptations):
    vals = [run(b) for _ in range(replicates)]
    m, lo, hi = sim.mean_ci(vals)
    rows.append([b, m, lo, hi, 0.0])
    sim.progress((idx + 1) / len(temptations) * 0.95, f"b={b}")
sim.save_table("cooperation", ["b", "coop", "coop_lo", "coop_hi", "well_mixed"], rows)

collapse = next((r[0] for r in rows if r[1] < 0.05), None)
sim.metric("cooperation_at_min_b", round(rows[0][1], 3), f"share of cooperators at b={temptations[0]}")
sim.metric("cooperation_at_max_b", round(rows[-1][1], 3), f"share of cooperators at b={temptations[-1]}")
sim.metric("collapse_b", collapse, "smallest temptation where cooperation drops below 5%")
mid = [r[1] for r in rows if 1.8 <= r[0] <= 2.0]
sim.metric("cooperation_chaotic_regime", round(sum(mid) / len(mid), 3) if mid else None,
           "mean cooperation for 1.8 <= b <= 2.0 (spatial chaos regime)")
sim.figure("fig_cooperation", "cooperation", "b", ["coop", "well_mixed"], lower=["coop_lo"], upper=["coop_hi"],
           labels=["spatial lattice", "well-mixed baseline"], xlabel="Temptation to defect $b$",
           ylabel="Share of cooperators",
           caption=f"Long-run cooperation on a {size}x{size} lattice after {generations} generations "
                   f"(mean and 95\\% CI over {replicates} runs).")
sim.finding(f"Spatial structure sustains {rows[0][1]:.0%} cooperation at b={temptations[0]} although defection "
            "dominates in a well-mixed population.")
if collapse is not None:
    sim.finding(f"Cooperation collapses below 5% once b >= {collapse}.")
if mid:
    sim.finding(f"In the 1.8 <= b <= 2.0 regime cooperators persist at about {sum(mid) / len(mid):.0%} "
                "in shifting spatial clusters.")
sim.finish(summary="Spatial PD: local interactions let cooperators survive moderate temptation.")
