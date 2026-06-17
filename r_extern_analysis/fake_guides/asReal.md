# Fake Header Implementation Guide: `asReal`

---

### 1. Overview of `asReal` in R API

`asReal` is a scalar-coercion function in R's C API, declared in `Rinternals.h` as `double Rf_asReal(SEXP x)` with the macro alias `#define asReal Rf_asReal`. It accepts a single `SEXP` argument — typically a length-1 real or integer vector — and returns the C `double` value of its first element. Unlike `REAL(x)`, which returns a pointer to the entire element buffer, `asReal` extracts and returns only the first element as a scalar `double`, performing a coercion if necessary (e.g., from `INTSXP` to `double`). In rpart's source files, `asReal` is used exclusively to extract scalar floating-point configuration parameters from `.Call` input arguments, converting single-element SEXP wrappers into plain `double` values for use as function arguments or local variable initializers. `asReal` is not an R Interpreter Item; it requires no running R interpreter and no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpartexp2.c` | 48 | `Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));` |
| `xpred.c` | 76 | `toprisk = asReal(toprisk2);` |

**Full context for `rpartexp2.c:43–51`.**

```c
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}
```

`eps` is a `.Call` input parameter received as a SEXP. The internal C function `Rpartexp2` is declared at `rpartexp2.c:14` as:

```c
static void Rpartexp2(int n, double *y, double eps, int *keep)
```

The third parameter is a plain `double` scalar. `asReal(eps)` converts the length-1 SEXP to that `double` and passes it directly without an intermediate variable.

**Full context for `xpred.c:33–76`.**

```c
SEXP
xpred(SEXP ncat2, SEXP method2, SEXP opt2,
      SEXP parms2, SEXP xvals2, SEXP xgrp2,
      SEXP ymat2, SEXP xmat2, SEXP wt2,
      SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2, SEXP toprisk2, SEXP nresp2)
{
    /* ... local variable declarations ... */
    double toprisk;
    /* ... */
    ncat = INTEGER(ncat2);
    xgrp = INTEGER(xgrp2);
    xvals = asInteger(xvals2);
    wt = REAL(wt2);
    parms = REAL(parms2);
    ncp = LENGTH(cp2);
    cp = REAL(cp2);
    toprisk = asReal(toprisk2);
    /* ... */
}
```

`toprisk2` is a `.Call` input parameter and `toprisk` is a local `double` variable declared at line 48. `asReal(toprisk2)` converts the length-1 SEXP to a plain `double` assigned to `toprisk` for later use in the function body.

**Argument and return types observed across all rows.**

`asReal` always takes a single `SEXP` argument and always returns `double`. The source SEXPs are `.Call` input parameters — scalar wrappers constructed by the R or Python caller before the `.Call` boundary. The `double` result is used in one of the following ways:

- Passed directly as a `double` scalar argument to an internal C function (`rpartexp2.c:48`: `Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep))`).
- Assigned to a local `double` variable used in subsequent computation (`xpred.c:76`: `toprisk = asReal(toprisk2)`).

**Co-occurring R API items in context windows.**

- `REAL(sexp)` — appears at the same call site in `rpartexp2.c:48`, accessing the `double *` buffer of `dtimes`. `REAL` returns a pointer; `asReal` returns a scalar.
- `INTEGER(sexp)` — appears at the same call site in `rpartexp2.c:48` (for `keep`) and at nearby lines in `xpred.c:69–70` (for `ncat2`, `xgrp2`). `INTEGER` returns `int *`; `asReal` returns the scalar `double`.
- `asInteger(sexp)` — appears at nearby lines in `xpred.c:71` (`xvals = asInteger(xvals2)`) and `xpred.c:81–87`. Both `asReal` and `asInteger` extract scalar values from length-1 SEXP parameters; they differ only in return type (`double` vs. `int`).
- `LENGTH(sexp)` — used at `rpartexp2.c:46` to read the element count from `dtimes` immediately before `asReal(eps)` on line 48.
- `allocVector(INTSXP, n)` — at `rpartexp2.c:47`, the allocated SEXP `keep` is used in the same `Rpartexp2` call as `asReal(eps)`. `asReal` does not interact with this allocation.
- `PROTECT` / `UNPROTECT` — wrap the `allocVector` call at `rpartexp2.c:47`. `asReal` itself is never wrapped in `PROTECT`.
- `error(_("Invalid value for 'method'"))` — appears in `xpred.c:89` in the `else` branch of the method guard immediately following the `asReal` call at line 76.

**Distinct usage patterns.**

Two structural contexts appear across the two CSV rows, but both use the identical fake `asReal` implementation. The distinction reflects the calling context (direct function argument vs. local variable assignment), not any difference in the fake function itself.

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Pass scalar `double` as a direct function argument | `rpartexp2.c:48` | `asReal(eps)` converts a length-1 SEXP to `double` and passes it as a positional argument to the internal C function `Rpartexp2`. No intermediate variable is used. |
| P2: Assign scalar `double` to a local variable | `xpred.c:76` | `toprisk = asReal(toprisk2)` converts a length-1 SEXP to `double` and stores the result in the local variable `toprisk` for later use in the function body. |

Both patterns share the identical fake `Rf_asReal` inline definition.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`asReal` is declared in `Rinternals.h` at line 488 as `double Rf_asReal(SEXP x)` and aliased at line 910 as `#define asReal Rf_asReal`. In the real R runtime, `Rf_asReal` performs full type coercion: if the SEXP holds a `REALSXP`, it returns the `double` value directly; if it holds an `INTSXP`, it converts the `int` element to `double`; it handles `NA_integer_` and `NA_real_` by returning `R_NaReal`. In rpart's usage, every SEXP passed to `asReal` is a scalar real vector (constructed by the R or Python caller as a `REALSXP` of length 1), so the primary path is always a direct `double` read.

