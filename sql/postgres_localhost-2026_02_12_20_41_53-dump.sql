--
-- PostgreSQL database dump
--

\restrict rcnvRluewFxQFO0aS1xon2pRXjt31KPnKb5UyLV8ecJ4NdgH7ahqV2tVmzQvILg

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
-- Name: postgres; Type: DATABASE; Schema: -; Owner: ASUS
--

CREATE DATABASE postgres WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'Chinese (Simplified)_China.936';


ALTER DATABASE postgres OWNER TO "ASUS";

\unrestrict rcnvRluewFxQFO0aS1xon2pRXjt31KPnKb5UyLV8ecJ4NdgH7ahqV2tVmzQvILg
\connect postgres
\restrict rcnvRluewFxQFO0aS1xon2pRXjt31KPnKb5UyLV8ecJ4NdgH7ahqV2tVmzQvILg

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
-- Name: DATABASE postgres; Type: COMMENT; Schema: -; Owner: ASUS
--

COMMENT ON DATABASE postgres IS 'default administrative connection database';


--
-- PostgreSQL database dump complete
--

\unrestrict rcnvRluewFxQFO0aS1xon2pRXjt31KPnKb5UyLV8ecJ4NdgH7ahqV2tVmzQvILg

