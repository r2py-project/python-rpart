"""
r2py_rpart — Python bindings for the rpart decision-tree C library.

The rpart C sources (with fake R headers) are compiled into _rpart_core.so
which lives alongside this file.  cffi's dlopen() loads it at import time.

Five pure-C-ABI entry points are exposed:
  rpart_c            — fit a recursive partition tree
  pred_rpart_c       — predict node membership for new data
  xpred_c            — cross-validation predictions
  rpartexp2_c        — unique death-time selection (survival/exp method)
  init_rpcallback_c  — initialise user-defined split callbacks (method=4)

For standard use (method 1-3: anova, poisson/exp, class) only rpart_c,
pred_rpart_c, and xpred_c are needed.  init_rpcallback_c is required only
for method=4 (user-defined splits), which also needs the callback registration
functions register_eval_fn, register_install_fn, register_findVar_fn, and
register_findVarInFrame_fn (exported as weak symbols from _rpart_core.so).

All functions return void and signal errors via a caller-supplied char buffer
(error_out / error_out_len).  Python callers must check error_out after each
call and raise RuntimeError if it is non-empty.
"""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Any

import cffi
import numpy as np
from numpy import ndarray

__all__ = [
    # High-level Python functions (from converted R modules)
    "pred_rpart",
    "rpart",
    "compress",
    "descendants",
    "drate2",
    "formatg",
    "importance",
    "labels_rpart",
    "meanvar",
    "meanvar_rpart",
    "model_frame_rpart",
    "na_rpart",
    "node_match",
    "on_unload",
    "oval",
    "path_rpart",
    "plot_rpart",
    "plotcp",
    "post",
    "post_rpart",
    "predict_rpart",
    "print_rpart",
    "printcp",
    "prune",
    "prune_rpart",
    "rectangle",
    "residuals_rpart",
    "roc_rpart",
    "rpart_anova",
    "rpart_branch",
    "rpart_class",
    "rpart_control",
    "rpart_exp",
    "rpart_matrix",
    "rpart_poisson",
    "rpartcallback",
    "rpartco",
    "rsq_rpart",
    "snip_rpart",
    "snip_rpart_mouse",
    "ss_compare",
    "string_bounding_box",
    "summary_rpart",
    "text_rpart",
    "tfun",
    "tree_depth",
    "xpred_rpart",
]

# ---------------------------------------------------------------------------
# Library loading
# ---------------------------------------------------------------------------

ffi = cffi.FFI()

