# Conversion Guide: `R_Free`

## 1. Overview of `R_Free` in R API

`R_Free` is a macro defined in `R_ext/RS.h` that performs a safe, checked deallocation of memory previously allocated by R's S-like memory API (e.g., `R_Calloc`, `R_Realloc`, or the lower-level `R_chk_calloc`). Its expansion is:

```c
#define R_Free(p)  (R_chk_free( (void *)(p) ), (p) = NULL)
```

It calls the internal `R_chk_free` function (which wraps `free` with an error-checking guard) and then sets the pointer to `NULL` immediately after freeing, preventing dangling-pointer reads. Unlike the standard C `free`, `R_Free` guarantees a null-assignment side-effect, so every call both deallocates memory and clears the pointer variable. This macro belongs to R's `.Call`/`.External`-era C API and is not available or meaningful in the pure `.C`/`.Fortran` paradigm where memory is managed entirely by the calling R code.

---

## 2. Contextual Usage Analysis

### Source Files and Line Numbers

| File | Line | Variable Freed | Allocated Type | Allocation Call |
|---|---|---|---|---|
| `free_tree.c` | 13 | `spl` | `pSplit` (`Split *`) | `CALLOC(1, splitsize)` in `insert_split.c` |
| `free_tree.c` | 29 | `node` | `pNode` (`Node *`) | `CALLOC(1, nodesize)` in `rpart.c` / `xval.c` |
| `insert_split.c` | 36 | `s3` | `pSplit` (`Split *`) | `CALLOC(1, splitsize)` on line 25 |
| `insert_split.c` | 63 | `s4` | `pSplit` (`Split *`) | `CALLOC(1, splitsize)` on line 65 (reallocated) |
| `xval.c` | 178 | `savew` | `int *` | `CALLOC(rp.n, sizeof(int))` on line 61 |
| `xval.c` | 179 | `xtemp` | `double *` | `CALLOC(3 * rp.num_unique_cp, sizeof(double))` on line 58 |

### Memory Management Macros in Context

The rpart package uses the alias `CALLOC` defined in `rpart.h`:

```c
#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)
```

This is `R_chk_calloc`, the same underlying function called by `R_Calloc`. Memory allocated via `CALLOC` / `R_Calloc` must be freed with `R_Free`. Standard `malloc`/`calloc`-allocated memory must be freed with standard `free`.

### Distinct Usage Patterns

**Pattern A — Recursive linked-list node deallocation (`free_tree.c`).**  
`free_split` and `free_tree` traverse dynamically-built linked structures (`Split` chains and `Node` trees) and free each heap node individually with `R_Free`. The structures are built incrementally during the fitting loop; their lifetime spans multiple `.Call` invocations within a session.

**Pattern B — Realloc-style replace-and-free within a list (`insert_split.c`).**  
`insert_split` manages a bounded-length sorted list of splits. When the list is full and a new, better split arrives, the tail element is freed with `R_Free` and a fresh `CALLOC` block replaces it. The free and re-allocate happen inside a single function call.

**Pattern C — Cleanup of function-scoped temporary arrays (`xval.c`).**  
`xtemp` and `savew` are plain flat arrays allocated at the top of `xval()` and freed at the bottom. They are not part of any recursive structure; they are simple scratch buffers with a lifetime equal to one invocation of `xval`.

---

## 3. Pure C/C++ Conversion Strategy

### API Paradigm Shift

Under the `.C` API, R passes pre-allocated vectors from R-side memory into C. The C code receives raw pointers (`int *`, `double *`, etc.) and must never call `malloc`, `calloc`, or `free` on those pointers — R owns them and frees them automatically after the `.C` call returns.

Consequently:

1. **Flat temporary arrays** (Pattern C): allocations like `CALLOC(rp.n, sizeof(int))` that are freed within the same function must be replaced by standard C `malloc`/`calloc` + `free`, or the arrays must be pre-allocated by R and passed in as additional `.C` arguments. The pointer-nulling side-effect of `R_Free` is replaced by an explicit `p = NULL` assignment after `free(p)` if that defense is still desired.

