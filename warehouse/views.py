from django.views.generic import FormView, TemplateView, ListView
from django.shortcuts import redirect, get_object_or_404
from .forms import BatchDataForm
from rest_framework import viewsets
from .models import Material, ImportLog, ReconciliationLog, Batch, Customer, Roll, Location, Transaction, Department
from .serializers import (
    MaterialSerializer, BatchSerializer, CustomerSerializer,
    RollSerializer, LocationSerializer, TransactionSerializer
)
from django.conf import settings
import qrcode, os
from django.db.models import Q, Max
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator

from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from .forms import SignUpForm
from django.views import View
from django.contrib import messages
from .mixins import DeptPermissionMixin

from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
import pandas as pd

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer

class BatchViewSet(viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    lookup_field = 'location_code'
    lookup_url_kwarg = 'location_code'

    @action(detail=True, methods=['get'], url_path='rolls')
    def rolls(self, request, *args, **kwargs):
        loc = self.get_object()
        # all rolls currently at this rack
        qs = Roll.objects.filter(current_location=loc)
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = RollSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(ser.data)

        ser = RollSerializer(qs, many=True, context={'request': request})
        return Response(ser.data)

class TransactionViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes     = [IsAuthenticated]
    queryset               = Transaction.objects.all().order_by('-scanned_at')
    serializer_class       = TransactionSerializer

    def create(self, request, *args, **kwargs):
        roll_id  = request.data.get('roll')
        action   = request.data.get('action')
        loc_code = request.data.get('location')  # may be None

        # 1) Validate roll exists
        roll = get_object_or_404(Roll, roll_id=roll_id)

        # 2) Check last tx
        last = (
            Transaction.objects
            .filter(roll=roll)
            .order_by('-scanned_at')
            .first()
        )

        if last and last.action == action:
            # allow idempotent PUTAWAY → same rack
            if action == 'PUTAWAY' and last.location and last.location.location_code == loc_code:
                # return the existing tx data as a 200 OK
                ser = self.get_serializer(last)
                return Response(ser.data, status=200)

            # for everything else, block duplicates
            if action != 'TRANSFER' or (last.location and last.location.location_code == loc_code):
                return Response(
                    {"detail": f"Roll already has action {action} at this location."},
                    status=400
                )

        # 3) Otherwise fall back to normal create
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # actually save the new Transaction
        tx = serializer.save()

        # update the Roll.current_location
        roll = tx.roll
        if tx.action in ('PUTAWAY', 'TRANSFER', 'TEMP_STORAGE'):
            roll.current_location = tx.location.location_code
        elif tx.action == 'DISPATCH':
            roll.current_location = None
        # for QA_SCAN or others, leave as‑is
        roll.save(update_fields=['current_location'])

class RollViewSet(viewsets.ModelViewSet):
    queryset = Roll.objects.all()
    serializer_class = RollSerializer
    # Lookup by roll_id instead of default pk
    lookup_field = 'roll_id'
    lookup_value_regex = '[0-9a-f\\-]+'  # to match a UUID

    def perform_create(self, serializer):
        # 1) Save the roll record to get its roll_id
        roll = serializer.save()

        # 2) Build the short‑link payload
        url = f"{settings.SITE_URL}/r/{roll.roll_id}"

        # 3) Generate the QR image
        img = qrcode.make(url)

        # 4) Save it under MEDIA_ROOT/qrcodes/{roll_id}.png
        qr_dir = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
        os.makedirs(qr_dir, exist_ok=True)
        path = os.path.join(qr_dir, f"{roll.roll_id}.png")
        img.save(path)




'''
class MaterialEntryView(FormView):
    template_name = 'warehouse/material_entry.html'
    form_class    = MaterialEntryForm
    allowed_roles   = [
        'Factory Admin',
        'Plant Manager',
        'Stock Keeper',
    ]

    def form_valid(self, form):
        data = form.cleaned_data

        # 1) Material: get or create, then update its film props
        material, created = Material.objects.get_or_create(
            material_number=data['material_number'],
            defaults={
              'description': data['description'],
              'colour':      data['colour'],
              'thickness_value': data['thickness_value'],
              'thickness_unit':  data['thickness_unit'],
            }
        )
        if not created:
            # update properties
            material.description     = data['description']
            material.colour          = data['colour']
            material.thickness_value = data['thickness_value']
            material.thickness_unit  = data['thickness_unit']
            material.save()
        # 2) Batch: now unique_together enforces per‐material uniqueness
        batch, _ = Batch.objects.get_or_create(
            material    = material,
            batch_number= data['batch_number']
        )
        # Thickness
        gauge  = data['thickness_value'] if data['thickness_unit']=='GAUGE' else 0
        micron = data['thickness_value'] if data['thickness_unit']=='MICRON' else 0

        # Roll
        # get or create the Customer
        customer_name = data['customer'].strip()
        customer, _ = Customer.objects.get_or_create(name=customer_name)

        roll = Roll.objects.create(
            batch      = batch,
            weight_kg  = data['weight_kg'],
            customer   = customer
        )
        # 4) generate & save QR to MEDIA_ROOT/qrcodes/<roll_id>.png
        qr_url = f"{settings.SITE_URL}/r/{roll.roll_id}"
        qr_img = qrcode.make(qr_url)
        qr_folder = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
        os.makedirs(qr_folder, exist_ok=True)
        qr_img.save(os.path.join(qr_folder, f"{roll.roll_id}.png"))

        # 5) redirect to your print‐label page for this roll:
        return redirect('material-print', roll_id=roll.roll_id)
'''


class BatchEntryView(DeptPermissionMixin, FormView):
    template_name = 'warehouse/material_entry.html'
    form_class    = BatchDataForm
    allowed_roles = ['Factory Admin','Plant Manager','Stock Keeper']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


    def form_valid(self, form):
        cd   = form.cleaned_data
        rows = []

        # 1) file‐upload branch
        if cd['data_file']:
            f   = cd['data_file']
            ext = f.name.rsplit('.',1)[-1].lower()
            df  = pd.read_excel(f) if ext in ['xls','xlsx'] else pd.read_csv(f)
            df  = df.rename(columns={
                'Material':           'material_number',
                'Material Description':'description',
                'Batch':              'batch_number',
                'Quantity in Kg':     'weight_kg',
                'Posting Date':       'posting_date',
                'Storage Location':   'location_code',
            })
            df  = df.dropna(subset=['batch_number'])
            for _,r in df.iterrows():
                dept = r.get('location_code','').strip().upper()[:2]
                rows.append({
                  'material_number': str(r['material_number']),
                  'description':     r['description'],
                  'batch_number':    str(r['batch_number']),
                  'weight_kg':       float(r['weight_kg']),
                  'posting_date':    (r['posting_date'].date()
                                      if hasattr(r['posting_date'],'date')
                                      else r['posting_date']),
                  'location_code':   r.get('location_code','').strip().upper(),
                  'department':      dept,
                })
        else:
            # 2) manual branch
            rows.append({
              'material_number': cd['material_number'],
              'description':     cd['description'],
              'batch_number':    cd['batch_number'],
              'weight_kg':       cd['weight_kg'],
              'posting_date':    cd['posting_date'],
              'department':      cd['department'],
            })

        # 2b) Permission check: same as before
        user = self.request.user
        if not user.groups.filter(name__in=['Factory Admin','Forklift Driver']).exists():
            user_dept = user.profile.department.code
            for data in rows:
                if data.get('department') != user_dept:
                    form.add_error(
                        None,
                        f"You ({user.username}, {user_dept}) cannot enter data "
                        f"for department {data.get('department')}."
                    )
                    return self.form_invalid(form)

        # ← NEW: set up our import trackers
        created = []
        skipped = []

        # 3) Process every row
        for data in rows:
            from .models import Department
            dept_obj = Department.objects.get(code=data['department'])

            mat, _ = Material.objects.get_or_create(
                material_number=data['material_number'],
                defaults={
                    'description': data['description'],
                    'department':  dept_obj,
                    'created_by':  user,
                }
            )

            # **THIS** is where we enforce the material+batch uniqueness:
            batch, was_new = Batch.objects.get_or_create(
                material=mat,
                batch_number=data['batch_number']
            )
            if not was_new:
                # record the skip and move on
                skipped.append(data)
                continue

            # otherwise create the Roll + QR exactly as before
            cust, _ = Customer.objects.get_or_create(name='Unknown')
            roll = Roll.objects.create(
                batch=batch,
                weight_kg=data['weight_kg'],
                customer=cust
            )
            url   = f"{settings.SITE_URL}/r/{roll.roll_id}"
            img   = qrcode.make(url)
            qrdir = os.path.join(settings.MEDIA_ROOT, 'qrcodes')
            os.makedirs(qrdir, exist_ok=True)
            img.save(os.path.join(qrdir, f"{roll.roll_id}.png"))
            created.append(roll)

        # 4) Persist an ImportLog for audit
        ImportLog.objects.create(
            total_rows = len(rows),
            imported   = len(created),
            skipped    = len(skipped),
            details    = "\n".join(
                f"{d['material_number']}|{d['batch_number']}" for d in skipped
            )
        )

        # 5) Surface messages to the user
        if created:
            messages.success(
                self.request,
                f"Imported {len(created)} of {len(rows)} rows; "
                f"skipped {len(skipped)} duplicate{'' if len(skipped)==1 else 's'}."
            )
            # redirect to print the *first* new roll
            return redirect('material-print', roll_id=created[0].roll_id)

        # if we got here, nothing was created
        messages.warning(
            self.request,
            f"No new rolls created; {len(skipped)} duplicate{'' if len(skipped)==1 else 's'} skipped."
        )
        form.add_error(None, "No new batches created (all duplicates?).")
        return self.form_invalid(form)


class MaterialPrintView(DeptPermissionMixin, TemplateView):
    template_name = 'warehouse/material_print.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        roll = get_object_or_404(Roll, roll_id=kwargs['roll_id'])
        ctx.update({
            'roll': roll,
            'qr_link': f"{settings.SITE_URL}/r/{roll.roll_id}",
            'qr_image_url': f"{settings.SITE_URL}{settings.MEDIA_URL}qrcodes/{roll.roll_id}.png",
        })
        return ctx

class UniversalScanView(TemplateView):
    template_name = 'warehouse/universal_scan.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        roll = get_object_or_404(Roll, roll_id=kwargs['roll_id'])
        # fetch latest location from roll.current_location
        # fetch full history
        history = Transaction.objects.filter(roll=roll).order_by('-scanned_at')
        ctx.update({
            'roll': roll,
            'history': history,
        })
        return ctx




# warehouse/views.py

from django.views.generic import ListView

'''
class PrintSearchView(DeptPermissionMixin, ListView):
    model               = Roll
    template_name       = 'warehouse/material_search.html'
    context_object_name = 'rolls'
    paginate_by         = 20

    def get_queryset(self):
        user = self.request.user
        print(f"[DEBUG] PrintSearchView: user={user.username!r}, groups={list(user.groups.values_list('name',flat=True))!r}")

        # 1) Start from all rolls, newest first
        qs = super().get_queryset().order_by('-batch__created_at')

        # 2) Plant Manager & Stock Keeper: restrict to their material.department
        if not (user.is_superuser or user.groups.filter(name='Factory Admin').exists()):
            home = user.profile.department.code
            allowed = [home]
            if user.groups.filter(name='Stock Keeper').exists():
                allowed += user.profile.get_extra_access_list()

            print(f"[DEBUG] allowed dept codes = {allowed!r}")
            # 🔥 Filter on batch → material → department, NOT current_location
            qs = qs.filter(batch__material__department__code__in=allowed)

        # 3) Date range
        df = self.request.GET.get('date_from','').strip()
        dt = self.request.GET.get('date_to','').strip()
        if df:
            qs = qs.filter(batch__created_at__date__gte=df)
        if dt:
            qs = qs.filter(batch__created_at__date__lte=dt)

        # 4) Free‑text search
        q = self.request.GET.get('q','').strip()
        if q:
            qs = qs.filter(
                Q(batch__material__material_number__icontains=q) |
                Q(batch__batch_number__icontains=q)              |
                Q(batch__material__description__icontains=q)
            )

        # 5) Admin override by ?dept=XX
        if user.is_superuser or user.groups.filter(name='Factory Admin').exists():
            dept = self.request.GET.get('dept','').upper().strip()
            if dept:
                print(f"[DEBUG] Admin override: filtering dept={dept!r}")
                qs = qs.filter(batch__material__department__code=dept)

        print("[DEBUG] final QS SQL:", qs.query)
        return qs

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        user = self.request.user

        # carry forward form values
        ctx['search_query'] = self.request.GET.get('q','')
        ctx['date_from']    = self.request.GET.get('date_from','')
        ctx['date_to']      = self.request.GET.get('date_to','')

        # Admins get a department picker
        if user.is_superuser or user.groups.filter(name='Factory Admin').exists():
            ctx['departments']   = Department.objects.order_by('name')
            ctx['selected_dept'] = self.request.GET.get('dept','').upper().strip()
        else:
            ctx['departments']   = None
            ctx['selected_dept'] = user.profile.department.code

        return ctx



    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # keep filter inputs populated
        ctx['date_from']    = self.request.GET.get('date_from','')
        ctx['date_to']      = self.request.GET.get('date_to','')
        ctx['search_query'] = self.request.GET.get('q','')

        # only expose dept dropdown to superuser/Factory Admin
        if user.is_superuser or user.groups.filter(name='Factory Admin').exists():
            ctx['departments']   = Department.objects.order_by('code')
            ctx['selected_dept'] = self.request.GET.get('dept','').upper()
        else:
            ctx['departments']   = []
            ctx['selected_dept'] = user.profile.department.code

        return ctx
'''


# warehouse/views.py


from django.views.generic import ListView



class PrintSearchView(DeptPermissionMixin, ListView):
    model               = Roll
    template_name       = 'warehouse/material_search.html'
    context_object_name = 'rolls'
    paginate_by         = 20

    def get_queryset(self):
        user = self.request.user
#        print(f"[DEBUG] PrintSearchView: user={user.username!r}, groups={list(user.groups.values_list('name', flat=True))!r}")

        # 1) Let the mixin already have scoped `qs` to the user's department(s)
        qs = super().get_queryset().order_by('-batch__created_at')

        # 2) Date range filters
        df = self.request.GET.get('date_from','').strip()
        dt = self.request.GET.get('date_to',  '').strip()
        if df:
            qs = qs.filter(batch__created_at__date__gte=df)
        if dt:
            qs = qs.filter(batch__created_at__date__lte=dt)

        # 3) Free‑text search
        q = self.request.GET.get('q','').strip()
        if q:
            qs = qs.filter(
                Q(batch__material__material_number__icontains=q) |
                Q(batch__batch_number__icontains=q)                |
                Q(batch__material__description__icontains=q)
            )

        # 4) Admin override: allow Factory Admin & superuser to add ?dept=XX
        if user.is_superuser or user.groups.filter(name='Factory Admin').exists():
            dept = self.request.GET.get('dept','').upper().strip()
            if dept:
                print(f"[DEBUG] Admin override: filtering dept={dept!r}")
                qs = qs.filter(batch__material__department__code=dept)

#        print("[DEBUG] final QS SQL:", qs.query)
        return qs

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        user = self.request.user

        # echo back filter values
        ctx['search_query'] = self.request.GET.get('q','')
        ctx['date_from']    = self.request.GET.get('date_from','')
        ctx['date_to']      = self.request.GET.get('date_to','')

        # only superuser/Factory Admin sees the dept dropdown
        if user.is_superuser or user.groups.filter(name='Factory Admin').exists():
            ctx['departments']   = Department.objects.order_by('name')
            ctx['selected_dept'] = self.request.GET.get('dept','').upper().strip()
        else:
            ctx['departments']   = None
            ctx['selected_dept'] = user.profile.department.code

        return ctx




# mobile view

@method_decorator(ensure_csrf_cookie, name="dispatch")
class RollScanView(DeptPermissionMixin, TemplateView):
    """
    QA Scan of newly produced rolls.
    Allowed: superuser, Factory Admin, Plant Manager, Stock Keeper, Operator
    """
    template_name   = 'mobile/roll_scan.html'
    allowed_roles   = [
        'Factory Admin',
        'Plant Manager',
        'Stock Keeper',
        'Operator',
    ]

@method_decorator(ensure_csrf_cookie, name="dispatch")
class StoreView(DeptPermissionMixin, TemplateView):
    """
    Store/Putaway rolls into a rack location.
    Allowed: superuser, Factory Admin, Plant Manager, Stock Keeper, Operator
    """
    template_name   = 'mobile/store.html'
    allowed_roles   = [
        'Factory Admin',
        'Plant Manager',
        'Stock Keeper',
        'Operator',
    ]

@method_decorator(ensure_csrf_cookie, name="dispatch")
class DispatchView(DeptPermissionMixin, TemplateView):
    template_name = 'mobile/dispatch.html'
    allowed_roles = [
        'Factory Admin',
        'Plant Manager',
        'Operator',
        'Forklift Driver',
    ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # supply the dropdown list of all departments
        ctx['departments'] = Department.objects.order_by('code')
        return ctx


# Dashboard for Managers & Stock Keepers



from django.db.models import Max, Q

class DashboardView(DeptPermissionMixin, TemplateView):
    template_name = 'warehouse/dashboard.html'
    allowed_roles = [
        'Factory Admin',
        'Plant Manager',
        'Stock Keeper',
    ]

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model
        User = get_user_model()


        ctx = super().get_context_data(**kwargs)

        user = self.request.user
        is_admin = user.groups.filter(name='Factory Admin').exists()

        # Determine effective department filter:
        if is_admin:
            selected_dept = self.request.GET.get('dept', '').upper().strip()
        else:
            # non-admins are locked to their own department
            selected_dept = getattr(getattr(user, 'profile', None), 'department', None)
            selected_dept = selected_dept.code if selected_dept else ''
        # --- summary cards logic with dept scoping ---
        # Produced: rolls whose material was created/registered by that department
        produced_qs = Roll.objects.all()
        if selected_dept:
            produced_qs = produced_qs.filter(batch__material__department__code=selected_dept)
        produced = produced_qs.count()

        # Stored: PUTAWAYs into locations prefixed by the department code
        stored_qs = Transaction.objects.filter(action='PUTAWAY')
        if selected_dept:
            stored_qs = stored_qs.filter(location__location_code__startswith=selected_dept)
        stored = stored_qs.values('roll').distinct().count()

        # Dispatched: dispatches performed by users of that department
        # Dispatched: dispatches performed by users of that department
        dispatched_qs = Transaction.objects.filter(action='DISPATCH')
        if selected_dept:
            # get usernames of users who belong to that department
            dept_usernames = list(
                User.objects.filter(profile__department__code=selected_dept)
                            .values_list('username', flat=True)
            )
            dispatched_qs = dispatched_qs.filter(user__in=dept_usernames)
        dispatched = dispatched_qs.values('roll').distinct().count()


        pending_storage = produced - stored
        pending_dispatch = stored - dispatched

        # Build latest transaction per roll (then scope for grid visibility)
        latest = Transaction.objects.values('roll').annotate(last_ts=Max('scanned_at'))
        latest_txs = Transaction.objects.filter(
            scanned_at__in=[l['last_ts'] for l in latest]
        )

        # Apply department-level visibility to latest_txs for the grid
        if selected_dept:
            if is_admin:
                if selected_dept:
                    dept_usernames = list(
                        User.objects.filter(profile__department__code=selected_dept)
                                    .values_list('username', flat=True)
                    )
                    latest_txs = latest_txs.filter(
                        Q(location__location_code__startswith=selected_dept) |
                        (Q(action='DISPATCH') & Q(user__in=dept_usernames))
                    )
             # else: no dept filter for admin → leave latest_txs as-is
            else:
                # non-admin: lock to their own department
                dept_usernames = list(
                    User.objects.filter(profile__department__code=selected_dept)
                                .values_list('username', flat=True)
                )
                latest_txs = latest_txs.filter(
                    Q(location__location_code__startswith=selected_dept) |
                    (Q(action='DISPATCH') & Q(user__in=dept_usernames))
                )


        # build location map from the filtered latest_txs
        location_map = {loc.location_code: [] for loc in Location.objects.all()}
        location_map['DISPATCHED'] = []
        for tx in latest_txs:
            key = tx.location.location_code if tx.location else 'DISPATCHED'
            location_map.setdefault(key, []).append({
                'roll':             tx.roll,
                'description':      tx.roll.batch.material.description,
                'posting_date':     tx.scanned_at,
            })

        cards = [
            {'label':'Produced',        'count':produced,        'bg':'#cce5ff'},
            {'label':'Stored',          'count':stored,          'bg':'#d4edda'},
            {'label':'Dispatched',      'count':dispatched,      'bg':'#f8d7da'},
            {'label':'Pending Storage', 'count':pending_storage, 'bg':'#fff3cd'},
            {'label':'Pending Dispatch','count':pending_dispatch,'bg':'#e2e3e5'},
        ]

        # flatten to list of tuples for any-dept view
        full_locations = list(location_map.items())

        # department picker + grid setup
        all_depts     = Department.objects.order_by('code')
        # selected_dept already determined above; for filtering the grid:
        if selected_dept:
            filtered = [
              (loc, rolls)
              for loc, rolls in full_locations
              if loc.startswith(selected_dept)
            ]
        else:
            filtered = full_locations

        # build rows/cols with minimum 2 logic (unchanged)
        real_rows = sorted({
            loc[2]
            for loc, _ in filtered
            if loc != 'DISPATCHED'
        })
        real_cols = sorted({
            int(loc[-2:])
            for loc, _ in filtered
            if loc != 'DISPATCHED'
        })

        rows = real_rows[:]
        if not rows:
            rows = ['A','B']
        elif len(rows) == 1:
            rows.append(chr(ord(rows[0]) + 1))

        cols = real_cols[:]
        if not cols:
            cols = [1, 2]
        elif len(cols) == 1:
            cols.append(cols[0] + 1)

        cell_map = {}
        for loc, entries in filtered:
            if loc == 'DISPATCHED':
                continue
            r = loc[2]
            c = int(loc[-2:])
            cell_map.setdefault((r,c), []).extend(entries)

        grid_matrix = []
        for r in rows:
            row_cells = [ cell_map.get((r,c), []) for c in cols ]
            grid_matrix.append((r, row_cells))

        ctx.update({
            'cards':         cards,
            'departments':   all_depts,
            'selected_dept': selected_dept,
            'is_admin':      is_admin,
            'grid_cols':     cols,
            'grid_matrix':   grid_matrix,
            'real_row_count': len(real_rows),
            'real_col_count': len(real_cols),
        })

        # reconciliation log (unchanged)
        latest_log = ReconciliationLog.objects.order_by('-run_at').first()
        if latest_log and not latest_log.is_clean:
            ctx['mismatch_count'] = latest_log.mismatches.count("\n") + 1
            ctx['mismatch_log_id'] = latest_log.id
        else:
            ctx['mismatch_count'] = 0
            ctx['mismatch_log_id'] = None

        return ctx




# Location


class LocationScanView(TemplateView):
    template_name = 'warehouse/location_scan.html'

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        loc = get_object_or_404(Location, location_code=self.kwargs['location_code'])
        # show rolls at this location
        latest = (Transaction.objects
                  .filter(location=loc, action='PUTAWAY')
                  .order_by('-scanned_at'))
        # you can dedupe/scoped as you like
        ctx.update({
            'location': loc,
            'transactions': latest[:50],
        })
        return ctx


# Login & Sign uo

class SignUpView(CreateView):
    template_name = 'registration/signup.html'
    form_class    = SignUpForm
    success_url   = reverse_lazy('login')   # after sign‑up, send them to the login page

    def form_valid(self, form):
        # save the new user + profile
        response = super().form_valid(form)

        # let them know they’re pending approval
        messages.info(
            self.request,
            "Thank you for signing up! Your account is now pending approval by your Factory Admin. "
            "If you need Operator/Dispatch/Manager access, please contact your Factory IT Admin."
        )

        return response


class RootRedirectView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_superuser:
            return redirect('dashboard')
        grp = {g.name for g in request.user.groups.all()}
        if 'Factory Admin' in grp or 'Plant Manager' in grp or 'Stock Keeper' in grp:
            return redirect('dashboard')
        if 'Operator' in grp:
            return redirect('scan-store')
        if 'Forklift Driver' in grp:
            return redirect('scan-dispatch')
        return redirect('scan-view')


class UniversalScanView(LoginRequiredMixin, TemplateView):
    template_name = 'mobile/scan_view_only.html'

from .bartender           import print_roll_label

class PrintLabelView(View):
    def post(self, request, *args, **kwargs):
        roll = get_object_or_404(Roll, roll_id=kwargs["roll_id"])
        try:
            result = print_roll_label(roll)
            job_id = result["JobIds"][0]
            messages.success(request, f"Label sent to printer (job #{job_id})")
        except Exception as e:
            messages.error(request, f"Print failed: {e}")
        return redirect('material-print', roll_id=roll.roll_id)