ffi.cdef("""
/* ---- rpart_c ----------------------------------------------------------- */
void rpart_c(
    int *ncat,        int ncat_len,
    int  method,
    double *opt,      int opt_len,
    double *parms,    int parms_len,
    int  xvals,
    int *xgrp,        int xgrp_len,
    double *ymat,     int ymat_len,
    double *xmat,     int xmat_nrow,  int xmat_ncol,
    double *wt,       int wt_len,
    int  ny,
    double *cost,     int cost_len,
    /* outputs: which */
    int *which_out,   int which_cap,  int *which_len_out,
    /* outputs: cptable */
    double *cptable_out,  int cptable_cap,
    int *cptable_nrow_out, int *cptable_ncol_out,
    /* outputs: dsplit */
    double *dsplit_out,   int dsplit_cap,  int *dsplit_nrow_out,
    /* outputs: isplit */
    int    *isplit_out,   int isplit_cap,  int *isplit_nrow_out,
    /* outputs: dnode */
    double *dnode_out,    int dnode_cap,
    int *dnode_nrow_out,  int *dnode_ncol_out,
    /* outputs: inode */
    int    *inode_out,    int inode_cap,   int *inode_nrow_out,
    /* outputs: csplit (conditional — present only when catcount > 0) */
    int    *csplit_out,   int csplit_cap,
    int *csplit_nrow_out, int *csplit_ncol_out, int *has_csplit,
    /* error propagation */
    char *error_out,  int error_out_len
);

/* ---- pred_rpart_c ------------------------------------------------------- */
void pred_rpart_c(
    int *dimx,        int dimx_len,
    int  nnode,
    int  nsplit,
    int *dimc,        int dimc_len,
    int *nnum,        int nnum_len,
    int *nodes2,      int nodes2_nrow,  int nodes2_ncol,
    int *vnum,        int vnum_len,
    double *split2,   int split2_nrow,  int split2_ncol,
    int *csplit2,     int csplit2_nrow, int csplit2_ncol,
    int *usesur,      int usesur_len,
    double *xdata2,   int xdata2_nrow,  int xdata2_ncol,
    int *xmiss2,      int xmiss2_nrow,  int xmiss2_ncol,
    int *where_out,   int where_len,
    char *error_out,  int error_out_len
);

/* ---- xpred_c ------------------------------------------------------------ */
void xpred_c(
    int *ncat,        int ncat_len,
    int  method,
    double *opt,      int opt_len,
    double *parms,    int parms_len,
    int  xvals,
    int *xgrp,        int xgrp_len,
    double *ymat,     int ymat_len,
    double *xmat,     int xmat_nrow,  int xmat_ncol,
    double *wt,       int wt_len,
    int  ny,
    double *cost,     int cost_len,
    int  all,
    double *cp,       int cp_len,
    double toprisk,
    int  nresp,
    double *predict_out,  int predict_len,
    char *error_out,  int error_out_len
);

/* ---- rpartexp2_c -------------------------------------------------------- */
void rpartexp2_c(
    double *dtimes,   int dtimes_len,
    double  eps,
    int    *keep_out, int keep_len,
    char   *error_out, int error_out_len
);

/* ---- init_rpcallback_c (method=4 only) ---------------------------------- */
void init_rpcallback_c(
    void  *rho_ptr,
    int    numy,
    int    numresp,
    void  *expr1_ptr,
    void  *expr2_ptr,
    char  *error_out,
    int    error_out_len
);

/* ---- Callback registration (method=4 only, weak symbols) ---------------- */
void register_eval_fn(void *fn);
void register_install_fn(void *fn);
void register_findVar_fn(void *fn);
void register_findVarInFrame_fn(void *fn);
void *get_R_UnboundValue(void);
""")


def _find_lib() -> str:
    if sys.platform == "win32":
        name = "_rpart_core.dll"
    elif sys.platform == "darwin":
        name = "_rpart_core.dylib"
    else:
        name = "_rpart_core.so"

    # First: alongside __file__ (normal installed layout)
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, name)
    if os.path.exists(path):
        return path

    # Fallback: when tests run from the source tree the source package is
    # imported instead of the installed one, so __file__ points into the source
    # directory where the .so was never placed.  Search all site-packages dirs.
    import sysconfig
    for scheme in ("platlib", "purelib"):
        site = sysconfig.get_path(scheme)
        if site:
            path = os.path.join(site, "r2py_rpart", name)
            if os.path.exists(path):
                return path

    raise RuntimeError(
        f"r2py_rpart: cannot find compiled library {name!r}. "
        "Run `pip install --no-build-isolation .` from r2py_rpart/ first."
    )


_lib = ffi.dlopen(_find_lib())

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ERR_BUF_SIZE = 2048


def _check_error(buf: Any) -> None:
    if isinstance(buf, np.ndarray):
        # numpy uint8 error buffer: split at first null byte
        msg = bytes(buf).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    else:
        msg = ffi.string(buf).decode("utf-8", errors="replace")
    if msg:
        raise RuntimeError(msg)


def _int32(arr: ndarray) -> ndarray:
    return np.ascontiguousarray(arr, dtype=np.int32)


def _float64(arr: ndarray) -> ndarray:
    return np.ascontiguousarray(arr, dtype=np.float64)


def _iptr(arr: ndarray):
    return ffi.cast("int *", arr.ctypes.data)


