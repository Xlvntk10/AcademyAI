"""Local-only text paste, including Windows non-Latin keyboard layouts."""
import tkinter as tk
import sys
from scripts.windows_clipboard import ClipboardFailure


def read_text(widget):
    if sys.platform == 'win32':
        from scripts.windows_clipboard import read_text as native_read
        return native_read()
    return widget.clipboard_get()


def copy_text(window, text, status, attempt=0, message='Скопировано в буфер Windows. Теперь можно вставить в другое приложение.'):
    try:
        if sys.platform == 'win32':
            from scripts.windows_clipboard import write_text
            write_text(window.winfo_id(),text)
        else:
            window.clipboard_clear()
            window.clipboard_append(text)
    except (tk.TclError,ClipboardFailure) as error:
        if str(error) == 'CLIPBOARD_BUSY' and attempt < 5:
            window.after(150,lambda:copy_text(window,text,status,attempt+1,message))
        else:
            status.set('Буфер Windows недоступен. Скопировать не удалось; попробуйте ещё раз.')
        return
    status.set(message)


def paste_text(entry, status, attempt=0):
    """Transfer clipboard directly to the field; never log or return its text."""
    if entry.instate(('disabled',)) or entry.instate(('readonly',)):
        status.set('Поле сейчас недоступно: дождитесь завершения проверки.')
        return 'break'
    try:
        text = read_text(entry)
    except (tk.TclError,ClipboardFailure) as error:
        if str(error) == 'CLIPBOARD_BUSY' and attempt < 5:
            entry.after(150,lambda:paste_text(entry,status,attempt+1))
        elif str(error) == 'NO_UNICODE_TEXT':
            status.set('Windows не видит скопированного текста. Выделите текст в Chrome и нажмите Ctrl+C, затем «Вставить».')
        else:
            status.set('Буфер Windows недоступен. Вставка не выполнена; попробуйте скопировать заново.')
        return 'break'
    if not text:
        status.set('Буфер обмена пуст. Сначала скопируйте нужное значение.')
        return 'break'
    if entry.selection_present():
        first = entry.index('sel.first')
        entry.delete('sel.first','sel.last')
        entry.icursor(first)
    entry.insert('insert',text)
    entry.focus_set()
    status.set('Текст вставлен. Содержимое скрытых полей не выводится в отчёт.')
    return 'break'


def bind_paste(entry, status):
    callback = lambda event=None:paste_text(entry,status)
    entry.bind('<<Paste>>',callback)
    entry.bind('<Shift-Insert>',callback)
    def control_key(event):
        # Windows virtual-key V/A stay unchanged with Russian/Kazakh layout.
        if event.keycode == 86 or event.keysym.lower() == 'v':
            return callback()
        if event.keycode == 65 or event.keysym.lower() == 'a':
            entry.selection_range(0,'end')
            return 'break'
        return None
    entry.bind('<Control-KeyPress>',control_key)
    menu = tk.Menu(entry,tearoff=False)
    menu.add_command(label='Вставить',command=callback)
    menu.add_command(label='Выделить всё',command=lambda:entry.selection_range(0,'end'))
    def context_menu(event):
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()
    entry.bind('<Button-3>',context_menu)
    return callback
