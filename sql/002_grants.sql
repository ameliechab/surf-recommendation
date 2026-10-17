-- FindYourWave : droits d'accès pour l'API Supabase (Data API)
-- Depuis mai 2026, les nouveaux projets Supabase n'exposent plus
-- automatiquement les tables : sans ces GRANT, les scripts Python reçoivent
-- « permission denied for table ... » (code 42501).
-- À coller dans Supabase > SQL Editor > New query, puis "Run".
-- Relançable sans risque.

-- Scripts Python (clé secrète = rôle service_role) : lecture + écriture
grant usage on schema public to service_role, anon, authenticated;
grant select, insert, update, delete on all tables in schema public to service_role;

-- App Streamlit (clé publishable = rôle anon) : lecture seule
grant select on all tables in schema public to anon, authenticated;
