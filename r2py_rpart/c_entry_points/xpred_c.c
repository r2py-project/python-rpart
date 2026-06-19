/* ================================================================
 * xpred_c.c — Pure C entry point for xpred()
 *
 * Original R call form:
 *   .Call(C_xpred,
 *         ncat   = as.integer(cats * !fit$ordered),
 *         method = as.integer(method.int),
 *         as.double(unlist(controls)),
 *         temp,                            # as.double(unlist(parms))
 *         as.integer(xval),
 *         as.integer(xgroups),
 *         Y,                               # as.double (vector or t(matrix))
 *         X,                               # storage.mode(X) <- "double", matrix
 *         wt,                              # storage.mode(wt) <- "double"
 *         as.integer(numy),
 *         as.double(costs),
 *         as.integer(return.all),
 *         as.double(cp),
 *         as.double(fit$frame[1L, "dev"]),
 *         as.integer(numresp))
 *
 * R call site: xpred.rpart.R:119
 *
 * Original C source: r2py_rpart/src/xpred.c
 *
 * Parameter map (SEXP -> plain C):
 * -----------------------------------------------------------------------
 *  SEXP param   Used as in C body                   Plain-C mapping         Dir
 *  ----------   ---------------------------------    --------------------   -----
 *  ncat2        INTEGER(ncat2), indexed [0..nvar-1]
 *               (also rp.numcat = INTEGER(ncat2))  -> int *ncat, int ncat_len  [in]
 *  method2      asInteger(method2) — scalar         -> int method              [in]
 *  opt2         REAL(opt2), indices [0]..[7]        -> double *opt, int opt_len [in]
 *  parms2       REAL(parms2) — passed to init_split -> double *parms, int parms_len [in]
 *  xvals2       asInteger(xvals2) — scalar          -> int xvals               [in]
 *  xgrp2        INTEGER(xgrp2) — int[n]             -> int *xgrp, int xgrp_len [in]
 *  ymat2        REAL(ymat2) — double vector/matrix,
 *               row-major when matrix (t(Y) before .Call)
 *               length = n * numy                   -> double *ymat, int ymat_len [in]
 *  xmat2        REAL(xmat2), nrows(xmat2), ncols(xmat2)
 *               column-major double matrix          -> double *xmat, int xmat_nrow,
 *                                                      int xmat_ncol          [in]
 *  wt2          REAL(wt2) — double[n]               -> double *wt, int wt_len [in]
 *  ny2          asInteger(ny2) — scalar (numy)      -> int ny                  [in]
 *  cost2        REAL(cost2) — double[nvar]           -> double *cost, int cost_len [in]
 *  all2         asInteger(all2) — scalar (0 or 1)   -> int all                 [in]
 *  cp2          REAL(cp2), LENGTH(cp2) — double[ncp] -> double *cp, int cp_len [in]
 *  toprisk2     asReal(toprisk2) — scalar double     -> double toprisk         [in]
 *  nresp2       asInteger(nresp2) — scalar           -> int nresp              [in]
 * -----------------------------------------------------------------------
 *  (return)     allocVector(REALSXP, n * ncp * nresp_out)
 *               1-D real vector where:
 *                 n         = xmat_nrow
 *                 ncp       = cp_len
 *                 nresp_out = rp.num_resp  if all == 1, else 1
 *               Length must be pre-computed by caller as predict_len.
 *                                          -> double *predict_out, int predict_len [out]
 * -----------------------------------------------------------------------
 *  error_out      char *  [out]  — non-empty on any C++ exception
 *  error_out_len  int     [in]   — capacity of error_out buffer in bytes
 *
 * NOTE: ctypes/cffi have no knowledge of C++ exceptions. All exceptions
 * are caught inside this file and written to error_out. The entry point
 * is declared noexcept to enforce this at the compiler level.
 * Python callers must check error_out after every call.
 *
 * NOTE on ymat layout: R passes Y as a flat double vector. When Y is a
 * matrix, the R code does `Y <- as.double(t(Y))` before the .Call, which
 * produces a row-major flat vector of length n * numy. When Y is a plain
 * vector, it is passed as-is (length == n). The C body accesses ymat2 via
 * REAL(ymat2) and walks it as rp.ydata[i] = dptr + i * num_y, consistent
 * with the row-major transposed layout.
 *
 * NOTE on cp2 mutation: xpred() scales cp[] in-place (*cp[i] *= toprisk*
 * and later rescaled inside the cross-validation loop). The caller must
 * pass a writable, private copy of the cp array and must not rely on its
 * values after the call.
 *
 * NOTE on predict_len: The caller must supply predict_len equal to
 *   xmat_nrow * cp_len * (nresp_out)
 * where nresp_out = numresp if return_all == 1, else 1. If predict_len
 * is smaller than what xpred() actually writes, extraction will silently
 * truncate. If larger, the extra elements are left untouched.
 *
 * Fake headers required: fake_R.h (and transitive includes)
 * ================================================================ */

