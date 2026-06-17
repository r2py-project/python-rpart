# Fake Header Implementation Guide: `LENGTH`

---

### 1. Overview of `LENGTH` in R API

`LENGTH` is a scalar accessor function declared in `Rinternals.h` as `int (LENGTH)(SEXP x)`. It takes a single `SEXP` argument and returns the total number of elements in the vector or matrix it represents as a plain C `int`. `LENGTH` is the standard way to query the element count of any R object at the C level — whether the object is an integer vector, a real vector, a real matrix, or a character vector — and its return value is used throughout rpart to bound loops, validate expected sizes, and allocate downstream buffers. `LENGTH` is not an R Interpreter Item; it does not require a running R interpreter and needs no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files and line-number windows examined.**

| File | Line | Context |
|---|---|---|
| `rpart_callback.c` | 115 | `if (LENGTH(value) != (1 + rsave))` — bounds check on a SEXP returned by `eval(expr2, rho)` |
| `rpart_callback.c` | 149 | `j = LENGTH(goodness);` — reads length into a local `int j` used to validate and iterate over a REALSXP returned by `eval(expr1, rho)` |
| `rpartexp2.c` | 46 | `int n = LENGTH(dtimes);` — reads length of an input SEXP parameter to size an allocation |
| `xpred.c` | 74 | `ncp = LENGTH(cp2);` — reads length of an input SEXP parameter into an existing `int ncp` variable |

**Argument and return types observed across all rows.**

`LENGTH` always takes one `SEXP` argument and always returns `int`. The receiving variable in each case is:

- `rpart_callback.c:115` — the result is compared directly against the integer expression `(1 + rsave)` in a conditional. `rsave` is a static `int` module-level variable. No intermediate variable is used.
- `rpart_callback.c:149` — the result is assigned to local `int j`, declared at `rpart_callback.c:130`.
- `rpartexp2.c:46` — the result initialises local `int n`, declared in the same statement.
- `xpred.c:74` — the result is assigned to local `int ncp`, declared at `xpred.c:42`.

In every case the return type is used as a plain C `int`, not as `R_xlen_t`. This is consistent with the `Rinternals.h` declaration at line 279:

```c
int  (LENGTH)(SEXP x);
```

The parenthesised name is a C technique that forces the compiler to treat this as a function declaration even when a macro of the same name exists in scope. The return type is `int`, not `R_xlen_t` (which is used by the longer-range `XLENGTH` variant). All rpart usage fits within 32-bit `int` bounds.

**Co-occurring R API items in context windows.**

- `eval(expr2, rho)` and `eval(expr1, rho)` — in `rpart_callback.c` the SEXP passed to `LENGTH` was produced by `eval()`, a Category E item. `LENGTH` itself is unaffected by how the SEXP was produced.
- `isReal(value)` / `isReal(goodness)` — immediately precede the `LENGTH` calls in `rpart_callback.c` to verify the SEXP type before bounds-checking its length.
- `error(...)` — immediately follows both `LENGTH` calls in `rpart_callback.c` inside the bounds-check branch. This is the `Rf_error` alias; in the fake it throws `RError`.
- `REAL(value)` / `REAL(goodness)` — immediately follow the `LENGTH` calls in `rpart_callback.c` to extract the `double *` buffer; `REAL(cp2)` follows the `LENGTH` call in `xpred.c`.
- `allocVector(INTSXP, n)` — immediately follows the `LENGTH` call in `rpartexp2.c:46`; the returned `int n` is used directly as the length argument to `allocVector`.
- `PROTECT` / `UNPROTECT` — present in `rpartexp2.c` wrapping the `allocVector` call that uses `n`. No direct interaction with `LENGTH`.

**Distinct usage patterns across the four CSV rows.**

