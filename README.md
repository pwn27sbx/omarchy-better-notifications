# Omarchy Better Notifications 🔔

A powerful, highly-dense, and beautifully organized notification center replacement for the Omarchy shell. 

Tired of messy notification lists? **Better Notifications** overhauls the default Omarchy notification panel to bring a sleek, hacker-friendly aesthetic with modern features like App-grouping (Windows 11 / macOS style) and rich media previews.

## ✨ Features

- **📱 Smart App Grouping:** Automatically groups notifications by application. The app with the most recent activity bubbles to the top!
- **📸 Rich Thumbnails:** Screenshots and media notifications now display a beautiful rounded thumbnail preview right inside the history list.
- **🗂️ Split Captures Tab:** Keep your alerts clean. Toggle the "Separate Captures" setting to move all your screen recordings and screenshots into a dedicated tab.
- **⚡ Optimistic UI Toggle:** A blazing-fast Do Not Disturb (DND) switch that reacts instantly without waiting for DBus roundtrips.
- **📐 Ultra-Compact Design:** Re-engineered margins, padding, and spacing to display maximum information on screen while maintaining a clean, technical aesthetic.
- **🖱️ Click to Focus:** Click on any notification to instantly focus the window of the application that sent it (or open the image in your editor).
- **🌍 Native i18n:** Automatically detects your Omarchy system language (supports English, Spanish, etc.) and translates the interface seamlessly.

## 🚀 Installation

Installing this plugin is incredibly simple thanks to Omarchy's native plugin manager.

1. Open your terminal.
2. Run the following one-liner command:
   ```bash
   omarchy plugin add https://github.com/pwn27sbx/omarchy-better-notifications.git --enable
   ```

Omarchy will automatically clone the repository, install it into your `~/.local/share/omarchy/plugins/` directory, and load it into your shell.

## 🗑️ Removal

If you ever wish to uninstall the plugin and return to the default Omarchy notifications, simply run:
```bash
omarchy plugin remove hero-notifications
```

## 🛠️ Usage & Configuration

Once installed, the widget integrates directly into your Omarchy top bar. 
- Click the **Bell Icon** to open the panel.
- Click the **Gear Icon** to access the settings (like toggling the split Captures tab).
- Hit **Clear all** to instantly purge your local notification cache.

## 🤝 Contributing
Feel free to open an issue or submit a Pull Request if you have ideas to make this notification center even better!
