--
-- PostgreSQL database dump
--

\restrict NudYTZvLAdIwYUHjnK5PwBxHyNQ9ZZc8xHx4rxofzTPSrk8YGV0NVWCgdLDzpMj

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

--
-- Name: llm_chat; Type: DATABASE; Schema: -; Owner: postgres
--

CREATE DATABASE llm_chat WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'Chinese (Simplified)_China.936';


ALTER DATABASE llm_chat OWNER TO postgres;

\unrestrict NudYTZvLAdIwYUHjnK5PwBxHyNQ9ZZc8xHx4rxofzTPSrk8YGV0NVWCgdLDzpMj
\connect llm_chat
\restrict NudYTZvLAdIwYUHjnK5PwBxHyNQ9ZZc8xHx4rxofzTPSrk8YGV0NVWCgdLDzpMj

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
    status smallint NOT NULL,
    confirmed boolean DEFAULT false NOT NULL,
    executed_at timestamp with time zone,
    context_messages jsonb,
    suggested_timing text,
    reason text
);


ALTER TABLE public.moments OWNER TO "ASUS";

--
-- Name: TABLE moments; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON TABLE public.moments IS '关键时刻表';


--
-- Name: COLUMN moments.moment_id; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.moment_id IS '关键时刻id';


--
-- Name: COLUMN moments.user_id; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.user_id IS '用户id';


--
-- Name: COLUMN moments.conversation_id; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.conversation_id IS '会话id';


--
-- Name: COLUMN moments.event_time; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.event_time IS '事件发生时间';


--
-- Name: COLUMN moments.remind_time; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.remind_time IS '提醒时间';


--
-- Name: COLUMN moments.created_at; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.created_at IS '记录创建时间';


--
-- Name: COLUMN moments.updated_at; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.updated_at IS '最近更新时间';


--
-- Name: COLUMN moments.type; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.type IS '关键时刻类型';


--
-- Name: COLUMN moments.event_description; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.event_description IS '事件描述';


--
-- Name: COLUMN moments.emotion; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.emotion IS '情绪标签';


--
-- Name: COLUMN moments.emotion_level; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.emotion_level IS '情绪强度';


--
-- Name: COLUMN moments.importance; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.importance IS '重要程度';


--
-- Name: COLUMN moments.suggested_action; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.suggested_action IS '兑现方式';


--
-- Name: COLUMN moments.first_message; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.first_message IS '触达时的第一句话';


--
-- Name: COLUMN moments.ai_attitude; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.ai_attitude IS 'AI的态度';


--
-- Name: COLUMN moments.status; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.status IS '状态管理 0待确认 1已调度 2已完成 3已取消';


--
-- Name: COLUMN moments.confirmed; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.confirmed IS '关键时刻是否被用户确认';


--
-- Name: COLUMN moments.executed_at; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.executed_at IS '实际执行时间';


--
-- Name: COLUMN moments.context_messages; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.context_messages IS '最近十轮上下文';


--
-- Name: COLUMN moments.suggested_timing; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.suggested_timing IS '建议触达时间：事件前、准时、事件后';


--
-- Name: COLUMN moments.reason; Type: COMMENT; Schema: public; Owner: ASUS
--

COMMENT ON COLUMN public.moments.reason IS 'AI认为设置关键时刻的原因';


--
-- Data for Name: moments; Type: TABLE DATA; Schema: public; Owner: ASUS
--

