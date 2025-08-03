# warehouse/apps.py

from django.apps import AppConfig
from django.core.mail import mail_admins
from django.db.models import Max

# 1) Module‐level: define the job function, but defer all model imports till call time
def reconcile_roll_counts():
    """
    Compare dashboard vs API roll counts and email ADMINS if they diverge.
    """
    # Now that this is running _after_ Django startup, we can import models safely
    from .models import Transaction, Location, Roll

    # 1) Build dashboard counts (latest tx per roll → location)
    latest = (
        Transaction.objects
        .values('roll')
        .annotate(last_ts=Max('scanned_at'))
    )
    latest_txs = Transaction.objects.filter(
        scanned_at__in=[l['last_ts'] for l in latest]
    )

    dash_map = { loc.location_code: 0 for loc in Location.objects.all() }
    for tx in latest_txs:
        if tx.location:
            dash_map[tx.location.location_code] += 1

    # 2) Build API counts (Roll.current_location)
    api_map = {
        loc.location_code: Roll.objects.filter(current_location=loc.location_code).count()
        for loc in Location.objects.all()
    }

    # 3) Find mismatches
    mismatches = [
        f"{code}: dashboard={dash_map[code]} vs api={api_map.get(code,0)}"
        for code in dash_map
        if dash_map[code] != api_map.get(code,0)
    ]

    # 4) If any, email ADMINS
    if mismatches:
        subject = "‼️ ITS Roll‐Count Mismatch"
        body    = "Discrepancies:\n" + "\n".join(mismatches)
        mail_admins(subject, body)


class WarehouseConfig(AppConfig):
    name = 'warehouse'

    def ready(self):
        # Defer all heavyweight imports until after apps are loaded
        import os
        # Under `runserver`, Django spawns two processes:
        #  - one to watch files and restart
        #  - one to actually serve requests.
        # We only want to start our scheduler in the *serving* process.
        if os.environ.get('RUN_MAIN') != 'true':
            return

        # Defer all heavyweight imports until after apps are loaded
        import threading
        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore
        # Only start the scheduler once per process
        if getattr(self, 'scheduler_started', False):
            return

        sched = BackgroundScheduler()
        sched.add_jobstore(DjangoJobStore(), 'default')

        # Schedule by string reference to our top‑level function
        sched.add_job(
            'warehouse.apps:reconcile_roll_counts',  # <module path>:<function name>
            trigger='cron',
            hour=9,
            minute=0,
            id='reconcile_roll_counts_job',
            replace_existing=True,
        )

        # Run in background so migrations/tests aren’t blocked
        threading.Thread(target=sched.start, daemon=True).start()
        self.scheduler_started = True
