-- FindYourWave : taux de remplissage de chaque colonne de chaque table
-- À coller dans Supabase > SQL Editor > New query, puis "Run". Lecture seule.
-- remplies = nombre de lignes où la colonne n'est pas vide (NULL).

with cols as (
    select 'surf_spot_properties' as table_name, j.key as colonne, j.value
      from surf_spot_properties t, jsonb_each(to_jsonb(t)) j
    union all
    select 'surf_spot_conditions_reference', j.key, j.value
      from surf_spot_conditions_reference t, jsonb_each(to_jsonb(t)) j
    union all
    select 'surf_level_conditions_reference', j.key, j.value
      from surf_level_conditions_reference t, jsonb_each(to_jsonb(t)) j
    union all
    select 'marine_forecast', j.key, j.value
      from marine_forecast t, jsonb_each(to_jsonb(t)) j
    union all
    select 'spot_hour_scores', j.key, j.value
      from spot_hour_scores t, jsonb_each(to_jsonb(t)) j
),
stats as (
    select table_name, colonne,
           count(*)                                         as lignes,
           count(*) filter (where value <> 'null'::jsonb)   as remplies
      from cols
     group by table_name, colonne
),
tables as (  -- pour faire apparaître aussi les tables vides
    select 'surf_spot_properties' t, (select count(*) from surf_spot_properties) n union all
    select 'surf_spot_conditions_reference', (select count(*) from surf_spot_conditions_reference) union all
    select 'surf_level_conditions_reference', (select count(*) from surf_level_conditions_reference) union all
    select 'marine_forecast', (select count(*) from marine_forecast) union all
    select 'spot_hour_scores', (select count(*) from spot_hour_scores)
)
select table_name, colonne, lignes, remplies,
       round(100.0 * remplies / lignes, 1) as pct_rempli,
       case when remplies = lignes then '✅ complète'
            when remplies = 0      then '⚠️ entièrement vide'
            else '🟡 partielle' end as statut
  from stats
union all
select t, '(table vide)', 0, 0, null, '⚠️ aucune ligne' from tables where n = 0
order by table_name, statut desc, colonne;
