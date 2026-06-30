/* ================================================================
 * init_rpcallback_c.c — Pure C entry point for init_rpcallback()
 *
 * Original R call form:
 *   .Call(C_init_rpcallback, rho, as.integer(numy), as.integer(numresp),
 *         expr1, expr2)
 *
 * R call site: rpartcallback.R:109
 *
 * Original C source: r2py_rpart/src/rpart_callback.c
 *
 * Parameter map (SEXP → plain C):
 * ─────────────────────────────────────────────────────────────────
 *  SEXP param   Used as in C body               Plain-C mapping         Dir
 *  ─────────    ─────────────────────────────    ─────────────────────  ────
 *  rhox         R environment (ENVSXP).          void *rho_ptr           [in]
 *               Category E — opaque pointer.     (SEXP cast internally)
 *               Used as rho in findVarInFrame
 *               calls via R_getVar/compat_getVar.
 *               Python must pre-populate the
 *               findVarInFrame frame registry for
 *               this rho handle with the four
 *               "back" variable SEXPs before
 *               calling init_rpcallback_c.
 *
 *  ny           asInteger(ny) → ysave (scalar).  int numy                [in]
 *               R passes as.integer(numy).
 *
 *  nr           asInteger(nr) → rsave (scalar).  int numresp             [in]
 *               R passes as.integer(numresp).
 *
 *  expr1x       R language object (LANGSXP).     void *expr1_ptr         [in]
 *               Category E — opaque pointer.     (SEXP cast internally)
 *               Stored in the static global expr1
 *               for later use by rpart_callback2
 *               at rpart_callback.c:146.
 *               Python passes the same opaque
 *               handle it records for dispatching
 *               the eval() callback.
 *
 *  expr2x       R language object (LANGSXP).     void *expr2_ptr         [in]
 *               Category E — opaque pointer.     (SEXP cast internally)
 *               Stored in the static global expr2
 *               for later use by rpart_callback1
 *               at rpart_callback.c:112.
 *
 *  (return)     R_NilValue — init_rpcallback()   (none)                  —
 *               returns NULL; it only initialises
 *               the static globals rho, ysave,
 *               rsave, expr1, expr2, ydata,
 *               wdata, xdata, ndata.
 *               No output array is needed.
 *
 * ─────────────────────────────────────────────────────────────────
 *  error_out    char *                                                    [out]
 *               Non-empty on any C++ exception.
 *  error_out_len int                                                      [in]
 *               Capacity of error_out buffer in bytes.
 *
 * ─────────────────────────────────────────────────────────────────
 *
 * CATEGORY E — R INTERPRETER ITEMS
 * ----------------------------------
 * Three of the five SEXP parameters are Category E R interpreter items
 * that cannot be constructed from plain-C data alone:
 *
 *   rho    — R environment (ENVSXP).  Python must:
 *            (a) allocate an opaque environment handle (e.g. via
 *                make_env_sexp() — see fake_R.h Python integration notes);
 *            (b) register the install() stub via register_install_fn();
 *            (c) register the findVarInFrame() stub via
 *                register_findVarInFrame_fn();
 *            (d) register the findVar() stub via register_findVar_fn();
 *            (e) populate the findVarInFrame frame registry for that
 *                rho handle with four SEXP entries:
 *                  "yback" → REALSXP wrapping a float64 array of length
 *                            n_obs * numy
 *                  "wback" → REALSXP wrapping a float64 array of length
 *                            n_obs
 *                  "xback" → REALSXP wrapping a float64 array of length
 *                            n_obs
 *                  "nback" → INTSXP wrapping an int32 array of length 1
 *
 *   expr1_ptr — opaque SEXP handle for the "split goodness" expression
 *               (consumed by rpart_callback2 / eval(expr1, rho)).
 *               Python must create a stable pointer-sized identity value
 *               and record it so the eval() callback can dispatch on it.
 *               May be nullptr/NULL if user-defined splits are not needed
 *               (method != 4); init_rpcallback() stores it without
 *               dereferencing.
 *
 *   expr2_ptr — opaque SEXP handle for the "node evaluation" expression
 *               (consumed by rpart_callback1 / eval(expr2, rho)).
 *               Same requirements as expr1_ptr.
 *
 * See R_getVar.h (Python-side usage note) for the complete step-by-step
 * registration guide including ctypes code.
 *
 * NOTE: init_rpcallback() is only needed for method=4 (user-defined
 * splits).  Standard rpart() calls (anova, poisson, class, exp) never
 * invoke it.
 *
 * NOTE: ctypes/cffi have no knowledge of C++ exceptions. All exceptions
 * are caught inside this file and written to error_out. The entry point
 * is declared noexcept to enforce this at the compiler level.
 * Python callers must check error_out after every call.
 *
 * NOTE: After init_rpcallback_c returns without error, the static globals
 * inside rpart_callback.c (rho, ysave, rsave, expr1, expr2, ydata, wdata,
 * xdata, ndata) are initialised and valid until the next call to
 * init_rpcallback_c or until the shared library is unloaded.
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
 * Placed OUTSIDE extern "C" so the C++ mangling of init_rpcallback() (compiled
 * from src/rpart_callback.c with g++/-x c++) is preserved. */
