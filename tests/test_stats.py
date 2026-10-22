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


def test_cluster_bootstrap_is_deterministic_and_checks_lengths():
    a, b, g = [0.9, 0.8, 0.7, 0.6], [0.5, 0.5, 0.5, 0.5], ["x", "x", "y", "y"]
    r1 = stats.cluster_paired_bootstrap(a, b, g, iters=500, seed=5)
    assert r1 == stats.cluster_paired_bootstrap(a, b, g, iters=500, seed=5)
    assert r1["n_groups"] == 2 and r1["mean_diff"] == pytest.approx(0.25)
    with pytest.raises(ValueError):
        stats.cluster_paired_bootstrap(a, b, ["x"], iters=10)


def test_cluster_bootstrap_widens_when_one_group_drives_the_gap():
    # nine groups with no difference, one group with a huge difference:
    # page-level resampling calls it significant, group-level resampling does not
    groups = [f"t{i}" for i in range(10) for _ in range(4)]
    a = [0.9] * 40
    b = [0.9] * 36 + [0.1] * 4
    page = stats.paired_bootstrap(a, b, iters=4000)
    clus = stats.cluster_paired_bootstrap(a, b, groups, iters=4000)
    assert page["significant"]
    assert not clus["significant"] and clus["lo"] <= 0
    assert (clus["hi"] - clus["lo"]) > (page["hi"] - page["lo"])