def _dptr(arr: ndarray):
    return ffi.cast("double *", arr.ctypes.data)


def _cptr(buf):
    return ffi.cast("char *", buf.ctypes.data)


# ---------------------------------------------------------------------------
# Internal C wrapper — rpart()
# ---------------------------------------------------------------------------

def _rpart_c(
    ncat: ndarray,
    method: int,
    opt: ndarray,
    parms: ndarray | None,
    xvals: int,
    xgrp: ndarray,
    ymat: ndarray,
    xmat: ndarray,
    wt: ndarray,
    ny: int,
    cost: ndarray,
) -> dict[str, Any]:
    """Fit a recursive partition tree.

    Parameters mirror the C-level rpart() call; see rpart_c.c for the full
    parameter contract.

    Parameters
    ----------
    ncat    : int32 array [nvar]      — category counts (0=continuous, >0=categorical)
    method  : int                     — 1=anova, 2=poisson/exp, 3=class, 4=user
    opt     : float64 array [8]       — rpart.control options (unlist(controls))
    parms   : float64 array or None   — split-function parameters; None → dummy 0.0
    xvals   : int                     — number of cross-validation folds
    xgrp    : int32 array [n]         — cross-validation group assignments
    ymat    : float64 array [n*ny]    — response matrix, row-major (= as.double(t(Y)))
    xmat    : float64 array [n, nvar] — predictor matrix, **column-major** (F-order)
    wt      : float64 array [n]       — case weights
    ny      : int                     — number of response columns (init$numy)
    cost    : float64 array [nvar]    — variable cost multipliers

    Returns
    -------
    dict with keys:
      which     : int32 [n]              — final node number per observation
      cptable   : float64 [nrow, ncol]   — complexity table (column-major)
      dsplit    : float64 [splitcount, 3]
      isplit    : int32  [splitcount, 3]
      dnode     : float64 [nodecount, 3+ny]
      inode     : int32  [nodecount, 6]
      csplit    : int32  [catcount, maxcat]  (only present when has_csplit=1)
    """
    ncat_a = _int32(ncat)
    opt_a  = _float64(opt)
    if parms is None or len(parms) == 0:
        parms_a = _float64(np.array([0.0]))
    else:
        parms_a = _float64(parms)
    xgrp_a = _int32(xgrp)
    ymat_a = _float64(ymat)
    n, nvar = int(xmat.shape[0]), int(xmat.shape[1])
    xmat_a = _float64(np.asfortranarray(xmat))   # column-major
    wt_a   = _float64(wt)
    cost_a = _float64(cost)

    # Pre-allocate output buffers (generous upper bounds)
    which_arr   = np.zeros(n,          dtype=np.int32)
    cptable_arr = np.zeros(5 * (n + 2), dtype=np.float64)
    dsplit_arr  = np.zeros(n * 3,      dtype=np.float64)
    isplit_arr  = np.zeros(n * 3,      dtype=np.int32)
    dnode_arr   = np.zeros(n * (3 + max(ny, 1)) * 2, dtype=np.float64)
    inode_arr   = np.zeros(n * 6 * 2, dtype=np.int32)
    csplit_arr  = np.zeros(n * nvar,   dtype=np.int32)
    err_buf     = np.zeros(_ERR_BUF_SIZE, dtype=np.uint8)

    which_len     = ffi.new("int *", 0)
    cptable_nr    = ffi.new("int *", 0)
    cptable_nc    = ffi.new("int *", 0)
    dsplit_nr     = ffi.new("int *", 0)
    isplit_nr     = ffi.new("int *", 0)
    dnode_nr      = ffi.new("int *", 0)
    dnode_nc      = ffi.new("int *", 0)
    inode_nr      = ffi.new("int *", 0)
    csplit_nr     = ffi.new("int *", 0)
    csplit_nc     = ffi.new("int *", 0)
    has_csplit    = ffi.new("int *", 0)

    _lib.rpart_c(
        _iptr(ncat_a),  len(ncat_a),
        int(method),
        _dptr(opt_a),   len(opt_a),
        _dptr(parms_a), len(parms_a),
        int(xvals),
        _iptr(xgrp_a),  len(xgrp_a),
        _dptr(ymat_a),  len(ymat_a),
        _dptr(xmat_a),  n, nvar,
        _dptr(wt_a),    len(wt_a),
        int(ny),
        _dptr(cost_a),  len(cost_a),
        _iptr(which_arr),   n,          which_len,
        _dptr(cptable_arr), len(cptable_arr), cptable_nr, cptable_nc,
        _dptr(dsplit_arr),  len(dsplit_arr),  dsplit_nr,
        _iptr(isplit_arr),  len(isplit_arr),  isplit_nr,
        _dptr(dnode_arr),   len(dnode_arr),   dnode_nr,   dnode_nc,
        _iptr(inode_arr),   len(inode_arr),   inode_nr,
        _iptr(csplit_arr),  len(csplit_arr),  csplit_nr,  csplit_nc, has_csplit,
        _cptr(err_buf), _ERR_BUF_SIZE,
    )
    _check_error(err_buf)

    nr_cp = cptable_nr[0];  nc_cp = cptable_nc[0]
    nr_ds = dsplit_nr[0];   nr_is = isplit_nr[0]
    nr_dn = dnode_nr[0];    nc_dn = dnode_nc[0]
    nr_in = inode_nr[0]

    result: dict[str, Any] = {
        "which":    which_arr[:which_len[0]].copy(),
        "cptable":  cptable_arr[:nr_cp * nc_cp].reshape(nr_cp, nc_cp, order="F").copy(),
        "dsplit":   dsplit_arr[:nr_ds * 3].reshape(nr_ds, 3, order="F").copy(),
        "isplit":   isplit_arr[:nr_is * 3].reshape(nr_is, 3, order="F").copy(),
        "dnode":    dnode_arr[:nr_dn * nc_dn].reshape(nr_dn, nc_dn, order="F").copy(),
        "inode":    inode_arr[:nr_in * 6].reshape(nr_in, 6, order="F").copy(),
    }
    if has_csplit[0]:
        nr_cs = csplit_nr[0];  nc_cs = csplit_nc[0]
        result["csplit"] = csplit_arr[:nr_cs * nc_cs].reshape(nr_cs, nc_cs, order="F").copy()
    return result


