# 🖥️ Shutdown Scheduler

A Windows application written in **Python** that allows you to **schedule PC shutdown or hibernation** based on time and selected weekdays, with a simple graphical interface and an option for automatic startup.

---

## ✨ Features
- Schedule multiple rules with:
  - Selectable weekdays (Mon → Sun)
  - Custom time (HH:MM)
  - Action: **Shutdown** or **Hibernate**
  - Enabled/Disabled state
- Notification with a **20-second countdown** before execution, with the option to cancel
- Graphical User Interface (GUI) built with **tkinter**
- Automatic saving of rules in `%APPDATA%\PyShutdownScheduler\config.json`
- Option to enable/disable **autostart on Windows login** (via Windows Registry)
- Also works as a `.exe` compiled with **PyInstaller**

---
