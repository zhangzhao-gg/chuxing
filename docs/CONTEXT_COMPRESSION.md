# 上下文压缩功能说明

## 功能概述

上下文压缩功能可以在对话历史过长时，自动将早期的对话压缩为摘要，从而：
- 减少 token 消耗
- 保持对话连贯性
- 避免超出模型上下文限制
- 保留最近的重要对话

## 配置说明

在 `.env` 文件中配置以下参数：

```bash
# 上下文压缩配置
ENABLE_CONTEXT_COMPRESSION=false  # 是否启用上下文压缩（true/false）
COMPRESSION_THRESHOLD=30          # 触发压缩的消息数阈值
COMPRESSION_TARGET=10             # 压缩后保留的最近消息数
```

### 配置参数详解

1. **ENABLE_CONTEXT_COMPRESSION**
   - `false`: 禁用压缩（默认）
   - `true`: 启用压缩

2. **COMPRESSION_THRESHOLD**
   - 当对话历史消息数超过此阈值时，触发压缩
   - 默认值：30 条消息
   - 建议范围：20-50

3. **COMPRESSION_TARGET**
   - 压缩后保留的最近消息数
   - 默认值：10 条消息
   - 建议范围：5-20

## 工作原理

### 压缩流程

```
原始对话历史（35条消息）:
[msg1, msg2, msg3, ..., msg25, msg26, ..., msg35]

↓ 触发压缩（超过阈值30）

压缩后（摘要 + 10条最近消息）:
[摘要(msg1-25), msg26, msg27, ..., msg35]
```

### 压缩策略

1. **检查阈值**：每次生成回复时，检查历史消息数是否超过 `COMPRESSION_THRESHOLD`

2. **分割消息**：
   - 需要压缩的消息：前 N-TARGET 条
   - 保留的消息：最近 TARGET 条

3. **生成摘要**：
   - 使用 LLM 将需要压缩的消息总结为简洁摘要
   - 提取关键信息、决策和结论
   - 保留重要的背景信息

4. **构建上下文**：
   ```
   [system_prompt]
   [历史对话摘要]
   [最近10条消息]
   [当前用户消息]
   ```

## 使用示例

### 场景1：短对话（不触发压缩）

```bash
# 配置
ENABLE_CONTEXT_COMPRESSION=true
COMPRESSION_THRESHOLD=30

# 对话历史：20条消息
# 结果：不压缩，直接使用全部历史
```

### 场景2：长对话（触发压缩）

```bash
# 配置
ENABLE_CONTEXT_COMPRESSION=true
COMPRESSION_THRESHOLD=30
COMPRESSION_TARGET=10

# 对话历史：35条消息
# 结果：
#   - 前25条消息 → 压缩为摘要
#   - 最近10条消息 → 保留原文
#   - 总计：摘要 + 10条消息
```

### 场景3：禁用压缩

```bash
# 配置
ENABLE_CONTEXT_COMPRESSION=false

# 对话历史：任意数量
# 结果：不压缩，使用原有的滑动窗口裁剪策略
```

## 压缩效果示例

### 原始对话（25条消息）

```
用户: 你好
助手: 你好！有什么可以帮助你的吗？
用户: 我想了解Python
助手: Python是一门优秀的编程语言...
... (共25条消息)
```

### 压缩后的摘要

```
[历史对话摘要]
用户咨询了Python编程语言的相关信息。助手介绍了Python的特点、应用场景和学习路径。
用户表示对数据分析感兴趣，助手推荐了pandas、numpy等库，并提供了学习资源。
用户询问了具体的代码示例，助手展示了数据读取和处理的基本操作。

[以下是最近的对话]
用户: 那机器学习呢？
助手: 机器学习可以使用scikit-learn...
... (最近10条消息)
```

## 性能影响

### Token 消耗

- **不压缩**：35条消息 ≈ 3500 tokens
- **压缩后**：摘要(200 tokens) + 10条消息(1000 tokens) ≈ 1200 tokens
- **节省**：约 65% 的 token

### 响应时间

- 压缩过程需要额外调用一次 LLM（生成摘要）
- 增加约 1-2 秒的延迟
- 但后续对话会因为上下文更短而更快

## 最佳实践

### 推荐配置

**日常对话场景**：
```bash
ENABLE_CONTEXT_COMPRESSION=true
COMPRESSION_THRESHOLD=30
COMPRESSION_TARGET=10
```

**长期咨询场景**（如客服）：
```bash
ENABLE_CONTEXT_COMPRESSION=true
COMPRESSION_THRESHOLD=20
COMPRESSION_TARGET=8
```

**短对话场景**（如问答）：
```bash
ENABLE_CONTEXT_COMPRESSION=false
```

### 注意事项

1. **首次压缩会有延迟**：生成摘要需要调用 LLM
2. **摘要可能丢失细节**：不适合需要精确回溯的场景
3. **API 成本**：压缩会额外消耗 API 调用次数
4. **阈值设置**：根据实际对话长度调整

## 监控和调试

### 日志输出

启用压缩后，日志会显示：

```
INFO - 触发上下文压缩: 当前消息数=35, 阈值=30
INFO - 开始压缩上下文: 原始消息数=25
INFO - 上下文压缩完成: 摘要长度=156
INFO - 上下文压缩完成: 35 条 → 摘要 + 10 条
```

### 检查压缩效果

可以通过日志观察：
- 压缩触发频率
- 摘要质量
- Token 节省情况

## 故障排除

### 问题1：压缩失败

**现象**：日志显示"上下文压缩失败"

**原因**：LLM API 调用失败

**解决**：
- 检查 API Key 是否有效
- 检查网络连接
- 系统会自动降级为简单摘要

### 问题2：摘要质量差

**现象**：压缩后的摘要丢失重要信息

**解决**：
- 增加 `COMPRESSION_TARGET`，保留更多原始消息
- 调整压缩提示词（修改 `context_compression.py`）

### 问题3：响应变慢

**现象**：启用压缩后响应时间增加

**解决**：
- 提高 `COMPRESSION_THRESHOLD`，减少压缩频率
- 使用更快的压缩模型（如 gpt-3.5-turbo）

## 技术实现

### 核心文件

- `backend/core/config.py`: 配置定义
- `backend/services/context_compression.py`: 压缩服务
- `backend/services/llm.py`: 集成压缩逻辑

### 压缩算法

```python
if message_count > COMPRESSION_THRESHOLD:
    messages_to_compress = history[:-COMPRESSION_TARGET]
    messages_to_keep = history[-COMPRESSION_TARGET:]

    summary = await compress_messages(messages_to_compress)

    compressed_context = [
        {"role": "system", "content": f"[历史对话摘要]\n{summary}"},
        *messages_to_keep
    ]
```

## 未来改进

- [ ] 支持增量压缩（多次压缩的摘要合并）
- [ ] 支持自定义压缩提示词
- [ ] 支持压缩历史的持久化存储
- [ ] 支持压缩质量评估
- [ ] 支持不同场景的压缩策略
