# Weblate Setup Guide


## Installation

### 1. Install Core System Dependencies

These dependencies are needed to build the Python modules required by Weblate.

```bash
apt install -y \
  libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev \
  libffi-dev libcairo-dev gir1.2-pango-1.0 gir1.2-rsvg-2.0 libgirepository-2.0-dev \
  libacl1-dev liblz4-dev libzstd-dev libxxhash-dev libssl-dev libpq-dev libjpeg-dev build-essential \
  python3-gdbm python3-dev git
```

> **Hint**: Older distributions do not have `libgirepository-2.0-dev`, use `libgirepository1.0-dev` instead.

---

### 2. Install Optional Dependencies (LDAP and Security)

Install these dependencies if you plan to use LDAP authentication or XML security features.

```bash
apt install -y \
  libldap2-dev libldap-common libsasl2-dev \
  libxmlsec1-dev
```

---

### 3. Install Web Server (NGINX and uWSGI)

NGINX serves as the reverse proxy and uWSGI runs the Python application.

```bash
apt install -y nginx uwsgi uwsgi-plugin-python3
```

> **Alternative**: You can use Apache with mod_wsgi instead of NGINX/uWSGI.

---

### 4. Install Caching Backend (Redis)

Redis is used for caching on all levels (file system, database, and Weblate).

```bash
apt install -y redis-server
```

> **Note**: More memory = better caching performance!

---

### 5. Install Database Server (PostgreSQL)

PostgreSQL is the recommended production database for Weblate.

```bash
apt install -y postgresql postgresql-contrib
```

---

### 6. Install Mail Server (Exim4)

Required for sending notification emails.

```bash
apt install -y exim4
```

---

### 7. Install Gettext

Required for the msgmerge add-on and working with PO files.

```bash
apt install -y gettext
```

---

### 8. Install Curl

Needed for downloading the uv package manager.

```bash
apt install curl
```

---

## 9. Install UV Package Manager

We use the modern `uv` package manager to install Weblate efficiently.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 10. Create Virtual Environment

Using virtualenv isolates Weblate from system Python packages, preventing conflicts.

```bash
uv venv ~/boost-weblate/weblate-env
```