**Chosen mechanism.**

The fake implements `asReal` as a C++ `inline` function that casts `sexp->data` to `double *` and dereferences the first element:

```cpp
inline double Rf_asReal(SEXP s) {
    if (s->type == INTSXP)
        return static_cast<double>(static_cast<int *>(s->data)[0]);
    return static_cast<double *>(s->data)[0];
}
#define asReal Rf_asReal
```

This is correct because:
1. The `SEXPREC` fake (from `SEXP.md`) stores the element buffer in `s->data` as a `void *`.
2. When the Python caller constructs a `REALSXP` scalar SEXP for a parameter like `eps` or `toprisk2`, it allocates a `SEXPREC` with `type=REALSXP`, `length=1`, and `data` pointing to a single `double` containing the value.
3. `static_cast<double *>(s->data)[0]` reads that first `double` element, which is identical to the real `Rf_asReal` behavior for `REALSXP` inputs.

The `INTSXP` branch is included for safety: if a Python caller passes a length-1 integer SEXP (e.g., one that was constructed with `type=INTSXP`) where a real scalar is expected, the coercion to `double` matches the real R runtime behavior rather than returning a bit-reinterpretation.

This design mirrors the `asInteger.md` pattern exactly, with the type roles transposed: `asInteger` uses `REALSXP` as the special branch and `INTSXP` as the primary path; `asReal` uses `INTSXP` as the special branch and `REALSXP` as the primary path.

The `SEXP.md` guide already shows `asReal` as a one-liner inline at line 445 of that guide: `inline double asReal(SEXP s) { return static_cast<double *>(s->data)[0]; }`. The present guide supersedes that inline reference with the complete `Rf_asReal` function name, the `#define` alias, and the `INTSXP` coercion safety branch.

**`#define` aliases that must be preserved.**

```c
#define asReal   Rf_asReal
```

This is the only alias. It is present in `Rinternals.h` at line 910. It must appear in `fake_Rinternals.hpp` after the `Rf_asReal` inline definition so that all occurrences of `asReal(...)` in rpart source files resolve to the fake inline function.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `asReal` itself. The function performs a cast and cannot fail for a well-formed SEXP. The functions that produce the SEXP argument (constructed by the Python caller before the `.Call` boundary) may throw `RError` during construction, but `asReal` is called only after successful argument delivery.
- Invariant 2 (arena memory): not triggered. `asReal` reads from an existing SEXP's `data` buffer; it does not allocate any memory, heap or arena.
- Invariant 3 (R Interpreter Items): not applicable. `asReal` does not invoke the R interpreter.

