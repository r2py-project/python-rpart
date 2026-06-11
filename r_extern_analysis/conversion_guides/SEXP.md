# Conversion Guide: `SEXP`

## 1. Overview of `SEXP` in R API

`SEXP` is a pointer type defined in `Rinternals.h` as `typedef struct SEXPREC *SEXP`. It is R's universal handle for every R object (integers, doubles, character strings, lists, language objects, environments, etc.) managed by the garbage collector. In the `.Call/.External` API, all function arguments arrive as `SEXP` values and return values must be `SEXP`; accessor macros such as `INTEGER()`, `REAL()`, `VECTOR_ELT()`, and `CHAR()` unwrap the opaque pointer to a typed C pointer that can be used for computation. Under the `.C/.Fortran` API, `SEXP` is entirely absent: functions must be `void`-returning and communicate exclusively through basic C pointer types (`int *`, `double *`, etc.), with all memory pre-allocated in R before the call.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `init.c` | 6 | `SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);` |
| `init.c` | 7 | `SEXP rpartexp2(SEXP dtimes, SEXP seps);` |
| `init.c` | 8–10 | `SEXP pred_rpart(SEXP dimx, …, SEXP xmiss2);` |
| `pred_rpart.c` | 133–136 | Function definition: `SEXP pred_rpart(SEXP dimx, …, SEXP xmiss2)` |
| `pred_rpart.c` | 139 | `SEXP where = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 40–43 | Function definition: `SEXP rpart(SEXP ncat2, …, SEXP cost2)` |
| `rpart.c` | 64 | `SEXP which3, cptable3, dsplit3, isplit3, csplit3 = R_NilValue, dnode3, inode3;` |
| `rpart.c` | 327 | `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` |
| `rpart.c` | 328 | `SEXP rname = allocVector(STRSXP, nout);` |
| `rpart_callback.c` | 20 | `static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)` |
| `rpart_callback.c` | 33–35 | `static SEXP expr1; static SEXP expr2; static SEXP rho;` |
| `rpart_callback.c` | 47–48 | Function definition: `SEXP init_rpcallback(SEXP rhox, …, SEXP expr2x)` |
| `rpart_callback.c` | 51 | `SEXP stemp;` |
| `rpart_callback.c` | 92 | `SEXP value;` — holds result of `eval(expr2, rho)` |
| `rpart_callback.c` | 131 | `SEXP goodness;` — holds result of `eval(expr1, rho)` |
| `rpartexp2.c` | 43–44 | Function definition: `SEXP rpartexp2(SEXP dtimes, SEXP eps)` |
| `rpartexp2.c` | 47 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` |
| `rpartproto.h` | 39–40 | Prototype: `SEXP rpart(…);` |
| `rpartproto.h` | 57–59 | Prototype: `SEXP xpred(…);` |
| `xpred.c` | 33–37 | Function definition: `SEXP xpred(SEXP ncat2, …, SEXP nresp2)` |
| `xpred.c` | 63 | `SEXP predict2;` — output double vector |

### Data types and memory management

All SEXP usages in this codebase fall into five functional roles:

1. **Function argument type** — every `.Call`-registered function receives its inputs as `SEXP`. Scalars (`int`, `double`) are unpacked via `asInteger(s)` or `asReal(s)`; vectors are unwrapped to `int *` via `INTEGER(s)` or to `double *` via `REAL(s)`.
2. **Output vector / matrix allocation** — `SEXP` variables hold GC-managed output buffers created by `PROTECT(allocVector(…))` or `PROTECT(allocMatrix(…))`. Types seen: `INTSXP` (integer), `REALSXP` (double), `VECSXP` (list), `STRSXP` (character).
3. **Return-list assembly** — `rlist` (a `VECSXP`) is built with `SET_VECTOR_ELT` and named with `SET_STRING_ELT`/`mkChar`; the entire list is the function's return value.
4. **Callback / environment handles** — in `rpart_callback.c`, module-level `static SEXP` variables (`expr1`, `expr2`, `rho`) store R language objects (expressions and an environment) that are later evaluated with `eval(expr, rho)` inside callback functions.
5. **Temporary working handles** — `SEXP stemp`, `SEXP value`, `SEXP goodness` are local variables that receive results of `R_getVar`, `eval`, or other API calls and are immediately unwrapped via `REAL()` / `INTEGER()` / `LENGTH()`.

