/* ================================================================
 * rpartexp2_c.c — Pure C entry point for rpartexp2()
 *
 * Original R call form:
 *   .Call(C_rpartexp2, as.double(dtimes), as.double(.Machine$double.eps))
 *   (rpart/R/rpart.exp.R, line 33)
 *
 * Parameter map (SEXP -> plain C):
 *   dtimes  (REALSXP, 1-D real vector)  -> double *dtimes, int dtimes_len  [in]
 *   eps     (REALSXP, scalar real)      -> double eps                       [in]
 *   keep    (INTSXP,  1-D int vector)   -> int *keep_out, int keep_len      [out]
 *   error_out     char *  [out]  -- non-empty on any C++ exception
 *   error_out_len int     [in]   -- capacity of error_out buffer
 *
 * Function body (rpartexp2.c):
 *   int n = LENGTH(dtimes);
 *   SEXP keep = PROTECT(allocVector(INTSXP, n));
 *   Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
 *   UNPROTECT(1);
 *   return keep;
 *
 * dtimes is accessed via REAL() with LENGTH() but no nrows/ncols -> 1-D real vector.
 * eps    is accessed via asReal() -> scalar double.
 * Return is a 1-D INTSXP of length n (same as dtimes_len).
 *
 * NOTE: ctypes/cffi have no knowledge of C++ exceptions.  All exceptions
 * are caught inside this file and written to error_out.  The entry point
 * is declared noexcept to enforce this at the compiler level.
 * Python callers must check error_out after every call.
 *
 * Fake headers required: fake_R.h (and transitive includes)
 * Original C source:     r2py_rpart/src/rpartexp2.c
 * R call sites:          rpart.exp.R:33
 * ================================================================ */

/*
 * IMPORTANT: fake_R.h pulls in C++ standard library headers (stdexcept,
 * string, new, type_traits, etc.).  These headers contain C++ templates
 * and must NOT be compiled inside an `extern "C"` block.  We therefore
 * place all #include directives BEFORE the extern "C" block, and only
 * put the function declarations and definitions inside it.
 */
#include "fake_R.h"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* --- Original function declaration — C++ linkage to match compiled symbol ---
 * Placed OUTSIDE extern "C" so the C++ mangling of rpartexp2 (which is
 * compiled from src/rpartexp2.c with g++/-x c++) is preserved.  If this
 * declaration were inside extern "C" it would expect an unmangled symbol that
 * the linker cannot find. */
extern SEXP rpartexp2(SEXP dtimes, SEXP eps);

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------
 * Input SEXP construction helpers (static, no-copy)
 *
 * make_real_vec: wraps a caller-supplied double array as a REALSXP
 *   1-D vector.  The SEXPREC node is heap-allocated; the data
 *   pointer is set directly to the caller array (no copy).
 *   The caller retains ownership of the array.
 *
 * make_real_scalar: wraps a single double value as a length-1 REALSXP.
 *   A 1-element double buffer is heap-allocated and the value is copied
 *   into it so that asReal(sexp) / REAL(sexp)[0] returns the value.
 * --------------------------------------------------------------- */

static inline SEXP make_real_vec(double *data, int len) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_vec: out of memory allocating SEXPREC");
    s->type   = REALSXP;
    s->length = len;
    s->nrow   = len;
    s->ncol   = 1;
    s->data   = data;   /* no copy — caller owns the underlying array */
    return s;
}

static inline SEXP make_real_scalar(double value) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_real_scalar: out of memory allocating SEXPREC");
    double *buf = (double *) malloc(sizeof(double));
    if (!buf) {
        free(s);
        throw RError("make_real_scalar: out of memory allocating data buffer");
    }
    buf[0]    = value;
    s->type   = REALSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = buf;
    return s;
}

/* ---------------------------------------------------------------
 * Output SEXP extraction helper (static, copy-out)
 *
 * extract_int_vec: copies INTEGER data from a 1-D INTSXP into a
 *   caller-supplied int array.  Validates that the SEXP type is
 *   INTSXP and that the output buffer is large enough.
 * --------------------------------------------------------------- */

static inline void extract_int_vec(SEXP s, int *out, int out_len) {
    if (!s || s->type != INTSXP)
        throw RError("extract_int_vec: expected INTSXP result");
    int n = s->length;
    if (n > out_len)
        throw RError("extract_int_vec: output buffer too small for result");
    int *src = INTEGER(s);
    for (int i = 0; i < n; i++) out[i] = src[i];
}

