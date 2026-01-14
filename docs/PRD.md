# 产品需求文档（PRD）
# 情绪陪伴与关键时刻兑现系统

**文档版本**: v1.0
**创建日期**: 2026-01-14
**负责人**: 张钊
**状态**: 草稿

---

## 一、产品概述

### 1.1 产品定位

一个基于 AI 的情绪陪伴系统，通过轻目的陪聊采集用户行为数据，自动识别用户生活中的关键时刻，并在合适的时间完成情绪兑现，为用户提供有温度的陪伴体验。

### 1.2 核心价值

- **用户价值**: 获得有温度的陪伴，在关键时刻得到及时的关心和支持
- **产品壁垒**: 关键时刻识别引擎 + 情绪兑现调度系统
- **商业价值**: 提升用户粘性，建立情感连接，探索情感陪伴商业模式

### 1.3 目标用户

- 需要情感陪伴的都市人群
- 工作压力大、生活节奏快的年轻人
- 希望被记住、被关心的用户

---

## 二、产品架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                          用户层                              │
│                    (对话交互 / 接收提醒)                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      陪聊层 (Layer 1)                        │
│  - 轻目的对话生成                                            │
│  - 行为标签提取                                              │
│  - 情绪识别                                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 关键时刻识别引擎 (Layer 2)                   │
│  - 规则层: 实时关键词匹配                                    │
│  - LLM层: 周期性深度分析                                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 关键时刻存储系统 (Layer 3)                   │
│  - 结构化存储                                                │
│  - 去重逻辑                                                  │
│  - 状态管理                                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   兑现调度引擎 (Layer 4)                     │
│  - 时间调度                                                  │
│  - 触达内容生成                                              │
│  - 多渠道触达                                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户对话
  → 陪聊层(生成回复 + 提取行为/情绪标签)
  → 关键时刻识别(规则判断 + LLM判断)
  → 结构化存储(Moment记录)
  → 调度引擎(定时轮询)
  → 触达用户(消息/电话)
```

---

## 三、功能模块详细设计

### 3.1 陪聊层 (Chat Layer)

#### 3.1.1 功能目标

- 提供自然、有温度的对话体验
- 在对话中无感采集用户行为数据
- 实时识别用户情绪状态

#### 3.1.2 输入输出

**输入**:
```json
{
  "user_id": "uuid",
  "conversation_id": "uuid",
  "message": "明天早上8点有个重要会议，好紧张啊"
}
```

**输出**:
```json
{
  "chat_response": "理解你的紧张，重要会议确实会让人有压力。你准备得怎么样了？需要我帮你梳理一下要点吗？",
  "behavior_tags": ["meeting", "work", "future_event"],
  "emotion_tags": ["nervous", "anxious"],
  "emotion_level": 4,
  "potential_moment": true,
  "extracted_info": {
    "time": "明天早上8点",
    "event": "重要会议",
    "emotion": "紧张"
  }
}
```

#### 3.1.3 技术实现

- **对话生成**: 使用 LLM (DeepSeek/GPT) 生成自然回复
- **标签提取**: 通过 Prompt Engineering 让 LLM 同时输出标签
- **情绪识别**: 基于情绪词典 + LLM 判断，输出 0-5 级情绪强度

#### 3.1.4 Prompt 设计

```
你是一个温暖、善解人意的陪伴者。在对话中：
1. 给出自然、有温度的回复
2. 识别用户的行为标签（如：meeting, travel, date等）
3. 识别用户的情绪标签（如：happy, nervous, sad等）
4. 评估情绪强度（0-5级）
5. 判断是否包含值得记录的关键时刻

输出格式：JSON
```

---

### 3.2 关键时刻识别引擎 (Moment Detection Engine)

#### 3.2.1 功能目标

- 准确识别用户生活中的关键时刻
- 避免重复记录
- 区分关键时刻类型和重要程度

#### 3.2.2 双层识别机制

##### **规则层 (Rule-based Layer)**

**触发条件**: 每轮对话都执行

**规则集**:
1. **时间词检测**: 明天、下周、3点、周五等
2. **事件词检测**: 会议、面试、约会、考试、生日等
3. **情绪词检测**: 紧张、开心、难过、期待等
4. **未来导向表达**: "要去"、"准备"、"打算"等

**处理逻辑**:
```python
if 检测到时间词 AND (事件词 OR 强情绪词):
    提取最近10轮对话上下文
    → 送入 LLM 层进行深度判断
