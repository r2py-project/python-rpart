"""Positive-path parity tests for r2py_rpart.rpart vs. R's rpart::rpart.

Each test builds an identical dataset/argument combination in both R (via
rpy2) and Python, then asserts that the fitted `$frame` / `$cptable` /
`$splits` / `$where` / `variable.importance` components match numerically.
Cross-validation is always disabled (xval=0) so that comparisons are
deterministic (R's cross-validation folds use R's own RNG stream, which
does not -- and is not meant to -- match numpy's).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart

from _r_rpart_helpers import (
    CU_RELIABILITY_LEVELS,
    cu_summary_df,
    extract_r_fit,
    kyphosis_df,
    mtcars_df,
    r_control,
    r_dataframe_assign,
    r_fit_rpart,
    r_literal,
    run_r,
    stagec_df,
)


# ---------------------------------------------------------------------------
# 1. method="anova" via formula + data, default controls except xval=0
# ---------------------------------------------------------------------------

def test_rpart_anova_formula_data_matches_r_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control=r_control(xval=0))
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0})

    assert py_fit["method"] == "anova" == r_out["method"]
    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"], rtol=1e-6)
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"], rtol=1e-6)
    assert_allclose(py_fit["cptable"].to_numpy(), r_out["cptable"], rtol=1e-6)


# ---------------------------------------------------------------------------
# 2. method="class" (default method inference from a factor response)
# ---------------------------------------------------------------------------

def test_rpart_class_default_method_inference_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control=r_control(xval=0))
    r_out = extract_r_fit(r_fit)

    # method left unspecified in Python too: rpart() must infer "class"
    # from the categorical response, exactly like R does.
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})

    assert py_fit["method"] == "class" == r_out["method"]
    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"])
    assert py_fit["_ylevels"] == r_out["ylevels"]


# ---------------------------------------------------------------------------
# 3. parms: priors + information splitting index for method="class"
# ---------------------------------------------------------------------------

def test_rpart_class_with_custom_priors_and_information_split_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start",
        method='"class"',
        parms=r_literal({"prior": np.array([0.65, 0.35]), "split": "information"}),
        control=r_control(xval=0),
    )
    r_out = extract_r_fit(r_fit)

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start",
        data=df,
        method="class",
        parms={"prior": np.array([0.65, 0.35]), "split": "information"},
        control={"xval": 0},
    )

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"])
    assert_allclose(np.asarray(py_fit["parms"]["prior"], dtype=float), [0.65, 0.35])


# ---------------------------------------------------------------------------
# 4. parms: loss matrix for method="class"
# ---------------------------------------------------------------------------

def test_rpart_class_with_loss_matrix_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = run_r(
        'rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", '
        'parms=list(loss=matrix(c(0,2,1,0), nrow=2)), control=rpart.control(xval=0))'
    )
    r_out = extract_r_fit(r_fit)

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start",
        data=df,
        method="class",
        parms={"loss": np.array([[0.0, 1.0], [2.0, 0.0]])},
        control={"xval": 0},
    )

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 5. control: non-default cp (fewer splits kept)
# ---------------------------------------------------------------------------

def test_rpart_control_cp_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"', control=r_control(cp=0.05, xval=0))
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"cp": 0.05, "xval": 0})

    assert_allclose(py_fit["cptable"].to_numpy(), r_out["cptable"], rtol=1e-6)
    assert py_fit["frame"]["var"].tolist() == r_out["var"]


# ---------------------------------------------------------------------------
# 6. control kwargs passed directly to rpart() (not via control=) plus
#    a non-default maxdepth
# ---------------------------------------------------------------------------

def test_rpart_control_kwargs_passthrough_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"', minsplit=5, maxdepth=3, xval=0)
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", minsplit=5, maxdepth=3, xval=0)

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert py_fit["control"]["minsplit"] == 5
    assert py_fit["control"]["maxdepth"] == 3


# ---------------------------------------------------------------------------
# 7. cost vector (non-uniform variable costs)
# ---------------------------------------------------------------------------

def test_rpart_cost_vector_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", method='"class"', cost=r_literal([1.0, 2.0, 1.0]), control=r_control(xval=0)
    )
    r_out = extract_r_fit(r_fit)

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start",
        data=df,
        method="class",
        cost=np.array([1.0, 2.0, 1.0]),
        control={"xval": 0},
    )

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["splits"].to_numpy(), r_out["splits"], rtol=1e-6)


# ---------------------------------------------------------------------------
# 8. weights (case weights)
# ---------------------------------------------------------------------------

def test_rpart_weights_matches_r():
    rng = np.random.default_rng(0)
    n = 40
    df = pd.DataFrame({"x": rng.standard_normal(n)})
    df["y"] = df["x"] * 2 + rng.standard_normal(n) * 0.1
    weights = np.concatenate([np.ones(n // 2), np.full(n // 2, 3.0)])

    r_dataframe_assign("df", df)
    run_r(f"w <- c({', '.join(str(w) for w in weights)})")
    r_fit = run_r('rpart(y ~ x, data=df, weights=w, method="anova", control=rpart.control(xval=0, cp=0.001))')
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, weights=weights, method="anova", control={"xval": 0, "cp": 0.001})

    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"], rtol=1e-6)
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 9. subset (fit on a subset of rows only)
# ---------------------------------------------------------------------------

def test_rpart_subset_matches_r():
    rng = np.random.default_rng(1)
    n = 30
    df = pd.DataFrame({"x": rng.standard_normal(n)})
    df["y"] = df["x"] * 2 + rng.standard_normal(n) * 0.1
    subset = np.arange(5, 25)  # 0-based row positions

    r_dataframe_assign("df", df)
    run_r(f"subv <- c({', '.join(str(i + 1) for i in subset)})")  # R is 1-based
    r_fit = run_r('rpart(y ~ x, data=df, subset=subv, method="anova", control=rpart.control(xval=0))')
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, subset=subset, method="anova", control={"xval": 0})

    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"], rtol=1e-6)


# ---------------------------------------------------------------------------
# 10. ordered factor + multi-level unordered factor predictors, with NAs
#     handled by the default na.action (cu.summary is rpart's canonical
#     example dataset for this: Reliability is Ord.factor, Mileage/
#     Reliability contain NA).
# ---------------------------------------------------------------------------

def test_rpart_ordered_and_unordered_factor_predictors_with_na_matches_r():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    run_r(
        f'df$Reliability <- factor(df$Reliability, '
        f'levels=c({", ".join(repr(l) for l in CU_RELIABILITY_LEVELS)}), ordered=TRUE)'
    )
    run_r("df$Country <- factor(df$Country); df$Type <- factor(df$Type)")
    r_fit = r_fit_rpart(
        "Mileage ~ Price + Country + Reliability + Type", method='"anova"', control=r_control(xval=0)
    )
    r_out = extract_r_fit(r_fit)

    py_fit = rpart(
        "Mileage ~ Price + Country + Reliability + Type", data=df, method="anova", control={"xval": 0}
    )

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"], rtol=1e-6)


# ---------------------------------------------------------------------------
# 11. method="poisson" with a Surv()-style 2-column response (person-time,
#     event indicator), matching R's `rpart(Surv(pgtime, pgstat) ~ ...,
#     method="poisson")` idiom from the package's own treble.R test.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    m = df[predictors].copy()
    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv_response"] + predictors,
        "response": 1,
        "xlevels": {"ploidy": list(df["ploidy"].cat.categories)},
    }
    m.attrs["response"] = np.column_stack(
        [df["pgtime"].to_numpy(dtype=float), df["pgstat"].to_numpy(dtype=float)]
    )
    return m


def test_rpart_poisson_surv_response_matches_r():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r("df$ploidy <- factor(df$ploidy)")
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0))'
    )
    r_out = extract_r_fit(r_fit)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0},
    )

    assert py_fit["method"] == "poisson" == r_out["method"]
    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"], rtol=1e-5)


# ---------------------------------------------------------------------------
# 12. method="exp" with the same Surv()-style response.
# ---------------------------------------------------------------------------

def test_rpart_exp_surv_response_matches_r():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r("df$ploidy <- factor(df$ploidy)")
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="exp", control=rpart.control(xval=0, maxsurrogate=0, cp=0))'
    )
    r_out = extract_r_fit(r_fit)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="exp",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0},
    )

    assert py_fit["method"] == "exp" == r_out["method"]
    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 13. model=TRUE / x=TRUE / y=FALSE flags control which extra components
#     are attached to the returned object.
# ---------------------------------------------------------------------------

def test_rpart_model_x_y_flags_match_r_presence():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start",
        method='"class"',
        model="TRUE",
        x="TRUE",
        y="FALSE",
        control=r_control(xval=0),
    )
    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class", model=True, x=True, y=False, control={"xval": 0}
    )

    assert "model" in py_fit and isinstance(py_fit["model"], pd.DataFrame)
    assert "x" in py_fit
    assert "y" not in py_fit
    # Cross-check frame/var parity as a sanity anchor that this is still
    # the same fit as R's.
    r_out = extract_r_fit(r_fit)
    assert py_fit["frame"]["var"].tolist() == r_out["var"]


# ---------------------------------------------------------------------------
# 14. variable.importance is populated and matches R when splits exist.
# ---------------------------------------------------------------------------

def test_rpart_variable_importance_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl + qsec", control=r_control(xval=0, cp=0.001))
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl + qsec", data=df, method="anova", control={"xval": 0, "cp": 0.001})

    assert "variable.importance" in py_fit
    for name, value in r_out["variable_importance"].items():
        assert name in py_fit["variable.importance"]
        assert_allclose(py_fit["variable.importance"][name], value, rtol=1e-5)
