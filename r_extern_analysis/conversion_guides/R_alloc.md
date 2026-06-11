# Conversion Guide: `R_alloc`

## 1. Overview of `R_alloc` in R API

`R_alloc` is declared in `R_ext/Memory.h` (included transitively through `R.h`) with the signature:

```c
char *R_alloc(R_SIZE_T nelem, int eltsize);
```

It allocates `nelem * eltsize` bytes of memory from R's internal garbage-collector-managed heap ("R stack") and returns a `char *` to the start of the block. The allocation is **automatically reclaimed** by R when the top-level `.Call`/`.External` invocation that triggered the allocation returns — no explicit `free` is ever required or permitted. Within the rpart package, `R_alloc` is exposed exclusively through the convenience macro defined in `rpart.h`:

```c
#define ALLOC(a, b)  R_alloc(a, b)
```

Every internal scratch buffer that does not need to survive across separate `.Call` invocations uses `ALLOC`/`R_alloc`; objects that must persist between calls use `CALLOC` (`R_chk_calloc`) instead and are released with `R_Free`.

---

## 2. Contextual Usage Analysis

### Declaration site

| File | Line | Statement |
|------|------|-----------|
| `rpart.h` | 25 | `#define ALLOC(a,b)  R_alloc(a,b)` |

### All call sites (via the `ALLOC` macro)

| File | Line(s) | Allocated type | Purpose |
|------|---------|----------------|---------|
| `rpart.c` | 123, 128 | `double **` | Ragged-array pointer tables (`rp.xdata`, `rp.ydata`) |
| `rpart.c` | 138–141 | `int *`, `double *`, `double **`, `double *` | Flat scratch vectors (`rp.tempvec`, `rp.xtemp`, `rp.ytemp`, `rp.wtemp`) |
| `rpart.c` | 148–149 | `int **`, `int *` | Ragged sort-index table (`rp.sorts`, `rp.sorts[0]`) |
| `rpart.c` | 174 | `int *` | Copy of sort indices for cross-validation (`savesort`) |
| `rpart.c` | 182–183, 188 | `int *`, `double *` | Conditional categorical scratch (`rp.csplit`, `rp.lwt`) |
| `rpart.c` | 206 | `pNode` (`Node *`) | Single tree-node struct of variable size (`nodesize`) |
| `rpart.c` | 219 | `CpTable` (`cpTable *`) | Single cp-table struct |
| `rpart.c` | 262, 294 | `double **`, `int **` | Ragged-array index tables over pre-existing output buffers (`ddnode`, `ccsplit`) |
| `xpred.c` | 122–192 | (same categories as `rpart.c`) | Cross-validation counterparts of the above |
| `gini.c` | 48–65 | `double *`, `int *`, `double **` | Flat class-count scratch vectors and pointer table |
| `anova.c` | 18, 20 | `int *`, `double *` | Flat scratch vectors for categorical splits |
| `poisson.c` | 23, 26 | `double *`, `int *` | Flat scratch vectors for Poisson splits |
| `graycode.c` | 20 | `int *` | Flat integer work vector |
| `usersplit.c` | 24 | `double *` | Flat scratch vector for user-defined split |
| `pred_rpart.c` | 54, 58–59 | `const int **`, `const double **` | Ragged-array pointer tables over read-only input matrices |
| `make_cp_list.c` | 61 | `CpTable` | Single cp-table struct node inserted into a linked list |

### Distinct data types and memory management properties

- **Lifetime:** All `R_alloc` blocks live until the enclosing `.Call` entry point returns; there are zero explicit `free` calls. The comment in `rpart.h` makes this explicit: *"Memory defined with `R_alloc` is removed automatically"*.
- **Types allocated:** flat `int *` arrays, flat `double *` arrays, arrays of pointers (`double **`, `int **`), and single heap structs cast from `char *` (`pNode`, `CpTable`).
- **No initialisation:** `R_alloc` does **not** zero-initialise; `memset` or explicit loops are used where zero-filled memory is required.
- **Interaction with `PROTECT`/`UNPROTECT`:** `R_alloc` allocations are completely orthogonal to R's GC protection stack. They are never `PROTECT`-ed; they are managed through the GC's own save-restore mechanism (`vmaxget`/`vmaxset`), which is transparent to the programmer.

### Usage patterns

