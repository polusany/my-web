# Shelter

A Nigerian asking-price estimator and admin-managed property discovery prototype. This dataset covers 24 states plus Abuja. Estimates are enabled only in locations with at least 50 usable examples. Sale and rental properties can be added in those covered locations; live listings are kept separate from historical estimate data.

## Run locally

1. Open PowerShell in this folder.
2. Set a private password for the admin area: `$env:SHELTER_ADMIN_PASSWORD = 'your-private-password-at-least-12-characters'`.
3. Start the app with `python app.py`.
4. Visit http://127.0.0.1:8000 for the public site.
5. Visit http://127.0.0.1:8000/admin to add homes and manage tour requests.

Shelter uses Python's built-in libraries. No package installation is needed. Set the environment variable each time you start a new terminal session. The admin password is not stored in this project.

## Available homes and viewings

Administrators can publish sale or rental listings, including rooms, self-contained units, flats, studios, and shops in the 24 covered states and Abuja. Rent can be priced monthly or yearly. Visitors can filter listings by sale or rent and location, then request an in-person or virtual viewing. Tour requests require admin confirmation and are saved in the local shelter_inventory.sqlite3 database.

For a public HTTPS deployment, set `SHELTER_COOKIE_SECURE=1` and use a production-ready server behind HTTPS. The built-in development server is intended for learning and local use.

## Main files

- `shelter.html`: public page, price estimator, available homes, and tour-request dialog.
- `app.py`: Python server, price estimator API, listing/tour APIs, admin login, and SQLite setup.
- `static/app.js`, `static/styles.css`: public page behavior and design.
- `admin.html`, `static/admin.js`, `static/admin.css`: administrator sign-in and property desk.
- `data/nigeria_houses_data.csv`: historical listing data for estimates, not current inventory.
- `train_model.py`, `model_report.json`: held-out evaluation script and report; run `python train_model.py` to refresh the report after changing data coverage.
- `SHELTER_README.md`: expanded project notes.
