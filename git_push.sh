#!/bin/bash
#$ -pe smp 1
#$ -q long
module load git
export PATH=~/bin:$PATH
# git remove add python-rpart https://github.com/caiyufei8/python-rpart.git
git push origin main
# git remote add r2py_rpart https://github.com/caiyufei8/r2py_rpart.git
git subtree push --prefix=r2py_rpart r2py_rpart main