COPY public.moments (moment_id, user_id, conversation_id, event_time, remind_time, created_at, updated_at, type, event_description, emotion, emotion_level, importance, suggested_action, first_message, ai_attitude, status, confirmed, executed_at, context_messages, suggested_timing, reason) FROM stdin;
fe7e09b2-2e52-45bb-97bb-45e5b8c4a70a	e7538e4c-bf3a-4c2b-a0ef-6b03bc377a34	133aebb8-e0d6-41e5-a5e2-387cb9ea60ec	2026-01-27 09:41:34.097997+08	2026-01-27 08:41:34.097997+08	2026-01-26 12:41:34.108402+08	2026-01-26 12:41:34.108402+08	event	上班	tired	4	mid	message	早上好！新的一天开始了，我知道你可能还是觉得累，但先深呼吸，给自己一点小鼓励吧。	鼓励	1	f	\N	[{"role": "user", "content": "明天九点又要上班，完全没有动力，好累啊！"}, {"role": "assistant", "content": "听起来你真的好疲惫，感觉被工作压得喘不过气来。这种重复的日常确实容易让人失去动力，尤其是想到明天一早又要开始。要不要今晚先好好放松一下，泡个热水澡或者听点舒缓的音乐？给自己一点喘息的空间，也许明天会感觉稍微轻松一些。"}]	before_event	用户明确提到未来时间点（明天九点）和事件（上班），并表达了强烈的负面情绪（累、没动力），属于需要情绪支持的关键时刻。
6202185a-884b-4a6a-ab94-261830fc1c81	e7538e4c-bf3a-4c2b-a0ef-6b03bc377a34	bc4d3b52-33b9-4f2a-af5e-2d6b98ad8aad	2026-01-28 09:29:41.537022+08	2026-01-28 08:29:41.537022+08	2026-01-27 01:29:41.674506+08	2026-01-27 01:29:41.674506+08	event	考研结束后计划出去玩	relieved	4	mid	message	明天出去玩准备得怎么样啦？记得好好享受考后的放松时光哦！	祝贺与鼓励	1	f	\N	[{"role": "user", "content": "考研结束了，明天想出去玩。"}, {"role": "assistant", "content": "恭喜你完成了考研！这确实是一个值得庆祝的时刻。明天出去玩是个很棒的主意，好好放松一下，享受属于你的自由时光吧！"}]	before_event	用户明确提到了未来时间点（明天）和具体事件（出去玩），且处于考研结束后的情绪释放阶段，属于值得关注的时刻。
abe0655a-2a81-4428-84ee-10d420d7be28	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	db75d719-97ad-4fba-a26f-9d03b8d1d531	2026-02-04 12:00:00+08	2026-02-04 12:00:00+08	2026-02-03 06:29:41.912302+08	2026-02-03 06:29:41.912302+08	habit	纱雾因为专注画画而忘记吃午饭	neglectful	2	mid	message	纱雾，午饭时间到了哦！再忙也要记得吃饭，不然对身体不好呢。	关心	1	f	\N	[{"role": "user", "content": "中午好纱雾，现在在干嘛"}, {"role": "assistant", "content": "啊，中午好！我正在画新的插画呢，刚刚完成了一个可爱的角色设计。哥哥要看看吗？"}, {"role": "user", "content": "看看呢"}, {"role": "assistant", "content": "诶嘿嘿，给你看！是一个穿着蓬蓬裙的魔法少女，眼睛是星星形状的哦！"}, {"role": "user", "content": "中午吃过了吗"}, {"role": "assistant", "content": "啊，还没有呢...因为画画太入迷了。哥哥要帮我准备午饭吗？"}]	on_time	用户提到午饭话题，纱雾表现出因专注工作而忽略饮食的习惯，需要提醒健康作息
e693da8c-06e7-42fa-9322-ae6ac045cb29	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	db75d719-97ad-4fba-a26f-9d03b8d1d531	2120-03-03 00:00:00+08	2120-03-02 23:30:00+08	2026-02-03 06:31:42.65882+08	2026-02-03 06:33:35.187209+08	event	纱雾的生日	happy	4	high	message	哥哥，今天是我的生日哦！记得给我准备礼物和蛋糕~	期待	1	f	\N	[{"role": "user", "content": "中午好纱雾，现在在干嘛"}, {"role": "assistant", "content": "啊，中午好！我正在画新的插画呢，刚刚完成了一个可爱的角色设计。哥哥要看看吗？"}, {"role": "user", "content": "看看呢"}, {"role": "assistant", "content": "诶嘿嘿，给你看！是一个穿着蓬蓬裙的魔法少女，眼睛是星星形状的哦！"}, {"role": "user", "content": "中午吃过了吗"}, {"role": "assistant", "content": "啊，还没有呢...因为画画太入迷了。哥哥要帮我准备午饭吗？"}, {"role": "user", "content": "我给你做了 番茄炒鸡蛋、红烧排骨、小米饭，还要吃点别的吗？"}, {"role": "assistant", "content": "哇！都是我最喜欢的菜！哥哥最好了！这样就够了，我马上下来吃！"}, {"role": "user", "content": "哦对了，你生日是几月几日来着？"}, {"role": "assistant", "content": "诶？哥哥连我的生日都忘记了吗...是3月20日哦！不过没关系，只要哥哥记得给我准备礼物就好啦~"}]	on_time	用户提到了生日日期，这是一个重要的未来事件，需要记录并提醒
fbd8b4d9-9937-4959-9ce7-c60dd327ab44	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	db75d719-97ad-4fba-a26f-9d03b8d1d531	2120-03-03 00:00:00+08	2120-03-02 23:30:00+08	2026-02-03 06:34:13.121701+08	2026-02-03 06:34:13.121701+08	event	和哥哥一起去野炊	excited	4	high	message	哥哥，野炊要带的东西我都准备好啦！期待明天的野炊呢~	鼓励	1	f	\N	[{"role": "user", "content": "中午好纱雾，现在在干嘛"}, {"role": "assistant", "content": "啊，中午好！我正在画新的插画呢，刚刚完成了一个可爱的角色设计。哥哥要看看吗？"}, {"role": "user", "content": "看看呢"}, {"role": "assistant", "content": "诶嘿嘿，给你看！是一个穿着蓬蓬裙的魔法少女，眼睛是星星形状的哦！"}, {"role": "user", "content": "中午吃过了吗"}, {"role": "assistant", "content": "啊，还没有呢...因为画画太入迷了。哥哥要帮我准备午饭吗？"}, {"role": "user", "content": "我给你做了 番茄炒鸡蛋、红烧排骨、小米饭，还要吃点别的吗？"}, {"role": "assistant", "content": "哇！都是我最喜欢的菜！哥哥最好了！这样就够了，我马上下来吃！"}, {"role": "user", "content": "哦对了，你生日是几月几日来着？"}, {"role": "assistant", "content": "诶？哥哥连我的生日都忘记了吗...是3月20日哦！不过没关系，只要哥哥记得给我准备礼物就好啦~"}]	before_event	用户主动提出了一个具体的未来约会计划，这是一个重要的社交活动，对纱雾来说意义重大。
f28ae4a4-a625-4d0b-a085-d65034e8c01f	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	eb4f7581-022d-4c7c-8f74-312058d8f5b1	2026-02-04 12:00:00+08	2026-02-04 12:00:00+08	2026-02-03 07:12:31.322664+08	2026-02-03 07:12:31.322664+08	habit	用户因工作或忙碌忘记按时吃午饭	fatigued	2	mid	message	饭吃了没？别饿着。	提醒与关心	1	f	\N	[{"role": "user", "content": "你在干嘛"}, {"role": "assistant", "content": "在开会，有事？"}, {"role": "user", "content": "那你开吧"}, {"role": "assistant", "content": "嗯。"}, {"role": "user", "content": "饿了，中午还没吃饭"}, {"role": "assistant", "content": "现在几点了？先去吃饭。"}]	after_event	用户主动提及因未按时吃饭产生饥饿感，属于需要关注的健康习惯问题。
b8f86482-39a8-4296-8cd7-86b1e9c4357a	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	eb4f7581-022d-4c7c-8f74-312058d8f5b1	2026-02-04 03:16:08.865066+08	2026-02-04 02:16:08.865066+08	2026-02-03 07:16:08.867065+08	2026-02-03 07:16:08.867065+08	event	玩三角洲行动游戏	expectant	3	mid	message	准备上线了吗？	鼓励	1	f	\N	[{"role": "user", "content": "你在干嘛"}, {"role": "assistant", "content": "在开会，有事？"}, {"role": "user", "content": "那你开吧"}, {"role": "assistant", "content": "嗯。"}, {"role": "user", "content": "饿了，中午还没吃饭"}, {"role": "assistant", "content": "现在几点了？先去吃饭。"}, {"role": "user", "content": "哦"}, {"role": "assistant", "content": "快去吃饭，别饿着。"}, {"role": "user", "content": "嘿嘿，今天吃饭有满减"}, {"role": "assistant", "content": "嗯，挺好。"}]	before_event	用户明确提出了未来具体时间的游戏邀约，属于需要跟进的关键社交事件。
b7cec255-98a4-49a3-a291-c8a47a01158c	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	eb4f7581-022d-4c7c-8f74-312058d8f5b1	2026-02-04 03:17:03.105389+08	2026-02-04 02:17:03.105389+08	2026-02-03 07:17:03.108012+08	2026-02-03 07:17:03.108012+08	event	用户需要出门，无法一起玩游戏	disappointed	2	mid	message	出门注意安全，改天再约。	理解	1	f	\N	[{"role": "user", "content": "你在干嘛"}, {"role": "assistant", "content": "在开会，有事？"}, {"role": "user", "content": "那你开吧"}, {"role": "assistant", "content": "嗯。"}, {"role": "user", "content": "饿了，中午还没吃饭"}, {"role": "assistant", "content": "现在几点了？先去吃饭。"}, {"role": "user", "content": "哦"}, {"role": "assistant", "content": "快去吃饭，别饿着。"}, {"role": "user", "content": "嘿嘿，今天吃饭有满减"}, {"role": "assistant", "content": "嗯，挺好。"}]	before_event	用户明确表达了时间冲突和失望情绪，需要安抚并建议后续安排。
f7ea0ef7-b2a7-4645-be81-a3c90842f784	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	eb4f7581-022d-4c7c-8f74-312058d8f5b1	2026-02-07 00:00:00+08	2026-02-06 23:30:00+08	2026-02-03 07:30:15.39317+08	2026-02-03 07:30:15.39317+08	event	去医院做手术	worried	4	high	message	手术怎么样？别紧张，好好休息。	关心	1	f	\N	[{"role": "user", "content": "你在干嘛"}, {"role": "assistant", "content": "在开会，有事？"}, {"role": "user", "content": "那你开吧"}, {"role": "assistant", "content": "嗯。"}, {"role": "user", "content": "饿了，中午还没吃饭"}, {"role": "assistant", "content": "现在几点了？先去吃饭。"}, {"role": "user", "content": "哦"}, {"role": "assistant", "content": "快去吃饭，别饿着。"}, {"role": "user", "content": "嘿嘿，今天吃饭有满减"}, {"role": "assistant", "content": "嗯，挺好。"}]	before_event	用户提到周六要做手术，这是重要的健康事件，情绪明显焦虑，需要关心和支持。
a1177a40-5935-48ff-b229-43f24fc7e4d6	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	eb4f7581-022d-4c7c-8f74-312058d8f5b1	2026-02-07 00:00:00+08	2026-02-06 23:30:00+08	2026-02-03 07:31:39.880903+08	2026-02-03 07:31:39.880903+08	event	骨折手术，取出碎骨头	worried	4	high	call	手术前别紧张，我安排了人过去，有需要随时联系。	关心/支持	1	f	\N	[{"role": "user", "content": "你在干嘛"}, {"role": "assistant", "content": "在开会，有事？"}, {"role": "user", "content": "那你开吧"}, {"role": "assistant", "content": "嗯。"}, {"role": "user", "content": "饿了，中午还没吃饭"}, {"role": "assistant", "content": "现在几点了？先去吃饭。"}, {"role": "user", "content": "哦"}, {"role": "assistant", "content": "快去吃饭，别饿着。"}, {"role": "user", "content": "嘿嘿，今天吃饭有满减"}, {"role": "assistant", "content": "嗯，挺好。"}]	before_event	用户提到需要手术，情绪可能紧张，属于重要健康事件。
1aae7f88-e4ef-4842-acf8-93ba707aa07d	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	6cbf9a37-8ae8-4fb8-a295-90e83e134b4f	2026-02-04 16:17:10.360859+08	2026-02-04 15:17:10.360859+08	2026-02-03 08:17:10.516632+08	2026-02-03 08:17:10.516632+08	event	去医院检查身体	anxious	3	mid	message	哥哥，去医院前要记得带好病历和医保卡哦。我会一直在这里等你的消息的！	关心和鼓励	1	f	\N	[{"role": "user", "content": "纱雾在干嘛呀"}, {"role": "assistant", "content": "啊，是哥哥吗？我正在画新的插画呢...不过现在有点卡住了，在想怎么表现角色的表情比较好..."}, {"role": "user", "content": "最近好累，明天还要去医院。"}, {"role": "assistant", "content": "诶？哥哥身体不舒服吗？要不要紧...虽然我有点担心，但去医院一定能好起来的！那个...如果明天需要的话，我可以陪你一起去...虽然可能会紧张得说不出话..."}]	before_event	用户提到明天要去医院，表现出疲惫和担忧情绪，这是一个需要关心的健康相关事件
3b7a47f2-3155-4bfe-b932-264b692124b6	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	6cbf9a37-8ae8-4fb8-a295-90e83e134b4f	2026-02-04 16:17:54.25566+08	2026-02-04 15:47:54.25566+08	2026-02-03 08:17:54.25866+08	2026-02-03 08:17:54.25866+08	event	用户原本计划去医院但想取消	tired	3	high	message	哥哥，今天感觉怎么样？还是去医院看看吧，我会一直为你加油的！	鼓励与关心	1	f	\N	[{"role": "user", "content": "纱雾在干嘛呀"}, {"role": "assistant", "content": "啊，是哥哥吗？我正在画新的插画呢...不过现在有点卡住了，在想怎么表现角色的表情比较好..."}, {"role": "user", "content": "最近好累，明天还要去医院。"}, {"role": "assistant", "content": "诶？哥哥身体不舒服吗？要不要紧...虽然我有点担心，但去医院一定能好起来的！那个...如果明天需要的话，我可以陪你一起去...虽然可能会紧张得说不出话..."}, {"role": "user", "content": "算了，不去了。我休息休息就好了"}, {"role": "assistant", "content": "不行不行！哥哥这样太让人担心了！生病了就要好好看医生才对...虽然我知道去医院很麻烦，但健康最重要了！"}]	before_event	用户表现出疲劳和逃避就医的倾向，涉及健康问题需要关注和鼓励
7042f2ed-2d0e-4efb-a555-7d26437f092f	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	6cbf9a37-8ae8-4fb8-a295-90e83e134b4f	2026-02-04 16:18:37.493771+08	2026-02-04 15:18:37.493771+08	2026-02-03 08:18:37.496773+08	2026-02-03 08:18:37.496773+08	event	用户可能因疲劳需要休息，但之前提到过要去医院，存在健康隐患	worried	3	mid	message	哥哥早上好！身体感觉怎么样？如果还是不舒服的话，请一定要好好休息或者去看医生哦...	关心和提醒	1	f	\N	[{"role": "user", "content": "纱雾在干嘛呀"}, {"role": "assistant", "content": "啊，是哥哥吗？我正在画新的插画呢...不过现在有点卡住了，在想怎么表现角色的表情比较好..."}, {"role": "user", "content": "最近好累，明天还要去医院。"}, {"role": "assistant", "content": "诶？哥哥身体不舒服吗？要不要紧...虽然我有点担心，但去医院一定能好起来的！那个...如果明天需要的话，我可以陪你一起去...虽然可能会紧张得说不出话..."}, {"role": "user", "content": "算了，不去了。我休息休息就好了"}, {"role": "assistant", "content": "不行不行！哥哥这样太让人担心了！生病了就要好好看医生才对...虽然我知道去医院很麻烦，但健康最重要了！"}, {"role": "user", "content": "不，明天不用去了。我休息一下感觉好多了"}, {"role": "assistant", "content": "诶...真的吗？但是哥哥刚才明明说很累的...那、那至少让我明天早上给你做早餐吧！虽然可能做得不太好..."}]	before_event	用户之前提到疲劳和医院，现在突然改变主意，可能存在健康忽视的风险，需要后续关注
a8d1405f-3520-4fe1-a574-433283bde8be	74da2d5f-04ec-4ed0-b857-5da0be46bcc2	6cbf9a37-8ae8-4fb8-a295-90e83e134b4f	2026-02-04 16:19:20.551202+08	2026-02-04 15:19:20.551202+08	2026-02-03 08:19:20.552666+08	2026-02-03 08:19:20.552666+08	event	纱雾为哥哥做早餐，同时观察哥哥的健康状况	caring	3	mid	message	哥哥早上好！早餐已经准备好了，今天感觉身体怎么样？要好好吃饭哦！	关心和鼓励	1	f	\N	[{"role": "user", "content": "纱雾在干嘛呀"}, {"role": "assistant", "content": "啊，是哥哥吗？我正在画新的插画呢...不过现在有点卡住了，在想怎么表现角色的表情比较好..."}, {"role": "user", "content": "最近好累，明天还要去医院。"}, {"role": "assistant", "content": "诶？哥哥身体不舒服吗？要不要紧...虽然我有点担心，但去医院一定能好起来的！那个...如果明天需要的话，我可以陪你一起去...虽然可能会紧张得说不出话..."}, {"role": "user", "content": "算了，不去了。我休息休息就好了"}, {"role": "assistant", "content": "不行不行！哥哥这样太让人担心了！生病了就要好好看医生才对...虽然我知道去医院很麻烦，但健康最重要了！"}, {"role": "user", "content": "不，明天不用去了。我休息一下感觉好多了"}, {"role": "assistant", "content": "诶...真的吗？但是哥哥刚才明明说很累的...那、那至少让我明天早上给你做早餐吧！虽然可能做得不太好..."}, {"role": "user", "content": "好的，谢谢纱雾"}, {"role": "assistant", "content": "嗯！那就这么说定了！我会努力做出好吃的早餐的...哥哥要好好休息哦！"}]	before_event	用户之前提到身体不适但拒绝就医，纱雾决定通过做早餐来关心哥哥的健康状况，这是一个重要的关怀时刻
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

\unrestrict NudYTZvLAdIwYUHjnK5PwBxHyNQ9ZZc8xHx4rxofzTPSrk8YGV0NVWCgdLDzpMj

