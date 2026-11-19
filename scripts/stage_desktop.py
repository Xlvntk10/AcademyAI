"""Local credential form with paste support. No web server or stored secrets."""
import argparse
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from scripts import run_stage
from scripts.desktop_clipboard import bind_paste


def execute(ca_file, credentials, *, create=False):
    """Inspect first; any failure or existing object prevents stage creation."""
    provider = lambda: credentials
    if run_stage.main(['--inspect', '--ca-file', ca_file], credential_provider=provider):
        return 'Проверка не прошла. См. безопасный отчёт supabase-stage-inspection.json.'
    inspection = json.loads((run_stage.ROOT/'.test-artifacts/supabase-stage-inspection.json').read_text(encoding='utf8'))
    if not create:
        return 'Проверка только для чтения завершена. Состояние: ' + inspection['state']
    if inspection['state'] != 'absent':
        return 'Тестовые объекты уже существуют. Остановка без изменений; требуется проверка.'
    code = run_stage.main(['--ca-file', ca_file, '--allow-creator-set'], credential_provider=provider)
    if code:
        return 'Создание остановлено. См. безопасный отчёт supabase-stage-result.json. Не повторяйте запуск вслепую.'
    return 'Успех: stage создана, RLS и изоляция проверены, тестовые данные откатились. Личный профиль не переносился.'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-creator-set', action='store_true', help='Previously approved narrow SET grant and stage creation.')
    args = parser.parse_args(argv)
    show_form(execute, allow_create=args.allow_creator_set)


def show_form(executor, *, allow_create=False,
              title='Academy AI — безопасная настройка Supabase',
              heading='Подключение к тестовой среде Supabase',
              create_label='Создать stage и проверить', with_progress=False):
    window = tk.Tk()
    window.title(title)
    window.geometry('800x440')
    window.minsize(680, 420)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(0, weight=1)
    status = tk.StringVar(value='Сначала выполняется чтение. Изменения возможны только после успешной проверки.')
    ttk.Label(frame, text=heading, font=('Segoe UI', 14, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
    ttk.Label(frame, text='Вставка: Ctrl+V или кнопка «Вставить». Пароль скрыт и хранится только в памяти.').grid(row=1, column=0, columnspan=2, sticky='w')
    ttk.Label(frame, text='CA-сертификат Supabase').grid(row=2, column=0, sticky='w', pady=(12, 3))
    ca = ttk.Entry(frame)
    bind_paste(ca,status)
    ca.grid(row=3, column=0, sticky='ew')
    default_ca = Path.home()/'Downloads/prod-ca-2021.crt'
    if default_ca.is_file():
        ca.insert(0, str(default_ca))
    def choose_ca():
        selected = filedialog.askopenfilename(parent=window, title='CA-сертификат Supabase', filetypes=[('Сертификаты', '*.crt *.pem'), ('Все файлы', '*.*')])
        if selected:
            ca.delete(0, 'end')
            ca.insert(0, selected)
    browse = ttk.Button(frame, text='Выбрать файл', command=choose_ca)
    browse.grid(row=3, column=1, padx=(10, 0))
    ttk.Label(frame, text='Session pooler URI — оставьте [YOUR-DATABASE-PASSWORD] вместо пароля').grid(row=4, column=0, columnspan=2, sticky='w', pady=(12, 3))
    uri = ttk.Entry(frame)
    paste_uri = bind_paste(uri,status)
    uri.grid(row=5, column=0, sticky='ew')
    uri_paste = ttk.Button(frame, text='Вставить', command=paste_uri)
    uri_paste.grid(row=5, column=1, padx=(10, 0))
    ttk.Label(frame, text='Пароль базы PostgreSQL — вставьте отдельно').grid(row=6, column=0, sticky='w', pady=(12, 3))
    password = ttk.Entry(frame, show='●')
    paste_password = bind_paste(password,status)
    password.grid(row=7, column=0, sticky='ew')
    password_paste = ttk.Button(frame, text='Вставить', command=paste_password)
    password_paste.grid(row=7, column=1, padx=(10, 0))
    ttk.Label(frame, textvariable=status, wraplength=730).grid(row=9, column=0, columnspan=2, sticky='w', pady=15)
    messages = queue.Queue()
    running = False
    def start(create):
        nonlocal running
        if running:
            return
        credentials = (uri.get(), password.get())
        ca_file = ca.get()
        password.delete(0, 'end')
        running = True
        for widget in controls:
            widget.configure(state='disabled')
        status.set('Подключение и проверка… Дождитесь результата; окно пока не закрывайте.')
        def worker():
            nonlocal credentials
            try:
                kwargs = {'create':create}
                if with_progress:
                    kwargs['progress'] = lambda phase: messages.put(('progress', phase))
                message = executor(ca_file, credentials, **kwargs)
            except Exception:
                message = 'Локальная ошибка. Подробности скрыты для защиты реквизитов. Не повторяйте создание без проверки отчёта.'
            finally:
                credentials = None
            messages.put(('done', message))
        threading.Thread(target=worker, daemon=False).start()
    buttons = ttk.Frame(frame)
    buttons.grid(row=8, column=0, columnspan=2, sticky='w', pady=(18, 0))
    inspect_button = ttk.Button(buttons, text='Только проверить', command=lambda: start(False))
    inspect_button.pack(side='left')
    create_button = ttk.Button(buttons, text=create_label, command=lambda: start(True))
    create_button.pack(side='left', padx=10)
    if not allow_create:
        create_button.configure(state='disabled')
    controls = [ca, uri, password, browse, uri_paste, password_paste, inspect_button, create_button]
    def poll():
        nonlocal running
        try:
            kind, message = messages.get_nowait()
        except queue.Empty:
            pass
        else:
            if kind == 'progress':
                labels = {'LOCAL_BACKUP':'Создание и сверка резервной копии…',
                    'CONFIGURATION':'Проверка подключения и проекта…',
                    'READ_ONLY_PREFLIGHT':'Проверка аккаунта и пустой рабочей базы…',
                    'IDENTITY_AND_DESTINATION':'Повторная проверка перед записью…',
                    'CREATE_PRODUCTION_SCHEMAS':'Создание рабочих таблиц…',
                    'IMPORT_PROFILE_COPY':'Перенос копии профиля…',
                    'VERIFY_IMPORTED_VALUES':'Сверка всех записей и 40 XP…',
                    'COMMIT':'Фиксация проверенного переноса…',
                    'VERIFY_AFTER_COMMIT':'Проверка сохранённых данных после фиксации…'}
                status.set(labels.get(message, 'Проверка…'))
            else:
                running = False
                status.set(message)
                for widget in controls:
                    widget.configure(state='normal')
                if not allow_create:
                    create_button.configure(state='disabled')
        window.after(200, poll)
    def close():
        if running:
            status.set('Проверка выполняется. Дождитесь результата, чтобы не оставить неопределённый COMMIT.')
        else:
            password.delete(0, 'end')
            window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(200, poll)
    uri.focus_set()
    window.mainloop()


if __name__ == '__main__':
    main()
