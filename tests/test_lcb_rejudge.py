"""Checkers of tools/lcb_rejudge.py (abc397_d, arc195_c) on hand-made cases.

  python tests/test_lcb_rejudge.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from lcb_rejudge import check_cubes, check_pieces, cubes_exists  # noqa: E402

# abc397_d: 397 = 12^3 - 11^3; 27 has no positive solution, so the reference "3 0" of test 41 is wrong and -1 is right
assert cubes_exists(397) and check_cubes("397\n", "12 11\n", "")
assert not check_cubes("397\n", "-1\n", "") and not check_cubes("397\n", "12 10\n", "")
assert not cubes_exists(27) and check_cubes("27\n", "-1\n", "3 0\n") and not check_cubes("27\n", "3 0\n", "3 0\n")
# arc195_c: one red + one blue can't form a cycle; two reds side by side can, in any valid placement
assert check_pieces("1\n1 1\n", "No\n", "No\n") and not check_pieces("1\n1 1\n", "Yes\nR 1 1\nB 2 2\n", "No\n")
assert check_pieces("1\n2 0\n", "Yes\nR 5 5\nR 5 6\n", "Yes\nR 1 1\nR 1 2\n")
assert not check_pieces("1\n2 0\n", "Yes\nR 5 5\nR 6 6\n", "Yes\nR 1 1\nR 1 2\n")
assert not check_pieces("1\n2 0\n", "Yes\nR 5 5\nR 5 5\n", "Yes\nR 1 1\nR 1 2\n")
print("ok")