/* fake_R.h pulls in C++ standard library headers (<new>, <type_traits>, etc.)
 * that contain templates. Templates cannot appear inside an extern "C" block.
 * Therefore all includes must precede the extern "C" opening brace. */
#include "fake_R.h"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* --- Original function declaration — C++ linkage to match compiled symbol ---
 * Placed OUTSIDE extern "C" so the C++ mangling of xpred() (compiled from
 * src/xpred.c with g++/-x c++) is preserved. */
extern SEXP xpred(SEXP ncat2, SEXP method2, SEXP opt2,
                  SEXP parms2, SEXP xvals2, SEXP xgrp2,
                  SEXP ymat2, SEXP xmat2, SEXP wt2,
                  SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2,
                  SEXP toprisk2, SEXP nresp2);

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * Input SEXP construction helpers (static, no-copy)
 *
 * These helpers wrap a caller-supplied array behind a SEXPREC node.
 * The SEXPREC node is heap-allocated (malloc); s->data points directly
 * at the caller's buffer — no data is copied.
 *
 * The caller retains ownership of the underlying data array. Only the
 * SEXPREC node itself must be freed after the call (via free(node)).
 *
 * Exception: make_int_scalar and make_real_scalar allocate a private
 * one-element buffer alongside the SEXPREC node. These must be freed
 * with free_int_scalar / free_real_scalar rather than plain free().
 * ================================================================ */

/* make_int_vec — wrap int *arr (length len) as a 1-D INTSXP.
 * s->data points directly at arr; arr is NOT copied or freed here. */
static inline SEXP make_int_vec(int *arr, int len) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_int_vec: out of memory allocating SEXPREC");
    s->type   = INTSXP;
    s->length = len;
    s->nrow   = len;
    s->ncol   = 1;
    s->data   = arr;   /* no copy — caller owns arr */
    return s;
}

/* make_real_vec — wrap double *arr (length len) as a 1-D REALSXP.
 * s->data points directly at arr; arr is NOT copied or freed here. */
static inline SEXP make_real_vec(double *arr, int len) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_vec: out of memory allocating SEXPREC");
    s->type   = REALSXP;
    s->length = len;
    s->nrow   = len;
    s->ncol   = 1;
    s->data   = arr;   /* no copy — caller owns arr */
    return s;
}

/* make_real_mat — wrap double *arr (nrow*ncol elements, column-major) as REALSXP.
 * s->data points directly at arr; arr is NOT copied or freed here. */
static inline SEXP make_real_mat(double *arr, int nrow, int ncol) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_mat: out of memory allocating SEXPREC");
    s->type   = REALSXP;
    s->length = nrow * ncol;
    s->nrow   = nrow;
    s->ncol   = ncol;
    s->data   = arr;   /* no copy — caller owns arr */
    return s;
}

/* make_int_scalar — wrap a single int value as a 1-element INTSXP.
 * A private int[1] buffer is allocated alongside the SEXPREC because
 * asInteger(s) reads ((int *)s->data)[0]. */
static inline SEXP make_int_scalar(int value) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_int_scalar: out of memory allocating SEXPREC");
    int *buf = (int *) malloc(sizeof(int));
    if (!buf) { free(s); throw RError("make_int_scalar: out of memory allocating data"); }
    buf[0]    = value;
    s->type   = INTSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = buf;
    return s;
}

