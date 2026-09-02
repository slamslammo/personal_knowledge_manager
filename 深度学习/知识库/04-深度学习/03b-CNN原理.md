<!--# cnnprinciples -->
# CNN 原理:完整课件脉络

> 本篇按李宏毅 CNN 课件 `cnn_v4.pdf` 的 1-35 页顺序整理,并用 d2l 卷积章节校对术语。核心主线是:图像分类若直接全连接会忽略图像结构;CNN 通过**局部感受野**、**参数共享**、**多个 filters**、**多层卷积**和**池化**把图像先验写进模型。

![课件封面:Convolutional Neural Network](../../assets/cnn-principles/cnn-lee-page1.png)

## 1. 从图像分类任务出发

图像分类的目标是:输入一张固定大小的图像,输出每个类别的分数或概率,再用交叉熵衡量预测和真实标签的差距。这个任务本身和 softmax 分类一致,区别在于输入不是普通向量,而是有空间结构的图像。

![图像分类:输入图像,模型输出类别概率,用 cross entropy 训练](../../assets/cnn-principles/cnn-lee-page2.png)

彩色图像可以看成一个三维张量:

$$
H\times W\times C
$$

其中 $H,W$ 是高和宽,$C$ 是通道数。课件里用 $100\times100$ 彩色图说明:它不是一串无结构数字,而是三张通道图叠在一起,每个数表示某个位置某个通道的强度。

![彩色图像是 3-D tensor:高、宽、通道](../../assets/cnn-principles/cnn-lee-page3.png)

如果把 $100\times100\times3$ 直接展平成向量再接全连接层,第一层参数会非常大。课件用 $1000$ 个神经元举例,参数量达到 $3\times10^7$ 量级,于是提出问题:图像处理真的需要 fully connected 吗?

![全连接处理图像会产生巨大参数量,引出是否必须 fully connected](../../assets/cnn-principles/cnn-lee-page4.png)

这一页是 CNN 动机的关键:不是说全连接完全不能做图像分类,而是它没有利用图像的两个强先验:

- 重要模式通常是局部的;
- 同一模式可能出现在不同位置。

## 2. Observation 1:重要模式小于整张图

人识别鸟时,常常不是先把整张图每个像素都等量看一遍,而是注意到一些关键局部:鸟喙、眼睛、轮廓、羽毛纹理。课件先用直观图说明:图像分类可以先找关键 pattern。

![Observation 1:人也可能先识别关键局部模式](../../assets/cnn-principles/cnn-lee-page5.png)

课件中间用一个网络迷因图做过渡,强调"看起来像鸟"往往来自局部视觉线索。这页不是数学推导,但它的作用是把抽象模型拉回直观经验。

![直观过渡:局部视觉线索可能主导识别结果](../../assets/cnn-principles/cnn-lee-page6.png)

于是得到第一条简化:一个神经元不一定要看完整图像,只需要看某个局部区域。这就是**局部感受野**的直觉来源。

![局部模式小于整张图,一个神经元不一定要看完整图像](../../assets/cnn-principles/cnn-lee-page7.png)

## 3. Simplification 1:局部感受野

在全连接层里,每个神经元都连接全部输入;在 CNN 里,每个输出位置只看输入中的一个小窗口,这个窗口叫**感受野**。

![Simplification 1:每个神经元只连接一个局部 receptive field](../../assets/cnn-principles/cnn-lee-page8.png)

课件随后说明:感受野可以有不同大小、可以重叠、也不一定是正方形;但典型设置会让许多局部窗口滑过整张图。

![感受野可以重叠,不同神经元看不同局部区域](../../assets/cnn-principles/cnn-lee-page9.png)

典型设置包括:

- kernel size:局部窗口大小,如 $3\times3$;
- stride:窗口每次滑动几格;
- padding:边界是否补零;
- all channels:卷积核通常跨过输入的全部通道。

![典型设置:kernel size、stride、padding、overlap、all channels](../../assets/cnn-principles/cnn-lee-page10.png)

若输入是单通道图像,一个 $3\times3$ 局部窗口的输出可以写成:

$$
y_{i,j}=\sum_{u=0}^{2}\sum_{v=0}^{2}K_{u,v}X_{i+u,j+v}+b
$$

如果输入有 $C$ 个通道,卷积核也要有 $C$ 个通道:

$$
K\in\mathbb R^{3\times3\times C}
$$

## 4. Observation 2:同一模式会出现在不同位置

只做局部连接还不够。因为同一种模式可能出现在图像不同位置,例如鸟喙可以在左上、右下或中间。如果每个局部位置都各自学习一套"鸟喙检测器",仍然浪费参数。

