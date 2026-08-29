## Setup

### Prerequisites
1. Web App at https://old.reddit.com/prefs/apps/; I believe Reddit stopped allowing you to make these, though!
2. Python is installed
3. Your joiner-account has the "manage contributors" (required) and "update" (optional) permissions for your threads

#### Windows
```
python -m venv .venv
.\venv\Scripts\Activate.ps1
pip install -e .
cp .env.example .env
```

#### Mac/Linux
```
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set your [web app](https://old.reddit.com/prefs/apps/)'s redirect URI to the `OAUTH_REDIRECT_URI` value in `.env`. Then, logged in as the bot account:

```
python -m joinlivecounting.scripts.bootstrap_token
```

Paste the printed token into `REDDIT_BOT_REFRESH_TOKEN` in `.env`.

## Running

```
python -m joinlivecounting                                    # dev
gunicorn -w 2 -b 0.0.0.0:8080 joinlivecounting.web.app:app    # prod (Linux)
waitress-serve --port=8080 joinlivecounting.web.app:app       # prod (Windows)
```

## Tests

```
pip install -e ".[dev]"
pytest
pyflakes src tests
```