/* free_int_scalar — frees both the SEXPREC node and the private int[1] buffer. */
static inline void free_int_scalar(SEXP s) {
    if (s) {
        free(s->data);
        free(s);
    }
}

/* make_real_scalar — wrap a single double value as a 1-element REALSXP.
 * A private double[1] buffer is allocated alongside the SEXPREC because
 * asReal(s) reads ((double *)s->data)[0]. */
static inline SEXP make_real_scalar(double value) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_scalar: out of memory allocating SEXPREC");
    double *buf = (double *) malloc(sizeof(double));
    if (!buf) { free(s); throw RError("make_real_scalar: out of memory allocating data"); }
    buf[0]    = value;
    s->type   = REALSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = buf;
    return s;
}

/* free_real_scalar — frees both the SEXPREC node and the private double[1] buffer. */
static inline void free_real_scalar(SEXP s) {
    if (s) {
        free(s->data);
        free(s);
    }
}

/* ================================================================
 * Output SEXP extraction helpers (static, copy-out)
 *
 * These helpers read from the SEXP returned by xpred() and copy
 * elements into caller-supplied output arrays.
 * ================================================================ */

/* extract_real_vec — copy up to out_len elements from a REALSXP into out.
 * Validates the SEXP type tag; throws RError on mismatch. */
static inline void extract_real_vec(SEXP s, double *out, int out_len) {
    if (!s)
        throw RError("extract_real_vec: NULL SEXP");
    if (s->type != REALSXP)
        throw RError("extract_real_vec: expected REALSXP but got different type");
    int copy_n = (s->length < out_len) ? s->length : out_len;
    memcpy(out, (double *) s->data, (size_t) copy_n * sizeof(double));
}

/* ================================================================
 * Entry point (noexcept: all exceptions are caught here; none may
 * escape across the C ABI boundary).
 *
 * Caller pre-conditions:
 *   ncat        int[ncat_len], length == ncols(X) (number of predictor vars).
 *               ncat[i] == 0 for continuous, > 0 for categorical vars.
 *   method      scalar: 1=anova, 2=poisson/exp, 3=class, 4=user.
 *   opt         double[opt_len], length >= 8. Same order as rpart.control.
 *               opt[0]=minsplit, opt[1]=minbucket, opt[2]=cp, opt[3]=maxcompete,
 *               opt[4]=maxsurrogate, opt[5]=usesurrogate, opt[6]=surrogatestyle,
 *               opt[7]=maxdepth.
 *   parms       double[parms_len] — extra parameters for the split function.
 *               May be length 1 with a dummy 0.0 when parms is NULL in R.
 *   xvals       scalar: number of cross-validation groups.
 *   xgrp        int[xgrp_len], length == nrow(X). Group index (1-based) for
 *               each observation.
 *   ymat        double[ymat_len]. When Y is a vector, length == n. When Y is
 *               a matrix, length == n * numy (row-major: R did t(Y) first).
 *   xmat        double[xmat_nrow * xmat_ncol], column-major. X matrix.
 *               xmat_nrow == n (number of observations).
 *               xmat_ncol == number of predictor variables.
 *   wt          double[wt_len], length == n. Case weights.
 *   ny          scalar: number of columns of the Y matrix (numy).
 *   cost        double[cost_len], length == ncols(X). Variable cost multipliers.
 *   all         scalar: 0 or 1. If 1, return all numresp response values per
 *               (obs, cp) combination; if 0, return only the first.
 *   cp          double[cp_len]. CP threshold vector. NOTE: xpred() mutates
 *               this array in-place (scales by toprisk and then rescales inside
 *               the cross-validation loop). Pass a private writable copy.
 *   toprisk     scalar double: risk at the top node of the tree
 *               (fit$frame[1L, "dev"]).
 *   nresp       scalar: numresp (number of response values stored per node).
 *   predict_out double[predict_len]. Pre-allocated output buffer. Filled on
 *               success with the flat prediction array of length
 *               n * ncp * nresp_out, where nresp_out = nresp if all==1, else 1.
 *   predict_len int: capacity of predict_out (in doubles). Must equal
 *               xmat_nrow * cp_len * (all ? nresp : 1).
 *   error_out   char[error_out_len]. Zeroed on entry; filled on error.
 *   error_out_len int: capacity of error_out in bytes.
 * ================================================================ */
