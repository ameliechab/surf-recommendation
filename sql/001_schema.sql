-- FindYourWave : schéma Supabase (PostgreSQL)
-- À coller dans Supabase > SQL Editor > New query, puis "Run".
-- Le script peut être relancé sans risque (IF NOT EXISTS / ON CONFLICT).
--
-- Choix : les "enum" du doc sont des contraintes CHECK sur du texte plutôt
-- que des types ENUM Postgres, plus simples à faire évoluer (ajouter une
-- valeur = modifier une ligne).

-- ---------------------------------------------------------------------------
-- 1. Données statiques : propriétés du spot (Sheet "Ref - surf_spot_properties")
-- ---------------------------------------------------------------------------
create table if not exists public.surf_spot_properties (
    spot_id              text primary key check (spot_id = lower(trim(spot_id))),
    spot_name            text not null,
    spot_description     text,
    department           text not null,
    localisation_lat     double precision not null check (localisation_lat between -90 and 90),
    localisation_lon     double precision not null check (localisation_lon between -180 and 180),
    spot_orientation_deg integer not null check (spot_orientation_deg between 0 and 360),
    bottom_type          text check (bottom_type in ('sable','roche','reef','mixte')),
    wave_type            text check (wave_type in ('beachbreak','reefbreak','pointbreak')),
    accessibility        text not null check (accessibility in ('facile','moyenne','difficile')),
    updated_at           timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 2. Expertise surf par spot (Sheet "Ref - surf_spot_conditions_reference")
--    Fenêtres circulaires autorisées (min > max, ex. 330 -> 30).
-- ---------------------------------------------------------------------------
create table if not exists public.surf_spot_conditions_reference (
    spot_id                     text primary key
                                references public.surf_spot_properties(spot_id) on delete cascade,
    min_level                   text not null
                                check (min_level in ('debutant','intermediaire','avance','expert','pro')),
    ideal_swell_orientation_min integer check (ideal_swell_orientation_min between 0 and 360),
    ideal_swell_orientation_max integer check (ideal_swell_orientation_max between 0 and 360),
    ideal_wind_orientation_min  integer check (ideal_wind_orientation_min between 0 and 360),
    ideal_wind_orientation_max  integer check (ideal_wind_orientation_max between 0 and 360),
    ideal_tide_stage            text not null default 'toutes'
                                check (ideal_tide_stage in ('basse','mi-maree','pleine','montante','descendante','toutes')),
    crowd_level                 smallint check (crowd_level between 1 and 5),  -- V2, non utilisé par l'algo
    updated_at                  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 3. Référentiel par niveau (Sheet "Ref - surf_level_conditions_reference")
--    Les CHECK bloquent les valeurs transformées en dates par Google Sheets
--    (ex. 46054 au lieu de 1.2) et les seuils dans le désordre.
-- ---------------------------------------------------------------------------
create table if not exists public.surf_level_conditions_reference (
    surf_level             text primary key
                           check (surf_level in ('debutant','intermediaire','avance','expert','pro')),
    swell_height_min       numeric(4,2) not null check (swell_height_min between 0 and 10),
    swell_height_ideal_min numeric(4,2) not null check (swell_height_ideal_min between 0 and 10),
    swell_height_ideal_max numeric(4,2) not null check (swell_height_ideal_max between 0 and 10),
    swell_height_max       numeric(4,2) not null check (swell_height_max between 0 and 10),
    period_min             numeric(4,1) not null check (period_min between 0 and 30),
    period_ideal_min       numeric(4,1) not null check (period_ideal_min between 0 and 30),
    period_ideal_max       numeric(4,1) not null check (period_ideal_max between 0 and 30),
    period_max             numeric(4,1) not null check (period_max between 0 and 30),
    wind_speed_ideal_max   numeric(5,1) not null check (wind_speed_ideal_max between 0 and 150),
    wind_speed_max         numeric(5,1) not null check (wind_speed_max between 0 and 150),
    updated_at             timestamptz not null default now(),
    check (swell_height_min <= swell_height_ideal_min
           and swell_height_ideal_min <= swell_height_ideal_max
           and swell_height_ideal_max <= swell_height_max),
    check (period_min <= period_ideal_min
           and period_ideal_min <= period_ideal_max
           and period_ideal_max <= period_max),
    check (wind_speed_ideal_max <= wind_speed_max)
);

-- Valeurs de départ (tableau "Référentiel intermédiaire" du doc).
-- La synchro Google Sheets les écrasera ensuite.
insert into public.surf_level_conditions_reference
    (surf_level, swell_height_min, swell_height_ideal_min, swell_height_ideal_max, swell_height_max,
     period_min, period_ideal_min, period_ideal_max, period_max, wind_speed_ideal_max, wind_speed_max)
values
    ('debutant',      0.4, 0.4, 0.8, 1.2, 8, 8, 11, 13, 10, 20),
    ('intermediaire', 0.5, 0.5, 1.2, 1.8, 8, 8, 12, 15, 15, 25),
    ('avance',        0.6, 0.6, 1.5, 2.5, 7, 8, 13, 16, 20, 30),
    ('expert',        0.6, 0.6, 2.0, 4.0, 7, 8, 14, 17, 25, 35),
    ('pro',           0.6, 0.6, 2.5, 4.0, 7, 8, 15, 18, 30, 40)
on conflict (surf_level) do nothing;

-- ---------------------------------------------------------------------------
-- 4. Données dynamiques : prévisions horaires Open-Meteo (collect.py)
--    Upsert sur (spot_id, forecast_datetime) : on écrase à chaque collecte.
-- ---------------------------------------------------------------------------
create table if not exists public.marine_forecast (
    forecast_id         uuid primary key default gen_random_uuid(),
    spot_id             text not null references public.surf_spot_properties(spot_id) on delete cascade,
    forecast_datetime   timestamptz not null,
    swell_height_m      real,
    swell_period_s      real,
    swell_direction_deg real,
    water_temp_c        real,
    wind_speed_kmh      real,
    wind_direction_deg  real,
    air_temp_c          real,
    uv_index            real,
    precipitation_mm    real,
    tide_coefficient    real,          -- V2 (SHOM)
    sea_level_height_m  real,
    tide_level_pct      real check (tide_level_pct between 0 and 1),
    tide_direction      text check (tide_direction in ('montante','descendante')),
    tide_stage          text check (tide_stage in ('basse','mi-maree','pleine')),
    is_daylight         boolean,       -- l'heure commence entre le lever et le coucher du soleil
    data_source         text not null,
    retrieved_at        timestamptz not null,
    unique (spot_id, forecast_datetime)
);

create index if not exists marine_forecast_datetime_idx
    on public.marine_forecast (forecast_datetime);

-- ---------------------------------------------------------------------------
-- 5. Scores calculés (score.py) : un score par spot, heure et niveau
-- ---------------------------------------------------------------------------
create table if not exists public.spot_hour_scores (
    spot_id               text not null references public.surf_spot_properties(spot_id) on delete cascade,
    forecast_datetime     timestamptz not null,
    surf_level            text not null
                          check (surf_level in ('debutant','intermediaire','avance','expert','pro')),
    is_eligible           boolean not null,
    ineligibility_reason  text
                          check (ineligibility_reason in ('niveau_spot','nuit','houle_trop_forte','vent_trop_fort','donnees_manquantes')),
    swell_height_score    real check (swell_height_score between 0 and 100),
    swell_direction_score real check (swell_direction_score between 0 and 100),
    swell_score           real check (swell_score between 0 and 100),
    period_score          real check (period_score between 0 and 100),
    wind_speed_score      real check (wind_speed_score between 0 and 100),
    wind_direction_score  real check (wind_direction_score between 0 and 100),
    wind_score            real check (wind_score between 0 and 100),
    tide_score            real check (tide_score between 0 and 100),
    global_score          real check (global_score between 0 and 100),
    scoring_version       text not null,
    forecast_retrieved_at timestamptz not null,
    scored_at             timestamptz not null default now(),
    primary key (spot_id, forecast_datetime, surf_level),
    check (is_eligible or global_score is null),
    check (is_eligible = (ineligibility_reason is null))
);

create index if not exists spot_hour_scores_lookup_idx
    on public.spot_hour_scores (surf_level, forecast_datetime);

-- ---------------------------------------------------------------------------
-- 6. Sécurité : droits (GRANT) + Row Level Security
--    Lecture publique (l'app Streamlit peut lire avec la clé "publishable"/anon).
--    Écriture : uniquement les scripts, avec la clé secrète, qui passe outre RLS.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
    foreach t in array array['surf_spot_properties','surf_spot_conditions_reference',
                             'surf_level_conditions_reference','marine_forecast','spot_hour_scores']
    loop
        execute format('alter table public.%I enable row level security', t);
        execute format('drop policy if exists "lecture publique" on public.%I', t);
        execute format('create policy "lecture publique" on public.%I for select to anon, authenticated using (true)', t);
    end loop;
end $$;

-- Droits pour l'API Supabase (même contenu que 002_grants.sql) : depuis mai 2026,
-- les nouvelles tables ne sont plus exposées automatiquement.
grant usage on schema public to service_role, anon, authenticated;
grant select, insert, update, delete on all tables in schema public to service_role;
grant select on all tables in schema public to anon, authenticated;