### Distinct implementation patterns

1. **Scalar input unpacking** — `asInteger(sexp)` / `asReal(sexp)` on single-element input `SEXP` arguments.
2. **Vector input unwrapping** — `INTEGER(sexp)` / `REAL(sexp)` on multi-element input `SEXP` arguments to obtain a raw pointer.
3. **Output buffer allocation (1-D)** — `SEXP out = PROTECT(allocVector(TYPE, n)); … return out;`
4. **Output buffer allocation (2-D)** — `SEXP out = PROTECT(allocMatrix(TYPE, nrow, ncol)); …`
5. **Named-list return value** — `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` combined with `SET_VECTOR_ELT` / `SET_STRING_ELT`.
6. **Environment / expression callbacks** — `static SEXP` globals holding R objects that require `eval()` against an R environment; cannot be trivially mapped to `.C`.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

The `.C` API forbids `SEXP` everywhere: functions must be `void`-returning and their argument list may only contain basic C pointer types (`int *`, `double *`, `char **`). The complete set of transformations required is:

1. **Change function signature.** Replace `SEXP func(SEXP arg1, …)` with `void func(const type1 *arg1, …)`. Every `SEXP` input argument becomes a typed C pointer whose element type is determined by how the argument is used inside the function (`asInteger` → `const int *`, `asReal` → `const double *`, `INTEGER` → `const int *`, `REAL` → `const double *`).

2. **Move output allocation to R.** Every internal `allocVector` / `allocMatrix` call is replaced by a pre-allocated output argument (e.g., `int *out`) that is passed in from the R side as `integer(n)` or `double(n)`. `PROTECT` / `UNPROTECT` are removed entirely; R's GC automatically protects the caller's vectors for the duration of the `.C` call.

3. **Remove SEXP accessor macros.** `INTEGER(s)` and `REAL(s)` become direct use of the pointer argument. `asInteger(s)` becomes `s[0]` and `asReal(s)` becomes `s[0]` (scalars arrive as single-element arrays under `.C`). `LENGTH(s)` must be replaced by an explicit `int *n` argument passed from R.

4. **Replace named-list return values.** The `.C` API has no equivalent of R's named list. Each output field that was a `VECSXP` element must become a separate `int *` or `double *` output argument. The R caller assembles the named list after the `.C` call returns.

5. **Callback / environment patterns cannot use `.C`.** Code in `rpart_callback.c` that stores `SEXP expr1/expr2/rho` and calls `eval()` depends fundamentally on R's evaluator and cannot be expressed in `.C`. These routines must remain as `.Call` functions or be reimplemented by moving the R-level evaluation to the R caller and passing only numeric results down into C.

6. **Register argument types.** Each converted function must provide an `R_NativePrimitiveArgType[]` array in the `R_CMethodDef` registration table, using `INTSXP` for `int *` arguments and `REALSXP` for `double *` arguments.

This approach is `.C`-compatible because the `.C` dispatcher communicates exclusively through typed C pointers; all R-object-level operations are lifted to the R side.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Function Signature — SEXP Inputs Unpacked as Scalars

- **Locations:** `pred_rpart.c` line 133; `rpartexp2.c` line 43; `xpred.c` line 33; `rpart.c` line 40

- **Original Context (.Call):**

```c
/* pred_rpart.c:133-138 — scalar extracted via asInteger */
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
                SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
                SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2)
{
    int n = asInteger(dimx);   /* scalar extraction */
    /* ... */
}

/* rpartexp2.c:43-48 — length extracted via LENGTH */
SEXP rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);    /* length extraction */
    double scalar_eps = asReal(eps);
    /* ... */
}
```

- **C/C++ Equivalent (.C):**

