#!/bin/bash
#$ -pe smp 1
#$ -q long
module load git
export PATH=~/bin:$PATH
# git remove add python-rpart https://github.com/caiyufei8/python-rpart.git
git pull origin main
# git remote add r2py_rpart https://github.com/caiyufei8/r2py_rpart.git
git subtree pull --squash --prefix=r2py_rpart r2py_rpart main
git push origin main