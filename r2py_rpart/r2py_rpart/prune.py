from __future__ import annotations

from typing import Any




def prune(tree: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    # UseMethod('prune') dispatches to prune_rpart for rpart objects.
    return prune_rpart(tree, **kwargs)
