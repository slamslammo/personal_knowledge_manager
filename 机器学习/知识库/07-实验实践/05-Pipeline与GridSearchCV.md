<!--# pipeline -->
# Pipeline 与 GridSearchCV

Pipeline 把预处理和模型串成一个整体,GridSearchCV 在交叉验证中搜索超参数。

## 核心价值

- 避免数据泄漏;
- 让预处理和模型一起参与交叉验证;
- 让实验更可复现;
- 让代码从“脚本堆叠”变成“训练流程”。

## 典型结构

ColumnTransformer
→ StandardScaler / OneHotEncoder
→ Model
→ GridSearchCV

## 本地运行

Pipeline 与 GridSearchCV 完全适合本地 Mac。多数经典数据集规模很小,CPU 足够。
