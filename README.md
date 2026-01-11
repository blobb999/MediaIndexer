# 🚀 MediaIndexer - Schnellstart für Einsteiger

## Haupt-App (MediaIndexer.exe)

### 3-Minuten-Start

**1. Ordner öffnen**
- Klick auf "Select Folder" oben
- Wähle deinen Musik/Film-Ordner

**2. Erste Suche**
- Suchbegriff oben eingeben
- Auf "Search" klicken
- Datei anklicken zum Abspielen

**3. Mouse-Over für Infos**
- Maus über Datei halten → Infos + Cover

### ⚙️ Wichtigste Einstellung

- Settings → ✅ "Use Database for Search" aktivieren
- Settings → "Train DB" einmal klicken (dauert beim ersten Mal)

### 📊 Statistiken

- Analytics → Übersicht über deine Sammlung

### 🎯 TL;DR Version

1. Ordner wählen
2. Suchen (braucht erst "Train DB")
3. Mouse-Over für Details
4. Analytics für Übersicht

**Fertig. Mehr muss man nicht wissen.**

---

## Web-App (MediaIndexerHTML.exe)

### 🚀 SOFORT STARTEN

1. Binary starten (`media_platform.exe`)
2. Browser öffnet automatisch: `http://localhost:8010`
3. **Fertig!** Medien werden automatisch erkannt

> **Hinweis**: FFmpeg wird automatisch mit MediaIndexer installiert - kein manueller Download nötig!

### 📁 MEDIEN ORGANISIEREN

- Filme/Serien/Musik in beliebige Ordner legen
- App erkennt automatisch: Kategorie, Genre, Staffel, Episode
- **Keine manuelle Kategorisierung nötig**

**Beispiel-Struktur:**
```
Medien/
├── Filme/Action/Die Hard.mp4
├── Serien/Sci-Fi/Star Trek/Staffel 1/S01E01.mkv
└── Musik/Rock/Pink Floyd/Dark Side/01 - Speak to Me.mp3
```

### 🔍 FILTERN & FINDEN

**Navigation:**
```
Kategorie → Genre → Untergenre → Serie → Staffel
```

**In der Web-Oberfläche:**
- **Kategorie-Tabs** oben: Alle, Film, Serie, Musik...
- **Suchfeld** rechts oben: Sofort-Suche
- **Filter-Panel** (🔧-Icon): Detaillierte Filter

### 🎥 MEDIEN ABSPIELEN

- **Karte anklicken** → Sofort-Wiedergabe
- **Video-Player**: Vollbild, Lautstärke, Suche
- **Fortsetzen** (grünes Symbol): Setzt an letzter Position fort

### ⚡ TASTATUR-SHORTCUTS

| Taste | Funktion |
|-------|----------|
| **Leertaste** | Play/Pause |
| **← →** | 10s vor/zurück |
| **F** | Vollbild |
| **M** | Stumm |
| **Esc** | Player schließen |

### ⚙️ EINSTELLUNGEN

- **Themen** (🌙/☀️): Dark/Light Mode
- **Netzwerk-Freigabe**: Andere Geräte im Netzwerk erlauben
- **History**: Letzte Wiedergaben anzeigen
- **Autoplay**: Nächstes Video automatisch starten

### 💡 WICHTIGE TIPPS

✅ **Kein Setup** → Einfach Ordner mit Medien füllen
✅ **Thumbnails** werden automatisch erstellt
✅ **Alle Video-Formate** werden unterstützt (MKV, AVI, MP4, etc.)
✅ **Mobile Geräte**: Gleiche URL im Browser öffnen
✅ **Beenden**: App-Fenster schließen oder Taskleiste-Icon

### 🆘 BEI PROBLEMEN

**Erste Hilfe:**
1. **App neu starten** → Behebt 90% der Probleme
2. **Thumbnail-Cache löschen** über Einstellungen
3. **Browser-Cache leeren** (Strg+F5)

