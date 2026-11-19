"""Local credential handoff for the restricted backend login; no secret files."""
import queue
import json
import secrets
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from scripts.runtime_setup import execute
from scripts.desktop_clipboard import bind_paste, copy_text, read_text
from scripts.windows_clipboard import ClipboardFailure
from scripts.check_postgres import validate_visible_uri, ConfigurationError


def main():
    window = tk.Tk()
    window.title('Academy AI — доступ приложения к Supabase')
    window.geometry('850x640')
    frame = ttk.Frame(window,padding=20)
    frame.pack(fill='both',expand=True)
    frame.columnconfigure(0,weight=1)
    ttk.Label(frame,text='Отдельный доступ для Academy AI',font=('Segoe UI',14,'bold')).grid(row=0,column=0,columnspan=2,sticky='w')
    ttk.Label(frame,text='Создаётся academy_runtime без административных прав. Перенос данных не повторяется.\nПароли и строка подключения остаются только в памяти этого окна.',wraplength=800).grid(row=1,column=0,columnspan=2,sticky='w',pady=10)
    fields = {}
    controls = []
    status = tk.StringVar(value='Вставка: кнопкой «Вставить», Ctrl+V, Shift+Insert или правой кнопкой мыши.')
    for index,(key,label,masked) in enumerate([
        ('ca','CA-сертификат Supabase',False),
        ('uri','Session pooler URI с [YOUR-DATABASE-PASSWORD] вместо пароля',False),
        ('admin','Пароль администратора PostgreSQL',True),
        ('runtime','Новый пароль приложения — сохраните в своём менеджере паролей',True),
    ]):
        row = 2+index*2
        ttk.Label(frame,text=label).grid(row=row,column=0,columnspan=2,sticky='w',pady=(8,3))
        entry = ttk.Entry(frame,show='●' if masked else '')
        entry.grid(row=row+1,column=0,sticky='ew')
        fields[key] = entry
        controls.append(entry)
        paste = bind_paste(entry,status)
        if key in ('uri','admin'):
            button = ttk.Button(frame,text='Вставить',command=paste)
        elif key == 'ca':
            def choose():
                path = filedialog.askopenfilename(parent=window,title='CA-сертификат',filetypes=[('Сертификат','*.pem *.crt')])
                if path:
                    fields['ca'].delete(0,'end'); fields['ca'].insert(0,path)
            button = ttk.Button(frame,text='Выбрать',command=choose)
        else:
            def copy_password():
                copy_text(window,fields['runtime'].get(),status)
            button = ttk.Button(frame,text='Копировать пароль',command=copy_password)
        button.grid(row=row+1,column=1,padx=10)
        controls.append(button)
    ca = Path.home()/'Downloads/prod-ca-2021.crt'
    if ca.is_file():
        fields['ca'].insert(0,str(ca))
    fields['runtime'].insert(0,secrets.token_urlsafe(36))
    # Optional local convenience profile: only a URI with a password placeholder.
    # The executor still verifies that the project matches the local account.
    try:
        settings = json.loads((Path(__file__).resolve().parents[1]/'.test-artifacts/runtime-connection.json').read_text(encoding='utf8'))
        fields['uri'].insert(0,validate_visible_uri(settings['uri']))
    except (OSError,ValueError,KeyError,ConfigurationError):
        pass
    saved = tk.BooleanVar(value=False)
    saved_box = ttk.Checkbutton(frame,text='Я сохранил новый пароль приложения вне чата',variable=saved)
    saved_box.grid(row=10,column=0,columnspan=2,sticky='w',pady=10)
    controls.append(saved_box)
    ttk.Label(frame,textvariable=status,wraplength=790).grid(row=12,column=0,columnspan=2,sticky='w',pady=12)
    messages = queue.Queue()
    running = False
    terminal = False
    private_url = None
    def start(create):
        nonlocal running
        if running or terminal:
            return
        if create and not saved.get():
            status.set('Сохраните новый пароль приложения и поставьте отметку выше.')
            return
        values = {key:entry.get() for key,entry in fields.items()}
        fields['admin'].delete(0,'end')
        running = True
        for control in controls:
            control.configure(state='disabled')
        status.set('Проверка базы и резервной копии… Не закрывайте окно.')
        def worker():
            try:
                result = execute(values['ca'],(values['uri'],values['admin']),values['runtime'],create=create,
                    progress=lambda phase:messages.put(('progress',phase)))
                messages.put(('done',result))
            except Exception:
                messages.put(('done',({'status':'local_error_review_before_retry'},None)))
            finally:
                values.clear()
        threading.Thread(target=worker,daemon=False).start()
    buttons = ttk.Frame(frame)
    buttons.grid(row=11,column=0,columnspan=2,sticky='w')
    inspect = ttk.Button(buttons,text='Только проверить',command=lambda:start(False))
    inspect.pack(side='left')
    create = ttk.Button(buttons,text='Создать ограниченный доступ',command=lambda:start(True))
    create.pack(side='left',padx=12)
    controls.extend((inspect,create))
    def copy_url():
        if private_url:
            copy_text(window,private_url,status,message='Строка подключения скопирована. Вставляйте только в DATABASE_URL сервера Render, не в чат.')
    copy = ttk.Button(frame,text='Копировать DATABASE_URL для Render',command=copy_url,state='disabled')
    copy.grid(row=13,column=0,columnspan=2,sticky='w')
    def poll():
        nonlocal running,terminal,private_url
        try:
            kind,value = messages.get_nowait()
        except queue.Empty:
            pass
        else:
            if kind == 'progress':
                labels = {'CONFIGURATION':'Проверка защищённого подключения…',
                    'READ_ONLY_PREFLIGHT':'Сверка 40 XP и текущих прав…',
                    'CREATE_RESTRICTED_LOGIN':'Создание отдельного логина приложения…',
                    'COMMIT':'Сохранение проверенных прав…',
                    'VERIFY_ACTUAL_LOGIN':'Вход новым логином, проверка изоляции и отката…'}
                status.set(labels.get(value,'Проверка…'))
            else:
                running = False
                report,private_url = value
                state = report['status']
                terminal = state != 'inspection_passed'
                if state == 'passed':
                    status.set('Готово: отдельный вход работает, 40 XP сохранены, изоляция и откат проверены. Сохраните это окно до заполнения Render.')
                elif state == 'inspection_passed':
                    status.set('Проверка пройдена, изменений нет. Для создания введите пароль администратора ещё раз и нажмите «Создать ограниченный доступ».')
                    for control in controls:
                        control.configure(state='normal')
                else:
                    status.set('Остановка: '+state+' / '+report.get('error','LOCAL_ERROR')+'. Не повторяйте создание: сначала нужен разбор безопасного отчёта.')
                if private_url:
                    copy.configure(state='normal')
        window.after(200,poll)
    def close():
        nonlocal private_url
        if running:
            status.set('Дождитесь результата, чтобы не прервать проверку после сохранения прав.')
            return
        # Clear only this form's credential, never unrelated clipboard content.
        try:
            clipboard = read_text(window)
            if clipboard in (private_url,fields['runtime'].get()):
                window.clipboard_clear()
        except (tk.TclError,ClipboardFailure):
            pass
        private_url = None
        window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    window.after(200,poll)
    window.mainloop()


if __name__ == '__main__':
    main()
