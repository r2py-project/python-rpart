# Fake Header Implementation Guide: `isReal`

---

### 1. Overview of `isReal` in R API

`isReal` is a type-checking predicate declared in `Rinternals.h` as `Rboolean (Rf_isReal)(SEXP s)`, with the alias `#define isReal Rf_isReal`. It accepts a single `SEXP` argument and returns a `Rboolean` (`TRUE` or `FALSE`) indicating whether the object's type tag is `REALSXP` (value `14`) — that is, whether the SEXP represents a real (double-precision floating-point) vector or matrix. It is used in guard clauses to validate that a value returned from an `eval()` call is the expected numeric type before applying the `REAL()` accessor. `isReal` is not an R Interpreter Item; it requires no running R interpreter and no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart_callback.c` | 113 | `if (!isReal(value))` — guards the SEXP returned by `eval(expr2, rho)` before `REAL(value)` is called |
| `rpart_callback.c` | 147 | `if (!isReal(goodness))` — guards the SEXP returned by `eval(expr1, rho)` before `REAL(goodness)` and `LENGTH(goodness)` are called |

**Full context window for line 113 (rpart_callback1, lines 88–120):**

```c
void
rpart_callback1(int n, double *y[], double *wt, double *z)
{
    int i, j, k;
    SEXP value;
    double *dptr;

    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];

    for (i = 0; i < n; i++)
        wdata[i] = wt[i];
    ndata[0] = n;

    /* no need to protect as no memory allocation (or error) below */
    value = eval(expr2, rho);
    if (!isReal(value))
        error(_("return value not a vector"));
    if (LENGTH(value) != (1 + rsave))
        error(_("returned value is the wrong length"));
    dptr = REAL(value);
    for (i = 0; i <= rsave; i++)
        z[i] = dptr[i];
}
```

**Full context window for line 147 (rpart_callback2, lines 126–165):**

```c
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

    /* no need to protect as no memory allocation (or error) below */
    goodness = eval(expr1, rho);
    if (!isReal(goodness))
        error(_("the expression expr1 did not return a vector!"));
    j = LENGTH(goodness);
    dptr = REAL(goodness);
    ...
}
```

**C types of arguments and return values.**

- Argument: `SEXP s` — a pointer to a `SEXPREC` node, in both usages the result of an `eval()` call.
- Return type: `Rboolean` (declared in `Rinternals.h:210`), which in the `Rf_isReal` declaration is `Rboolean`. In practice the result is used in a negated boolean test (`!isReal(...)`) which treats the return value as a plain integer. Returning `int` (1 or 0) is behaviorally equivalent, but for full signature fidelity the fake returns `int` (which is the underlying type of `Rboolean` on the target GCC/Linux platform where `HAVE_ENUM_BASE_TYPE` is not defined).

**Co-occurring R API items in context windows.**

- `eval(expr1, rho)` / `eval(expr2, rho)` — immediately precede each `isReal` call. `eval` is a Category E R Interpreter Item; the SEXP returned by it is passed into `isReal`. The `isReal` predicate itself is independent of the interpreter.
- `error(...)` — immediately follows each `isReal` check in the `!isReal(...)` branch, throwing `RError` in the fake runtime (Invariant 1; documented in `error.md`).
- `LENGTH(value)` / `LENGTH(goodness)` — called on the same SEXP immediately after the `isReal` guard passes (documented in `LENGTH.md`).
- `REAL(value)` / `REAL(goodness)` — called on the same SEXP after both guards pass, obtaining a `double *` (documented in `REAL.md`).
- `PROTECT` / `UNPROTECT` — absent at these sites; the source comment explicitly notes "no need to protect as no memory allocation (or error) below". The fake's no-op PROTECT/UNPROTECT (documented in `PROTECT.md`) is consistent with this.

**Distinct implementation patterns.**

There is exactly one structural pattern in the CSV: `isReal` is called on a `SEXP` that was just returned from `eval()`, and the result is used as a boolean guard before calling `REAL()` on the same SEXP. Both CSV rows belong to this single pattern. No other patterns (e.g., calling `isReal` on an input parameter SEXP, or storing the result in a variable) appear in the dataset.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`isReal` is a type-checking predicate that inspects the `type` field of the `SEXPREC` node. In the real R runtime, `Rf_isReal` inspects the internal SEXP header to compare the stored `SEXPTYPE` against `REALSXP`. In the fake runtime, `SEXPREC` has a public `type` field of type `SEXPTYPE`, so the check reduces to `s->type == REALSXP`.

