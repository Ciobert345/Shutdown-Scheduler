"""
Modern UI Shutdown Scheduler per Windows
- Interfaccia moderna con temi chiari/scuri
- Esperienza utente migliorata
- Mantiene tutte le funzionalità originali
"""

import os
import sys
import json
import time
import threading
import datetime
import subprocess
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    PYSYSTRAY_AVAILABLE = True
except ImportError:
    PYSYSTRAY_AVAILABLE = False
    print("Note: pystray not available. System tray functionality will be disabled.")
from pathlib import Path
import winreg
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox as tk_messagebox, LEFT, RIGHT, X, BOTH
from functools import partial
from functools import partial
# Import PIL indipendentemente dalla disponibilita' di pystray per le icone UI
try:
    from PIL import Image as PILImage, ImageDraw as PILImageDraw
except Exception:
    PILImage = None
    PILImageDraw = None

# Configurazione tema personalizzato
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Stili personalizzati (palette coerente, dark + accent blu)
ACCENT_COLOR   = "#2563eb"  # blu più spento
HOVER_COLOR    = "#2f6bdc"  # blu hover
TEXT_COLOR     = "#e6e9ef"  # testo primario
TEXT_DISABLED  = "#6b7280"  # testo disabilitato

# Stili aggiuntivi per le card (monocromatici coerenti)
CARD_BG        = "#14161a"
CARD_BG_HOVER  = "#191c22"
CARD_BG_SELECTED = "#1f2430"
CARD_BORDER    = "#262a33"
MUTED_TEXT     = "#a3a9b7"
CONTENT_MAX_WIDTH = 1000  # larghezza massima della colonna cards centrata
ROOT_BG        = "#0f1115"  # sfondo uniforme sotto alle card

# Pill stato
STATUS_ON  = "#16a34a"   # verde acceso
STATUS_OFF = "#3f3f46"   # grigio scuro
BTN_PRIMARY      = ACCENT_COLOR
BTN_PRIMARY_HOV  = HOVER_COLOR
BTN_DANGER       = "#ef4444"
BTN_DANGER_HOV   = "#dc2626"

# Tooltip semplice per widget CTk
class Tooltip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        try:
            if self.tip or not self.text:
                return
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            lbl = ctk.CTkLabel(self.tip, text=self.text, fg_color="#111111", corner_radius=6)
            lbl.pack(ipadx=8, ipady=4)
        except Exception:
            pass

    def _hide(self, event=None):
        try:
            if self.tip:
                self.tip.destroy()
                self.tip = None
        except Exception:
            pass

