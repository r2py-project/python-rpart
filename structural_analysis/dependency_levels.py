#!/usr/bin/env python3
"""
Topological layering of rpart R functions by internal dependencies only.

Algorithm
---------
Build a directed call graph:  edge A → B  means A lists B in its
internal_dependencies (i.e. A calls B).  Then assign levels with BFS:

  Level 0        – entry points: functions that no other internal function calls
  Level N        – max(level of all callers) + 1
  "(leaf)" tag   – functions that call no other internal function
                   (their internal_dependencies list is empty after removing
                    self-recursion and unknown references)

Output CSV
----------
  r_file   | function | level | parents | children
  -------- | -------- | ----- | ------- | --------
  rpart.R  | rpart    | 0     |         | rpart.matrix; rpartcallback; …
  …

  • level column contains e.g. "0", "1 (leaf)", "2", …
  • parents / children are "; "-separated lists of function names
  • rows are sorted by level ASC, then r_file, then function name
"""

import csv
import json
from collections import deque
from pathlib import Path

HERE     = Path(__file__).parent
JSON_DIR = HERE / "R"
OUT_CSV  = HERE / "dependency_levels.csv"


# ── data loading ──────────────────────────────────────────────────────────────

def load_data() -> dict:
    """
    Return {func_name: {"r_file": str, "int_deps": [str]}} for every function
    found in the JSON files.  Self-recursive calls are dropped immediately.
    """
    func_info: dict[str, dict] = {}
    for path in sorted(JSON_DIR.glob("*.json")):
        r_file = path.stem + ".R"           # "rpartco.json" → "rpartco.R"
        with open(path, encoding="utf-8") as f:
            functions: dict = json.load(f)
        for func_name, deps in functions.items():
            int_deps = [
                d for d in deps.get("internal_dependencies", [])
                if d != func_name           # drop self-loops (recursion)
            ]
            func_info[func_name] = {"r_file": r_file, "int_deps": int_deps}
    return func_info


# ── graph construction ────────────────────────────────────────────────────────

def build_graph(func_info: dict) -> tuple[dict, dict]:
    """
    Build two adjacency maps restricted to functions actually present in
    func_info (i.e. truly internal to the package).

    children[f]  – functions that f calls
    parents[f]   – functions that call f
    """
    all_funcs = set(func_info)
    children: dict[str, list] = {f: [] for f in all_funcs}
    parents:  dict[str, list] = {f: [] for f in all_funcs}

    for func, info in func_info.items():
        for dep in info["int_deps"]:
            if dep in all_funcs:
                children[func].append(dep)
                parents[dep].append(func)

    return children, parents


# ── level computation ─────────────────────────────────────────────────────────

def compute_levels(all_funcs: set, children: dict, parents: dict) -> dict:
    """
    Kahn's BFS topological layering.

      level[f] = 0                          if f has no callers
      level[f] = max(level[caller]) + 1     otherwise

    The BFS guarantees correctness for DAGs.  Any functions remaining in a
    cycle after the main pass receive a best-effort level via a subsequent
    relaxation pass over their acyclic callers.
    """
    in_deg = {f: len(parents[f]) for f in all_funcs}
    level  = {f: 0               for f in all_funcs}

    # Seed queue with functions that have no callers (true entry points)
    queue = deque(f for f in all_funcs if in_deg[f] == 0)

    while queue:
        func = queue.popleft()
        for child in children[func]:
            proposed = level[func] + 1
            if proposed > level[child]:
                level[child] = proposed
            in_deg[child] -= 1
            if in_deg[child] == 0:
                queue.append(child)

    # Fallback relaxation for functions caught in mutual-recursion cycles
    cyclic = {f for f in all_funcs if in_deg[f] > 0}
    if cyclic:
        for _ in range(len(cyclic)):
            changed = False
            for f in cyclic:
                # Use only acyclic (already-settled) callers as anchors
                settled_parents = [p for p in parents[f] if p not in cyclic]
                if settled_parents:
                    proposed = max(level[p] for p in settled_parents) + 1
                    if proposed > level[f]:
                        level[f] = proposed
                        changed = True
            if not changed:
                break

    return level


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading JSON structural-analysis files …")
    func_info = load_data()
    print(f"  {len(func_info)} functions loaded from {JSON_DIR.name}/")

    children, parents = build_graph(func_info)

    print("Computing topological levels …")
    levels = compute_levels(set(func_info), children, parents)

    # Build output rows
    rows = []
    for func, info in func_info.items():
        lev     = levels[func]
        kids    = sorted(children[func])
        pars    = sorted(parents[func])
        is_leaf = (len(kids) == 0)

        rows.append({
            "r_file":    info["r_file"],
            "function":  func,
            "_level":    lev,                       # numeric, for sorting
            "level":     f"{lev} (leaf)" if is_leaf else str(lev),
            "parents":   "; ".join(pars),
            "children":  "; ".join(kids),
        })

    # Sort: level ASC → r_file → function name
    rows.sort(key=lambda r: (r["_level"], r["r_file"], r["function"]))

    # Write CSV
    print(f"Writing {OUT_CSV.name} …")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["r_file", "function", "level", "parents", "children"])
        for r in rows:
            writer.writerow([
                r["r_file"],
                r["function"],
                r["level"],
                r["parents"],
                r["children"],
            ])

    # Summary to stdout
    from collections import Counter
    lev_counts = Counter(r["_level"] for r in rows)
    leaf_count = sum(1 for r in rows if "(leaf)" in r["level"])
    cyclic_count = sum(
        1 for f in func_info
        if any(f in children[c] and c in children[f] for c in children[f])
    )

    print("\nLevel distribution:")
    for lev in sorted(lev_counts):
        marker = "← entry points" if lev == 0 else ""
        print(f"  Level {lev:2d}: {lev_counts[lev]:3d} function(s)  {marker}")

    print(f"\nLeaf functions (no internal calls): {leaf_count}")
    if cyclic_count:
        print(f"Mutually-recursive pairs detected : {cyclic_count}")
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
