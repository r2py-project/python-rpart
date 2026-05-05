#!/usr/bin/env python3
"""
Dependency graph for the rpart R package.

Three-level layout
  Level 1 (top)    – R source files  (one node per .json file)
  Level 2 (middle) – User-defined functions  (keys inside each JSON)
  Level 3 (bottom) – Language (base-R) and external (C/Fortran) dependencies

Internal dependencies (function → function) are drawn as cross-edges at level 2.

Outputs
  dependency_graph.png  – raster image (150 dpi)
  dependency_graph.pdf  – vector image
  dependency_graph.html – interactive graph (requires pyvis; skipped if missing)
"""

import json
import sys
from pathlib import Path

import numpy as np
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── paths ─────────────────────────────────────────────────────────────────────
HERE     = Path(__file__).parent
JSON_DIR = HERE / "R"
OUT_BASE = HERE / "dependency_graph"   # suffix added per format

# ── visual constants ──────────────────────────────────────────────────────────
LAYER_Y = {0: 2.0, 1: 1.0, 2: 0.0}   # y-coordinate per layer

NODE_COLOR = {
    "file":     "#4472C4",   # blue
    "function": "#70AD47",   # green
    "language": "#FFD966",   # amber
    "external": "#E74C3C",   # red
}

NODE_ALPHA = {
    "file": 0.95, "function": 0.90, "language": 0.65, "external": 0.95,
}

NODE_SIZE = {
    "file": 1400, "function": 550, "language": 90, "external": 700,
}

EDGE_STYLE = {
    "defines":      dict(color="#2C5FA8", alpha=0.55, width=1.2),
    "internal_dep": dict(color="#2E7D32", alpha=0.85, width=1.8),
    "language_dep": dict(color="#BDBDBD", alpha=0.20, width=0.35),
    "external_dep": dict(color="#C0392B", alpha=0.90, width=2.0),
}

LAYER_LABEL = {0: "Level 1 – R Source Files",
               1: "Level 2 – Functions",
               2: "Level 3 – Dependencies"}


# ── data loading ──────────────────────────────────────────────────────────────
def load_data() -> dict:
    """Return {json_filename: {func_name: {lang, internal, external}}} for every JSON."""
    result = {}
    for path in sorted(JSON_DIR.glob("*.json")):
        with open(path) as f:
            result[path.name] = json.load(f)
    return result


# ── graph construction ────────────────────────────────────────────────────────
def build_graph(data: dict) -> nx.DiGraph:
    G = nx.DiGraph()

    for json_name, functions in data.items():
        r_file = json_name.replace(".json", ".R")
        G.add_node(r_file, node_type="file", label=r_file)

        for func_name, deps in functions.items():
            # Guarantee correct type even if the node was pre-created as a
            # forward reference by an internal_dep edge
            if func_name not in G.nodes:
                G.add_node(func_name, node_type="function", label=func_name)
            else:
                G.nodes[func_name]["node_type"] = "function"
                G.nodes[func_name].setdefault("label", func_name)

            G.add_edge(r_file, func_name, edge_type="defines")

            for dep in deps.get("language_dependencies", []):
                key = f"__lang__{dep}"
                if key not in G.nodes:
                    G.add_node(key, node_type="language", label=dep)
                G.add_edge(func_name, key, edge_type="language_dep")

            for dep in deps.get("external_dependencies", []):
                key = f"__ext__{dep}"
                if key not in G.nodes:
                    G.add_node(key, node_type="external", label=dep)
                G.add_edge(func_name, key, edge_type="external_dep")

            for dep in deps.get("internal_dependencies", []):
                if dep not in G.nodes:
                    G.add_node(dep, node_type="function", label=dep)
                G.add_edge(func_name, dep, edge_type="internal_dep")

    return G


# ── layout ────────────────────────────────────────────────────────────────────
def assign_layers(G: nx.DiGraph):
    layer_map = {"file": 0, "function": 1, "language": 2, "external": 2}
    for node, attrs in G.nodes(data=True):
        G.nodes[node]["layer"] = layer_map.get(attrs.get("node_type", "language"), 2)