---

### 4. Fake Implementation Examples

#### Pattern P1: Pass Scalar `double` as a Direct Function Argument

- **Locations:** `rpartexp2.c:48`

- **Original R API Usage:**

```c
/* rpartexp2.c:43-51 — asReal(eps) converts a length-1 SEXP to double,
   passed as the third argument to Rpartexp2 (declared as double eps) */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}

/* Internal callee declaration at rpartexp2.c:14 */
static void Rpartexp2(int n, double *y, double eps, int *keep)
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — asReal accessor, Category B)
// Must appear after the SEXPREC struct and SEXP typedef from SEXP.md,
// and after the SEXPTYPE constants (REALSXP=14, INTSXP=13) from INTSXP.md
// and REALSXP.md.

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

// ... (SEXPREC, SEXP, SEXPTYPE block, RError, PROTECT/UNPROTECT,
//      allocVector, INTEGER, REAL, LENGTH, asInteger from SEXP.md) ...

// -------------------------------------------------------------------------
// Rf_asReal — extracts element [0] of a SEXP as a C double.
//
// Corresponds to Rinternals.h declaration:
//   double Rf_asReal(SEXP x);
//   #define asReal  Rf_asReal
//
// For REALSXP input (the primary type used in rpart): casts s->data to
// double * and returns element [0].
//
// For INTSXP input (not used in rpart, but handled for safety): casts
// s->data to int * and widens element [0] to double, matching real
// Rf_asReal coercion semantics.
//
// For all other SEXPTYPE values: falls through to the double * cast.
// -------------------------------------------------------------------------
inline double Rf_asReal(SEXP s) {
    if (s->type == INTSXP)
        return static_cast<double>(static_cast<int *>(s->data)[0]);
    return static_cast<double *>(s->data)[0];
}

// Preserve the #define alias from Rinternals.h line 910 so that the
// original rpart source files compile with 'asReal(...)' unchanged.
#define asReal Rf_asReal

#endif // FAKE_RINTERNALS_H
```

The `.Call` entry-point boundary wrapper for `rpartexp2` illustrates the `ArenaFrame` guard (needed because `rpartexp2` calls `allocVector`, which uses heap — but `ArenaFrame` is still declared at the top level per convention for all entry points) and the `try/catch` boundary (Invariant 1). `asReal` itself requires neither guard nor catch:

```cpp
// Python-facing entry-point wrapper for rpartexp2.
// asReal is called inside rpartexp2() — no special guard needed for it.
// The ArenaFrame is declared at the entry of every top-level .Call function
// per Invariant 2. rpartexp2 itself does not call R_alloc/ALLOC, but the
// guard is harmless and required for consistency.
extern "C" SEXP rpartexp2_entry(SEXP dtimes, SEXP eps) {
    ArenaFrame _frame;   // frees any R_alloc / ALLOC scratch on exit (Invariant 2)
    try {
        return rpartexp2(dtimes, eps);
    } catch (const RError &e) {
        set_python_error(e.what());   // store for Python to read
        return nullptr;
    }
}
```

Inside `rpartexp2()`, the original line compiles unchanged:

```c
// rpartexp2.c:48 — unchanged original source
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
// asReal(eps) expands to: Rf_asReal(eps)
// which executes: static_cast<double *>(eps->data)[0]
// eps is a length-1 REALSXP SEXP constructed by the Python caller.
// The double value is passed directly to Rpartexp2's third parameter (double eps).
```

- **Arena / Memory Notes:** Not applicable. `asReal` performs no memory allocation. It reads from the `data` buffer of an existing SEXP. The buffer was allocated by the Python caller as part of the input `SEXPREC` node construction before the `.Call` boundary; it remains valid for the lifetime of the `.Call` invocation.

- **Explanation:**

  `asReal(eps)` expands via the `#define` alias to `Rf_asReal(eps)`, which resolves to `static_cast<double *>(eps->data)[0]`. The `eps` SEXP was constructed by the Python caller with `type=REALSXP`, `length=1`, and `data` pointing to a single `double` holding the machine-precision threshold. The result is the plain `double` value of that element, passed directly as the third argument of `Rpartexp2(int n, double *y, double eps, int *keep)`. No intermediate variable is created; the compiler generates a register load from the SEXP data pointer directly into the function-call argument slot.

  The original source file is not modified. The `#define asReal Rf_asReal` alias in `fake_Rinternals.hpp` ensures that every occurrence of `asReal(...)` in the rpart source resolves to the fake inline function.

