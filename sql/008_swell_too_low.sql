-- FindYourWave : migration « mer plate » du scoring v1 (20/10)
-- À lancer une fois, AVANT de pousser la version de score.py qui l'utilise.
-- Peut être relancé sans risque.

-- Nouvelle raison de non-éligibilité « houle_trop_faible » (remplie par score.py)
alter table public.spot_hour_scores drop constraint if exists spot_hour_scores_ineligibility_reason_check;
alter table public.spot_hour_scores add constraint spot_hour_scores_ineligibility_reason_check
    check (ineligibility_reason in ('niveau_spot','nuit','houle_trop_forte','houle_trop_faible','vent_trop_fort','donnees_manquantes'));


-- check que la requête ci-dessus a bien été appliquée (doit renvoyer true)
select pg_get_constraintdef(oid) like '%houle_trop_faible%' as houle_trop_faible_ok
from pg_constraint
where conname = 'spot_hour_scores_ineligibility_reason_check';
