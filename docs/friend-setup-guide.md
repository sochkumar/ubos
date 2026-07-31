# UBOS — Setup guide (Windows)

A short guide for installing and running UBOS on your two PCs.

## 1. Install

1. Download **`UBOS-Setup-x.y.z.exe`** (sent to you / from the Releases page).
2. Run it. Windows may warn that the publisher is unknown — click **More info → Run anyway** (the app is safe; it's just not code-signed yet).
3. Choose an install location and finish. A **UBOS** shortcut is added to the Start menu / desktop.

## 2. First launch

- Open **UBOS**. You'll see a "Starting your workspace…" screen for a few seconds while it boots.
- The first time, it shows an **Activation** screen with **this machine's ID**.

## 3. Activate (once per PC — up to 2 PCs)

1. On the Activation screen, copy **This machine's ID** (e.g. `UBOS-1A2B-3C4D-…`).
2. Send it to your provider.
3. Do the same on your **second** PC and send that ID too.
4. Your provider sends back a **`ubos.lic`** file.
5. On each PC: click **Load license file…** and pick the `ubos.lic`. UBOS opens.

> A single license works on the **2 PCs** whose IDs you sent — no internet needed.

## 4. Sign in

Use the account you were given. (Default demo login: `owner@ubos.test` / `OwnerPass!123`.)

## 5. Your data & backups

- Everything you enter is stored **on that PC** at:
  `%APPDATA%\UBOS\`  (paste that into the File Explorer address bar)
- **Back up regularly:** in UBOS go to **Settings → Organization → Workspace backup & sharing → Export workspace**. Save the `.ubos` file somewhere safe (USB drive, cloud folder).

## 6. Sharing data between your two PCs

The two PCs are independent — they do **not** sync automatically. To copy an
updated dataset from one to the other:

1. On the PC with the latest data: **Settings → Organization → Export workspace** → save the `.ubos` file.
2. Move that file to the other PC (USB / email / cloud).
3. On the other PC: **Settings → Organization → Import workspace…** → pick the file.
   - ⚠ Import **replaces** everything on that PC with the file's contents. Export that PC first if it has changes you want to keep.

## Troubleshooting

- **"Publisher unknown" warning:** expected (unsigned) — click Run anyway.
- **Stuck on the loading screen:** give it up to a minute on first launch; if it never opens, restart the app.
- **Lost your data:** restore your latest exported `.ubos` via Import.
- **New PC / reinstalled Windows:** the Machine ID changes — you'll need a new `ubos.lic` for that machine from your provider.