```c
/* Every SEXP input becomes a typed C pointer.
 * Scalars arrive as single-element arrays: scalar = arg[0].
 * LENGTH(sexp) must become an explicit int *n argument. */

void pred_rpart_c(const int    *n,        /* was: asInteger(dimx)   */
                  const int    *dimx,     /* INTEGER(dimx) contents */
                  const int    *nnode,
                  const int    *nsplit,
                  const int    *dimc,
                  const int    *nnum,
                  const int    *nodes2,
                  const int    *vnum,
                  const double *split2,
                  const int    *csplit2,
                  const int    *usesur,
                  const double *xdata2,
                  const int    *xmiss2,
                  int          *where)   /* output, pre-allocated */
{
    /* n[0] replaces asInteger(dimx) */
    pred_rpart0(dimx, nnode[0], nsplit[0], dimc, nnum, nodes2,
                vnum, split2, csplit2, usesur, xdata2, xmiss2,
                where);
}

void rpartexp2_c(const double *dtimes,
                 const int    *n,        /* was: LENGTH(dtimes)  */
                 const double *eps,      /* was: asReal(eps)     */
                 int          *keep)     /* output, pre-allocated */
{
    Rpartexp2(n[0], dtimes, eps[0], keep);
}
```

- R-side call:

```r
n <- nrow(xdata)
result <- .C("pred_rpart_c",
             n       = as.integer(n),
             dimx    = as.integer(c(n, ncol(xdata))),
             nnode   = as.integer(nnode),
             # ... remaining integer/double args ...
             where   = integer(n))
```

- **Explanation:**
  - `SEXP dimx` (used only for `asInteger(dimx)`) collapses to `const int *n` where `n[0]` carries the scalar value.
  - `SEXP dtimes` (used for both `LENGTH` and `REAL`) splits into two arguments: `const int *n` for the length and `const double *dtimes` for the data.
  - `asInteger(s)` becomes `s[0]`; `asReal(s)` becomes `s[0]`; `INTEGER(s)` / `REAL(s)` become the pointer argument directly.
  - The function return type changes from `SEXP` to `void`; the output data is now in the pre-allocated `where` / `keep` argument.

---

### Pattern: Output Buffer Allocation (1-D Integer Vector)

- **Locations:** `pred_rpart.c` line 139; `rpartexp2.c` line 47

- **Original Context (.Call):**

```c
/* pred_rpart.c:139-146 */
SEXP where = PROTECT(allocVector(INTSXP, n));
pred_rpart0(/* … */, INTEGER(where));
UNPROTECT(1);
return where;

/* rpartexp2.c:47-50 */
SEXP keep = PROTECT(allocVector(INTSXP, n));
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
UNPROTECT(1);
return keep;
```

- **C/C++ Equivalent (.C):**

```c
/* The allocation moves to R; the C function receives the pre-filled pointer. */
void pred_rpart_c(/* input args … */, int *where /* pre-allocated: integer(n) */)
{
    /* INTEGER(where) -> where directly; no PROTECT/UNPROTECT */
    pred_rpart0(/* … */, where);
}

void rpartexp2_c(const double *dtimes, const int *n,
                 const double *eps, int *keep /* pre-allocated: integer(*n) */)
{
    Rpartexp2(n[0], dtimes, eps[0], keep);
}
```

- R-side call:

```r
# Allocate output on the R side before calling .C
n <- as.integer(length(dtimes))
result <- .C("rpartexp2_c",
             dtimes = as.double(dtimes),
             n      = n,
             eps    = as.double(eps),
             keep   = integer(n))
keep_vec <- result$keep
```

- **Explanation:**
  - `PROTECT(allocVector(INTSXP, n))` is replaced by `integer(n)` in R passed as an extra argument.
  - `PROTECT` / `UNPROTECT(1)` are removed; R's GC protects the caller's vector automatically.
  - `INTEGER(where)` (unwrapping `SEXP -> int *`) disappears; `where` is already `int *`.
  - The `return where;` statement is removed; the caller reads the output from `result$where`.

---

### Pattern: Named-List Return Value (VECSXP + STRSXP)

- **Locations:** `rpart.c` lines 327–348

- **Original Context (.Call):**

```c
/* rpart.c:326-348 — build a named list of 6 or 7 output SEXPs */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
SET_VECTOR_ELT(rlist, 0, which3);    SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);  SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);   SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);   SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);    SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);    SET_STRING_ELT(rname, 5, mkChar("inode"));
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

- **C/C++ Equivalent (.C):**

```c
/* Each element of the former list becomes a separate pre-allocated output arg.
 * The function is void; the R caller assembles the named list. */
