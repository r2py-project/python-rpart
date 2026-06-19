#!/bin/bash
#$ -pe smp 1
#$ -q long
module load gcc
source /software/c/conda/26.3.2/etc/profile.d/conda.sh
conda activate r-to-python
pip install --no-build-isolation .