# ---------------------------------------------------------------------------
# Internal C wrapper — pred_rpart()
# ---------------------------------------------------------------------------

def _pred_rpart_c(
    dimx: ndarray,
    nnode: int,
    nsplit: int,
    dimc: ndarray,
    nnum: ndarray,
    nodes2: ndarray,
    vnum: ndarray,
    split2: ndarray,
    csplit2: ndarray,
    usesur: ndarray,
    xdata2: ndarray,
    xmiss2: ndarray,
) -> ndarray:
    """Predict node membership for new observations.

    All array parameters must follow the memory-layout conventions described in
    pred_rpart_c.c (column-major for 2-D arrays, as produced by R's storage).

    Parameters
    ----------
    dimx    : int32 [2]              — [nrow, ncol] of the predictor matrix
    nnode   : int                    — number of nodes in the tree
    nsplit  : int                    — number of split rows
    dimc    : int32 [2]              — [nrow, ncol] of csplit2 (zeros if absent)
    nnum    : int32 [nnode]          — node numbers (row.names of frame)
    nodes2  : int32 [nnode, 4]      — frame columns n/ncompete/nsurrogate/index, col-major
    vnum    : int32 [nsplit]         — variable number for each split
    split2  : float64 [nsplit, 4]   — split table, column-major
    csplit2 : int32  [dimc[0], dimc[1]] — categorical split table, col-major (may be empty)
    usesur  : int32 [1]             — usesurrogate level
    xdata2  : float64 [dimx[0], dimx[1]] — predictor data, column-major
    xmiss2  : int32  [dimx[0], dimx[1]] — NA indicator, column-major

    Returns
    -------
    where : int32 [n]  — node membership index (1-based) for each observation
    """
    dimx_a   = _int32(dimx)
    dimc_a   = _int32(dimc)
    nnum_a   = _int32(nnum)
    nodes2_a = _int32(np.asfortranarray(nodes2))
    vnum_a   = _int32(vnum)
    split2_a = _float64(np.asfortranarray(split2))
    csplit2_a = _int32(np.asfortranarray(csplit2) if csplit2.size else np.zeros((0, 0), dtype=np.int32))
    usesur_a = _int32(usesur)
    xdata2_a = _float64(np.asfortranarray(xdata2))
    xmiss2_a = _int32(np.asfortranarray(xmiss2))

    n_obs = int(dimx_a[0])
    where_out = np.zeros(n_obs, dtype=np.int32)
    err_buf   = np.zeros(_ERR_BUF_SIZE, dtype=np.uint8)

    _lib.pred_rpart_c(
        _iptr(dimx_a),    len(dimx_a),
        int(nnode),
        int(nsplit),
        _iptr(dimc_a),    len(dimc_a),
        _iptr(nnum_a),    len(nnum_a),
        _iptr(nodes2_a),  int(nodes2_a.shape[0]), int(nodes2_a.shape[1]),
        _iptr(vnum_a),    len(vnum_a),
        _dptr(split2_a),  int(split2_a.shape[0]), int(split2_a.shape[1]),
        _iptr(csplit2_a), int(csplit2_a.shape[0]), int(csplit2_a.shape[1]),
        _iptr(usesur_a),  len(usesur_a),
        _dptr(xdata2_a),  int(xdata2_a.shape[0]), int(xdata2_a.shape[1]),
        _iptr(xmiss2_a),  int(xmiss2_a.shape[0]), int(xmiss2_a.shape[1]),
        _iptr(where_out), n_obs,
        _cptr(err_buf),   _ERR_BUF_SIZE,
    )
    _check_error(err_buf)
    return where_out.copy()