/* ---------------------------------------------------------------
 * Entry point (noexcept: all exceptions caught internally)
 *
 * Parameters:
 *   dtimes      [in]  pointer to array of death times (double, sorted unique)
 *   dtimes_len  [in]  number of elements in dtimes
 *   eps         [in]  machine epsilon (scalar double, e.g. .Machine$double.eps)
 *   keep_out    [out] caller-allocated int array, length >= dtimes_len;
 *                     receives 1 (keep) or 0 (discard) for each death time
 *   keep_len    [in]  capacity of keep_out in elements (must be >= dtimes_len)
 *   error_out     [out] null-terminated error message on failure, else ""
 *   error_out_len [in]  capacity of error_out in bytes
 *
 * Python caller pattern:
 *   import ctypes, numpy as np
 *   lib = ctypes.CDLL("rpartexp2_c.so")
 *   lib.rpartexp2_c.restype  = None
 *   lib.rpartexp2_c.argtypes = [
 *       ctypes.POINTER(ctypes.c_double), ctypes.c_int,
 *       ctypes.c_double,
 *       ctypes.POINTER(ctypes.c_int), ctypes.c_int,
 *       ctypes.c_char_p, ctypes.c_int,
 *   ]
 *   n = len(dtimes_arr)
 *   keep_arr   = np.zeros(n, dtype=np.int32)
 *   error_buf  = ctypes.create_string_buffer(1024)
 *   lib.rpartexp2_c(
 *       dtimes_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), n,
 *       float(machine_eps),
 *       keep_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), n,
 *       error_buf, 1024,
 *   )
 *   if error_buf.value:
 *       raise RuntimeError(error_buf.value.decode())
 * --------------------------------------------------------------- */

void rpartexp2_c(
    /* inputs */
    double *dtimes,     int dtimes_len,
    double  eps,
    /* outputs */
    int    *keep_out,   int keep_len,
    /* error propagation */
    char   *error_out,  int error_out_len
) noexcept {
    /* 1. Zero the error buffer immediately. */
    if (error_out && error_out_len > 0) error_out[0] = '\0';

    /* 2. RAII arena guard — frees all R_alloc/ALLOC scratch on return/throw. */
    ArenaFrame _frame;

    /* 3. Wrap plain-C inputs as fake SEXP objects.
     *    s_dtimes: points directly into caller's array (no copy).
     *    s_eps:    owns a 1-element double buffer (value copied in). */
    SEXP s_dtimes = nullptr;
    SEXP s_eps    = nullptr;

    try {
        s_dtimes = make_real_vec(dtimes, dtimes_len);
        s_eps    = make_real_scalar(eps);
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* s_dtimes->data is caller-owned; only free the SEXPREC node itself. */
        free(s_dtimes);
        /* s_eps may be partially constructed; guard each piece. */
        if (s_eps) { free(s_eps->data); free(s_eps); }
        return;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free(s_dtimes);
        if (s_eps) { free(s_eps->data); free(s_eps); }
        return;
    }

    /* 4. Call original rpartexp2 — catch ALL exception types so nothing escapes. */
    SEXP _result = nullptr;
    try {
        _result = rpartexp2(s_dtimes, s_eps);
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* s_dtimes->data is caller's array — free only the SEXPREC node. */
        free(s_dtimes);
        if (s_eps) { free(s_eps->data); free(s_eps); }
        return;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free(s_dtimes);
        if (s_eps) { free(s_eps->data); free(s_eps); }
        return;
    }
    catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free(s_dtimes);
        if (s_eps) { free(s_eps->data); free(s_eps); }
        return;
    }
    catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        free(s_dtimes);
        if (s_eps) { free(s_eps->data); free(s_eps); }
        return;
    }

    /* 5. Extract the INTSXP keep vector into caller-supplied keep_out. */
    try {
        extract_int_vec(_result, keep_out, keep_len);
    }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* still fall through to free all wrappers below */
    }

    /* 6. Free all heap-allocated SEXP wrappers.
     *    s_dtimes->data  — points into caller's array; do NOT free.
     *    s_eps->data     — 1-element buffer we allocated; free it.
     *    _result->data   — owned by allocVector inside rpartexp2; free it.
     *    _result         — SEXPREC node; free it. */
    free(s_dtimes);
    if (s_eps)    { free(s_eps->data);    free(s_eps);    }
    if (_result)  { free(_result->data);  free(_result);  }
}

#ifdef __cplusplus
} /* extern "C" */
#endif
