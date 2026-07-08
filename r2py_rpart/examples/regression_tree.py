"""Python translation of regression_tree.R using r2py_rpart."""
import contextlib
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from r2py_rpart import rpart, printcp, plotcp, prune, print_rpart, plot_rpart, text_rpart

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ########################################################################
    #	Read in files
    col_name = ["Inc", "Sex", "Mar", "Age", "Edu", "Occ", "Res", "Dua", "Per",
                "Chi", "Hou", "Hom", "Eth", "Lan"]
    data = pd.read_csv(os.path.join(HERE, "income.data"), sep=",", header=None,
                        names=col_name, na_values="NA")

    for col in ("Sex", "Mar", "Occ", "Dua", "Hou", "Hom", "Eth", "Lan"):
        # R's as.factor() on a numeric column labels levels via as.character(),
        # e.g. "1"/"2"/"3" (not "1.0"/"2.0"); replicate that before making it a
        # pandas category so downstream formatting (labels_rpart etc.) matches.
        data[col] = data[col].apply(lambda v: str(int(v)) if pd.notna(v) else v).astype("category")

    ########################################################################
    #	Train the tree, plot the CV error
    np.random.seed(20)  # This seed is for CV, not tree itself
    # method="anova" means a regression tree
    tree_full = rpart("Inc ~ .", data=data, method="anova", control={"cp": .0005})
    printcp(tree_full)

    fig, ax = plt.subplots(figsize=(7, 14))
    plotcp(tree_full, ax=ax)
    fig.savefig(os.path.join(HERE, "regression_tree_cptable_Python.pdf"))
    plt.close(fig)

    ########################################################################
    # find the cp value that minimizes the cv error
    cptable = tree_full["cptable"]
    xerror = cptable["xerror"].to_numpy()
    xstd = cptable["xstd"].to_numpy()

    ind = int(np.argmin(xerror))
    print(cptable.iloc[ind])  # This one contains 45 splits
    cp_best_cv = cptable["CP"].iloc[ind]

    # if 1-se rule is used
    ind = int(np.argmin(xerror))
    ind_1se = int(np.argmax(xerror <= xerror[ind] + xstd[ind]))
    print(cptable.iloc[ind_1se])  # This one contains 20 splits
    cp_best_1se = cptable["CP"].iloc[ind_1se]

    ########################################################################
    #	prune the tree using the 1se rule
    tree_pruned = prune(tree_full, cp=cp_best_1se)
    print_rpart(tree_pruned)

    fig, ax = plt.subplots(figsize=(12, 8))
    plot_rpart(tree_pruned, ax=ax, main="Pruned Regression Tree")
    text_rpart(tree_pruned, ax=ax)
    fig.savefig(os.path.join(HERE, "regression_tree_pruned_Python.pdf"))
    plt.close(fig)

    ########################################################################
    # a bootstrap sample: showing how sensitive the tree structure is
    np.random.seed(10)
    data = data.iloc[np.random.choice(len(data), len(data), replace=True)]

    tree_full = rpart("Inc ~ .", data=data, method="anova", control={"cp": .0005})
    tree_pruned = prune(tree_full, cp=cp_best_1se)

    fig, ax = plt.subplots(figsize=(12, 8))
    plot_rpart(tree_pruned, ax=ax, main="Pruned Regression Tree")
    text_rpart(tree_pruned, ax=ax)
    fig.savefig(os.path.join(HERE, "regression_tree_bootstraped_Python.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    output_path = os.path.join(HERE, "regression_tree_output_Python.txt")
    with open(output_path, "w") as output_file, contextlib.redirect_stdout(output_file):
        main()
