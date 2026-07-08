"""Python translation of classification_tree.R using r2py_rpart."""
import contextlib
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from r2py_rpart import rpart, printcp, prune, print_rpart, plot_rpart, text_rpart

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    # iris_jun.RData holds a data.frame named `iris` (cols sl, sw, pl, pw, tp);
    # iris_jun.csv is a plain-text export of that same data.frame for pandas.
    iris = pd.read_csv(os.path.join(HERE, "iris_jun.csv"))
    iris["tp"] = iris["tp"].astype("category")

    ######### decision tree
    np.random.seed(10)  # This seed is for CV, not tree itself

    # usually, we need to set cp to be really small to start so that the minimal cv error is achieved.
    # This method="class" means a classification tree.
    tree_full = rpart("tp ~ .", data=iris, method="class", control={"cp": 0.0001, "minsplit": 5})

    print_rpart(tree_full)

    fig, ax = plt.subplots(figsize=(8, 8))
    plot_rpart(tree_full, ax=ax)
    text_rpart(tree_full, ax=ax)
    fig.savefig(os.path.join(HERE, "classification_tree_iris_tree_Python.pdf"))
    plt.close(fig)

    # explain the "root node error", "rel error", and "xerror"
    printcp(tree_full)  # There is no need to prune this tree

    ########################################################################
    #	Just in case if we decide to prune it, here is how we do it.
    tree_pruned = prune(tree_full, cp=0.02)
    print_rpart(tree_pruned)

    fig, ax = plt.subplots(figsize=(8, 8))
    plot_rpart(tree_pruned, ax=ax, main="Pruned decision Tree")
    text_rpart(tree_pruned, ax=ax)
    fig.savefig(os.path.join(HERE, "classification_tree_iris_pruned_Python.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    output_path = os.path.join(HERE, "classification_tree_output_Python.txt")
    with open(output_path, "w") as output_file, contextlib.redirect_stdout(output_file):
        main()