extern SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr,
                             SEXP expr1x, SEXP expr2x);

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * Input SEXP construction helpers (static, no-copy)
 *
 * make_int_scalar — wrap a single int value as a 1-element INTSXP.
 * A private int[1] buffer is malloc'd alongside the SEXPREC because
 * asInteger(s) reads s->data[0].
 * ================================================================ */

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

/* free_int_scalar — frees both the SEXPREC node and the private int[1] buffer
 * created by make_int_scalar. */
static inline void free_int_scalar(SEXP s) {
    if (s) {
        free(s->data);
        free(s);
    }
}

/* make_opaque_sexp — wrap an opaque Python-supplied pointer as a minimal
 * SEXPREC shell of the requested type.
 *
 * Purpose: rho, expr1x, and expr2x are Category E R interpreter items.
 * The original init_rpcallback() body only STORES these pointers (it never
 * dereferences them beyond passing them to install/findVarInFrame callbacks
 * for rho, or storing them in module-level statics for later eval() calls
 * for expr1/expr2).  Therefore we only need a SEXPREC node whose ->data
 * field points to the caller-supplied opaque handle; no data is copied.
 *
 * sexp_type should be:
 *   ENVSXP  (4) for rho
 *   LANGSXP (6) for expr1 and expr2
 *
 * The caller-supplied ptr is passed as void * and stored in s->data.
 * The SEXPREC node is heap-allocated and must be freed (via free()) after
 * the call; the pointed-to data is owned by the caller and is not freed. */
static inline SEXP make_opaque_sexp(void *ptr, SEXPTYPE sexp_type) {
    SEXPREC *s = (SEXPREC *) malloc(sizeof(SEXPREC));
    if (!s) throw RError("make_opaque_sexp: out of memory allocating SEXPREC");
    s->type   = sexp_type;
    s->length = 0;
    s->nrow   = 0;
    s->ncol   = 0;
    s->data   = ptr;   /* no copy — caller owns ptr */
    return s;
}

/* ================================================================
 * Entry point — noexcept: all exceptions are caught here; none may
 * escape across the C ABI boundary.
 *
 * Caller pre-conditions:
 *   - rho_ptr    opaque SEXP handle (void *) for the R environment.
 *                Must be the same pointer registered in the
 *                findVarInFrame frame registry.  See Category E notes
 *                in the file header and in R_getVar.h for the full
 *                setup protocol.
 *   - numy       scalar int: number of y columns (ysave in C source).
 *                Corresponds to R's as.integer(numy).
 *   - numresp    scalar int: length of the eval return vector minus 1
 *                (rsave in C source).
 *                Corresponds to R's as.integer(numresp).
 *   - expr1_ptr  opaque SEXP handle (void *) for the split-goodness
 *                expression.  Recorded by init_rpcallback in the static
 *                global expr1; later passed to eval(expr1, rho) inside
 *                rpart_callback2.  May be NULL if method != 4.
 *   - expr2_ptr  opaque SEXP handle (void *) for the node-evaluation
 *                expression.  Recorded in static global expr2; later
 *                passed to eval(expr2, rho) inside rpart_callback1.
 *                May be NULL if method != 4.
 *   - error_out  char[error_out_len]. Set to '\0' on entry; filled on error.
 *   - error_out_len  capacity of error_out in bytes.
 *
 * Post-conditions on success (error_out[0] == '\0'):
 *   The static globals inside rpart_callback.c are populated:
 *     rho    <- rho_ptr  (ENVSXP handle used by eval/findVarInFrame)
 *     ysave  <- numy
 *     rsave  <- numresp
 *     expr1  <- expr1_ptr
 *     expr2  <- expr2_ptr
 *     ydata  <- REAL(findVarInFrame(rho, install("yback")))
 *     wdata  <- REAL(findVarInFrame(rho, install("wback")))
 *     xdata  <- REAL(findVarInFrame(rho, install("xback")))
 *     ndata  <- INTEGER(findVarInFrame(rho, install("nback")))
 *
 * ================================================================ */
