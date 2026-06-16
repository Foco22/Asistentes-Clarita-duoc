-- ============================================================
-- Schema para el Chatbot Telegram con LangGraph y Supabase
-- Clase 3.5 - Ingeniería de Soluciones con IA - DuocUC
-- ============================================================

-- Migraciones: agregar columnas si las tablas ya existen
alter table if exists traces add column if not exists step_order       int  not null default 0;
alter table if exists traces add column if not exists prompt_tokens    int;
alter table if exists traces add column if not exists completion_tokens int;
alter table if exists traces add column if not exists company          text;
alter table if exists traces add column if not exists model            text;


-- Sesiones: una por usuario de Telegram
create table if not exists sessions (
  id               uuid        primary key default gen_random_uuid(),
  telegram_chat_id bigint      not null,
  thread_id        text        not null,
  created_at       timestamptz default now()
);

-- Mensajes: cada mensaje enviado o recibido
create table if not exists messages (
  id         uuid        primary key default gen_random_uuid(),
  session_id uuid        not null references sessions(id) on delete cascade,
  role       text        not null check (role in ('user', 'assistant')),
  content    text        not null,
  blocked    boolean     default false,
  created_at timestamptz default now()
);

-- Trazas: cada nodo del grafo LangGraph ejecutado
create table if not exists traces (
  id                uuid        primary key default gen_random_uuid(),
  session_id        uuid        not null references sessions(id) on delete cascade,
  message_id        uuid        not null references messages(id) on delete cascade,
  step_order        int         not null,
  node_name         text        not null,
  tool_name         text,
  started_at        timestamptz not null,
  ended_at          timestamptz not null,
  duration_ms       int         not null,
  input             jsonb,
  output            jsonb,
  prompt_tokens     int,
  completion_tokens int,
  company           text,
  model             text,
  created_at        timestamptz default now()
);

-- Precios por modelo: costo por 1 millón de tokens
create table if not exists model_pricing (
  id                      uuid    primary key default gen_random_uuid(),
  company                 text    not null,
  model                   text    not null,
  prompt_price_per_1m     numeric not null,
  completion_price_per_1m numeric not null,
  created_at              timestamptz default now(),
  unique (company, model)
);

insert into model_pricing (company, model, prompt_price_per_1m, completion_price_per_1m)
values
  ('openai',    'gpt-4o-mini',                0.15,  0.60),
  ('openai',    'gpt-4o',                     2.50, 10.00),
  ('openai',    'gpt-4-turbo',               10.00, 30.00),
  ('anthropic', 'claude-3-haiku-20240307',    0.25,  1.25),
  ('anthropic', 'claude-3-5-haiku-20241022',  0.80,  4.00),
  ('anthropic', 'claude-3-5-sonnet-20241022', 3.00, 15.00),
  ('anthropic', 'claude-3-opus-20240229',    15.00, 75.00)
on conflict (company, model) do nothing;

-- Evaluaciones: calidad de cada conversación (good/bad) generada por el pipeline de feedback
create table if not exists evaluations (
  id               uuid        primary key default gen_random_uuid(),
  session_id       uuid        not null unique references sessions(id) on delete cascade,
  verdict          text        not null check (verdict in ('good', 'bad')),
  score            int         not null check (score between 1 and 10),
  reason           text        not null,
  evaluator_model  text,
  diagnosed_file   text,
  suggestion       text,
  reviewer_model   text,
  reviewed_at      timestamptz,
  evaluated_at     timestamptz default now()
);

-- Costos: costo real por cada llamada al LLM
create table if not exists costs (
  id                uuid    primary key default gen_random_uuid(),
  session_id        uuid    not null references sessions(id) on delete cascade,
  message_id        uuid    not null references messages(id) on delete cascade,
  trace_id          uuid    not null references traces(id)   on delete cascade,
  company           text    not null,
  model             text    not null,
  prompt_tokens     int     not null,
  completion_tokens int     not null,
  prompt_cost       numeric not null,
  completion_cost   numeric not null,
  total_cost        numeric not null,
  created_at        timestamptz default now()
);
