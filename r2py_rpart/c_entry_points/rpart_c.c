/* ================================================================
 * rpart_c.c — Pure C entry point for rpart()
 *
 * Original R call form:
 *   .Call(C_rpart,
 *         ncat    = as.integer(cats * !isord),
 *         method  = as.integer(method.int),
 *         as.double(unlist(controls)),
 *         temp,                          -- as.double(unlist(init$parms))
 *         as.integer(xval),
 *         as.integer(xgroups),
 *         as.double(t(init$y)),
 *         X,                             -- double matrix (column-major)
 *         wt,                            -- double vector (weights)
 *         as.integer(init$numy),
 *         as.double(cost))
 *
 * Parameter map (SEXP -> plain C):
 *   ncat2   (INTSXP vector, length nvar)          -> int *ncat,   int ncat_len      [in]
 *   method2 (INTSXP scalar)                       -> int method                      [in]
 *   opt2    (REALSXP vector, length 8)            -> double *opt, int opt_len        [in]
 *   parms2  (REALSXP vector, variable length)     -> double *parms, int parms_len    [in]
 *   xvals2  (INTSXP scalar)                       -> int xvals                       [in]
 *   xgrp2   (INTSXP vector, length n)             -> int *xgrp,  int xgrp_len       [in]
 *   ymat2   (REALSXP vector, length n*num_y,
 *            stored row-major as t(init$y))       -> double *ymat, int ymat_len      [in]
 *   xmat2   (REALSXP matrix, nrow=n, ncol=nvar,
 *            column-major; X is already double)   -> double *xmat, int xmat_nrow,
 *                                                    int xmat_ncol                   [in]
 *   wt2     (REALSXP vector, length n)            -> double *wt,  int wt_len        [in]
 *   ny2     (INTSXP scalar)                       -> int ny                          [in]
 *   cost2   (REALSXP vector, length nvar)         -> double *cost, int cost_len      [in]
 *
 * Return value — named list (VECSXP, length 6 or 7):
 *   [0] which   (INTSXP vector, length n)                        -> int *which_out,   int which_len       [out]
 *   [1] cptable (REALSXP matrix, nrow=3 or 5, ncol=num_unique_cp)-> double *cptable_out,
 *                                                                    int *cptable_nrow_out,
 *                                                                    int *cptable_ncol_out               [out]
 *   [2] dsplit  (REALSXP matrix, nrow=splitcount, ncol=3)        -> double *dsplit_out,
 *                                                                    int *dsplit_nrow_out                [out]
 *   [3] isplit  (INTSXP  matrix, nrow=splitcount, ncol=3)        -> int    *isplit_out,
 *                                                                    int *isplit_nrow_out                [out]
 *   [4] dnode   (REALSXP matrix, nrow=nodecount,  ncol=3+num_resp)-> double *dnode_out,
 *                                                                     int *dnode_nrow_out,
 *                                                                     int *dnode_ncol_out               [out]
 *   [5] inode   (INTSXP  matrix, nrow=nodecount,  ncol=6)        -> int    *inode_out,
 *                                                                    int *inode_nrow_out                [out]
 *   [6] csplit  (INTSXP  matrix, nrow=catcount, ncol=maxcat;
 *                conditional — present only when catcount > 0)    -> int    *csplit_out,
 *                                                                    int *csplit_nrow_out,
 *                                                                    int *csplit_ncol_out,
 *                                                                    int *has_csplit                    [out]
 *   error_out     char *  [out]  — non-empty on any C++ exception
 *   error_out_len int     [in]   — capacity of error_out buffer
 *
 * NOTE: ctypes/cffi have no knowledge of C++ exceptions.  All exceptions
 * are caught inside this file and written to error_out.  The entry point
 * is declared noexcept to enforce this at the compiler level.
 * Python callers must check error_out after every call.
 *
 * Dimension conventions:
 *   cptable is column-major: nrow=3 (no xval) or 5 (with xval), ncol=num_unique_cp.
 *   dsplit  is column-major: nrow=splitcount, ncol=3.
 *   isplit  is column-major: nrow=splitcount, ncol=3.
 *   dnode   is column-major: nrow=nodecount,  ncol=3+num_resp.
 *   inode   is column-major: nrow=nodecount,  ncol=6.
 *   csplit  is column-major: nrow=catcount,   ncol=maxcat.
 *   xmat    is column-major: nrow=n,          ncol=nvar (matches R's storage.mode).
 *   ymat    is row-major (t(init$y)): the caller must transpose before passing.
 *
 * Caller pre-allocation:
 *   The caller must allocate the output arrays with sufficient capacity.
 *   Recommended strategy: query nrow/ncol after the call via the *_nrow_out /
 *   *_ncol_out outputs and pre-allocate conservatively (e.g., max expected
 *   nodecount and splitcount), or make two passes (first call with NULL outputs
 *   to get dimensions, second call with allocated buffers -- but this is expensive).
 *   Simplest approach: allocate generously (e.g., 2*n elements for each matrix
 *   output), and read only *_nrow_out * ncol elements after the call.
 *
 * Fake headers required: fake_R.h (and transitive includes in r_fake_headers/)
 * Original C source:     r2py_rpart/src/rpart.c
 * R call sites:          rpart.R:160
 * ================================================================ */

