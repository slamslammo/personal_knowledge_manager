<!--# sklearn -->
# sklearn 实践范式

scikit-learn 的核心不是某个模型 API,而是一套统一范式:

estimator.fit(X_train, y_train)
estimator.predict(X_test)
estimator.score(X_test, y_test)

## 重要概念

- estimator;
- transformer;
- predictor;
- pipeline;
- cross-validation;
- model selection;
- metrics。

## 理解检查

- 哪些对象有 `fit_transform`?
- `fit` 和 `transform` 的边界是什么?
- 为什么 Pipeline 能防止数据泄漏?
- 如何把预处理和模型选择合在一起调参?
