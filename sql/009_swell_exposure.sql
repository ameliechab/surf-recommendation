-- Coefficient d'abri des spots (scoring v1.1)
-- À exécuter UNE FOIS dans Supabase > SQL Editor, AVANT de pousser le code qui l'utilise
-- (sinon sync_sheets.py échoue : la colonne n'existe pas encore en base).
--
-- swell_exposure = part de la houle du large qui atteint le spot :
--   1 (ou vide) = spot exposé, 0,5 = baie abritée où les vagues font la moitié de la houle du large.
-- Le scoring juge la hauteur utile = houle au large × facteur de direction × swell_exposure.

alter table public.surf_spot_conditions_reference
    add column if not exists swell_exposure numeric(3, 2)
        check (swell_exposure is null or swell_exposure between 0.1 and 1);

comment on column public.surf_spot_conditions_reference.swell_exposure is
    'Part de la houle du large qui atteint le spot (1 ou vide = exposé, ex. 0,5 = baie abritée)';

-- Les droits de lecture (anon, authenticated) portent sur la table : rien à ajouter.

-- Contrôle : doit afficher agadir 0.50, hash_point 0.70 et imsouane_the_bay 0.70 après la synchro du Sheet
-- select spot_id, swell_exposure from public.surf_spot_conditions_reference
-- where swell_exposure < 1 order by spot_id;
