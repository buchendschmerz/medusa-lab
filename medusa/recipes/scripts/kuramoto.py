"""Kuramoto model of coupled oscillators (mean-field coupling).

d theta_i / dt = omega_i + K r sin(psi - theta_i), with natural frequencies omega_i ~ N(0, sigma^2).
We sweep the coupling K and measure the time-averaged order parameter r. For a Gaussian
frequency distribution the critical coupling is K_c = 2 / (pi g(0)) = sigma * sqrt(8 / pi).
"""

import math
import random

import medusa_sim as sim

n = int(sim.param("oscillators", 150))
sigma = float(sim.param("sigma", 1.0))
dt = float(sim.param("dt", 0.1))
steps = int(sim.param("steps", 1200))
couplings = [float(k) for k in sim.param("couplings", [0.0, 0.4, 0.8, 1.2, 1.4, 1.6, 1.8, 2.0, 2.4, 2.8, 3.2, 4.0])]
replicates = int(sim.param("replicates", 3))
sim.seed(sim.param("seed", 20260924))
rng = random.Random(sim.param("seed", 20260924))
k_c = sigma * math.sqrt(8 / math.pi)


def order_parameter(theta):
    c = sum(math.cos(t) for t in theta) / len(theta)
    s = sum(math.sin(t) for t in theta) / len(theta)
    return math.hypot(c, s), math.atan2(s, c)


def run(coupling):
    omega = [rng.gauss(0.0, sigma) for _ in range(n)]
    theta = [rng.uniform(-math.pi, math.pi) for _ in range(n)]
    samples = []
    for step in range(steps):
        r, psi = order_parameter(theta)
        kr = coupling * r
        theta = [t + dt * (w + kr * math.sin(psi - t)) for t, w in zip(theta, omega, strict=True)]
        if step >= steps // 2:
            samples.append(r)
    return sum(samples) / len(samples)


rows = []
for idx, coupling in enumerate(couplings):
    vals = [run(coupling) for _ in range(replicates)]
    m, lo, hi = sim.mean_ci(vals)
    # self-consistent mean-field prediction r = sqrt(1 - K_c/K) near onset (Lorentzian-exact, Gaussian-approx.)
    theory = math.sqrt(max(0.0, 1 - k_c / coupling)) if coupling > 0 else 0.0
    rows.append([coupling, m, lo, hi, theory])
    sim.progress((idx + 1) / len(couplings) * 0.95, f"K={coupling}")
sim.save_table("sync", ["K", "r", "r_lo", "r_hi", "r_theory"], rows)

onset = next((r[0] for r in rows if r[1] >= 0.3), None)
incoherent = [r[1] for r in rows if r[0] < 0.8 * k_c]
sim.metric("critical_coupling_theory", round(k_c, 3), "K_c = sigma * sqrt(8/pi) for Gaussian frequencies")
sim.metric("onset_coupling_sim", onset, "smallest K with mean order parameter r >= 0.3")
sim.metric("r_at_max_K", round(rows[-1][1], 3), "order parameter at the strongest coupling")
sim.metric("r_incoherent_mean", round(sum(incoherent) / len(incoherent), 3) if incoherent else None,
           "mean r well below K_c (finite-size noise floor ~ 1/sqrt(N))")
sim.figure("fig_sync", "sync", "K", ["r", "r_theory"], lower=["r_lo"], upper=["r_hi"],
           labels=["simulation", "mean-field sqrt(1 - K_c/K)"], xlabel="Coupling strength $K$",
           ylabel="Order parameter $r$",
           caption=f"Synchronisation transition for $N={n}$ oscillators, $\\sigma={sigma}$ "
                   f"(time-averaged $r$, mean and 95\\% CI over {replicates} runs).")
sim.finding(f"Below K_c = {k_c:.2f} the population stays incoherent (r close to the 1/sqrt(N) noise floor); "
            f"collective synchrony appears from K = {onset}.")
sim.finding(f"At K = {couplings[-1]} the order parameter reaches r = {rows[-1][1]:.2f}.")
sim.finish(summary=f"Kuramoto: synchronisation onset near K_c = {k_c:.2f}.")
