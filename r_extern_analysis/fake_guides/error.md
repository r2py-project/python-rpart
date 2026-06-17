# Fake Header Implementation Guide: `error`

---

### 1. Overview of `error` in R API

`error` is a preprocessor alias for `Rf_error`, declared in `R_ext/Error.h` via `#define error Rf_error` (when `R_NO_REMAP` is not defined). The underlying function `Rf_error` has the signature `[[noreturn]] void Rf_error(const char *fmt, ...)` — it accepts a `printf`-style format string and variadic arguments, formats the message, and then terminates the current R computation by invoking R's condition-signalling machinery via `longjmp` back to R's top-level error handler. In a live R session, control never returns from `Rf_error`. In the fake runtime, `longjmp` is forbidden (Invariant 1); instead `Rf_error` must format its message and throw a C++ exception of type `RError : public std::runtime_error`, allowing the `.Call` boundary wrapper in Python to catch and translate it into a Python exception.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines (window) | Context |
|---|---|---|
| `rpart.c` | 76–106 | Inside `rpart()` entry point; call follows an `if` that tests `asInteger(method2) > NUM_METHODS`. No `PROTECT`/`UNPROTECT` or allocations at the immediate call site. |
| `rpart.c` | 188–218 | Inside `rpart()` entry point; call follows `(*rp_init)(...)` return value check; `errmsg` is a `const char *` set by the init function. Uses `"%s"` format with `errmsg` argument. |
| `rpart_callback.c` | 9–39 | Inside a `compat_getVar` shim; call fires when `findVar`/`findVarInFrame` returns `R_UnboundValue`. Uses `_("variable '%s' not found")` with `CHAR(PRINTNAME(sym))` — a `const char *` extracted from a symbol SEXP. |
| `rpart_callback.c` | 99–133 | Inside `rpart_callback1()`; two consecutive calls guard the result of `eval(expr2, rho)`: one checks `!isReal(value)`, the other checks `LENGTH(value) != (1 + rsave)`. Both pass only a literal string (no format arguments). |
| `rpart_callback.c` | 133–175 | Inside `rpart_callback2()`; one call guards `!isReal(goodness)` (literal string, no format args); a second call (line 158) uses a full format string with two `int` arguments (`j` and `2*(n-1)`). |
| `xpred.c` | 74–104 | Inside `xpred()` entry point; identical guard to `rpart.c:91` — fires when `asInteger(method2) > NUM_METHODS`. Literal string, no format arguments. |

**Function signature observed in the header.**

From `~/.conda/envs/r-to-python/lib/R/include/R_ext/Error.h`:

```c
/* C++ compilation unit */
[[noreturn]] void Rf_error(const char *, ...) R_PRINTF_FORMAT(1, 2);

void Rf_warning(const char *, ...) R_PRINTF_FORMAT(1, 2);

#ifndef R_NO_REMAP
#define error   Rf_error
#define warning Rf_warning
#endif
```

The `R_PRINTF_FORMAT(1, 2)` decorator is a GCC format-checking attribute; it has no runtime effect.

**Argument types observed across all CSV rows.**

| Call site | Format string | Additional argument type(s) |
|---|---|---|
| `rpart.c:91` | `_("Invalid value for 'method'")` — string literal via `_()` | None |
| `rpart.c:203` | `"%s"` | `const char *errmsg` |
| `rpart_callback.c:24` | `_("variable '%s' not found")` | `const char *` from `CHAR(PRINTNAME(sym))` |
| `rpart_callback.c:114` | `_("return value not a vector")` | None |
| `rpart_callback.c:116` | `_("returned value is the wrong length")` | None |
| `rpart_callback.c:148` | `_("the expression expr1 did not return a vector!")` | None |
| `rpart_callback.c:158` | `"the expression expr1 returned a list of %d elements, %d required"` | `int j`, `int 2*(n-1)` |
| `xpred.c:89` | `_("Invalid value for 'method'")` | None |

**The `_()` gettext macro.**

`rpart_callback.c` and `rpart.c` both conditionally define the `_()` macro:

```c
#ifdef ENABLE_NLS
#include <libintl.h>
#define _(String) dgettext ("rpart", String)
#else
#define _(String) (String)
#endif
```

When `ENABLE_NLS` is not defined (the normal case for a fake/standalone build), `_()` is already a pass-through identity macro. The fake header must define `_()` as `(x)` only if it is not already defined, to avoid conflicts.

**Co-occurring R API items in context windows.**

