# Academy AI V5 — первый облачный запуск

Инструкция подготовлена 18 ноября 2026 года. Это план действий **после отдельного разрешения на публикацию и реальные миграции**. В рамках подготовки внешние ресурсы не создаются, push не выполняется.

## Архитектура и граница готовности

Основной `render.yaml` теперь описывает два сервиса:

1. Render Static Site `academy-ai-web`: React, TypeScript, Vite и публичные PWA-ресурсы.
2. Render Free Web Service `academy-ai-api`: FastAPI из `deploy/Dockerfile.api`, без постоянных файлов пользователя.
3. Supabase Free: PostgreSQL и Auth, подключение только с backend.

Браузер обращается к `/api` на **origin Static Site**. Правило Rewrite перенаправляет запрос внутри инфраструктуры на публичный HTTPS-адрес API. Cookie остаётся host-only, HttpOnly, Secure, SameSite=Strict. Не заменяйте Rewrite на Redirect, не добавляйте токены в localStorage и не ослабляйте SameSite ради обхода проблем iPhone.

Render документирует внешние адреса назначения Rewrite, но локальная имитация не подтверждает все свойства его CDN. До допуска реальных пользователей обязательно проверить передачу POST/body, Origin, If-Match, X-Academy-Account, Cookie/Set-Cookie и отсутствие кеширования персональных ответов. Если этот контракт не выполняется, раздельный вариант нельзя считать готовым. Сохранённый `deploy/render-single-origin.yaml` и корневой Dockerfile — вариант с одним origin FastAPI, который выбирается отдельно; это не подмена целевой архитектуры.

`deploy/render-static.yaml` предназначен только для отдельного создания Static Site вручную. **Не создавайте дубликат Static Site из него, если уже применили корневой Blueprint.**

## Бесплатный режим и ограничения

Ориентир — 0 ₸ в пределах Free для личного пилота, без гарантий непрерывной доступности. Проверено по официальной документации 18 ноября 2026 года; перед созданием ресурсов сверьте текущие условия.

