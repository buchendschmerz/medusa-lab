"""Schelling's segregation model on a periodic grid.

Two groups and a few empty cells. An agent is unhappy if the share of like neighbours among its
occupied Moore neighbours is below the tolerance threshold tau; unhappy agents relocate to a
random empty cell. We sweep tau and record the resulting segregation (mean like-neighbour share).
"""

import random

import medusa_sim as sim

size = int(sim.param("grid", 30))
empty_share = float(sim.param("empty_share", 0.1))
thresholds = [float(t) for t in sim.param("thresholds", [0.1, 0.2, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8])]
max_sweeps = int(sim.param("max_sweeps", 60))
replicates = int(sim.param("replicates", 4))
sim.seed(sim.param("seed", 20260926))
rng = random.Random(sim.param("seed", 20260926))

cells = size * size
neigh = [[((x + dx) % size) * size + (y + dy) % size for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
         for x in range(size) for y in range(size)]


def like_share(grid, i):
    me = grid[i]
    same = other = 0
    for j in neigh[i]:
        g = grid[j]
        if g == me:
            same += 1
        elif g:
            other += 1
    total = same + other
    return same / total if total else 1.0


def run(tau):
    n_empty = int(cells * empty_share)
    agents = cells - n_empty
    grid = [1] * (agents // 2) + [2] * (agents - agents // 2) + [0] * n_empty
    rng.shuffle(grid)
    empties = [i for i, g in enumerate(grid) if g == 0]
    moves_last = 0
    sweeps = 0
    for sweep_no in range(1, max_sweeps + 1):
        sweeps = sweep_no
        unhappy = [i for i in range(cells) if grid[i] and like_share(grid, i) < tau]
        if not unhappy:
            break
        rng.shuffle(unhappy)
        moves_last = 0
        for i in unhappy:
            if not grid[i] or like_share(grid, i) >= tau:
                continue
            k = rng.randrange(len(empties))
            j = empties[k]
            grid[j], grid[i] = grid[i], 0
            empties[k] = i
            moves_last += 1
    seg = [like_share(grid, i) for i in range(cells) if grid[i]]
    unhappy_share = sum(1 for i in range(cells) if grid[i] and like_share(grid, i) < tau) / agents
    return sum(seg) / len(seg), unhappy_share, sweeps


rows = []
for idx, tau in enumerate(thresholds):
    segs, unhappy, sweeps = [], [], []
    for _ in range(replicates):
        s, u, sw = run(tau)
        segs.append(s)
        unhappy.append(u)
        sweeps.append(sw)
    m, lo, hi = sim.mean_ci(segs)
    um, ulo, uhi = sim.mean_ci(unhappy)
    rows.append([tau, m, lo, hi, um, ulo, uhi, sum(sweeps) / len(sweeps), 0.5])
    sim.progress((idx + 1) / len(thresholds) * 0.95, f"tau={tau}")
sim.save_table("segregation", ["tau", "segregation", "seg_lo", "seg_hi", "unhappy", "unhappy_lo", "unhappy_hi",
                               "sweeps", "random_mix"], rows)

amplification = [(r[0], r[1]) for r in rows if r[0] >= 0.3]
first_high = next((t for t, s in amplification if s >= 0.7), None)
frozen = next((r[0] for r in rows if r[4] > 0.2), None)
sim.metric("segregation_at_tau_0_3", next((round(r[1], 3) for r in rows if abs(r[0] - 0.3) < 1e-9), None),
           "mean like-neighbour share when agents only want 30% like neighbours")
sim.metric("tau_first_strong_segregation", first_high, "smallest tau >= 0.3 with like-neighbour share >= 0.7")
sim.metric("tau_persistent_dissatisfaction", frozen, "smallest tau where > 20% of agents remain unhappy")
sim.metric("segregation_max", round(max(r[1] for r in rows), 3), "maximum mean like-neighbour share")
sim.figure("fig_segregation", "segregation", "tau", ["segregation", "random_mix"], lower=["seg_lo"], upper=["seg_hi"],
           labels=["after relocation", "random mixing"], xlabel="Tolerance threshold $\\tau$ (wanted like share)",
           ylabel="Mean like-neighbour share",
           caption=f"Segregation emerging from mild individual preferences ({size}x{size} grid, mean and "
                   f"95\\% CI over {replicates} runs).")
sim.figure("fig_unhappy", "segregation", "tau", ["unhappy"], lower=["unhappy_lo"], upper=["unhappy_hi"],
           labels=["unhappy agents"], xlabel="Tolerance threshold $\\tau$", ylabel="Share of unhappy agents",
           caption="Share of agents still unsatisfied at the end of the run.")
at03 = next((r[1] for r in rows if abs(r[0] - 0.3) < 1e-9), rows[0][1])
sim.finding(f"Agents who only require 30% like neighbours end up with {at03:.0%} like neighbours on average "
            "(random mixing gives 50%).")
if frozen is not None:
    sim.finding(f"For tau >= {frozen} a sizeable share of agents never settles, so the city keeps churning.")
sim.finish(summary="Schelling: mild preferences produce strong macro-level segregation.")