- `asInteger()` — appears immediately before `error()` calls at `rpart.c:91` and `xpred.c:89`; its result is compared against `NUM_METHODS`.
- `CHAR(PRINTNAME(sym))` — appears as the `%s` argument at `rpart_callback.c:24`; requires the `CHAR` and `PRINTNAME` fakes.
- `eval(expr2, rho)` and `isReal(value)` — appear immediately before `error()` calls at `rpart_callback.c:114,116`; these are R Interpreter Items.
- `LENGTH(value)` — appears at `rpart_callback.c:116` alongside the length-check error call.
- `REAL(goodness)` and `eval(expr1, rho)` — appear before `error()` calls at `rpart_callback.c:148,158`.
- No `PROTECT`/`UNPROTECT` calls are in the immediate scope of any `error()` call (they appear in surrounding scopes, but not between the error check and the `error()` invocation itself).

**Distinct implementation patterns.**

All eight call sites share a single mechanical fake strategy: format a variadic message and throw `RError`. The observable variation is:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Literal string, no format arguments | `rpart.c:91`, `rpart_callback.c:114`, `rpart_callback.c:116`, `rpart_callback.c:148`, `xpred.c:89` | `error(_("some message"))` — the `_()` macro expands to the string itself; no `%` specifiers. |
| P2: `%s` format with `const char *` argument | `rpart.c:203`, `rpart_callback.c:24` | `error("%s", errmsg)` or `error(_("... '%s' ..."), CHAR(...))` |
| P3: Integer format arguments | `rpart_callback.c:158` | `error("... %d ... %d ...", j, 2*(n-1))` — two `int` arguments. |

Patterns P1, P2, and P3 all use the same single fake implementation of `Rf_error`; the variadic argument handling via `vsnprintf` covers all three patterns uniformly. They are separated here only to document the observed argument diversity.

---

### 3. Fake C++ Implementation Strategy

**Category: D — Error, Warning, or Print Function.**

`error` (i.e., `Rf_error`) belongs to Category D. Per Invariant 1, errors must throw a C++ exception; `longjmp`, `setjmp`, R condition handlers, and `abort()` are forbidden.

**The `RError` exception class.**

A project-level exception class is defined once and shared by all Category D fakes:

```cpp
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};
```

This definition must appear in a foundational header (e.g., `fake_RError.hpp` or at the top of the master entry-point header) before any per-item fake header that throws it. The `Rprintf.md` guide was generated before this one and does not define `RError` (it has no error-throwing responsibility). This guide introduces `RError` and all subsequent Category D guides that throw must reference it.

**The `Rf_error` fake mechanism.**

The real `Rf_error` uses `longjmp` internally. The fake replaces this with:

1. Format the variadic message into a fixed-size buffer using `std::vsnprintf`.
2. Construct a `std::string` from the buffer.
3. `throw RError(msg)`.

The function is declared `[[noreturn]]` in the real header. In C++ a function that always throws is legitimately `[[noreturn]]`; the fake preserves this attribute so that the compiler's control-flow analysis remains correct for all call sites (e.g., it knows that code after `error(...)` is unreachable).

**The `_()` gettext macro.**

The fake header defines `_()` as a pass-through only if not already defined:

```cpp
#ifndef _
#  define _(x) (x)
#endif
```

In a standalone build without `ENABLE_NLS`, the original source files define `_(String) (String)` themselves (as shown in `rpart_callback.c:15`). The guard `#ifndef _` prevents a redefinition conflict. In an NLS-enabled build the original `dgettext` definition takes precedence and the fake's definition is suppressed.

**`Rf_warning` coverage.**

`R_ext/Error.h` also declares `Rf_warning` and defines `#define warning Rf_warning`. Per Invariant 1, warnings write to `stderr` via `std::fprintf` and do not throw. The fake header implements both `Rf_error` and `Rf_warning` together (they come from the same source header) so that a single include covers both aliases.

**`#define` aliases preserved.**

The following aliases from the real `R_ext/Error.h` must be reproduced in the fake header:

```cpp
#ifndef R_NO_REMAP
#  define error   Rf_error
#  define warning Rf_warning
#endif
```

Every call site in the rpart source uses the `error(...)` short form, not `Rf_error(...)`. Preserving this alias allows all seven source files to compile without modification.

**`.Call` boundary `try/catch`.**

Every top-level C function registered with `.Call` must be wrapped at the Python boundary by a `try/catch` block that catches `RError` and converts it into a Python exception. This wrapper lives in the Python ctypes glue layer, not in the original C source:

```cpp
// In the generated C++ entry-point wrapper for each .Call function:
extern "C" int call_rpart(...) {
    try {
        // Call the original rpart() function.
        rpart(...);
        return 0;  // success
    } catch (const RError &e) {
        set_last_error(e.what());  // store message for Python to retrieve
        return -1;                 // error sentinel
    }
}
```

On the Python side:

```python
import ctypes

lib = ctypes.CDLL("./librpart_fake.so")

# Retrieve the last C++ error message after a -1 return.
lib.get_last_error.restype = ctypes.c_char_p
lib.get_last_error.argtypes = []

result = lib.call_rpart(...)
if result == -1:
    raise RuntimeError(lib.get_last_error().decode())
```

**Interaction with `R_ext/Print.h`.**

The real `R_ext/Error.h` includes `R_ext/Print.h` solely for the `R_PRINTF_FORMAT` macro. The fake `fake_error.hpp` must therefore either include `fake_Print.hpp` (from the `Rprintf` guide) or define `R_PRINTF_FORMAT` itself. Including `fake_Print.hpp` is preferred: it is already generated and provides the full set of print-related fakes.

---

### 4. Fake Implementation Examples

#### Pattern: Literal String — No Format Arguments (P1)

- **Locations:** `rpart.c:91`, `rpart_callback.c:114`, `rpart_callback.c:116`, `rpart_callback.c:148`, `xpred.c:89`

- **Original R API Usage:**

```c
/* rpart.c:91 and xpred.c:89 — method validation */
if (asInteger(method2) <= NUM_METHODS) {
    /* ... assign function pointers ... */
} else
    error(_("Invalid value for 'method'"));

/* rpart_callback.c:114–116 — eval() result type/length guard */
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));

/* rpart_callback.c:148 — goodness eval() result type guard */
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
```

- **C++ Fake Implementation:**

```cpp
// fake_error.hpp
// Drop-in replacement for R_ext/Error.h.
// Provides: Rf_error, Rf_warning, and the #define aliases error / warning.
// Also defines the RError exception class used at .Call boundaries.
//
// Invariant 1: Rf_error throws RError (never longjmp/abort).
//              Rf_warning writes to stderr (never throws).
//
// Dependencies: fake_Print.hpp (for R_PRINTF_FORMAT definition).

#pragma once
#ifndef FAKE_R_EXT_ERROR_H_
#define FAKE_R_EXT_ERROR_H_

#include "fake_Print.hpp"   // provides R_PRINTF_FORMAT

#include <cstdarg>          // std::va_list, va_start, va_end
#include <cstdio>           // std::vsnprintf, std::fprintf, stderr
#include <stdexcept>        // std::runtime_error
#include <string>           // std::string

// -----------------------------------------------------------------------
// RError — C++ exception thrown by Rf_error in place of longjmp.
//
// Defined once here; all .Call boundary wrappers catch const RError &.
// Any other Category D fake that needs to throw re-uses this class.
// -----------------------------------------------------------------------
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

// -----------------------------------------------------------------------
// Rf_error — formats a printf-style message, then throws RError.
//
// [[noreturn]] is preserved: a function that always throws is legitimately
// noreturn, so the compiler's unreachable-code analysis remains correct for
// all call sites that follow an error() call.
// -----------------------------------------------------------------------
[[noreturn]] inline void Rf_error(const char *fmt, ...) {
    char buf[4096];
    std::va_list args;
    va_start(args, fmt);
    std::vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    throw RError(buf);
}

// -----------------------------------------------------------------------
// Rf_warning — formats a printf-style message and writes to stderr.
//
// Per Invariant 1, warnings do NOT throw; they write to stderr only.
// -----------------------------------------------------------------------
inline void Rf_warning(const char *fmt, ...) {
    char buf[4096];
    std::va_list args;
    va_start(args, fmt);
    std::vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    std::fprintf(stderr, "Warning: %s\n", buf);
}

// -----------------------------------------------------------------------
// Macro aliases — must match R_ext/Error.h exactly so original source
// files compile without modification.
//
// rpart.c, rpart_callback.c, and xpred.c all call error(...) (not
// Rf_error(...)) via this alias.
// -----------------------------------------------------------------------
#ifndef R_NO_REMAP
#  define error   Rf_error
#  define warning Rf_warning
#endif

// -----------------------------------------------------------------------
// _() — gettext pass-through macro.
//
// rpart_callback.c and other files define:
//   #ifdef ENABLE_NLS
//   #  define _(String) dgettext("rpart", String)
//   #else
//   #  define _(String) (String)
//   #endif
//
// In a standalone fake build, ENABLE_NLS is not defined, so the source
// files already define _(x) as (x). The guard below prevents a
// redefinition conflict if the fake header is included before the source
// file's own definition fires.
// -----------------------------------------------------------------------
#ifndef _
#  define _(x) (x)
#endif

#endif /* FAKE_R_EXT_ERROR_H_ */
```

