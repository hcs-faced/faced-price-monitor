-- Face D Price Monitor — schema database (Supabase / Postgres)
-- Eseguire una sola volta nel SQL Editor del progetto Supabase.

-- ---------- Tabelle ----------

create table if not exists public.sites (
  id          serial primary key,
  code        text unique not null,          -- es. 'atida', 'amazon'
  name        text not null,
  domain      text,
  authorized  boolean not null default false, -- rivenditore autorizzato da Face D
  kind        text not null default 'retailer', -- retailer | amazon | discovered
  created_at  timestamptz not null default now()
);

create table if not exists public.products (
  id            serial primary key,
  ean           text unique not null,
  sku           text,
  name          text not null,
  variant       text,
  handle        text,                         -- handle Shopify su faced.com
  rrp           numeric(10,2),                -- prezzo consigliato (faced.com)
  asin          text,                         -- ASIN Amazon.it (trovato in automatico)
  active        boolean not null default true,
  in_prototype  boolean not null default true,
  updated_at    timestamptz not null default now()
);

-- Pagine prodotto da leggere sui siti (una riga per prodotto x sito)
create table if not exists public.product_urls (
  id          serial primary key,
  product_id  int not null references public.products(id) on delete cascade,
  site_id     int not null references public.sites(id) on delete cascade,
  url         text not null,
  active      boolean not null default true,
  note        text,
  created_at  timestamptz not null default now(),
  unique (product_id, site_id, url)
);

create table if not exists public.runs (
  id           bigserial primary key,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  status       text not null default 'running', -- running | ok | partial | error
  summary      jsonb
);

-- Ogni rilevazione di prezzo
create table if not exists public.observations (
  id               bigserial primary key,
  run_id           bigint references public.runs(id) on delete set null,
  observed_at      timestamptz not null default now(),
  product_id       int not null references public.products(id) on delete cascade,
  site_id          int not null references public.sites(id) on delete cascade,
  seller_id        text not null default '',    -- per Amazon: SellerId; per i siti: ''
  seller_name      text,
  url              text,
  title            text,
  price            numeric(10,2),               -- prezzo di vendita (IVA inclusa)
  list_price       numeric(10,2),               -- prezzo barrato, se rilevato
  shipping         numeric(10,2),
  in_stock         boolean,
  is_buybox        boolean,
  is_fba           boolean,
  possible_bundle  boolean not null default false,
  error            text
);
create index if not exists observations_lookup
  on public.observations (product_id, site_id, seller_id, observed_at desc);

-- Venditori (soprattutto Amazon): autorizzato sì/no si decide dalla dashboard
create table if not exists public.sellers (
  id          serial primary key,
  site_id     int not null references public.sites(id) on delete cascade,
  seller_id   text not null,
  name        text,
  authorized  boolean,                          -- null = da verificare
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  unique (site_id, seller_id)
);

-- ---------- Viste ----------

-- Ultima rilevazione valida (ultimi 10 giorni) per prodotto x sito x venditore
create or replace view public.v_latest
with (security_invoker = true) as
select distinct on (o.product_id, o.site_id, o.seller_id)
  o.product_id, p.ean, p.name as product_name, p.variant, p.rrp,
  o.site_id, s.code as site_code, s.name as site_name,
  o.seller_id, coalesce(o.seller_name, sl.name) as seller_name,
  case when s.kind = 'amazon' then sl.authorized else s.authorized end as authorized,
  o.price, o.list_price, o.shipping, o.in_stock, o.is_buybox, o.is_fba,
  o.possible_bundle, o.url, o.title, o.observed_at,
  case when p.rrp > 0 and o.price is not null
       then round((o.price - p.rrp) / p.rrp * 100, 1) end as deviation_pct
from public.observations o
join public.products p on p.id = o.product_id
join public.sites s on s.id = o.site_id
left join public.sellers sl on sl.site_id = o.site_id and sl.seller_id = o.seller_id
where o.price is not null
  and o.observed_at > now() - interval '10 days'
order by o.product_id, o.site_id, o.seller_id, o.observed_at desc;

-- Storico giornaliero per i grafici di scostamento
create or replace view public.v_history
with (security_invoker = true) as
select
  o.product_id, o.site_id, o.seller_id,
  date_trunc('day', o.observed_at)::date as day,
  min(o.price) as price,
  bool_or(o.possible_bundle) as possible_bundle,
  bool_or(o.in_stock) as in_stock,
  round((min(o.price) - p.rrp) / nullif(p.rrp, 0) * 100, 1) as deviation_pct
from public.observations o
join public.products p on p.id = o.product_id
where o.price is not null
group by o.product_id, o.site_id, o.seller_id, date_trunc('day', o.observed_at), p.rrp;

-- ---------- Sicurezza (Row Level Security) ----------
-- Lettura: solo utenti con login. Scrittura dei dati: solo il raccoglitore
-- (chiave segreta, che salta l'RLS). I colleghi possono gestire URL e venditori.

alter table public.sites         enable row level security;
alter table public.products      enable row level security;
alter table public.product_urls  enable row level security;
alter table public.runs          enable row level security;
alter table public.observations  enable row level security;
alter table public.sellers       enable row level security;

do $$
declare t text;
begin
  foreach t in array array['sites','products','product_urls','runs','observations','sellers'] loop
    execute format('drop policy if exists "read_%1$s" on public.%1$s', t);
    execute format('create policy "read_%1$s" on public.%1$s for select to authenticated using (true)', t);
  end loop;
end $$;

drop policy if exists "edit_product_urls" on public.product_urls;
create policy "edit_product_urls" on public.product_urls
  for all to authenticated using (true) with check (true);

drop policy if exists "edit_sellers" on public.sellers;
create policy "edit_sellers" on public.sellers
  for update to authenticated using (true) with check (true);

revoke all on all tables in schema public from anon;