2. **Dynamic linked structures** (Patterns A and B): `Split` and `Node` chains are heap-allocated inside C during the algorithm and have no direct analog in the `.C`/`.Fortran` flat-array model. The correct strategy is to replace these pointer-linked structures with pre-allocated flat arrays of sufficient size (sized by worst-case tree depth / split count), passed in from R. Each logical "node" or "split" becomes an index into those flat arrays rather than a heap pointer. Freeing the structure then requires no `free` call at all — R reclaims the pre-allocated array memory.

3. **Pointer nulling**: `R_Free(p)` sets `p = NULL` after the free. With standard `free`, this must be done explicitly: `free(p); p = NULL;` if the pattern relied on the null-check (e.g., `if (spl)` in `free_split`). When structures are replaced by flat arrays, the null-pointer sentinel is replaced by a sentinel index value (e.g., `-1` or `0`).

### Type Mapping

| R `.Call` API | `.C`-compatible equivalent |
|---|---|
| `R_Free(p)` on a `pSplit` or `pNode` pointer | `free(p); p = NULL;` when using heap; eliminated when structures become flat arrays |
| `R_Free(p)` on a flat `int *` or `double *` scratch buffer | `free(p); p = NULL;` (heap), or pass buffer from R and omit free entirely |
| `CALLOC(n, size)` counterpart | `calloc(n, size)` (heap) or pre-allocated R vector argument (`.C`) |

---

## 4. Step-by-Step Conversion Examples

### Pattern A: Recursive Linked-List Node Deallocation

- **Locations:** `free_tree.c` lines 13, 29
- **Original Context (.Call):**

```c
/* free_tree.c */
static void
free_split(pSplit spl)
{
    if (spl) {
        free_split(spl->nextsplit);  /* recurse down the chain */
        R_Free(spl);                 /* R_chk_free + sets spl = NULL */
    }
}

void
free_tree(pNode node, int freenode)
{
    if (node->rightson)  free_tree(node->rightson, 1);
    if (node->leftson)   free_tree(node->leftson, 1);
    free_split(node->surrogate);
    free_split(node->primary);
    if (freenode == 1)
        R_Free(node);
    else {
        node->primary   = (pSplit) NULL;
        node->surrogate = (pSplit) NULL;
        node->rightson  = (pNode) NULL;
        node->leftson   = (pNode) NULL;
    }
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Replacement strategy: represent the tree as flat arrays indexed by
 * node/split index rather than heap pointers.  The flat arrays are
 * pre-allocated in R and passed in as .C arguments.
 *
 * Sentinel value: index -1 (or 0 if 1-based) replaces NULL pointers.
 * "Freeing" a node/split now simply marks its slot as unused.
 */

#define NO_CHILD  -1  /* sentinel replacing NULL pNode / pSplit */

/* Flat-array node layout (example) */
/* int node_rightson[MAX_NODES];   -- passed from R as int * */
/* int node_leftson[MAX_NODES];    -- passed from R as int * */
/* int node_primary[MAX_NODES];    -- index into split arrays */
/* int node_surrogate[MAX_NODES];  -- index into split arrays */
/* int split_nextsplit[MAX_SPLITS]; */

static void
free_split_flat(int split_idx,
                int *split_nextsplit,
                int *split_active)   /* 1=in use, 0=freed */
{
    while (split_idx != NO_CHILD) {
        int next = split_nextsplit[split_idx];
        split_active[split_idx] = 0;  /* mark slot as free */
        split_nextsplit[split_idx] = NO_CHILD;
        split_idx = next;
    }
}

void
free_tree_flat(int node_idx, int freenode,
               int *node_rightson, int *node_leftson,
               int *node_primary,  int *node_surrogate,
               int *node_active,
               int *split_nextsplit, int *split_active)
{
    if (node_idx == NO_CHILD) return;

    free_tree_flat(node_rightson[node_idx], 1,
                   node_rightson, node_leftson,
                   node_primary, node_surrogate,
                   node_active, split_nextsplit, split_active);
    free_tree_flat(node_leftson[node_idx], 1,
                   node_rightson, node_leftson,
                   node_primary, node_surrogate,
                   node_active, split_nextsplit, split_active);

    free_split_flat(node_surrogate[node_idx], split_nextsplit, split_active);
    free_split_flat(node_primary[node_idx],   split_nextsplit, split_active);

    if (freenode == 1) {
        node_active[node_idx] = 0;    /* mark slot as free; no free() call */
    } else {
        node_primary[node_idx]   = NO_CHILD;
        node_surrogate[node_idx] = NO_CHILD;
        node_rightson[node_idx]  = NO_CHILD;
        node_leftson[node_idx]   = NO_CHILD;
    }
}
```

