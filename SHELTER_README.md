# Shelter House Price Guide

A professional Nigerian home asking-price estimator and property listings page. The Kaggle dataset covers 24 states plus Abuja. The property search and admin inventory are limited to those dataset locations, while price estimates require at least 50 usable listings for the selected state.

## Run the app

1. Open a terminal in this folder.
2. Set a private admin password for this terminal session. In PowerShell, run `$env:SHELTER_ADMIN_PASSWORD = 'choose-a-private-password-of-at-least-12-characters'`.
3. Run `python app.py`.
4. Open http://127.0.0.1:8000.
5. Open http://127.0.0.1:8000/admin to sign in and add the first available home.
6. Stop the server with Ctrl+C in the terminal.

The app uses Python's built-in libraries, so no package installation is needed. The admin password is read from the environment and is not stored in the project files. It must be at least 12 characters.

## Files

- `shelter.html`: the Shelter page and property form.
- `app.py`: local Python server, data loading, validation, and estimate logic.
- `static/styles.css`: responsive visual design.
- `static/app.js`: browser behavior and API calls.
- `data/nigeria_houses_data.csv`: property listing examples.
- `train_model.py`: held-out evaluation script.
- `model_report.json`: held-out evaluation summary; run `python train_model.py` to refresh it after changing data coverage.
- `shelter_inventory.sqlite3`: created automatically for admin-managed homes and tour requests; keep this private and back it up.
- `admin.html`, `static/admin.css`, `static/admin.js`: private property-management interface.

The tool estimates advertised asking prices, not verified completed-sale prices or formal valuations. See `data/DATA_SOURCE.txt` for attribution and license details.

## Available homes and tours

The public listing section shows homes added and marked available by an administrator. Sale and rental listings, including rooms, self-contained units, flats, studios, and shops, are limited to the 24 dataset-covered states plus Abuja. Rental prices can be monthly or yearly. Price estimates require at least 50 usable listings per location. Tour requests are not confirmed until an administrator contacts the visitor.

Admin sessions expire after eight hours or when the server restarts. For a public deployment, run Shelter behind HTTPS and set `SHELTER_COOKIE_SECURE=1`. Do not expose the built-in development server directly to the internet.
