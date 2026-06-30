from __future__ import annotations

from typing import Any

from .prune_rpart import prune_rpart


def prune(tree: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    # UseMethod('prune') dispatches to prune_rpart for rpart objects.
    return prune_rpart(tree, **kwargs)
