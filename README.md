# Zefoy Views Automation

Automates the "Views" flow on https://zefoy.com using Selenium and blocks intrusive ad requests.

## 1.  Create & activate a Python virtual environment
Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```
Windows (cmd):
```bat
python -m venv venv
venv\Scripts\activate
```

## 2.  Install dependencies
```bash
pip install -r requirements.txt
```

## 3.  Ensure ChromeDriver matches your Chrome version
Download from <https://chromedriver.chromium.org/downloads> and **put it on your `PATH`** (or in the project root).  macOS users can `brew install --cask chromedriver`.

## 4.  Run the automation script
```bash
python zefoy_views.py
```
A Chrome window will open:
1. Wait for Cloudflare verification.
2. Manually solve Zefoy's captcha when prompted.
3. The script fills the TikTok URL, handles the countdown, and submits automatically.

## 5.  Logs
All runs write verbose output to `logs/run-YYYY-MM-DD.log` (created automatically). Review these files for troubleshooting or proof of execution. 