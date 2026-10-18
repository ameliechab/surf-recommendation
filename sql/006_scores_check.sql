-- FindYourWave : contrôle des scores (score.py)
-- À coller dans Supabase > SQL Editor > New query, puis "Run". Lecture seule.

with s as (select * from spot_hour_scores),
checks(ordre, controle, resultat, attendu, ok) as (
    select 1, 'Lignes de scores',
           (select count(*) from s)::text || ' (' || (select count(distinct spot_id) from s) || ' spots × '
             || (select count(distinct forecast_datetime) from s) || ' h × '
             || (select count(distinct surf_level) from s) || ' niveaux)',
           'spots × 168 h × 5 niveaux',
           (select count(*) from s) = (select count(distinct spot_id) * count(distinct forecast_datetime) * 5 from s)
           and (select count(*) from s) > 0
    union all
    select 2, 'Dernier calcul (heure de Paris)',
           (select to_char(max(scored_at) at time zone 'Europe/Paris', 'DD/MM HH24:MI') from s),
           'il y a moins de 13 h',
           (select max(scored_at) from s) > now() - interval '13 hours'
    union all
    select 3, 'Scores calculés sur la dernière collecte',
           (select count(*) from s join (select spot_id, forecast_datetime, retrieved_at from marine_forecast) f
              using (spot_id, forecast_datetime) where s.forecast_retrieved_at <> f.retrieved_at)::text || ' ligne(s) en retard',
           '0',
           not exists (select 1 from s join marine_forecast f using (spot_id, forecast_datetime)
                        where s.forecast_retrieved_at <> f.retrieved_at)
    union all
    select 4, 'Spots interdits au niveau : jamais éligibles',
           (select count(*) from s join surf_spot_conditions_reference c using (spot_id)
             where s.is_eligible
               and array_position(array['debutant','intermediaire','avance','expert','pro'], s.surf_level)
                 < array_position(array['debutant','intermediaire','avance','expert','pro'], c.min_level))::text,
           '0', true
    union all
    select 5, 'Créneaux éligibles par niveau',
           (select string_agg(surf_level || '=' || n, ', ' order by n)
              from (select surf_level, count(*) filter (where is_eligible) n from s group by 1) t),
           'croissant du débutant au pro', true
    union all
    select 6, 'Raisons de non-éligibilité',
           (select string_agg(ineligibility_reason || '=' || n, ', ' order by n desc)
              from (select ineligibility_reason, count(*) n from s where not is_eligible group by 1) t),
           'peu ou pas de donnees_manquantes', true
    union all
    select 7, 'Score global min / moyen / max',
           (select round(min(global_score)::numeric, 0) || ' / ' || round(avg(global_score)::numeric, 0) || ' / '
                   || round(max(global_score)::numeric, 0) from s),
           'entre 0 et 100, bien étalé', true
    union all
    select 8, 'Créneaux à 50 ou plus (seuil d''affichage)',
           (select round(100.0 * count(*) filter (where global_score >= 50) / greatest(count(*) filter (where is_eligible), 1), 0)
              from s)::text || ' % des éligibles',
           'ni 0 %, ni 100 %', true
)
select controle, resultat, attendu,
       case when ordre = 4 then case when resultat = '0' then '✅ OK' else '⚠️ À VOIR' end
            when ok then '✅ OK' else '⚠️ À VOIR' end as statut
from checks
order by ordre;
