from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import matplotlib.axes

from .plot_rpart import plot_rpart
from .text_rpart import text_rpart

_post_rpart_MISSING = object()



def post_rpart(tree: dict[str, Any], title_: Any = _post_rpart_MISSING, filename: str = 'tree.ps', digits: int | None = None, pretty: bool = True, use_n: bool = True, horizontal: bool = True, **kwargs: Any) -> None:
    if digits is None:
        import builtins
        digits = max(getattr(builtins, '_rpart_digits', 7) - 2, 1)
    fig, ax = plt.subplots()
    fig.subplots_adjust(left=0.1, right=0.9, top=0.85, bottom=0.1)
    plot_rpart(tree, uniform=True, branch=0.2, compress=True, margin=0.1, ax=ax)
    text_rpart(tree, all=True, use_n=use_n, fancy=True, digits=digits, pretty=pretty, ax=ax)
    if title_ is _post_rpart_MISSING:
        # tree['terms'] is a plain dict (the package-wide convention, see
        # rpart.py), not an object with R-attribute-style .attrs.
        temp = tree['terms'].get('variables', [])[1]
        ax.set_title(f'Endpoint = {temp}', fontsize=8)
    elif len(title_) > 0:
        ax.set_title(title_, fontsize=8)
    if filename != '':
        orientation = 'landscape' if horizontal else 'portrait'
        fig.savefig(filename, format='ps', orientation=orientation)
        plt.close(fig)
    else:
        plt.close(fig)