void xpred_c(
    /* inputs */
    int    *ncat,        int    ncat_len,
    int     method,
    double *opt,         int    opt_len,
    double *parms,       int    parms_len,
    int     xvals,
    int    *xgrp,        int    xgrp_len,
    double *ymat,        int    ymat_len,
    double *xmat,        int    xmat_nrow,  int xmat_ncol,
    double *wt,          int    wt_len,
    int     ny,
    double *cost,        int    cost_len,
    int     all,
    double *cp,          int    cp_len,
    double  toprisk,
    int     nresp,
    /* outputs */
    double *predict_out, int    predict_len,
    /* error propagation */
    char   *error_out,   int    error_out_len
) noexcept {
    /* Step 1: zero the error buffer */
    if (error_out && error_out_len > 0) error_out[0] = '\0';

    /* Step 2: declare ArenaFrame — frees all R_alloc/ALLOC scratch on exit.
     * xpred() uses ALLOC extensively for rp.sorts, rp.tempvec, rp.xtemp,
     * rp.ytemp, rp.wtemp, rp.wt, rp.csplit, rp.which, etc. */
    ArenaFrame _frame;

    /* Step 3: declare all SEXP wrapper variables (initialised to nullptr so
     * the FREE_INPUT_WRAPPERS macro is safe to invoke at any point). */
    SEXP s_ncat     = nullptr;
    SEXP s_method   = nullptr;
    SEXP s_opt      = nullptr;
    SEXP s_parms    = nullptr;
    SEXP s_xvals    = nullptr;
    SEXP s_xgrp     = nullptr;
    SEXP s_ymat     = nullptr;
    SEXP s_xmat     = nullptr;
    SEXP s_wt       = nullptr;
    SEXP s_ny       = nullptr;
    SEXP s_cost     = nullptr;
    SEXP s_all      = nullptr;
    SEXP s_cp       = nullptr;
    SEXP s_toprisk  = nullptr;
    SEXP s_nresp    = nullptr;

    /* Helper macro: free all input SEXP wrappers.
     *
     * No-copy wrappers (make_int_vec, make_real_vec, make_real_mat):
     *   free only the SEXPREC node via free(); the caller owns the data.
     *
     * Scalar wrappers (make_int_scalar, make_real_scalar):
     *   free both the SEXPREC node and the private one-element data buffer
     *   via free_int_scalar() / free_real_scalar(). */
#define FREE_INPUT_WRAPPERS() do { \
    if (s_ncat)    { free(s_ncat);               s_ncat    = nullptr; } \
    if (s_method)  { free_int_scalar(s_method);  s_method  = nullptr; } \
    if (s_opt)     { free(s_opt);                s_opt     = nullptr; } \
    if (s_parms)   { free(s_parms);              s_parms   = nullptr; } \
    if (s_xvals)   { free_int_scalar(s_xvals);   s_xvals   = nullptr; } \
    if (s_xgrp)    { free(s_xgrp);               s_xgrp    = nullptr; } \
    if (s_ymat)    { free(s_ymat);               s_ymat    = nullptr; } \
    if (s_xmat)    { free(s_xmat);               s_xmat    = nullptr; } \
    if (s_wt)      { free(s_wt);                 s_wt      = nullptr; } \
    if (s_ny)      { free_int_scalar(s_ny);      s_ny      = nullptr; } \
    if (s_cost)    { free(s_cost);               s_cost    = nullptr; } \
    if (s_all)     { free_int_scalar(s_all);     s_all     = nullptr; } \
    if (s_cp)      { free(s_cp);                 s_cp      = nullptr; } \
    if (s_toprisk) { free_real_scalar(s_toprisk); s_toprisk = nullptr; } \
    if (s_nresp)   { free_int_scalar(s_nresp);   s_nresp   = nullptr; } \
} while(0)

    /* Construct SEXP wrappers for each input parameter.
     * Wrapped in a try block so partial construction failures are cleaned up. */
    try {
        /* ncat2: INTEGER(ncat2) — int vector of length nvar (= ncols of X).
         * Also used as rp.numcat = INTEGER(ncat2). */
        s_ncat = make_int_vec(ncat, ncat_len);

        /* method2: asInteger(method2) — scalar int (1=anova, 2=poisson/exp,
         * 3=class, 4=user). The C body calls asInteger(method2) twice. */
        s_method = make_int_scalar(method);

        /* opt2: REAL(opt2) — double vector of control options (length >= 8).
         * Accessed as dptr = REAL(opt2); dptr[0..7]. */
        s_opt = make_real_vec(opt, opt_len);

        /* parms2: REAL(parms2) — double vector of split function parameters.
         * Passed directly to (*rp_init)(). May be a dummy {0.0} when NULL. */
        s_parms = make_real_vec(parms, parms_len);

        /* xvals2: asInteger(xvals2) — scalar int: number of CV folds. */
        s_xvals = make_int_scalar(xvals);

        /* xgrp2: INTEGER(xgrp2) — int vector of length n (= xmat_nrow).
         * xgrp[i] is the 1-based CV group index for observation i. */
        s_xgrp = make_int_vec(xgrp, xgrp_len);

        /* ymat2: REAL(ymat2) — flat double vector.
         * When Y is a matrix (numy > 1), R passes as.double(t(Y)), giving a
         * row-major vector of length n * numy. When a plain vector, length == n.
         * The C body iterates: rp.ydata[i] = dptr; dptr += rp.num_y;
         * so the layout must be consistent with num_y (= ny). */
        s_ymat = make_real_vec(ymat, ymat_len);

        /* xmat2: REAL(xmat2), nrows(xmat2), ncols(xmat2) — column-major double
         * matrix with xmat_nrow rows (n) and xmat_ncol cols (nvar).
         * Accessed as rp.xdata[i] = dptr; dptr += n; for i in 0..nvar-1. */
        s_xmat = make_real_mat(xmat, xmat_nrow, xmat_ncol);

        /* wt2: REAL(wt2) — double vector of case weights, length n. */
        s_wt = make_real_vec(wt, wt_len);

        /* ny2: asInteger(ny2) — scalar int: number of Y columns (numy). */
        s_ny = make_int_scalar(ny);

        /* cost2: REAL(cost2) — double vector of variable costs, length nvar.
         * Stored as rp.vcost = REAL(cost2). */
        s_cost = make_real_vec(cost, cost_len);

        /* all2: asInteger(all2) — scalar int (0 or 1). Controls whether all
         * numresp response components are returned. */
        s_all = make_int_scalar(all);

        /* cp2: REAL(cp2), LENGTH(cp2) — double vector of CP thresholds.
         * WARNING: xpred() mutates this array in-place (scales by toprisk
         * and then further rescales inside the loop). The caller must pass
         * a private writable copy. No-copy wrapper is used; the SEXPREC
         * node points directly at the caller's cp array. */
        s_cp = make_real_vec(cp, cp_len);

        /* toprisk2: asReal(toprisk2) — scalar double: top-node risk. */
        s_toprisk = make_real_scalar(toprisk);

        /* nresp2: asInteger(nresp2) — scalar int: numresp (response count). */
        s_nresp = make_int_scalar(nresp);

    } catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    } catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    } catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    } catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception during SEXP construction",
                    (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    }

    /* Step 4: call the original function — catch ALL exception types.
     * xpred() returns allocVector(REALSXP, n * ncp * nresp_out), a heap-
     * allocated 1-D real vector.  Both the SEXPREC node and its double[]
     * data buffer were malloc'd by allocVector and are owned by us. */
    SEXP _result = nullptr;
    try {
        _result = xpred(s_ncat, s_method, s_opt,
                        s_parms, s_xvals, s_xgrp,
                        s_ymat, s_xmat, s_wt,
                        s_ny, s_cost, s_all, s_cp,
                        s_toprisk, s_nresp);
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    }
    catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    }
    catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception", (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUT_WRAPPERS();
        return;
    }

    /* Step 5: extract outputs from the returned SEXP.
     *
     * xpred() returns a 1-D REALSXP of length n * ncp * nresp_out.
     * Copy into caller-supplied predict_out[0..predict_len-1]. */
    try {
        extract_real_vec(_result, predict_out, predict_len);
    } catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        /* fall through to cleanup */
    } catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        /* fall through to cleanup */
    } catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception during result extraction",
                    (size_t)(error_out_len - 1));
            error_out[error_out_len - 1] = '\0';
        }
        /* fall through to cleanup */
    }

    /* Step 6: free all allocated SEXPREC wrappers.
     *
     * No-copy wrappers (make_int_vec, make_real_vec, make_real_mat):
     *   free only the SEXPREC node — the caller owns the data arrays.
     *
     * Scalar wrappers (make_int_scalar, make_real_scalar):
     *   free both the SEXPREC node and the private one-element data buffer.
     *
     * Result SEXP (_result):
     *   xpred() allocates predict2 via allocVector(REALSXP, n*ncp*nresp).
     *   Both the SEXPREC node and its double[n*ncp*nresp] data buffer were
     *   malloc'd by allocVector and are owned here. Free with free_sexp(). */
    FREE_INPUT_WRAPPERS();

    if (_result) {
        free(_result->data);   /* the double[n*ncp*nresp_out] predict buffer */
        free(_result);         /* the SEXPREC node */
    }

