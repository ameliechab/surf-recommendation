-- FindYourWave : migration « créneaux de nuit » (18/10)
-- À lancer une fois, AVANT de pousser la version de collect.py / score.py qui l'utilise.
-- Peut être relancé sans risque.

-- 1. Jour / nuit pour chaque heure de prévision (rempli par collect.py)
alter table public.marine_forecast add column if not exists is_daylight boolean;

-- 2. Nouvelle raison de non-éligibilité « nuit » (remplie par score.py)
alter table public.spot_hour_scores drop constraint if exists spot_hour_scores_ineligibility_reason_check;
alter table public.spot_hour_scores add constraint spot_hour_scores_ineligibility_reason_check
    check (ineligibility_reason in ('niveau_spot','nuit','houle_trop_forte','vent_trop_fort','donnees_manquantes'));


-- check que la requete ci-dessus a bien été appliquée
select
  (select count(*) from information_schema.columns
    where table_name = 'marine_forecast' and column_name = 'is_daylight') as colonne_ok,
  (select pg_get_constraintdef(oid) like '%nuit%' from pg_constraint
    where conname = 'spot_hour_scores_ineligibility_reason_check') as nuit_ok;