/* ================================================================
 * pred_rpart_c.c — Pure C entry point for pred_rpart()
 *
 * Original R call form:
 *   .Call(C_pred_rpart,
 *         as.integer(dim(x)),
 *         as.integer(dim(frame)[1L]),
 *         as.integer(dim(fit$splits)),
 *         as.integer(if (is.null(fit$csplit)) rep(0L, 2L) else dim(fit$csplit)),
 *         as.integer(row.names(frame)),
 *         as.integer(unlist(frame[, c("n", "ncompete", "nsurrogate", "index")])),
 *         as.integer(vnum),
 *         as.double(fit$splits),
 *         as.integer(fit$csplit - 2L),
 *         as.integer((fit$control)$usesurrogate),
 *         as.double(x),
 *         as.integer(is.na(x)))
 *
 * R call site: pred.rpart.R:16
 *
 * Original C source: r2py_rpart/src/pred_rpart.c
 *
 * Parameter map (SEXP → plain C):
 * ─────────────────────────────────────────────────────────────────
 *  SEXP param   Used as in C body               Plain-C mapping         Dir
 *  ─────────    ─────────────────────────────    ─────────────────────  ────
 *  dimx         INTEGER(dimx) → int[2]: [0]=nrow,[1]=ncol of x;
 *               also asInteger(dimx)=dimx[0]  → int *dimx, int dimx_len  [in]
 *  nnode        asInteger(nnode) scalar        → int nnode               [in]
 *  nsplit       asInteger(nsplit) scalar
 *               (R passes dim(splits)[1] as    → int nsplit              [in]
 *               1-element int)
 *  dimc         INTEGER(dimc) → int[2]: [0]=nrow,[1]=ncol of csplit
 *               matrix (or [0,0] if no csplit) → int *dimc, int dimc_len [in]
 *  nnum         INTEGER(nnum) → int[nnode]    → int *nnum, int nnum_len  [in]
 *  nodes2       INTEGER(nodes2) → int[nnode*4]
 *               column-major, stride=nnode    → int *nodes2,
 *                                               int nodes2_nrow,
 *                                               int nodes2_ncol          [in]
 *  vnum         INTEGER(vnum) → int[nsplit]   → int *vnum, int vnum_len  [in]
 *  split2       REAL(split2) → double[nsplit*4]
 *               column-major, stride=nsplit   → double *split2,
 *                                               int split2_nrow,
 *                                               int split2_ncol          [in]
 *  csplit2      INTEGER(csplit2) → int[dimc[0]*dimc[1]]
 *               column-major (may be empty    → int *csplit2,
 *               when dimc[1]==0)                int csplit2_nrow,
 *                                               int csplit2_ncol         [in]
 *  usesur       INTEGER(usesur), used as *usesur (scalar)
 *                                             → int *usesur, int usesur_len [in]
 *  xdata2       REAL(xdata2) → double[dimx[0]*dimx[1]]
 *               column-major                  → double *xdata2,
 *                                               int xdata2_nrow,
 *                                               int xdata2_ncol          [in]
 *  xmiss2       INTEGER(xmiss2) → int[dimx[0]*dimx[1]]
 *               column-major                  → int *xmiss2,
 *                                               int xmiss2_nrow,
 *                                               int xmiss2_ncol          [in]
 *  ─────────────────────────────────────────────────────────────────
 *  (return)     allocVector(INTSXP, n) — 1-D integer vector, length n
 *               where n = dimx[0]            → int *where_out            [out]
 *                                              int where_len              [in]
 *  ─────────────────────────────────────────────────────────────────
 *  error_out    char *                                                    [out]
 *               Non-empty on any C++ exception.
 *  error_out_len int                                                      [in]
 *               Capacity of error_out buffer in bytes.
 *
 * NOTE: ctypes/cffi have no knowledge of C++ exceptions. All exceptions
 * are caught inside this file and written to error_out. The entry point
 * is declared noexcept to enforce this at the compiler level.
 * Python callers must check error_out after every call.
 *
 * NOTE on matrix layout: R stores matrices in column-major order. The flat
 * arrays passed here (nodes2, split2, csplit2, xdata2, xmiss2) must also be
 * column-major. The SEXP wrappers created below do NOT copy data; they point
 * directly into the caller-supplied buffers.
 *
 * NOTE on csplit2: When fit$csplit is NULL, R passes rep(0L, 2L) as dimc,
 * giving dimc[0]=0 and dimc[1]=0. In that case csplit2 may be NULL. The
 * pred_rpart0() inner function guards csplit allocation on dimc[1]>0.
 *
 * Fake headers required: fake_R.h (and transitive includes)
 * ================================================================ */

