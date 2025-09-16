"""
Python Scheduler GUI per Windows
- Permette di programmare spegnimento o ibernazione in orari e giorni specifici
- Salva la configurazione in %APPDATA%\PyShutdownScheduler\config.json
- Opzione per abilitare/disabilitare l'avvio automatico all'accesso (scrive nel registro HKCU Run)

Requisiti: Python 3.8+, Windows
Nota: per compilare in .exe usa PyInstaller (istruzioni nel README sotto).
"""

import os
import sys
import json
import time
import threading
import datetime
import subprocess
import pystray
from PIL import Image, ImageTk, ImageDraw
from pathlib import Path
import winreg
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    from tkinter import font as tkfont
except Exception as e:
    raise SystemExit("Tkinter non trovato. Assicurati di avere Python con Tkinter installato.")

# moduli win-specific
if sys.platform != "win32":
    raise SystemExit("Questa applicazione è pensata per Windows.")

import winreg

APP_NAME = "ShutdownScheduler"
CONFIG_DIR = Path(os.getenv('APPDATA')) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
REGISTRY_RUN_KEY = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
REGISTRY_VALUE_NAME = "ShutdownScheduler"

DEFAULT_CONFIG = {
    "schedules": [],
    "autostart": False
}

# utilità per registry autostart

def set_autostart(enabled: bool):
    """Aggiunge o rimuove la chiave di Run per l'avvio automatico dell'app.
    Usa sys.executable e il percorso dello script. Quando compilato con PyInstaller,
    sys.executable punta all'.exe risultante.
    """
    exe_path = getattr(sys, 'frozen', False) and sys.executable or os.path.abspath(sys.argv[0])
    # se non è un exe, meglio usare pythonw per non mostrare console
    if not getattr(sys, 'frozen', False):
        pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
        if os.path.exists(pythonw):
            cmd = f'"{pythonw}" "{exe_path}"'
        else:
            cmd = f'"{sys.executable}" "{exe_path}"'
    else:
        cmd = f'"{exe_path}"'

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN_KEY, 0, winreg.KEY_WRITE) as key:
            if enabled:
                winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print('Errore registry autostart:', e)
        return False


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception:
        return False


# utilità per salvare e caricare config

def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                return cfg
        except Exception:
            return DEFAULT_CONFIG.copy()
    else:
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# scheduler runtime
class SchedulerThread(threading.Thread):
    def __init__(self, get_schedules_callable, stop_event):
        super().__init__(daemon=True)
        self.get_schedules = get_schedules_callable
        self.stop_event = stop_event
        # memorizza l'ultimo minuto in cui abbiamo eseguito un'azione per evitare ripetizioni
        self.last_executed = {}

    def run(self):
        while not self.stop_event.is_set():
            now = datetime.datetime.now()
            current_day = now.weekday()  # lun=0 .. dom=6
            current_time = now.strftime('%H:%M')
            schedules = self.get_schedules()
            for idx, s in enumerate(schedules):
                days = s.get('days', [])
                time_str = s.get('time')
                action = s.get('action')
                enabled = s.get('enabled', True)
                if not enabled:
                    continue
                # check giorno
                if current_day in days and current_time == time_str:
                    key = f"{idx}-{time_str}"
                    last = self.last_executed.get(key)
                    # esegui se non eseguito nello stesso minuto
                    if last != now.strftime('%Y%m%d%H%M'):
                        print(f"Eseguo azione: {action} alle {time_str} ({now})")
                        try:
                            perform_action(action)
                        except Exception as e:
                            print('Errore esecuzione azione:', e)
                        self.last_executed[key] = now.strftime('%Y%m%d%H%M')
            # sleep per evitare CPU busy
            time.sleep(1)


# azioni di sistema

def perform_action(action_name: str):
    """Esegue l'azione: 'shutdown' o 'hibernate'. Mostra prima un avviso di 20 secondi.
    """
    if action_name not in ('shutdown', 'hibernate'):
        return
    # notifica all'utente
    try:
        # usa msgbox asincrono
        threading.Thread(target=lambda: messagebox.showinfo('ShutdownScheduler', f"Il PC verrà { 'spento' if action_name=='shutdown' else 'ibernato' } tra 20 secondi."), daemon=True).start()
    except Exception:
        pass
    # attesa breve per dare il tempo all'utente
    time.sleep(20)

    if action_name == 'shutdown':
        # forza chiusura applicazioni
        subprocess.run(['shutdown', '/s', '/f', '/t', '0'])
    elif action_name == 'hibernate':
        # hibernate richiede che l'ibernazione sia abilitata in Windows
        subprocess.run(['shutdown', '/h'])


# GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Shutdown Scheduler')
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.setup_dpi_awareness()
        self.configure(bg='#000000')
        # calcolo fattore scala UI da Tk
        try:
            self.ui_scale = float(self.tk.call('tk', 'scaling'))
        except Exception:
            self.ui_scale = 1.0
        # aumento dimensioni UI globalmente
        self.user_scale_boost = 1.3
        self.ui_scale = max(1.0, min(2.5, self.ui_scale * self.user_scale_boost))
        # applica dimensioni finestra in base alla scala
        base_w, base_h = 760, 500
        width = max(640, int(base_w * self.ui_scale))
        height = max(440, int(base_h * self.ui_scale))
        self.geometry(f"{width}x{height}")
        try:
            self.minsize(int(560 * self.ui_scale), int(400 * self.ui_scale))
        except Exception:
            pass

        self.cfg = load_config()
        # ensure schedules format
        if 'schedules' not in self.cfg:
            self.cfg['schedules'] = []
        if 'autostart' not in self.cfg:
            self.cfg['autostart'] = False

        self.setup_theme()
        self.create_widgets()

        # scheduler thread
        self.stop_event = threading.Event()
        self.scheduler = SchedulerThread(self.get_schedules, self.stop_event)
        self.scheduler.start()

        # sync autostart state
        self.autostart_var.set(is_autostart_enabled())

        # Crea l'icona per la system tray
        self.create_tray_icon()

    def create_widgets(self):
        frm = ttk.Frame(self, padding=self.scale(12), style='Amoled.TFrame')
        frm.pack(fill='both', expand=True)

        top = ttk.Label(frm, text='Programma spegnimento / ibernazione', font=self.font_title, style='Amoled.TLabel')
        top.pack(anchor='w')
        sub = ttk.Label(frm, text='Aggiungi una pianificazione, scegli giorni, orario e azione.', style='Amoled.TLabel', font=self.font_small)
        sub.pack(anchor='w', pady=(self.scale(2), self.scale(8)))

        # toolbar superiore
        toolbar = ttk.Frame(frm, style='Amoled.TFrame')
        toolbar.pack(fill='x', pady=(0, self.scale(6)))
        btn_add = ttk.Button(toolbar, text='➕  Aggiungi', command=self.add_schedule)
        btn_edit = ttk.Button(toolbar, text='✎  Modifica', command=self.edit_schedule)
        btn_del = ttk.Button(toolbar, text='🗑  Rimuovi', command=self.remove_schedule)
        btn_add.pack(side='left', padx=(0, self.scale(8)))
        btn_edit.pack(side='left', padx=(0, self.scale(8)))
        btn_del.pack(side='left')
        # tooltips
        for widget, tip in ((btn_add, 'Crea una nuova pianificazione (Ctrl+N)'),
                            (btn_edit, 'Modifica la voce selezionata (Invio/doppio clic)'),
                            (btn_del, 'Rimuove la voce selezionata (Canc)')):
            try:
                Tooltip(widget, tip)
            except Exception:
                pass

        ttk.Separator(frm, orient='horizontal').pack(fill='x', pady=(0, self.scale(8)))

        # lista schedule con scrollbar
        list_wrap = ttk.Frame(frm, style='Amoled.TFrame')
        list_wrap.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(list_wrap, columns=('days', 'time', 'action', 'enabled'), show='headings', selectmode='browse')
        self.tree.heading('days', text='Giorni')
        self.tree.heading('time', text='Orario')
        self.tree.heading('action', text='Azione')
        self.tree.heading('enabled', text='Attivo')
        self.tree.column('days', width=self.scale(220), anchor='w', stretch=True)
        self.tree.column('time', width=self.scale(120), anchor='center', stretch=False)
        self.tree.column('action', width=self.scale(160), anchor='w', stretch=False)
        self.tree.column('enabled', width=self.scale(110), anchor='center', stretch=False)
        vsb = ttk.Scrollbar(list_wrap, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True, pady=self.scale(8))
        vsb.pack(side='right', fill='y', pady=self.scale(8))
        # righe alternate
        try:
            self.tree.tag_configure('odd', background='#0a0a0a')
            self.tree.tag_configure('even', background='#131313')
        except Exception:
            pass
        # scorciatoie e azioni rapide
        self.tree.bind('<Double-1>', lambda e: self.edit_schedule())
        self.tree.bind('<Return>', lambda e: self.edit_schedule())
        self.tree.bind('<Delete>', lambda e: self.remove_schedule())

        # barra sotto rimossa su richiesta

        bottom = ttk.Frame(frm, style='Amoled.TFrame')
        bottom.pack(fill='x', side='bottom', pady=self.scale(8))

        self.autostart_var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(bottom, text="Avvia automaticamente all'accesso (Autostart)", variable=self.autostart_var, command=self.toggle_autostart)
        cb.pack(anchor='w')



        # barra di stato
        self.status_var = tk.StringVar(value='Pronto')
        status_bar = ttk.Frame(self, style='Amoled.TFrame')
        status_bar.pack(fill='x', side='bottom')
        status = ttk.Label(status_bar, textvariable=self.status_var, anchor='w', style='Amoled.TLabel')
        status.pack(fill='x', side='left', padx=self.scale(8), pady=(0, self.scale(6)))
        try:
            ttk.Sizegrip(status_bar).pack(side='right', anchor='se', padx=self.scale(4), pady=self.scale(2))
        except Exception:
            pass

        # menu contestuale
        self._build_context_menu()
        self.tree.bind('<Button-3>', self._show_context_menu)

        # scorciatoie globali
        self.bind_all('<Control-n>', lambda e: self.add_schedule())
        self.bind_all('<Control-e>', lambda e: self.edit_schedule())

        # wrapping dinamico della nota in base alla larghezza disponibile
        self.bind('<Configure>', self._on_resize)

        # riempi tree
        self.refresh_tree()

    def get_schedules(self):
        return self.cfg.get('schedules', [])

    def refresh_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        data = self.cfg.get('schedules', [])
        for idx, s in enumerate(data):
            days = s.get('days', [])
            days_str = days_to_string(days)
            time_str = s.get('time')
            action = 'Spegni' if s.get('action') == 'shutdown' else 'Ibernazione'
            enabled = 'Sì' if s.get('enabled', True) else 'No'
            tag = 'odd' if idx % 2 else 'even'
            self.tree.insert('', 'end', iid=str(idx), values=(days_str, time_str, action, enabled), tags=(tag,))
        self._update_status()

    def add_schedule(self):
        """Apre la finestra di dialogo per aggiungere una nuova pianificazione."""
        try:
            dlg = ScheduleDialog(self, None)
            self.wait_window(dlg)
            if hasattr(dlg, 'result') and dlg.result:
                # Assicurati che la chiave 'schedules' esista nel dizionario di configurazione
                if 'schedules' not in self.cfg:
                    self.cfg['schedules'] = []
                
                # Aggiungi la nuova pianificazione
                self.cfg['schedules'].append(dlg.result)
                
                # Salva la configurazione
                save_config(self.cfg)
                
                # Aggiorna la visualizzazione
                self.refresh_tree()
                
                # Log per debug
                print("Nuova pianificazione aggiunta:", dlg.result)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aggiungere la pianificazione: {str(e)}")
            print("Errore in add_schedule:", str(e))

    def edit_schedule(self):
        """Modifica una pianificazione esistente."""
        try:
            # Ottieni la selezione corrente
            sel = self.tree.selection()
            if not sel:
                messagebox.showwarning('Attenzione', 'Seleziona una pianificazione da modificare')
                return
                
            # Ottieni l'indice della pianificazione selezionata
            idx = int(sel[0])
            
            # Crea una copia della pianificazione esistente per evitare modifiche dirette
            schedule = self.cfg['schedules'][idx].copy()
            
            # Apri la finestra di dialogo di modifica
            dlg = ScheduleDialog(self, schedule)
            self.wait_window(dlg)
            
            # Se l'utente ha confermato le modifiche
            if hasattr(dlg, 'result') and dlg.result:
                # Aggiorna la pianificazione esistente
                self.cfg['schedules'][idx] = dlg.result
                
                # Salva le modifiche
                save_config(self.cfg)
                
                # Aggiorna la visualizzazione
                self.refresh_tree()
                
                print("Pianificazione aggiornata:", dlg.result)  # Debug
                
        except IndexError:
            messagebox.showerror('Errore', 'Impossibile trovare la pianificazione selezionata')
        except Exception as e:
            messagebox.showerror('Errore', f'Si è verificato un errore durante la modifica: {str(e)}')
            print("Errore in edit_schedule:", str(e))  # Debug

    def remove_schedule(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('Attenzione', 'Seleziona una voce da rimuovere')
            return
        idx = int(sel[0])
        if messagebox.askyesno('Conferma', 'Rimuovere la voce selezionata?'):
            del self.cfg['schedules'][idx]
            save_config(self.cfg)
            self.refresh_tree()

    def run_selected_now(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('Attenzione', 'Seleziona una voce')
            return
        idx = int(sel[0])
        s = self.cfg['schedules'][idx]
        perform_action(s.get('action'))

    def toggle_autostart(self):
        enabled = self.autostart_var.get()
        ok = set_autostart(enabled)
        if not ok:
            messagebox.showerror("Errore", "Impossibile modificare l'autostart. Esegui come utente con permessi normali e riprova.")
            # ripristina stato reale
            self.autostart_var.set(is_autostart_enabled())
        else:
            self.cfg['autostart'] = enabled
            save_config(self.cfg)
            messagebox.showinfo('Autostart', 'Impostazione autostart aggiornata.')
        self._update_status()

    def on_close(self, event=None):
        """Minimizza nella system tray invece di chiudere."""
        self.withdraw()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.update_menu()
            
    def show_window(self, icon=None, item=None):
        """Ripristina la finestra dalla system tray."""
        self.deiconify()
        self.lift()
        self.focus_force()
        
    def quit_app(self, icon=None, item=None):
        """Chiude completamente l'applicazione."""
        # Salva la configurazione
        save_config(self.cfg)
        
        # Ferma il thread dello scheduler
        self.stop_event.set()
        if self.scheduler.is_alive():
            self.scheduler.join(timeout=2.0)
        
        # Chiudi l'icona nella system tray
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        
        # Chiudi l'applicazione
        self.quit()
        self.destroy()
        
    def create_tray_icon(self):
        """Crea l'icona per la system tray."""
        # Crea un'immagine di default (un cerchio blu con 'S' bianca)
        width = 64
        height = 64
        color1 = '#3498db'
        color2 = 'white'
        
        # Crea un'immagine di default
        image = Image.new('RGB', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.rectangle([(0, 0), (width, height)], fill=color1)
        dc.text((width/2, height/2), 'S', fill=color2, font=None, anchor='mm')
        
        # Crea il menu della system tray
        menu = (
            pystray.MenuItem('Mostra', self.show_window, default=True),
            pystray.MenuItem('Esci', self.quit_app)
        )
        
        # Crea e avvia l'icona nella system tray
        self.tray_icon = pystray.Icon("shutdown_scheduler", image, "Shutdown Scheduler", menu)
        
        # Avvia l'icona in un thread separato
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
        # Mostra una notifica all'avvio
        self.after(1000, self.show_startup_notification)
        
    def show_startup_notification(self):
        """Mostra una notifica all'avvio."""
        if hasattr(self, 'tray_icon'):
            try:
                self.tray_icon.notify(
                    "Shutdown Scheduler è in esecuzione",
                    "Clicca sull'icona nella system tray per aprire il pannello di controllo."
                )
            except:
                # Se le notifiche non funzionano, ignoriamo l'errore
                pass

    def setup_theme(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        black = '#000000'
        white = '#FFFFFF'
        gray = '#1a1a1a'
        accent = '#2b2b2b'
        # font scalati
        base_size = max(9, int(round(10 * getattr(self, 'ui_scale', 1.0))))
        title_size = max(base_size, int(round(13 * getattr(self, 'ui_scale', 1.0))))
        small_size = max(8, int(round(9 * getattr(self, 'ui_scale', 1.0))))
        self.font_base = tkfont.Font(family='Segoe UI', size=base_size)
        self.font_title = tkfont.Font(family='Segoe UI', size=title_size, weight='bold')
        self.font_small = tkfont.Font(family='Segoe UI', size=small_size)
        # base
        style.configure('.', background=black, foreground=white, font=self.font_base)
        # container
        style.configure('Amoled.TFrame', background=black)
        style.configure('Amoled.TLabel', background=black, foreground=white)
        # buttons
        style.configure('TButton', background=gray, foreground=white, padding=(self.scale(10), self.scale(6))),
        style.map('TButton', background=[('active', '#2a2a2a'), ('pressed', '#202020')])
        # checkbutton
        style.configure('TCheckbutton', background=black, foreground=white)
        # treeview
        style.configure('Treeview', background=black, foreground=white, fieldbackground=black, rowheight=self.scale(28), borderwidth=0)
        style.configure('Treeview.Heading', background=black, foreground=white, font=self.font_base)
        style.map('Treeview', background=[('selected', accent)], foreground=[('selected', white)])
        

    def setup_dpi_awareness(self):
        try:
            # Per-Monitor v2 se disponibile
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
        # Imposta scaling Tk in base al DPI di sistema
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
            scaling = max(0.75, min(2.0, dpi / 96.0))
            self.tk.call('tk', 'scaling', scaling)
        except Exception:
            pass

    def scale(self, value: int) -> int:
        s = getattr(self, 'ui_scale', 1.0)
        try:
            return max(1, int(round(value * s)))
        except Exception:
            return value

    def _build_context_menu(self):
        self.ctx = tk.Menu(self, tearoff=0, bg='#0f0f0f', fg='#ffffff', activebackground='#1f1f1f', activeforeground='#ffffff', bd=0)
        self.ctx.add_command(label='Aggiungi', command=self.add_schedule)
        self.ctx.add_command(label='Modifica', command=self.edit_schedule)
        self.ctx.add_command(label='Rimuovi', command=self.remove_schedule)

    def _show_context_menu(self, event):
        try:
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
            self.ctx.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.ctx.grab_release()
            except Exception:
                pass

    def _update_status(self):
        count = len(self.cfg.get('schedules', []))
        auto = 'attivo' if self.autostart_var.get() else 'disattivo'
        self.status_var.set(f"Voci: {count}   •   Autostart: {auto}")

    def _on_resize(self, event):
        try:
            # imposta wraplength per evitare che la nota sparisca o vada fuori schermo
            pad = self.scale(24)
            self.info_label.configure(wraplength=max(200, event.width - pad))
        except Exception:
            pass

    


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow is not None:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg="#0f0f0f")
        label = ttk.Label(tw, text=self.text, style='Amoled.TLabel')
        label.pack(ipadx=8, ipady=4)
        tw.wm_geometry(f"+{x}+{y}")

    def hide(self, event=None):
        if self.tipwindow is not None:
            self.tipwindow.destroy()
            self.tipwindow = None

    def _show_context_menu(self, event):
        try:
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
            self.ctx.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.ctx.grab_release()
            except Exception:
                pass

    def _update_status(self):
        count = len(self.cfg.get('schedules', []))
        auto = 'attivo' if self.autostart_var.get() else 'disattivo'
        self.status_var.set(f"Voci: {count}   •   Autostart: {auto}")


class ScheduleDialog(tk.Toplevel):
    def __init__(self, parent, schedule):
        super().__init__(parent)
        self.title('Aggiungi / Modifica pianificazione' if schedule else 'Nuova pianificazione')
        self.resizable(False, False)
        self.result = None
        self.schedule = schedule or {'days': [0,1,2,3,4], 'time': '23:30', 'action': 'shutdown', 'enabled': True}
        self.parent = parent
        self.scale = getattr(parent, 'scale', lambda v: v)
        
        # Imposta l'icona della finestra
        try:
            self.iconbitmap(default='icon.ico')
        except:
            pass

        # Stili
        self.style = ttk.Style()
        self.style.theme_use('clam')  # Usa il tema 'clam' per un migliore supporto degli stili personalizzati
        
        # Stili per i frame
        self.style.configure('TFrame', background='#1a1a1a')
        
        # Stili per le etichette
        self.style.configure('TLabel', background='#1a1a1a', foreground='#ffffff')
        
        # Stili per i pulsanti
        self.style.configure('TButton', 
                           padding=8, 
                           font=('Segoe UI', 10),
                           background='#2d2d2d',
                           foreground='#ffffff',
                           borderwidth=1,
                           width=15)  # Larghezza fissa per i pulsanti
        self.style.map('TButton',
                     background=[('active', '#3d3d3d'), ('pressed', '#4d4d4d')],
                     foreground=[('active', '#ffffff')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'raised')])
        
        # Stili per i checkbox
        self.style.configure('TCheckbutton', 
                           background='#1a1a1a', 
                           foreground='#ffffff')
        self.style.map('TCheckbutton',
                     background=[('active', '#2a2a2a')],
                     foreground=[('active', '#ffffff')])
        
        # Stili per i radio button
        self.style.configure('TRadiobutton', 
                           background='#1a1a1a', 
                           foreground='#ffffff')
        self.style.map('TRadiobutton',
                     background=[('active', '#2a2a2a')],
                     foreground=[('active', '#ffffff')])
        
        # Stili per le combobox
        self.style.configure('TCombobox', 
                           padding=6, 
                           font=('Segoe UI', 10),
                           fieldbackground='#2d2d2d',
                           background='#2d2d2d',
                           foreground='#ffffff',
                           arrowcolor='#ffffff')
        self.style.map('TCombobox',
                     fieldbackground=[('readonly', '#2d2d2d')],
                     selectbackground=[('readonly', '#3d3d3d')],
                     selectforeground=[('readonly', '#ffffff')],
                     background=[('active', '#3d3d3d')],
                     foreground=[('active', '#ffffff')])
        
        # Stile per i campi ora e minuti
        try:
            # Prova a creare l'elemento, se già esiste verrà sollevata un'eccezione
            self.style.element_create('Spinbox.field', 'from', 'clam')
            
            # Crea il layout solo se l'elemento è stato creato con successo
            self.style.layout('Time.TSpinbox', [
                ('Spinbox.field', {
                    'border': '2',
                    'children': [
                        ('null', {'side': 'right'}),
                        ('Spinbox.padding', {
                            'sticky': 'ns',
                            'children': [
                                ('Spinbox.textarea', {'sticky': 'nswe'})
                            ]
                        })
                    ]
                })
            ])
        except tk.TclError:
            # Se l'elemento esiste già, non fare nulla
            pass
        
        self.style.configure('Time.TSpinbox', 
                           font=('Segoe UI', 20, 'bold'),  # Aumentata la dimensione del font
                           padding=15,  # Aumentato il padding
                           fieldbackground='#333333',
                           background='#333333',
                           foreground='#ffffff',
                           borderwidth=1,
                           arrowsize=20,  # Aumentata la dimensione delle frecce
                           arrowcolor='#ffffff',
                           bordercolor='#555555',
                           lightcolor='#555555',
                           darkcolor='#333333',
                           width=5)  # Larghezza fissa per i numeri
        
        self.style.map('Time.TSpinbox',
                     fieldbackground=[('readonly', '#333333')],
                     selectbackground=[('readonly', '#555555')],
                     selectforeground=[('readonly', '#ffffff')],
                     background=[('active', '#444444')],
                     foreground=[('active', '#ffffff')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'raised')])
        self.style.configure('Time.TLabel', 
                           font=('Segoe UI', 12, 'bold'),
                           foreground='#ffffff')
        self.style.configure('Time.TFrame', 
                           padding=5,
                           background='#1a1a1a')
        self.style.configure('TLabelframe', background='#1a1a1a', foreground='#ffffff')
        self.style.configure('TLabelframe.Label', background='#1a1a1a', foreground='#ffffff')
        
        # Frame principale
        main_frame = ttk.Frame(self, padding=(15, 15, 15, 10))
        main_frame.pack(fill='both', expand=True)

        # Sezione giorni
        days_frame = ttk.LabelFrame(main_frame, text=' Giorni della settimana ', padding=(10, 10, 10, 5))
        days_frame.pack(fill='x', pady=(0, 15))
        
        # Rimossi i pulsanti rapidi per la selezione dei giorni
        
        # Checkbox per i giorni
        self.day_vars = []
        days_frame_inner = ttk.Frame(days_frame)
        days_frame_inner.pack(fill='x')
        
        day_names = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        short_day_names = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']
        
        # Stile personalizzato per i pulsanti dei giorni
        self.style.configure('Day.TCheckbutton',
                           background='#1a1a1a',
                           foreground='#ffffff',
                           font=('Segoe UI', 11, 'bold'),  # Aumentata la dimensione del font e aggiunto grassetto
                           padding=8,  # Aumentato il padding
                           width=8)  # Larghezza fissa per uniformità
        self.style.map('Day.TCheckbutton',
                     background=[('active', '#2a2a2a'), ('selected', '#121212')],
                     foreground=[('active', '#ffffff'), ('selected', '#ffffff')])
        
        for i, (long_name, short_name) in enumerate(zip(day_names, short_day_names)):
            var = tk.BooleanVar(value=(i in self.schedule.get('days', [])))
            self.day_vars.append(var)
            
            day_frame = ttk.Frame(days_frame_inner)
            day_frame.pack(side='left', expand=True, fill='both')
            
            cb = ttk.Checkbutton(
                day_frame, 
                text=short_name,
                variable=var,
                command=self._update_preview,
                style='Day.TCheckbutton'
            )
            cb.pack(pady=2)
            
            # Tooltip con il nome completo del giorno
            Tooltip(cb, long_name)

        # Sezione orario con stile migliorato
        time_frame = ttk.LabelFrame(main_frame, text=' Orario ', padding=(15, 15, 15, 20), style='TLabelframe')
        time_frame.pack(fill='x', pady=(0, 15))
        
        # Controlli per l'orario con più spazio
        time_controls = ttk.Frame(time_frame, style='TFrame')
        time_controls.pack(pady=5, anchor='center')
        
        # Frame per l'input dell'ora
        time_input_frame = ttk.Frame(time_controls)
        time_input_frame.pack(side='left')
        
        # Etichetta "Ore"
        ttk.Label(time_input_frame, text="Ore:", font=('Segoe UI', 11, 'bold'), foreground='#ffffff').pack(side='left', padx=(0, 10))
        
        # Selettore ore
        self.hour_var = tk.StringVar(value=self.schedule.get('time', '23:30').split(':')[0])
        self.hour_spin = ttk.Spinbox(
            time_input_frame,
            from_=0, 
            to=23,
            width=3,  # Larghezza aumentata
            textvariable=self.hour_var,
            wrap=True,
            command=self._update_preview,
            style='Time.TSpinbox',
            font=('Segoe UI', 20, 'bold')  # Dimensione del font esplicitata
        )
        self.hour_spin.pack(side='left', padx=5, ipady=5)
        
        # Separatore
        ttk.Label(time_input_frame, text=":", font=('Segoe UI', 16, 'bold'), foreground='#ffffff').pack(side='left')
        
        # Selettore minuti
        self.minute_var = tk.StringVar(value=self.schedule.get('time', '23:30').split(':')[1])
        self.minute_spin = ttk.Spinbox(
            time_input_frame,
            from_=0, 
            to=59,
            width=3,  # Larghezza aumentata
            textvariable=self.minute_var,
            wrap=True,
            command=self._update_preview,
            style='Time.TSpinbox',
            font=('Segoe UI', 20, 'bold')  # Dimensione del font esplicitata
        )
        self.minute_spin.pack(side='left', padx=5, ipady=5)
        
        # Etichetta "minuti"
        ttk.Label(time_input_frame, text="minuti", font=('Segoe UI', 11), foreground='#cccccc').pack(side='left', padx=(10, 0))
        
        
        # Anteprima prossima esecuzione
        self.preview_var = tk.StringVar()
        self.preview_label = ttk.Label(
            time_frame, 
            textvariable=self.preview_var,
            foreground='#4CAF50',
            font=('Segoe UI', 9, 'italic')
        )
        self.preview_label.pack(pady=(10, 0))
        self._update_preview()

        # Sezione azione
        action_frame = ttk.LabelFrame(main_frame, text=' Azione ', padding=(15, 10, 15, 10))
        action_frame.pack(fill='x', pady=(0, 15))
        
        self.action_var = tk.StringVar(value=self.schedule.get('action', 'shutdown'))
        
        # Frame per i pulsanti di azione
        action_btns_frame = ttk.Frame(action_frame)
        action_btns_frame.pack(fill='x', pady=5)
        
        # Icone per i pulsanti di azione
        shutdown_icon = '⏻'
        hibernate_icon = '⏾'
        
        # Pulsante di spegnimento
        self.shutdown_btn = ttk.Radiobutton(
            action_btns_frame,
            text=f"{shutdown_icon}  Spegni il computer",
            value='shutdown',
            variable=self.action_var,
            command=self._update_preview
        )
        self.shutdown_btn.pack(anchor='w', pady=2)
        
        # Pulsante di ibernazione
        self.hibernate_btn = ttk.Radiobutton(
            action_btns_frame,
            text=f"{hibernate_icon}  Ibernazione",
            value='hibernate',
            variable=self.action_var,
            command=self._update_preview
        )
        self.hibernate_btn.pack(anchor='w', pady=2)
        
        # Tooltip informativo per l'ibernazione
        Tooltip(self.hibernate_btn, "L'ibernazione deve essere abilitata in Windows\n(apri un prompt dei comandi come amministratore\ne digita: powercfg -h on)")

        # Checkbox abilitazione
        self.enabled_var = tk.BooleanVar(value=self.schedule.get('enabled', True))
        self.enabled_cb = ttk.Checkbutton(
            main_frame,
            text='Attiva questa pianificazione',
            variable=self.enabled_var,
            command=self._update_preview
        )
        self.enabled_cb.pack(anchor='w', pady=(0, 15))

        # Pulsanti di conferma
        btn_frame = ttk.Frame(main_frame, padding=(0, 15, 0, 5))
        btn_frame.pack(fill='x')
        
        # Stile per il pulsante di salvataggio
        self.style.configure('Accent.TButton', 
                           font=('Segoe UI', 10, 'bold'),
                           background='#121212',
                           foreground='#ffffff')
        self.style.map('Accent.TButton',
                     background=[('active', '#121212'), ('pressed', '#121212')],
                     foreground=[('active', '#ffffff')])
        
        # Frame per i pulsanti allineati a destra
        btn_container = ttk.Frame(btn_frame)
        btn_container.pack(side='right')
        
        ttk.Button(btn_container, text='Annulla', command=self._on_cancel).pack(side='left', padx=5)
        save_btn = ttk.Button(btn_container, text='Salva', command=self._on_save, style='Accent.TButton')
        save_btn.pack(side='left', padx=5)
        
        # Imposta il focus sul pulsante Salva
        save_btn.focus_set()
        
        # Scorciatoie da tastiera
        self.bind('<Return>', lambda e: self._on_save())
        self.bind('<Escape>', lambda e: self._on_cancel())
        
        # Centra la finestra rispetto alla finestra principale
        self.transient(parent)
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        # Imposta la finestra come modale
        self.grab_set()
        
    def _update_preview(self, event=None):
        """Aggiorna l'anteprima della prossima esecuzione"""
        try:
            # Ottieni l'orario selezionato
            hh = self.hh.get().strip()
            mm = self.mm.get().strip()
            
            # Valida l'orario
            if not hh.isdigit() or not mm.isdigit():
                self.preview_var.set("")
                return
                
            hh = int(hh)
            mm = int(mm)
            
            if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                self.preview_var.set("Orario non valido")
                return
                
            # Formatta l'orario
            time_str = f"{hh:02d}:{mm:02d}"
            
            # Ottieni i giorni selezionati
            selected_days = [i for i, var in enumerate(self.day_vars) if var.get()]
            
            if not selected_days:
                self.preview_var.set("Seleziona almeno un giorno")
                return
                
            # Ottieni il nome dei giorni selezionati
            day_names = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']
            selected_day_names = [day_names[i] for i in selected_days]
            
            # Ottieni il tipo di azione
            action = self.action_var.get()
            action_text = "spegnerà" if action == 'shutdown' else "ibernerà"
            
            # Costruisci il testo dell'anteprima
            if len(selected_days) == 7:
                days_text = "Ogni giorno"
            elif selected_days == list(range(5)):  # Tutti i giorni feriali
                days_text = "Ogni giorno feriale"
            elif selected_days == [5, 6]:  # Weekend
                days_text = "Ogni weekend"
            else:
                days_text = f"Ogni {', '.join(selected_day_names)}"
            
            # Aggiungi indicazione se disabilitato
            status = ""
            if not self.enabled_var.get():
                status = " (disabilitata)"
            
            # Imposta il testo dell'anteprima
            preview = f"{days_text} alle {time_str} {action_text} il computer{status}"
            self.preview_var.set(preview)
            
        except Exception as e:
            self.preview_var.set("Errore nell'anteprima")
    
    def _on_save(self, event=None):
        """Gestisce il salvataggio della pianificazione."""
        print("Salvataggio in corso...")  # Debug
        try:
            # Verifica che almeno un giorno sia selezionato
            selected_days = [i for i, var in enumerate(self.day_vars) if var.get()]
            if not selected_days:
                print("Nessun giorno selezionato")  # Debug
                messagebox.showwarning('Attenzione', 'Seleziona almeno un giorno della settimana')
                return
                
            # Verifica che l'ora sia valida
            try:
                hours = int(self.hour_var.get())
                minutes = int(self.minute_var.get())
                if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                    print(f"Orario non valido: {hours}:{minutes}")  # Debug
                    raise ValueError()
            except ValueError as ve:
                print(f"Errore validazione orario: {ve}")  # Debug
                messagebox.showerror('Errore', 'Inserisci un orario valido (ore: 0-23, minuti: 0-59)')
                return
                
            # Imposta il risultato e chiudi la finestra
            self.result = {
                'days': selected_days,
                'time': f"{hours:02d}:{minutes:02d}",
                'action': self.action_var.get(),
                'enabled': self.enabled_var.get()
            }
            print("Pianificazione salvata:", self.result)  # Debug
            self.destroy()
            
        except Exception as e:
            print(f"Errore in _on_save: {str(e)}", file=sys.stderr)  # Debug
            messagebox.showerror('Errore', f'Si è verificato un errore: {str(e)}')
    
    def _on_cancel(self, event=None):
        """Annulla le modifiche e chiude la finestra."""
        self.result = None
        print("Finestra chiusa")  # Debug
        self.destroy()
    
    def on_ok(self):
        """Alias per _on_save per compatibilità con il codice esistente."""
        self._on_save()


def days_to_string(days):
    names = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']
    return ','.join(names[d] for d in days)


if __name__ == '__main__':
    app = App()
    app.mainloop()