- **Explanation:** `pSplit` and `pNode` heap pointers are replaced by integer indices into flat arrays pre-allocated by R. The `R_Free(spl)` and `R_Free(node)` calls become slot-marking operations (`active[idx] = 0`) with no actual memory deallocation in C. The NULL pointer sentinel becomes the integer constant `NO_CHILD` (-1). No `free()` or `R_Free()` appears anywhere in the converted code. The calling R side pre-allocates integer vectors of `MAX_NODES` and `MAX_SPLITS` length and passes them to `.C`.

---

### Pattern B: Replace-and-Free in a Bounded Sorted List

- **Locations:** `insert_split.c` lines 36, 63
- **Original Context (.Call):**

```c
/* insert_split.c -- simplified relevant branches */

/* Branch: max == 1, categorical split replacing current head */
if (ncat > 1) {
    R_Free(s3);                         /* free old head */
    s3 = (pSplit) CALLOC(1, splitsize); /* allocate fresh block */
    s3->nextsplit = NULL;
    *listhead = s3;
}

/* Branch: list full, tail element replaced by better split */
if (ncat > 1) {
    R_Free(s4);                         /* free tail */
    s4 = (pSplit) CALLOC(1, splitsize); /* allocate fresh block */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Replacement strategy: maintain a fixed-size pool of split slots
 * (flat arrays).  "Freeing" a slot means marking it available for
 * reuse; "allocating" means finding the next free slot index.
 *
 * split_pool_active[MAX_SPLITS]: 1=occupied, 0=free
 * All other split fields are stored in parallel flat arrays.
 */

static int alloc_split_slot(int *split_pool_active, int max_splits)
{
    for (int i = 0; i < max_splits; i++) {
        if (!split_pool_active[i]) {
            split_pool_active[i] = 1;
            return i;
        }
    }
    return -1;  /* pool exhausted — caller must handle error */
}

/* Branch: max == 1, categorical split replacing current head */
if (ncat > 1) {
    /* "R_Free(s3)" equivalent: mark slot as available */
    split_pool_active[s3_idx] = 0;
    split_nextsplit[s3_idx]   = NO_CHILD;

    /* "CALLOC(1, splitsize)" equivalent: claim a free slot */
    s3_idx = alloc_split_slot(split_pool_active, max_splits);
    /* zero-initialise the slot fields manually */
    split_improve[s3_idx]     = 0.0;
    split_nextsplit[s3_idx]   = NO_CHILD;
    *listhead_idx             = s3_idx;
}

/* Branch: list full, tail element replaced by better split */
if (ncat > 1) {
    split_pool_active[s4_idx] = 0;    /* free tail slot */
    split_nextsplit[s4_idx]   = NO_CHILD;
    s4_idx = alloc_split_slot(split_pool_active, max_splits);
    split_improve[s4_idx]     = 0.0;
    split_nextsplit[s4_idx]   = NO_CHILD;
}
```