```

##### **LLM层 (LLM-based Layer)**

**触发条件**:
- 规则层触发时立即执行
- 每隔 N 轮对话（N=5）周期性执行

**输入**:
```json
{
  "recent_messages": [最近10轮对话],
  "user_profile": {用户画像},
  "existing_moments": [已记录的关键时刻]
}
```

**输出**:
```json
{
  "is_moment": true,
  "type": "event",  // event / habit / emotion
  "time": "2026-01-15 08:00:00",
  "event_description": "重要工作会议",
  "emotion": "nervous",
  "importance": "high",  // low / mid / high
  "suggested_action": "call",  // call / message
  "suggested_timing": "before_event",  // before_event / after_event / on_time
  "reason": "用户表达了对明天会议的紧张情绪，这是一个值得关心的关键时刻",
  "first_message": "明天早上的会议快到了，准备好了吗？相信你一定可以的！"
}
```

#### 3.2.3 去重逻辑

**场景**: 用户多次提到同一事件

**策略**:
1. 检查已存储的 Moment 中是否有相似事件（时间±2小时 + 事件相似度>0.8）
2. 如果存在，更新现有 Moment 而非创建新记录
3. 更新内容：情绪强度、重要程度、最新上下文

#### 3.2.4 关键时刻类型

| 类型 | 说明 | 示例 |
|------|------|------|
| **event** | 具体事件 | 会议、面试、约会、考试 |
| **habit** | 习惯养成 | 每天跑步、戒烟、早睡 |
| **emotion** | 情绪关怀 | 失恋、压力大、焦虑 |

---

### 3.3 关键时刻存储系统 (Moment Storage)

#### 3.3.1 数据模型

**Moment 表结构**:

```python
class Moment:
    # 基础信息
    moment_id: str          # UUID
    user_id: str            # 用户ID
    conversation_id: str    # 来源会话ID

    # 时间信息
    event_time: datetime    # 事件发生时间
    remind_time: datetime   # 提醒时间（根据策略计算）
    created_at: datetime    # 记录创建时间
    updated_at: datetime    # 最后更新时间

    # 事件信息
    type: str              # event / habit / emotion
    event_description: str # 事件描述
    emotion: str           # 情绪标签
    emotion_level: int     # 情绪强度 0-5
    importance: str        # low / mid / high

    # 兑现信息
    suggested_action: str  # call / message
    first_message: str     # 触达时的第一句话
    ai_attitude: str       # AI的态度（鼓励/安慰/祝贺等）

    # 状态管理
    status: str            # pending / scheduled / completed / cancelled
    confirmed: bool        # 用户是否确认
    executed_at: datetime  # 实际执行时间

    # 上下文
    context_messages: JSON # 相关对话上下文（最近10轮）
```

#### 3.3.2 索引设计

```sql
-- 用户维度查询
INDEX idx_user_time ON moments(user_id, event_time)

-- 调度查询
INDEX idx_remind_status ON moments(remind_time, status)

-- 去重查询
INDEX idx_user_event_time ON moments(user_id, event_time, type)
```

#### 3.3.3 状态流转

```
pending (待确认)
  ↓
scheduled (已调度)
  ↓
completed (已完成)

或

cancelled (已取消)
```

---

### 3.4 兑现调度引擎 (Fulfillment Scheduler)

#### 3.4.1 功能目标

- 在合适的时间触达用户
- 生成个性化的触达内容
- 支持多渠道触达

#### 3.4.2 调度策略

**提醒时机计算**:

| 事件类型 | 重要程度 | 提醒时机 |
|---------|---------|---------|
| event | high | 事件前30分钟 |
| event | mid | 事件前1小时 |
| event | low | 事件前2小时 |
| habit | - | 每天固定时间 |
| emotion | high | 立即 + 次日回访 |
| emotion | mid | 次日回访 |

**调度流程**:

```python
# 后台定时任务（每分钟执行）
def schedule_task():
    # 1. 查询即将到期的 Moment
    moments = query_pending_moments(
        remind_time <= now + 5分钟,
        status = 'scheduled'
    )

    # 2. 生成触达内容
    for moment in moments:
        content = generate_fulfillment_content(moment)

        # 3. 执行触达
        if moment.suggested_action == 'call':
            initiate_call(moment.user_id, content)
        else:
            send_message(moment.user_id, content)

        # 4. 更新状态
        update_moment_status(moment.id, 'completed')
```

#### 3.4.3 触达内容生成

**输入**:
```json
{
  "moment": {Moment对象},
  "user_profile": {用户画像},
  "recent_interaction": {最近交互记录}
}
```

**Prompt 设计**:
```
基于以下信息，生成一条温暖、自然的提醒消息：

关键时刻：{event_description}
时间：{event_time}
用户情绪：{emotion}
AI态度：{ai_attitude}
上下文：{context_messages}