1. **Flat 1-D scratch arrays** — `(T *) ALLOC(n, sizeof(T))` producing a plain C array of scalars or structs.
2. **Ragged-array index tables over a flat buffer** — `(T **) ALLOC(ncols, sizeof(T *))` followed by pointer arithmetic to subdivide a separately allocated flat buffer into column views.
3. **Single-object struct allocation** — `(StructType *) ALLOC(1, sizeof(StructType))` to place a variable-size or fixed-size struct on R's managed heap.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_alloc` belongs exclusively to R's `.Call`/`.External` framework. When converting to the `.C` API, the central constraint is that **all memory crossing the R–C boundary must be allocated on the R side** before the call; the C function receives pre-allocated raw pointers and must not allocate or free any of them.

The conversion strategy proceeds in three tiers corresponding to the three usage patterns:

**Tier 1 — Flat 1-D scratch arrays** (`int *`, `double *`): Replace `(T *) ALLOC(n, sizeof(T))` with an extra `.C` argument of type `integer(n)` or `double(n)` allocated in R before the call. The C function gains the corresponding `int *` or `double *` parameter; no allocation statement remains in C. Because `.C` copies arguments in and back out, the buffer is naturally protected for the duration of the call.

**Tier 2 — Ragged-array index tables** (`double **`, `int **`, `const double **`, `const int **`): `R_alloc` is used here purely to create a C-internal array of pointers that sub-divides an existing flat buffer — it never crosses the R–C boundary and is not observable from R. Replace these allocations with standard C `malloc` (or a fixed-size stack array when the count is bounded at compile time), and pair each `malloc` with an explicit `free` before the function returns. Alternatively, if the maximum pointer-table length is known at the call site, declare it as a variable-length array (`T *ptrs[n]`) or pre-allocate it in R and pass it in as an additional `int *` or `double *` argument. Because the pointer table is only ever used internally, passing it from R is the cleanest option: the table slot content (indices into the flat buffer) is computed entirely inside C.

**Tier 3 — Single-object struct allocation** (`pNode`, `CpTable`): Variable-size or pointer-linked structs have no direct `.C` equivalent. The correct strategy mirrors the one documented in the `R_Free.md` guide: replace each struct with a set of parallel flat arrays (one per struct field), pre-allocated by R and passed in as separate `.C` arguments. Each "object" is then an integer index into those arrays. Single-purpose temporary structs (e.g., a one-shot `cpTable` node in `make_cp_list.c`) can alternatively be allocated on the C stack (`StructType node; memset(&node, 0, sizeof(node));`) when the struct contains no heap-pointer fields that outlive the call.

### Why this approach is `.C`-compatible

The `.C` API allows only `int *`, `double *`, `char **`, `Rcomplex *`, and `unsigned char *` as argument types (see `.C`/`.Fortran` documentation). `R_alloc` returns `char *` used as a generic pointer to an arbitrary type — this typing idiom is meaningful only inside the `.Call` framework. By moving all allocations to R-side `integer(n)` / `double(n)` vectors, every value crossing the boundary has an explicit type, and R manages the memory lifetime transparently.

### Type mapping summary

| `.Call` pattern | `.C`-compatible equivalent |
|---|---|
| `(int *)    ALLOC(n, sizeof(int))` | `int *` pre-allocated by R: `integer(n)` |
| `(double *) ALLOC(n, sizeof(double))` | `double *` pre-allocated by R: `double(n)` |
| `(T **)     ALLOC(n, sizeof(T *))` (internal pointer table) | `malloc(n * sizeof(T *))` + `free()`; or fixed-size stack VLA |
| `(pNode)    ALLOC(1, nodesize)` | Parallel flat arrays pre-allocated by R; or C stack struct when lifetime is one call |
| `(CpTable)  ALLOC(1, sizeof(cpTable))` | C stack struct (`cpTable node; memset(...)`) for single-use; parallel flat arrays for linked lists |

---

## 4. Step-by-Step Conversion Examples

### Pattern: Flat 1-D Scratch Array Allocation

- **Locations:** `rpart.c` lines 138–141, 174, 182–183, 188; `xpred.c` lines 137–140, 172, 179–180, 185, 191; `gini.c` lines 48, 51, 54, 65; `anova.c` lines 18, 20; `poisson.c` lines 23, 26; `graycode.c` line 20; `usersplit.c` line 24

- **Original Context (.Call):**