def compute_positions(G: nx.DiGraph) -> dict:
    """
    Arrange nodes in three horizontal bands.

    Files   – sorted alphabetically.
    Functions – grouped by their defining file to minimise edge crossings.
    Deps    – language nodes sorted alphabetically; external nodes appended at
              the right end so they are visually distinct.
    """
    layers: dict[int, list] = {0: [], 1: [], 2: []}
    for node, attrs in G.nodes(data=True):
        layers[attrs["layer"]].append(node)

    # Layer 0: alphabetical
    layers[0].sort()
    file_order = {f: i for i, f in enumerate(layers[0])}

    # Layer 1: group functions by the file that defines them
    def func_sort_key(fn):
        for pred in G.predecessors(fn):
            if G.nodes[pred].get("node_type") == "file":
                return (file_order.get(pred, 9999), fn)
        return (9999, fn)

    layers[1].sort(key=func_sort_key)

    # Layer 2: language nodes A-Z, then external nodes A-Z at the far right
    lang_nodes = sorted(
        (n for n in layers[2] if G.nodes[n]["node_type"] == "language"),
        key=lambda n: G.nodes[n].get("label", n).lower()
    )
    ext_nodes = sorted(
        (n for n in layers[2] if G.nodes[n]["node_type"] == "external"),
        key=lambda n: G.nodes[n].get("label", n).lower()
    )
    layers[2] = lang_nodes + ext_nodes

    pos = {}
    for layer_idx, nodes in layers.items():
        n = len(nodes)
        xs = np.linspace(0.0, 1.0, n) if n > 1 else np.array([0.5])
        y  = LAYER_Y[layer_idx]
        for node, x in zip(nodes, xs):
            pos[node] = np.array([x, y])

    return pos


# ── matplotlib drawing ────────────────────────────────────────────────────────
def draw_graph(G: nx.DiGraph, pos: dict):
    fig, ax = plt.subplots(figsize=(48, 24))
    fig.patch.set_facecolor("#F5F5F5")
    ax.set_facecolor("#F5F5F5")

    # Draw edges from least to most important so key edges render on top
    for etype in ("language_dep", "defines", "external_dep", "internal_dep"):
        edges = [(u, v) for u, v, d in G.edges(data=True)
                 if d.get("edge_type") == etype]
        if not edges:
            continue
        s = EDGE_STYLE[etype]
        use_arrows = etype in ("internal_dep", "external_dep")
        nx.draw_networkx_edges(
            G, pos,
            edgelist=edges,
            edge_color=s["color"],
            alpha=s["alpha"],
            width=s["width"],
            arrows=use_arrows,
            arrowsize=12,
            arrowstyle="-|>",
            min_source_margin=6,
            min_target_margin=6,
            ax=ax,
        )

    # Draw nodes, one type at a time for colour accuracy
    for ntype in ("language", "external", "function", "file"):
        nodelist = [n for n, d in G.nodes(data=True)
                    if d.get("node_type") == ntype]
        if not nodelist:
            continue
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=nodelist,
            node_color=NODE_COLOR[ntype],
            node_size=NODE_SIZE[ntype],
            alpha=NODE_ALPHA[ntype],
            ax=ax,
        )

    # Labels
    def draw_labels(ntype, fontsize, fontweight="normal", color="black"):
        subset = {n: G.nodes[n].get("label", n)
                  for n in G.nodes if G.nodes[n].get("node_type") == ntype}
        nx.draw_networkx_labels(
            G, pos, labels=subset,
            font_size=fontsize, font_weight=fontweight,
            font_color=color, ax=ax,
        )

    draw_labels("file",     fontsize=6.0, fontweight="bold")
    draw_labels("function", fontsize=5.0)
    draw_labels("language", fontsize=3.2)
    draw_labels("external", fontsize=5.5, fontweight="bold", color="#7B0000")

    # Layer band labels on the left margin
    x_margin = -0.03
    for layer_idx, text in LAYER_LABEL.items():
        y = LAYER_Y[layer_idx]
        ax.text(x_margin, y, text,
                ha="right", va="center",
                fontsize=9, fontstyle="italic", color="#444444",
                transform=ax.transData)

    # Horizontal dividers between layers
    for y_div in [0.5, 1.5]:
        ax.axhline(y=y_div, color="#CCCCCC", linewidth=0.8, linestyle="--", zorder=0)

    # Legend
    handles = [
        mpatches.Patch(color=NODE_COLOR["file"],     label="R source file"),
        mpatches.Patch(color=NODE_COLOR["function"], label="User-defined function"),
        mpatches.Patch(color=NODE_COLOR["language"], label="Language dependency (base R / CRAN)"),
        mpatches.Patch(color=NODE_COLOR["external"], label="External dependency (C / Fortran)"),
        plt.Line2D([0], [0], color=EDGE_STYLE["defines"]["color"],
                   lw=2, label="file  →  function  (defines)"),
        plt.Line2D([0], [0], color=EDGE_STYLE["internal_dep"]["color"],
                   lw=2, label="function  →  function  (internal dep)"),
        plt.Line2D([0], [0], color=EDGE_STYLE["language_dep"]["color"],
                   lw=1.5, label="function  →  language dep"),
        plt.Line2D([0], [0], color=EDGE_STYLE["external_dep"]["color"],
                   lw=2, label="function  →  external dep (C call)"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=9,
              framealpha=0.92, edgecolor="#AAAAAA")

    # Stats box
    n_files = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "file")
    n_funcs = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "function")
    n_lang  = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "language")
    n_ext   = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "external")
    stats = (f"Nodes: {G.number_of_nodes()}  |  Edges: {G.number_of_edges()}\n"
             f"Files: {n_files}  ·  Functions: {n_funcs}  "
             f"·  Lang deps: {n_lang}  ·  Ext deps: {n_ext}")
    ax.text(0.5, -0.04, stats, transform=ax.transAxes,
            ha="center", va="top", fontsize=8, color="#555555")

    ax.set_title("rpart R Package — Structural Dependency Graph",
                 fontsize=17, fontweight="bold", pad=16)
    ax.axis("off")

    # Expand x-axis so left-margin labels are not clipped
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(xmin - 0.12, xmax + 0.02)

    plt.tight_layout()
    return fig