void init_rpcallback_c(
    /* inputs */
    void  *rho_ptr,
    int    numy,
    int    numresp,
    void  *expr1_ptr,
    void  *expr2_ptr,
    /* error propagation */
    char  *error_out,
    int    error_out_len
) noexcept {
    /* Step 1: zero the error buffer */
    if (error_out && error_out_len > 0) error_out[0] = '\0';

    /* Step 2: declare ArenaFrame — frees all R_alloc/ALLOC scratch on exit.
     * init_rpcallback() itself does not perform arena allocations, but it is
     * compiled in the same translation unit (rpart_callback.c) as
     * rpart_callback1() and rpart_callback2().  The ArenaFrame guard is a
     * standard precautionary measure for the entire callback subsystem. */
    ArenaFrame _frame;

    /* Step 3: construct SEXP wrappers for each input.
     *
     * BUGFIX: rho_ptr/expr1_ptr/expr2_ptr must be passed through to
     * init_rpcallback() with their pointer IDENTITY preserved, because:
     *   - Python registers rho_ptr as the key into its findVarInFrame
     *     frame registry (_frame_registry[rho_ptr] = {...}) BEFORE this
     *     call, and later receives whatever pointer init_rpcallback()
     *     hands to findVarInFrame(rho, sym) as the lookup key.
     *   - Python similarly dispatches eval(expr, rho) by comparing the
     *     incoming expr pointer against the expr1_ptr/expr2_ptr identities
     *     it recorded when rpartcallback() was set up.
     * make_opaque_sexp() allocates a NEW SEXPREC node whose ->data field
     * points at the original pointer -- but init_rpcallback() stores and
     * later passes around the WRAPPER node itself (rho = rhox; expr1 =
     * expr1x; ...), not rhox->data. That substitutes a fresh address that
     * was never registered with Python, so every findVarInFrame/eval
     * lookup misses and rpart_callback.c's compat_getVar always raises
     * "variable not found". Since these three parameters are Category E
     * opaque handles that init_rpcallback() never dereferences as actual
     * SEXPREC structs (see R_getVar.h's own documentation: "(SEXP cast
     * internally)"), a direct reinterpret-cast preserves identity and is
     * sufficient -- no allocation needed, and therefore nothing to free
     * for these three afterwards. */
    SEXP s_rhox   = (SEXP) rho_ptr;
    SEXP s_ny     = nullptr;
    SEXP s_nr     = nullptr;
    SEXP s_expr1  = (SEXP) expr1_ptr;
    SEXP s_expr2  = (SEXP) expr2_ptr;

    /* Helper macro: free all input wrappers.
     * make_int_scalar wrappers (s_ny, s_nr): free node + private int[1] buffer.
     * s_rhox/s_expr1/s_expr2 are the caller's raw pointers (see BUGFIX note
     * above) -- not separately heap-allocated here, so must NOT be freed. */
#define FREE_INPUT_WRAPPERS() do { \
    if (s_ny)    { free_int_scalar(s_ny); s_ny    = nullptr; } \
    if (s_nr)    { free_int_scalar(s_nr); s_nr    = nullptr; } \
} while(0)

    try {
        /* ny: scalar int.  init_rpcallback calls asInteger(ny) → ysave.
         * Wrapped as a 1-element INTSXP with a private int[1] data buffer. */
        s_ny = make_int_scalar(numy);

        /* nr: scalar int.  init_rpcallback calls asInteger(nr) → rsave. */
        s_nr = make_int_scalar(numresp);

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
     *
     * init_rpcallback() execution path:
     *   rho = rhox;                          (stores ENVSXP handle)
     *   ysave = asInteger(ny);               (reads s_ny->data[0])
     *   rsave = asInteger(nr);               (reads s_nr->data[0])
     *   expr1 = expr1x;                      (stores LANGSXP handle)
     *   expr2 = expr2x;                      (stores LANGSXP handle)
     *   stemp = R_getVar(install("yback"), rho, FALSE);  ydata = REAL(stemp);
     *   stemp = R_getVar(install("wback"), rho, FALSE);  wdata = REAL(stemp);
     *   stemp = R_getVar(install("xback"), rho, FALSE);  xdata = REAL(stemp);
     *   stemp = R_getVar(install("nback"), rho, FALSE);  ndata = INTEGER(stemp);
     *   return R_NilValue;
     *
     * The R_getVar calls expand to compat_getVar which calls:
     *   install(name)          → g_install_fn callback (Category E)
     *   findVarInFrame(rho, sym) → g_findVarInFrame_fn callback (Category E)
     * Both must be registered before this call or RError is thrown. */
    SEXP _result = nullptr;
    try {
        _result = init_rpcallback(s_rhox, s_ny, s_nr, s_expr1, s_expr2);
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

    /* Step 5: no output extraction needed.
     *
     * init_rpcallback() returns R_NilValue — a sentinel SEXP representing
     * NULL.  All meaningful work (initialising static globals ydata, wdata,
     * xdata, ndata) is a side effect inside rpart_callback.c.
     * The returned _result is R_NilValue (a non-heap function-static SEXP);
     * it must NOT be freed. */

    /* Step 6: free all heap-allocated SEXPREC wrapper nodes.
     *
     * make_int_scalar wrappers (s_ny, s_nr):
     *   free_int_scalar() releases the SEXPREC node AND the private int[1]
     *   data buffer.
     *
     * make_opaque_sexp wrappers (s_rhox, s_expr1, s_expr2):
     *   Only the SEXPREC node is heap-allocated (via malloc in
     *   make_opaque_sexp).  The s->data field points to the Python-supplied
     *   opaque pointer and must NOT be freed here.
     *
     * _result is R_NilValue (function-static sentinel, not heap-allocated):
     *   do NOT free it.
     */
    FREE_INPUT_WRAPPERS();

    /* _result is R_NilValue — not heap-allocated, nothing to free. */
    (void) _result;

#undef FREE_INPUT_WRAPPERS
}

/* Python caller pattern:
 *
 *   import ctypes
 *   import numpy as np
 *
 *   lib = ctypes.CDLL("path/to/rpart_with_entry_points.so")
 *
 *   # ----------------------------------------------------------------
 *   # Step 1: Retrieve R_UnboundValue sentinel (required by findVarInFrame).
 *   # ----------------------------------------------------------------
 *   lib.get_R_UnboundValue.restype  = ctypes.c_void_p
 *   lib.get_R_UnboundValue.argtypes = []
 *   R_UNBOUND = lib.get_R_UnboundValue()
 *
 *   # ----------------------------------------------------------------
 *   # Step 2: Register install() stub.
 *   # ----------------------------------------------------------------
 *   _symbol_handles = {}
 *   _symbol_nodes   = {}
 *
 *   InstallFnType = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
 *   def py_install(name_bytes):
 *       name = name_bytes.decode()
 *       if name not in _symbol_handles:
 *           node = (ctypes.c_char * 1)()
 *           _symbol_handles[name] = ctypes.cast(node, ctypes.c_void_p).value
 *           _symbol_nodes[name] = node
 *       return _symbol_handles[name]
 *
 *   _install_cb = InstallFnType(py_install)
 *   lib.register_install_fn.restype  = None
 *   lib.register_install_fn.argtypes = [InstallFnType]
 *   lib.register_install_fn(_install_cb)
 *
 *   # ----------------------------------------------------------------
 *   # Step 3: Allocate "back" arrays.
 *   # ----------------------------------------------------------------
 *   n_obs   = 100        # number of observations
 *   numy    = 1          # number of y columns
 *   numresp = 1          # length of eval return - 1
 *
 *   yback_arr = np.zeros(n_obs * numy,  dtype=np.float64)
 *   wback_arr = np.ones(n_obs,          dtype=np.float64)
 *   xback_arr = np.zeros(n_obs,         dtype=np.float64)
 *   nback_arr = np.array([0],           dtype=np.int32)
 *
 *   # ----------------------------------------------------------------
 *   # Step 4: Wrap "back" arrays as fake SEXPs.
 *   #
 *   # make_real_sexp / make_int_sexp are helpers exported by the fake
 *   # header infrastructure (e.g. provided by a utility source file
 *   # compiled alongside the rpart sources).  Alternatively, build them
 *   # using ctypes structures that match SEXPREC layout.
 *   # ----------------------------------------------------------------
 *   SEXP = ctypes.c_void_p
 *
 *   lib.make_real_sexp.restype  = SEXP
 *   lib.make_real_sexp.argtypes = [ctypes.c_void_p, ctypes.c_int]
 *   lib.make_int_sexp.restype   = SEXP
 *   lib.make_int_sexp.argtypes  = [ctypes.c_void_p, ctypes.c_int]
 *
 *   sexp_y = lib.make_real_sexp(
 *       yback_arr.ctypes.data_as(ctypes.c_void_p), yback_arr.size)
 *   sexp_w = lib.make_real_sexp(
 *       wback_arr.ctypes.data_as(ctypes.c_void_p), wback_arr.size)
 *   sexp_x = lib.make_real_sexp(
 *       xback_arr.ctypes.data_as(ctypes.c_void_p), xback_arr.size)
 *   sexp_n = lib.make_int_sexp(
 *       nback_arr.ctypes.data_as(ctypes.c_void_p), nback_arr.size)
 *
 *   # ----------------------------------------------------------------
 *   # Step 5: Create opaque rho handle and populate the frame registry.
 *   # ----------------------------------------------------------------
 *   rho_node = (ctypes.c_char * 1)()
 *   rho_ptr  = ctypes.cast(rho_node, ctypes.c_void_p).value
 *
 *   _frame_registry = {}
 *
 *   FindVarInFrameFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)
 *   def py_findVarInFrame(rho_p, sym_p):
 *       frame = _frame_registry.get(rho_p, {})
 *       val = frame.get(sym_p)
 *       return R_UNBOUND if val is None else val
 *
 *   _findVarInFrame_cb = FindVarInFrameFnType(py_findVarInFrame)
 *   lib.register_findVarInFrame_fn.restype  = None
 *   lib.register_findVarInFrame_fn.argtypes = [FindVarInFrameFnType]
 *   lib.register_findVarInFrame_fn(_findVarInFrame_cb)
 *
 *   FindVarFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)
 *   def py_findVar(sym_p, rho_p):
 *       return R_UNBOUND    # conservative; inherits=TRUE never reached
 *   _findVar_cb = FindVarFnType(py_findVar)
 *   lib.register_findVar_fn.restype  = None
 *   lib.register_findVar_fn.argtypes = [FindVarFnType]
 *   lib.register_findVar_fn(_findVar_cb)
 *
 *   _frame_registry[rho_ptr] = {
 *       py_install(b"yback"): sexp_y,
 *       py_install(b"wback"): sexp_w,
 *       py_install(b"xback"): sexp_x,
 *       py_install(b"nback"): sexp_n,
 *   }
 *
 *   # ----------------------------------------------------------------
 *   # Step 6: Create opaque expr1/expr2 handles.
 *   #
 *   # These are unique pointer-sized identity values.  Python records
 *   # them so the eval() callback can dispatch on expr_ptr.
 *   # For method != 4 (no user-defined splits), pass None (nullptr).
 *   # ----------------------------------------------------------------
 *   expr1_node = (ctypes.c_char * 1)()
 *   expr2_node = (ctypes.c_char * 1)()
 *   expr1_ptr  = ctypes.cast(expr1_node, ctypes.c_void_p).value
 *   expr2_ptr  = ctypes.cast(expr2_node, ctypes.c_void_p).value
 *   _expr1_handle = expr1_ptr   # record for eval() dispatcher
 *   _expr2_handle = expr2_ptr
 *
 *   # ----------------------------------------------------------------
 *   # Step 7: Call init_rpcallback_c.
 *   # ----------------------------------------------------------------
 *   lib.init_rpcallback_c.restype  = None
 *   lib.init_rpcallback_c.argtypes = [
 *       ctypes.c_void_p,   # rho_ptr
 *       ctypes.c_int,      # numy
 *       ctypes.c_int,      # numresp
 *       ctypes.c_void_p,   # expr1_ptr
 *       ctypes.c_void_p,   # expr2_ptr
 *       ctypes.c_char_p,   # error_out
 *       ctypes.c_int,      # error_out_len
 *   ]
 *
 *   error_buf = ctypes.create_string_buffer(1024)
 *   lib.init_rpcallback_c(
 *       rho_ptr,
 *       numy,
 *       numresp,
 *       expr1_ptr,   # or None if method != 4
 *       expr2_ptr,   # or None if method != 4
 *       error_buf,
 *       1024,
 *   )
 *   if error_buf.value:
 *       raise RuntimeError(error_buf.value.decode())
 *
 *   # After a successful call, the C statics are initialised:
 *   #   rho, ysave, rsave, expr1, expr2 are set.
 *   #   ydata/wdata/xdata/ndata point into yback/wback/xback/nback arrays.
 *   # rpart() with method=4 can now be called.
 */

#ifdef __cplusplus
} /* extern "C" */
#endif
