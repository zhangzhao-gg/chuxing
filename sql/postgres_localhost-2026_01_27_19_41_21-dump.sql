--
-- PostgreSQL database dump
--

\restrict L8krfw2hXCFhRvmci8tRGOhBWblSeTsGpAtWN3L6BEPItKTNOSgkXONvkFhukA8

-- Dumped from database version 18.1
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP DATABASE IF EXISTS llm_chat;
--
-- Name: llm_chat; Type: DATABASE; Schema: -; Owner: postgres
--

CREATE DATABASE llm_chat WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'Chinese (Simplified)_China.936';


ALTER DATABASE llm_chat OWNER TO postgres;

\unrestrict L8krfw2hXCFhRvmci8tRGOhBWblSeTsGpAtWN3L6BEPItKTNOSgkXONvkFhukA8
\connect llm_chat
\restrict L8krfw2hXCFhRvmci8tRGOhBWblSeTsGpAtWN3L6BEPItKTNOSgkXONvkFhukA8

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: moments; Type: TABLE; Schema: public; Owner: ASUS
--

CREATE TABLE public.moments (
    moment_id text NOT NULL,
    user_id text NOT NULL,
    conversation_id text,
    event_time timestamp with time zone NOT NULL,
    remind_time timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    type text NOT NULL,
    event_description text NOT NULL,
    emotion text,
    emotion_level integer,
    importance text NOT NULL,
    suggested_action text NOT NULL,
    first_message text,
    ai_attitude text,
    status text NOT NULL,
    confirmed boolean DEFAULT false NOT NULL,
    executed_at timestamp with time zone,
    context_messages jsonb,
    suggested_timing text,
    reason text
);


ALTER TABLE public.moments OWNER TO "ASUS";

--
-- Data for Name: moments; Type: TABLE DATA; Schema: public; Owner: ASUS
--

