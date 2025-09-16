🖥️ PyShutdownScheduler

Un’applicazione per Windows scritta in Python che permette di programmare lo spegnimento o l’ibernazione del PC in base a orari e giorni della settimana, con interfaccia grafica semplice e opzione di avvio automatico.

✨ Funzionalità

Pianificazione di più regole con:

Giorni della settimana selezionabili (lun → dom)

Orario personalizzato (HH:MM)

Azione: Spegni o Iberna

Stato attivo/disattivo

Avviso con countdown di 20 secondi prima dell’esecuzione, con possibilità di annullare.

Interfaccia grafica (GUI) realizzata con tkinter.

Salvataggio automatico delle regole in %APPDATA%\PyShutdownScheduler\config.json.

Opzione per abilitare/disabilitare l’avvio automatico all’accesso di Windows (tramite registro di sistema).

Funziona anche da .exe compilato con PyInstaller.

🚀 Come usarlo

Avvia lo script Python:
