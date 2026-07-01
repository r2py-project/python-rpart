#!/bin/bash
#$ -pe smp 1
#$ -q long
# conda create -n r-to-python python r-base -c conda-forge -y
module load gcc
conda activate r-to-python
conda install -c conda-forge meson-python numpy pandas scipy scikit-learn matplotlib r-kernsmooth -y
conda install -c conda-forge r-cardata -y
conda install -c conda-forge rpy2 -y
conda install -c conda-forge radian -y
conda install -c conda-forge r-rpart -y
conda install -c conda-forge r-survival -y
conda install -c conda-forge pyvis -y
R
install.packages("vscDebugger", repos = c("https://manuelhentschel.r-universe.dev", "https://cloud.r-project.org"))