# ---------------------------------------------------------------------------
# Internal C wrapper — xpred()
# ---------------------------------------------------------------------------

def _xpred_c(
    ncat: ndarray,
    method: int,
    opt: ndarray,
    parms: ndarray | None,
    xvals: int,
    xgrp: ndarray,
    ymat: ndarray,
    xmat: ndarray,
    wt: ndarray,
    ny: int,
    cost: ndarray,
    return_all: int,
    cp: ndarray,
    toprisk: float,
    numresp: int,
) -> ndarray:
    """Cross-validation predictions for rpart.

    Parameters mirror xpred_c.c.  Note that cp is **mutated in-place** by the
    C code; pass a copy if the caller needs to preserve the original values.

    Returns
    -------
    predict : float64 flat array of length n * len(cp) * nresp_out
              where nresp_out = numresp if return_all == 1 else 1.
              Reshape as described in xpred_c.c's caller pattern comment.
    """
    ncat_a  = _int32(ncat)
    opt_a   = _float64(opt)
    if parms is None or len(parms) == 0:
        parms_a = _float64(np.array([0.0]))
    else:
        parms_a = _float64(parms)
    xgrp_a  = _int32(xgrp)
    ymat_a  = _float64(ymat)
    n, nvar = int(xmat.shape[0]), int(xmat.shape[1])
    xmat_a  = _float64(np.asfortranarray(xmat))
    wt_a    = _float64(wt)
    cost_a  = _float64(cost)
    cp_a    = _float64(cp.copy())    # xpred mutates cp in-place

    ncp       = len(cp_a)
    nresp_out = numresp if return_all else 1
    predict_len = n * ncp * nresp_out

    predict_out = np.zeros(predict_len, dtype=np.float64)
    err_buf     = np.zeros(_ERR_BUF_SIZE, dtype=np.uint8)

    _lib.xpred_c(
        _iptr(ncat_a),  len(ncat_a),
        int(method),
        _dptr(opt_a),   len(opt_a),
        _dptr(parms_a), len(parms_a),
        int(xvals),
        _iptr(xgrp_a),  len(xgrp_a),
        _dptr(ymat_a),  len(ymat_a),
        _dptr(xmat_a),  n, nvar,
        _dptr(wt_a),    len(wt_a),
        int(ny),
        _dptr(cost_a),  len(cost_a),
        int(return_all),
        _dptr(cp_a),    ncp,
        float(toprisk),
        int(numresp),
        _dptr(predict_out), predict_len,
        _cptr(err_buf), _ERR_BUF_SIZE,
    )
    _check_error(err_buf)
    return predict_out.copy()