```c
/* rpart.c / xpred.c — representative cluster */
rp.tempvec = (int *)    ALLOC(n, sizeof(int));
rp.xtemp   = (double *) ALLOC(n, sizeof(double));
rp.wtemp   = (double *) ALLOC(n, sizeof(double));

/* Conditional scratch (categorical variables only) */
if (maxcat > 0) {
    rp.csplit = (int *)    ALLOC(3 * maxcat, sizeof(int));
    rp.lwt    = (double *) ALLOC(2 * maxcat, sizeof(double));
    rp.left   = rp.csplit + maxcat;
    rp.right  = rp.left   + maxcat;
    rp.rwt    = rp.lwt    + maxcat;
} else
    rp.csplit = (int *) ALLOC(1, sizeof(int));

/* usersplit.c */
uscratch = (double *) ALLOC(
    n_return + 1 > 2 * n ? n_return + 1 : 2 * n,
    sizeof(double));
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Each ALLOC(...) is removed.  The corresponding raw pointer becomes
 * a function argument pre-allocated by the R caller.
 * No R_alloc, no free, no PROTECT/UNPROTECT.
 */
void rpart_c(
    /* ... existing input args ... */
    int    *tempvec,     /* was: ALLOC(n, sizeof(int))           — R: integer(n)          */
    double *xtemp,       /* was: ALLOC(n, sizeof(double))        — R: double(n)           */
    double *wtemp,       /* was: ALLOC(n, sizeof(double))        — R: double(n)           */
    int    *csplit_buf,  /* was: ALLOC(3*maxcat, sizeof(int))    — R: integer(3*maxcat)   */
    double *lwt_buf,     /* was: ALLOC(2*maxcat, sizeof(double)) — R: double(2*maxcat)    */
    /* ... */)
{
    /* Pointer arithmetic over pre-allocated contiguous buffers: unchanged */
    rp.tempvec = tempvec;
    rp.xtemp   = xtemp;
    rp.wtemp   = wtemp;

    if (maxcat > 0) {
        rp.csplit = csplit_buf;
        rp.left   = rp.csplit + maxcat;
        rp.right  = rp.left   + maxcat;
        rp.lwt    = lwt_buf;
        rp.rwt    = rp.lwt + maxcat;
    } else {
        rp.csplit = csplit_buf;  /* length-1 buffer still provided by R */
    }

    /* usersplit.c: scratch length is max(n_return+1, 2*n) */
    /* uscratch = uscratch_buf; — pointer assigned from argument */
}
```

Corresponding R-side call:

```r
maxcat <- max(rp_numcat)
csplit_len <- if (maxcat > 0L) 3L * maxcat else 1L
lwt_len    <- if (maxcat > 0L) 2L * maxcat else 0L

result <- .C("rpart_c",
    # ... input args ...
    tempvec     = integer(n),
    xtemp       = double(n),
    wtemp       = double(n),
    csplit_buf  = integer(csplit_len),
    lwt_buf     = double(lwt_len))
```

- **Explanation:**
  - `ALLOC(n, sizeof(int))` and `ALLOC(n, sizeof(double))` are removed from C entirely; the corresponding buffers are pre-allocated on the R side as `integer(n)` and `double(n)`.
  - The pointer arithmetic that subdivides a buffer into sub-ranges (`rp.left = rp.csplit + maxcat`) is preserved verbatim — only the initial allocation line disappears.
  - The conditional `else ALLOC(1, sizeof(int))` guard becomes a length-1 buffer always supplied by R; the C guard on `maxcat > 0` remains unchanged.
  - For `usersplit.c`, the `max(n_return+1, 2*n)` length computation moves to the R side: `uscratch_len <- max(n_return + 1L, 2L * n)`.

---

### Pattern: Ragged-Array Index Table over a Flat Buffer

- **Locations:** `rpart.c` lines 123, 128, 140, 148–149, 262, 294; `xpred.c` lines 122, 127, 139, 147–148; `pred_rpart.c` lines 54, 58–59; `gini.c` lines 59–60

- **Original Context (.Call):**

```c
/* rpart.c:122-134 — column-view pointers over a column-major matrix */
dptr = REAL(xmat2);
rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
for (i = 0; i < rp.nvar; i++) {
    rp.xdata[i] = dptr;
    dptr += n;
}

rp.ydata = (double **) ALLOC(n, sizeof(double *));
dptr = REAL(ymat2);
for (i = 0; i < n; i++) {
    rp.ydata[i] = dptr;
    dptr += rp.num_y;
}

/* rpart.c:148-152 — sort index pointer table over flat sort buffer */
rp.sorts    = (int **) ALLOC(rp.nvar, sizeof(int *));
rp.sorts[0] = (int *)  ALLOC(n * rp.nvar, sizeof(int));
for (i = 0; i < rp.nvar; i++)
    rp.sorts[i] = rp.sorts[0] + i * n;

/* rpart.c:262 — pointer table over an SEXP output matrix */
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);           /* SEXP output buffer */
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;
}

/* pred_rpart.c:54-63 — pointer tables over read-only input matrices */
csplit = (const int **)    ALLOC((int) dimc[1], sizeof(int *));
xmiss  = (const int **)    ALLOC((int) dimx[1], sizeof(int *));
xdata  = (const double **) ALLOC((int) dimx[1], sizeof(double *));
for (i = 0; i < dimx[1]; i++) {
    xmiss[i] = &(xmiss2[i * dimx[0]]);
    xdata[i] = &(xdata2[i * dimx[0]]);
}
```

