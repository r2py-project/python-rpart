/* ================================================================
 * interpreter_helpers_c.c — Python-callable SEXP construction helpers
 *
 * Provides four extern "C" functions that let Python (via cffi) build
 * fake SEXPREC nodes without knowing the struct layout:
 *
 *   make_real_sexp(data, length) — heap-allocates a REALSXP wrapper
 *   make_int_sexp(data, length)  — heap-allocates an INTSXP wrapper
 *   make_env_sexp()              — heap-allocates a minimal ENVSXP shell
 *   free_sexp_helper(sexp)       — frees the SEXPREC node only (not data)
 *   call_install(name)           — calls install(name) → SYMSXP pointer
 *
 * The caller-owned data buffer is never copied: the SEXPREC->data field
 * just points to the buffer supplied by Python.  The caller is responsible
 * for ensuring the buffer remains live for the duration of any C call that
 * uses the returned SEXP.
 *
 * Error reporting: all functions are noexcept.  On malloc failure a message
 * is written to a static thread_local error buffer, exposed via
 * get_make_sexp_error().  Python must call get_make_sexp_error() after each
 * call and raise RuntimeError if the returned string is non-empty.
 *
 * Fake headers required: fake_R.h (and transitive includes)
 * ================================================================ */

/* fake_R.h pulls in C++ standard library headers (<new>, <type_traits>, etc.)
 * that contain templates.  Templates cannot appear inside an extern "C" block.
 * Therefore all includes must precede the extern "C" opening brace. */
#include "fake_R.h"
#include <stdlib.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * Static thread_local error buffer for allocation failures.
 * Exposed via get_make_sexp_error() so Python can check it.
 * ================================================================ */
static thread_local char _make_sexp_error_buf[256] = {'\0'};

/* get_make_sexp_error — returns the error buffer.
 * Returns an empty string ("") when the last helper call succeeded. */
const char *get_make_sexp_error(void) noexcept {
    return _make_sexp_error_buf;
}

/* ================================================================
 * make_real_sexp — wrap a caller-owned float64 buffer as REALSXP.
 *
 * data   : pointer to a contiguous float64 array (not copied).
 * length : number of elements in the array.
 *
 * Returns a heap-allocated SEXPREC* cast to void*, or nullptr on
 * malloc failure (error message written to _make_sexp_error_buf).
 * ================================================================ */
void *make_real_sexp(void *data, int length) noexcept {
    _make_sexp_error_buf[0] = '\0';
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) {
        strncpy(_make_sexp_error_buf,
                "make_real_sexp: out of memory allocating SEXPREC",
                sizeof(_make_sexp_error_buf) - 1);
        _make_sexp_error_buf[sizeof(_make_sexp_error_buf) - 1] = '\0';
        return nullptr;
    }
    s->type   = REALSXP;
    s->length = length;
    s->nrow   = length;
    s->ncol   = 1;
    s->data   = data;   /* no copy — caller owns buffer */
    return (void *) s;
}

/* ================================================================
 * make_int_sexp — wrap a caller-owned int32 buffer as INTSXP.
 *
 * data   : pointer to a contiguous int32 array (not copied).
 * length : number of elements in the array.
 *
 * Returns a heap-allocated SEXPREC* cast to void*, or nullptr on
 * malloc failure.
 * ================================================================ */
void *make_int_sexp(void *data, int length) noexcept {
    _make_sexp_error_buf[0] = '\0';
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) {
        strncpy(_make_sexp_error_buf,
                "make_int_sexp: out of memory allocating SEXPREC",
                sizeof(_make_sexp_error_buf) - 1);
        _make_sexp_error_buf[sizeof(_make_sexp_error_buf) - 1] = '\0';
        return nullptr;
    }
    s->type   = INTSXP;
    s->length = length;
    s->nrow   = length;
    s->ncol   = 1;
    s->data   = data;   /* no copy — caller owns buffer */
    return (void *) s;
}

/* ================================================================
 * make_env_sexp — allocate a minimal ENVSXP identity shell.
 *
 * Returns a heap-allocated SEXPREC* with type=ENVSXP and data=nullptr.
 * The returned pointer is a stable unique identity key for use as a
 * rho handle in the findVarInFrame frame registry.
 *
 * On malloc failure, writes to the error buffer and returns nullptr.
 * ================================================================ */
void *make_env_sexp(void) noexcept {
    _make_sexp_error_buf[0] = '\0';
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) {
        strncpy(_make_sexp_error_buf,
                "make_env_sexp: out of memory allocating SEXPREC",
                sizeof(_make_sexp_error_buf) - 1);
        _make_sexp_error_buf[sizeof(_make_sexp_error_buf) - 1] = '\0';
        return nullptr;
    }
    s->type   = ENVSXP;
    s->length = 0;
    s->nrow   = 0;
    s->ncol   = 0;
    s->data   = nullptr;
    return (void *) s;
}

/* ================================================================
 * free_sexp_helper — free the SEXPREC node only (NOT its data buffer).
 *
 * Use this for SEXPREC nodes created by make_real_sexp / make_int_sexp
 * / make_env_sexp: those nodes do NOT own their data buffers (the buffers
 * are owned by the Python-side numpy arrays).  Freeing only the node
 * prevents a double-free of the caller's buffer.
 *
 * Contrast with free_sexp() in INTSXP.h, which frees both node AND data
 * (for SEXPs created by allocVector / allocMatrix that own their buffers).
 * ================================================================ */
void free_sexp_helper(void *sexp) noexcept {
    if (sexp) {
        free(sexp);   /* free the SEXPREC node only */
    }
}

#ifdef __cplusplus
} /* extern "C" */
#endif
