# Semantic Image Finder

Find pictures on your Mac by **what they look like**, not what they are named.

Point it at a folder. It looks inside that folder and every folder within it,
studies each picture, and remembers what it saw. After that you can:

- **Drop in any image** and get back the most similar pictures you own.
- **Type a description** — "dog on a beach at sunset" — and get matching pictures.
- Choose how many results you want: **top 3, 5, 10, 20, 50 or 100**.
- Click **More like this** on any result to keep exploring.
- Click **Finder** to jump straight to the real file on your Mac.

Everything runs on your own computer. No account, no subscription, no uploading
your photos anywhere. It is free.

---

## Before you start

You need a **Mac**. That is genuinely it — the setup script installs the rest.

Set aside about **15 minutes** for the one-time setup, and roughly **1.5 GB** of
disk space. Most of that time is your Mac downloading things in the background,
so you can leave it running and go make a coffee.

---

## Part 1 — Install it (you only ever do this once)

### Step 1: Open Terminal

Terminal is an app that is already on your Mac.

1. Press **Command (⌘) + Space** together. A search box appears.
2. Type `Terminal`
3. Press **Return**.

A window with plain text appears. This is where you type the commands below.
Don't worry — you only need to copy and paste.

### Step 2: Go to the app's folder

Copy the line below, paste it into Terminal, and press **Return**:

```bash
cd ~/Documents/Coding/semantic_image_finder
```

> **If you moved the folder somewhere else:** type `cd ` (with a space after it),
> then drag the `semantic_image_finder` folder from Finder into the Terminal
> window. It fills in the path for you. Then press **Return**.

### Step 3: Run the installer

Copy, paste, press **Return**:

```bash
./setup.sh
```

Now wait. You will see progress messages with green ticks. The installer:

- installs **Homebrew** (the standard tool for installing Mac software),
- installs and starts **PostgreSQL** (the database that stores the results),
- installs **pgvector** (the part that makes "find similar" possible),
- installs **Python** and **Node.js** if you don't have them,
- downloads the **CLIP** model — the AI that actually looks at your pictures.

**Things that may happen along the way:**

| What you see | What to do |
|---|---|
| It asks for your password | Type your Mac login password and press Return. Nothing appears as you type — that is normal. |
| A box says *"command line developer tools"* | Click **Install** and wait for it to finish, then run `./setup.sh` again. |
| It sits still on "Installing Python packages" | That is the big download. Give it several minutes. |

When it is finished you will see **Setup complete.**

---

## Part 2 — Use it

### Starting the app

In Terminal, in that same folder, run:

```bash
./start.sh
```

Your browser opens automatically at **http://localhost:5173**.

**Leave the Terminal window open.** It is running the app. If you close it, the
app stops. To stop it deliberately, click the Terminal window and press
**Control + C**.

Every time you want the app in future: open Terminal, run the two lines below,
and it comes straight back.

```bash
cd ~/Documents/Coding/semantic_image_finder
./start.sh
```

### Adding your pictures

1. Click the **Folders** tab at the top.
2. Click **+ Add folder**.
3. A folder browser opens, starting in your home folder. Click folder names to
   go deeper, or `.. (up one level)` to go back. You can also paste a path
   straight into the box at the top.
4. When you are inside the folder you want, click **Index this folder**.

A progress bar appears showing how many pictures have been processed. Nested
folders are included automatically — you do not need to add them separately.

> **How long does it take?** Roughly 20–60 pictures per second on Apple Silicon.
> A folder of 5,000 photos takes a couple of minutes. You can keep using the
> other tabs while it works.

### Finding a picture

Click the **Search** tab.

**By image** — drag any picture onto the box, or click it to choose a file.
You get back the pictures in your folders that look most like it, each with a
match percentage.

**By words** — click *Search by words* and describe what you want:
`a red bicycle`, `snowy mountain`, `handwritten notes`, `screenshot of a chart`.

Use the **Show top** dropdown to pick how many results you want (3, 5, 10, 20,
50 or 100), and **Look in** to search a single folder instead of all of them.

Click a result to see it full size. Click **Finder** to reveal the actual file.

### The Database tab

Shows exactly what is stored — how many images, how much disk the database uses,
how many pictures came from each folder — and gives you one-click buttons:

| Button | What it does |
|---|---|
| **Scan all folders for new images** | Picks up pictures you added since last time. Skips everything unchanged, so it is fast. |
| **Remove entries for deleted files** | Tidies up after pictures you deleted or moved. |
| **Optimise the database** | Reclaims space and keeps searching fast. |
| **Rebuild every vector from scratch** | Re-processes everything. Slow; rarely needed. |
| **Delete all indexed data** | Empties the index and starts over. |

> **Your photos are never touched.** This app only ever *reads* your image files.
> Every button here affects the database, never the pictures themselves.

---

## If something goes wrong

**The page says "Waiting for the backend"**
Look at the Terminal window running `./start.sh` for a red error message. The
usual fix is to press Control + C and run `./start.sh` again.

**It says PostgreSQL is not running**
Paste this into Terminal:
```bash
brew services start postgresql@18
```

**"Permission denied" when running ./setup.sh**
Paste this once, then try again:
```bash
chmod +x setup.sh start.sh
```

**A folder won't open in the folder browser**
macOS protects some folders (Desktop, Documents, Photos). Go to
**System Settings → Privacy & Security → Full Disk Access**, turn it on for
**Terminal**, then quit and reopen Terminal.

**Some pictures were skipped**
The count of "failed" files in the progress bar covers broken or unreadable
files. They are skipped safely and everything else still indexes.

**I want to start completely fresh**
Database tab → **Delete all indexed data**. Your photos are unaffected.

**The port is already in use**
`start.sh` clears ports 8000 and 5173 for you. To use different ones:
```bash
API_PORT=8010 FRONTEND_PORT=5200 ./start.sh
```

---

## What is actually happening (optional reading)

Every picture is passed through **CLIP**, a small open model from OpenAI that
turns an image into a list of 512 numbers describing its content. Pictures that
look alike end up with similar numbers.

Those numbers live in **PostgreSQL** alongside the file path and the date it was
added. The **pgvector** extension lets the database sort by similarity directly,
using an HNSW index so results stay fast as your collection grows.

CLIP was trained on images *and* their captions, which is why typing a
description works: your words get turned into numbers in the very same space as
the pictures.

**Supported file types:** JPG, PNG, GIF, BMP, WEBP, TIFF, HEIC/HEIF, AVIF.

**Layout of this project:**

```
semantic_image_finder/
├── setup.sh            Run once to install everything
├── start.sh            Run to use the app
├── backend/            Python: the AI model, database and API
│   ├── app/
│   │   ├── main.py     The API the web page talks to
│   │   ├── embedder.py Turns pictures and words into numbers
│   │   ├── indexer.py  Walks your folders, in the background
│   │   ├── db.py       Creates the database and tables on first run
│   │   └── config.py   Settings
│   └── .env            Change ports or database settings here
└── frontend/           React: the web page you actually use
```

**Settings** live in `backend/.env`. The defaults work for a normal Homebrew
install; you only need to touch it if your PostgreSQL uses a password or a
different port.

**Privacy:** the app listens only on `127.0.0.1`, meaning your own Mac. Nothing
is reachable from the internet and no image ever leaves your computer.
