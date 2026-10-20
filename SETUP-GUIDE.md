# Setting Up the Dynamic Documentary Engine

**A guide for running the engine on your own computer.**

No coding required. You will install two free programs once, then start the
engine by double-clicking a file — the same way you'd open any other
application.

Prepared for Dr. Betsy Campbell
Dynamic Documentary Engine · Penn State University, College of IST
Contact for help: Oluwafemisola David Ademoye (ademoyedavid11@gmail.com)

---

## Before you begin

- Set aside about **20 minutes** for the one-time setup.
- You'll need to be connected to the **internet** for setup. After that the
  engine works completely offline.
- You'll need the **project folder** and the **film clips**. These arrive
  separately — see [Step 3](#step-3--put-the-project-on-your-computer) and
  [Step 4](#step-4--add-the-film-clips).

**Which set of instructions do I follow?**
Look at your keyboard. If the key beside the space bar says **command (⌘)**,
you have a Mac. If it says **Alt**, you have a Windows PC. Follow the
matching sections below and ignore the other.

---

## Step 1 — Install Python

Python is the language the engine is written in. Your computer needs it to
run the engine, the same way it needs a PDF reader to open a PDF.

### On a Mac

1. Go to **https://www.python.org/downloads/**
2. Click the large yellow **Download Python** button at the top.
3. Open the file that downloads (it'll be in your Downloads folder).
4. Click **Continue** / **Agree** / **Install** through the installer,
   entering your Mac password when asked.
5. When it says the installation was successful, click **Close**.

### On Windows

1. Go to **https://www.python.org/downloads/**
2. Click the large yellow **Download Python** button at the top.
3. Open the file that downloads.
4. **This step matters.** On the very first screen of the installer, tick
   the box at the bottom that says **Add python.exe to PATH**. It is easy
   to miss, and the engine will not start without it.
5. Click **Install Now** and let it finish.

> If you miss the PATH box, no harm done — run the installer again, choose
> **Modify**, and make sure that box is ticked.

---

## Step 2 — Install FFmpeg

FFmpeg is the tool that actually assembles the video and audio into a film.
Without it, the engine can choose the clips but can't build the movie.

### On a Mac

FFmpeg doesn't have a normal installer on a Mac, so this is the one place
you'll paste a line of text. It's safe, and you only do it once.

1. Press **Command (⌘) + Space**, type `Terminal`, and press **Return**.
   A window with plain text appears. This is normal.
2. Copy the line below exactly and paste it into that window, then press
   **Return**:

   ```
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   This installs **Homebrew**, a tool that installs other tools. It will
   ask for your Mac password — type it and press Return. You won't see the
   characters as you type; that's normal.

3. When it finishes, it may print a couple of lines beginning with
   `eval` and ask you to run them. If it does, copy and paste those too.
4. Now paste this line and press **Return**:

   ```
   brew install ffmpeg
   ```

5. Wait. This takes several minutes and prints a lot of text. When you get
   a fresh prompt back, it's done. You can close the Terminal window.

### On Windows

1. Press the **Windows key**, type `PowerShell`, and press **Enter**.
2. Copy the line below into that window and press **Enter**:

   ```
   winget install --id Gyan.FFmpeg -e
   ```

3. If it asks you to agree to terms, type `Y` and press Enter.
4. When it finishes, **close the PowerShell window**. Windows only notices
   newly installed programs in a fresh window.

> **If it says `winget` is not recognised**, your Windows version is a
> little older. Do this instead:
> 1. Go to **https://www.gyan.dev/ffmpeg/builds/**
> 2. Under *release builds*, download **ffmpeg-release-essentials.zip**
> 3. Right-click the downloaded file → **Extract All**
> 4. Rename the extracted folder to `ffmpeg` and drag it to your `C:\` drive,
>    so you have `C:\ffmpeg`
> 5. Press the Windows key, type `environment variables`, and open
>    **Edit the system environment variables**
> 6. Click **Environment Variables…** → under *System variables* select
>    **Path** → **Edit** → **New** → type `C:\ffmpeg\bin` → **OK** on every
>    window
> 7. Restart your computer

---

## Step 3 — Put the project on your computer

You'll receive the project as a single `.zip` file (or on a USB drive). It
is made with the packaging step at the end of this guide, and usually
already contains the film clips.

1. If it's a `.zip`, double-click it to unzip it.
2. Move the resulting **`dynamic-documentary-engine`** folder somewhere
   you'll find it again — your **Documents** folder is a good choice.

Keep the folder together. Everything inside it is needed, and moving pieces
out will stop the engine from working.

---

## Step 4 — Add the film clips

**If your package already includes the clips** (the usual case), they're
already in place — look inside `local-media/WWII/assets/b-roll` to check,
then skip to Step 5. Read on only to add more clips.

A package made *without* footage (or a copy downloaded from GitHub) has the
engine but not the video and audio clips. Without them the engine starts
fine but says a topic has no footage.

Inside the project folder, open **`local-media`**. You'll see a folder for
each film topic, for example:

```
local-media/
├── WWII/
│   ├── assets/
│   │   ├── a-roll/     <- video clips WITH their own sound
│   │   ├── b-roll/     <- video clips with NO sound
│   │   └── x-roll/     <- sound only (music, narration, ambience)
│   ├── titles/
│   │   ├── opening/    <- an opening piece for this topic (optional)
│   │   └── closing/    <- a closing piece for this topic (optional)
│   └── artifacts/      <- finished films appear here
└── Validation/
    └── ...
```

Copy your clips into the right `a-roll`, `b-roll`, or `x-roll` folder for
the topic they belong to. That's all — the engine notices new files by
itself. Reload the page in your browser and the new count appears beside
the topic name. Nothing to register, no settings to change.

**How many sound files do I need?** Every silent `b-roll` clip is paired
with an `x-roll` sound file. There's no minimum — a topic with sixteen
video clips and two sound files still uses all sixteen clips, sharing the
audio between them and playing a different passage of each recording every
time it's heard.

More recordings simply means less sharing. The engine always reaches for
whatever has been heard least, so once you have about as many sound files
as video clips, nothing repeats at all. Anywhere in between works fine.

Clips in `a-roll` already carry their own sound and don't need a partner.

**Which folder does a clip go in?**

| If the clip is… | Put it in |
|---|---|
| Video that already has the sound you want | `a-roll` |
| Video you want other sound played over | `b-roll` |
| Sound only — music, narration, atmosphere | `x-roll` |

**Adding a new topic** (say, "Swiss"): make a folder inside `local-media`
named after the topic, and inside it create `assets` (containing `a-roll`,
`b-roll` and `x-roll`) and `artifacts`. It appears in the engine's topic
list automatically.

---

## Step 5 — Start the engine

Open the project folder and double-click:

- **Mac** → `Start Engine (Mac).command`
- **Windows** → `Start Engine (Windows).bat`

A window of plain text opens, checks everything is installed, and then your
browser opens automatically at the engine.

**You never type anything into the text window.** Leave it open while you
use the engine — closing it stops the engine.

> **First time on a Mac:** you may see *"cannot be opened because it is
> from an unidentified developer."* Click **OK**, then **right-click** the
> Start Engine file and choose **Open**, then **Open** again. You only
> need to do this once.

> **First time on Windows:** you may see a blue *"Windows protected your
> PC"* box. Click **More info**, then **Run anyway**. Once only.

> **If your browser doesn't open by itself**, look in the text window for a
> line like `http://127.0.0.1:5001` and type that into your browser.

---

## Step 6 — Make a film

1. Choose a **Film topic**.
2. Set the **Target length** — you can enter it in seconds or minutes.
3. Click **Generate Film**.
4. Wait. A short film takes under a minute; longer ones take proportionally
   longer, roughly a third of the film's own length. A 30-minute film takes
   about 10 minutes to build.
5. The film plays in the page when it's ready.

Everything you make is saved under **Previously generated films**, so you
can go back to any of them.

**The two switches:**

- **Diversity mode** — spreads usage across your clips so the same
  favourites don't dominate every film.
- **Exact duration** — makes the film match your requested length exactly.
  Off by default, because it trims the final clip mid-shot to hit the
  number. Left off, films use whole clips and land a few seconds short.

**Memory triggers** (optional) — switch this on and the film favours clips
whose date or season matches today's (taken from the computer's clock), and
always brings the best match in partway through. Type a word or phrase in
**Cue** (say, *Camp Swift*) to also bring up clips labelled with exactly
that. It only has an effect once clips are labelled — see the next step.

---

## Step 6½ — Label your clips (Clip library)

Click **Clip library** at the top-right of the main page. You'll see a
table with one row per clip in the chosen topic — the clips are found from
the folders by themselves. Each row starts with a small picture of the
clip: rest the mouse on it to see the clip play silently right there, or
click it (or its ▶) to watch it with sound. The very first time a clip is
played it takes a few seconds to prepare.

1. Choose the **Film topic** at the top.
2. In a clip's row, click the **Date** cell and type the date, e.g.
   *8 May 1945*, *December 1944* or just *1944*. Press **Enter**: it saves
   and moves down to the next clip, so you can work down the column.
3. If only the season is known, choose it in **Season** (leave it on *Auto*
   when there's a date).
4. Optionally add a **Title**, **Mood**, **Tags**, **People** and **Place**.
   **Details** on each row shows a few more labels.

Everything saves by itself — a cell flashes green when it's saved, and a
red note appears if something can't be understood (nothing is saved then).
Set **Show** to *No date or season yet* to see only the clips left to do.
Labels can only be changed on the computer running the engine.

---

## Step 7 — Exhibit mode (for the gallery)

Click **Exhibit mode** at the top-right for a full-screen version designed
for a gallery: no settings, no file lists, just the film and one button.

Set the topic and length once on the setup screen, choose how films should
start, and press **Start exhibit**:

- **A visitor presses the button** — the screen waits showing one large
  button. Each press makes a new film and plays it. Best for shorter films.
- **Runs by itself, all day** — makes a new film each time one finishes.
  Nobody needs to touch it. Best for longer films.

Films play automatically. Touching the screen brings up **Pause**, the time
elapsed, **Start over** and **Make another**.

**To get back to the settings**, press **Esc**, or tap the **top-left
corner of the screen three times**. It takes three taps so a visitor can't
wander into the settings by accident.

---

## Stopping the engine

Close the plain-text window that opened when you started it. That's it.
Films you've already made stay on your computer.

---

## If something goes wrong

**"Python is not installed yet"**
Step 1 didn't complete. On Windows this is almost always the
**Add python.exe to PATH** box — run the Python installer again, choose
**Modify**, and tick it.

**"FFmpeg — NOT FOUND"**
Step 2 didn't complete, or you didn't open a fresh window afterwards. Close
the text window, open a new one by double-clicking Start Engine again.

**"has no footage yet"**
That topic's folders are empty. Go back to [Step 4](#step-4--add-the-film-clips)
and check the clips are inside `local-media/<topic>/assets/a-roll` (or
`b-roll`/`x-roll`) — not loose in the topic folder.

**The browser says the page can't be reached**
The engine isn't running. Double-click Start Engine, wait for the text
window to say it's running, then reload the page.

**A film failed partway through**
Click Generate again. If it keeps happening, one clip may be damaged — try
moving recently added clips out of the `assets` folder and generating again.

**Anything else**
Take a photo or screenshot of the text window and send it to David. The
message in that window says what went wrong.

---

## Quick reference

| I want to… | Do this |
|---|---|
| Start the engine | Double-click **Start Engine** |
| Stop the engine | Close the plain-text window |
| Add clips | Drop them in `local-media/<topic>/assets/<type>/` |
| Add a topic | New folder in `local-media` with `assets` + `artifacts` inside |
| Give a topic its own opening | Drop a video in `local-media/<topic>/titles/opening/` |
| Run it in the gallery | Click **Exhibit mode**, top-right |
| Label clips (dates, seasons…) | Click **Clip library**, top-right |
| Find finished films | `local-media/<topic>/artifacts/` |
| Make a copy for someone else | See *Making a package for someone else* |

---

## Making a package for someone else

To give the engine — with its clips and all the labels you've typed — to
someone else, or to move it to another computer, make a package. It takes
a minute or two.

**On a Mac:** open **Terminal** (press ⌘ + Space, type *Terminal*, press
Return). **On Windows:** open **Command Prompt** from the Start menu.

1. Type `cd ` (with a space after it), drag the project folder into the
   window, and press Return/Enter.
2. Type the line below and press Return/Enter (on Windows, type `py`
   instead of `python3` — or `python` if `py` isn't found):

   ```
   python3 scripts/make_package.py
   ```

3. When it says **Done**, the package is next to the project folder, named
   like `DDE-package-2026-10-19.zip`. Send or copy that one file.

It includes the engine, the guides, every topic's clips and labels, and
leaves out films made while testing. Add `--no-footage` to the end of the
line in step 2 for a small package without the clips.

