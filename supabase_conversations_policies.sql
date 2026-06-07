-- Run in Supabase: SQL Editor → New query → Run
-- Fixes: "new row violates row-level security policy for table conversations"
--
-- Your Python app uses SUPABASE_KEY (publishable / anon key), so policies
-- must allow role "anon" unless you switch to the service_role key server-side.

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

-- Safe to re-run: drop old names then recreate
DROP POLICY IF EXISTS "anon_insert_conversations" ON public.conversations;
DROP POLICY IF EXISTS "anon_select_conversations" ON public.conversations;
DROP POLICY IF EXISTS "anon_update_conversations" ON public.conversations;

CREATE POLICY "anon_insert_conversations"
ON public.conversations
FOR INSERT
TO anon
WITH CHECK (true);

CREATE POLICY "anon_select_conversations"
ON public.conversations
FOR SELECT
TO anon
USING (true);

CREATE POLICY "anon_update_conversations"
ON public.conversations
FOR UPDATE
TO anon
USING (true)
WITH CHECK (true);