/* fake_R.h pulls in C++ standard library headers (<new>, <type_traits>, etc.)
 * that contain templates.  Templates cannot appear inside an extern "C" block.
 * Therefore all includes must precede the extern "C" opening brace. */
#include "fake_R.h"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* --- Original function declaration — C++ linkage to match compiled symbol ---
 * Placed OUTSIDE extern "C" so the C++ mangling of pred_rpart() (compiled
 * from src/pred_rpart.c with g++/-x c++) is preserved. */
extern SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
                       SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
                       SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * Input SEXP construction helpers (static, no-copy)
 *
 * These helpers wrap a caller-supplied array behind a SEXPREC node.
 * The SEXPREC is heap-allocated (malloc); the data pointer is set
 * directly to the caller's buffer — no data is copied.
 *
 * The caller retains ownership of the data array. Only the SEXPREC
 * node itself must be freed after the call (via free(node)).
 * ================================================================ */

/* make_int_scalar — wrap a single int value as a 1-element INTSXP.
 * A private int[1] buffer is allocated alongside the SEXPREC because
 * asInteger(s) reads s->data[0]. */
static inline SEXP make_int_scalar(int value) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_int_scalar: out of memory allocating SEXPREC");
    int *buf = (int *) malloc(sizeof(int));
    if (!buf) { free(s); throw RError("make_int_scalar: out of memory allocating data"); }
    buf[0]   = value;
    s->type   = INTSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = buf;
    return s;
}

/* free_int_scalar — frees both the SEXPREC node and the private int[1] buffer
 * created by make_int_scalar (unlike the no-copy helpers below whose buffers
 * are owned by the caller). */
static inline void free_int_scalar(SEXP s) {
    if (s) {
        free(s->data);
        free(s);
    }
}

/* make_int_vec — wrap int *arr (length len) as a 1-D INTSXP.
 * The SEXPREC points directly into arr; arr is NOT copied or freed here. */
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
 * The SEXPREC points directly into arr; arr is NOT copied or freed here. */
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

/* make_int_mat — wrap int *arr (nrow*ncol elements, column-major) as INTSXP.
 * The SEXPREC points directly into arr; arr is NOT copied or freed here. */
static inline SEXP make_int_mat(int *arr, int nrow, int ncol) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_int_mat: out of memory allocating SEXPREC");
    s->type   = INTSXP;
    s->length = nrow * ncol;
    s->nrow   = nrow;
    s->ncol   = ncol;
    s->data   = arr;   /* no copy — caller owns arr */
    return s;
}

/* make_real_mat — wrap double *arr (nrow*ncol elements, column-major) as REALSXP.
 * The SEXPREC points directly into arr; arr is NOT copied or freed here. */
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

/* ================================================================
 * Output SEXP extraction helpers (static, copy-out)
 *
 * These helpers read from the SEXP returned by pred_rpart() and
 * copy elements into caller-supplied output arrays.
 * ================================================================ */

/* extract_int_vec — copy up to out_len elements from an INTSXP into out.
 * Validates the SEXP type tag; throws RError on mismatch. */
static inline void extract_int_vec(SEXP s, int *out, int out_len) {
    if (!s) throw RError("extract_int_vec: NULL SEXP");
    if (s->type != INTSXP)
        throw RError("extract_int_vec: expected INTSXP but got different type");
    int copy_n = (s->length < out_len) ? s->length : out_len;
    memcpy(out, (int *) s->data, (size_t) copy_n * sizeof(int));
}

