# Moment 兑现（到点发消息）端到端测试报告

- run_id: `20260212_105358`
- started_at_utc: `2026-02-12T02:53:58.599794+00:00`
- started_at_bj: `2026-02-12T10:53:58.599794+08:00`
- api_url: `http://localhost:8000`
- timeout_seconds: **30.0**

## 资源创建

- user_id: `3d8f85f9-7589-4c2c-87d8-ad2ac50238d6` (username `delivery_test_20260212_105358`)
- agent_id: `2fcb52e3-65c9-437e-8017-3582bb754e93` (model `gpt-4o-mini`)
- conversation_id: `b245780a-9748-4a83-8f62-8d77970cf3e7`

## Moment 创建与确认

- moment_id: `13b77a06-58a6-46cd-a11b-4b37a60458c4`
- event_time: `2026-02-12T02:54:58.599794Z`
- event_time_bj: `2026-02-12T10:54:58.599794+08:00`
- remind_time: `2026-02-12T02:24:58.599794Z`
- remind_time_bj: `2026-02-12T10:24:58.599794+08:00`
- confirmed(initial): **False**
- status(initial): **1**
- first_message: `[DELIVERY_TEST 20260212_105358] 到点了：我来兑现一下，看看你现在状态如何？`

- confirmed(after confirm): **True**
- status(after confirm): **1**

## 兑现验证（messages / moment 状态）

- checked_at_utc: `2026-02-12T02:54:02.196002+00:00`
- checked_at_bj: `2026-02-12T10:54:02.196002+08:00`
- result: **PASS**（已看到 worker 写入的 assistant 消息）
- delivered_message_id: `716179c7-f936-466f-8715-a0ac2f621504`
- delivered_message_created_at: `2026-02-12T02:54:01.694000`
- delivered_message_created_at_bj: `2026-02-12T10:54:01.694000+08:00`

### Moment 最终状态

- status(final): **2**（期望 2=completed）
- executed_at(final): `2026-02-12T02:54:01.694239Z`（期望非空）
- executed_at(final)_bj: `2026-02-12T10:54:01.694239+08:00`

- assertion: **PASS**