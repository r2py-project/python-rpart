# Conversion Guide: `eval`

## 1. Overview of `eval` in R API

`eval` is a macro defined in `Rinternals.h` as `#define eval Rf_eval`, aliasing the function declared as `SEXP Rf_eval(SEXP expr, SEXP rho)`. It takes an unevaluated R language object (`expr`, typically of type `LANGSXP` or `EXPRSXP`) and an R environment (`rho`, of type `ENVSXP`), executes the expression inside that environment using R's interpreter, and returns the resulting R object as a `SEXP`. In the `.Call/.External` API it is the standard mechanism for invoking user-supplied R callback expressions from within C code — the returned `SEXP` is immediately inspected with type-checking predicates (`isReal`, `isInteger`, etc.) and unwrapped with `REAL()` or `INTEGER()` to extract the underlying C array. The `.C/.Fortran` API has no equivalent: `SEXP` objects, R environments, and R's evaluator are entirely absent from that interface, making every direct use of `eval` incompatible with `.C`.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart_callback.c` | 112 | `value = eval(expr2, rho);` |
| `rpart_callback.c` | 146 | `goodness = eval(expr1, rho);` |

Both calls occur inside `rpart_callback.c`, which is the dedicated module implementing user-supplied split-function callbacks. Neither call exists in any other rpart source file.

### Variables and types involved

**Global `SEXP` state (module level, `rpart_callback.c` lines 33–35):**

- `static SEXP expr1` — an unevaluated R language object storing the user-provided "goodness of split" expression; set from the `expr1x` argument of `init_rpcallback` (`.Call`-registered at line 48).
- `static SEXP expr2` — an unevaluated R language object storing the "node value / deviance" expression; set from `expr2x`.
- `static SEXP rho` — an R environment (`ENVSXP`) that serves as both the evaluation frame and the shared data channel between C and R. C code writes numeric results into named variables within `rho` (via the `double *ydata`, `double *wdata`, `double *xdata`, `int *ndata` pointers, which are interior pointers into pre-allocated R vectors held in `rho` — obtained at init time via `R_getVar`), then calls `eval` to execute the user's expression inside that same environment, where the expression can read those updated values by name.

**Occurrence 1 — `rpart_callback.c` line 112, function `rpart_callback1`:**

- Enclosing function signature: `void rpart_callback1(int n, double *y[], double *wt, double *z)` — this is a `.C`-registered void function.
- Preceding logic (lines 96–103): fills `ydata[k]` with transposed `y` data, `wdata[i]` with case weights, and `ndata[0]` with `n`. These are interior pointers into R vectors inside `rho`, so writing them effectively updates variables visible to the user's R expression.
- `SEXP value = eval(expr2, rho)` — executes the "node value" expression; the result is expected to be a real vector of length `1 + rsave` (deviance followed by `rsave` means).
- Immediately after: `isReal(value)` type check (line 113), `LENGTH(value)` length check (line 115), `dptr = REAL(value)` unwrap (line 117), copy loop into `z[]` (lines 118–119).
- The source comment at line 111 notes: "no need to protect as no memory allocation (or error) below" — `value` is not `PROTECT`ed because no GC-triggering allocation occurs between the `eval` call and the end of the function.

**Occurrence 2 — `rpart_callback.c` line 146, function `rpart_callback2`:**

- Enclosing function signature: `void rpart_callback2(int n, int ncat, double *y[], double *wt, double *x, double *good)` — also `.C`-registered.
- Preceding logic (lines 134–142): fills `ydata`, `wdata`, `xdata`, `ndata` (with a sign-encoded `n` value to signal categorical vs. continuous splits).
- `SEXP goodness = eval(expr1, rho)` — executes the "goodness of split" expression; result is a real vector whose expected length depends on `ncat` (0 for continuous: `2*(n-1)` elements; non-zero for categorical: `2*(#categories present) - 1` elements).
- Immediately after: `isReal(goodness)` type check (line 147), `LENGTH(goodness)` length extraction (line 149), `dptr = REAL(goodness)` unwrap (line 150), conditional copy into `good[]` (lines 156–172).

### Memory management context

Neither `value` nor `goodness` is `PROTECT`ed. Both are results of `eval` calls that are immediately consumed (type-checked, length-checked, unwrapped, and copied); the source explicitly documents that no GC-triggering allocation occurs between `eval` and the end of each function, so protection is unnecessary. The expressions `expr1` and `expr2` and the environment `rho` are module-level `static SEXP` variables that were set by an earlier `.Call` to `init_rpcallback` and are implicitly protected by the R call stack for the lifetime of the rpart computation.

### Distinct implementation patterns

Both CSV rows represent a single functionally identical pattern: **evaluate a stored R language expression inside a shared R environment, type-check and length-check the returned `SEXP`, unwrap it with `REAL()`, and copy the raw `double` values into a pre-allocated C output array.** The only differences between the two calls are the specific expression variable (`expr2` vs. `expr1`), the receiving `SEXP` variable name (`value` vs. `goodness`), and the exact length constraint and copy logic applied to the result.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`eval(expr, rho)` is a call into R's interpreter from within C. It depends on three `.Call`-exclusive mechanisms that have no counterpart in the `.C` API:

1. **`SEXP` environment handle (`rho`)** — the `.C` API accepts no `SEXP` arguments of any kind. An R environment object cannot be received as a function parameter or stored as a module-level C variable under `.C`.
2. **`SEXP` language object (`expr1`, `expr2`)** — unevaluated R expressions are `SEXP` objects. They cannot be created, stored, or passed through the `.C` interface.
3. **R's evaluator** — `Rf_eval` is an R internal function that executes the R interpreter. It is not available to a function entered via `.C`.

The complete architectural change required is to **move expression evaluation out of C and into R**. The C code must be split into two layers:

- A **data-marshalling layer** that writes updated numeric data into pre-allocated shared buffers (this part is already `.C`-compatible — it is plain pointer arithmetic on `double *` and `int *` arguments).
- An **R-level orchestration layer** that calls the user's expression, collects the resulting numeric vector, and passes it back into C as a pre-allocated `double *` argument for the next step.

Because `rpart_callback1` and `rpart_callback2` are currently called as function-pointer callbacks from inside the monolithic C tree-building loop (in `rpart.c`, which calls them through the `ufcn` mechanism), moving the eval step to R requires restructuring the tree-building loop into an iterative, R-driven design. **There is no mechanical line-by-line substitution for `eval` under `.C`.**

### Why no simple substitute exists

Under `.C`, every piece of information exchanged between C and R must flow through typed C pointer arguments at the moment the `.C()` call is made. `eval` communicates in both directions through a live R environment object: C writes into `rho`'s variables before the call and reads from the returned `SEXP` after the call. This bidirectional, in-place, environment-mediated communication has no representation in the `.C` argument-passing model.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Evaluate a Stored R Expression Inside a Shared Environment and Copy Results to a C Array

- **Locations:** `rpart_callback.c` line 112 (`rpart_callback1`); `rpart_callback.c` line 146 (`rpart_callback2`)

- **Original Context (.Call):**

```c
/* rpart_callback.c:30-35 — module-level SEXP state */
static SEXP expr1;   /* user-supplied "goodness of split" expression */
static SEXP expr2;   /* user-supplied "node value / deviance" expression */
static SEXP rho;     /* shared R environment used as data channel */

/* rpart_callback.c:88-120 — rpart_callback1: node evaluation */
void
rpart_callback1(int n, double *y[], double *wt, double *z)
{
    int i, j, k;
    SEXP value;
    double *dptr;

    /* Write updated data into variables inside rho */
    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++)
        wdata[i] = wt[i];
    ndata[0] = n;

    /* Evaluate the user's R expression inside rho */
    value = eval(expr2, rho);                    /* line 112 */
    if (!isReal(value))
        error(_("return value not a vector"));
    if (LENGTH(value) != (1 + rsave))
        error(_("returned value is the wrong length"));
    dptr = REAL(value);
    for (i = 0; i <= rsave; i++)
        z[i] = dptr[i];
}

/* rpart_callback.c:126-173 — rpart_callback2: split goodness */
void
rpart_callback2(int n, int ncat, double *y[], double *wt,
                double *x, double *good)
{
    int i, j, k;
    SEXP goodness;
    double *dptr;

    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++) {
        wdata[i] = wt[i];
        xdata[i] = x[i];
    }
    ndata[0] = (ncat > 0) ? -n : n;

    /* Evaluate the user's R expression inside rho */
    goodness = eval(expr1, rho);                 /* line 146 */
    if (!isReal(goodness))
        error(_("the expression expr1 did not return a vector!"));
    j = LENGTH(goodness);
    dptr = REAL(goodness);
    if (ncat == 0) {
        if (j != 2 * (n - 1))
            error("...", j, 2 * (n - 1));
        for (i = 0; i < j; i++)
            good[i] = dptr[i];
    } else {
        good[0] = (j + 1) / 2;
        for (i = 0; i < j; i++)
            good[i + 1] = dptr[i];
    }
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Direct .C conversion of eval() is NOT possible.
 *
 * The required architectural replacement has two parts:
 *
 * Part A — C data-marshalling functions (fully .C-compatible).
 *   These functions receive the updated numeric arrays as pointer arguments
 *   and write them into the shared buffers.  No SEXP, no eval, no rho.
 */

/* Marshals data before the R-level callback1 evaluation.
 * Called from R with .C("rpcb1_write", ...) before invoking the user expr. */
void rpcb1_write(const int    *n_arg,
                 const double *y_flat,   /* ysave * n values, row-major */
                 const int    *ysave_arg,
                 const double *wt,
                 double       *ydata,    /* shared output buffer: ysave * n */
                 double       *wdata,    /* shared output buffer: n */
                 int          *ndata)    /* shared output buffer: 1 */
{
    int n     = *n_arg;
    int ysave = *ysave_arg;
    int k = 0;
    for (int i = 0; i < ysave; i++)
        for (int j = 0; j < n; j++)
            ydata[k++] = y_flat[j * ysave + i];   /* transpose */
    for (int i = 0; i < n; i++)
        wdata[i] = wt[i];
    ndata[0] = n;
}

/* Copies the eval result (already computed in R) back into the z output. */
void rpcb1_read(const double *value,    /* result of user expr evaluated in R */
                const int    *len_arg,  /* length of value — must equal 1+rsave */
                double       *z)        /* output array: rsave + 1 elements */
{
    int len = *len_arg;
    for (int i = 0; i < len; i++)
        z[i] = value[i];
}

/* Similarly for callback2 write phase */
void rpcb2_write(const int    *n_arg,
                 const int    *ncat_arg,
                 const double *y_flat,
                 const int    *ysave_arg,
                 const double *wt,
                 const double *x,
                 double       *ydata,
                 double       *wdata,
                 double       *xdata,
                 int          *ndata)
{
    int n     = *n_arg;
    int ncat  = *ncat_arg;
    int ysave = *ysave_arg;
    int k = 0;
    for (int i = 0; i < ysave; i++)
        for (int j = 0; j < n; j++)
            ydata[k++] = y_flat[j * ysave + i];
    for (int i = 0; i < n; i++) {
        wdata[i] = wt[i];
        xdata[i] = x[i];
    }
    ndata[0] = (ncat > 0) ? -n : n;
}

/* Copies the eval result for callback2 into good[] */
void rpcb2_read(const double *goodness,  /* result of user expr evaluated in R */
                const int    *j_arg,     /* LENGTH(goodness) */
                const int    *ncat_arg,
                double       *good)
{
    int j    = *j_arg;
    int ncat = *ncat_arg;
    if (ncat == 0) {
        for (int i = 0; i < j; i++)
            good[i] = goodness[i];
    } else {
        good[0] = (double)((j + 1) / 2);
        for (int i = 0; i < j; i++)
            good[i + 1] = goodness[i];
    }
}

/*
 * Part B — R-level orchestration wrapper.
 *   The tree-building loop that previously ran entirely in C must be surfaced
 *   to R, which calls the write step, evaluates the user expression, then
 *   calls the read step.  Pseudocode:
 *
 *   rpart_callback1_R <- function(n, y_flat, wt, z, rho, expr2, ysave, rsave) {
 *       # Write data into shared buffers held in rho
 *       .C("rpcb1_write",
 *          n_arg    = as.integer(n),
 *          y_flat   = as.double(y_flat),
 *          ysave_arg = as.integer(ysave),
 *          wt       = as.double(wt),
 *          ydata    = get("yback", envir = rho),
 *          wdata    = get("wback", envir = rho),
 *          ndata    = get("nback", envir = rho))
 *       # Evaluate the user expression in the shared environment
 *       value <- eval(expr2, rho)
 *       if (!is.double(value))
 *           stop("return value not a vector")
 *       if (length(value) != 1L + rsave)
 *           stop("returned value is the wrong length")
 *       # Copy result back into C output buffer
 *       result <- .C("rpcb1_read",
 *                    value   = as.double(value),
 *                    len_arg = as.integer(length(value)),
 *                    z       = as.double(z))
 *       result$z
 *   }
 */
```

- **Explanation:**

  1. **`eval(expr, rho)` has no `.C` substitute.** The call itself must be removed from C entirely. The user's expression (`expr2` or `expr1`) is now evaluated at the R level, where `eval()` is a normal R function. The C function is no longer responsible for invoking the interpreter.

  2. **The shared-environment data channel is replaced by explicit pointer arguments.** The original design wrote `ydata`, `wdata`, `xdata`, `ndata` (which are interior pointers into R vectors inside `rho`) immediately before `eval`, so the user's expression could read the updated values by name from `rho`. Under `.C`, there is no live environment. Instead, the write-phase C function (`rpcb1_write` / `rpcb2_write`) receives the data arrays as ordinary `double *` / `int *` arguments and writes into the shared buffer arrays that are also passed by pointer.

  3. **Static `SEXP` module-level variables (`expr1`, `expr2`, `rho`) are eliminated from C.** These have no representation in a `.C` function. `expr1` and `expr2` are held and evaluated entirely in R. `rho` is accessed in R with `get()`/`assign()` — standard R operations on environments that need never enter C.

  4. **`isReal(value)` and `LENGTH(value)` move to R.** These are SEXP-introspection calls. Under `.C`, type checking becomes `!is.double(value)` in R before the `.C("rpcb1_read", …)` call, and length checking becomes `length(value) != 1L + rsave` in R.

  5. **`REAL(value)` / `REAL(goodness)` become `as.double(value)` in R.** The R caller passes the result of `eval(expr2, rho)` (already a plain R numeric vector) to the read-phase `.C` function as `as.double(value)`, making it arrive in C as a `const double *` argument. No `SEXP` unwrapping is needed in C.

  6. **`PROTECT` / `UNPROTECT` are absent.** Neither `value` nor `goodness` was protected even under `.Call` (the source comments confirm this). Their removal is therefore a no-op with respect to memory management.

  7. **Architectural implication.** The tree-building loop in `rpart.c`, which currently invokes `rpart_callback1` and `rpart_callback2` through function pointers set up by the user-split-function dispatch mechanism, must be restructured as an iterative loop driven from R if these callbacks are to be ported. Each iteration that requires a user callback must return control to R, let R evaluate the expression, and re-enter C with the results. This is a significant redesign; the alternative is to keep only the callback functions under `.Call` while porting the rest of the tree-building logic to `.C`.