---

#### Pattern P2: Assign Scalar `double` to a Local Variable

- **Locations:** `xpred.c:76`

- **Original R API Usage:**

```c
/* xpred.c:33-76 — asReal(toprisk2) extracts a scalar double from an input SEXP,
   assigned to the local variable toprisk (declared double toprisk at xpred.c:48) */
SEXP
xpred(SEXP ncat2, SEXP method2, SEXP opt2,
      SEXP parms2, SEXP xvals2, SEXP xgrp2,
      SEXP ymat2, SEXP xmat2, SEXP wt2,
      SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2, SEXP toprisk2, SEXP nresp2)
{
    /* ... */
    double toprisk;
    /* ... */
    ncat = INTEGER(ncat2);
    xgrp = INTEGER(xgrp2);
    xvals = asInteger(xvals2);
    wt = REAL(wt2);
    parms = REAL(parms2);
    ncp = LENGTH(cp2);
    cp = REAL(cp2);
    toprisk = asReal(toprisk2);

    if (asInteger(method2) <= NUM_METHODS) {
        /* ... */
    } else
        error(_("Invalid value for 'method'"));
    /* ... */
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (asReal — same definition as Pattern P1)
// The implementation is identical; the pattern here reflects local variable
// assignment rather than inline usage as a direct function argument.

inline double Rf_asReal(SEXP s) {
    if (s->type == INTSXP)
        return static_cast<double>(static_cast<int *>(s->data)[0]);
    return static_cast<double *>(s->data)[0];
}
#define asReal Rf_asReal

// The error() call in the else branch of the method guard is a Category D item.
// It expands via Rinternals.h as: #define error Rf_error
// In the fake, Rf_error formats a message and throws RError (Invariant 1).
// The RError propagates through xpred() to the .Call wrapper:

struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

inline void Rf_error(const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    throw RError(buf);
}
#define error Rf_error

// .Call boundary wrapper for xpred — catches RError thrown anywhere inside:
extern "C" SEXP xpred_entry(
        SEXP ncat2, SEXP method2, SEXP opt2,
        SEXP parms2, SEXP xvals2, SEXP xgrp2,
        SEXP ymat2, SEXP xmat2, SEXP wt2,
        SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2,
        SEXP toprisk2, SEXP nresp2) {
    ArenaFrame _frame;   // frees R_alloc / ALLOC scratch on exit (Invariant 2)
    try {
        return xpred(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2, all2, cp2,
                     toprisk2, nresp2);
    } catch (const RError &e) {
        set_python_error(e.what());   // store message for Python to read
        return nullptr;
    }
}
```

Inside `xpred()`, the original line compiles unchanged:

```c
// xpred.c:76 — unchanged original source
toprisk = asReal(toprisk2);
// asReal(toprisk2) expands to: Rf_asReal(toprisk2)
// which executes: static_cast<double *>(toprisk2->data)[0]
// toprisk2 is a length-1 REALSXP SEXP constructed by the Python caller.
// The double result is stored in the local variable toprisk.
```

- **Arena / Memory Notes:** Not applicable. `asReal` performs no memory allocation. The `toprisk2` SEXP is an input parameter constructed by the Python caller; its `data` buffer is Python-owned and remains valid for the duration of the `.Call` invocation. The local variable `toprisk` is a plain `double` on the C stack.