- **C/C++ Equivalent (.C):**

```c
#include <stdlib.h>   /* malloc, free */

void rpart_c(
    const double *xmat,   /* pre-allocated flat input, length n * nvar (column-major) */
    const double *ymat,   /* pre-allocated flat input, length n * num_y (row-major)   */
    const int    *sorts_flat, /* pre-allocated flat sort index buffer, length n * nvar */
    /* ... */)
{
    /*
     * Pointer tables are C-internal bookkeeping only — never returned to R.
     * Use malloc/free (or stack VLAs) rather than R_alloc.
     */
    double **xdata = (double **) malloc(nvar * sizeof(double *));
    double **ydata = (double **) malloc(n    * sizeof(double *));
    int    **sorts = (int **)    malloc(nvar * sizeof(int *));

    /* Column-view setup: identical logic, different pointer source */
    const double *dptr = xmat;
    for (int i = 0; i < nvar; i++) {
        xdata[i] = (double *)(dptr);   /* cast away const for internal use */
        dptr += n;
    }
    dptr = ymat;
    for (int i = 0; i < n; i++) {
        ydata[i] = (double *)(dptr);
        dptr += num_y;
    }
    for (int i = 0; i < nvar; i++)
        sorts[i] = (int *)(sorts_flat) + i * n;

    /* For output matrix pointer tables (ddnode etc.), point into the
     * pre-allocated output buffer argument instead of REAL(sexp): */
    double **ddnode = (double **) malloc((3 + num_resp) * sizeof(double *));
    double *out_dnode_ptr = out_dnode;   /* was: REAL(dnode3) */
    for (int i = 0; i < 3 + num_resp; i++) {
        ddnode[i] = out_dnode_ptr;
        out_dnode_ptr += nodecount;
    }

    /* ... algorithm body using xdata[i][k], ydata[i][k], sorts[i][k],
           ddnode[i][j] unchanged ... */

    free(xdata);
    free(ydata);
    free(sorts);
    free(ddnode);
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
    xmat       = as.double(xmat_matrix),   # flat column-major; was REAL(xmat2)
    ymat       = as.double(ymat_matrix),   # flat row-major;    was REAL(ymat2)
    sorts_flat = integer(n * nvar),        # output sort buffer; was ALLOC(n*nvar, sizeof(int))
    out_dnode  = double(nodecount * (3L + num_resp)),
    # ...
)
```

- **Explanation:**
  - `ALLOC(nvar, sizeof(double *))` and similar pointer-table allocations never appear in R's type system and must be replaced by `malloc`/`free` (or a stack VLA) inside C. These are pure C bookkeeping arrays that partition a flat buffer into column views — they are always constructed, used, and discarded within one C function call.
  - The *flat data buffers* that the pointer tables index (`xmat`, `ymat`, `sorts_flat`, `out_dnode`) are either existing input arguments (already passed from R) or new output arguments pre-allocated in R; no change to the data buffer allocation is needed.
  - `REAL(sexp)` and `INTEGER(sexp)` calls that previously extracted the raw pointer from an `SEXP` are replaced by the corresponding function argument name directly, since the argument already carries the raw pointer.
  - `free` calls for the pointer tables are placed at the end of the function, before return, to avoid memory leaks. Because these arrays are never passed back to R, their contents are not copied out by `.C`.

---

### Pattern: Single-Object Struct Allocation

- **Locations:** `rpart.c` lines 206, 219; `xpred.c` line 192; `make_cp_list.c` line 61

- **Original Context (.Call):**

