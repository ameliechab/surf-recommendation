-- FindYourWave : vérification du calcul de la marée (tide.py)
-- À coller dans Supabase > SQL Editor > New query, puis "Run". Lecture seule.
-- Compare, heure par heure, la marée calculée avec la hauteur d'eau brute d'Open-Meteo.

with s as (
    select spot_id, forecast_datetime, sea_level_height_m as h,
           tide_level_pct as pct, tide_direction as dir, tide_stage as stage,
           lag(sea_level_height_m)  over w as h_prev,
           lead(sea_level_height_m) over w as h_next
      from marine_forecast
     where forecast_datetime >= now() - interval '1 day'
    window w as (partition by spot_id order by forecast_datetime)
),
checks(ordre, controle, erreurs, sur, explication) as (
    select 1, 'Stade cohérent avec le niveau (basse < 0,3 ; pleine > 0,7)',
           count(*) filter (where stage <> case when pct < 0.3 then 'basse' when pct > 0.7 then 'pleine' else 'mi-maree' end),
           count(*) filter (where pct is not null),
           'tide_stage suit bien la règle du doc'
      from s
    union all
    select 2, 'Montante : l''eau monte bien jusqu''à l''heure suivante',
           count(*) filter (where dir = 'montante' and h_next < h - 0.01),
           count(*) filter (where dir = 'montante' and h_next is not null),
           'tolérance de 1 cm'
      from s
    union all
    select 3, 'Descendante : l''eau baisse bien jusqu''à l''heure suivante',
           count(*) filter (where dir = 'descendante' and h_next > h + 0.01),
           count(*) filter (where dir = 'descendante' and h_next is not null),
           'tolérance de 1 cm'
      from s
    union all
    select 4, 'Basse mer (pct = 0) : c''est bien un creux local',
           count(*) filter (where pct = 0 and (h > h_prev or h > h_next)),
           count(*) filter (where pct = 0 and h_prev is not null and h_next is not null),
           'le niveau est ≤ aux heures voisines'
      from s
    union all
    select 5, 'Pleine mer (pct = 1) : c''est bien un sommet local',
           count(*) filter (where pct = 1 and (h < h_prev or h < h_next)),
           count(*) filter (where pct = 1 and h_prev is not null and h_next is not null),
           'le niveau est ≥ aux heures voisines'
      from s
    union all
    select 6, 'Niveau de marée entre 0 et 1',
           count(*) filter (where pct < 0 or pct > 1),
           count(*) filter (where pct is not null),
           'tide_level_pct borné'
      from s
    union all
    select 7, 'Durée moyenne entre deux basses mers (h)',
           null, null,
           (select round(avg(ecart)::numeric, 1)::text || ' h (attendu : environ 12,4 h)'
              from (select extract(epoch from forecast_datetime - lag(forecast_datetime) over (partition by spot_id order by forecast_datetime)) / 3600 as ecart
                      from s where pct = 0) x)
)
select controle, erreurs, sur as lignes_testees,
       case when erreurs is null then 'ℹ️' when erreurs = 0 then '✅ OK' else '⚠️ À VOIR' end as statut,
       explication
  from checks
 order by ordre;

-- Pour voir la courbe d'un spot sur 36 h, lance aussi cette requête seule :
-- select to_char(forecast_datetime at time zone 'Europe/Paris', 'DD/MM HH24:MI') as heure_paris,
--        round(sea_level_height_m::numeric, 2) as hauteur_m, tide_level_pct, tide_direction, tide_stage
--   from marine_forecast
--  where spot_id = 'la_torche' and forecast_datetime >= now()
--  order by forecast_datetime limit 36;
