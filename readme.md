# ootp-learning

This repo is a learning + prototype space for an OOTP optimizer toolchain.

## Quick start (new machine)

From the repo root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

## Verify repo is up to date with GitHub

Run from the repo root:

git fetch origin
git status


Expected when synced:

Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

## If you're ahead (local commits not on GitHub)

git push

## If you're behind (GitHub has commits you don't)

git pull --ff-only

## Verify local main exactly matches GitHub main

git fetch origin
git rev-parse HEAD
git rev-parse origin/main


If the two hashes match, local == GitHub.

## Verify two PCs match each other

On each PC:

git fetch origin
git rev-parse HEAD


If both PCs show the same hash (and git status is clean), they are identical.

## Notes

.venv/ is local to each machine and is intentionally not committed.

If PowerShell blocks venv activation, set execution policy (CurrentUser):

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser


Then commit + push it:

```powershell
git add README.md
git commit -m "docs: add setup and sync instructions"
git push