#######################################################################
#	Redirect all console output to a file
sink("regression_tree_output_R.txt")

#######################################################################
#	Read in files
col.name <- c("Inc", "Sex", "Mar", "Age", "Edu", "Occ", "Res", "Dua", "Per", "Chi", "Hou", "Hom", "Eth", "Lan")
data <- read.table("income.data", sep = ",", col.names = col.name)

data$Sex <- as.factor(data$Sex)
data$Mar <- as.factor(data$Mar)
data$Occ <- as.factor(data$Occ)
data$Dua <- as.factor(data$Dua)
data$Hou <- as.factor(data$Hou)
data$Hom <- as.factor(data$Hom)
data$Eth <- as.factor(data$Eth)
data$Lan <- as.factor(data$Lan)

#######################################################################
#	Train the tree, plot the CV error
library(rpart)
set.seed(20) # This seed is for CV, not tree itself
# This method="anova" means a regression tree
tree.full <- rpart(Inc ~., data = data, method = "anova", control = rpart.control(cp = .0005))
printcp(tree.full)

pdf("regression_tree_cptable_R.pdf", width=7, height=14)
plotcp(tree.full)
dev.off()

#######################################################################
# find the cp value that minimizes the cv error
ind <- which.min(tree.full$cptable[, "xerror"])[1]
tree.full$cptable[ind, ] # This one contains 45 splits
cp.best.cv <- tree.full$cptable[ind, "CP"]

# if 1-se rule is used
ind <- which.min(tree.full$cptable[, "xerror"])[1]
ind.1se <- which(tree.full$cptable[, "xerror"] <= tree.full$cptable[ind, "xerror"] + tree.full$cptable[ind, "xstd"])[1]
tree.full$cptable[ind.1se, ] # This one contains 20 splits
cp.best.1se <- tree.full$cptable[ind.1se, "CP"]

#######################################################################
#	prune the tree using the 1se rule
tree.pruned <- prune(tree.full, cp = cp.best.1se)
print(tree.pruned)
pdf("regression_tree_pruned_R.pdf", width=12, height=8)
plot(tree.pruned, main = "Pruned Regression Tree")
text(tree.pruned)
dev.off()

####################################################################
# a bootstrap sample: showing how sensitive the tree structure is
set.seed(10)
data <- data[sample(1 : nrow(data), nrow(data), replace=TRUE), ]

tree.full <- rpart(Inc ~., data = data, method = "anova", control = rpart.control(cp = .0005))
tree.pruned <- prune(tree.full, cp = cp.best.1se)
pdf("regression_tree_bootstraped_R.pdf", width=12, height=8)
plot(tree.pruned, main = "Pruned Regression Tree")
text(tree.pruned)
dev.off()

#######################################################################
#	Stop redirecting console output
sink()