void rpart_c(/* ... input args ... */,
             int    *which,     /* integer(n)                    */
             double *cptable,   /* double(cptable_nrow * cptable_ncol) */
             double *dsplit,    /* double(splitcount * 3)        */
             int    *isplit,    /* integer(splitcount * 3)       */
             double *dnode,     /* double(nodecount * (3 + num_resp)) */
             int    *inode,     /* integer(nodecount * 6)        */
             int    *csplit)    /* integer(catcount * maxcat) or integer(0) */
{
    /* All downstream logic using which3, cptable3, etc. is rewritten to
     * use the raw pointer arguments directly.  No SEXP, no PROTECT,
     * no SET_VECTOR_ELT, no mkChar. */
}
```

- R-side call:

```r
result <- .C("rpart_c",
             # ... input args ...
             which   = integer(n),
             cptable = double(cptable_nrow * cptable_ncol),
             dsplit  = double(splitcount * 3L),
             isplit  = integer(splitcount * 3L),
             dnode   = double(nodecount * (3L + num_resp)),
             inode   = integer(nodecount * 6L),
             csplit  = integer(max(0L, catcount * maxcat)))

# Reassemble the named list on the R side
output <- list(
    which   = result$which,
    cptable = matrix(result$cptable, nrow = cptable_nrow),
    dsplit  = matrix(result$dsplit,  nrow = splitcount, ncol = 3L),
    isplit  = matrix(result$isplit,  nrow = splitcount, ncol = 3L),
    dnode   = matrix(result$dnode,   nrow = nodecount),
    inode   = matrix(result$inode,   nrow = nodecount, ncol = 6L)
)
if (catcount > 0L)
    output$csplit <- matrix(result$csplit, nrow = catcount, ncol = maxcat)
```

- **Explanation:**
  - `allocVector(VECSXP, nout)` and `allocVector(STRSXP, nout)` are removed entirely; there is no list object inside C.
  - `SET_VECTOR_ELT` / `SET_STRING_ELT` / `setAttrib` / `mkChar` / `R_NamesSymbol` calls are all removed.
  - Each output `SEXP` variable (`which3`, `cptable3`, etc.) becomes a separate pre-allocated `int *` or `double *` argument.
  - The R caller reconstructs the named list with `list()` and `matrix()` after `.C` returns.
  - `UNPROTECT(1 + nout)` is removed; no protection is needed.

---

### Pattern: SEXP as Local Temporary for eval() Return Value

- **Locations:** `rpart_callback.c` lines 92 and 131; `rpart_callback.c` lines 33–35 (static globals)

- **Original Context (.Call):**

```c
/* rpart_callback.c:88-119 — eval result captured in SEXP, then unwrapped */
static SEXP expr2;
static SEXP rho;

void rpart_callback1(int n, double *y[], double *wt, double *z)
{
    SEXP value;
    /* ... populate ydata, wdata, ndata ... */
    value = eval(expr2, rho);       /* evaluate R expression */
    if (!isReal(value))
        error("return value not a vector");
    double *dptr = REAL(value);     /* unwrap to double * */
    for (int i = 0; i <= rsave; i++)
        z[i] = dptr[i];
}

/* rpart_callback.c:126-172 — similar pattern with goodness */
void rpart_callback2(int n, int ncat, double *y[], double *wt,
                     double *x, double *good)
{
    SEXP goodness;
    goodness = eval(expr1, rho);
    double *dptr = REAL(goodness);
    /* ... copy dptr into good[] ... */
}
```

- **C/C++ Equivalent (.C):**

```c
/* Direct .C conversion is NOT possible for this pattern.
 *
 * The callback relies on:
 *   - Storing an R environment (SEXP rho) across calls
 *   - Calling R's evaluator (eval) from within C
 *   - Receiving an arbitrary-length R vector back
 *
 * None of these operations are available in .C functions.
 *
 * Recommended migration strategy:
 *   Option A — Keep as .Call.
 *     Register rpart_callback1 / rpart_callback2 as .Call functions that
 *     accept SEXP arguments, perform the eval(), and return a SEXP.  The
 *     main rpart computation loop invokes these via a function pointer set
 *     up at initialisation time.
 *
 *   Option B — Move evaluation to R.
 *     Restructure the algorithm so that each "callback" step surfaces as
 *     an R-level call.  The C code signals back to R (e.g., via a shared
 *     pre-allocated double * buffer), R evaluates the expression, fills
 *     results into another shared buffer, and C reads from it on the next
 *     entry.  This requires splitting the monolithic tree-building loop
 *     into iterative calls driven from R.
 */
