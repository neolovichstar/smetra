-- Workspace storage (archive flag and file source) and «Что нового» product updates.
-- Deployment gated on version 65. Additive only.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS archived_at bigint;
ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS smetra.changelog_posts (
 id text PRIMARY KEY,
 title text NOT NULL,
 body text NOT NULL,
 tag text NOT NULL DEFAULT '',
 author_id text REFERENCES smetra.users(id) ON DELETE SET NULL,
 published_at bigint NOT NULL,
 updated_at bigint NOT NULL,
 deleted_at bigint
);
CREATE INDEX IF NOT EXISTS idx_changelog_posts_published ON smetra.changelog_posts(published_at DESC);
CREATE TABLE IF NOT EXISTS smetra.changelog_views (
 post_id text NOT NULL REFERENCES smetra.changelog_posts(id) ON DELETE CASCADE,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 viewed_at bigint NOT NULL,
 PRIMARY KEY(post_id,user_id)
);
CREATE TABLE IF NOT EXISTS smetra.changelog_reactions (
 post_id text NOT NULL REFERENCES smetra.changelog_posts(id) ON DELETE CASCADE,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 reaction text NOT NULL CHECK(reaction IN ('up','love','fire','down')),
 created_at bigint NOT NULL,
 PRIMARY KEY(post_id,user_id)
);
-- Read and written only through the server connection, like the partner tables.
DO $private$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['changelog_posts','changelog_views','changelog_reactions'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC, anon, authenticated, smetra_runtime',t);
 END LOOP;
END $private$;
-- The first update in the feed.
INSERT INTO smetra.changelog_posts(id,title,body,tag,author_id,published_at,updated_at)
VALUES('release-2026-11-01','Хранилище файлов и «Что нового»',
'Всё, что вы прикрепляете, теперь собрано в одном месте.

## Хранилище
- **Изображения** — галерея всех фото, в том числе отправленных ассистенту в чате.
- **Файлы** — PDF, DOCX, XLSX, CSV, TXT и заметки карточками с иконкой формата.
- **Архив** — уберите редко нужное, файл останется в хранилище.
- Шкала показывает, сколько места занято и сколько осталось по тарифу.
- У каждого файла: открыть, **спросить ИИ**, перенести в архив или удалить.

## Что нового
Здесь будем рассказывать об обновлениях. Отмечайте реакцией, нравится ли изменение — мы читаем каждую.

## А ещё
- Интерфейс на телефоне стал компактнее, а нижняя панель — стеклянной.
- Новая иконка приложения и экран загрузки с каплями — их можно лопать.',
'Новое',NULL,extract(epoch FROM now())::bigint,extract(epoch FROM now())::bigint)
ON CONFLICT(id) DO NOTHING;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(65,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