# ---------------------------------------------------------------------------
# Internal C wrapper — rpartexp2()
# ---------------------------------------------------------------------------

def _rpartexp2_c(dtimes: ndarray, eps: float | None = None) -> ndarray:
    """Select unique death times for the exponential survival method.

    Parameters
    ----------
    dtimes : float64 array — sorted unique death times
    eps    : float or None — machine epsilon (default: np.finfo(float).eps)

    Returns
    -------
    keep : int32 array — 1 to keep each death time, 0 to discard
    """
    if eps is None:
        eps = float(np.finfo(float).eps)
    dtimes_a = _float64(dtimes)
    n        = len(dtimes_a)
    keep_out = np.zeros(n, dtype=np.int32)
    err_buf  = np.zeros(_ERR_BUF_SIZE, dtype=np.uint8)

    _lib.rpartexp2_c(
        _dptr(dtimes_a), n,
        float(eps),
        _iptr(keep_out), n,
        _cptr(err_buf),  _ERR_BUF_SIZE,
    )
    _check_error(err_buf)
    return keep_out.copy()


# ---------------------------------------------------------------------------
# High-level Python functions (converted from R source)
# Note: rpart, pred_rpart, xpred, rpartexp2 keep their C-wrapper definitions
#       above; the same-named high-level functions live in rpart.py / pred_rpart.py
#       and are importable as r2py_rpart.rpart.rpart / r2py_rpart.pred_rpart.pred_rpart.
# ---------------------------------------------------------------------------
from .formatg import formatg
from .importance import importance
from .labels_rpart import labels_rpart
from .meanvar_rpart import meanvar, meanvar_rpart
from .model_frame_rpart import model_frame_rpart
from .na_rpart import na_rpart
from .path_rpart import path_rpart
from .plot_rpart import plot_rpart
from .plotcp import plotcp
from .post import post
from .post_rpart import post_rpart
from .predict_rpart import predict_rpart
from .print_rpart import print_rpart
from .printcp import printcp
from .prune import prune
from .prune_rpart import prune_rpart
from .residuals_rpart import residuals_rpart
from .roc_rpart import roc_rpart, ss_compare
from .rpart import rpart, tfun
from .pred_rpart import pred_rpart
from .rpart_anova import rpart_anova
from .rpart_branch import rpart_branch
from .rpart_class import rpart_class
from .rpart_control import rpart_control
from .rpart_exp import drate2, rpart_exp
from .rpart_matrix import rpart_matrix
from .rpart_poisson import rpart_poisson
from .rpartcallback import rpartcallback
from .rpartco import compress, rpartco
from .rsq_rpart import rsq_rpart
from .snip_rpart import snip_rpart
from .snip_rpart_mouse import snip_rpart_mouse
from .summary_rpart import summary_rpart
from .text_rpart import oval, rectangle, text_rpart
from .xpred_rpart import xpred_rpart
from .zzz import descendants, node_match, on_unload, string_bounding_box, tree_depth