/* fake_R.h pulls in C++ standard library headers (<new>, <type_traits>, etc.)
 * that contain templates.  Templates cannot appear inside an extern "C" block.
 * Therefore all includes must precede the extern "C" opening brace. */
#include "fake_R.h"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* --- Original function declaration — C++ linkage to match compiled symbol ---
 * Placed OUTSIDE extern "C" so the C++ mangling of rpart() (compiled from
 * src/rpart.c with g++/-x c++) is preserved. */
extern SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2,
                  SEXP parms2, SEXP xvals2, SEXP xgrp2,
                  SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2);

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * Input SEXP construction helpers (static, no-copy)
 *
 * These helpers allocate only the SEXPREC header node on the heap.
 * The data field points directly at the caller-supplied array; it is
 * NOT freed when the SEXPREC wrapper is freed.  The caller owns the
 * underlying array.
 *
 * Each helper throws RError (via Rf_error / throw) on malloc failure.
 * ================================================================ */

/* make_int_scalar — wrap a single int value in a length-1 INTSXP.
 * The value is copied into a 1-element heap buffer (since the source
 * is a stack int, not a caller-owned array). */
static inline SEXP make_int_scalar(int value) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_int_scalar: out of memory allocating SEXPREC");
    int *buf = (int *) malloc(sizeof(int));
    if (!buf) { free(s); throw RError("make_int_scalar: out of memory allocating data"); }
    *buf = value;
    s->type   = INTSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = buf;
    return s;
}

/* free_int_scalar — frees both the SEXPREC node and its private 1-element buffer.
 * Use this (not free_sexp) for SEXPs created by make_int_scalar. */
static inline void free_int_scalar(SEXP s) {
    if (!s) return;
    free(s->data);
    free(s);
}

/* make_real_scalar — wrap a single double value in a length-1 REALSXP.
 * Same ownership pattern as make_int_scalar. */
static inline SEXP make_real_scalar(double value) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_scalar: out of memory allocating SEXPREC");
    double *buf = (double *) malloc(sizeof(double));
    if (!buf) { free(s); throw RError("make_real_scalar: out of memory allocating data"); }
    *buf = value;
    s->type   = REALSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = buf;
    return s;
}

static inline void free_real_scalar(SEXP s) {
    if (!s) return;
    free(s->data);
    free(s);
}

/* make_int_vec — wrap caller-supplied int array as a 1-D INTSXP.
 * data pointer is NOT copied; the caller retains ownership. */
static inline SEXP make_int_vec(int *data, int len) {
    if (!data && len > 0)
        throw RError("make_int_vec: null data pointer with non-zero length");
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_int_vec: out of memory allocating SEXPREC");
    s->type   = INTSXP;
    s->length = len;
    s->nrow   = len;
    s->ncol   = 1;
    s->data   = data;   /* no copy — caller owns this buffer */
    return s;
}

/* free_int_vec_wrapper — frees only the SEXPREC node; caller's array is NOT freed. */
static inline void free_int_vec_wrapper(SEXP s) {
    if (!s) return;
    /* do NOT free s->data — it belongs to the caller */
    free(s);
}

/* make_real_vec — wrap caller-supplied double array as a 1-D REALSXP. */
static inline SEXP make_real_vec(double *data, int len) {
    if (!data && len > 0)
        throw RError("make_real_vec: null data pointer with non-zero length");
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_vec: out of memory allocating SEXPREC");
    s->type   = REALSXP;
    s->length = len;
    s->nrow   = len;
    s->ncol   = 1;
    s->data   = data;
    return s;
}