```

- **Explanation:**
  - `static SEXP expr1`, `static SEXP expr2`, and `static SEXP rho` store R language objects between C function calls. There is no `.C`-compatible equivalent for R environments or unevaluated expressions.
  - `eval(expr, rho)` invokes R's interpreter from inside C; this is an operation that belongs to the `.Call` or `.External` API and has no counterpart in `.C`.
  - `isReal(value)` and `LENGTH(value)` require a `SEXP` to introspect; under `.C`, sizes must be communicated through explicit `int *` arguments.
  - This pattern is the single hard blocker for a full `.C` migration of the callback subsystem. All other SEXP usages in the codebase are mechanically convertible.

---

### Pattern: SEXP Function Prototype in Header and Registration Table

- **Locations:** `rpartproto.h` lines 39–40, 57–59; `init.c` lines 6–10 (forward declarations); `init.c` lines 12–19 (`R_CallMethodDef` table)

- **Original Context (.Call):**

```c
/* rpartproto.h */
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
           SEXP ymat2, SEXP xmat2, SEXP xvals2, SEXP xgrp2,
           SEXP wt2, SEXP ny2, SEXP cost2);
SEXP xpred(SEXP ncat2, …, SEXP nresp2);

/* init.c — registration */
static const R_CallMethodDef CallEntries[] = {
    {"rpart",      (DL_FUNC) &rpart,      11},
    {"xpred",      (DL_FUNC) &xpred,      15},
    {"rpartexp2",  (DL_FUNC) &rpartexp2,   2},
    {"pred_rpart", (DL_FUNC) &pred_rpart, 12},
    {NULL, NULL, 0}
};
void R_init_rpart(DllInfo *dll) {
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
}
```

- **C/C++ Equivalent (.C):**

```c
/* Header prototypes change to void with typed pointer arguments */
void rpart_c(const int *ncat, const int *method, const double *opt,
             const double *parms, const double *ymat, const double *xmat,
             const int *xvals, const int *xgrp, const double *wt,
             const int *ny, const double *cost,
             /* output args: */
             int *which, double *cptable, int *cptable_nrow,
             double *dsplit, int *isplit, double *dnode, int *inode,
             int *csplit, const int *catcount, const int *maxcat);

/* Registration uses R_CMethodDef with R_NativePrimitiveArgType[] */
static R_NativePrimitiveArgType rpart_c_types[] = {
    INTSXP,  /* ncat    */
    INTSXP,  /* method  */
    REALSXP, /* opt     */
    REALSXP, /* parms   */
    REALSXP, /* ymat    */
    REALSXP, /* xmat    */
    INTSXP,  /* xvals   */
    INTSXP,  /* xgrp    */
    REALSXP, /* wt      */
    INTSXP,  /* ny      */
    REALSXP, /* cost    */
    INTSXP,  /* which   (output) */
    REALSXP, /* cptable (output) */
    INTSXP,  /* cptable_nrow (output) */
    REALSXP, /* dsplit  (output) */
    INTSXP,  /* isplit  (output) */
    REALSXP, /* dnode   (output) */
    INTSXP,  /* inode   (output) */
    INTSXP,  /* csplit  (output) */
    INTSXP,  /* catcount */
    INTSXP   /* maxcat   */
};

static const R_CMethodDef CEntries[] = {
    {"rpart_c", (DL_FUNC) &rpart_c, 21, rpart_c_types},
    /* ... */
    {NULL, NULL, 0, NULL}
};

void R_init_rpart(DllInfo *dll) {
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
}
```

- **Explanation:**
  - `R_CallMethodDef` (third argument to `R_registerRoutines`) is replaced by `R_CMethodDef` (first argument).
  - Each `SEXP`-typed parameter in the prototype becomes a typed C pointer; return type changes from `SEXP` to `void`.
  - An `R_NativePrimitiveArgType[]` array maps each argument position to `INTSXP` or `REALSXP`, enabling R's `.C` dispatcher to coerce and type-check arguments automatically.
  - The number of arguments in the registration entry increases because formerly-internal allocations are now explicit output parameters.
