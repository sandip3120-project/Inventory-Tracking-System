from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, FieldError
from django.shortcuts import redirect
from django.contrib import messages
from django.db.models import Q

class DeptPermissionMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    – Superuser, Factory Admin, Forklift Driver: full access.
    – Plant Manager & Operator: only their profile.department.
    – Stock Keeper: their department + any in extra_access.
    """

    def test_func(self):
        user = self.request.user

        # 1) Superuser, Admin, Forklift Driver bypass
        if user.is_superuser or user.groups.filter(
            name__in=['Factory Admin','Forklift Driver']
        ).exists():
            return True

        # 2) Everyone else: must have a home department
        prof = getattr(user, 'profile', None)
        if not prof or not prof.department:
            return False

        # 3) Plant Manager & Operator: can only act in prof.department
        if user.groups.filter(name__in=['Plant Manager','Operator']).exists():
            # we'll enforce in dispatch() below
            return True

        # 4) Stock Keeper: can create/print in home dept, 
        #    but may receive transfers into extra_access
        if user.groups.filter(name='Stock Keeper').exists():
            return True

        return False  # any other roles denied

    def handle_no_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return super().handle_no_permission()
        messages.error(
            self.request,
            "You don’t have permission to view that page. "
            "Please contact your Factory IT Admin if you need access."
        )
        return redirect('root')

    def dispatch(self, request, *args, **kwargs):
        # 0) If not logged in, let Mixin redirect to login
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        # now it's safe to touch request.user.profile
        user = request.user
        prof = user.profile

        # Skip for admin/drivers
        if user.is_superuser or user.groups.filter(
            name__in=['Factory Admin','Forklift Driver']
        ).exists():
            return super().dispatch(request, *args, **kwargs)

        home = prof.department.code  # two‑letter code

        # For list & search views: filter querysets
        if hasattr(self, 'get_queryset'):
            qs = super().get_queryset()

            # build the list of codes this user can see
            allowed = [home]
            if user.groups.filter(name='Stock Keeper').exists():
                allowed += prof.get_extra_access_list()

            # now scope on material.department.code
            qs = qs.filter(batch__material__department__code__in=allowed)

            self.queryset = qs

        # For forms that ask department, lock it down
        if hasattr(self, 'get_form'):
            form = self.get_form()
            if 'department' in form.fields:
#                form.fields['department'].choices = [(home, home)]
#                form.fields['department'].initial   = home
                # show “FM – Film” instead of just “FM”
                label = f"{home} – {prof.department.name}"
                form.fields['department'].choices = [(home, label)]
                form.fields['department'].initial   = home
                form.fields['department'].widget.attrs['readonly'] = True

        return super().dispatch(request, *args, **kwargs)