static inline void free_real_vec_wrapper(SEXP s) {
    if (!s) return;
    free(s);
}

/* make_real_mat — wrap caller-supplied double array as a 2-D REALSXP matrix.
 * The array must be column-major (R's default storage order), length nrow*ncol. */
static inline SEXP make_real_mat(double *data, int nrow, int ncol) {
    if (!data && nrow > 0 && ncol > 0)
        throw RError("make_real_mat: null data pointer with non-zero dimensions");
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_mat: out of memory allocating SEXPREC");
    s->type   = REALSXP;
    s->length = nrow * ncol;
    s->nrow   = nrow;
    s->ncol   = ncol;
    s->data   = data;
    return s;
}

static inline void free_real_mat_wrapper(SEXP s) {
    if (!s) return;
    free(s);
}

/* ================================================================
 * Output SEXP extraction helpers (static, copy-out)
 *
 * Each helper validates the SEXP type tag and copies data into
 * the caller-supplied output buffer.  Type mismatches throw RError.
 * ================================================================ */

/* extract_int_vec — copy INTEGER data from a 1-D INTSXP into out[0..len-1].
 * out must be pre-allocated by the caller. */
static inline void extract_int_vec(SEXP s, int *out, int *len_out) {
    if (!s || s->type != INTSXP)
        throw RError("extract_int_vec: expected INTSXP");
    *len_out = s->length;
    const int *src = (const int *) s->data;
    for (int i = 0; i < s->length; i++)
        out[i] = src[i];
}

/* extract_real_mat — copy REAL data from a 2-D REALSXP matrix into out[].
 * The matrix is column-major; out must hold nrow*ncol doubles.
 * Writes actual nrow and ncol into *nrow_out and *ncol_out. */
static inline void extract_real_mat(SEXP s, double *out,
                                    int *nrow_out, int *ncol_out) {
    if (!s || s->type != REALSXP)
        throw RError("extract_real_mat: expected REALSXP");
    *nrow_out = s->nrow;
    *ncol_out = s->ncol;
    const double *src = (const double *) s->data;
    int total = s->length;
    for (int i = 0; i < total; i++)
        out[i] = src[i];
}

/* extract_int_mat — copy INTEGER data from a 2-D INTSXP matrix into out[].
 * Column-major layout.  Writes nrow into *nrow_out (ncol is fixed by caller). */
static inline void extract_int_mat(SEXP s, int *out,
                                   int *nrow_out, int *ncol_out) {
    if (!s || s->type != INTSXP)
        throw RError("extract_int_mat: expected INTSXP");
    *nrow_out = s->nrow;
    *ncol_out = s->ncol;
    const int *src = (const int *) s->data;
    int total = s->length;
    for (int i = 0; i < total; i++)
        out[i] = src[i];
}

/* ================================================================
 * Entry point — noexcept: all exceptions caught internally.
 *
 * Parameter naming conventions:
 *   Inputs ending in _len     — 1-D vector length.
 *   Inputs ending in _nrow/_ncol — matrix dimensions.
 *   Outputs ending in _out    — pre-allocated caller buffer.
 *   Outputs ending in _nrow_out/_ncol_out — actual dimensions written
 *       by rpart() into those buffers.  The caller uses these to know
 *       how many elements are valid after the call.
 *
 * Memory layout of output matrices (column-major, same as R):
 *   cptable_out[row + col * (*cptable_nrow_out)]
 *   dsplit_out [row + col * (*dsplit_nrow_out)]   ncol=3
 *   isplit_out [row + col * (*isplit_nrow_out)]   ncol=3
 *   dnode_out  [row + col * (*dnode_nrow_out)]    ncol=3+num_resp
 *   inode_out  [row + col * (*inode_nrow_out)]    ncol=6
 *   csplit_out [row + col * (*csplit_nrow_out)]   ncol=*csplit_ncol_out
 * ================================================================ */
