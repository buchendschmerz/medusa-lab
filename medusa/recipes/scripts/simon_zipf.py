"""Simon's model of word-frequency growth (rich-get-richer) and Zipf's law.

A text grows one token at a time: with probability alpha a brand-new word is coined; otherwise a
previous token is copied uniformly at random (so frequent words are reused proportionally to their
frequency). The rank-frequency distribution follows a power law f(r) ~ r^(-z) with z = 1 - alpha.
"""

import random

import medusa_sim as sim

tokens = int(sim.param("tokens", 60000))
alphas = [float(a) for a in sim.param("alphas", [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4])]
replicates = int(sim.param("replicates", 4))
fit_ranks = int(sim.param("fit_max_rank", 200))
sim.seed(sim.param("seed", 20260927))
rng = random.Random(sim.param("seed", 20260927))


def run(alpha):
    text = [0]
    freq = [1]
    for _ in range(tokens - 1):
        if rng.random() < alpha:
            word = len(freq)
            freq.append(1)
        else:
            word = text[rng.randrange(len(text))]
            freq[word] += 1
        text.append(word)
    ranked = sorted(freq, reverse=True)
    top = ranked[:fit_ranks]
    _c, slope, r2 = sim.loglog_fit(range(1, len(top) + 1), top)
    return -slope, r2, len(freq), ranked


rows = []
example = None
for idx, alpha in enumerate(alphas):
    zs, r2s, vocab = [], [], []
    for _ in range(replicates):
        z, r2, v, ranked = run(alpha)
        zs.append(z)
        r2s.append(r2)
        vocab.append(v)
        if example is None and abs(alpha - 0.1) < 1e-9:
            example = ranked
    m, lo, hi = sim.mean_ci(zs)
    rows.append([alpha, m, lo, hi, 1 - alpha, sum(r2s) / len(r2s), sum(vocab) / len(vocab)])
    sim.progress((idx + 1) / len(alphas) * 0.9, f"alpha={alpha}")
sim.save_table("zipf", ["alpha", "z", "z_lo", "z_hi", "z_theory", "r2", "vocabulary"], rows)

if example is None:
    example = run(alphas[0])[3]
rank_rows = []
r = 1
while r <= len(example):
    rank_rows.append([r, example[r - 1]])
    r = max(r + 1, int(r * 1.3))
sim.save_table("rank_frequency", ["rank", "frequency"], rank_rows)

errors = [abs(row[1] - row[4]) for row in rows]
sim.metric("mean_abs_error_z", round(sum(errors) / len(errors), 3), "|fitted Zipf exponent - (1 - alpha)| averaged")
sim.metric("z_at_min_alpha", round(rows[0][1], 3), f"fitted Zipf exponent at alpha={alphas[0]}")
sim.metric("z_at_max_alpha", round(rows[-1][1], 3), f"fitted Zipf exponent at alpha={alphas[-1]}")
sim.metric("mean_fit_r2", round(sum(r[5] for r in rows) / len(rows), 3), "mean R^2 of the log-log rank fits")
sim.figure("fig_zipf", "zipf", "alpha", ["z", "z_theory"], lower=["z_lo"], upper=["z_hi"],
           labels=["fitted exponent", "theory 1 - alpha"], xlabel="Innovation rate $\\alpha$",
           ylabel="Zipf exponent $z$",
           caption=f"Zipf exponent of the top-{fit_ranks} ranks versus innovation rate "
                   f"({tokens} tokens, mean and 95\\% CI over {replicates} runs).")
sim.figure("fig_rank", "rank_frequency", "rank", ["frequency"], labels=["word frequency"], xlabel="Rank $r$",
           ylabel="Frequency $f(r)$", logx=True, logy=True,
           caption="Rank-frequency distribution of one simulated text (alpha = 0.1).")
sim.finding(f"The fitted Zipf exponent falls from {rows[0][1]:.2f} at alpha={alphas[0]} to {rows[-1][1]:.2f} at "
            f"alpha={alphas[-1]}, close to the theoretical 1 - alpha.")
sim.finding(f"The mean absolute deviation from theory is {sum(errors) / len(errors):.3f}.")
sim.finish(summary="Simon's model reproduces Zipf's law with exponent 1 - alpha.")
