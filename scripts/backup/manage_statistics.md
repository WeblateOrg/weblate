# How to Manage Weblate Statistics

## 1. Recalculate Statistics for All Components

### Option A: Using the Script (Recommended)

```bash
cd /home/boost-weblate
source weblate-env/bin/activate
python3 scripts/recalculate_stats.py boost-unordered-documentation
```

This script:
- Recalculates statistics for all components in the project
- Updates translation statistics
- Updates component statistics
- Updates project statistics
- Shows progress and summary

### Option B: Manual Django Shell

```bash
cd /home/boost-weblate
source weblate-env/bin/activate
python3 manage.py shell
```

Then in the shell:
```python
from weblate.trans.models import Component, Project

# Get the project
project = Project.objects.get(slug='boost-unordered-documentation')

# Recalculate for all components
for comp in project.component_set.all():
    comp.invalidate_cache()
    for trans in comp.translation_set.all():
        trans.stats.update_stats(update_parents=False)
    comp.stats.update_stats(update_parents=True)
    print(f"✓ {comp.slug}")

# Update project statistics
project.stats.update_stats()
print("✓ Project statistics updated")
```

### Option C: For a Single Component

```bash
cd /home/boost-weblate
source weblate-env/bin/activate
python3 manage.py shell
```

```python
from weblate.trans.models import Component

comp = Component.objects.get(slug='nav', project__slug='boost-unordered-documentation')
comp.invalidate_cache()
for trans in comp.translation_set.all():
    trans.stats.update_stats(update_parents=False)
comp.stats.update_stats(update_parents=True)
print("✓ Statistics recalculated")
```

---

## 2. Clear the Django Cache

### Option A: Using Django Shell (Recommended)

```bash
cd /home/boost-weblate
source weblate-env/bin/activate
python3 manage.py shell
```

```python
from django.core.cache import cache
cache.clear()
print("✓ Cache cleared")
```

### Option B: Clear Redis Cache Directly

```bash
# Clear Redis database #1 (where Weblate cache is stored)
redis-cli -n 1 FLUSHDB

# Or clear all Redis databases
redis-cli FLUSHALL
```

### Option C: Clear Specific Cache Keys

```bash
cd /home/boost-weblate
source weblate-env/bin/activate
python3 manage.py shell
```

```python
from django.core.cache import cache

# Clear specific component cache
from weblate.trans.models import Component
comp = Component.objects.get(slug='nav', project__slug='boost-unordered-documentation')
comp.invalidate_cache()
print("✓ Component cache invalidated")
```

---

## Complete Workflow: Recalculate + Clear Cache

```bash
#!/bin/bash
# Complete statistics refresh workflow

cd /home/boost-weblate
source weblate-env/bin/activate

PROJECT="boost-unordered-documentation"

echo "=== Step 1: Recalculating Statistics ==="
python3 scripts/recalculate_stats.py "$PROJECT"

echo -e "\n=== Step 2: Clearing Cache ==="
python3 manage.py shell << 'PYEOF'
from django.core.cache import cache
cache.clear()
print("✓ Cache cleared")
PYEOF

echo -e "\n✓ Complete!"
```

Save this as `scripts/refresh_statistics.sh` and run:
```bash
chmod +x scripts/refresh_statistics.sh
./scripts/refresh_statistics.sh
```

---

## Quick Reference Commands

```bash
# 1. Recalculate statistics
cd /home/boost-weblate && source weblate-env/bin/activate && \
python3 scripts/recalculate_stats.py boost-unordered-documentation

# 2. Clear cache
cd /home/boost-weblate && source weblate-env/bin/activate && \
python3 manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
```

---

## Troubleshooting

### Statistics Still Wrong After Recalculation

1. **Clear cache again**:
   ```bash
   redis-cli -n 1 FLUSHDB
   ```

2. **Invalidate component cache**:
   ```python
   comp.invalidate_cache()
   ```

3. **Force recalculation**:
   ```python
   comp.stats.update_stats(update_parents=True)
   ```

### Cache Not Clearing

- Check Redis is running: `systemctl status redis`
- Check which Redis database Weblate uses: Check `CACHES` in `settings.py`
- Try clearing all databases: `redis-cli FLUSHALL`

### Statistics Show 0%

- Check if translations exist in the database
- Verify translation files are loaded
- Check if component is locked (locked components may not update)
- Trigger a component update: Component → Repository → Update

