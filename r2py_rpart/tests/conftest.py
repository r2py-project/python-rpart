"""Test-session-wide setup.

Forces matplotlib's non-interactive "Agg" backend *before* anything else in
the test session can import `r2py_rpart.plotcp` (which itself does `import
matplotlib.pyplot as plt` at module load time) -- this keeps the plotcp
parity tests (test_plotcp_positive.py/test_plotcp_negative.py/
test_plotcp_edge.py) from trying to open a real GUI window/display in a
headless CI environment, regardless of whether a `$DISPLAY` happens to be
set on the machine running the tests.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
