# backend/tests/
> L2 | 父级: backend/CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**__init__.py**: 标记 tests 为包，便于 unittest 发现与导入

**e2e_suite.py**: **独立 E2E 测试套件**（合并 cli/commands 三个测试脚本），内置 HTTP 客户端，脱离 cli.client 依赖。包含三个测试命令：
- `test-delivery`：Moment 兑现链路验证（创建→确认→worker 到点发消息→completed）
- `test-conversation`：马拉松备赛 20 轮对话→LLM 识别 10+ 关键时刻→确认→兑现
- `test-full-lifecycle`：全生命周期（15+5 轮对话→识别 12+ moment→取消/修改→确认→兑现→评估）
- `test-all`：依次运行全部三个测试

运行方式：`uv run python -m backend.tests.e2e_suite test-all`

**test_moment_dedup_50_rounds.py**: 对话链路回归测试（>=50轮、同一话题、情绪大起大落），验证 open_moments 注入 + LLM 去重（重复则 moment=null）+ moment_updates 状态迁移

**moment_dedup_50_rounds_report.md**: （测试运行时生成）保存 55 轮对话过程 + 关键时刻识别/查重/状态更新过程的完整报告

**test_cli_chat_dedup_report.py**: CLI 逐条对话回归测试（模拟人类在 `cli chat start` 中逐条输入，>=50轮），验证查重与状态更新，并生成单文件报告

**cli_chat_dedup_55_turns_report.md**: （测试运行时生成）保存 CLI 逐条对话过程 + 关键时刻识别/查重/状态更新的单文件报告（写入 backend/tests）

**test_cli_chat_real_db_moments_report.py**: CLI 逐条对话"真落库"回归测试（moments 写入 PostgreSQL），要求 DB 中 moments>=10 且 >=5 个发生状态变更，并生成单文件报告

**cli_chat_real_db_moments_report.md**: （测试运行时生成）保存 CLI 逐条对话过程 + 关键时刻识别/查重过程 + PostgreSQL 快照（moments>=10，状态变更>=5）

---

## 设计原则

**不依赖真实外部系统**: 使用依赖覆盖注入 FakeLLM/FakeRepository，避免连接 MongoDB/PostgreSQL/OpenAI

**围绕 Router 数据流**: 直接打 `/api/conversations/{conv_id}/chat`，覆盖"注入 open_moments → LLM 输出 → 状态更新 →（可选）创建 moment"的关键路径

**E2E 套件独立**: `e2e_suite.py` 内置 APIClient，不依赖 cli 包，可独立运行

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