![Observation 2:同一模式可能出现在不同区域](../../assets/cnn-principles/cnn-lee-page11.png)

于是得到第二条简化:**参数共享**。不同位置的神经元如果在检测同一种模式,就可以使用同一组参数。

![Simplification 2:不同位置共享同一组参数](../../assets/cnn-principles/cnn-lee-page12.png)

注意,共享参数并不是说两个神经元输入值相同;它们看的是不同位置的局部窗口,但使用同一组权重去做同一种检测。

![参数共享:不同输入局部窗口,相同权重模式](../../assets/cnn-principles/cnn-lee-page13.png)

典型设置中,每个局部位置会有一组神经元,不同位置的对应神经元共享参数。

![参数共享的典型设置:不同 receptive fields 上有同组参数](../../assets/cnn-principles/cnn-lee-page14.png)

把共享参数的一组神经元换个说法,就是一个 **filter**。多个 filter 就代表多种局部模式检测器。

![多个 filters:同一组 filter 在不同位置复用](../../assets/cnn-principles/cnn-lee-page15.png)

课件把 CNN 相比全连接的收益总结为两点:

- 局部感受野:局部模式小于整张图;
- 参数共享:同一模式会出现在不同区域。

![卷积层收益:局部感受野 + 参数共享](../../assets/cnn-principles/cnn-lee-page16.png)

## 5. Filter 视角:卷积层如何产生 feature map

前面是从神经元视角讲 CNN。接下来换成 filter 视角更直观:一个 filter 是一个小张量,如 $3\times3\times C$,负责检测一种小模式。

![Filter 视角:每个 filter 检测一个小模式](../../assets/cnn-principles/cnn-lee-page17.png)

以单通道 $6\times6$ 图像为例,课件给出两个 $3\times3$ filters。filter 里的数值都是模型要学习的参数,不是人工固定的模板。

![卷积示例:输入图像与两个 filters](../../assets/cnn-principles/cnn-lee-page18.png)

filter 在图像上滑动,每个位置做局部加权求和,得到一个输出值。stride 为 1 时,它会逐格移动。

![filter 在图像上滑动,每个位置产生一个响应](../../assets/cnn-principles/cnn-lee-page19.png)

对每个 filter 都做同样过程,就会得到一张 feature map。多个 filters 产生多张 feature maps,也就是输出的多个通道。

![每个 filter 产生一张 feature map](../../assets/cnn-principles/cnn-lee-page20.png)

如果一层有 64 个 filters,输出就可以看成一张有 64 个通道的"新图像"。这不是原始 RGB 图像,而是 64 种局部模式的响应图。

![一层卷积输出可以看成有多个通道的新 image](../../assets/cnn-principles/cnn-lee-page21.png)

## 6. 多层卷积:在 feature maps 上继续卷积

第二层卷积的输入不再是原始像素,而是上一层产生的多通道 feature maps。若上一层输出 64 个通道,下一层的 filter 尺寸就可能是 $3\times3\times64$。

![多层卷积:下一层 filter 的深度等于上一层通道数](../../assets/cnn-principles/cnn-lee-page22.png)

多层卷积让网络可以逐层组合特征:

- 第一层可能学边缘、颜色变化、简单纹理;
- 中间层组合成角点、笔画、局部形状;
- 更深层组合成物体部件和类别相关特征。

![多层卷积:由浅层局部响应继续组合成高层特征](../../assets/cnn-principles/cnn-lee-page23.png)

## 7. 两种故事其实是同一件事

课件接着对比"神经元版本"和"filter 版本":一个是说不同位置的神经元共享参数,一个是说同一个 filter 在输入图像上卷积。两者是同一件事的两种描述。

![神经元视角与 filter 视角的对照](../../assets/cnn-principles/cnn-lee-page24.png)

从神经元视角看:不同 receptive fields 上的神经元共享参数。

![神经元视角:不同 receptive fields 共享参数](../../assets/cnn-principles/cnn-lee-page25.png)

从 filter 视角看:同一个 filter 在整张输入图像上滑动。

![两种故事等价:神经元只看局部 + filter 扫过全图](../../assets/cnn-principles/cnn-lee-page26.png)

这一步很重要:卷积并不是额外神秘操作,而是"局部连接 + 参数共享"的紧凑表示。

## 8. Observation 3:适度下采样不改变对象

第三个观察是:对许多图像分类任务,适度降低分辨率不会改变物体类别。鸟缩小后仍然是鸟,猫缩小后仍然是猫。

![Observation 3:适度 subsampling 不改变对象类别](../../assets/cnn-principles/cnn-lee-page27.png)

这引出 pooling。最大池化会在一个局部区域里取最大值:

