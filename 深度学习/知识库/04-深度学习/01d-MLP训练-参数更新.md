<!--# mlptrain -->
# MLP 训练:batch、epoch 与参数更新

> 本篇承接 [感知机 → 多层感知机](node:mlp) 与 [训练:线性模型 → 深度网络](node:training),专门解释 MLP 训练时"参数怎么一轮轮更新"。视频里的 `compute gradient → update` 是一般训练框架;在 MLP 里,`compute gradient` 这一步通常由 [反向传播](node:backprop) / 自动微分完成。

## 1. 这张训练流程图代表什么

监督学习训练的目标可以写成:

$$
\theta^\*=\arg\min_\theta L(\theta)
$$

这里 $\theta$ 代表模型的全部可训练参数,$L(\theta)$ 是损失。训练不是一次算出 $\theta^\*$,而是从一个初始参数 $\theta^0$ 出发,不断重复:

1. 取一批数据;
2. 用当前参数做前向传播;
3. 算这一批数据上的损失;
4. 计算损失对参数的梯度;
5. 沿负梯度方向更新参数。

所以截图里的流程确实代表 MLP 的一般训练过程,也代表很多可微模型的训练过程。区别在于:不同模型的前向函数不同,损失函数可能不同,梯度的计算难度也不同。

## 2. 参数 $\theta$ 到底是什么

在线性模型里,参数可能只是 $\mathbf w,b$。在 MLP 里,参数包括每一层的权重矩阵和偏置向量。以一个隐藏层为例:

$$
\mathbf h=\sigma(XW_1+\mathbf b_1),\qquad
\mathbf o=\mathbf hW_2+\mathbf b_2
$$

那么参数集合就是:

$$
\theta=\{W_1,\mathbf b_1,W_2,\mathbf b_2\}
$$

为了写梯度下降公式,常把所有参数想象成一个很长的向量:

$$
\theta=
\begin{bmatrix}
\theta_1\\
\theta_2\\
\theta_3\\
\vdots
\end{bmatrix}
$$

梯度 $g=\nabla_\theta L$ 也是同样长度的向量,每一项告诉我们:在当前参数位置,某个参数变大一点会让损失怎么变。

## 3. 损失是参数的函数

训练数据固定以后,预测结果由参数决定,损失也就由参数决定:

$$
\theta \rightarrow \hat y=f_\theta(x) \rightarrow L(\hat y,y)
$$

如果用全部 $N$ 条样本定义训练损失,可以写成:

$$
L(\theta)=\frac{1}{N}\sum_{n=1}^{N}\ell(f_\theta(x_n),y_n)
$$

实际训练深度网络时,通常不会每次都用全部数据算梯度,而是取一个小批量 batch。若当前 batch 是 $\mathcal B$,batch size 为 $B$,则这一小批上的损失是:

$$
L_{\mathcal B}(\theta)=\frac{1}{B}\sum_{n\in\mathcal B}\ell(f_\theta(x_n),y_n)
$$

于是一次更新用的是当前 batch 的梯度:

$$
g=\nabla_\theta L_{\mathcal B}(\theta)
$$

这个梯度不是完整训练集损失的精确梯度,而是一个小批量估计。它通常更快,也带有一点随机性,这就是 mini-batch SGD 的基本思想。

## 4. 一次参数更新在做什么

假设当前参数是 $\theta^t$,学习率是 $\eta$,当前 batch 上算出的梯度是:

$$
g^t=\nabla_\theta L_{\mathcal B_t}(\theta^t)
$$

最基本的 SGD 更新为:

$$
\theta^{t+1}\leftarrow\theta^t-\eta g^t
$$

逐项看就是:

$$
\begin{bmatrix}
\theta_1^{t+1}\\
\theta_2^{t+1}\\
\vdots
\end{bmatrix}
\leftarrow
\begin{bmatrix}
\theta_1^t\\
\theta_2^t\\
\vdots
\end{bmatrix}
-
\eta
\begin{bmatrix}
\dfrac{\partial L_{\mathcal B_t}}{\partial \theta_1}\\
\dfrac{\partial L_{\mathcal B_t}}{\partial \theta_2}\\
\vdots
\end{bmatrix}
$$

直觉是:如果某个参数增大会让损失上升,它的梯度为正,更新时就减小它;如果某个参数增大会让损失下降,它的梯度为负,更新时反而会增大它。学习率 $\eta$ 控制这一步走多远。

## 5. batch、update、epoch 的关系

把训练集分成很多个 batch,每处理一个 batch 就更新一次参数。若训练集有 $N$ 条样本,batch size 是 $B$,且 $N$ 能被 $B$ 整除,那么一轮 epoch 的更新次数是:

$$
\frac{N}{B}
$$

例如:

| 样本数 $N$ | batch size $B$ | 1 个 epoch 的更新次数 |
|---|---:|---:|
| 10000 | 10 | 1000 |
| 1000 | 100 | 10 |

如果不能整除,最后一个 batch 可能更小,更新次数通常是 $\lceil N/B\rceil$。

**1 个 epoch** 的意思是:训练过程已经把所有训练样本大致看过一遍。训练通常会跑很多个 epoch,每个 epoch 开始前还会打乱数据顺序,再重新分 batch。

## 6. 为什么这里没有提反向传播

因为这段内容讲的是**优化流程**,它把"求梯度"先写成一个抽象步骤:

$$
g=\nabla_\theta L(\theta)
$$

但对 MLP 来说,这个 $g$ 不是凭空出现的。MLP 的参数通过多层复合函数影响损失:

$$
W_1 \rightarrow \mathbf z_1 \rightarrow \mathbf h \rightarrow \mathbf o \rightarrow L
$$

早期层参数离损失很远,必须沿这条链用链式法则把梯度传回来。**反向传播负责的正是这件事:高效计算 $g$。**

所以这两句话要区分开:

- `compute gradient`:训练流程里的一个步骤,表示"现在需要梯度";
- `backpropagation`:在多层网络里高效完成这个步骤的方法。

换句话说,视频这段没有提反向传播,不是因为 MLP 不需要反向传播,而是因为它正在讲训练循环的外层框架。等进入"梯度如何计算"时,才需要专门展开反向传播。

## 7. MLP 的一次 batch 训练过程

把上面的内容合起来,一个 MLP 在一个 batch 上的一次更新是:

1. **取 batch**:从训练集中取出 $X_{\mathcal B},Y_{\mathcal B}$。
2. **前向传播**:用当前参数 $\theta^t$ 计算预测。

$$
\mathbf h=\sigma(X_{\mathcal B}W_1+\mathbf b_1),\qquad
\mathbf o=\mathbf hW_2+\mathbf b_2
$$

3. **计算损失**:回归任务可用 MSE,分类任务常用交叉熵。
4. **反向传播求梯度**:得到所有参数的梯度。

$$
\nabla_{W_1}L,\quad \nabla_{\mathbf b_1}L,\quad \nabla_{W_2}L,\quad \nabla_{\mathbf b_2}L
$$

5. **更新参数**:SGD 会直接沿负梯度方向更新;Adam 等优化器会在梯度基础上加入动量、自适应步长等机制。

$$
W_1\leftarrow W_1-\eta\nabla_{W_1}L,\qquad
\mathbf b_1\leftarrow \mathbf b_1-\eta\nabla_{\mathbf b_1}L
$$

输出层参数 $W_2,\mathbf b_2$ 也同样更新。

## 8. 这篇和反向传播文章的边界

本篇回答的是:"拿到梯度之后,MLP 的训练循环如何推动参数一步步更新?"

[反向传播与计算图](node:backprop) 回答的是:"这些梯度到底如何沿计算图一层层算出来?"

因此可以把 MLP 训练理解成两层:

| 层次 | 关注问题 |
|---|---|
| 外层训练循环 | batch 怎么取,loss 怎么算,参数什么时候更新,epoch 怎么数 |
| 内层梯度计算 | 每个参数的梯度如何由反向传播得到 |

两者合在一起,才是完整的 MLP 训练过程。

## 常见误解

- **误解 1:1 个 epoch 只更新一次参数。** 不对。1 个 epoch 通常包含多个 batch,每个 batch 更新一次。
- **误解 2:batch loss 就是完整训练集 loss。** 不对。batch loss 是完整 loss 的小批量估计。
- **误解 3:反向传播就是参数更新。** 不对。反向传播负责求梯度;SGD / Adam 负责用梯度更新参数。
- **误解 4:MLP 的训练规则和线性模型完全不同。** 不对。训练闭环一致,只是 MLP 的梯度计算必须穿过多层结构。

## 应掌握的要点

- MLP 训练目标是最小化损失 $L(\theta)$;
- $\theta$ 表示网络中所有可训练参数;
- batch 是一次计算梯度和更新参数所用的小批量数据;
- 1 个 epoch 表示大致看完全部训练样本一次,通常包含多次 update;
- 参数更新公式是 $\theta^{t+1}\leftarrow\theta^t-\eta\nabla_\theta L_{\mathcal B_t}(\theta^t)$;
- 反向传播不负责决定怎么更新,它负责把这个公式里的梯度高效算出来。

---
### 参考链接
- 本库内链:[训练:线性模型 → 深度网络](node:training) · [反向传播与计算图](node:backprop)
- 李宏毅机器学习 2021:[Optimization of New Model](https://www.youtube.com/watch?v=bHcJCp2Fyxs&list=PLJV_el3uVTsMhtt7_Y6sgTHGHp1Vb2P2J&index=2)