**Port bereits belegt?**
- Andere Programme auf Port 8010 schließen
- Oder in den Einstellungen anderen Port wählen

**Video lädt nicht?**
- FFmpeg ist bereits mit MediaIndexer installiert
- Prüfe ob Datei wirklich existiert
- Versuche anderen Browser

**Keine Thumbnails?**
- Gib der App Zeit (erste Thumbnail-Generierung dauert)
- Prüfe Schreibrechte im Programmordner

### 🌐 NETZWERK-MODUS (Optional)

**Für Zugriff von anderen Geräten im Haus:**

1. Settings → "Network Mode" aktivieren
2. Lokale IP wird angezeigt (z.B. `192.168.1.100:8010`)
3. Auf Tablet/Handy: Diese IP im Browser eingeben

⚠️ **Nur in privaten Netzwerken nutzen!**

### 📱 MOBILE GERÄTE

**Smartphone/Tablet im gleichen WLAN:**
1. Netzwerk-Modus aktivieren (siehe oben)
2. Browser öffnen → IP-Adresse eingeben
3. Zum Homescreen hinzufügen (wie eine App nutzen)

### 🎬 BEISPIEL-WORKFLOW

**Filme schauen:**
1. App starten
2. Kategorie "Film" wählen
3. Genre (z.B. "Action") anklicken
4. Film auswählen → Abspielen

**Serie weiterschauen:**
1. Kategorie "Serie" wählen
2. Deine Serie anklicken
3. "Weiterschauen" (grünes Symbol) → Setzt an letzter Stelle fort

**Musik hören:**
1. Kategorie "Musik"
2. Artist/Album wählen
3. Track abspielen
4. Optional: Crossfade-Plugin für nahtlose Übergänge

---

## 🎓 FORTGESCHRITTENE FEATURES

### Hierarchie verstehen

Die App erkennt automatisch:

**Filme:**
- Franchise (Marvel, DC, etc.)
- Film-Reihen (Teil 1, 2, 3...)
- Jahr, Genre

**Serien:**
- Staffeln (S01, S02...)
- Episoden (E01, E02...)
- Serien-Name

**Musik:**
- Artist
- Album
- Track-Nummer

### Plugin-System

**Crossfade-Plugin** (für Musik):
- Settings → Plugins → Crossfade aktivieren
- Nahtlose Übergänge zwischen Songs

**Eigene Plugins:**
- Ordner `plugins/mein_plugin/` erstellen
- App neu starten → Plugin wird geladen

### Statistiken & Analytics

**In der Web-App:**
- Analytics-Seite: Übersicht über Sammlung
- Anzahl Filme/Serien/Musik
- Genre-Verteilung
- Meistgesehene Medien

---

## ❓ FAQ

**Brauche ich technisches Wissen?**
→ Nein! Binary starten, Ordner wählen, fertig.

**Werden meine Daten hochgeladen?**
→ Nein! Alles bleibt 100% lokal auf deinem PC.

**Kostet es etwas?**
→ Nein! Komplett kostenlos für private Nutzung.

**Funktioniert es ohne Internet?**
→ Ja! Alles läuft lokal, kein Internet nötig.

**Kann ich es im ganzen Haus nutzen?**
→ Ja! Netzwerk-Modus aktivieren → Alle Geräte im WLAN können zugreifen.

**Welche Formate werden unterstützt?**
→ Alle gängigen: MP4, MKV, AVI, MP3, FLAC, JPG, PNG, etc.

**Muss ich Medien umbenennen?**
→ Nein! Die App erkennt automatisch Struktur und Metadaten.

---

## 🎉 FERTIG!

**Das war's! Mehr brauchst du nicht zu wissen.**

Bei Problemen: GitHub Issues → [Issues](https://github.com/blobb999/MediaIndexer/issues)

---

**"Binary starten → Browser öffnet → Medien genießen"**

Viel Spaß mit deiner privaten Media-Bibliothek! 🍿🎬🎵