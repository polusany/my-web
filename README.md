# Moshelter

A Nigerian home discovery and asking-price guide with a private property administration workspace. This dataset covers 24 states plus Abuja. Estimates are enabled only in locations with at least 50 usable examples. Sale and rental properties can be added in those covered locations; live listings are kept separate from historical estimate data.

## Run locally

1. Open PowerShell in this folder.
2. Set a private password for the admin area: `$env:MOSHELTER_ADMIN_PASSWORD = 'your-private-password-at-least-12-characters'`.
3. Start the app with `python app.py`.
4. Visit http://127.0.0.1:8000 for the public site.
5. Visit http://127.0.0.1:8000/admin to add homes and manage tour requests.

Moshelter uses Python's built-in libraries. No package installation is needed. Set the environment variable each time you start a new terminal session. The admin password is not stored in this project.

## Available homes and viewings

Administrators can publish sale or rental listings, including rooms, self-contained units, flats, studios, and shops in the 24 covered states and Abuja. Rent can be priced monthly or yearly. Visitors can filter listings by sale or rent and location, then request an in-person or virtual viewing. Tour requests require admin confirmation and are saved in the local shelter_inventory.sqlite3 database.

## Deploy to Render

The included `render.yaml` configures a small Python web service in Frankfurt with HTTPS, the required environment variables, a health check, and a 1 GB persistent disk for the SQLite inventory. Connect this repository to Render and create a Blueprint from `render.yaml`. Render prompts for `MOSHELTER_ADMIN_PASSWORD`; enter a private password of at least 12 characters in the dashboard and never commit it to Git.

This service needs a paid Render instance because the free web tier cannot use persistent disks. The current Blueprint uses Render's `0.5c-512mb` plan and a 1 GB disk. Listing and tour data are written under `/var/data` and survive deploys and restarts. The `shelter_inventory.sqlite3` file in the project root is excluded from Git; this deployment starts with an empty inventory.

Render terminates public HTTPS and forwards requests to the Python server over its private service connection. The service is configured for a single instance and small traffic volumes. If you attach a custom domain, set its DNS records in Render and verify HTTPS before sharing the site.

## Main files

- `shelter.html`: public page, price estimator, available homes, and tour-request dialog.
- `app.py`: Python server, price estimator API, listing/tour APIs, admin login, and SQLite setup.
- `static/app.js`, `static/styles.css`: public page behavior and design.
- `admin.html`, `static/admin.js`, `static/admin.css`: administrator sign-in and property desk.
- `data/nigeria_houses_data.csv`: historical listing data for estimates, not current inventory.
- `train_model.py`, `model_report.json`: held-out evaluation script and report; run `python train_model.py` to refresh the report after changing data coverage.
- `SHELTER_README.md`: expanded project notes.