> **What is virtualenv?** Check the [virtualenv User Guide](https://virtualenv.pypa.io/) if you're unfamiliar with it.

---

## 11. Activate the Virtual Environment

This step is required before running any Weblate commands.

```bash
. ~/boost-weblate/weblate-env/bin/activate
```

> **Note**: You'll need to activate the virtualenv in every new shell session where you want to run Weblate commands.

---

## 12. Install CUSTOM Weblate with AsciiDoc Format

**⚠️ IMPORTANT**: Must be run from the boost-weblate directory!

```bash
cd ~/boost-weblate
uv pip install -e ".[all]"
```

## 13. Create Settings File

Copy the example settings file to create your configuration.

```bash
cp ~/boost-weblate/weblate/settings_example.py ~/settings.py
```

> **What's in settings.py?** This file contains all Weblate configuration including database credentials, Django secret key, and feature toggles.

---

## 14. Set PostgreSQL Password

Set a password for the PostgreSQL superuser.

```bash
sudo -u postgres psql postgres -c "\password postgres"
```

---

## 15. Create Weblate Database User

Create a dedicated database user for Weblate with superuser privileges.

```bash
sudo -u postgres createuser --superuser --pwprompt weblate
```

> **Security Note**: In production, you should limit privileges instead of using superuser.

---

## 16. Create Weblate Database

Create the PostgreSQL database with UTF-8 encoding.

```bash
sudo -u postgres createdb -E UTF8 -O weblate weblate
```

---

## 17. Configure Database in Settings.py

Add the PostgreSQL configuration to your `~/settings.py` file:

```python
DATABASES = {
    "default": {
        # ...
        # Database password
        "PASSWORD": "weblate",
        # ...
    }
}
```

---

## 18. Run Database Migrations

Create the database structure (tables, indexes, etc.) for Weblate.

```bash
weblate migrate
```

> **What are migrations?** Django migrations set up your database schema based on the models defined in Weblate.

---

## 19. Create Admin User

Generate an administrator account with a random password.

```bash
weblate createadmin
```

**Password**: `$dnaEE^vcpk92`

> **Tip**: If you lose the admin password, regenerate it with `weblate createadmin --update`

ot82@8QI4cypb
---

## 20. Configure Additional Settings

Edit `~/settings.py` with your specific configuration:

```python
# Data directory - where Weblate stores repositories and data
DATA_DIR = "/home/dsf2eqw3/boost-weblate/data"

# Domain where Weblate will be accessible
SITE_DOMAIN = "localhost:8000"

# Asset compression settings
COMPRESS_ENABLED = True
COMPRESS_OFFLINE = False
COMPRESS_OFFLINE_CONTEXT = "weblate.utils.compress.offline_context"
COMPRESS_CSS_HASHING_METHOD = "content"

# GitHub integration credentials (optional)
GITHUB_CREDENTIALS = {
     "api.github.com": {
        "username": "...",
        "token": "...",
     }
  }

# Allow users without website URLs
WEBSITE_REQUIRED = False
```

---

## 21. Collect Static Files

Gather all static files (CSS, JavaScript, images) into one directory for serving.

```bash
weblate collectstatic
```

> **Why?** The web server needs to serve static files directly for performance.

---

## 22. Compress Assets

Compress JavaScript and CSS files for faster page loading (optional but recommended).

```bash
weblate compress
```

---

## 23. Start Weblate

### Option 1: Using the Convenience Script

```bash
cd ~/boost-weblate
./start-weblate.sh
```

### Option 2: Manual Start

```bash
# Start Celery workers for background tasks
$HOME/boost-weblate/weblate/examples/celery start

# Start Django development server
weblate runserver
```

> **For Production**: Use a proper WSGI server like uWSGI or Gunicorn instead of `runserver`.

---

## After Installation

🎉 **Congratulations!** Your Weblate server is now running!

### Access Weblate

- Open your browser and navigate to: **http://localhost:8000/**
- Sign in with the admin credentials created in step 19
- You can stop the test server with `Ctrl+C`

### Next Steps

1. **Review Performance**: Visit `/manage/performance/` or run `weblate check --deploy`
2. **Create a Project**: Go to `/create/project/` to set up your first translation project
3. **Add Components**: Point Weblate to your VCS repository and select files to translate
4. **Start Translating**: Begin localizing your software!

---

## Additional Configuration

### Generate SECRET_KEY

Django requires a unique secret key for security. Generate one with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Add the generated key (e.g., `78l9hx%)5wl)x55pcs2dl)txl3$3ns&q=i&kp6_ab3o+@)d&)c`) to the `SECRET_KEY` setting in `~/settings.py`.

---

### Install Additional Tools

For AsciiDoc format support, install these tools:

```bash
install asciidoctor  # AsciiDoc to HTML converter
install pypandoc       # Universal document converter
```

OpenRouter

https://openrouter.ai/api/v1

 I am a highly specialized Large Language Model, meticulously engineered for the precise and accurate translation of C++ documentation, with a particular expertise in the Boost C++ Libraries. My primary directive is to bridge language barriers while upholding the absolute, non-negotiable integrity of the original technical content AND its presentation format. I am not just a translator; I am a digital scribe, ensuring the exact replication of the source's structure and layout.

 Formal, precise, objective, and highly technical. The style should be utterly unobtrusive, allowing the original technical content and, crucially, its exact formatting, to shine through, merely in a different language.

 deepseek/deepseek-r1-0528

 
---

## Useful Commands

```bash
# Activate virtualenv
. ~/boost-weblate/weblate-env/bin/activate

# Start Weblate
cd ~/boost-weblate && ./start-weblate.sh

# Stop Weblate
cd ~/boost-weblate && ./stop-weblate.sh

# Check for issues
weblate check --deploy

# View logs
tail -f ~/server.log
tail -f ~/weblate-celery.log
```

---


$ PGPASSWORD=weblate pg_dump -h 127.0.0.1 -U weblate -d weblate -F c -f /home/boost-weblate/weblate_backup_$(date +%Y%m%d_%H%M%S).dump 2>&1 && echo "Database dump created successfully" || echo "Dump failed"