- Render Free останавливает API после 15 минут без трафика; пробуждение занимает около минуты. Есть 750 бесплатных часов на workspace в месяц и квоты трафика/сборок. При платёжном методе возможны начисления за превышение квот: проверьте настройки расходов, не включайте платный план или дополнительные ресурсы. Без платёжного метода превышение может привести к остановке сервисов или сборок. Не используйте искусственные keep-alive-запросы. [Render Free](https://render.com/docs/free)
- Render Free не имеет постоянного диска и shell/one-off jobs. Миграции выполняются с доверенного компьютера, а не при старте API. SQLite на Render не используется для прогресса. SMTP с Render не отправляется — backend вызывает Supabase по HTTPS. [Ограничения Render](https://render.com/docs/free)
- Supabase Free: 500 MB базы, 50 000 MAU, 5 GB исходящего трафика, 1 GB файлового хранилища; неактивный проект может приостанавливаться через неделю. Учебный каталог сейчас копируется каждому владельцу, что учитывается в размере базы. [Supabase Pricing](https://supabase.com/pricing)
- Встроенная почта Supabase предназначена для пробного использования: только адреса участников команды проекта, обычно 2 письма в час на проект. Для произвольных пользователей нужен собственный SMTP/поддерживаемый email hook; бесплатность почты и домена не гарантируется. Подтверждение email не отключать. [Supabase SMTP](https://supabase.com/docs/guides/auth/auth-smtp)
- Бесплатные проекты должны иметь собственные регулярные выгрузки базы; нельзя рассчитывать на доступное восстановление из ежедневных dashboard-backup как на Pro. [Supabase Backups](https://supabase.com/docs/guides/platform/backups)

## Что получить от владельца

- Разрешение на push проверенных коммитов и публикацию существующего GitHub-репозитория в Render.
- Supabase Project URL и publishable key `sb_publishable_…`.
- Адрес **Session pooler**, порт 5432, project reference и административные реквизиты PostgreSQL.
- Отдельный пароль ограниченной роли `academy_runtime`.
- Публичные HTTPS-адреса будущих API и Static Site.
- Email для первого входа; выбор встроенной тестовой почты или собственного SMTP.
- Сопоставление каждого переносимого SQLite-файла и UUID владельца в Supabase Auth.
- Место для приватных резервных копий вне репозитория и дополнительная копия на другом носителе.

Секреты вводятся непосредственно в Render Environment или локальную защищённую сессию. Не присылайте их в отчёты, не помещайте в Git, `VITE_*`, браузерные конфиги или журналы.

## Переменные окружения

| Где | Переменная | Значение |
| --- | --- | --- |
| Backend | ACADEMY_ENV | production |
| Backend | ACADEMY_AUTH_MODE | supabase |
| Backend | ACADEMY_SERVE_FRONTEND | 0 |
| Backend | ACADEMY_PUBLIC_ORIGIN | Точный `https://STATIC-SITE.onrender.com`, без пути и завершающего `/` |
| Backend | DATABASE_URL | PostgreSQL session pooler, роль academy_runtime, TLS |
| Backend | SUPABASE_URL | `https://PROJECT_REF.supabase.co` |
| Backend | SUPABASE_PUBLISHABLE_KEY | Publishable key этого проекта |
| Static Site, сборка | NODE_VERSION | 22; поддерживаемая актуальная версия ветки |
| Static Site, сборка | VITE_ACCOUNT_MODE | supabase |
| Компьютер обслуживания | MIGRATION_DATABASE_URL | Отдельный административный PostgreSQL URL |

Не задавайте `ACADEMY_DATABASE_URL` на Render: эта переменная имеет приоритет над DATABASE_URL и может случайно выбрать старую SQLite. `ACADEMY_ACCOUNTS_DIR` нужен только для прежнего локального режима нескольких SQLite-профилей, в PostgreSQL-режиме он не используется. Приложение не загружает `.env` автоматически.

Пример runtime URL:

```text
postgresql+psycopg://academy_runtime.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=verify-full&sslrootcert=/etc/secrets/supabase-ca.pem
```

Пароль обязательно percent-encode. Production отклоняет SQLite и любой sslmode кроме verify-full. Используйте `sslmode=verify-full` с доверенным `sslrootcert`, подходящим для вашего Supabase/pooler: это дополнительно проверяет сервер. Для Linux можно использовать доверенный системный CA bundle, если цепочка pooler им подписана; для Windows задайте проверенный CA-файл. Локальная репетиция V5 использует `verify-full`; при ошибке сертификата исправьте цепочку/hostname, не отключайте проверку. [Подключения Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres)

Supabase `service_role`, секрет подписи JWT и пароль администратора не требуются runtime-приложению и не должны попадать во frontend.

## Supabase Auth

1. Создайте Free project только после разрешения. Сохраните пароль БД отдельно от кода.
2. Включите Email provider, подтверждение адреса и нужный режим регистрации.
3. Site URL — HTTPS-origin Static Site; Redirect URLs — точный `https://STATIC-SITE.onrender.com/auth/callback`, без wildcard. Для локальной проверки на 5173 см. [MAGIC_LINK_SETUP.md](MAGIC_LINK_SETUP.md).
4. Для входа по ссылке оставьте стандартные шаблоны Magic Link и Confirm signup с `{{ .ConfirmationURL }}`. Backend отправляет PKCE S256 challenge и обменивает одноразовый code на серверную сессию. Если нужен дополнительный числовой OTP, добавьте `{{ .Token }}` в текст письма; ссылка и код — отдельные способы входа. Старые письма без PKCE не поддерживаются.
5. Для личного теста проверьте, что почта получателя разрешена встроенным SMTP. Для других пользователей настройте свой SMTP в Supabase. Не выключайте Confirm email ради доставки.
6. Не экспортируйте схемы `academy`, `academy_auth`, `academy_migrations` через Supabase Data API. Схема Auth провайдера остаётся под его управлением.
7. Проверьте первый вход и повторный вход на том же email: это механизм восстановления доступа без собственного пароля приложения.

Backend проверяет токен запросом `/auth/v1/user` к выбранному Supabase, а не доверяет декодированному JWT с клиента. Клиент получает только непрозрачную cookie; её хеш и серверные токены хранятся в закрытой PostgreSQL-схеме. Обновление сессии сериализовано, аккаунт ответа проверяется. [Email OTP](https://supabase.com/docs/guides/auth/auth-email-passwordless)

## V6: сначала изолированная репетиция

Текущий безопасный этап описан в [V6_CLOUD_DATABASE.md](V6_CLOUD_DATABASE.md). SQL для `academy_stage` только подготовлен; выполнение в настоящем Supabase требует отдельного разрешения. Рабочие схемы, Auth и личный профиль пока не переносим.

Для Render добавьте в API → Environment → Secret Files файл `supabase-ca.pem` с доверенным публичным CA, которым успешно проверялся ваш pooler. Runtime-путь — `/etc/secrets/supabase-ca.pem`. Это сертификат CA, **не приватный ключ**. Его нельзя заменять случайным сертификатом или отключать verify-full. [Secret Files в Render](https://render.com/docs/configure-environment-variables#secret-files).

## Миграция PostgreSQL и права

Сначала репетиция на отдельной тестовой базе. В production выполнять только после разрешения и резервного копирования, при остановленной записи. Миграции не запускаются автоматически в Docker или Render.

```powershell
Set-Location 'C:\Users\user\OneDrive\Рабочий стол\academy ai'
$cloudSecret = Read-Host 'Административный PostgreSQL URL' -AsSecureString
$env:MIGRATION_DATABASE_URL = [System.Net.NetworkCredential]::new('', $cloudSecret).Password
.\.venv\Scripts\python.exe -m scripts.migrate_cloud
```

Cloud-ревизия — `cloud_0001`, SQLite — `0009_offline_sync`. В V5 схема учебных данных не менялась. Ревизии независимы.

В SQL Editor создайте ограниченную роль:

```sql
CREATE ROLE academy_runtime LOGIN NOINHERIT;
```

Задайте сильный пароль через защищённый инструмент управления ролями или интерактивную `\password academy_runtime` в psql. Затем выполните `deploy/grant_runtime.sql`. Роль не должна быть владельцем схем, иметь SUPERUSER/BYPASSRLS/CREATEROLE или членство в повышенных ролях. Backend проверяет опасные атрибуты при запуске.

```sql
SELECT rolname, rolsuper, rolbypassrls, rolcreaterole
FROM pg_roles WHERE rolname = 'academy_runtime';
```

Все три флага — false. Для pooler runtime-логин имеет вид `academy_runtime.PROJECT_REF`. Все 21 учебная таблица используют user_id, ключи владельца и принудительную RLS; owner-контекст задаётся на транзакцию.

## Перенос SQLite без потери прогресса

1. Остановите локальный API и отправьте очередь с каждого старого origin/устройства. Экспортируйте оставшиеся ответы.
2. Сохраните исходные SQLite и проверенные backup; не удаляйте их после переноса.
3. Получите подтверждённый UUID пользователя из Supabase Authentication → Users. Подготовьте профиль до первого входа этого пользователя в облачное приложение, иначе там уже будет создан пустой профиль и импорт откажется перезаписывать его.
4. Проведите импорт копии в отдельную тестовую PostgreSQL. Сверьте данные и API-статистику.
5. После разрешения повторите процедуру в целевой базе при остановленном API. Важно: у текущего пользователя 40 XP в отдельном файле `%LOCALAPPDATA%\AcademyAI\accounts\<UUID>.db`. Корневая `database.db` содержит другой профиль с 50 XP. Не подставляйте её вместо аккаунтного файла. В `$profileCopy` укажите проверенную копию именно нужного профиля:

```powershell
$profileCopy = Read-Host 'Полный путь к проверенной копии профиля с 40 XP (без внешних кавычек)'
.\.venv\Scripts\python.exe -m scripts.import_cloud `
  --source $profileCopy `
  --user-id 'ПРОВЕРЕННЫЙ-UUID-ВЛАДЕЛЬЦА' `
  --backup-dir '.\backups\cloud-import'
```

Повторите для каждого существующего SQLite-профиля с его владельцем. Команда делает backup, проверяет целостность, переносит одной транзакцией, сравнивает все строки и повторно сверяет источник перед commit. Существующий профиль не перезаписывается. Сохраняются уроки, попытки, расписание, словарь, настройки, UUID и подтверждения офлайн-попыток. XP и streak вычисляются из сохранённых записей, а не импортируются как произвольные числа. Демонстрационные попытки остаются вне настоящего XP.

Cookie прежних локальных сессий не переносятся: потребуется вход. IndexedDB привязана к адресу сайта; автоматического переноса на новый домен и слияния двух существующих профилей нет.

## Безопасное подключение GitHub и Render

После отдельного разрешения:

1. В существующем репозитории проверьте ветку, diff и отсутствие секретов/баз среди tracked-файлов. Не загружайте `.test-artifacts`, backups, `.env`, `.accounts` и `.venv`.
2. Выполните согласованный push проверенных коммитов в существующую ветку `feature/academy-ai-v2`.
3. Подключите Render GitHub App только к этому репозиторию; не выдавайте доступ ко всем репозиториям без необходимости.
4. Создавайте ровно один Free Web Service и один Static Site. Постоянный диск, Render PostgreSQL, платные планы и дополнительные экземпляры не нужны.
5. В интерфейсе Render сначала получите имена/адреса сервисов. В `render.yaml` замените `REPLACE-API-HOST.onrender.com` на фактический публичный HTTPS API-host. Затем сохраните согласованный конфиг в Git. Blueprint не может подставить env-переменную в URL rewrite.
6. Для API укажите ACADEMY_PUBLIC_ORIGIN равным адресу Static Site, остальные значения — в Environment. Не указывайте в Static Site никакие DB/Auth секреты.
7. Отключите автоматические deploy и автоматический Blueprint Sync до завершения первой проверки. В файле autoDeployTrigger уже off. Не включайте previews с production-секретами.

Ручные настройки, если Blueprint не используется:

| Параметр | Static Site | Web Service |
| --- | --- | --- |
| Ветка | feature/academy-ai-v2 | feature/academy-ai-v2 |
| Корневая папка | Корень репозитория | Корень репозитория |
| Runtime | Static | Docker |
| Dockerfile | — | deploy/Dockerfile.api |
| Docker context | — | Корень репозитория |
| Build command | npm --prefix frontend ci && npm --prefix frontend run build | Из Dockerfile |
| Publish directory | frontend/dist | — |
| План | Static Site Free | Free |
| Регион | CDN | Frankfurt или близкий регион Supabase |
| Health check | — | /api/health |
| Start | — | Uvicorn на $PORT, 1 worker |

На Static Site первое правило — **Rewrite `/api/*` → `https://API-HOST/api/*`**, второе — **Rewrite `/*` → `/index.html`**. Примените headers из render.yaml. API всегда выдаёт no-store для браузера и CDN. HTTPS на Render управляется провайдером. [Blueprint](https://render.com/docs/blueprint-spec), [Rewrite](https://render.com/docs/redirects-rewrites)

## Проверка после публикации — обязательный допуск

Первая проверка не отправляет email и не меняет учебные данные:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_deployment --url 'https://STATIC-SITE.onrender.com'
```

Утилита проверяет HTTPS-сертификат, HTML-маршруты, ресурсы PWA, cloud schema, режим аккаунтов, запрет анонимного доступа, no-store и отклонение запроса с чужого Origin. При пробуждении Free API может потребоваться повтор через минуту. Она не заменяет реальную проверку входа и устройств.

Затем вручную:

- [ ] В адресной строке только HTTPS; root, /today, /learn, /plan, /progress открываются.
- [ ] Запрос Magic Link, переход по последнему письму в том же браузере и открытие профиля проходят. В Network запросы идут на `/api` Static Site и возвращают JSON, а не HTML.
- [ ] Ответ exchange (либо verify для OTP) передаёт Secure/HttpOnly/SameSite=Strict cookie без Domain; последующий session возвращает того же пользователя. API-ответы не кешируются CDN.
- [ ] После обновления страницы вход сохраняется. Выход отзывает конкретную сессию, второе устройство продолжает работать.
- [ ] Windows завершает урок; iPhone с тем же аккаунтом получает XP, streak и план.
- [ ] iPhone скачивает урок, сохраняет черновик и отвечает без сети; после подключения результат подтверждается. Повторная отправка не добавляет XP.
- [ ] Windows получает изменения телефона; конфликт плана предлагает перечитать данные, а не молча перезаписывает их.
- [ ] Другой аккаунт не видит чужие результаты, историю, план и очередь.
- [ ] PWA устанавливается в Edge/Chrome на Windows и через Safari «Поделиться → На экран Домой» на iPhone; после закрытия и отключения сети открывается через иконку.
- [ ] Новая версия PWA предлагается уведомлением; незавершённые ответы не теряются.
- [ ] После сна Render и пробуждения состояние восстанавливается; пользователь видит понятную ошибку/повтор, а не ложный успех.
- [ ] Подтверждённый backup хранится вне хостинга, пробное восстановление прошло.

Пока хотя бы передача cookie/no-store через Render или изоляция аккаунтов не подтверждены, реальные данные не переводить на новый origin.

## Backup, восстановление и откат

pg_dump/pg_restore должны быть той же или более новой основной версии, чем сервер. Архив содержит личные данные и серверные сессии: храните его приватно и отдельно от компьютера. Supabase Auth-пользователи находятся вне трёх Academy-схем, этот архив не является резервной копией всего провайдера Auth.

```powershell
# MIGRATION_DATABASE_URL задан безопасно, pg_dump/pg_restore находятся в PATH.
.\.venv\Scripts\python.exe -m scripts.cloud_backup backup '.\backups\academy-before-release.dump'
# При необходимости добавьте --bin-dir 'C:\path\to\postgresql\bin'.
```

Файл не перезаписывается; проверяются формат архива и возможность чтения. Делайте копию перед каждой миграцией/импортом/релизом и регулярно после занятий.

Если ошибочен только код, верните предыдущие проверенные backend/frontend-коммиты без отката данных. Если повреждены данные:

1. Остановите запись, сохраните отдельный backup текущего состояния и очереди устройств.
2. Подготовьте отдельную пустую PostgreSQL с тем же доверенным Auth-проектом. Не восстанавливайте поверх рабочей базы.
3. Укажите URL назначения в MIGRATION_DATABASE_URL и выполните:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_backup restore '.\backups\academy-before-release.dump'
```

4. Примените grant_runtime.sql, проверьте RLS, владельцев, строки, XP/streak и /api/health ограниченной ролью.
5. Переключите DATABASE_URL на проверенную базу и совместимую версию API. Не переключайте Auth-проект: UUID/realm должны совпадать.
6. Сохраните проблемную базу для сверки записей, появившихся после backup. Автоматического обратного переноса PostgreSQL → SQLite нет.
7. Не считайте новую копию автоматически содержащей все поздние результаты: сверяйте их отдельно и только после этого разрешайте запись.

После обслуживания удалите секретные переменные из текущего терминала:

```powershell
Remove-Item Env:MIGRATION_DATABASE_URL -ErrorAction SilentlyContinue
```

## Непроверенные внешние части

Локальные HTTPS/TLS, cookie-прокси, миграции, импорт, обновление сессий и два клиента проверяются отдельно от внешней среды. Реальные Render rewrite/CDN, Supabase pooler/SMTP, установка на физических iPhone/Windows, Docker/Linux требуют проверки после разрешения и получения конфигурации. Нельзя считать локальную имитацию проверкой опубликованной системы.