- **Explanation:** The heap allocation pair (`R_Free` + `CALLOC`) is replaced by a pool-slot recycling pattern. The `split_pool_active` array (an `int *` pre-allocated by R) acts as a free-list bitmap. Marking a slot `0` corresponds to `R_Free`; claiming the next `0` slot corresponds to `CALLOC`. All split data fields are stored in separate flat arrays (also pre-allocated by R), so the variable-size `splitsize` concern disappears. The `ncat > 1` guard is preserved because for continuous splits the existing fixed-size slot is reused in place without reallocation.

---

### Pattern C: Function-Scoped Flat Temporary Array Cleanup

- **Locations:** `xval.c` lines 178, 179
- **Original Context (.Call):**

```c
/* xval.c */
/* Allocation at top of xval() */
xtemp = (double *) CALLOC(3 * rp.num_unique_cp, sizeof(double));
xpred = xtemp + rp.num_unique_cp;   /* pointer arithmetic into same block */
cp    = xpred + rp.num_unique_cp;
savew = (int *)    CALLOC(rp.n, sizeof(int));

/* ... algorithm body ... */

/* Cleanup at bottom of xval() */
for (i = 0; i < rp.n; i++)
    rp.which[i] = savew[i];
R_Free(savew);   /* R_chk_free(savew); savew = NULL; */
R_Free(xtemp);   /* R_chk_free(xtemp); xtemp = NULL; */
```

- **C/C++ Equivalent (.C) — Option 1: pass buffers from R:**

```c
/*
 * R pre-allocates the scratch buffers and passes them as .C arguments:
 *   xtemp_buf: double vector of length 3 * num_unique_cp
 *   savew_buf: integer vector of length n
 *
 * The C function signature gains two extra pointer parameters.
 * No allocation or deallocation occurs inside C at all.
 */
void
xval_c(int *n_xval, /* ... other args ... */
       double *xtemp_buf,   /* pre-allocated by R, length 3*num_unique_cp */
       int    *savew_buf,   /* pre-allocated by R, length n             */
       /* ... */)
{
    double *xtemp = xtemp_buf;
    double *xpred = xtemp_buf + num_unique_cp;
    double *cp    = xtemp_buf + 2 * num_unique_cp;
    int    *savew = savew_buf;

    /* ... algorithm body unchanged ... */

    for (int i = 0; i < n; i++)
        which[i] = savew[i];
    /* No R_Free / free() needed: R reclaims the memory after .C returns */
}
```

- **C/C++ Equivalent (.C) — Option 2: use standard heap (if lifetime must stay within C):**

```c
#include <stdlib.h>  /* for calloc, free */

void
xval_c(int *n_xval, /* ... */)
{
    double *xtemp = (double *) calloc(3 * num_unique_cp, sizeof(double));
    double *xpred = xtemp + num_unique_cp;
    double *cp    = xtemp + 2 * num_unique_cp;
    int    *savew = (int *) calloc(n, sizeof(int));

    if (!xtemp || !savew) {
        free(xtemp);
        free(savew);
        /* signal error to R */
        return;
    }

    /* ... algorithm body unchanged ... */

    for (int i = 0; i < n; i++)
        which[i] = savew[i];

    free(savew); savew = NULL;
    free(xtemp); xtemp = NULL;  /* explicit NULL mirrors R_Free semantics */
}
```

- **Explanation:** For flat temporary arrays, the conversion has two valid options. Option 1 (preferred for `.C` style) moves the allocation responsibility to R: the calling R script creates vectors of the required sizes (`vector("double", 3*num_unique_cp)`, `integer(n)`) and passes them as extra `.C` arguments. The C function uses those pointers directly without `calloc` or `free`. Option 2 keeps allocation inside C but replaces `CALLOC`/`R_Free` with standard `calloc`/`free`; the `p = NULL` nulling that `R_Free` provides automatically must be done explicitly. In both cases, `R_Free` is completely removed from the C code, and no R-specific memory-management headers are needed.
