# MLP 引入非线性的作用 —— 可视化复现

配套知识点:[`知识库/04-深度学习/01a-MLP引入非线性的作用.md`](../../知识库/04-深度学习/01a-MLP引入非线性的作用.md)

用一份 50 点的环形数据,从零(numpy 手写前向 + 反向传播)演示「线性模型为何分不开环形数据,MLP 如何靠隐藏层非线性换空间解决」。所有图都由本目录代码生成,可直接在 Jupyter / VS Code 复现与改造。

## 文件

| 文件 | 说明 |
|---|---|
| `nonlinear_demo.py` | 完整可运行代码(含数据、训练、6 张图)。用 `# %%` 分单元,VS Code / Jupyter 可逐块运行 |
| `nonlinear_demo.ipynb` | 同款代码的 Jupyter notebook 版,可直接在 Jupyter 打开运行(1 说明单元 + 8 代码单元) |
| `nonlinear_data.csv` | 原始 50 点数据(`x1, x2, label`;内圈 20、外圈 30),保证与文档图一致 |
| `nonlinear_data_hidden.csv` | 运行后生成:每个点经隐藏层算出的 `(h1, h2, h3)` 新坐标 |
| `figures/` | 运行后生成的 6 张图(首次运行自动创建) |

## 运行

```bash
pip install numpy matplotlib pillow   # pillow 用于写旋转 GIF
python nonlinear_demo.py              # 生成全部图到 ./figures/
```

或直接在 **Jupyter / VS Code** 打开 `nonlinear_demo.ipynb`(或打开 `.py` 按 `# %%` 单元),逐块运行——3D 图可交互旋转,便于观察"三角凹陷"与俯瞰投影。`.ipynb` 与 `.py` 代码一致;若改了 `.py`,可用 `jupytext --to notebook nonlinear_demo.py` 重新同步 notebook。

> 中文标签需系统装有 CJK 字体(macOS 自带 PingFang/Heiti;Linux 可装 `fonts-noto-cjk`)。缺字体不影响计算,只是中文显示为方块。

## 六张图

1. `nonlinear-data-linear.png` —— 环形数据 + 线性分类器分不开。
2. `nonlinear-step1-r2.png` —— 已知分布:1 个特制单元 `r²` 把数据**降到 1 维**,一个阈值分开,回到 2D 是圆。
3. `nonlinear-h-a.png` —— 3 个 tanh:MLP 结构 + 每个 hᵢ 的**真实表达式** + 逐点算出 `(h1,h2,h3)`。
4. `nonlinear-h-b.gif` —— 旋转动图:50 点画在**真实的** `(h1,h2,h3)` 坐标上;转到 edge-on(侧视)时平面缩成一条线,两类清楚分居两侧(升维 = 换空间让线性可分)。
5. `nonlinear-h-c.png` —— 映射回原 2D:边界 = 平面的「原像」;同两点★分居切面两侧。
6. `nonlinear-step3-width.png` —— 加大宽度 3 / 5 / 8:三角形 → 五边形 → 八边形 ≈ 圆(整片区域判准约 94% → 96% → 98%)。

## 关键设定(可改)

- **数据**:`load_or_make_data()`,内圈 `r∈[0.05,1.0]`、外圈 `r∈[1.25,2.1]`,种子 7;删掉 csv 会按规则重新生成。
- **模型**:`train(h, seed, epochs, lr)`,结构 `2 → h(tanh) → 1(sigmoid)`,交叉熵 + 全量梯度下降,特征标准化。
- **"整片区域判准"**:`acc_eval()` 在同分布另采 4000 点上算正确率,衡量边界形状(而非死记 50 个训练点)。
- **典型表现**:`pick(h)` 跑 25 个随机初始化取平均判准,图用最接近平均的那次(不挑最好,避免小模型"蒙对")。
- **真实隐藏坐标图**:`pick_spread()` 用轻微权重衰减(`wd`)挑一个**低饱和**网络,让 tanh 不过度饱和、`(h1,h2,h3)` 在 3D 里铺得开;`hidden()` 算出每点真实隐藏坐标(存入 `nonlinear_data_hidden.csv`)。

想试 ReLU?把 `train` 里的 `np.tanh(...)` 换成 `np.maximum(0, ...)`、并把 `1 - H**2` 换成 `(Z1 > 0)`(需另存预激活),即可观察边界从"圆滑"变"带硬棱角的多边形"。