/* ================================================================
 * Entry point — noexcept: all exceptions are caught here; none may
 * escape across the C ABI boundary.
 *
 * Caller pre-conditions:
 *   - dimx        points to an int array of length dimx_len (>= 2).
 *                 dimx[0] = number of rows in x.
 *                 dimx[1] = number of columns in x.
 *   - nnode       scalar: number of nodes in the tree (= dim(frame)[1]).
 *   - nsplit      scalar: number of split rows (= dim(fit$splits)[1]).
 *   - dimc        points to an int array of length dimc_len (>= 2).
 *                 dimc[0] = nrow of csplit matrix (0 if no csplit).
 *                 dimc[1] = ncol of csplit matrix (0 if no csplit).
 *   - nnum        int[nnum_len], length == nnode.
 *   - nodes2      int[nodes2_nrow * nodes2_ncol], column-major,
 *                 nodes2_nrow == nnode, nodes2_ncol == 4.
 *   - vnum        int[vnum_len], length == nsplit (or number of split rows).
 *   - split2      double[split2_nrow * split2_ncol], column-major,
 *                 split2_nrow == nsplit, split2_ncol == 4.
 *   - csplit2     int[csplit2_nrow * csplit2_ncol], column-major.
 *                 May be NULL when dimc[1] == 0 (no categorical splits).
 *   - usesur      int[usesur_len] (>= 1), usesur[0] is the surrogate level.
 *   - xdata2      double[xdata2_nrow * xdata2_ncol], column-major,
 *                 xdata2_nrow == dimx[0], xdata2_ncol == dimx[1].
 *   - xmiss2      int[xmiss2_nrow * xmiss2_ncol], column-major,
 *                 xmiss2_nrow == dimx[0], xmiss2_ncol == dimx[1].
 *   - where_out   int[where_len], where_len >= dimx[0]. Filled on success.
 *   - error_out   char[error_out_len]. Set to '\0' on entry; filled on error.
 *   - error_out_len capacity of error_out in bytes.
 * ================================================================ */