- **Explanation:**

  For P1 call sites (`error(_("some literal message"))`), the `_()` macro expands to the string itself (no `dgettext` lookup), and no `%` format specifiers are present. Inside `Rf_error`, `std::vsnprintf(buf, sizeof(buf), fmt, args)` copies the literal string verbatim into `buf` (no substitution occurs). The result is `throw RError("some literal message")`. The 4096-byte buffer is sufficient for all observed literal messages; messages longer than 4095 bytes are silently truncated at the last byte before the null terminator — acceptable given that none of the rpart messages approach this length.

  The `[[noreturn]]` attribute is preserved in the fake. Without it, compilers would emit spurious "control reaches end of non-void function" warnings at call sites like:

  ```c
  } else
      error(_("Invalid value for 'method'"));
  // compiler must know nothing follows here in the else branch
  ```

  Because `Rf_error` is `[[noreturn]]`, the compiler correctly treats the `else` branch as a dead-end, suppressing the warning.

---

#### Pattern: `%s` Format with `const char *` Argument (P2)

- **Locations:** `rpart.c:203`, `rpart_callback.c:24`

- **Original R API Usage:**

```c
/* rpart.c:203 — init function returned an error string */
errmsg = _("unknown error");
which3 = PROTECT(allocVector(INTSXP, n));
rp.which = INTEGER(which3);
/* ... */
i = (*rp_init)(n, rp.ydata, maxcat, &errmsg, parms, &rp.num_resp, 1, wt);
if (i > 0)
    error("%s", errmsg);

/* rpart_callback.c:24 — variable not found in R environment */
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
    SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
    if (val == R_UnboundValue)
        error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
    return val;
}
```

- **C++ Fake Implementation:**

The same `fake_error.hpp` defined in Pattern P1 handles this case. No additional code is required. For illustration, the boundary wrapper that would enclose `rpart()` or `compat_getVar`'s enclosing `.Call` function is:

```cpp
// Illustrative .Call boundary wrapper for rpart() — lives in the
// Python ctypes glue layer (generated entry-point file), NOT in rpart.c.

#include "fake_error.hpp"
#include "fake_arena.hpp"

// Thread-local storage for the last error message, readable from Python.
static thread_local std::string g_last_error;

extern "C" const char *get_last_error() {
    return g_last_error.c_str();
}

extern "C" int call_rpart(
    /* raw pointer parameters replacing SEXP parameters */
    int *method_val, int method_len,
    /* ... other parameters ... */
) {
    ArenaFrame frame;   // Invariant 2: push arena frame; freed on exit
    try {
        // Reconstruct SEXP wrappers from raw pointers, then call rpart().
        // If rpart() calls error("%s", errmsg), Rf_error formats the
        // message and throws RError; control unwinds here.
        rpart(/* reconstructed SEXP args */);
        return 0;
    } catch (const RError &e) {
        g_last_error = e.what();
        return -1;
    }
}
```

```python
# Python ctypes glue — retrieve error message after a failed .Call.
import ctypes

lib = ctypes.CDLL("./librpart_fake.so")

lib.call_rpart.restype  = ctypes.c_int
lib.call_rpart.argtypes = [/* matching parameter types */]

lib.get_last_error.restype  = ctypes.c_char_p
lib.get_last_error.argtypes = []

result = lib.call_rpart(/* arguments */)
if result == -1:
    msg = lib.get_last_error()
    raise RuntimeError(msg.decode("utf-8") if msg else "unknown error in rpart")
```