```c
/* rpart.c:205-208 — variable-size Node struct */
nodesize = sizeof(Node) + (rp.num_resp - 20) * sizeof(double);
tree = (pNode) ALLOC(1, nodesize);
memset(tree, 0, nodesize);
tree->num_obs = n;

/* rpart.c:219-226 — fixed-size cpTable struct (list head) */
CpTable cptable = (CpTable) ALLOC(1, sizeof(cpTable));
cptable->cp     = tree->complexity;
cptable->risk   = tree->risk;
cptable->nsplit = 0;
cptable->forward = 0;

/* make_cp_list.c:61-72 — fixed-size cpTable struct (list node insertion) */
cplist = (CpTable) ALLOC(1, sizeof(cpTable));
cplist->cp    = me_cp;
cplist->risk  = cplist->xrisk = cplist->xstd = 0;
cplist->nsplit = 0;
cplist->back  = cptemp;
cplist->forward = cptemp->forward;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Option A — C stack allocation (for single-use, non-recursive structs):
 *   Suitable for cpTable nodes where the linked-list structure
 *   can be replaced by a flat array or the single head node only.
 */
void rpart_c(/* ... */)
{
    /* Fixed-size struct on the stack: no malloc, no R_alloc */
    cpTable cptable_head;
    memset(&cptable_head, 0, sizeof(cpTable));
    cptable_head.cp     = tree_complexity;
    cptable_head.risk   = tree_risk;
    cptable_head.nsplit = 0;
    /* forward/back pointers are replaced by flat-array indices (see below) */
}

/*
 * Option B — Flat parallel arrays for linked-list or tree structs:
 *   Required for pNode (variable-size) and any cpTable linked list
 *   that grows dynamically.  Each struct field becomes a separate
 *   pre-allocated array argument.  See also the R_Free.md guide.
 */
void rpart_c(
    /* cpTable parallel arrays (pre-allocated by R for max_cp entries) */
    double *cptable_cp,      /* double(max_cp) */
    double *cptable_risk,    /* double(max_cp) */
    double *cptable_xrisk,   /* double(max_cp) */
    double *cptable_xstd,    /* double(max_cp) */
    int    *cptable_nsplit,  /* integer(max_cp) */
    int    *cptable_forward, /* integer(max_cp) — index, -1 = no next */
    int    *cptable_back,    /* integer(max_cp) — index, -1 = no prev */
    int    *num_unique_cp,   /* scalar output: how many cp entries used */
    /* ... Node parallel arrays ... */
    /* ... */)
{
    /* "Allocate" the head cp entry: use slot 0 */
    int cp_head = 0;
    cptable_cp[cp_head]      = initial_complexity;
    cptable_risk[cp_head]    = initial_risk;
    cptable_nsplit[cp_head]  = 0;
    cptable_forward[cp_head] = -1;  /* sentinel: no next */
    cptable_back[cp_head]    = -1;
    *num_unique_cp = 1;

    /* "Allocate" a new cp entry in make_cp_list equivalent: */
    int new_slot = *num_unique_cp;  /* next free index */
    cptable_cp[new_slot]      = me_cp;
    cptable_risk[new_slot]    = 0.0;
    cptable_forward[new_slot] = cptable_forward[cptemp_idx];
    cptable_back[new_slot]    = cptemp_idx;
    if (cptable_forward[cptemp_idx] != -1)
        cptable_back[cptable_forward[cptemp_idx]] = new_slot;
    cptable_forward[cptemp_idx] = new_slot;
    (*num_unique_cp)++;
}
```

Corresponding R-side call:

```r
max_cp <- as.integer(max_expected_cp_entries)   # upper bound; e.g. n splits + 1

result <- .C("rpart_c",
    cptable_cp      = double(max_cp),
    cptable_risk    = double(max_cp),
    cptable_xrisk   = double(max_cp),
    cptable_xstd    = double(max_cp),
    cptable_nsplit  = integer(max_cp),
    cptable_forward = integer(max_cp),
    cptable_back    = integer(max_cp),
    num_unique_cp   = integer(1L),
    # ...
)
num_unique_cp <- result$num_unique_cp
cptable_df <- data.frame(
    cp     = result$cptable_cp[seq_len(num_unique_cp)],
    risk   = result$cptable_risk[seq_len(num_unique_cp)],
    nsplit = result$cptable_nsplit[seq_len(num_unique_cp)]
)
```

- **Explanation:**
  - `ALLOC(1, sizeof(cpTable))` and `ALLOC(1, nodesize)` are removed. There is no `.C`-compatible equivalent for returning or passing opaque structs with internal pointers.
  - For a fixed-size struct used only within one C function call (e.g., the head `cpTable` node), C stack allocation (`cpTable node; memset(...)`) is the simplest replacement — no argument change is needed and no memory management occurs.
  - For dynamically growing linked structures (the full `cpTable` list, `pNode` trees), each field becomes a pre-allocated flat array argument. An integer index replaces each pointer; the sentinel value `-1` replaces `NULL`. The `num_unique_cp` scalar output tells R how many array slots were actually populated.
  - Variable-size structs (`nodesize = sizeof(Node) + extra`) are handled by allocating the maximum possible size on the R side: `integer(max_node_count * max_node_fields)` or individual parallel arrays, as described in the `R_Free.md` guide.
  - After the `.C` call, R reads only the first `num_unique_cp` entries from each `cptable_*` array, discarding unused pre-allocated tail slots.