void rpart_c(
    /* --- inputs --- */
    int    *ncat,        int ncat_len,    /* ncat[nvar]: category counts per variable */
    int     method,                       /* 1=anova, 2=poisson/exp, 3=class, 4=user */
    double *opt,         int opt_len,     /* controls vector (8 elements) */
    double *parms,       int parms_len,   /* extra params for split fn (0 -> pass dummy 0.0) */
    int     xvals,                        /* number of cross-validations */
    int    *xgrp,        int xgrp_len,    /* cross-validation group assignments [n] */
    double *ymat,        int ymat_len,    /* response matrix, row-major t(init$y) [n*ny] */
    double *xmat,        int xmat_nrow,   /* predictor matrix, column-major [n x nvar] */
                         int xmat_ncol,
    double *wt,          int wt_len,      /* case weights [n] */
    int     ny,                           /* number of response columns (init$numy) */
    double *cost,        int cost_len,    /* variable cost vector [nvar] */
    /* --- outputs: which --- */
    int    *which_out,   int which_cap,   /* pre-allocated [n]; capacity must be >= n */
    int    *which_len_out,                /* actual length written */
    /* --- outputs: cptable --- */
    double *cptable_out, int cptable_cap, /* pre-allocated [nrow*ncol]; column-major */
    int    *cptable_nrow_out,
    int    *cptable_ncol_out,
    /* --- outputs: dsplit --- */
    double *dsplit_out,  int dsplit_cap,  /* pre-allocated [splitcount*3]; column-major */
    int    *dsplit_nrow_out,
    /* --- outputs: isplit --- */
    int    *isplit_out,  int isplit_cap,  /* pre-allocated [splitcount*3]; column-major */
    int    *isplit_nrow_out,
    /* --- outputs: dnode --- */
    double *dnode_out,   int dnode_cap,   /* pre-allocated [nodecount*(3+num_resp)]; col-major */
    int    *dnode_nrow_out,
    int    *dnode_ncol_out,
    /* --- outputs: inode --- */
    int    *inode_out,   int inode_cap,   /* pre-allocated [nodecount*6]; column-major */
    int    *inode_nrow_out,
    /* --- outputs: csplit (conditional) --- */
    int    *csplit_out,  int csplit_cap,  /* pre-allocated [catcount*maxcat]; col-major */
    int    *csplit_nrow_out,
    int    *csplit_ncol_out,
    int    *has_csplit,                   /* set to 1 if csplit present, 0 otherwise */
    /* --- error propagation --- */
    char   *error_out,   int error_out_len
) noexcept {

    /* Step 1: zero the error buffer */
    if (error_out && error_out_len > 0) error_out[0] = '\0';

    /* Step 2: ArenaFrame — frees all R_alloc/ALLOC scratch when we return */
    ArenaFrame _frame;

    /* Initialise output dimension fields to 0 so the caller sees defined
     * values even when an error occurs before extraction. */
    if (which_len_out)    *which_len_out    = 0;
    if (cptable_nrow_out) *cptable_nrow_out = 0;
    if (cptable_ncol_out) *cptable_ncol_out = 0;
    if (dsplit_nrow_out)  *dsplit_nrow_out  = 0;
    if (isplit_nrow_out)  *isplit_nrow_out  = 0;
    if (dnode_nrow_out)   *dnode_nrow_out   = 0;
    if (dnode_ncol_out)   *dnode_ncol_out   = 0;
    if (inode_nrow_out)   *inode_nrow_out   = 0;
    if (csplit_nrow_out)  *csplit_nrow_out  = 0;
    if (csplit_ncol_out)  *csplit_ncol_out  = 0;
    if (has_csplit)       *has_csplit        = 0;

    /* Step 3: wrap inputs into SEXP objects (no-copy for arrays) */
    SEXP s_ncat   = NULL;
    SEXP s_method = NULL;
    SEXP s_opt    = NULL;
    SEXP s_parms  = NULL;
    SEXP s_xvals  = NULL;
    SEXP s_xgrp   = NULL;
    SEXP s_ymat   = NULL;
    SEXP s_xmat   = NULL;
    SEXP s_wt     = NULL;
    SEXP s_ny     = NULL;
    SEXP s_cost   = NULL;

    /* Helper macro: free all input wrappers, then return.
     * Scalars (s_method, s_xvals, s_ny) own their 1-element buffer.
     * Vectors/matrices (s_ncat, s_opt, etc.) do NOT own the data buffer. */
#define FREE_INPUTS_AND_RETURN \
    do { \
        free_int_vec_wrapper(s_ncat); \
        free_int_scalar(s_method); \
        free_real_vec_wrapper(s_opt); \
        free_real_vec_wrapper(s_parms); \
        free_int_scalar(s_xvals); \
        free_int_vec_wrapper(s_xgrp); \
        free_real_vec_wrapper(s_ymat); \
        free_real_mat_wrapper(s_xmat); \
        free_real_vec_wrapper(s_wt); \
        free_int_scalar(s_ny); \
        free_real_vec_wrapper(s_cost); \
        return; \
    } while (0)

    try {
        s_ncat   = make_int_vec(ncat, ncat_len);
        s_method = make_int_scalar(method);
        s_opt    = make_real_vec(opt, opt_len);
        /* R code: if (!length(parms)) temp <- 0 — pass dummy 0.0 when parms_len==0 */
        if (parms_len > 0) {
            s_parms = make_real_vec(parms, parms_len);
        } else {
            /* allocate a private 1-element buffer containing 0.0 */
            s_parms = make_real_scalar(0.0);
        }
        s_xvals  = make_int_scalar(xvals);
        s_xgrp   = make_int_vec(xgrp, xgrp_len);
        s_ymat   = make_real_vec(ymat, ymat_len);
        s_xmat   = make_real_mat(xmat, xmat_nrow, xmat_ncol);
        s_wt     = make_real_vec(wt, wt_len);
        s_ny     = make_int_scalar(ny);
        s_cost   = make_real_vec(cost, cost_len);
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }
    catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }
    catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception during input wrapping", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }

    /* Step 4: call the original SEXP-based function; catch ALL exceptions */
    SEXP _result = NULL;
    try {
        _result = rpart(s_ncat, s_method, s_opt,
                        s_parms, s_xvals, s_xgrp,
                        s_ymat, s_xmat, s_wt, s_ny, s_cost);
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }
    catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }
    catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        FREE_INPUTS_AND_RETURN;
    }

    /* Step 5: free input wrappers (underlying arrays remain caller-owned) */
    free_int_vec_wrapper(s_ncat);
    free_int_scalar(s_method);
    free_real_vec_wrapper(s_opt);
    /* s_parms: if parms_len==0 we allocated a private scalar buffer; free it.
     * If parms_len>0 we only own the SEXPREC node. */
    if (parms_len > 0)
        free_real_vec_wrapper(s_parms);
    else
        free_real_scalar(s_parms);
    free_int_scalar(s_xvals);
    free_int_vec_wrapper(s_xgrp);
    free_real_vec_wrapper(s_ymat);
    free_real_mat_wrapper(s_xmat);
    free_real_vec_wrapper(s_wt);
    free_int_scalar(s_ny);
    free_real_vec_wrapper(s_cost);

    /* Step 6: unpack the returned VECSXP into caller-supplied output arrays.
     *
     * rpart.c constructs the list as:
     *   nout = (catcount > 0) ? 7 : 6
     *   rlist[0] = which3    (INTSXP  vector,  length n)
     *   rlist[1] = cptable3  (REALSXP matrix,  nrow=3or5, ncol=num_unique_cp)
     *   rlist[2] = dsplit3   (REALSXP matrix,  nrow=splitcount, ncol=3)
     *   rlist[3] = isplit3   (INTSXP  matrix,  nrow=splitcount, ncol=3)
     *   rlist[4] = dnode3    (REALSXP matrix,  nrow=nodecount,  ncol=3+num_resp)
     *   rlist[5] = inode3    (INTSXP  matrix,  nrow=nodecount,  ncol=6)
     *   rlist[6] = csplit3   (INTSXP  matrix,  nrow=catcount,   ncol=maxcat)  -- optional
     *
     * All matrices are column-major (R default for allocMatrix).
     */
    try {
        if (!_result || _result->type != VECSXP)
            throw RError("rpart_c: rpart() did not return a VECSXP list");

        int nout = _result->length;

        /* [0] which */
        {
            SEXP which3 = VECTOR_ELT(_result, 0);
            if (!which3 || which3->type != INTSXP)
                throw RError("rpart_c: result[0] (which) is not INTSXP");
            int len = which3->length;
            if (which_len_out) *which_len_out = len;
            if (which_out && which_cap >= len) {
                const int *src = (const int *) which3->data;
                for (int i = 0; i < len; i++)
                    which_out[i] = src[i];
            }
        }

        /* [1] cptable */
        {
            SEXP cptable3 = VECTOR_ELT(_result, 1);
            if (!cptable3 || cptable3->type != REALSXP)
                throw RError("rpart_c: result[1] (cptable) is not REALSXP");
            int nr = cptable3->nrow;
            int nc = cptable3->ncol;
            if (cptable_nrow_out) *cptable_nrow_out = nr;
            if (cptable_ncol_out) *cptable_ncol_out = nc;
            if (cptable_out && cptable_cap >= nr * nc) {
                const double *src = (const double *) cptable3->data;
                for (int i = 0; i < nr * nc; i++)
                    cptable_out[i] = src[i];
            }
        }

        /* [2] dsplit */
        {
            SEXP dsplit3 = VECTOR_ELT(_result, 2);
            if (!dsplit3 || dsplit3->type != REALSXP)
                throw RError("rpart_c: result[2] (dsplit) is not REALSXP");
            int nr = dsplit3->nrow;   /* splitcount; ncol always 3 */
            if (dsplit_nrow_out) *dsplit_nrow_out = nr;
            if (dsplit_out && dsplit_cap >= nr * 3) {
                const double *src = (const double *) dsplit3->data;
                for (int i = 0; i < nr * 3; i++)
                    dsplit_out[i] = src[i];
            }
        }

        /* [3] isplit */
        {
            SEXP isplit3 = VECTOR_ELT(_result, 3);
            if (!isplit3 || isplit3->type != INTSXP)
                throw RError("rpart_c: result[3] (isplit) is not INTSXP");
            int nr = isplit3->nrow;   /* splitcount; ncol always 3 */
            if (isplit_nrow_out) *isplit_nrow_out = nr;
            if (isplit_out && isplit_cap >= nr * 3) {
                const int *src = (const int *) isplit3->data;
                for (int i = 0; i < nr * 3; i++)
                    isplit_out[i] = src[i];
            }
        }

        /* [4] dnode */
        {
            SEXP dnode3 = VECTOR_ELT(_result, 4);
            if (!dnode3 || dnode3->type != REALSXP)
                throw RError("rpart_c: result[4] (dnode) is not REALSXP");
            int nr = dnode3->nrow;   /* nodecount */
            int nc = dnode3->ncol;   /* 3 + num_resp */
            if (dnode_nrow_out) *dnode_nrow_out = nr;
            if (dnode_ncol_out) *dnode_ncol_out = nc;
            if (dnode_out && dnode_cap >= nr * nc) {
                const double *src = (const double *) dnode3->data;
                for (int i = 0; i < nr * nc; i++)
                    dnode_out[i] = src[i];
            }
        }

        /* [5] inode */
        {
            SEXP inode3 = VECTOR_ELT(_result, 5);
            if (!inode3 || inode3->type != INTSXP)
                throw RError("rpart_c: result[5] (inode) is not INTSXP");
            int nr = inode3->nrow;   /* nodecount; ncol always 6 */
            if (inode_nrow_out) *inode_nrow_out = nr;
            if (inode_out && inode_cap >= nr * 6) {
                const int *src = (const int *) inode3->data;
                for (int i = 0; i < nr * 6; i++)
                    inode_out[i] = src[i];
            }
        }

        /* [6] csplit (conditional) */
        if (nout >= 7) {
            SEXP csplit3 = VECTOR_ELT(_result, 6);
            if (csplit3 && csplit3 != R_NilValue && csplit3->type == INTSXP) {
                int nr = csplit3->nrow;   /* catcount */
                int nc = csplit3->ncol;   /* maxcat */
                if (has_csplit)       *has_csplit       = 1;
                if (csplit_nrow_out)  *csplit_nrow_out  = nr;
                if (csplit_ncol_out)  *csplit_ncol_out  = nc;
                if (csplit_out && csplit_cap >= nr * nc) {
                    const int *src = (const int *) csplit3->data;
                    for (int i = 0; i < nr * nc; i++)
                        csplit_out[i] = src[i];
                }
            }
        }
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free_sexp_deep(_result);
        return;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory during output extraction", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free_sexp_deep(_result);
        return;
    }
    catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free_sexp_deep(_result);
        return;
    }
    catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception during output extraction", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free_sexp_deep(_result);
        return;
    }

    /* Step 7: free the returned VECSXP tree (rpart.c heap-allocates everything) */
    free_sexp_deep(_result);
}