void pred_rpart_c(
    /* inputs */
    int    *dimx,       int  dimx_len,
    int     nnode,
    int     nsplit,
    int    *dimc,       int  dimc_len,
    int    *nnum,       int  nnum_len,
    int    *nodes2,     int  nodes2_nrow,  int nodes2_ncol,
    int    *vnum,       int  vnum_len,
    double *split2,     int  split2_nrow,  int split2_ncol,
    int    *csplit2,    int  csplit2_nrow, int csplit2_ncol,
    int    *usesur,     int  usesur_len,
    double *xdata2,     int  xdata2_nrow,  int xdata2_ncol,
    int    *xmiss2,     int  xmiss2_nrow,  int xmiss2_ncol,
    /* outputs */
    int    *where_out,  int  where_len,
    /* error propagation */
    char   *error_out,  int  error_out_len
) noexcept {
    /* Step 1: zero the error buffer */
    if (error_out && error_out_len > 0) error_out[0] = '\0';

    /* Step 2: declare ArenaFrame — frees all R_alloc/ALLOC scratch on exit */
    ArenaFrame _frame;

    /* Step 3: construct SEXP wrappers for each input
     *
     * All no-copy helpers (make_int_vec, make_real_mat, etc.) point
     * s->data directly at the caller's array. Only the SEXPREC node
     * itself is malloc'd and must be freed in the catch arms and after
     * extracting results.
     *
     * make_int_scalar allocates a private int[1] buffer; its wrapper
     * (free_int_scalar) frees both the buffer and the node.
     */
    SEXP s_dimx    = nullptr;
    SEXP s_nnode   = nullptr;
    SEXP s_nsplit  = nullptr;
    SEXP s_dimc    = nullptr;
    SEXP s_nnum    = nullptr;
    SEXP s_nodes2  = nullptr;
    SEXP s_vnum    = nullptr;
    SEXP s_split2  = nullptr;
    SEXP s_csplit2 = nullptr;
    SEXP s_usesur  = nullptr;
    SEXP s_xdata2  = nullptr;
    SEXP s_xmiss2  = nullptr;

    /* Helper macro: free all input wrappers.
     * No-copy wrappers: free only the SEXPREC node (not s->data).
     * Scalar wrappers (s_nnode, s_nsplit): free node + private buffer. */
#define FREE_INPUT_WRAPPERS() do { \
    if (s_dimx)    { free(s_dimx);    s_dimx    = nullptr; } \
    if (s_nnode)   { free_int_scalar(s_nnode);   s_nnode   = nullptr; } \
    if (s_nsplit)  { free_int_scalar(s_nsplit);  s_nsplit  = nullptr; } \
    if (s_dimc)    { free(s_dimc);    s_dimc    = nullptr; } \
    if (s_nnum)    { free(s_nnum);    s_nnum    = nullptr; } \
    if (s_nodes2)  { free(s_nodes2);  s_nodes2  = nullptr; } \
    if (s_vnum)    { free(s_vnum);    s_vnum    = nullptr; } \
    if (s_split2)  { free(s_split2);  s_split2  = nullptr; } \
    if (s_csplit2) { free(s_csplit2); s_csplit2 = nullptr; } \
    if (s_usesur)  { free(s_usesur);  s_usesur  = nullptr; } \
    if (s_xdata2)  { free(s_xdata2);  s_xdata2  = nullptr; } \
    if (s_xmiss2)  { free(s_xmiss2);  s_xmiss2  = nullptr; } \
} while(0)

    try {
        /* dimx: int[2] vector; the C body reads INTEGER(dimx) as an array
         * (dimx[0]=nrow, dimx[1]=ncol) and asInteger(dimx)=dimx[0]. */
        s_dimx = make_int_vec(dimx, dimx_len);

        /* nnode: scalar int — R passes dim(frame)[1L] as a 1-element vector;
         * C body calls asInteger(nnode). Wrap as 1-element INTSXP. */
        s_nnode = make_int_scalar(nnode);

        /* nsplit: scalar int — R passes dim(fit$splits)[1L] as a 1-element
         * vector; C body calls asInteger(nsplit). Wrap as 1-element INTSXP. */
        s_nsplit = make_int_scalar(nsplit);

        /* dimc: int[2] vector; C body reads INTEGER(dimc)[0] and [1]. */
        s_dimc = make_int_vec(dimc, dimc_len);

        /* nnum: 1-D int vector, length == nnode */
        s_nnum = make_int_vec(nnum, nnum_len);

        /* nodes2: column-major int matrix, nnode rows × 4 columns.
         * C body: nodes[i] = &nodes2[nnode * i]  for i in 0..3 */
        s_nodes2 = make_int_mat(nodes2, nodes2_nrow, nodes2_ncol);

        /* vnum: 1-D int vector, length == number of splits */
        s_vnum = make_int_vec(vnum, vnum_len);

        /* split2: column-major double matrix, nsplit rows × 4 columns.
         * C body: split[i] = &split2[nsplit * i]  for i in 0..3 */
        s_split2 = make_real_mat(split2, split2_nrow, split2_ncol);

        /* csplit2: column-major int matrix, dimc[0] rows × dimc[1] cols.
         * May be NULL / empty when there are no categorical splits
         * (dimc[1] == 0). The C body guards on dimc[1] > 0 before using it.
         * When csplit2 is NULL we still allocate a SEXPREC node pointing to
         * NULL data; the C body will not dereference it in that case. */
        s_csplit2 = make_int_mat(csplit2, csplit2_nrow, csplit2_ncol);

        /* usesur: 1-element int vector; C body accesses as *usesur (pointer). */
        s_usesur = make_int_vec(usesur, usesur_len);

        /* xdata2: column-major double matrix, dimx[0] rows × dimx[1] cols.
         * C body: xdata[i] = &xdata2[i * dimx[0]]  for i in 0..dimx[1]-1 */
        s_xdata2 = make_real_mat(xdata2, xdata2_nrow, xdata2_ncol);

        /* xmiss2: column-major int matrix, dimx[0] rows × dimx[1] cols. */
        s_xmiss2 = make_int_mat(xmiss2, xmiss2_nrow, xmiss2_ncol);

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

    /* Step 4: call the original function — catch ALL exception types */
    SEXP _result = nullptr;
    try {
        _result = pred_rpart(s_dimx, s_nnode, s_nsplit, s_dimc,
                             s_nnum, s_nodes2, s_vnum, s_split2,
                             s_csplit2, s_usesur, s_xdata2, s_xmiss2);
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

    /* Step 5: extract outputs from the returned SEXP
     *
     * pred_rpart returns a 1-D INTSXP of length n (= dimx[0]).
     * Copy into caller-supplied where_out[0..where_len-1].
     */
    try {
        extract_int_vec(_result, where_out, where_len);
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

    /* Step 6: free all allocated SEXPREC wrappers
     *
     * No-copy wrappers (make_int_vec, make_real_mat, make_int_mat):
     *   free only the SEXPREC node — the caller owns the data arrays.
     *
     * Scalar wrappers (s_nnode, s_nsplit via make_int_scalar):
     *   free both the SEXPREC node and the private int[1] data buffer
     *   via free_int_scalar().
     *
     * Result SEXP (_result):
     *   pred_rpart allocates the 'where' vector with allocVector(INTSXP,n).
     *   Both the SEXPREC node and its int[n] data buffer were malloc'd by
     *   allocVector and are owned by us. Use free_sexp() to release both.
     */
    FREE_INPUT_WRAPPERS();

    if (_result) {
        free(_result->data);   /* the int[n] 'where' buffer */
        free(_result);         /* the SEXPREC node */
    }

#undef FREE_INPUT_WRAPPERS
}

/* Python caller pattern:
 *
 *   import ctypes, numpy as np
 *
 *   lib = ctypes.CDLL("path/to/rpart_with_entry_points.so")
 *   lib.pred_rpart_c.restype  = None
 *   lib.pred_rpart_c.argtypes = [
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int,   # dimx, dimx_len
 *       ctypes.c_int,                                    # nnode
 *       ctypes.c_int,                                    # nsplit
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int,   # dimc, dimc_len
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int,   # nnum, nnum_len
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int, ctypes.c_int,  # nodes2, nrow, ncol
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int,   # vnum, vnum_len
 *       ctypes.POINTER(ctypes.c_double),ctypes.c_int, ctypes.c_int,  # split2, nrow, ncol
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int, ctypes.c_int,  # csplit2, nrow, ncol
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int,   # usesur, usesur_len
 *       ctypes.POINTER(ctypes.c_double),ctypes.c_int, ctypes.c_int,  # xdata2, nrow, ncol
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int, ctypes.c_int,  # xmiss2, nrow, ncol
 *       ctypes.POINTER(ctypes.c_int),   ctypes.c_int,   # where_out, where_len
 *       ctypes.c_char_p,                ctypes.c_int,   # error_out, error_out_len
 *   ]
 *
 *   n_obs = x.shape[0]
 *   where_out  = np.zeros(n_obs, dtype=np.int32)
 *   error_buf  = ctypes.create_string_buffer(1024)
 *
 *   lib.pred_rpart_c(
 *       dimx_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(dimx_arr),
 *       int(nnode),
 *       int(nsplit),
 *       dimc_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(dimc_arr),
 *       nnum_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(nnum_arr),
 *       nodes2_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), nodes2_arr.shape[0], nodes2_arr.shape[1],
 *       vnum_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(vnum_arr),
 *       split2_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), split2_arr.shape[0], split2_arr.shape[1],
 *       csplit2_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), csplit2_arr.shape[0], csplit2_arr.shape[1],
 *       usesur_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(usesur_arr),
 *       xdata2_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), xdata2_arr.shape[0], xdata2_arr.shape[1],
 *       xmiss2_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), xmiss2_arr.shape[0], xmiss2_arr.shape[1],
 *       where_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), len(where_out),
 *       error_buf, 1024,
 *   )
 *   if error_buf.value:
 *       raise RuntimeError(error_buf.value.decode())
 */

#ifdef __cplusplus
} /* extern "C" */
#endif