- **Explanation:**

  `toprisk = asReal(toprisk2)` expands via the `#define` alias to `toprisk = Rf_asReal(toprisk2)`, which resolves to `toprisk = static_cast<double *>(toprisk2->data)[0]`. The `toprisk2` SEXP was constructed by the Python caller with `type=REALSXP`, `length=1`, and `data` pointing to a single `double`. The local variable `toprisk` then holds this value for the rest of the `xpred()` function body.

  The surrounding context at `xpred.c:69–76` shows six consecutive scalar and vector extractions: `INTEGER(ncat2)`, `INTEGER(xgrp2)`, `asInteger(xvals2)`, `REAL(wt2)`, `REAL(parms2)`, `REAL(cp2)`, and finally `asReal(toprisk2)`. Each fake is an independent inline cast from `sexp->data` to the appropriate type. None of them interact with each other or with the arena.

  The `error()` call at `xpred.c:89` is documented in the `error.md` guide. It throws `RError` if `asInteger(method2)` exceeds `NUM_METHODS`. The `try/catch` wrapper in `xpred_entry` catches that exception and converts it to a Python-side error via `set_python_error`. The `asReal` call at line 76 occurs before the method guard, so it executes successfully regardless of whether the method check later fails.

  The original source file is not modified. The `#define asReal Rf_asReal` alias in `fake_Rinternals.hpp` ensures that every occurrence of `asReal(...)` in the rpart source resolves to the fake inline function.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` — `fake_Rinternals.hpp` | The `SEXPREC` struct with a `void *data` field and a `SEXPTYPE type` field. `Rf_asReal` casts `s->data` to `double *` and reads element `[0]`; the `INTSXP` coercion branch additionally casts `s->data` to `int *` and reads element `[0]`. The `SEXPREC` and `SEXP` typedef must appear before `Rf_asReal` in the header. `SEXP.md` is the authoritative source for `fake_Rinternals.hpp`; `asReal` resides in that same header. The `SEXP.md` guide already shows `asReal` as a one-liner inline (line 445 of that guide) — the present guide supersedes that with the full `Rf_asReal` / `#define asReal` form and the `INTSXP` coercion branch. |
| `INTSXP.md` | Establishes `#define INTSXP 13` and `#define REALSXP 14` in the `SEXPTYPE` constant block. The `Rf_asReal` fake references `INTSXP` by name in the type-dispatch branch. |
| `REALSXP.md` | Establishes `#define REALSXP 14`. Required because the primary execution path of `Rf_asReal` (for `REALSXP` SEXPs) implicitly relies on the SEXP having been constructed with `type=REALSXP` and a `double[]` buffer in `data`. The `REALSXP` constant must be defined in the same header block. |
| `asInteger.md` | Establishes `Rf_asInteger` and `#define asInteger Rf_asInteger` in `fake_Rinternals.hpp`. `asReal` and `asInteger` are parallel scalar coercion functions defined in the same header; the fake designs are symmetric (each handles the opposite SEXPTYPE in its safety branch). `asInteger` appears alongside `asReal` in `xpred.c:71–76`. Both must be consistent in their use of `sexp->data` and `sexp->type`. |
| `error.md` — `RError` and `Rf_error` | The `RError : public std::runtime_error` exception class and the `Rf_error` / `#define error` fake. Required because `asReal` is called immediately before the method guard at `xpred.c:81–89` which may invoke `error(...)` in its `else` branch. The `error()` call must be defined in the same header or an included header. |
| `REAL.md` | The `REAL` inline accessor. Used at the same call site as `asReal` in `rpartexp2.c:48` (`REAL(dtimes)`) and at nearby lines in `xpred.c:72–75` (`REAL(wt2)`, `REAL(parms2)`, `REAL(cp2)`). Both `REAL` and `asReal` cast `sexp->data` to `double *`; `REAL` returns the pointer, `asReal` dereferences element `[0]`. Both reside in `fake_Rinternals.hpp` and must be consistent. |
| `INTEGER.md` | The `INTEGER` inline accessor. Used at the same call site as `asReal` in `rpartexp2.c:48` (`INTEGER(keep)`) and at nearby lines in `xpred.c:69–70` (`INTEGER(ncat2)`, `INTEGER(xgrp2)`). Both `INTEGER` and `asReal` reside in `fake_Rinternals.hpp`; consistency in the `sexp->data` cast pattern is required. |
| `fake_arena.hpp` (no separate guide; generated once as a foundation) | The `ArenaFrame` RAII struct and `gArenaStack`. Not used by `asReal` directly, but required at the `.Call` wrapper level for `xpred()` and `rpartexp2()` — both of which call `asReal` and also involve other API calls that may interact with the arena or require the exception boundary. |
