#######################################################################
#	Redirect all console output to a file
sink("classification_tree_output_R.txt")

load("iris_jun.RData")

######### decision tree
#install.packages("rpart")
library("rpart")
set.seed(10)	# This seed is for CV, not tree itself

# usually, we need to set cp to be really small to start so that the minimal cv error is achieved.
# This method="class" means a classification tree.
tree.full <- rpart(tp ~ ., data=iris, method="class", control=rpart.control(cp=0.0001, minsplit=5))

print(tree.full)

pdf("classification_tree_iris_tree_R.pdf", width=8, height=8)
plot(tree.full)
text(tree.full)
dev.off()

# explain the "root node error", "rel error", and "xerror"
printcp(tree.full) # There is no need to prune this tree

#######################################################################
#	Just in case if we decide to prune it, here is how we do it.
tree.pruned <- prune(tree.full, cp = 0.02)
print(tree.pruned)
pdf("classification_tree_iris_pruned_R.pdf", width=8, height=8)
plot(tree.pruned, main = "Pruned decision Tree")
text(tree.pruned)
dev.off()

#######################################################################
#	Stop redirecting console output
sink()