Two structural patterns emerge:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Read length of an input SEXP parameter to size a subsequent allocation or variable | `rpartexp2.c:46`, `xpred.c:74` | `LENGTH` is applied to a `SEXP` received as a `.Call` parameter. The result is stored in a local `int` and immediately used to size an `allocVector` call (`rpartexp2.c`) or to control downstream loop bounds (`xpred.c`). |
| P2: Read length of a SEXP produced by `eval()` for bounds validation | `rpart_callback.c:115`, `rpart_callback.c:149` | `LENGTH` is applied to a `SEXP` returned by `eval(expr, rho)` (a Category E item). The result is compared against an expected size; a mismatch causes `error()` to throw `RError`. |

Both patterns use the identical `LENGTH` fake implementation. The only guide-level distinction is that Pattern P2's SEXP source requires the `eval` function-pointer bridge to be registered at runtime; `LENGTH` itself is indifferent to the SEXP's origin.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`LENGTH` is declared in `Rinternals.h` at line 279 as `int (LENGTH)(SEXP x)`. The parentheses around the name serve the same purpose as for `INTEGER`: they prevent the compiler from treating the declaration as a macro invocation if a `#define LENGTH` is in scope. In modern R builds (R >= 4.5) a `USE_RINTERNALS`-gated macro path may redirect `LENGTH` through `LENGTH_EX(x, __FILE__, __LINE__)`, but rpart does not define `USE_RINTERNALS`, so the non-gated function declaration at line 279 is the one resolved by the compiler.

**Chosen mechanism.**

The fake implements `LENGTH` as a C++ `inline` function:

```cpp
inline int LENGTH(SEXP s) {
    return s->length;
}
```

This is correct because the `SEXPREC` fake (defined in `SEXP.md` / `fake_Rinternals.hpp`) stores the total element count in the `int length` field. Every SEXP allocation function (`allocVector`, `allocMatrix`) sets `s->length` at construction time. For input-parameter SEXPs constructed by the Python-side caller, the `length` field must be set correctly before the `.Call` boundary.

The `SEXP.md` guide already includes this definition at line 451 of the `fake_Rinternals.hpp` block shown there. This guide documents `LENGTH` as a first-class item with its own pattern analysis and integration requirements, and confirms that the definition in `fake_Rinternals.hpp` is correct and sufficient for all four CSV usages.

**`XLENGTH` and `Rf_length` aliases.**

The real `Rinternals.h` also declares:

```c
R_xlen_t (XLENGTH)(SEXP x);          // line 280 — 64-bit length
R_xlen_t  Rf_xlength(SEXP);          // line 1137
int LENGTH_EX(SEXP x, const char *file, int line);  // line 1140 — debug variant
R_xlen_t XLENGTH_EX(SEXP x);         // line 1141
```

None of these appear in the rpart source files, but they must not cause compilation failures if a transitive include pulls them in. The fake provides inline definitions for all of them that delegate to `s->length`. In the fake runtime `R_xlen_t` is `typedef int R_xlen_t` (matching the 32-bit-safe definition at line 80 of `Rinternals.h`), so there is no truncation risk.

**No `#define` alias needed.**

The real `Rinternals.h` does not define a macro `#define LENGTH(x) ...` in the non-`USE_RINTERNALS` build path. The parenthesised function declaration `int (LENGTH)(SEXP x)` suppresses macro interpretation. Therefore no `#define LENGTH` is required in the fake header; the inline function definition suffices and the compiler resolves it correctly when the original source files call `LENGTH(sexp)`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `LENGTH` itself. The function reads a field and cannot fail. The `error(...)` calls at `rpart_callback.c:116` and `rpart_callback.c:158-160` that follow the `LENGTH` comparison are `Rf_error` aliases; they throw `RError` as documented in the `error` fake guide. `LENGTH` is not involved in that throw path.
- Invariant 2 (arena memory): not triggered by `LENGTH`. The function reads `s->length`; it performs no allocation and does not interact with the arena.
- Invariant 3 (R Interpreter Items): not applicable to `LENGTH` itself. In Pattern P2, the SEXP whose length is read was produced by `eval()`, a Category E item, but `LENGTH` operates on the SEXP pointer value after `eval()` returns and is entirely unaware of the SEXP's provenance.

---

### 4. Fake Implementation Examples

#### Pattern P1: Read Length of an Input SEXP Parameter

- **Locations:** `rpartexp2.c:46`, `xpred.c:74`

- **Original R API Usage:**

```c
/* rpartexp2.c:43-48 — entry-point; LENGTH sizes an allocation */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}

/* xpred.c:42, 74-75 — entry-point; LENGTH stores into a pre-declared int */
int maxcat, ncp;
/* ... */
ncp = LENGTH(cp2);
cp = REAL(cp2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — LENGTH accessor, Category B)
// Must appear after the SEXPREC struct and SEXP typedef defined in SEXP.md.

// -------------------------------------------------------------------------
// LENGTH — returns the int element count of any SEXP vector or matrix.
//
// Corresponds to the Rinternals.h declaration:
//   int (LENGTH)(SEXP x);      // line 279
//
// The fake reads s->length, set by allocVector / allocMatrix at construction
// time and by the Python-side caller for input-parameter SEXPs.
// -------------------------------------------------------------------------
inline int LENGTH(SEXP s) {
    return s->length;
}

// XLENGTH — 64-bit variant; R_xlen_t == int in the 32-bit-safe fake build.
inline int XLENGTH(SEXP s) {
    return s->length;
}

// LENGTH_EX — debug variant present in newer R headers (Rinternals.h:1140).
// Ignores file/line; delegates to LENGTH.
inline int LENGTH_EX(SEXP s, const char * /*file*/, int /*line*/) {
    return s->length;
}

// XLENGTH_EX — same as XLENGTH but in the _EX debug form.
inline int XLENGTH_EX(SEXP s) {
    return s->length;
}

// Rf_xlength — alias used by some macro paths.
inline int Rf_xlength(SEXP s) {
    return s->length;
}
```

The `.Call` entry-point wrapper for `rpartexp2` shows how `ArenaFrame` guards scratch memory while `LENGTH` and `allocVector` cooperate. `LENGTH` itself neither allocates nor interacts with the arena; it is shown here for completeness of the boundary pattern:

```cpp
// Boundary wrapper for rpartexp2 — illustrative of the full .Call boundary.
// ArenaFrame is needed because Rpartexp2 (the internal function) uses
// R_alloc / ALLOC for scratch arrays.
extern "C" SEXP rpartexp2_entry(SEXP dtimes, SEXP eps) {
    ArenaFrame _frame;   // arena scratch freed on exit (Invariant 2)
    try {
        return rpartexp2(dtimes, eps);
        // Inside rpartexp2:
        //   int n = LENGTH(dtimes);   => dtimes->length
        //   SEXP keep = PROTECT(allocVector(INTSXP, n));  => heap-allocated
        //   Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
        //   UNPROTECT(1);             => no-op
        //   return keep;              => heap SEXP; outlives ArenaFrame
    } catch (const RError &e) {
        set_python_error(e.what());
        return nullptr;
    }
}
```

The original source lines compile unchanged:

```c
// rpartexp2.c:46 — unchanged original source
int n = LENGTH(dtimes);   // expands to: int n = dtimes->length;

// xpred.c:74 — unchanged original source
ncp = LENGTH(cp2);        // expands to: ncp = cp2->length;
```

- **Arena / Memory Notes:**

  `LENGTH` performs no allocation. It reads the `int length` field from the `SEXPREC` node, which is heap-allocated (via `std::malloc` inside `allocVector` for output SEXPs, or Python-constructed for input-parameter SEXPs). The arena is not involved. The `int n` or `int ncp` result is a plain stack variable; it requires no cleanup.

  In `rpartexp2.c:47`, the `n` value returned by `LENGTH(dtimes)` is passed directly to `allocVector(INTSXP, n)`, which heap-allocates the SEXP `keep`. That heap allocation is independent of the arena and survives past `ArenaFrame` destruction because `keep` is the return value.