- **Explanation:**

  At `rpart.c:203`, `errmsg` is a `const char *` written by the `(*rp_init)` callback. `error("%s", errmsg)` passes it as the sole variadic argument. Inside `Rf_error`, `std::vsnprintf(buf, sizeof(buf), "%s", args)` substitutes `errmsg` into `buf` and the resulting string becomes the `RError` message. The `PROTECT(allocVector(...))` call that precedes this point in the function body allocates heap memory for `which3`; that memory is not freed on the error path because `PROTECT`/`UNPROTECT` are no-ops in the fake runtime. In practice, the Python process exits after catching the error at the boundary, so the leaked SEXP allocation is acceptable. If leak-freedom is required, the `SEXP` allocations must be tracked in the `ArenaFrame` — see the `allocVector.md` guide for discussion.

  At `rpart_callback.c:24`, `CHAR(PRINTNAME(sym))` yields a `const char *` pointing into the name string of a symbol SEXP. The `compat_getVar` function is a static shim invoked only via the `R_getVar` macro on R < 4.5.0 path; it is called from within `init_rpcallback`, which is itself a `.Call`-registered function. The `ArenaFrame` guard must therefore be placed in the entry-point wrapper for `init_rpcallback`, not inside `compat_getVar` itself. If the pointer `val == R_UnboundValue` check fires, `Rf_error` throws `RError`, which unwinds through `compat_getVar` and `R_getVar` back to the `call_init_rpcallback` boundary wrapper.

---

#### Pattern: Integer `%d` Format Arguments (P3)

- **Locations:** `rpart_callback.c:158`

- **Original R API Usage:**

```c
/* rpart_callback.c:158 — inside rpart_callback2(), ncat == 0 branch */
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
j = LENGTH(goodness);
dptr = REAL(goodness);

if (ncat == 0) {
    if (j != 2 * (n - 1))
        error("the expression expr1 returned a list of %d elements, %d required",
              j, 2 * (n - 1));
    for (i = 0; i < j; i++)
        good[i] = dptr[i];
}
```

- **C++ Fake Implementation:**

The same `fake_error.hpp` defined in Pattern P1 handles this case. `std::vsnprintf` supports `%d` format specifiers natively; no additional code is required. The call expands as:

```
buf = "the expression expr1 returned a list of 5 elements, 8 required"
throw RError(buf)
```

(with actual values of `j` and `2*(n-1)` substituted at runtime).

- **Explanation:**

  This call site does not use the `_()` macro: the format string is a plain C string literal, not wrapped in `_()`. This is intentional in the original source — the message contains two `%d` placeholders, and `dgettext` with format arguments requires careful use; the rpart authors chose to leave it un-translated. The fake handles this identically to all other patterns: `std::vsnprintf` substitutes the two `int` values and the result is thrown as `RError`.

  This call site is inside `rpart_callback2()`, which is invoked from the user-defined splitting code path (method = 4 in rpart). That code path requires `eval(expr1, rho)` to be operational. In the fake runtime, `eval` is an R Interpreter Item (Invariant 3) — unless the Python-side function pointer bridge for `eval` has been registered, `eval()` will throw `RError("eval() not available: no Python callback registered")` before reaching the `error()` call at line 158. The `error.md` fake covers the throw mechanism; the `eval.md` / `R_getVar.md` guides cover the interpreter bridge.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `Rprintf.md` | Provides `fake_Print.hpp`, which defines `R_PRINTF_FORMAT(M, N)`. `fake_error.hpp` includes `fake_Print.hpp` to obtain this macro before declaring `Rf_error`. |
| `SEXP.md` | Provides the `SEXPREC` struct and `SEXP` typedef. Required because `rpart_callback.c` uses `SEXP sym` as the argument to `PRINTNAME(sym)` / `CHAR(...)` at the P2 call site (`rpart_callback.c:24`). The `error` fake itself does not reference `SEXP`, but the translation unit that calls `error` at line 24 does. |
| `CHAR.md` | Provides the fake `CHAR()` accessor used as the `%s` argument at `rpart_callback.c:24`. Must be compiled before `rpart_callback.c`. |
| `PRINTNAME.md` | Provides the fake `PRINTNAME()` accessor used as the argument to `CHAR()` at `rpart_callback.c:24`. Must be compiled before `rpart_callback.c`. |

`fake_error.hpp` itself has no compile-order dependency on `allocVector.md`, `INTEGER.md`, `REAL.md`, or `fake_arena.hpp` — it only defines `Rf_error`, `Rf_warning`, `RError`, `error`, `warning`, and `_()`. The `ArenaFrame` guard is the responsibility of the generated `.Call` boundary entry-point wrappers, not of `fake_error.hpp`.

The master entry-point header that replaces `R.h` should include `fake_error.hpp` after `fake_Print.hpp` and before any rpart source-level includes, ensuring that the `error` alias and `RError` class are visible to every translation unit in the build.