# ── optional pyvis interactive export ────────────────────────────────────────
def export_pyvis(G: nx.DiGraph):
    try:
        from pyvis.network import Network
    except ImportError:
        print("pyvis not installed — skipping HTML export.")
        return

    nt = Network(height="900px", width="100%", directed=True,
                 bgcolor="#F5F5F5", font_color="#333333")
    nt.barnes_hut(gravity=-8000, central_gravity=0.3,
                  spring_length=120, spring_strength=0.05)

    color_map = {
        "file": NODE_COLOR["file"],
        "function": NODE_COLOR["function"],
        "language": NODE_COLOR["language"],
        "external": NODE_COLOR["external"],
    }
    size_map = {"file": 28, "function": 18, "language": 8, "external": 22}

    for node, attrs in G.nodes(data=True):
        ntype = attrs.get("node_type", "language")
        nt.add_node(
            node,
            label=attrs.get("label", node),
            color=color_map.get(ntype, "#CCCCCC"),
            size=size_map.get(ntype, 8),
            title=f"type: {ntype}\nid: {node}",
        )

    edge_color_map = {
        "defines":      EDGE_STYLE["defines"]["color"],
        "internal_dep": EDGE_STYLE["internal_dep"]["color"],
        "language_dep": EDGE_STYLE["language_dep"]["color"],
        "external_dep": EDGE_STYLE["external_dep"]["color"],
    }

    for u, v, attrs in G.edges(data=True):
        etype = attrs.get("edge_type", "language_dep")
        nt.add_edge(u, v, color=edge_color_map.get(etype, "#AAAAAA"),
                    width=2 if etype in ("internal_dep", "external_dep") else 0.8,
                    arrows="to" if etype in ("internal_dep", "external_dep") else "")

    html_path = str(OUT_BASE.with_suffix(".html"))
    nt.save_graph(html_path)
    print(f"Saved: {html_path}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("Loading JSON files …")
    data = load_data()
    print(f"  {len(data)} files loaded")

    print("Building graph …")
    G = build_graph(data)
    assign_layers(G)
    pos = compute_positions(G)

    n_files = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "file")
    n_funcs = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "function")
    n_lang  = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "language")
    n_ext   = sum(1 for _, d in G.nodes(data=True) if d["node_type"] == "external")
    print(f"  Nodes  : {G.number_of_nodes()}  "
          f"(files={n_files}, functions={n_funcs}, "
          f"language={n_lang}, external={n_ext})")
    print(f"  Edges  : {G.number_of_edges()}")

    print("Drawing graph …")
    fig = draw_graph(G, pos)

    png_path = str(OUT_BASE.with_suffix(".png"))
    pdf_path = str(OUT_BASE.with_suffix(".pdf"))
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    fig.savefig(pdf_path,           bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {png_path}")
    print(f"Saved: {pdf_path}")

    export_pyvis(G)
    print("Done.")


if __name__ == "__main__":
    main()
