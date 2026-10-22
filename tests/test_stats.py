import pytest

from extract_bench import stats


def test_bootstrap_is_deterministic_for_seed():
    x = [0.1, 0.5, 0.9, 0.3, 0.7]
    assert stats.bootstrap_ci(x, iters=500, seed=3) == stats.bootstrap_ci(x, iters=500, seed=3)


def test_bootstrap_changes_with_seed():
    x = [0.1, 0.5, 0.9, 0.3, 0.7, 0.2]
    a = stats.bootstrap_ci(x, iters=500, seed=1)
    b = stats.bootstrap_ci(x, iters=500, seed=2)
    assert (a["lo"], a["hi"]) != (b["lo"], b["hi"])


def test_bootstrap_ci_brackets_mean():
    ci = stats.bootstrap_ci([0.2, 0.4, 0.6, 0.8], iters=2000)
    assert ci["lo"] <= ci["mean"] <= ci["hi"]
    assert ci["mean"] == pytest.approx(0.5)


def test_bootstrap_constant_has_zero_width():
    ci = stats.bootstrap_ci([0.7] * 10, iters=200)
    assert ci["lo"] == pytest.approx(0.7) and ci["hi"] == pytest.approx(0.7)


def test_paired_identical_is_not_significant():
    a = [0.5, 0.6, 0.7, 0.8]
    r = stats.paired_bootstrap(a, a, iters=500)
    assert r["verdict"] == "not significantly different" and r["mean_diff"] == 0


def test_paired_clear_difference_is_significant():
    a = [0.9, 0.92, 0.88, 0.91, 0.95, 0.9, 0.93, 0.89]
    b = [x - 0.3 for x in a]
    r = stats.paired_bootstrap(a, b, iters=1000)
    assert r["significant"] and r["lo"] > 0 and r["mean_diff"] == pytest.approx(0.3)


def test_paired_noisy_small_difference_crosses_zero():
    a = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3]
    b = [0.1, 0.9, 0.2, 0.8, 0.3, 0.75]
    r = stats.paired_bootstrap(a, b, iters=2000)
    assert r["lo"] < 0 < r["hi"] and r["verdict"] == "not significantly different"


def test_paired_requires_same_length():
    with pytest.raises(ValueError):
        stats.paired_bootstrap([1, 2], [1])


def test_kappa_perfect_and_hand_computed():
    assert stats.cohen_kappa(["G", "B", "G"], ["G", "B", "G"]) == 1.0
    # po = 0.5; pa(G)=0.5 pb(G)=0.5 -> pe = 0.5 -> kappa 0
    assert stats.cohen_kappa(["G", "G", "B", "B"], ["G", "B", "G", "B"]) == pytest.approx(0.0)
    # po = 0.75, pe = (3*2 + 1*2)/16 = 0.5 -> kappa 0.5
    assert stats.cohen_kappa(["G", "G", "G", "B"], ["G", "G", "B", "B"]) == pytest.approx(0.5)


def test_kappa_rejects_bad_input():
    with pytest.raises(ValueError):
        stats.cohen_kappa([], [])
