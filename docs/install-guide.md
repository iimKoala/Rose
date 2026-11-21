# Download Rose and get it running

This is the fork at [iimKoala/Rose](https://github.com/iimKoala/Rose): the original Rose skin changer plus an account switcher, a mod store, builds, in-game panels and auto accept ([what is whose](https://github.com/iimKoala/Rose#what-is-whose)). It takes about ten minutes, most of it downloads.

> This text is also the description of the [Installer and tools](https://github.com/iimKoala/Rose/releases/tag/tools) release.

## Before you start

| You need | Notes |
|---|---|
| Windows 10 or 11 | Rose asks for administrator rights each time it starts. |
| League of Legends | Installed, and started at least once. |
| [LTK Manager](https://github.com/LeagueToolkit/ltk-manager/releases) | The mod tool Rose applies skins through. Download its installer from that page and run it. You never have to open it: Rose starts it in the background and closes it after the game. |
| An internet connection | About 20 MB of downloads, plus Python's packages. |
| Python 3.11 or newer | Nothing to do. If you have none, the installer installs Python 3.13 with `winget`, Windows' own package tool. |

If the **original Rose** is installed on the same PC: the two share one settings folder and must not run at once. Uninstall the original, or switch off its start with Windows.

## 1. Download the installer

Download **[Install-Rose.bat](https://github.com/iimKoala/Rose/releases/download/tools/Install-Rose.bat)** (2 KB). It is the first file under **Assets** on the release page.

- Your browser may say the file is not commonly downloaded. Choose **Keep**.
- It is a text file of about 40 lines. To read it before you run it: right-click it, **Edit**.
- You do not need `rose-tools.zip`: the installer downloads it by itself.

## 2. Run it

Double-click `Install-Rose.bat`.

- Windows may show a blue **Windows protected your PC** box, because the file is new and not signed. Press **More info**, then **Run anyway**.
- A black window opens and says what it is doing:

| The window says | What happens |
|---|---|
| `Installing Python 3.13...` | Only when you have no Python 3.11 or newer. |
| `Downloading the newest Rose...` | Rose's source from this repository, about 11 MB. |
| `Installing Rose's Python packages (a few minutes the first time)...` | Rose gets its own Python environment. Your other Python programs are not touched. |
| `Downloading the programs Rose starts (Pengu Loader, the mod bridge)...` | `rose-tools.zip` from the release, about 9 MB. |
| `Rose is installed in C:\Users\<you>\AppData\Local\Programs\Rose.` | Done. A **Rose** shortcut is on your Desktop. |

Press a key to close the window.

## 3. Start Rose

1. Double-click the **Rose** shortcut on your Desktop, and answer **Yes** when Windows asks for administrator rights.
2. A window named **Rose** opens. It looks for a new version, then says `Starting Rose. Keep this window open; close it to stop Rose.` Rose's icon appears in the tray, next to the clock.
3. Start League of Legends.

The League client loads Rose's plugins only when it starts. So start Rose first, then League. If the client is already open when Rose starts, Rose restarts the client once by itself.

## 4. Check that it works

In the League client's top bar, on the right, you should see Rose's own button and three more:

| Button | What it opens |
|---|---|
| A person | The **account switcher**: save your accounts, sign in to one with a press. |
| A shopping bag | The **mod store**. |
| A check mark | **Auto accept**. Grey is off, gold is on. It is off until you press it. |

Then:

- **Champion select**: hover any skin of your champion, owned or not. It is applied when the game starts. The **Builds** panel shows the builds of the champion's best one-trick players.
- **In the game** (borderless or windowed): the build strip sits between the minimap and your abilities, with your CS a minute in a row above it (**Ctrl+Shift+C** turns that row off and on). Hold **Tab** for the gold board. Press **Ctrl+X** for the player stats.

Play one Practice Tool game first: it shows in a minute whether skins load.

## Updates

Nothing to do.

- Each time Rose starts, it asks GitHub whether there is a new version and installs it.
- While Rose runs, it asks every 30 minutes and downloads a new version in the background. When you are not in a game, a queue or champion select, a window asks **Restart Rose now to install it?** Yes restarts Rose in the same window. No keeps it running: the next start installs it.
- An update never touches your accounts, mods or settings.

## Where things are

| What | Where |
|---|---|
| Rose itself | `%LOCALAPPDATA%\Programs\Rose` |
| Your accounts list, mods, settings | `%LOCALAPPDATA%\Rose` |
| Logs | `%LOCALAPPDATA%\Rose\logs`, or the tray icon's **Open Logs folder** |
| Saved passwords | Windows Credential Manager, under `Rose-AccountSwitcher`. Never in a file. |

To paste one of those paths: press **Win+R**, paste it, press Enter.

## If something goes wrong

| What you see | What to do |
|---|---|
| `Python could not be installed automatically.` | Your Windows has no `winget`. Install Python 3.13 from [python.org](https://www.python.org/downloads/windows/) (leave **py launcher** ticked), then run `Install-Rose.bat` again. |
| `The installer could not be downloaded.` | Check your internet connection. A firewall or DNS filter may block `raw.githubusercontent.com`. Run the file again. |
| `Rose was not installed. The reason is above.` | Read the line above it. Running the file again is safe: it only does what is still missing. |
| `Rose could not be updated: ...` at a start | Rose starts anyway, as it is, and tries again next time. GitHub answers this question 60 times an hour for one internet address. |
| No Rose buttons in the client | Is Rose's icon in the tray? Close the League client and open it again while Rose runs. Still nothing: right-click the tray icon, **Diagnose Rose startup**. |
| Skins do not show in the game | LTK Manager must be installed and closed. If Rose cannot find it, press **Set up path** at Rose's start and pick `ltk-manager.exe`. |
| Rose says LTK Manager's patcher is missing | An antivirus removed it. Reinstall LTK Manager and add its folder (`C:\Program Files\LTK Manager`) to your antivirus exclusions. |
| The window closes at once | Start the shortcut again and read the last lines. They are also in the newest file of the logs folder. |
| Something from the original stopped working | The original's own guide: [docs/troubleshooting.md](https://github.com/iimKoala/Rose/blob/release/docs/troubleshooting.md). |

A problem with the account switcher, the mod store, builds, the panels or auto accept is this fork's. The original project's authors do not support it: please do not report it to them.

## Uninstall

1. Quit Rose: right-click its tray icon, **Quit**. Rose then switches the League client's plugin loader off again. Do this before you delete anything.
2. Delete the folder `%LOCALAPPDATA%\Programs\Rose` and the shortcut on your Desktop.
3. To remove your data as well: delete `%LOCALAPPDATA%\Rose`, and in Windows Credential Manager the entries named `Rose-AccountSwitcher`.

LTK Manager and Python are programs of their own: remove them in Windows' settings if you no longer want them.

## What is in this release

- **Install-Rose.bat**: the installer described above.
- **rose-tools.zip**: the programs Rose starts that are not in the source. The installer downloads it.
  - `Pengu Loader.exe`: built from `vendor/PenguLoader-1.1.6`
  - `LeagueToolFlop.dll`, `ltk_launcher.exe`: built from `native/ltf`
  - `rose-mod-check.exe`: built from `native/rose-mod-check` (GPL-3.0-or-later; its source is in that folder)

Rose is not endorsed by Riot Games. Riot does not allow custom skins: use it at your own risk ([disclaimer](https://github.com/iimKoala/Rose#disclaimer)).
