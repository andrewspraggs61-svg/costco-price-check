# Deploying (free, HTTPS, Tesseract included)

Target: **Render** free web service. No credit card required. Gives an HTTPS URL
you open on your phone and "Add to Home Screen", and share with family/friends.

The code is already committed to a local git repo with a `Dockerfile` (which
installs Tesseract) and a `render.yaml` blueprint. You just need to (1) put the
repo on GitHub and (2) connect it to Render.

## 1. Put the repo on GitHub
If you have the GitHub CLI (`gh`) installed and logged in, from the project folder:

```powershell
gh repo create costco-price-check --private --source . --push
```

Or manually: create a new **empty** repo at https://github.com/new called
`costco-price-check`, then:

```powershell
git remote add origin https://github.com/<your-username>/costco-price-check.git
git branch -M main
git push -u origin main
```

## 2. Connect it to Render
1. Sign up / log in at https://render.com (you can sign in *with GitHub* — easiest).
2. Click **New → Blueprint**.
3. Pick your `costco-price-check` repo. Render reads `render.yaml` automatically.
4. Click **Apply**. First build takes a few minutes (it's building the Docker
   image and installing Tesseract).
5. When it's live you'll get a URL like `https://costco-price-check.onrender.com`.

## 3. Use it on your phone
- Open that URL in Safari (iPhone) or Chrome (Android).
- Allow **location** when asked (so it picks your nearest stores).
- Tap the browser menu → **Add to Home Screen**. Now it's an app icon.
- Send the same URL to family/friends — that's the whole "install".

## Notes
- **Free tier sleeps when idle**, so the *first* scan after a quiet period takes
  ~30-60s to wake up; after that it's fast. Fine for personal use.
- Every `git push` to `main` auto-redeploys.
- HTTPS is automatic (required for the camera and Add-to-Home-Screen to work).
