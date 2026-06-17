# Fake Header Implementation Guide: `warning`

---

### 1. Overview of `warning` in R API

`warning` is a preprocessor alias for `Rf_warning`, declared in `R_ext/Error.h` via `#define warning Rf_warning` (when `R_NO_REMAP` is not defined). The underlying function `Rf_warning` has the signature `void Rf_warning(const char *fmt, ...)` — it accepts a `printf`-style format string and variadic arguments, formats the message, and delivers it to R's warning-handling machinery. In a live R session, `Rf_warning` may invoke R condition handlers or accumulate warnings for later display; control always returns to the caller. In the fake runtime, no R condition system exists; per Invariant 1, `Rf_warning` must write the formatted message to `stderr` via `std::fprintf` and return normally — it must never throw, `longjmp`, or call `abort()`.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context window summary |
|---|---|---|
| `rundown.c` | 48 | Inside `rundown()`, in an `oops:` error-recovery block reached via `goto oops`. Fires only if `rp.usesurrogate >= 2`, a branch the author considers impossible in practice. No adjacent `PROTECT`/`UNPROTECT`, no SEXP allocations, no arena allocations. The call uses a plain string literal with no format specifiers. |
| `rundown2.c` | 48 | Structurally identical to `rundown.c:48`. Inside `rundown2()`, same `oops:` block and same impossible-in-practice guard. Plain string literal, no format specifiers, no adjacent R API calls. |

**Full context window — `rundown.c` (lines 33–49):**

```c
    return;

oops:;
    if (rp.usesurrogate < 2) {  /* must have hit a missing value */
        for (; i < rp.num_unique_cp; i++)
            xpred[i] = otree->response_est[0];
        xtemp[i] = (*rp_error) (rp.ydata[obs2], otree->response_est);
        return;
    }
    /*
     * I never really expect to get to this code.  It can only happen if
     *  the last cp on my list is smaller than the terminal cp of the
     *  xval tree just built.  This is impossible (I think).  But just in
     *  case I put a message here.
     */
    warning("Warning message--see rundown.c");
}
```

**Full context window — `rundown2.c` (lines 33–49):**

```c
    return;

oops:;
    if (rp.usesurrogate < 2) {  /* must have hit a missing value */
        for (; i < rp.num_unique_cp; i++)
            for (j = 0; j < nresp; j++)
                xpred[k++] = otree->response_est[j];
        return;
    }
    /*
     * I never really expect to get to this code.  It can only happen if
     *  the last cp on my list is smaller than the terminal cp of the
     *  xval tree just built.  This is impossible (I think).  But just in
     *  case I put a message here.
     */
    warning("Warning message--see rundown2.c");
}
```

**Function signature observed in the header.**

From `~/.conda/envs/r-to-python/lib/R/include/R_ext/Error.h`:

```c
void Rf_warning(const char *, ...) R_PRINTF_FORMAT(1, 2);

#ifndef R_NO_REMAP
#define warning Rf_warning
#endif
```

`R_PRINTF_FORMAT(1, 2)` is a GCC format-checking attribute with no runtime effect.

**Argument types observed across all CSV rows.**

| Call site | Format string | Additional argument types |
|---|---|---|
| `rundown.c:48` | `"Warning message--see rundown.c"` — plain string literal | None |
| `rundown2.c:48` | `"Warning message--see rundown2.c"` — plain string literal | None |

Both call sites use a single plain string argument with no `%` format specifiers. There is exactly one distinct usage pattern.

**Co-occurring R API items in context windows.**

Neither call site has any adjacent R API calls. The `oops:` blocks contain only plain C array accesses (`otree->response_est`, `rp.ydata`, `xpred`, `xtemp`) and the `(*rp_error)` function-pointer call — all of which are internal rpart types, not R API items.

**Distinct implementation patterns.**

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Plain string literal, no format arguments | `rundown.c:48`, `rundown2.c:48` | `warning("Warning message--see rundown.c")` — no `%` specifiers; `std::vsnprintf` copies the string verbatim. |

Both rows share a single fake strategy. No separate treatment is needed.

---

### 3. Fake C++ Implementation Strategy

**Category: D — Error, Warning, or Print Function.**

`warning` (i.e., `Rf_warning`) belongs to Category D. Per Invariant 1:
- Warnings must write to `stderr` via `std::fprintf`. They must not throw.
- Only errors (`Rf_error`) throw `RError`; `Rf_warning` is the non-throwing counterpart.

**Relationship to `error.md`.**

The `error.md` guide has already been generated. It defines `fake_error.hpp`, which implements both `Rf_error` (throwing) and `Rf_warning` (non-throwing) in a single header, along with the `RError` exception class and the `#define error Rf_error` / `#define warning Rf_warning` aliases. This design was intentional: `Rf_error` and `Rf_warning` are declared in the same source header (`R_ext/Error.h`), so they naturally belong in the same fake header.

**Consequence for this guide.**

The `warning` fake is already fully covered by `fake_error.hpp` from `error.md`. No new header file is required. This guide documents the `warning`-specific usage patterns in rpart and confirms that the implementation in `fake_error.hpp` is correct and sufficient.

**The `Rf_warning` fake mechanism.**

The fake implementation in `fake_error.hpp`:

1. Accepts a `printf`-style format string and variadic arguments.
2. Formats the message into a fixed-size buffer using `std::vsnprintf`.
3. Writes the formatted message to `stderr` via `std::fprintf(stderr, "Warning: %s\n", buf)`.
4. Returns normally — no exception is thrown, no `longjmp` is issued.

**`#define` alias preserved.**

```cpp
#ifndef R_NO_REMAP
#  define warning Rf_warning
#endif
```

Both `rundown.c` and `rundown2.c` call `warning(...)` (not `Rf_warning(...)`). This alias, already present in `fake_error.hpp`, ensures both source files compile without modification.

**No `ArenaFrame` interaction.**

Neither call site performs arena-based allocations or SEXP allocations. `rundown()` and `rundown2()` are internal helper functions called from `xval()`, not `.Call`-registered entry points. The `ArenaFrame` guard is placed at the entry of the enclosing `.Call` entry-point wrapper (e.g., `xval()`'s wrapper), not inside `rundown()` or `rundown2()`. The `warning()` call itself does not interact with the arena at all.

**No `.Call` boundary `catch` required.**

Because `Rf_warning` does not throw, no `try/catch` block is needed at the `.Call` boundary for the warning path. The `catch (const RError &e)` block already present in every `.Call` wrapper (from `error.md`) is unaffected by `warning` calls.

---

### 4. Fake Implementation Examples

#### Pattern: Plain String Literal — No Format Arguments (P1)

- **Locations:** `rundown.c:48`, `rundown2.c:48`

- **Original R API Usage:**

```c
/* rundown.c:48 — impossible-branch diagnostic, inside oops: block */
warning("Warning message--see rundown.c");

/* rundown2.c:48 — structurally identical */
warning("Warning message--see rundown2.c");
```

- **C++ Fake Implementation:**

The implementation lives entirely in `fake_error.hpp`, which was defined by `error.md`. The `Rf_warning` portion is reproduced here for reference:

```cpp
// fake_error.hpp  (excerpt — Rf_warning section)
// Full file defined in error.md; this excerpt shows only the warning-relevant parts.
//
// Invariant 1: Rf_warning writes to stderr and returns normally (never throws).

#include <cstdarg>   // std::va_list, va_start, va_end
#include <cstdio>    // std::vsnprintf, std::fprintf, stderr

// -----------------------------------------------------------------------
// Rf_warning — formats a printf-style message and writes to stderr.
//
// Does NOT throw. Does NOT longjmp. Returns void to the caller.
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
// Macro alias — preserves R_ext/Error.h convention.
// rundown.c and rundown2.c call warning(...) via this alias.
// -----------------------------------------------------------------------
#ifndef R_NO_REMAP
#  define warning Rf_warning
#endif
```

For completeness, the `ArenaFrame` guard that must appear at the entry of the enclosing `.Call` wrapper (`xval`'s entry point) is shown below — it is not needed inside `rundown()` / `rundown2()` themselves:

```cpp
// In the generated C++ entry-point wrapper for xval() — NOT inside rundown.c.
#include "fake_error.hpp"
#include "fake_arena.hpp"

extern "C" int call_xval(/* raw pointer parameters */) {
    ArenaFrame frame;  // Invariant 2: push arena frame; freed at scope exit.
    try {
        xval(/* arguments */);
        return 0;
    } catch (const RError &e) {
        g_last_error = e.what();
        return -1;
    }
    // If warning() fires inside rundown() or rundown2(), it writes to stderr
    // and returns normally — no catch block is triggered, return 0 executes.
}
```

- **Explanation:**

  At `rundown.c:48` and `rundown2.c:48`, the `warning(...)` call expands via the `#define warning Rf_warning` alias to `Rf_warning("Warning message--see rundown.c")`. Inside `Rf_warning`, `std::vsnprintf(buf, sizeof(buf), "Warning message--see rundown.c", args)` copies the literal string verbatim into `buf` — no `%` substitution occurs because there are no format specifiers. `std::fprintf(stderr, "Warning: %s\n", buf)` then writes `Warning: Warning message--see rundown.c` to `stderr`. Control returns normally to the caller (the `oops:` block), which falls through to the closing `}` of the function.

  The 4096-byte buffer is more than sufficient for both messages. The `[[noreturn]]` attribute is absent from `Rf_warning` (it is not `[[noreturn]]` in the real API either), so no compiler annotations need to change.

  The original source files `rundown.c` and `rundown2.c` include `rpart.h` and `rpartproto.h` — neither of which includes `R_ext/Error.h` directly in a standalone build. The `warning` macro reaches `rundown.c` through the master fake header (which includes `fake_error.hpp`), making the alias visible at compile time without any modification to the original sources.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `error.md` | Provides `fake_error.hpp`, which contains the complete `Rf_warning` inline function, the `#define warning Rf_warning` alias, the `RError` exception class, and `Rf_error`. The `warning` guide adds no new header file; it depends entirely on `fake_error.hpp`. |
| `Rprintf.md` | Provides `fake_Print.hpp`, which defines `R_PRINTF_FORMAT(M, N)`. `fake_error.hpp` includes `fake_Print.hpp` to obtain this macro before declaring `Rf_warning`. |

No other guides are required to compile `rundown.c` or `rundown2.c`. Neither file uses SEXP types, arena allocation, or any other R API item beyond `warning`.