**Chosen mechanism.**

Implement `isReal` (via its canonical name `Rf_isReal`) as a C++ `inline` function that returns `int` (compatible with `Rboolean`):

```cpp
inline int Rf_isReal(SEXP s) { return s->type == REALSXP; }
#define isReal Rf_isReal
```

The `#define isReal Rf_isReal` alias is essential: the original `rpart_callback.c` source calls `isReal(value)` (no `Rf_` prefix), exactly as the real `Rinternals.h` macro provides it. Without this alias, the original source would not compile.

The return type is declared `int` rather than `Rboolean` in the inline body to avoid a circular dependency: `Rboolean` is defined in `fake_Boolean.hpp` / `R_ext/Boolean.h`, and `isReal` may be needed before that header is processed. Because the return value is used exclusively in boolean tests (`!isReal(...)`) in all rpart source files, returning `int` (1 or 0) is fully compatible with every usage. The `Rf_isReal` declaration in the real `Rinternals.h:210` uses `Rboolean` as the return type; if strict type-matching is desired, the inline may return `(Rboolean)(s->type == REALSXP)` once `Rboolean` is in scope.

**`#define` aliases from the original header that must be preserved.**

From `Rinternals.h:986`:

```c
#define isReal    Rf_isReal
```

This macro is the only alias. It must be reproduced in the fake header so that the unmodified `rpart_callback.c` (which uses `isReal`, not `Rf_isReal`) compiles correctly.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not directly triggered by `isReal`. The `error(...)` calls that immediately follow the `!isReal(...)` tests are governed by the `error` / `Rf_error` fake (documented in `error.md`); `isReal` itself never throws.
- Invariant 2 (arena memory): not triggered. `isReal` allocates nothing; it only reads `s->type`.
- Invariant 3 (R Interpreter Items): not triggered. `isReal` does not call `eval`, `findVar`, or any interpreter function. The fact that the SEXP passed to it was produced by `eval()` (a Category E item) is irrelevant to the implementation of `isReal` itself — once the SEXP is in hand, `isReal` needs only the `type` field.

---

### 4. Fake Implementation Examples

#### Pattern: Type Guard on `eval()` Result Before `REAL()` Access

- **Locations:** `rpart_callback.c:113`, `rpart_callback.c:147`

- **Original R API Usage:**