$$
y_{i,j}=\max_{(u,v)\in \Omega_{i,j}}x_{u,v}
$$

![Max Pooling:每个局部区域取最大响应](../../assets/cnn-principles/cnn-lee-page28.png)

池化的作用:

- 降低 feature map 的空间尺寸;
- 减少后续计算;
- 增强对小范围位移的鲁棒性;
- 扩大后续层间接看到的原图范围。

卷积层和池化层可以交替堆叠,逐步提取特征并降低空间分辨率。

![卷积层 + 池化层可以重复堆叠](../../assets/cnn-principles/cnn-lee-page29.png)

## 9. 完整 CNN:卷积/池化提特征,全连接分类

经典图像分类 CNN 可以概括为:

$$
\text{image}\rightarrow \text{conv/pool blocks}\rightarrow \text{flatten}\rightarrow \text{fully connected}\rightarrow \text{softmax}
$$

![完整 CNN:Convolution、Pooling、Flatten、Fully Connected、Softmax](../../assets/cnn-principles/cnn-lee-page30.png)

这条结构线和 MLP 的关系是:

| 阶段 | 作用 |
|---|---|
| 卷积层 | 学局部模式检测器 |
| 多个 filters | 同时检测多种局部模式 |
| 多层卷积 | 从小模式组合成更高层模式 |
| 池化 / 下采样 | 降低分辨率,增强小位移鲁棒 |
| 全连接 / softmax | 基于提取出的特征做最终分类 |

## 10. 应用:围棋与其他序列任务

课件最后说明 CNN 不只用于自然图像。围棋棋盘也可以看成 $19\times19$ 的二维结构,每个位置有黑子、白子、空位等通道。全连接也能用,但 CNN 更适合利用局部棋形和位置复用。

![应用:围棋棋盘可以看成 image-like input](../../assets/cnn-principles/cnn-lee-page31.png)

围棋里同样存在 CNN 的前两个观察:

- 局部棋形小于整张棋盘;
- 相似棋形可出现在不同区域。

![为什么 CNN 可用于围棋:局部模式与位置复用](../../assets/cnn-principles/cnn-lee-page32.png)

但池化不一定适合围棋,因为棋盘上的精确位置关系很重要。课件用 AlphaGo 不使用 pooling 提醒:池化是常见工具,不是 CNN 的必选件。

![围棋任务中 pooling 未必合适,因为位置精度很重要](../../assets/cnn-principles/cnn-lee-page33.png)

CNN 也可以扩展到语音和自然语言等领域。关键不在于输入是不是照片,而在于输入是否有局部结构、模式复用和层级组合。

![更多应用:Speech 与 Natural Language Processing](../../assets/cnn-principles/cnn-lee-page34.png)

最后,课件提醒 CNN 本身并不天然对缩放和旋转不变,通常需要数据增强或专门结构,例如 Spatial Transformer Layer。

![CNN 对缩放和旋转不天然不变,可用数据增强或空间变换层](../../assets/cnn-principles/cnn-lee-page35.png)

## 11. 和 d2l 标准术语对齐

把课件直觉和 d2l 术语合起来:

| 课件直觉 | d2l / 标准术语 | 作用 |
|---|---|---|
| 神经元只看一小块 | receptive field / kernel | 局部连接 |
| 不同位置共享检测器 | parameter sharing | 减少参数,复用模式 |
| filter 扫过整张图 | convolution / cross-correlation | 生成 feature map |
| 多个 filters | output channels | 同时检测多种特征 |
| 多层卷积 | hierarchical features | 低层到高层组合 |
| pooling | downsampling | 降低分辨率,增强鲁棒性 |

## 应掌握的要点

- 图像分类输入是 $H\times W\times C$,不是普通无结构向量;
- 全连接可以训练,但参数大且没有利用图像先验;
- CNN 的三个核心观察是:局部模式小、模式位置可变、适度下采样常不改类别;
- 局部感受野让神经元只看一小块;
- 参数共享让同一个 filter 在全图复用;
- 多个 filters 产生多张 feature maps;
- 多层卷积在 feature maps 上继续组合更复杂的特征;
- pooling 常用于下采样,但不一定适合所有任务;
- 完整 CNN 通常是卷积/池化提特征,末端分类器输出类别概率。

---
### 参考链接
- 李宏毅机器学习 2021:[CNN 课程视频](https://www.youtube.com/watch?v=OP5HcXJg2Aw&list=PLJV_el3uVTsMhtt7_Y6sgTHGHp1Vb2P2J&index=9),课件截图来自本地 `cnn_v4.pdf`
- d2l:[第 6 章 卷积神经网络](https://zh.d2l.ai/chapter_convolutional-neural-networks/index.html)
