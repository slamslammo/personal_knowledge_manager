# 机器学习实验

本目录存放机器学习板块的可运行实验。第一阶段以本地 Mac 可运行为约束，使用 scikit-learn、NumPy、pandas、Matplotlib、seaborn 与 JupyterLab。

## 环境

项目使用 Miniforge 管理独立环境，环境定义在 `机器学习/environment.yml`：

```bash
cd 机器学习
conda env create -f environment.yml
conda activate pkm-ml
python --version
python -m pip --version
```

当前环境使用 Python 3.11。进入 `pkm-ml` 后，`python` 与 `python -m pip` 都指向该虚拟环境，不依赖系统 Python。

## 打开与运行

```bash
conda activate pkm-ml
cd 机器学习
jupyter lab
```

浏览器直接打开 `.ipynb` 会看到 JSON 源文件；JupyterLab、VS Code 和 GitHub 会把它渲染成 Notebook。仓库同时保留 `实验/reports/` 中的静态 HTML，方便无需启动服务直接阅读。

重新生成第一份实验：

```bash
python 实验/scripts/build_iris_data_analysis_notebook.py
jupyter nbconvert --to notebook --execute --inplace 实验/notebooks/01_iris_data_analysis.ipynb
jupyter nbconvert --to html --output-dir 实验/reports 实验/notebooks/01_iris_data_analysis.ipynb
```

## 实验规范

每个实验必须包含：数据来源、核心问题、关键代码、执行结果、观察、结论和对应知识节点。概念正文解释“为什么”，Notebook 展示“如何验证”，静态 HTML 用于直接阅读。

## 实验顺序

1. Iris 数据理解、预处理与特征分析。
2. 分类任务划分、指标与交叉验证。
3. 逻辑回归、KNN 与决策边界。
4. 决策树、随机森林与集成学习。
5. SVM 与核方法。
6. PCA、K-Means 与聚类评估。
7. Pipeline 与 GridSearchCV。
8. MLPClassifier 连接深度学习。

回归使用独立的小型数据示例，不强行套用 Iris。