# Helper per creare icone toolbar come CTkImage
def create_toolbar_icon(kind: str, size=(20, 20), color="#FFFFFF"):
    """Ritorna un ctk.CTkImage con icona disegnata via PIL. In caso PIL mancante, ritorna None."""
    if PILImage is None or PILImageDraw is None:
        return None
    w, h = size
    img = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
    d = PILImageDraw.Draw(img)
    c = color
    thick = max(2, min(w, h)//10)
    pad = max(2, thick)
    if kind == "add":
        # Croce '+' centrata
        d.rectangle((w//2 - thick//2, pad, w//2 + thick//2, h - pad), fill=c)
        d.rectangle((pad, h//2 - thick//2, w - pad, h//2 + thick//2), fill=c)
    elif kind == "edit":
        # Matita diagonale
        d.line((pad, h - pad, w - pad, pad), fill=c, width=thick)
        # Punta
        d.polygon([(w - pad - thick, pad), (w - pad, pad), (w - pad, pad + thick)], fill=c)
    elif kind == "remove":
        # Cestino stilizzato
        # corpo
        d.rectangle((pad+2, pad+6, w - pad-2, h - pad), outline=c, width=thick)
        # coperchio
        d.rectangle((pad, pad+2, w - pad, pad+4), fill=c)
        # manico
        d.line((w//2, pad, w//2, pad+2), fill=c, width=thick)
    else:
        # fallback: cerchio
        d.ellipse((pad, pad, w - pad, h - pad), outline=c, width=thick)
    try:
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        return None

class Messagebox:
    @staticmethod
    def show_info(title, message):
        return tk_messagebox.showinfo(title, message)
        
    @staticmethod
    def show_warning(title, message):
        return tk_messagebox.showwarning(title, message)
        
    @staticmethod
    def show_error(title, message):
        return tk_messagebox.showerror(title, message)
        
    @staticmethod
    def show_question(title, message):
        return tk_messagebox.askyesno(title, message)

APP_NAME = "ShutdownScheduler"
CONFIG_DIR = Path(os.getenv('APPDATA')) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
REGISTRY_RUN_KEY = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
REGISTRY_VALUE_NAME = "ShutdownScheduler"

DEFAULT_CONFIG = {
    "schedules": [],
    "autostart": True,
    "theme": "dark",  # Nuovo campo per salvare il tema preferito
    "ui_scale": 1.0     # Fattore di scala UI (1.0 = 100%)
}

# Funzioni di utilità per il registro di sistema
def set_autostart(enabled: bool):
    exe_path = getattr(sys, 'frozen', False) and sys.executable or os.path.abspath(sys.argv[0])
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
        print('Errore autostart:', e)
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

def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                # Assicurati che la configurazione abbia tutti i campi necessari
                for key, value in DEFAULT_CONFIG.items():
                    if key not in cfg:
                        cfg[key] = value
                return cfg
        except Exception as e:
            print('Errore caricamento configurazione:', e)
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# Thread per lo scheduling
class SchedulerThread(threading.Thread):
    def __init__(self, get_schedules_callable, stop_event, app=None):
        super().__init__(daemon=True)
        self.get_schedules = get_schedules_callable
        self.stop_event = stop_event
        self.last_executed = {}
        self.app = app  # riferimento alla UI per eseguire callback nel main thread

    def run(self):
        while not self.stop_event.is_set():
            now = datetime.datetime.now()
            current_day = now.weekday()
            current_time = now.strftime('%H:%M')
            schedules = self.get_schedules()
            
            for idx, s in enumerate(schedules):
                if not s.get('enabled', True):
                    continue
                    
                days = s.get('days', [])
                time_str = s.get('time')
                action = s.get('action')
                
                # Esegui entro i primi 5 secondi del minuto pianificato, una sola volta
                if current_day in days and current_time == time_str and now.second < 5:
                    key = f"{idx}-{time_str}"
                    last = self.last_executed.get(key)
                    
                    if last != now.strftime('%Y%m%d%H%M'):
                        print(f"Eseguo azione immediata: {action} alle {time_str} ({now})")
                        try:
                            # Esegui direttamente l'azione senza avviso/attesa
                            self._perform_action(action)
                        except Exception as e:
                            print('Errore esecuzione azione:', e)
                        self.last_executed[key] = now.strftime('%Y%m%d%H%M')
            
            time.sleep(1)
    
    def _show_notification(self, action):
        # Mostra una notifica non intrusiva sul thread UI
        # Avviso disabilitato: esecuzione immediata senza popup
        try:
            return
        except Exception:
            pass
    
    def _perform_action(self, action_name):
        if action_name == 'shutdown':
            subprocess.run(['shutdown', '/s', '/f', '/t', '0'])
        elif action_name == 'hibernate':
            subprocess.run(['shutdown', '/h'])

# Finestra di dialogo per aggiungere/modificare pianificazioni
class ScheduleDialog(ctk.CTkToplevel):
    def __init__(self, parent, schedule=None):
        super().__init__(parent)
        self.parent = parent
        self.schedule = schedule or {}
        self.result = None
        
        self.title("Aggiungi pianificazione" if not schedule else "Modifica pianificazione")
        self.geometry("500x560")
        # Consenti ridimensionamento verticale per evitare tagli su display ad alto DPI
        self.resizable(False, True)
        
        # Imposta la finestra come modale
        self.transient(parent)
        self.grab_set()
        
        # Crea il frame principale
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._setup_ui()
        
        # Se stiamo modificando, popola i campi
        if schedule:
            self._load_schedule()
    
    def _setup_ui(self):
        # Etichetta titolo
        title = "Modifica pianificazione" if self.schedule else "Nuova pianificazione"
        title_label = ctk.CTkLabel(
            self.main_frame, 
            text=title,
            font=("Segoe UI", 16, "bold")
        )
        title_label.pack(pady=(15, 10))
        
        # Barra pulsanti: va creata prima cosi' con side=BOTTOM resta realmente ancorata in basso
        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(side=tk.BOTTOM, fill=X, padx=20, pady=15)
        
        buttons_right = ctk.CTkFrame(button_frame, fg_color="transparent")
        buttons_right.pack(side=RIGHT)
        
        self.save_btn = ctk.CTkButton(
            buttons_right,
            text="Salva" if self.schedule else "Aggiungi",
            command=self._on_save,
            width=120,
            height=32,
            corner_radius=8
        )
        self.save_btn.pack(side=RIGHT, padx=5)
        
        self.cancel_btn = ctk.CTkButton(
            buttons_right,
            text="Annulla",
            command=self._on_cancel,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "#DCE4EE"),
            width=120,
            height=32,
            corner_radius=8
        )
        self.cancel_btn.pack(side=RIGHT, padx=5)
        
        # Frame per i giorni
        days_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        days_frame.pack(fill=X, padx=20, pady=(0, 15))
        
        ctk.CTkLabel(days_frame, text="Giorni:", anchor="w").pack(fill=X, pady=(0, 5))
        
        self.day_vars = {}
        days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        
        # Crea i checkbox per i giorni
        days_container = ctk.CTkFrame(days_frame, fg_color="transparent")
        days_container.pack(fill=X, pady=5)
        
        for i in range(7):
            col = i % 2
            row = i // 2
            
            if col == 0:
                row_frame = ctk.CTkFrame(days_container, fg_color="transparent")
                row_frame.pack(fill=X, pady=2)
            
            day_idx = i
            self.day_vars[day_idx] = ctk.BooleanVar(value=day_idx in self.schedule.get('days', []))
            cb = ctk.CTkCheckBox(
                row_frame, 
                text=days[day_idx],
                variable=self.day_vars[day_idx],
                width=100
            )
            cb.pack(side=LEFT, padx=5, pady=2, expand=True, fill=X)
        
        # Frame per l'orario
        time_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        time_frame.pack(fill=X, padx=20, pady=10)
        
        ctk.CTkLabel(time_frame, text="Orario (HH:MM):", anchor="w").pack(fill=X, pady=(0, 5))
        
        self.time_entry = ctk.CTkEntry(time_frame, placeholder_text="HH:MM")
        self.time_entry.pack(fill=X)
        
        # Imposta l'orario corrente se nuovo, altrimenti quello della pianificazione
        if not self.schedule:
            self.time_entry.insert(0, datetime.datetime.now().strftime("%H:%M"))
        elif 'time' in self.schedule:
            self.time_entry.delete(0, tk.END)
            self.time_entry.insert(0, self.schedule['time'])
        
        # Frame per l'azione
        action_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        action_frame.pack(fill=X, padx=20, pady=10)
        
        ctk.CTkLabel(action_frame, text="Azione:", anchor="w").pack(fill=X, pady=(0, 5))
        
        self.action_var = ctk.StringVar(value=self.schedule.get('action', 'shutdown'))
        
        shutdown_radio = ctk.CTkRadioButton(
            action_frame, 
            text="Spegni il computer", 
            variable=self.action_var, 
            value="shutdown"
        )
        shutdown_radio.pack(anchor="w", pady=2)
        
        hibernate_radio = ctk.CTkRadioButton(
            action_frame, 
            text="Iberna il computer", 
            variable=self.action_var, 
            value="hibernate"
        )
        hibernate_radio.pack(anchor="w", pady=2)
        
        # Checkbox per abilitare/disabilitare
        self.enabled_var = ctk.BooleanVar(value=self.schedule.get('enabled', True))
        enabled_cb = ctk.CTkCheckBox(
            action_frame,
            text="Attiva questa pianificazione",
            variable=self.enabled_var
        )
        enabled_cb.pack(anchor="w", pady=(10, 0))
        
        # (i pulsanti sono gia' stati creati e ancorati in basso)
        
        # Il riferimento a time_entry è già salvato come self.time_entry
    
    def _load_schedule(self):
        # Questo metodo popola i campi con i valori esistenti
        if 'days' in self.schedule:
            for day in self.schedule['days']:
                if day in self.day_vars:
                    self.day_vars[day].set(True)
        
        if 'time' in self.schedule:
            self.time_entry.delete(0, tk.END)
            self.time_entry.insert(0, self.schedule['time'])
        
        if 'action' in self.schedule:
            self.action_var.set(self.schedule['action'])
        
        if 'enabled' in self.schedule:
            self.enabled_var.set(self.schedule['enabled'])
    
    def _on_save(self):
        # Validazione
        time_str = self.time_entry.get().strip()
        
        try:
            # Verifica il formato dell'orario
            hours, minutes = map(int, time_str.split(':'))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Ora non valida")
            time_str = f"{hours:02d}:{minutes:02d}"
        except (ValueError, AttributeError):
            Messagebox.show_error("Formato orario non valido. Usa il formato HH:MM", "Errore")
            return
        
        # Ottieni i giorni selezionati
        selected_days = [day for day, var in self.day_vars.items() if var.get()]
        
        if not selected_days:
            Messagebox.show_warning("Seleziona almeno un giorno della settimana", "Attenzione")
            return
            
        # Ottieni l'azione selezionata e lo stato
        action = self.action_var.get()
        enabled = self.enabled_var.get()
            
        self.result = {
            'days': selected_days,
            'time': time_str,
            'action': action,
            'enabled': enabled
        }
        
        self.destroy()
        
    def _on_cancel(self):
        # Chiudi la finestra senza salvare
        self.result = None
        self.destroy()

# Classe principale dell'applicazione
class ModernShutdownScheduler(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configurazione della finestra
        self.title("Shutdown Scheduler")
        # Finestra a dimensione fissa (niente ridimensionamento), ma con toggle fullscreen
        self.fixed_width, self.fixed_height = 900, 750
        self.geometry(f"{self.fixed_width}x{self.fixed_height}")
        # Blocca lo scaling manuale
        self.minsize(self.fixed_width, self.fixed_height)
        self.maxsize(self.fixed_width, self.fixed_height)
        self.resizable(False, False)
        # Centra la finestra sullo schermo (dopo che la finestra è stata creata)
        try:
            self.after(0, self._center_window)
        except Exception:
            self._center_window()
        # Gestione fullscreen: F11 per entrare/uscire, Esc per uscire
        self.is_fullscreen = False
        try:
            self.bind('<F11>', lambda e: self._toggle_fullscreen())
            self.bind('<Escape>', lambda e: self._exit_fullscreen())
        except Exception:
            pass
        # Sfondo uniforme dell'app
        try:
            self.configure(fg_color=ROOT_BG)
        except Exception:
            pass
        
        # Carica la configurazione
        self.cfg = load_config()
        # Default per nuova impostazione: avvio minimizzato su tray
        if 'start_minimized_tray' not in self.cfg:
            self.cfg['start_minimized_tray'] = False
        
        # Imposta forzatamente il tema scuro (disabilita modalita' chiara)
        self.theme_mode = 'dark'
        ctk.set_appearance_mode("Dark")
        # Sincronizza la config per coerenza
        self.cfg['theme'] = 'dark'
        # Applica scala UI (ridurre la scala migliora le performance su macchine lente)
        ui_scale = float(self.cfg.get('ui_scale', 1.0))
        try:
            ctk.set_widget_scaling(ui_scale)
            ctk.set_window_scaling(ui_scale)
        except Exception:
            pass
        save_config(self.cfg)
        
        # Inizializza le variabili
        self.scheduler = None
        self.stop_event = threading.Event()
        self.tray_icon = None
        # Inizializza selezione per evitare errori in hover
        self.selected_row = None
        self._render_pending = False
        self._resizing = False
        self._resize_after = None
        
        # Crea l'interfaccia utente
        self._setup_ui()
        # Inizializza la tray icon (se disponibile)
        try:
            self._create_tray_icon()
        except Exception:
            pass
        # Avvio minimizzato su tray (se impostato)
        try:
            if bool(self.cfg.get('start_minimized_tray', False)):
                self.withdraw()
        except Exception:
            pass
        # Throttle durante il resize finestra
        try:
            self.bind('<Configure>', self._on_window_configure)
        except Exception:
            pass
        # Scorciatoie da tastiera
        self._bind_shortcuts()
        
        # Avvia il thread di pianificazione
        self._start_scheduler()
        
        
        # Gestisci la chiusura della finestra
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _setup_ui(self):
        # Configura il layout principale (due colonne: cards a sinistra, pannelli a destra)
        # Aumenta lo spazio per le cards (più largo a sinistra)
        self.grid_columnconfigure(0, weight=8)
        self.grid_columnconfigure(1, weight=0)
        # Imposta una larghezza minima più piccola al pannello destro per dare più spazio alle card
        try:
            self.grid_columnconfigure(1, minsize=240)
        except Exception:
            pass
        
        # Barra superiore
        self.header = ctk.CTkFrame(self, corner_radius=0, fg_color=ROOT_BG)
        self.header.grid(row=0, column=0, sticky="nsew", columnspan=2)
        self.header.grid_columnconfigure(1, weight=1)
        
        # Titolo
        title = ctk.CTkLabel(
            self.header, 
            text="Shutdown Scheduler",
            font=("Segoe UI", 20, "bold"),
            text_color=TEXT_COLOR
        )
        title.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        # Contatori a destra nell'header
        counters = ctk.CTkFrame(self.header, fg_color="transparent")
        counters.grid(row=0, column=1, padx=20, pady=10, sticky="e")
        self.rules_count_var = ctk.StringVar(value="0")
        self.active_count_var = ctk.StringVar(value="0")
        ctk.CTkLabel(counters, textvariable=self.rules_count_var, font=("Segoe UI", 16, "bold"), anchor="e").pack(side="left", padx=8)
        ctk.CTkLabel(counters, text="Rules", anchor="w").pack(side="left")
        ctk.CTkLabel(counters, textvariable=self.active_count_var, font=("Segoe UI", 16, "bold"), anchor="e").pack(side="left", padx=(20,8))
        ctk.CTkLabel(counters, text="Active", anchor="w").pack(side="left")
        self.ready_pill = ctk.CTkLabel(counters, text="Ready", fg_color="#1a1a1a", corner_radius=12, padx=10, pady=2)
        self.ready_pill.pack(side="left", padx=12)
        
        # (Modalita' chiara disabilitata: rimosso pulsante cambio tema)
        
        # Inizializza variabili UI necessarie ai pannelli
        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        # Stato (variabile nascosta, niente footer visibile)
        self.status_var = ctk.StringVar(value="")
        # Elenco pianificazioni in stile "cards" e pannelli laterali
        self._setup_schedule_cards()
        self._setup_side_panels()
        
        # (Footer rimosso su richiesta; nessun controllo visibile in basso)
    
    def _setup_schedule_cards(self):
        # Colonna sinistra: barra azioni + lista cards
        left_col = ctk.CTkFrame(self, corner_radius=8, fg_color=ROOT_BG)
        # Spingi a destra: riduci il padding destro per guadagnare spazio sulle card
        left_col.grid(row=1, column=0, padx=(10,0), pady=(0, 16), sticky="nsew")
        left_col.grid_columnconfigure(0, weight=1)
        left_col.grid_rowconfigure(1, weight=1)

        # Barra azioni compatta
        actions = ctk.CTkFrame(left_col, corner_radius=6)
        actions.grid(row=0, column=0, sticky="ew", padx=0, pady=(0,8))
        # Colonne compatte senza stretch
        for c in range(5):
            try:
                actions.grid_columnconfigure(c, weight=0)
            except Exception:
                pass
        btn_w = 100
        btn_h = 34
        gap   = 6
        add_btn = ctk.CTkButton(
            actions, text="Aggiungi", width=btn_w, height=btn_h,
            fg_color=BTN_PRIMARY, hover_color=BTN_PRIMARY_HOV, text_color=TEXT_COLOR,
            corner_radius=8, command=self._add_schedule
        )
        add_btn.grid(row=0, column=0, padx=(8,gap), pady=6)
        edit_btn = ctk.CTkButton(
            actions, text="Modifica", width=btn_w, height=btn_h,
            fg_color=BTN_PRIMARY, hover_color=BTN_PRIMARY_HOV, text_color=TEXT_COLOR,
            corner_radius=8, command=self._edit_schedule
        )
        edit_btn.grid(row=0, column=1, padx=(gap,gap), pady=6)
        save_btn = ctk.CTkButton(
            actions, text="Save Config", width=btn_w, height=btn_h,
            fg_color=BTN_PRIMARY, hover_color=BTN_PRIMARY_HOV, text_color=TEXT_COLOR,
            corner_radius=8, command=lambda: (save_config(self.cfg), self.status_var.set("Configurazione salvata"))
        )
        save_btn.grid(row=0, column=2, padx=(gap,gap), pady=6)
        del_btn = ctk.CTkButton(
            actions, text="Elimina", width=btn_w, height=btn_h,
            fg_color=BTN_DANGER, hover_color=BTN_DANGER_HOV, text_color=TEXT_COLOR,
            corner_radius=8, command=self._remove_schedule
        )
        del_btn.grid(row=0, column=3, padx=(gap,8), pady=6)

        # Contenitore scrollabile per le "cards"
        cards_frame = ctk.CTkFrame(left_col, corner_radius=8, fg_color=ROOT_BG)
        cards_frame.grid(row=1, column=0, sticky="nsew")
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_rowconfigure(0, weight=1)

        # Usa tk.Canvas per performance nel ridimensionamento
        self.cards_canvas = tk.Canvas(cards_frame, bg=ROOT_BG, highlightthickness=0, highlightbackground=ROOT_BG, highlightcolor=ROOT_BG)
        # Scrollbar sottile e scura (quasi invisibile) per evitare gutter bianchi
        self.cards_vsb = ctk.CTkScrollbar(
            cards_frame,
            orientation="vertical",
            width=6,
            fg_color=ROOT_BG,
            button_color="#2a2a2a",
            button_hover_color="#3a3a3a",
            corner_radius=8,
        )
        self.cards_vsb.pack(side=RIGHT, fill="y", padx=0)
        self.cards_canvas.configure(yscrollcommand=self.cards_vsb.set)
        # Assicurati che il canvas occupi TUTTA la larghezza del contenitore
        self.cards_canvas.pack(fill="both", expand=True)
        # Scorrimento con rotellina del mouse anche senza scrollbar visibile
        def _on_mousewheel(event):
            try:
                delta = int(-1 * (event.delta / 120))
            except Exception:
                delta = -1
            self.cards_canvas.yview_scroll(delta, "units")
            return "break"
        try:
            self.cards_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        except Exception:
            pass
        # Contenitore interno
        self.cards_inner = tk.Frame(self.cards_canvas, bg=ROOT_BG)
        # Salva l'ID della finestra canvas per poterla centrare/riscalare
        self.cards_canvas_window = self.cards_canvas.create_window(0, 0, window=self.cards_inner, anchor='n')

        # Centro e limito la larghezza della colonna cards
        def _on_canvas_configure(event):
            try:
                # Usa tutta la larghezza del canvas per evitare aree vuote e differenze colore
                width = event.width
                self.cards_canvas.itemconfigure(self.cards_canvas_window, width=width, anchor='nw')
                self.cards_canvas.coords(self.cards_canvas_window, 0, 0)
            except Exception:
                pass
        self.cards_canvas.bind('<Configure>', _on_canvas_configure)

        # Aggiorna scrollregion quando il contenuto cambia
        def _on_inner_configure(event=None):
            try:
                self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox('all'))
            except Exception:
                pass
        self.cards_inner.bind('<Configure>', _on_inner_configure)

        self._render_cards()

    def _setup_side_panels(self):
        # Colonna destra con pannelli
        side = ctk.CTkFrame(self, corner_radius=8, fg_color=ROOT_BG)
        # Avvicina il pannello a destra e riduci il padding sinistro, così le card hanno più spazio
        side.grid(row=1, column=1, padx=(6,12), pady=(0,16), sticky="nsew")
        side.grid_columnconfigure(0, weight=1)

        # Settings panel
        settings = ctk.CTkFrame(side, corner_radius=8)
        # Rimuovi padding superiore per allineare l'altezza con la barra azioni a sinistra
        settings.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(settings, text="Settings", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10,6))
        autostart_row = ctk.CTkFrame(settings, fg_color="transparent")
        autostart_row.pack(fill="x", padx=12, pady=(0,6))
        ctk.CTkLabel(autostart_row, text="Start with Windows", anchor="w").pack(side="left")
        autostart_toggle = ctk.CTkSwitch(autostart_row, text="", variable=self.autostart_var, command=self._toggle_autostart)
        autostart_toggle.pack(side="right")

        # Start minimized to tray
        tray_row = ctk.CTkFrame(settings, fg_color="transparent")
        tray_row.pack(fill="x", padx=12, pady=(0,10))
        ctk.CTkLabel(tray_row, text="Start minimized to tray", anchor="w").pack(side="left")
        self.start_min_tray_var = ctk.BooleanVar(value=bool(self.cfg.get('start_minimized_tray', False)))
        tray_toggle = ctk.CTkSwitch(tray_row, text="", variable=self.start_min_tray_var, command=self._toggle_start_minimized_tray)
        tray_toggle.pack(side="right")
        
        # Analytics (include Weekly Activity e Stats)
        analytics = ctk.CTkFrame(side, corner_radius=8)
        analytics.pack(fill="x", pady=8)
        ctk.CTkLabel(analytics, text="Analytics", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10,6))
        # Weekly Activity (progress bars Lun-Dom)
        weekly = ctk.CTkFrame(analytics, corner_radius=8)
        weekly.pack(fill="x")
        ctk.CTkLabel(weekly, text="Weekly Activity", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(6,4))
        self.week_pbars = []
        self.week_labels = []
        for i, day in enumerate(["Lun","Mar","Mer","Gio","Ven","Sab","Dom"]):
            row = ctk.CTkFrame(weekly, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            lbl = ctk.CTkLabel(row, text=day, width=40, anchor="w")
            lbl.pack(side="left")
            p = ctk.CTkProgressBar(row)
            p.set(0)
            p.pack(side="left", fill="x", expand=True, padx=8)
            self.week_labels.append(lbl)
            self.week_pbars.append(p)
        # Stats sintetiche
        stats = ctk.CTkFrame(analytics, corner_radius=8)
        stats.pack(fill="x", pady=(6, 10))
        row = ctk.CTkFrame(stats, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(row, text="Totali:", width=60).pack(side="left")
        self.stat_total = ctk.StringVar(value=self.stat_total.get() if hasattr(self, 'stat_total') else "0")
        ctk.CTkLabel(row, textvariable=self.stat_total, font=("Segoe UI", 14, "bold")).pack(side="left", padx=(4,12))
        ctk.CTkLabel(row, text="Attive:").pack(side="left")
        self.stat_active = ctk.StringVar(value=self.stat_active.get() if hasattr(self, 'stat_active') else "0")
        ctk.CTkLabel(row, textvariable=self.stat_active, font=("Segoe UI", 14, "bold")).pack(side="left", padx=(4,12))
        ctk.CTkLabel(row, text="Peak Day:").pack(side="left")
        self.stat_peak = ctk.StringVar(value=self.stat_peak.get() if hasattr(self, 'stat_peak') else "-")
        ctk.CTkLabel(row, textvariable=self.stat_peak, font=("Segoe UI", 14, "bold")).pack(side="left", padx=(4,0))

        # Info panel
        info = ctk.CTkFrame(side, corner_radius=8)
        info.pack(fill="x", pady=8)
        ctk.CTkLabel(info, text="Config Path", anchor="w").pack(fill="x", padx=12, pady=(10,2))
        ctk.CTkLabel(info, text=str(CONFIG_FILE), anchor="w", text_color=TEXT_DISABLED).pack(fill="x", padx=12, pady=(0,10))

        # Bottom stats
        stats = ctk.CTkFrame(side, corner_radius=8)
        stats.pack(fill="x", pady=8)
        stats_row = ctk.CTkFrame(stats, fg_color="transparent")
        stats_row.pack(fill="x", padx=12, pady=10)
        self.stat_total = ctk.StringVar(value="0")
        self.stat_active = ctk.StringVar(value="0")
        self.stat_peak = ctk.StringVar(value="-")
        lbl_total = ctk.CTkLabel(stats_row, textvariable=self.stat_total, font=("Segoe UI", 16, "bold"))
        lbl_total.pack(side="left")
        lbl_total_text = ctk.CTkLabel(stats_row, text=" Total Rules", padx=12)
        lbl_total_text.pack(side="left")
        lbl_active = ctk.CTkLabel(stats_row, textvariable=self.stat_active, font=("Segoe UI", 16, "bold"))
        lbl_active.pack(side="left", padx=(20,0))
        lbl_active_text = ctk.CTkLabel(stats_row, text=" Active")
        lbl_active_text.pack(side="left")
        lbl_peak = ctk.CTkLabel(stats_row, textvariable=self.stat_peak, font=("Segoe UI", 16, "bold"))
        lbl_peak.pack(side="left", padx=(20,0))
        lbl_peak_text = ctk.CTkLabel(stats_row, text=" Peak Day")
        lbl_peak_text.pack(side="left")

        self.side_panel = side

    def _create_day_badge(self, parent, text, active=True):
        fg = "#1e1e1e" if active else "#2a2a2a"
        txt = TEXT_COLOR if active else TEXT_DISABLED
        badge = ctk.CTkLabel(parent, text=text, fg_color=fg, text_color=txt, corner_radius=12, padx=8, pady=2)
        return badge

    def _create_pill(self, parent, text):
        return ctk.CTkLabel(parent, text=text, fg_color="#", text_color=TEXT_COLOR, corner_radius=12, padx=10, pady=2)

    def _toggle_schedule_enabled(self, idx, value):
        try:
            self.cfg['schedules'][idx]['enabled'] = bool(value)
            save_config(self.cfg)
            self.status_var.set("Stato regola aggiornato")
        except Exception:
            pass

    def _toggle_enabled_by_index(self, idx):
        """Toggle enabled state for schedule at index and refresh UI."""
        try:
            schedules = self.cfg.get('schedules', [])
            if 0 <= idx < len(schedules):
                schedules[idx]['enabled'] = not bool(schedules[idx].get('enabled', True))
                save_config(self.cfg)
                # Aggiorna pill e contatori
                self._after_config_change("Stato regola aggiornato")
        except Exception:
            pass

    def _toggle_start_minimized_tray(self):
        try:
            val = bool(self.start_min_tray_var.get())
            self.cfg['start_minimized_tray'] = val
            save_config(self.cfg)
            self.status_var.set("Impostazione avvio minimizzato aggiornata")
        except Exception:
            pass

    def _render_cards(self):
        # Pulisce e ricrea le cards
        container = getattr(self, 'cards_inner', None)
        if not container:
            return
        for w in container.winfo_children():
            w.destroy()

        schedules = self.cfg.get('schedules', [])
        # Aggiorna header, status e pannelli in modo centralizzato
        self._update_overview(schedules)

        # Prepara selezione
        prev_sel = getattr(self, 'selected_row', None)
        self.card_items = []

        for idx, s in enumerate(schedules):
            # Card elegante: CTkFrame con bordo e hover
            card = ctk.CTkFrame(container, corner_radius=12, fg_color=CARD_BG, border_color=CARD_BORDER, border_width=1)
            # Padding interno coerente
            card.pack(fill="x", padx=12, pady=10)
            # Griglia a 4 colonne: 0=icon, 1=contenuti (flex), 2=spacer, 3=azioni (destra)
            card.grid_columnconfigure(0, weight=0, minsize=38)
            card.grid_columnconfigure(1, weight=1)
            card.grid_columnconfigure(2, weight=0, minsize=12)
            card.grid_columnconfigure(3, weight=0)

            # Icon chip (monocromatica)
            is_shutdown = (s.get('action') == 'shutdown')
            icon_text = '⏻' if is_shutdown else '☾'
            icon_chip = ctk.CTkLabel(card, text=icon_text, width=30, height=30, fg_color="#1e1e1e", corner_radius=15, text_color=TEXT_COLOR)
            icon_chip.grid(row=0, column=0, rowspan=2, sticky='n', padx=(12, 6), pady=(12, 0))

            # Riga 0: Titolo a sinistra, Stato pill a destra
            title_text = "Spegni" if is_shutdown else "Ibernazione"
            title = ctk.CTkLabel(card, text=title_text, font=("Segoe UI", 16, "bold"))
            title.grid(row=0, column=1, sticky='w', padx=(8, 8), pady=(12, 0))

            enabled = bool(s.get('enabled', True))
            pill_color = "#1f874a" if enabled else "#555555"
            pill_text = "ON" if enabled else "OFF"
            status_pill = ctk.CTkLabel(card, text=pill_text, fg_color=pill_color, text_color="white", corner_radius=14, padx=12, pady=5, font=("Segoe UI", 11))
            status_pill.grid(row=0, column=3, sticky='e', padx=(8, 14), pady=(12, 0))
            status_pill.bind('<Button-1>', lambda e, i=idx: self._toggle_enabled_by_index(i))

            # Riga 1: Orario a sinistra, Azione a destra
            time_lbl = ctk.CTkLabel(card, text=s.get('time', ''), text_color=MUTED_TEXT, font=("Segoe UI", 12))
            time_lbl.grid(row=1, column=1, sticky='w', padx=(8, 8), pady=(4, 8))

            action_lbl = ctk.CTkLabel(card, text=("Shutdown" if is_shutdown else "Ibernazione"), fg_color="#0f0f0f", text_color=TEXT_COLOR, corner_radius=12, padx=12, pady=5, font=("Segoe UI", 11))
            action_lbl.grid(row=1, column=3, sticky='e', padx=(8, 14), pady=(4, 8))

            # Divider sottile
            divider = ctk.CTkFrame(card, height=1, fg_color=CARD_BORDER)
            divider.grid(row=2, column=0, columnspan=4, sticky='ew', padx=12, pady=(0,8))

            # Riga 3: Giorni (pills intelligenti)
            days_row = ctk.CTkFrame(card, fg_color="transparent")
            days_row.grid(row=3, column=0, columnspan=4, sticky='w', padx=12, pady=(0,12))
            days_list = sorted(s.get('days', []))
            all_days = list(range(7))
            feriali = set(range(5))  # Lun-Ven
            weekend = {5, 6}         # Sab-Dom
            if set(days_list) == set(all_days):
                ctk.CTkLabel(days_row, text='Tutti i giorni', fg_color="#1e1e1e", text_color=TEXT_COLOR, corner_radius=12, padx=10, pady=3, font=("Segoe UI", 11)).pack(side='left', padx=4)
            elif set(days_list) == feriali:
                ctk.CTkLabel(days_row, text='Feriali', fg_color="#1e1e1e", text_color=TEXT_COLOR, corner_radius=12, padx=10, pady=3, font=("Segoe UI", 11)).pack(side='left', padx=4)
            elif set(days_list) == weekend:
                ctk.CTkLabel(days_row, text='Weekend', fg_color="#1e1e1e", text_color=TEXT_COLOR, corner_radius=12, padx=10, pady=3, font=("Segoe UI", 11)).pack(side='left', padx=4)
            else:
                # Pills compatte per singoli giorni
                for d in days_list:
                    ctk.CTkLabel(days_row, text=self._get_day_name(d), fg_color="#1e1e1e", text_color=TEXT_COLOR, corner_radius=12, padx=10, pady=3, font=("Segoe UI", 11)).pack(side='left', padx=4)

            # Hover/Selezione
            def on_enter(e, w=card):
                if self.selected_row != idx:
                    w.configure(fg_color=CARD_BG_HOVER)
            def on_leave(e, w=card):
                if self.selected_row != idx:
                    w.configure(fg_color=CARD_BG)
            card.bind('<Enter>', on_enter)
            card.bind('<Leave>', on_leave)

            # Salva riferimenti card per selezione
            self.card_items.append({'frame': card, 'bg': CARD_BG})

            # Binding per selezione/doppio click
            for w in (card, icon_chip, title, time_lbl, days_row, action_lbl, status_pill):
                try:
                    w.bind('<Button-1>', lambda e, i=idx: self._select_card(i))
                    w.bind('<Double-Button-1>', lambda e, i=idx: self._on_card_double_click(i))
                except Exception:
                    pass

            # Ripristina selezione precedente se applicabile
            if prev_sel is not None and prev_sel == idx:
                try:
                    card.configure(fg_color=CARD_BG_SELECTED, border_color=ACCENT_COLOR)
                    self.selected_row = idx
                except Exception:
                    pass

    

    def _select_card(self, idx, event=None):
        """Seleziona la card all'indice dato aggiornando l'evidenziazione e lo stato interno."""
        try:
            if not hasattr(self, 'card_items'):
                return
            total = len(self.card_items)
            if not (0 <= idx < total):
                return
            # Ripristina la selezione precedente, se esiste
            prev = getattr(self, 'selected_row', None)
            if isinstance(prev, int) and 0 <= prev < total:
                try:
                    prev_frame = self.card_items[prev].get('frame')
                    if prev_frame:
                        prev_frame.configure(fg_color=CARD_BG, border_color=CARD_BORDER)
                except Exception:
                    pass
            # Applica nuova selezione
            self.selected_row = idx
            try:
                cur_frame = self.card_items[idx].get('frame')
                if cur_frame:
                    cur_frame.configure(fg_color=CARD_BG_SELECTED, border_color=ACCENT_COLOR)
            except Exception:
                pass
        except Exception:
            pass

    def _on_card_double_click(self, idx, event=None):
        try:
            self._select_card(idx)
            self._edit_schedule()
        except Exception:
            pass

    def _request_render(self):
        # Debounce del rendering per migliorare le performance durante cambi rapidi
        if self._render_pending:
            return
        self._render_pending = True
        try:
            # Se si sta ridimensionando, posticipa leggermente per evitare scatti
            if self._resizing:
                self.after(150, self._do_render)
            else:
                self.after_idle(self._do_render)
        except Exception:
            # fallback immediato
            self._do_render()

    def _do_render(self):
        self._render_pending = False
        self._render_cards()

    # -------------------- Helper di utilità per evitare duplicazioni --------------------
    def _update_overview(self, schedules):
        try:
            # Totali e attive
            total = len(schedules)
            active = sum(1 for s in schedules if s.get('enabled', True))
            if hasattr(self, 'status_var'):
                self.status_var.set(f"Regole: {total} | Attive: {active}")
            if hasattr(self, 'rules_count_var'):
                self.rules_count_var.set(str(total))
            if hasattr(self, 'active_count_var'):
                self.active_count_var.set(str(active))
            # Aggiorna pannelli laterali
            self._update_side_panels_stats(schedules)
        except Exception as e:
            print('Update overview error:', e)

        
    def _update_side_panels_stats(self, schedules):
        """Aggiorna le barre settimanali e le stats sintetiche"""
        try:
            # Weekly counts per day (solo regole attive)
            counts = [0]*7
            for s in schedules:
                if not s.get('enabled', True):
                    continue
                for d in s.get('days', []):
                    if 0 <= d < 7:
                        counts[d] += 1
            max_c = max(counts) if counts else 1
            if hasattr(self, 'week_pbars'):
                for i, p in enumerate(self.week_pbars):
                    p.set(counts[i]/max_c if max_c else 0)
            # Stats: total, active, peak day
            if hasattr(self, 'stat_total'):
                self.stat_total.set(str(len(schedules)))
            if hasattr(self, 'stat_active'):
                self.stat_active.set(str(sum(1 for s in schedules if s.get('enabled', True))))
            if hasattr(self, 'stat_peak'):
                peak_idx = counts.index(max(counts)) if counts else 0
                self.stat_peak.set(self._get_day_name(peak_idx) if max_c > 0 else '-')
        except Exception as e:
            print('Update side panels error:', e)
    
    def _on_row_click(self, event, idx):
        # Gestisce il click su una riga in modo robusto (nessun errore se non c'era selezione)
        try:
            self._select_row(idx)
        except Exception as e:
            # Non interrompere l'app se la selezione fallisce
            print("Errore selezione riga:", e)

    def _select_row(self, idx):
        # Ripristina la selezione precedente, se esiste ed è valida
        if (
            hasattr(self, 'selected_row')
            and isinstance(self.selected_row, int)
            and 0 <= self.selected_row < len(self.table_rows)
            and hasattr(self, 'selected_row_frame')
            and self.selected_row_frame is not None
        ):
            # Usa il colore originale salvato per evitare calcoli con indici e None
            prev_bg = self.table_rows[self.selected_row].get('bg', "#2b2b2b")
            try:
                self.selected_row_frame.configure(fg_color=prev_bg)
                # ripristina banda selezione
                if 'accent' in self.table_rows[self.selected_row]:
                    self.table_rows[self.selected_row]['accent'].configure(fg_color=prev_bg)
            except Exception:
                pass
        # Imposta nuova selezione
        self.selected_row = idx
        self.selected_row_frame = self.table_rows[idx]['frame']
        try:
            self.selected_row_frame.configure(fg_color=HOVER_COLOR)
            # evidenzia banda a sinistra
            if 'accent' in self.table_rows[idx]:
                self.table_rows[idx]['accent'].configure(fg_color=ACCENT_COLOR)
        except Exception:
            pass
    
    def _load_schedules(self):
        # Pulisci la tabella
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Reset selezione e righe memorizzate
        self.table_rows = []
        self.selected_row = None
        self.selected_row_frame = None
        
        # Carica le pianificazioni
        schedules = self.cfg.get('schedules', [])
        # Applica ordinamento se impostato
        if getattr(self, 'sort_column', None) is not None:
            try:
                schedules = sorted(schedules, key=lambda s: self._schedule_sort_key(s, self.sort_column), reverse=getattr(self, 'sort_reverse', False))
            except Exception:
                pass
        
        for idx, sched in enumerate(schedules):
            # Formatta i giorni
            days = sched.get('days', [])
            days_str = ", ".join([self._get_day_name(d) for d in sorted(days)])
            
            # Formatta l'azione
            action = "Spegni" if sched.get('action') == 'shutdown' else "Ibernazione"
            
            # Stato
            status = "Attivo" if sched.get('enabled', True) else "Disattivato"
            
            # Crea una riga (altezza leggermente aumentata per font piu' grande)
            row_frame = ctk.CTkFrame(self.scrollable_frame, height=29, corner_radius=3)
            row_frame.pack(fill="x", pady=0, padx=6)
            # Impedisci che il contenuto espanda l'altezza oltre quella indicata
            try:
                row_frame.pack_propagate(False)
            except Exception:
                pass
            
            # Colora le righe alternate
            bg_color = "#2b2b2b" if idx % 2 == 0 else "#333333"
            row_frame.configure(fg_color=bg_color)
            # Banda di selezione a sinistra (piu' sottile)
            accent = ctk.CTkFrame(row_frame, width=2, fg_color=bg_color)
            accent.pack(side="left", fill="y")
            
            # Aggiungi i dati
            data = [days_str, sched.get('time', ''), action, status]
            for col, text in enumerate(data):
                text_color = TEXT_COLOR if sched.get('enabled', True) else TEXT_DISABLED
                label = ctk.CTkLabel(
                    row_frame,
                    text=text,
                    text_color=text_color,
                    anchor="w",
                    justify="left",
                    font=("Segoe UI", 12)
                )
                label.pack(side="left", fill="x", expand=True, padx=6, pady=1)
            
            # Aggiungi gestore di eventi per la selezione sull'intera riga
            row_frame.bind("<Button-1>", lambda e, i=idx: self._on_row_click(e, i))
            for widget in row_frame.winfo_children():
                widget.bind("<Button-1>", lambda e, i=idx: self._on_row_click(e, i))
            # Doppio click per aprire direttamente la modifica
            row_frame.bind("<Double-Button-1>", lambda e, i=idx: (self._on_row_click(e, i), self._edit_schedule()))
            
            # Memorizza il riferimento alla riga
            self.table_rows.append({
                'frame': row_frame,
                'data': sched,
                'idx': idx,
                'accent': accent,
                'bg': bg_color
            })
        # Aggiorna barra di stato con il conteggio
        if hasattr(self, 'status_var'):
            self.status_var.set(f"Caricate {len(schedules)} pianificazioni")

    def _schedule_sort_key(self, sched, col_idx):
        # Giorni come stringa ordinabile
        days_str = ", ".join([self._get_day_name(d) for d in sorted(sched.get('days', []))])
        if col_idx == 0:
            return days_str
        if col_idx == 1:
            t = sched.get('time', '00:00')
            try:
                h, m = map(int, t.split(':'))
            except Exception:
                h, m = 0, 0
            return (h, m)
        if col_idx == 2:
            return sched.get('action', '')
        if col_idx == 3:
            return 1 if not sched.get('enabled', True) else 0  # Attivi prima
        return 0

    def _sort_by(self, col_idx):
        # Toggle reverse se stessa colonna, altrimenti ordina crescente
        if getattr(self, 'sort_column', None) == col_idx:
            self.sort_reverse = not getattr(self, 'sort_reverse', False)
        else:
            self.sort_column = col_idx
            self.sort_reverse = False
        self._load_schedules()

    def _bind_shortcuts(self):
        # Scorciatoie globali
        try:
            self.bind('<Control-n>', lambda e: self._add_schedule())
            self.bind('<F5>', lambda e: self._refresh_table())
            self.bind('<Return>', lambda e: self._edit_schedule())
            self.bind('<Delete>', lambda e: self._remove_schedule())
        except Exception:
            pass
    
    def _get_day_name(self, day_idx):
        days = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
        return days[day_idx] if 0 <= day_idx < len(days) else ""
    
    def _add_schedule(self):
        dialog = ScheduleDialog(self)
        self.wait_window(dialog)
        
        if hasattr(dialog, 'result') and dialog.result:
            if 'schedules' not in self.cfg:
                self.cfg['schedules'] = []
            # Evita duplicati (stessi giorni, ora e azione)
            new = dialog.result
            exists = any(
                (set(s.get('days', [])) == set(new.get('days', [])) and
                 s.get('time') == new.get('time') and
                 s.get('action') == new.get('action'))
                for s in self.cfg['schedules']
            )
            if exists:
                Messagebox.show_warning("Una pianificazione identica esiste già", "Duplicato")
                return
            # Aggiungi, salva e ricarica la tabella
            self.cfg['schedules'].append(new)
            save_config(self.cfg)
            self._after_config_change("Pianificazione aggiunta con successo")
    
    def _edit_schedule(self):
        # Modifica la riga selezionata con controllo duplicati
        if not hasattr(self, 'selected_row') or self.selected_row is None:
            Messagebox.show_warning("Seleziona una pianificazione da modificare", "Attenzione")
            return
        idx = self.selected_row
        schedules = self.cfg.get('schedules', [])
        if not (0 <= idx < len(schedules)):
            Messagebox.show_warning("Selezione non valida", "Attenzione")
            return
        dialog = ScheduleDialog(self, schedules[idx].copy())
        self.wait_window(dialog)
        if hasattr(dialog, 'result') and dialog.result:
            updated = dialog.result
            # Evita duplicati con altri elementi
            for j, s in enumerate(schedules):
                if j == idx:
                    continue
                if (
                    set(s.get('days', [])) == set(updated.get('days', []))
                    and s.get('time') == updated.get('time')
                    and s.get('action') == updated.get('action')
                ):
                    Messagebox.show_warning("Esiste già una pianificazione identica", "Duplicato")
                    return
            self.cfg['schedules'][idx] = updated
            save_config(self.cfg)
            self._after_config_change("Pianificazione aggiornata")
    
    def _remove_schedule(self):
        if not hasattr(self, 'selected_row') or self.selected_row is None:
            Messagebox.show_warning("Seleziona una pianificazione da rimuovere", "Attenzione")
            return
        
        idx = self.selected_row
        if 0 <= idx < len(self.cfg.get('schedules', [])):
            if Messagebox.show_question(
                "Conferma rimozione",
                "Sei sicuro di voler rimuovere questa pianificazione?"
            ):
                del self.cfg['schedules'][idx]
                save_config(self.cfg)
                self._after_config_change("Pianificazione rimossa")
                self.selected_row = None

    def _on_scale_change(self, value: str):
        # Applica scala UI subito e salva in config
        try:
            pct = int(value.replace('%','').strip())
            scale = max(0.6, min(1.5, pct/100.0))
            ctk.set_widget_scaling(scale)
            ctk.set_window_scaling(scale)
            self.cfg['ui_scale'] = scale
            save_config(self.cfg)
            # Non forziamo un rerender completo: CTk ridisegna i widget con la nuova scala
        except Exception as e:
            print('UI scale change error:', e)
    
    def _refresh_table(self):
        # Rirenderizza le cards e aggiorna i contatori
        if hasattr(self, '_request_render'):
            self._request_render()
        self.status_var.set("Vista aggiornata")

    def _after_config_change(self, status_msg: str = ""):
        """Salva config, ricarica vista e mantiene selezione valida."""
        try:
            save_config(self.cfg)
        except Exception:
            pass
        # Rirenderizza
        try:
            self._request_render()
        except Exception:
            pass
        # Aggiorna stato
        try:
            if status_msg:
                self.status_var.set(status_msg)
        except Exception:
            pass

    def _test_countdown(self):
        # Mostra un semplice test di avviso senza spegnere nulla
        try:
            Messagebox.show_info("Test Countdown", "Esempio di avviso: il PC verrebbe spento tra 20 secondi (TEST)")
        except Exception as e:
            print("Errore test countdown:", e)
    
    def _toggle_autostart(self):
        enabled = self.autostart_var.get()
        if set_autostart(enabled):
            self.status_var.set("Avvio automatico " + ("abilitato" if enabled else "disabilitato"))
        else:
            self.autostart_var.set(not enabled)
            self.status_var.set("Errore durante l'aggiornamento dell'avvio automatico")
    
    def _toggle_theme(self):
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        ctk.set_appearance_mode(self.theme_mode.capitalize())
        
        # Salva la preferenza del tema
        self.cfg['theme'] = self.theme_mode
        save_config(self.cfg)
        
        # Ricarica l'interfaccia per applicare il tema
        self._setup_ui()

    def _toggle_fullscreen(self):
        try:
            if not self.is_fullscreen:
                # Entra in fullscreen
                self.is_fullscreen = True
                # Su Windows fullscreen vero può coprire la taskbar; alternativa è state('zoomed')
                try:
                    self.attributes('-fullscreen', True)
                except Exception:
                    self.state('zoomed')
            else:
                self._exit_fullscreen()
        except Exception:
            pass

    def _exit_fullscreen(self):
        try:
            self.is_fullscreen = False
            try:
                self.attributes('-fullscreen', False)
            except Exception:
                self.state('normal')
            # Ripristina dimensioni fisse e blocca resize
            self.geometry(f"{self.fixed_width}x{self.fixed_height}")
            self.minsize(self.fixed_width, self.fixed_height)
            self.maxsize(self.fixed_width, self.fixed_height)
            self.resizable(False, False)
            # Centra nuovamente dopo aver ripristinato la finestra
            try:
                self.after(0, self._center_window)
            except Exception:
                self._center_window()
        except Exception:
            pass

    def _center_window(self):
        try:
            # Ottieni l'area di lavoro del monitor corrente (sotto il mouse)
            left, top, right, bottom = self._get_work_area()
            aw = max(100, right - left)
            ah = max(100, bottom - top)
            # Usa le dimensioni già impostate (non ridimensionare qui)
            self.update_idletasks()
            w = self.winfo_width() or self.fixed_width
            h = self.winfo_height() or self.fixed_height
            x = left + max(0, (aw - w) // 2)
            y = top + max(0, (ah - h) // 2)
            # Sposta soltanto
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
    
    def _get_work_area(self):
        # Restituisce (left, top, right, bottom) dell'area di lavoro disponibile
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            # Coordinate del cursore per scegliere il monitor corrente
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            MONITOR_DEFAULTTONEAREST = 2
            hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                # rcWork esclude taskbar
                return mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom
        except Exception:
            pass
        # Fallback: intero schermo
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
    
    def _start_scheduler(self):
        if self.scheduler and self.scheduler.is_alive():
            self.stop_event.set()
            self.scheduler.join(timeout=2.0)
        
        self.stop_event = threading.Event()
        self.scheduler = SchedulerThread(self._get_schedules, self.stop_event, app=self)
        self.scheduler.start()
    
    def _get_schedules(self):
        return self.cfg.get('schedules', [])
    
    def _create_tray_icon(self):
        if not PYSYSTRAY_AVAILABLE:
            print("System tray functionality not available (pystray not installed)")
            return
        try:
            # Icona monocromatica coerente con la palette
            def create_image(size=24):
                s = max(16, min(128, size))
                img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
                dc = ImageDraw.Draw(img)
                # cerchio esterno accent
                dc.ellipse((1, 1, s-2, s-2), outline=ACCENT_COLOR, width=max(2, s//12))
                # simbolo power interno
                cx, cy = s//2, s//2
                r = s//4
                dc.arc((cx-r, cy-r, cx+r, cy+r), start=300, end=240, fill=ACCENT_COLOR, width=max(2, s//14))
                # lineetta centrale
                dc.line((cx, cy-r-1, cx, cy-r//2), fill=ACCENT_COLOR, width=max(2, s//14))
                return img

            image = create_image(24)
            menu = pystray.Menu(
                pystray.MenuItem("Apri", lambda icon=None, item=None: self._show_window()),
                pystray.MenuItem("Esci", lambda icon=None, item=None: self._on_quit())
            )
            self.tray_icon = pystray.Icon("ShutdownScheduler", image, "Shutdown Scheduler", menu)
            self.tray_icon.run_detached()
        except Exception as e:
            print("Error creating tray icon:", e)

    def _show_window(self, icon=None, item=None):
        """Mostra la finestra principale dal tray o altrove."""
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass
        self.focus_force()
    
    def _on_close(self):
        if PYSYSTRAY_AVAILABLE and hasattr(self, 'tray_icon') and self.tray_icon:
            # Nascondi la finestra invece di chiudere l'applicazione
            self.withdraw()
        else:
            # Se la system tray non è disponibile, chiudi l'applicazione
            self._on_quit()
    
    def _on_quit(self):
        # Esegui lo shutdown in modo sicuro dal main thread Tk
        def _shutdown():
            if PYSYSTRAY_AVAILABLE and hasattr(self, 'tray_icon') and self.tray_icon:
                try:
                    self.tray_icon.visible = False
                    self.tray_icon.stop()
                except Exception:
                    pass
            # Ferma lo scheduler
            try:
                if getattr(self, 'scheduler', None) and self.scheduler.is_alive():
                    self.stop_event.set()
                    self.scheduler.join(timeout=2.0)
            except Exception:
                pass
            # Chiudi l'app
            try:
                self.destroy()
            except Exception:
                pass
        try:
            self.after(0, _shutdown)
        except Exception:
            _shutdown()

# Funzione principale
def main():
    # Crea l'applicazione
    app = ModernShutdownScheduler()
    # Avvia il loop principale
    app.mainloop()

if __name__ == "__main__":
    # Assicurati che il processo non mostri una finestra della console quando eseguito come script
    if sys.platform == "win32" and not hasattr(sys, "frozen"):
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    # Avvia l'applicazione
    main()