要求：
1. 语气自然、有温度
2. 体现对用户的关心
3. 适当给予鼓励或安慰
4. 长度控制在50字以内
```

**输出示例**:
```
"明天早上的会议快到了，准备好了吗？相信你一定可以的！加油💪"
```

#### 3.4.4 多渠道触达

**消息触达**:
- 应用内推送
- 短信（可选）
- 微信（未来）

**电话触达**:
- AI 语音通话
- 播放预生成的关心内容
- 支持简单的语音交互

---

## 四、技术实现方案

### 4.1 技术栈

**后端**:
- FastAPI (Python)
- MongoDB (对话存储)
- PostgreSQL (关键时刻存储)
- Redis (缓存 + 任务队列)
- Celery (定时任务)

**AI 能力**:
- LLM: DeepSeek / GPT-4
- NLP: 情绪识别、实体提取
- 时间解析: dateparser

**基础设施**:
- Docker
- Nginx
- 监控: Prometheus + Grafana

### 4.2 API 设计

#### 4.2.1 陪聊接口

```http
POST /api/chat
Content-Type: application/json

{
  "user_id": "uuid",
  "conversation_id": "uuid",
  "message": "明天早上8点有个重要会议"
}

Response:
{
  "chat_response": "...",
  "behavior_tags": ["meeting"],
  "emotion_tags": ["nervous"],
  "emotion_level": 4,
  "potential_moment": true
}
```

#### 4.2.2 关键时刻管理

```http
# 获取用户的关键时刻列表
GET /api/moments?user_id={user_id}&status=pending

# 确认关键时刻
POST /api/moments/{moment_id}/confirm

# 取消关键时刻
POST /api/moments/{moment_id}/cancel

# 手动创建关键时刻
POST /api/moments
{
  "user_id": "uuid",
  "type": "event",
  "event_time": "2026-01-15 08:00:00",
  "event_description": "重要会议",
  "importance": "high"
}
```

### 4.3 数据库设计

#### 4.3.1 MongoDB (对话存储)

```javascript
// conversations 集合
{
  conversation_id: "uuid",
  user_id: "uuid",
  agent_id: "uuid",
  created_at: ISODate,
  updated_at: ISODate
}

// messages 集合
{
  message_id: "uuid",
  conversation_id: "uuid",
  role: "user/assistant",
  content: "...",
  metadata: {
    behavior_tags: ["meeting"],
    emotion_tags: ["nervous"],
    emotion_level: 4,
    potential_moment: true
  },
  created_at: ISODate
}
```

#### 4.3.2 PostgreSQL (关键时刻存储)

```sql
CREATE TABLE moments (
    moment_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    conversation_id UUID,

    -- 时间
    event_time TIMESTAMP NOT NULL,
    remind_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- 事件
    type VARCHAR(20) NOT NULL,  -- event/habit/emotion
    event_description TEXT NOT NULL,
    emotion VARCHAR(50),
    emotion_level INT CHECK (emotion_level BETWEEN 0 AND 5),
    importance VARCHAR(10) CHECK (importance IN ('low', 'mid', 'high')),

    -- 兑现
    suggested_action VARCHAR(20) CHECK (suggested_action IN ('call', 'message')),
    first_message TEXT,
    ai_attitude VARCHAR(50),

    -- 状态
    status VARCHAR(20) DEFAULT 'pending',
    confirmed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,

    -- 上下文
    context_messages JSONB,

    INDEX idx_user_time (user_id, event_time),
    INDEX idx_remind_status (remind_time, status)
);
```

### 4.4 关键算法

#### 4.4.1 时间解析算法

```python
def parse_time_expression(text: str, reference_time: datetime) -> datetime:
    """
    解析自然语言时间表达

    示例：
    - "明天早上8点" → 2026-01-15 08:00:00
    - "下周五下午3点" → 2026-01-19 15:00:00
    - "3天后" → 2026-01-17 00:00:00
    """
    # 使用 dateparser 库 + 自定义规则
    pass
```

#### 4.4.2 事件相似度计算

```python
def calculate_similarity(moment1: Moment, moment2: Moment) -> float:
    """
    计算两个关键时刻的相似度（用于去重）

    考虑因素：
    - 时间差（±2小时内）
    - 事件描述相似度（余弦相似度）
    - 情绪标签重合度
    """
    time_score = calculate_time_similarity(moment1.event_time, moment2.event_time)
    text_score = calculate_text_similarity(moment1.event_description, moment2.event_description)
    emotion_score = calculate_emotion_similarity(moment1.emotion, moment2.emotion)

    return 0.5 * time_score + 0.3 * text_score + 0.2 * emotion_score
