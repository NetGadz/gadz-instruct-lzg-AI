# Render deployment

This project is prepared for Render free hosting.

## Files to keep

- app.py
- requirements.txt
- render.yaml

## Deploy steps

1. Push the project to GitHub.
2. Open Render.
3. New -> Web Service.
4. Connect the GitHub repo.
5. Use the settings from `render.yaml`.
6. Deploy.

## Important note

This app loads ML models from the Hugging Face Hub on first run. Render free plan may be limited by memory and startup time, so the app is best treated as a demo service rather than a permanent production deployment.

## Local validation

```bash
python -m pip install -r requirements.txt
python app.py
```
