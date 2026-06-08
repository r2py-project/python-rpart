#!/bin/bash
#$ -pe smp 1
#$ -q long
# Reinstall the rpart package from this directory into the conda env r-to-python.
set -euo pipefail
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="r-to-python"
CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
R CMD INSTALL --preclean "${PKG_DIR}"