```

---

## 五、开发计划

### 5.1 迭代规划

#### **Phase 1: MVP (2周)**

**目标**: 完成陪聊逻辑闭环

**功能范围**:
- ✅ 基础陪聊对话
- ✅ 行为标签提取
- ✅ 情绪识别
- ✅ 对话历史存储

**技术债务**:
- 暂不实现关键时刻识别
- 暂不实现兑现调度
- 暂不实现语音识别

#### **Phase 2: 关键时刻识别 (2周)**

**功能范围**:
- 规则层实现（关键词匹配）
- LLM层实现（深度分析）
- 关键时刻存储
- 去重逻辑

**验收标准**:
- 能准确识别80%的明确事件（如"明天8点开会"）
- 误报率<10%

#### **Phase 3: 兑现调度 (2周)**

**功能范围**:
- 调度引擎实现
- 触达内容生成
- 消息推送
- 状态管理

**验收标准**:
- 提醒准时率>95%
- 触达内容自然度评分>4/5

#### **Phase 4: 优化与扩展 (持续)**

**功能范围**:
- 电话触达
- 用户画像
- 个性化推荐
- 数据分析

### 5.2 开发优先级

| 优先级 | 功能模块 | 预计工期 |
|--------|---------|---------|
| P0 | 陪聊层基础功能 | 1周 |
| P0 | 对话存储 | 3天 |
| P1 | 规则层识别 | 1周 |
| P1 | LLM层识别 | 1周 |
| P1 | 关键时刻存储 | 3天 |
| P2 | 调度引擎 | 1周 |
| P2 | 消息触达 | 3天 |
| P3 | 电话触达 | 2周 |
| P3 | 用户画像 | 持续 |

---

## 六、核心指标

### 6.1 产品指标

| 指标 | 定义 | 目标值 |
|------|------|--------|
| **识别准确率** | 正确识别的关键时刻 / 总关键时刻 | >80% |
| **误报率** | 错误识别的关键时刻 / 总识别数 | <10% |
| **触达准时率** | 准时触达的次数 / 总触达次数 | >95% |
| **用户满意度** | 用户对触达内容的满意度评分 | >4/5 |
| **日活跃用户** | 每日活跃对话的用户数 | 持续增长 |

### 6.2 技术指标

| 指标 | 定义 | 目标值 |
|------|------|--------|
| **对话响应时间** | P95 响应时间 | <2s |
| **识别延迟** | 从对话到识别完成的时间 | <5s |
| **调度精度** | 实际触达时间与计划时间的偏差 | <1min |
| **系统可用性** | 服务正常运行时间占比 | >99.9% |

---

## 七、风险与挑战

### 7.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **LLM识别不准确** | 误报/漏报关键时刻 | 规则层兜底 + 持续优化Prompt |
| **时间解析错误** | 提醒时间不准确 | 多轮确认 + 用户手动修正 |
| **并发性能问题** | 高峰期响应慢 | 异步处理 + 缓存优化 |
| **调度延迟** | 提醒不及时 | 分布式调度 + 监控告警 |

### 7.2 产品风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **用户隐私担忧** | 用户不愿分享信息 | 明确隐私政策 + 数据加密 |
| **触达频率过高** | 用户反感 | 智能频控 + 用户自定义 |
| **内容不够个性化** | 用户体验差 | 持续优化用户画像 |

---

## 八、未来规划

### 8.1 短期规划 (3个月)

- [ ] 完成 MVP 并上线测试
- [ ] 完成关键时刻识别引擎
- [ ] 完成基础兑现调度
- [ ] 积累 1000+ 真实对话数据

### 8.2 中期规划 (6个月)

- [ ] 支持电话触达
- [ ] 支持语音对话
- [ ] 建立用户画像系统
- [ ] 优化识别准确率至 90%+

### 8.3 长期规划 (1年)

- [ ] 多模态交互（文字+语音+图片）
- [ ] 主动关怀（不依赖用户触发）
- [ ] 情感陪伴生态（接入第三方服务）
- [ ] 商业化探索

---

## 九、附录

### 9.1 术语表

| 术语 | 定义 |
|------|------|
| **关键时刻** | 用户生活中值得被记住和关心的时刻 |
| **情绪兑现** | 在合适的时间给予用户情感上的回应和支持 |
| **轻目的陪聊** | 不带明确任务目标的自然对话 |
| **规则层** | 基于关键词和规则的快速识别 |
| **LLM层** | 基于大模型的深度语义理解 |

### 9.2 参考资料

- [OpenAI API 文档](https://platform.openai.com/docs)
- [DeepSeek API 文档](https://platform.deepseek.com/docs)
- [dateparser 文档](https://dateparser.readthedocs.io/)

### 9.3 变更记录

| 版本 | 日期 | 变更内容 | 负责人 |
|------|------|---------|--------|
| v1.0 | 2026-01-14 | 初始版本 | 张昭 |

---

**文档结束**

如有疑问或建议，请联系产品负责人。