- **Explanation:**

  `LENGTH(dtimes)` resolves to `dtimes->length`. The SEXP `dtimes` is an input parameter to `rpartexp2()`, constructed by the Python-side caller before the `.Call` boundary. Python must set `dtimes->length` to the actual number of `double` elements in the `dtimes` array. The returned `int n` is then used as the size argument to `allocVector(INTSXP, n)`, yielding an output SEXP buffer of the correct length.

  `LENGTH(cp2)` in `xpred.c:74` follows the same pattern. `cp2` is an input SEXP parameter to `xpred()`; its `length` field holds the number of cross-validation complexity parameter values. The result `ncp` is used later in `xpred.c` to bound iterations and size the output prediction matrix.

  No `#define` alias for `LENGTH` is required in the fake header. The inline function definition satisfies the call at source level. The original source files are not modified.

---

#### Pattern P2: Read Length of a SEXP Produced by `eval()` for Bounds Validation

- **Locations:** `rpart_callback.c:115`, `rpart_callback.c:149`

- **Original R API Usage:**

```c
/* rpart_callback.c:112-119 — in rpart_callback1 */
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));
dptr = REAL(value);
for (i = 0; i <= rsave; i++)
    z[i] = dptr[i];

/* rpart_callback.c:146-162 — in rpart_callback2 */
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
j = LENGTH(goodness);
dptr = REAL(goodness);
if (ncat == 0) {
    if (j != 2 * (n - 1))
        error("the expression expr1 returned a list of %d elements, "
              "%d required", j, 2 * (n - 1));
    for (i = 0; i < j; i++)
        good[i] = dptr[i];
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (LENGTH — same definition as in Pattern P1)
// No change to the implementation; the distinction is in how the SEXP
// argument was produced (eval() vs. a direct .Call parameter).

inline int LENGTH(SEXP s) {
    return s->length;
}

// The error() calls that follow the LENGTH comparison expand to Rf_error()
// which throws RError (Invariant 1).  The error fake (from error.md):
//
//   inline void Rf_error(const char *fmt, ...) {
//       char buf[1024];
//       va_list ap;
//       va_start(ap, fmt);
//       std::vsnprintf(buf, sizeof(buf), fmt, ap);
//       va_end(ap);
//       throw RError(buf);
//   }
//   #define error Rf_error
//
// The Category E eval() stub (from the eval fake guide):
//
//   typedef SEXP (*eval_fn_t)(SEXP expr, SEXP rho);
//   static eval_fn_t g_eval_fn = nullptr;
//
//   extern "C" void register_eval_fn(eval_fn_t fn) { g_eval_fn = fn; }
//
//   inline SEXP eval(SEXP expr, SEXP rho) {
//       if (!g_eval_fn)
//           throw RError("eval: Python callback not registered. "
//                        "User-defined splits (method=4) require "
//                        "registration via register_eval_fn().");
//       return g_eval_fn(expr, rho);
//   }
//
// When eval() returns a valid SEXP whose length field was set correctly
// by the Python callback, LENGTH(value) correctly reads that length.
```

The `.Call` boundary wrapper for `init_rpcallback` (the entry point that sets up the callback environment used by `rpart_callback1` and `rpart_callback2`) must catch `RError` from the `eval()` stub path and from `LENGTH`-adjacent `error()` calls:

```cpp
// Boundary wrapper for init_rpcallback.
// rpart_callback1 and rpart_callback2 are NOT .Call entry points themselves
// (they are called from C by rpart's internal split machinery).  Their
// RError throws propagate up through the call stack to the rpart() .Call
// wrapper, which is the authoritative catch site:
//
//   extern "C" SEXP rpart_entry(
//           SEXP ncat2, SEXP method2, SEXP opt2,
//           SEXP parms2, SEXP xvals2, SEXP xgrp2,
//           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2) {
//       ArenaFrame _frame;
//       try {
//           return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                        ymat2, xmat2, wt2, ny2, cost2);
//           // Inside rpart -> rpart_callback1/2 -> eval() -> LENGTH()
//           // -> error() if length mismatch -> throws RError
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return nullptr;
//       }
//   }
```

The original source lines compile unchanged:

```c
// rpart_callback.c:115 — unchanged original source
if (LENGTH(value) != (1 + rsave))  // expands to: if (value->length != ...)

// rpart_callback.c:149 — unchanged original source
j = LENGTH(goodness);              // expands to: j = goodness->length;
```

- **Arena / Memory Notes:**

  `LENGTH` performs no allocation. The SEXP `value` or `goodness` was produced by the `eval()` function-pointer stub; the Python-side callback is responsible for constructing a valid `SEXPREC` with `type=REALSXP`, the correct `length`, and a `double *` data buffer. `LENGTH` reads only the `length` field of that Python-constructed node. No arena interaction occurs.

- **Explanation:**

  In both callback functions, `LENGTH` is called on a SEXP that originated from `eval()`. The `eval()` call is a Category E stub: if the Python function pointer has not been registered, the stub throws `RError("eval: Python callback not registered")` before `LENGTH` is ever reached. If the pointer is registered and returns a valid SEXP, then `LENGTH(value)` reads `value->length` — identical to Pattern P1 mechanically.

  The `if (LENGTH(value) != (1 + rsave))` check at line 115 validates that the evaluation expression returned a vector of the expected length (`1 + rsave` elements: one deviance value followed by `rsave` mean values). If the check fails, `error(_("returned value is the wrong length"))` expands to `Rf_error(...)`, which formats the message and throws `RError`. The `RError` propagates up through `rpart_callback1` to `rpart()`'s internal call chain and is caught at the `.Call` boundary wrapper.

  The `j = LENGTH(goodness)` assignment at line 149 stores the length of the goodness-of-split vector. The subsequent code validates `j` against expected values and uses it as a loop bound. In the fake runtime this is purely a field read (`j = goodness->length`) followed by integer arithmetic and comparison.

  These code paths — `rpart_callback1` and `rpart_callback2` — are only reachable when `rpart()` is invoked with `method=4` (user-defined splits). All standard built-in methods (anova, poisson, class, exp) use the `func_table.h` evaluation functions and never invoke the callback infrastructure. For all standard use cases, these `LENGTH` call sites are never reached at runtime, and the absence of a registered `eval` pointer does not matter.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` — `fake_Rinternals.hpp` | The `SEXPREC` struct with an `int length` field. `LENGTH` reads `s->length` directly; the struct definition must precede the `LENGTH` inline function in the header. `SEXP.md` is the authoritative source for `fake_Rinternals.hpp`, which already includes `LENGTH` at line 451 of the code block shown in that guide. This guide confirms and expands that definition. |
| `fake_arena.hpp` (no separate guide; generated once as a foundation) | The `ArenaFrame` RAII struct and `gArenaStack`. Required by the `.Call` wrapper functions that enclose the `LENGTH` call sites (`rpartexp2_entry`, `rpart_entry`, `xpred_entry`). `LENGTH` itself does not use the arena; the dependency is at the enclosing function level. |
| `error.md` — `RError` and `Rf_error` / `#define error` | The `struct RError : public std::runtime_error` definition and the `Rf_error` variadic inline that throws it. Required because `rpart_callback.c:116` and `rpart_callback.c:158-160` call `error(...)` (the `#define error Rf_error` alias) immediately after the `LENGTH` comparison. `RError` must be defined in `fake_Rinternals.hpp` before `Rf_error` is defined. |
| `eval` fake guide (Category E, not yet generated) | The `eval(SEXP expr, SEXP rho)` function-pointer stub. Required at runtime for Pattern P2 (`rpart_callback.c:112` and `rpart_callback.c:146`). Without it, the `eval()` stub throws `RError` before `LENGTH` is reached. `LENGTH` itself compiles without the `eval` guide; the dependency is a runtime prerequisite for the Pattern P2 code paths only. |
| `INTEGER.md` — `fake_Rinternals.hpp` | The `INTEGER` inline function. Not a prerequisite for `LENGTH` itself, but `INTEGER` is called at `rpartexp2.c:48` in the same statement block that begins with the `LENGTH` call at `rpartexp2.c:46`. Both reside in `fake_Rinternals.hpp`; their compile-order dependency is satisfied by their position in the single header file. |