COPY public.moments (moment_id, user_id, conversation_id, event_time, remind_time, created_at, updated_at, type, event_description, emotion, emotion_level, importance, suggested_action, first_message, ai_attitude, status, confirmed, executed_at, context_messages, suggested_timing, reason) FROM stdin;
smoke-9d5c03b6d1a2	test-user	\N	2026-01-26 21:18:25.550158+08	2026-01-26 20:18:25.550158+08	2026-01-26 19:18:25.550158+08	2026-01-26 19:18:25.550158+08	event	pg smoke test: meeting in 2 hours	nervous	3	high	message	you got this	support	pending	f	\N	[{"role": "user", "content": "meeting soon, a bit nervous"}]	\N	\N
smoke-13b6ab22d278	test-user	\N	2026-01-26 21:18:55.769407+08	2026-01-26 20:18:55.769407+08	2026-01-26 19:18:55.769407+08	2026-01-26 19:18:55.769407+08	event	pg smoke test: meeting in 2 hours	nervous	3	high	message	you got this	support	pending	f	\N	[{"role": "user", "content": "meeting soon, a bit nervous"}]	\N	\N
smoke-2498cbd30dc8	test-user	\N	2026-01-26 21:21:40.837331+08	2026-01-26 20:21:40.837331+08	2026-01-26 19:21:40.837331+08	2026-01-26 19:21:40.842493+08	event	pg smoke test: important meeting in 2 hours	nervous	3	high	message	you got this	support	scheduled	t	\N	[{"role": "user", "content": "meeting soon, a bit nervous"}, {"role": "assistant", "content": "totally normal. let's prepare together."}]	\N	\N
0f815355-409b-4fc7-b11e-12b8646bdf96	04324648-a8f1-456c-9008-627fbd3e8845	02942338-ec96-460b-a27e-e82461c2586a	2026-01-27 19:31:45.060633+08	2026-01-28 19:31:45.060633+08	2026-01-26 11:31:45.210436+08	2026-01-26 11:31:45.210436+08	emotion	上班	exhausted	4	mid	message	早上好，想到今天要上班，是不是还觉得有点累？先深呼吸一下，我在这里陪着你。	安慰	pending	f	\N	[{"role": "user", "content": "明天不想上班，心好累"}, {"role": "assistant", "content": "听起来你今天真的感到疲惫和无力呢。工作压力大确实会让人感到心力交瘁，尤其是想到明天还要继续面对。或许可以试着给自己一点小小的奖励，比如下班后做一件喜欢的事，或者今晚好好休息一下。你愿意和我聊聊具体是什么让你感到这么累吗？"}]	\N	\N
fe7e09b2-2e52-45bb-97bb-45e5b8c4a70a	e7538e4c-bf3a-4c2b-a0ef-6b03bc377a34	133aebb8-e0d6-41e5-a5e2-387cb9ea60ec	2026-01-27 09:41:34.097997+08	2026-01-27 08:41:34.097997+08	2026-01-26 12:41:34.108402+08	2026-01-26 12:41:34.108402+08	event	上班	tired	4	mid	message	早上好！新的一天开始了，我知道你可能还是觉得累，但先深呼吸，给自己一点小鼓励吧。	鼓励	pending	f	\N	[{"role": "user", "content": "明天九点又要上班，完全没有动力，好累啊！"}, {"role": "assistant", "content": "听起来你真的好疲惫，感觉被工作压得喘不过气来。这种重复的日常确实容易让人失去动力，尤其是想到明天一早又要开始。要不要今晚先好好放松一下，泡个热水澡或者听点舒缓的音乐？给自己一点喘息的空间，也许明天会感觉稍微轻松一些。"}]	before_event	用户明确提到未来时间点（明天九点）和事件（上班），并表达了强烈的负面情绪（累、没动力），属于需要情绪支持的关键时刻。
6202185a-884b-4a6a-ab94-261830fc1c81	e7538e4c-bf3a-4c2b-a0ef-6b03bc377a34	bc4d3b52-33b9-4f2a-af5e-2d6b98ad8aad	2026-01-28 09:29:41.537022+08	2026-01-28 08:29:41.537022+08	2026-01-27 01:29:41.674506+08	2026-01-27 01:29:41.674506+08	event	考研结束后计划出去玩	relieved	4	mid	message	明天出去玩准备得怎么样啦？记得好好享受考后的放松时光哦！	祝贺与鼓励	pending	f	\N	[{"role": "user", "content": "考研结束了，明天想出去玩。"}, {"role": "assistant", "content": "恭喜你完成了考研！这确实是一个值得庆祝的时刻。明天出去玩是个很棒的主意，好好放松一下，享受属于你的自由时光吧！"}]	before_event	用户明确提到了未来时间点（明天）和具体事件（出去玩），且处于考研结束后的情绪释放阶段，属于值得关注的时刻。
\.


--
-- Name: moments moments_pkey; Type: CONSTRAINT; Schema: public; Owner: ASUS
--

ALTER TABLE ONLY public.moments
    ADD CONSTRAINT moments_pkey PRIMARY KEY (moment_id);


--
-- Name: idx_moments_remind_status; Type: INDEX; Schema: public; Owner: ASUS
--

CREATE INDEX idx_moments_remind_status ON public.moments USING btree (remind_time, status);


--
-- Name: idx_moments_user_event; Type: INDEX; Schema: public; Owner: ASUS
--

CREATE INDEX idx_moments_user_event ON public.moments USING btree (user_id, event_time);


--
-- Name: idx_moments_user_event_type; Type: INDEX; Schema: public; Owner: ASUS
--

CREATE INDEX idx_moments_user_event_type ON public.moments USING btree (user_id, event_time, type);


--
-- PostgreSQL database dump complete
--

\unrestrict L8krfw2hXCFhRvmci8tRGOhBWblSeTsGpAtWN3L6BEPItKTNOSgkXONvkFhukA8

