"""python3 -I tools/corpus/test_pooling.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pooling as P


def close(a, b):
    return abs(a - b) < 1e-9


# a part at the bar keeps itself entirely
assert P.weights([30, 100, 500]) == [1.0, 0.0, 0.0]
assert close(P.shrink([(40, 2.0), (100, 3.0), (500, 4.0)]), 2.0)
# under the bar: n / (n + 30), the rest split at the package the same way, the class takes what is left
w = P.weights([10, 30, 500])
assert close(w[0], 0.25) and close(w[1], 0.75) and close(w[2], 0.0)
w = P.weights([10, 10, 500])
assert close(w[0], 0.25) and close(w[1], 0.75 * 0.25) and close(w[2], 0.75 * 0.75)
assert close(sum(w), 1.0)
# held out: the part has weight 0, and with the package held out too the class has all of it
assert P.weights([0, 30, 500]) == [0.0, 1.0, 0.0]
assert P.weights([0, 0, 500]) == [0.0, 0.0, 1.0]
w = P.weights([0, 15, 500])
assert close(w[1], 1 / 3) and close(w[2], 2 / 3)
assert close(P.shrink([(0, 9.0), (15, 3.0), (500, 6.0)]), 5.0)
# an empty general level gives its weight to the last level with data
assert P.weights([5, 0, 0]) == [1.0, 0.0, 0.0]
assert close(sum(P.weights([3, 4, 0])), 1.0)
try:
    P.weights([0, 0, 0])
    raise SystemExit("no data must raise")
except ValueError:
    pass
# quantiles shrink level by level
q = P.pooled_quantiles([[], [1, 2, 3, 4, 5] * 6, [100] * 90])
assert close(q[0.5], 3.0)
q = P.pooled_quantiles([[], [2.0] * 15, [8.0] * 90])
assert close(q[0.5], 6.0)
# the floor: 5 rows and 3 repos
assert P.usable([(0, "a"), (0, "a"), (0, "b"), (0, "c"), (0, "c")])
assert not P.usable([(0, "a"), (0, "a"), (0, "b"), (0, "b"), (0, "b")])
assert not P.usable([(0, "a"), (0, "b"), (0, "c")])
print("ok")
