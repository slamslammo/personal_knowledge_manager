<!--# knn -->
# KNN

KNN 用“离当前样本最近的 $k$ 个训练样本”来预测。

## 核心直觉

相似的样本应该有相似的输出。

## 核心要点

- KNN 几乎没有显式训练过程;
- 预测成本较高;
- 对特征尺度敏感;
- 高维空间中距离度量会变得困难;
- $k$ 控制模型复杂度。

## sklearn 对应

- `KNeighborsClassifier`;
- `KNeighborsRegressor`。
