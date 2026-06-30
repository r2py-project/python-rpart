from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd



def roc_rpart(object: dict, plot_ok: bool = True, x_orient: int = 1) -> pd.DataFrame:
    if object.get('_rpart_class') != 'rpart' or object.get('method') != 'class' or len(object.get('_ylevels', [])) != 2:
        raise ValueError('Not legitimate "rpart" tree and endpoint not a 2 level-factor')

    frame = object['frame']
    # R's roc.rpart.R reads object$frame$splits/object$frame$yprob, but
    # neither is ever a *column* of frame (frame only carries 'yval2'; the
    # per-class probabilities live inside it, see rpart.py's
    # frame['yval2'] = hstack([yval2, yprob, nodeprob])). Reading a missing
    # column off frame is a no-op in R ($ on an absent name returns NULL,
    # and NULL[,1] is again NULL), so in real R this function silently
    # always operates on zero rows for every tree -- not a usable
    # implementation. We instead wire 'truth'/leaf-probabilities from the
    # yval2 block actually produced by rpart(), the equivalent data under
    # the current (post rpart.R rewrite) frame schema this function's
    # variable names (tpcp/tncp/tpcn/tncn) were clearly written against.
    endnodes = (frame['var'] == '<leaf>').to_numpy()
    yval2 = np.array(frame['yval2'].tolist(), dtype=float)
    nclass = (yval2.shape[1] - 2) // 2
    counts = yval2[:, 1:1 + nclass]            # per-node class counts
    yprob_all = yval2[:, 1 + nclass:1 + 2 * nclass]  # per-node class probabilities

    truth = counts[endnodes]
    leaf_probs = yprob_all[endnodes, 1]

    cutoffs = np.sort(np.unique(np.concatenate([[0.0], [1.0], leaf_probs])))
    pred_np = cutoffs[:, None] >= leaf_probs[None, :]

    last_r = pred_np.shape[0]
    last_c = pred_np.shape[1]
    if np.sum(pred_np[0, :]) > 0:
        pred_np = np.vstack([np.zeros((1, last_c), dtype=bool), pred_np])
        cutoffs = np.concatenate([[np.nan], cutoffs])

    last_r = pred_np.shape[0]
    last_c = pred_np.shape[1]
    if np.sum(pred_np[last_r - 1, :]) < last_c:
        pred_np = np.vstack([pred_np, np.ones((1, last_c), dtype=bool)])
        cutoffs = np.concatenate([cutoffs, [np.nan]])

    cutoff_n = len(cutoffs)
    sensitivity = np.zeros(cutoff_n)
    specificity = np.zeros(cutoff_n)
    negpred = np.zeros(cutoff_n)
    pospred = np.zeros(cutoff_n)
    tpcp = np.zeros(cutoff_n)
    tncp = np.zeros(cutoff_n)
    tpcn = np.zeros(cutoff_n)
    tncn = np.zeros(cutoff_n)

    for i in range(cutoff_n):
        mask = pred_np[i, :]
        ss_table = np.zeros((2, 2))
        ss_table[0, 0] = np.sum(truth[mask, 0])
        ss_table[1, 0] = np.sum(truth[~mask, 0])
        ss_table[0, 1] = np.sum(truth[mask, 1])
        ss_table[1, 1] = np.sum(truth[~mask, 1])

        sensitivity[i] = ss_table[1, 1] / (ss_table[1, 1] + ss_table[0, 1])
        specificity[i] = ss_table[0, 0] / (ss_table[0, 0] + ss_table[1, 0])
        negpred[i] = ss_table[0, 0] / (ss_table[0, 0] + ss_table[0, 1])
        pospred[i] = ss_table[1, 1] / (ss_table[1, 1] + ss_table[1, 0])
        tpcp[i] = ss_table[1, 1]
        tncp[i] = ss_table[1, 0]
        tpcn[i] = ss_table[0, 1]
        tncn[i] = ss_table[0, 0]

    if plot_ok:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 6))
        if x_orient == 1:
            ax.plot(1 - specificity, sensitivity, 'o-')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_ylabel('Sensitivity')
            ax.set_xlabel('1-Specificity')
        if x_orient == 2:
            ax.plot(specificity, sensitivity, 'o-')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_ylabel('Sensitivity')
            ax.set_xlabel('Specificity')
        ax.set_aspect('equal')
        plt.show()

    cutoffs_fmt = [f'{v:.3f}' if not np.isnan(v) else 'NA' for v in cutoffs]
    sensitivity_fmt = [f'{v:.2f}' if not np.isnan(v) else 'NA' for v in np.round(sensitivity, 2)]
    specificity_fmt = [f'{v:.2f}' if not np.isnan(v) else 'NA' for v in np.round(specificity, 2)]
    pospred_fmt = [f'{v:.2f}' if not np.isnan(v) else 'NA' for v in np.round(pospred, 2)]
    negpred_fmt = [f'{v:.2f}' if not np.isnan(v) else 'NA' for v in np.round(negpred, 2)]

    return pd.DataFrame({
        'cutoffs': cutoffs_fmt,
        'tpcp': tpcp,
        'tncp': tncp,
        'tpcn': tpcn,
        'tncn': tncn,
        'sensitivity': sensitivity_fmt,
        'specificity': specificity_fmt,
        'pospred': pospred_fmt,
        'negpred': negpred_fmt,
    })


def ss_compare(a: np.ndarray[Any, np.dtype[np.bool_]] | np.ndarray[Any, np.dtype[np.float64]] | float, b: np.ndarray[Any, np.dtype[np.bool_]] | np.ndarray[Any, np.dtype[np.float64]] | float) -> np.ndarray[Any, np.dtype[np.bool_]] | bool:
    return a >= b