```c
/* rpart_callback.c:112-119 — rpart_callback1 */
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));
dptr = REAL(value);
for (i = 0; i <= rsave; i++)
    z[i] = dptr[i];

/* rpart_callback.c:146-151 — rpart_callback2 */
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
j = LENGTH(goodness);
dptr = REAL(goodness);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — isReal type predicate)
// -----------------------------------------------------------------------
// Prerequisites in this header (declared above this section):
//   - SEXPTYPE typedef and #define REALSXP 14  (SEXPTYPE block)
//   - struct SEXPREC { SEXPTYPE type; int length; int nrow; int ncol; void *data; }
//   - typedef SEXPREC *SEXP
// -----------------------------------------------------------------------

// isReal / Rf_isReal
// Checks whether a SEXP's type tag is REALSXP (14).
// Return type is int (compatible with Rboolean) to avoid a forward-reference
// dependency on the Rboolean typedef from fake_Boolean.hpp.
// The #define alias preserves the unqualified name used in the original source.
inline int Rf_isReal(SEXP s) {
    return s->type == REALSXP;   // REALSXP is #define'd as 14
}
#define isReal Rf_isReal

// Related type predicates used elsewhere in rpart_callback.c
// (isInteger and isNull are included here for completeness; they follow
// the same pattern and belong in the same fake_Rinternals.hpp section.)
inline int Rf_isInteger(SEXP s) { return s->type == INTSXP; }
#define isInteger Rf_isInteger

inline int Rf_isNull(SEXP s)    { return s->type == NILSXP; }
#define isNull Rf_isNull

// -----------------------------------------------------------------------
// Usage context: the calls to isReal in rpart_callback.c appear after
// eval() returns a SEXP (Category E; requires a Python-registered callback).
// Once eval() delivers a valid SEXP, isReal, LENGTH, REAL, and error
// all operate on it using only the SEXPREC->type/length/data fields.
//
// The enclosing functions rpart_callback1 and rpart_callback2 are internal
// C functions (not .Call entry points); they are called from the rpart
// computation loop which itself is invoked from the rpart() .Call entry
// point.  The ArenaFrame guard is declared at the rpart() boundary wrapper,
// not inside rpart_callback1/2.  No arena memory is allocated in either
// callback; their only allocations are stack variables (int i, j, k;
// double *dptr;).
//
// .Call boundary wrapper illustration (for the rpart() entry point that
// ultimately invokes rpart_callback1 and rpart_callback2):
//
//   extern "C" SEXP rpart_entry(
//           SEXP ncat2, SEXP method2, SEXP opt2,
//           SEXP parms2, SEXP xvals2, SEXP xgrp2,
//           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2) {
//       ArenaFrame _frame;   // frees R_alloc / ALLOC scratch on exit
//       try {
//           return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                        ymat2, xmat2, wt2, ny2, cost2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// If isReal(value) returns 0 (false), the error(...) call immediately
// following it will throw RError (via the fake Rf_error; see error.md).
// That exception unwinds through rpart_callback1/2 -> rpart computation
// loop -> rpart() -> and is caught at the .Call boundary wrapper above.
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:** Not applicable. `isReal` does not allocate or free memory. It reads a single `int`-sized field (`s->type`) from a heap-allocated `SEXPREC` node. The SEXP node itself was produced by `eval()` via the Python-side callback (a Category E item); `isReal` has no responsibility for its lifetime.

- **Explanation:**

  The fake provides `inline int Rf_isReal(SEXP s) { return s->type == REALSXP; }` and the alias `#define isReal Rf_isReal`. When the original source calls `isReal(value)`, the preprocessor substitutes `Rf_isReal(value)`, and the inline function checks `value->type == 14`. In the fake runtime, every `SEXPREC` produced by `allocVector(REALSXP, ...)` or `allocMatrix(REALSXP, ...)` has `type = REALSXP = 14`, so this predicate correctly identifies real vectors and matrices. Any SEXP constructed by the Python-side `eval()` callback must also set `type = REALSXP` when representing a real result; this is the contract imposed on the Python-side implementation of the `eval` stub.

  The `#define isReal Rf_isReal` alias is reproduced verbatim from `Rinternals.h:986`. Without it, the line `if (!isReal(value))` in `rpart_callback.c:113` would fail to compile with "undefined identifier `isReal`". The original source is not modified.

  The real `Rf_isReal` is declared in `Rinternals.h:210` with return type `Rboolean`. The fake returns `int` instead. This is safe on the target GCC/Linux platform because `Rboolean` has no `HAVE_ENUM_BASE_TYPE` extension and its members are `int`-compatible constants. All call sites in rpart use the result solely in `!isReal(...)` boolean tests, which implicitly convert `int` to `bool` in C++ — no explicit `Rboolean` comparison occurs.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The `SEXPREC` struct with public `type` field (`SEXPTYPE type`) and the `typedef SEXPREC *SEXP`. `isReal` reads `s->type` directly; this field must exist and be named `type`. |
| `REALSXP.md` | The `#define REALSXP 14` constant within the `SEXPTYPE` block. `isReal` compares `s->type` against `REALSXP`; the constant must be defined before `Rf_isReal` is compiled. |
| `INTSXP.md` | The complete `SEXPTYPE` block that includes `#define NILSXP 0` and `#define INTSXP 13`, required by the companion predicates `isNull` and `isInteger` defined in the same fake section. |
| `error.md` | The `RError` exception type and the `Rf_error` / `error` fake (throws `RError`). Required by the `error(...)` calls that immediately follow each `!isReal(...)` guard in `rpart_callback.c:114` and `rpart_callback.c:148`. `isReal` itself does not call `error`; the dependency is in the surrounding code. |
| `eval.md` (Category E) | The `eval(SEXP expr, SEXP rho)` function-pointer stub. The SEXP values passed to `isReal` at both call sites are the direct return values of `eval(expr2, rho)` and `eval(expr1, rho)`. Without the `eval` stub registered, the `isReal` lines are never reached at runtime (the program throws `RError` inside `eval` before `isReal` is called). `isReal` itself has no compile-time dependency on `eval.md`, but the runtime paths that exercise `isReal` require the Python-side `eval` callback to be registered. |
| `LENGTH.md` | The `LENGTH(SEXP s)` inline function. Called on the same SEXP immediately after the `isReal` guard in `rpart_callback1` (line 115). No compile-time dependency on `isReal`, but the two items appear in the same fake header section and must be consistent. |
| `REAL.md` | The `REAL(SEXP s)` inline function returning `double *`. Called on the same SEXP after both guards (lines 117 and 150). Same relationship as `LENGTH.md`. |
