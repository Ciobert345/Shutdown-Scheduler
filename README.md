# 🖥️ Shutdown Scheduler

A Windows application written in **Python** that allows you to **schedule PC shutdown or hibernation** based on time and selected weekdays, with a simple graphical interface and an option for automatic startup.

---

## ✨ Features
- Schedule multiple rules with:
  - Selectable weekdays (Mon → Sun)
  - Custom time (HH:MM)
  - Action: **Shutdown** or **Hibernate**
  - Enabled/Disabled state
- Modern graphical User Interface 
- Automatic saving of rules in `%APPDATA%\PyShutdownScheduler\config.json`
- Option to enable/disable **autostart on Windows login** (via Windows Registry)
- Autostart minimized to system tray** for a cleaner startup experience
- Also works as a `.exe` compiled with **PyInstaller**

---
