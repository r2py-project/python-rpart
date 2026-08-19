#!/bin/bash
#$ -pe smp 1
#$ -q long
module load git
export PATH=~/bin:$PATH
# git remote add python-rpart https://github.com/r2py-project/python-rpart.git
git push origin main
# git remote add r2py_rpart https://github.com/r2py-project/r2py_rpart.git
git subtree push --prefix=r2py_rpart r2py_rpart main