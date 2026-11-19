"""Allowlisted diagnostics: never serialize driver messages, SQL or parameters."""
import re
import traceback
from pathlib import Path
import psycopg
import sqlalchemy as sa
from scripts.check_postgres import diagnose, MESSAGES

STATE_MESSAGES = {
    '42501': ('INSUFFICIENT_PRIVILEGE', 'Недостаточно прав для операции на указанном этапе.'),
    '42601': ('SQL_SYNTAX', 'PostgreSQL отклонил синтаксис SQL на указанном этапе.'),
    '42P01': ('TABLE_MISSING', 'Требуемая таблица отсутствует; это не повод запускать миграцию автоматически.'),
    '3F000': ('SCHEMA_MISSING', 'Требуемая схема отсутствует.'),
    '42704': ('OBJECT_MISSING', 'Требуемая роль или другой объект отсутствует.'),
    '42P06': ('SCHEMA_EXISTS', 'Схема уже существует. Перезапись запрещена.'),
    '42P07': ('TABLE_EXISTS', 'Таблица уже существует. Перезапись запрещена.'),
    '42710': ('OBJECT_EXISTS', 'Объект уже существует. Перезапись запрещена.'),
    '23503': ('FOREIGN_KEY', 'Нарушен внешний ключ тестовых данных.'),
    '23505': ('UNIQUE_KEY', 'Нарушено ограничение уникальности.'),
    '23502': ('NOT_NULL', 'Отсутствует обязательное значение.'),
    '23514': ('CHECK_CONSTRAINT', 'Нарушено проверочное ограничение.'),
    '25006': ('READ_ONLY_VIOLATION', 'Сервер отклонил запись в транзакции только чтения; режим не ослабляется.'),
    '25P02': ('TRANSACTION_ABORTED', 'Транзакция уже прервана предыдущей ошибкой.'),
    '55P03': ('LOCK_UNAVAILABLE', 'Не удалось получить блокировку; возможен lock_timeout.'),
    '57014': ('QUERY_CANCELLED', 'Запрос отменён сервером или истёк statement_timeout.'),
    '40P01': ('DEADLOCK', 'PostgreSQL обнаружил взаимную блокировку.'),
    '40001': ('SERIALIZATION_FAILURE', 'Конфликт параллельных транзакций.'),
    '0A000': ('FEATURE_UNSUPPORTED', 'Операция не поддерживается выбранным сервером или режимом подключения.'),
    'P0001': ('SQL_GUARD_REJECTED', 'SQL-проверка остановила операцию. Сначала проверь состояние только чтением.'),
}
SAFE_TYPES = (psycopg.Error, sa.exc.SQLAlchemyError, OSError, ValueError, TypeError,
              RuntimeError, ImportError, AssertionError)


def safe_diagnostic(error, phase):
    chain, pending, seen = [], [error], set()
    while pending and len(chain) < 12:
        item = pending.pop(0)
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        seen.add(id(item)); chain.append(item)
        pending.extend([getattr(item, 'orig', None), item.__cause__, item.__context__])
    states = [(item, getattr(item, 'sqlstate', None)) for item in chain if isinstance(item, psycopg.Error)]
    driver, state = next(((item, state) for item,state in states
                          if isinstance(state, str) and re.fullmatch('[0-9A-Z]{5}', state)), (None, None))
    code, message = STATE_MESSAGES.get(state, ('UNCLASSIFIED_EXCEPTION', 'Ошибка вне известных категорий; тип и место в коде указаны без текста исключения.'))
    for item in ([driver] if driver else chain):
        category = diagnose(item)
        if category != 'UNKNOWN' and state not in STATE_MESSAGES:
            code, message = category, MESSAGES[category]
            break
    if driver is not None:
        result_states = sorted({value for _,value in states if isinstance(value,str) and re.fullmatch('[0-9A-Z]{5}',value)})
    else:
        result_states = []
    if state == '42501':
        detail = str(driver).lower()  # Inspect only; never put this text in the report.
        for needle, tag, explanation in (
            ('permission denied to set role', 'ROLE_SWITCH_DENIED', 'Нет права SET ROLE для тестовой роли.'),
            ('permission denied to create role', 'ROLE_CREATE_DENIED', 'Нет права создавать роли (CREATEROLE).'),
            ('admin option', 'ROLE_ADMIN_REQUIRED', 'Для операции требуется ADMIN OPTION на роль.'),
            ('must be owner', 'OBJECT_OWNER_REQUIRED', 'Операция разрешена только владельцу объекта.'),
        ):
            if needle in detail:
                code, message = tag, explanation
                break
    if code == 'UNCLASSIFIED_EXCEPTION':
        for item in chain:
            if isinstance(item, PermissionError):
                code, message = 'LOCAL_FILE_ACCESS', 'Нет доступа к локальному файлу; путь скрыт.'
                break
            if isinstance(item, FileNotFoundError):
                code, message = 'LOCAL_FILE_MISSING', 'Не найден необходимый локальный файл; путь скрыт.'
                break
            if isinstance(item, (TypeError, ValueError)):
                code, message = 'LOCAL_TYPE_OR_VALUE', 'Ошибка типа или значения в Python; это не доказательство неверного пароля.'
                break
    # Class names are selected from trusted built-in/library classes, not arbitrary names.
    kind = next((base.__name__ for base in SAFE_TYPES if isinstance(driver or error, base)), 'Exception')
    result = {'phase':phase, 'code':code, 'sqlstate':state, 'exception_family':kind, 'message':message, 'related_sqlstates':result_states}
    if state:
        try:
            result['postgres_condition'] = psycopg.errors.lookup(state).__name__
        except KeyError:
            result['postgres_condition'] = 'UnlistedSQLSTATE'
    # Only known project filenames and numeric line numbers; no locals/source lines.
    allowed = {'run_stage.py', 'stage_learning_trial.py', 'stage_diagnostics.py', 'stage_state.py', 'stage_role_checks.py', 'check_postgres.py'}
    locations = []
    for item in chain:
        for frame in traceback.extract_tb(item.__traceback__):
            name = Path(frame.filename).name
            if name in allowed:
                location = {'file':name, 'line':frame.lineno}
                if location not in locations:
                    locations.append(location)
    result['locations'] = locations[-6:]
    return result
