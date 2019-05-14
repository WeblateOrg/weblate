import os

string_command = "celery -A weblate multi start \
  search notify celery memory \
  --pidfile=/opt/app-root/data/celery/weblate-%n.pid \
  --logfile=/opt/app-root/data/celery/weblate-%n%I.log --loglevel=DEBUG \
  --concurrency:celery=4 --queues:celery=celery --prefetch-multiplier:celery=4 \
  --concurrency:notify=4 --queues:notify=notify --prefetch-multiplier:notify=4 \
  --concurrency:search=1 --queues:search=search --prefetch-multiplier:search=2000 \
  --concurrency:memory=1 --queues:memory=memory --prefetch-multiplier:memory=2000"

beat_command = "celery beat -s /opt/app-root/data/celery/celerybeat-schedule \
  --loglevel=DEBUG \
  --app=weblate --pidfile /opt/app-root/data/celery/beat.pid"

print(string_command)
os.system(string_command)

print(beat_command)
os.system(beat_command)
