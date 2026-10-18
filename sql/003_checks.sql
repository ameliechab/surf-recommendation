-- FindYourWave : contrôle de l'alimentation des tables
-- À coller dans Supabase > SQL Editor > New query, puis "Run".
-- Ne modifie rien : lecture seule. Une ligne par contrôle, statut OK ou À VOIR.

with
spots as (select count(*) n from surf_spot_properties),
fc as (
    select spot_id,
           count(*)                                         as heures,
           min(forecast_datetime)                           as debut,
           max(forecast_datetime)                           as fin,
           max(retrieved_at)                                as derniere_collecte,
           extract(epoch from max(forecast_datetime) - min(forecast_datetime)) / 3600 + 1 as heures_attendues
    from marine_forecast
    group by spot_id
),
recent as (  -- uniquement les heures de la dernière collecte (fenêtre -1 j / +8 j)
    select * from marine_forecast
    where forecast_datetime >= now() - interval '1 day'
      and forecast_datetime <  now() + interval '7 days'
),
checks(ordre, controle, resultat, attendu, ok) as (
    -- 1. Référentiels (Google Sheet -> Supabase)
    select 1, 'Spots dans surf_spot_properties',
           (select n from spots)::text, '14 (ou ton nombre de spots)',
           (select n from spots) > 0
    union all
    select 2, 'Spots sans conditions (surf_spot_conditions_reference)',
           (select count(*) from surf_spot_properties p
             where not exists (select 1 from surf_spot_conditions_reference c where c.spot_id = p.spot_id))::text,
           '0',
           not exists (select 1 from surf_spot_properties p
                        where not exists (select 1 from surf_spot_conditions_reference c where c.spot_id = p.spot_id))
    union all
    select 3, 'Niveaux dans surf_level_conditions_reference',
           (select string_agg(surf_level, ', ' order by swell_height_max) from surf_level_conditions_reference),
           'debutant, intermediaire, avance, expert, pro',
           (select count(*) from surf_level_conditions_reference) = 5
    union all
    select 4, 'Seuils de houle max par niveau (m)',
           (select string_agg(surf_level || '=' || swell_height_max, ', ' order by swell_height_max)
              from surf_level_conditions_reference),
           'entre 1 et 4 m, croissants',
           (select bool_and(swell_height_max between 0.5 and 5) from surf_level_conditions_reference)
    union all
    -- 2. Prévisions (Open-Meteo -> marine_forecast)
    select 5, 'Spots avec des prévisions',
           (select count(*) from fc)::text || ' / ' || (select n from spots), 'tous les spots',
           (select count(*) from fc) = (select n from spots)
    union all
    select 6, 'Dernière collecte (heure de Paris)',
           (select to_char(max(derniere_collecte) at time zone 'Europe/Paris', 'DD/MM HH24:MI') from fc),
           'il y a moins de 13 h',
           (select max(derniere_collecte) from fc) > now() - interval '13 hours'
    union all
    select 7, 'Spots en retard (collecte > 13 h)',
           coalesce((select string_agg(spot_id, ', ') from fc where derniere_collecte < now() - interval '13 hours'), 'aucun'),
           'aucun',
           not exists (select 1 from fc where derniere_collecte < now() - interval '13 hours')
    union all
    select 8, 'Prévisions jusqu''à',
           (select to_char(min(fin) at time zone 'Europe/Paris', 'DD/MM HH24:MI') from fc),
           'au moins J+7',
           (select min(fin) from fc) > now() + interval '6 days'
    union all
    select 9, 'Heures manquantes (trous dans la série horaire)',
           (select coalesce(sum(heures_attendues - heures), 0)::int from fc)::text, '0',
           (select coalesce(sum(heures_attendues - heures), 0) from fc) = 0
    union all
    -- 3. Valeurs manquantes sur la fenêtre utile (J-1 à J+7)
    select 10, 'Houle : hauteur / période / direction vides',
           (select count(*) filter (where swell_height_m is null) || ' / ' ||
                   count(*) filter (where swell_period_s is null) || ' / ' ||
                   count(*) filter (where swell_direction_deg is null) from recent),
           '0 / 0 / 0',
           (select count(*) filter (where swell_height_m is null or swell_period_s is null
                                    or swell_direction_deg is null) from recent) = 0
    union all
    select 11, 'Vent : vitesse / direction vides',
           (select count(*) filter (where wind_speed_kmh is null) || ' / ' ||
                   count(*) filter (where wind_direction_deg is null) from recent),
           '0 / 0',
           (select count(*) filter (where wind_speed_kmh is null or wind_direction_deg is null) from recent) = 0
    union all
    select 12, 'Températures air / eau vides',
           (select count(*) filter (where air_temp_c is null) || ' / ' ||
                   count(*) filter (where water_temp_c is null) from recent),
           '0 / 0',
           (select count(*) filter (where air_temp_c is null or water_temp_c is null) from recent) = 0
    union all
    select 13, 'Hauteur d''eau (marée) vide',
           (select count(*) filter (where sea_level_height_m is null) from recent)::text, '0',
           (select count(*) filter (where sea_level_height_m is null) from recent) = 0
    union all
    select 14, 'Heures sans stade de marée (% de la fenêtre)',
           (select round(100.0 * count(*) filter (where tide_stage is null) / greatest(count(*), 1), 1) from recent)::text || ' %',
           'moins de 5 %',
           (select 100.0 * count(*) filter (where tide_stage is null) / greatest(count(*), 1) from recent) < 5
    union all
    -- 4. Valeurs plausibles
    select 15, 'Houle (m) min / max',
           (select round(min(swell_height_m)::numeric, 2) || ' / ' || round(max(swell_height_m)::numeric, 2) from recent),
           'entre 0 et 10',
           (select coalesce(min(swell_height_m) >= 0 and max(swell_height_m) <= 10, false) from recent)
    union all
    select 16, 'Période (s) min / max',
           (select round(min(swell_period_s)::numeric, 1) || ' / ' || round(max(swell_period_s)::numeric, 1) from recent),
           'entre 3 et 25',
           (select coalesce(min(swell_period_s) >= 2 and max(swell_period_s) <= 25, false) from recent)
    union all
    select 17, 'Vent (km/h) max',
           (select round(max(wind_speed_kmh)::numeric, 0) from recent)::text,
           'moins de 120',
           (select coalesce(max(wind_speed_kmh) < 120, false) from recent)
    union all
    select 18, 'Eau (°C) min / max',
           (select round(min(water_temp_c)::numeric, 1) || ' / ' || round(max(water_temp_c)::numeric, 1) from recent),
           'entre 8 et 22 en Bretagne',
           (select coalesce(min(water_temp_c) >= 6 and max(water_temp_c) <= 24, false) from recent)
    union all
    select 19, 'Répartition des stades de marée',
           (select string_agg(tide_stage || '=' || n, ', ' order by tide_stage)
              from (select tide_stage, count(*) n from recent where tide_stage is not null group by 1) t),
           '3 stades présents, ~30 % / 40 % / 30 %',
           (select count(distinct tide_stage) = 3 from recent)
    union all
    select 20, 'Sens de marée montante / descendante',
           (select count(*) filter (where tide_direction = 'montante') || ' / ' ||
                   count(*) filter (where tide_direction = 'descendante') from recent),
           'à peu près égaux',
           (select count(*) filter (where tide_direction = 'montante') > 0
               and count(*) filter (where tide_direction = 'descendante') > 0 from recent)
)
select controle, resultat, attendu, case when ok then '✅ OK' else '⚠️ À VOIR' end as statut
from checks
order by ordre;
