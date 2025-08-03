# warehouse/management/commands/reconcile_roll_counts.py
from django.core.management.base import BaseCommand
from django.core.mail import mail_admins
from django.db.models import Max
from warehouse.models import Location, Roll, Transaction

class Command(BaseCommand):
    help = 'Reconcile per-location roll counts between API logic and dashboard logic.'

    def handle(self, *args, **options):
        mismatches = []

        # 1) Build dashboard counts: for each location, count rolls whose latest tx points here
        #    (i.e. latest transaction per roll with action PUTAWAY/TRANSFER/TEMP_STORAGE whose location matches)
        latest = (
            Transaction.objects
            .values('roll')
            .annotate(last_ts=Max('scanned_at'))
        )
        latest_txs = Transaction.objects.filter(
            scanned_at__in=[l['last_ts'] for l in latest]
        )

        dashboard_map = { loc.location_code: 0 for loc in Location.objects.all() }
        # dispatched we ignore for this comparison (or you can add 'DISPATCHED' if you like)
        for tx in latest_txs:
            if tx.location:
                dashboard_map[tx.location.location_code] += 1

        # 2) Build API counts: count rolls whose current_location == each rack
        api_map = {}
        for loc in Location.objects.all():
            api_map[loc.location_code] = Roll.objects.filter(current_location=loc.location_code).count()

        # 3) Compare
        for code in dashboard_map:
            dcount = dashboard_map[code]
            acount = api_map.get(code, 0)
            if dcount != acount:
                mismatches.append((code, dcount, acount))

        # 4) Report
        if mismatches:
            subject = '‼️ Warehouse Roll‐Count Mismatch'
            body = 'Found count discrepancies:\n\n' + '\n'.join(
                f"{loc}: Dashboard={dcount} vs API={acount}"
                for loc, dcount, acount in mismatches
            )
            # email all in ADMINS
            mail_admins(subject, body)
            self.stdout.write(self.style.ERROR(body))
        else:
            self.stdout.write(self.style.SUCCESS('✅ All location counts match'))