#undef FREE_INPUT_WRAPPERS
}

/* Python caller pattern:
 *
 *   import ctypes, numpy as np
 *
 *   lib = ctypes.CDLL("path/to/rpart_with_entry_points.so")
 *   lib.xpred_c.restype  = None
 *   lib.xpred_c.argtypes = [
 *       ctypes.POINTER(ctypes.c_int),    ctypes.c_int,   # ncat, ncat_len
 *       ctypes.c_int,                                     # method
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # opt, opt_len
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # parms, parms_len
 *       ctypes.c_int,                                     # xvals
 *       ctypes.POINTER(ctypes.c_int),    ctypes.c_int,   # xgrp, xgrp_len
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # ymat, ymat_len
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, # xmat, nrow, ncol
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # wt, wt_len
 *       ctypes.c_int,                                     # ny
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # cost, cost_len
 *       ctypes.c_int,                                     # all
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # cp, cp_len
 *       ctypes.c_double,                                  # toprisk
 *       ctypes.c_int,                                     # nresp
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,   # predict_out, predict_len
 *       ctypes.c_char_p,                 ctypes.c_int,   # error_out, error_out_len
 *   ]
 *
 *   n_obs   = X.shape[0]
 *   n_var   = X.shape[1]
 *   ncp     = len(cp)
 *   nresp_out = numresp if return_all else 1
 *   predict_len = n_obs * ncp * nresp_out
 *
 *   # cp is mutated in-place by xpred(); pass a private copy
 *   cp_copy = cp.copy().astype(np.float64)
 *
 *   predict_out = np.zeros(predict_len, dtype=np.float64)
 *   error_buf   = ctypes.create_string_buffer(1024)
 *
 *   lib.xpred_c(
 *       ncat_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),    len(ncat_arr),
 *       int(method),
 *       opt_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),  len(opt_arr),
 *       parms_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(parms_arr),
 *       int(xvals),
 *       xgrp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),    len(xgrp_arr),
 *       ymat_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(ymat_arr),
 *       xmat_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), n_obs, n_var,
 *       wt_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),   len(wt_arr),
 *       int(ny),
 *       cost_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(cost_arr),
 *       int(return_all),
 *       cp_copy.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),  ncp,
 *       float(toprisk),
 *       int(numresp),
 *       predict_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), predict_len,
 *       error_buf, 1024,
 *   )
 *   if error_buf.value:
 *       raise RuntimeError(error_buf.value.decode())
 *
 *   # predict_out is the flat array; reshape as R does:
 *   if return_all and numresp > 1:
 *       pred = predict_out.reshape((numresp, ncp, n_obs))
 *       pred = np.transpose(pred, (2, 1, 0))   # aperm equivalent
 *   else:
 *       pred = predict_out.reshape((n_obs, ncp), order='C')
 */

#ifdef __cplusplus
} /* extern "C" */
#endif
