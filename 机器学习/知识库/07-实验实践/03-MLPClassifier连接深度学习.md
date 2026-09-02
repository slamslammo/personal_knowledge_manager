<!--# mlpbridge -->
# MLPClassifier 连接深度学习

`sklearn.neural_network.MLPClassifier` 可以作为传统机器学习到神经网络的桥。

## 为什么适合本地 Mac

- 数据集通常很小;
- CPU 可运行;
- API 保持 sklearn 风格;
- 能观察隐藏层、激活函数、正则化、迭代次数等概念;
- 不需要先进入 PyTorch 训练工程。

## 它不适合做什么

- 不适合训练大型深度网络;
- 不适合作为 CNN/RNN/Transformer 实验平台;
- 不适合处理大规模图像或文本任务。

## 学习价值

它适合用来理解:

- 多层非线性模型;
- 训练迭代;
- 正则化;
- 过拟合;
- 从手工特征到表示学习的过渡。
