# Moment 兑现（到点发消息）端到端测试报告

- run_id: `20260212_101929`
- started_at_utc: `2026-02-12T02:19:29.492617+00:00`
- api_url: `http://localhost:8000`
- timeout_seconds: **30.0**

## 资源创建

- user_id: `15fb1fea-bea0-4a4b-b5ab-c546ddbc65fa` (username `delivery_test_20260212_101929`)
- agent_id: `d363f494-8646-4161-ad88-2ba773fbafe6` (model `gpt-4o-mini`)
- conversation_id: `9e8b9e2d-eb78-4612-a146-5c614ae034bd`

## Moment 创建与确认

- moment_id: `0ecc72f1-aa33-4965-a673-d3dbde870f58`
- event_time: `2026-02-12T02:20:29.492617Z`
- remind_time: `2026-02-12T01:50:29.492617Z`
- confirmed(initial): **False**
- status(initial): **1**
- first_message: `[DELIVERY_TEST 20260212_101929] 到点了：我来兑现一下，看看你现在状态如何？`

- confirmed(after confirm): **True**
- status(after confirm): **1**

## 兑现验证（messages / moment 状态）

- checked_at_utc: `2026-02-12T02:19:32.074332+00:00`
- result: **PASS**（已看到 worker 写入的 assistant 消息）
- delivered_message_id: `1df15da2-b150-4cd5-9747-c0eceafac251`
- delivered_message_created_at: `2026-02-12T02:19:31.720000`

### Moment 最终状态

- status(final): **2**（期望 2=completed）
- executed_at(final): `2026-02-12T02:19:31.720699Z`（期望非空）

- assertion: **PASS**