/* ================================================================
 * Python caller pattern:
 *
 *   import ctypes, numpy as np
 *
 *   lib = ctypes.CDLL("path/to/rpart_bundle.so")
 *   lib.rpart_c.restype  = None
 *   lib.rpart_c.argtypes = [
 *       # ncat
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       # method
 *       ctypes.c_int,
 *       # opt
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       # parms
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       # xvals
 *       ctypes.c_int,
 *       # xgrp
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       # ymat
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       # xmat
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int,
 *       # wt
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       # ny
 *       ctypes.c_int,
 *       # cost
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       # which_out
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int),
 *       # cptable_out
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
 *       # dsplit_out
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int),
 *       # isplit_out
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int),
 *       # dnode_out
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
 *       # inode_out
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int),
 *       # csplit_out
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
 *       ctypes.POINTER(ctypes.c_int),
 *       # error
 *       ctypes.c_char_p, ctypes.c_int,
 *   ]
 *
 *   n    = xmat.shape[0]
 *   nvar = xmat.shape[1]
 *   error_buf = ctypes.create_string_buffer(1024)
 *
 *   which_arr   = np.zeros(n,          dtype=np.int32)
 *   cptable_arr = np.zeros(5 * 64,     dtype=np.float64)  # generous upper bound
 *   dsplit_arr  = np.zeros(n * 3,      dtype=np.float64)
 *   isplit_arr  = np.zeros(n * 3,      dtype=np.int32)
 *   dnode_arr   = np.zeros(n * 10,     dtype=np.float64)
 *   inode_arr   = np.zeros(n * 6,      dtype=np.int32)
 *   csplit_arr  = np.zeros(n * nvar,   dtype=np.int32)
 *
 *   which_len   = ctypes.c_int(0)
 *   cptable_nr  = ctypes.c_int(0); cptable_nc = ctypes.c_int(0)
 *   dsplit_nr   = ctypes.c_int(0)
 *   isplit_nr   = ctypes.c_int(0)
 *   dnode_nr    = ctypes.c_int(0); dnode_nc   = ctypes.c_int(0)
 *   inode_nr    = ctypes.c_int(0)
 *   csplit_nr   = ctypes.c_int(0); csplit_nc  = ctypes.c_int(0)
 *   has_csplit  = ctypes.c_int(0)
 *
 *   lib.rpart_c(
 *       ncat_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), nvar,
 *       method_int,
 *       opt_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(opt_arr),
 *       parms_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(parms_arr),
 *       xvals_int,
 *       xgrp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), n,
 *       ymat_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), n * ny,
 *       xmat_colmajor.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), n, nvar,
 *       wt_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), n,
 *       ny_int,
 *       cost_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), nvar,
 *       which_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), n, ctypes.byref(which_len),
 *       cptable_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(cptable_arr),
 *           ctypes.byref(cptable_nr), ctypes.byref(cptable_nc),
 *       dsplit_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(dsplit_arr),
 *           ctypes.byref(dsplit_nr),
 *       isplit_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(isplit_arr),
 *           ctypes.byref(isplit_nr),
 *       dnode_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(dnode_arr),
 *           ctypes.byref(dnode_nr), ctypes.byref(dnode_nc),
 *       inode_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(inode_arr),
 *           ctypes.byref(inode_nr),
 *       csplit_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(csplit_arr),
 *           ctypes.byref(csplit_nr), ctypes.byref(csplit_nc), ctypes.byref(has_csplit),
 *       error_buf, 1024,
 *   )
 *   if error_buf.value:
 *       raise RuntimeError(error_buf.value.decode())
 *
 *   which   = which_arr[:which_len.value]
 *   cptable = cptable_arr[:cptable_nr.value * cptable_nc.value].reshape(
 *                 cptable_nr.value, cptable_nc.value, order='F')
 *   dsplit  = dsplit_arr[:dsplit_nr.value * 3].reshape(dsplit_nr.value, 3, order='F')
 *   isplit  = isplit_arr[:isplit_nr.value * 3].reshape(isplit_nr.value, 3, order='F')
 *   dnode   = dnode_arr[:dnode_nr.value * dnode_nc.value].reshape(
 *                 dnode_nr.value, dnode_nc.value, order='F')
 *   inode   = inode_arr[:inode_nr.value * 6].reshape(inode_nr.value, 6, order='F')
 *   if has_csplit.value:
 *       csplit = csplit_arr[:csplit_nr.value * csplit_nc.value].reshape(
 *                    csplit_nr.value, csplit_nc.value, order='F')
 * ================================================================ */

#ifdef __cplusplus
} /* extern "C" */
#endif
