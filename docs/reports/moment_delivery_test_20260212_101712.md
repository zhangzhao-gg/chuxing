# Moment 兑现（到点发消息）端到端测试报告

- run_id: `20260212_101712`
- started_at_utc: `2026-02-12T02:17:12.830960+00:00`
- api_url: `http://localhost:8000`
- timeout_seconds: **30.0**

## 资源创建

- user_id: `67cc28db-d49e-407b-add1-651ace8fe1a2` (username `delivery_test_20260212_101712`)
- agent_id: `4ca3bb94-be7e-4e28-b823-65789719b97c` (model `gpt-4o-mini`)
- conversation_id: `889be6af-1e24-4a06-801e-ba73c05b9401`

## Moment 创建与确认

- moment_id: `d8296abd-93e0-49c8-bd47-b42bd72ff50f`
- event_time: `2026-02-12T02:18:12.830960Z`
- remind_time: `2026-02-12T01:48:12.830960Z`
- confirmed(initial): **False**
- status(initial): **1**
- first_message: `[DELIVERY_TEST 20260212_101712] 到点了：我来兑现一下，看看你现在状态如何？`

- confirmed(after confirm): **True**
- status(after confirm): **1**

## 兑现验证（messages / moment 状态）

- checked_at_utc: `2026-02-12T02:17:45.497943+00:00`
- result: **FAIL**（超时未看到 worker 写入的 assistant 消息）

### 最近 messages（最多 10 条）

| # | role | created_at | content |
|---:|---|---|---|