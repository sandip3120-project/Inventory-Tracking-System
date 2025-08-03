from django import forms
from .models import Customer, Material, Department, Location 
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from .models import ROLE_CHOICES



class BatchDataForm(forms.Form):
    material_number = forms.CharField(label="Material Number", max_length=50, required=False)
    description     = forms.CharField(label="Description",     max_length=200, required=False)
    batch_number    = forms.CharField(label="Batch Number",    max_length=50, required=False)
    weight_kg       = forms.FloatField(label="Weight (KG)",    required=False)
    posting_date    = forms.DateField(
                        label="Posting Date",
                        required=False,
                        widget=forms.DateInput(attrs={'type':'date'})
                     )

    # NEW: upload SAP sheet
    data_file       = forms.FileField(
                        label="Upload SAP Excel/CSV",
                        required=False,
                        help_text="We’ll extract the 5 columns you need"
                     )

    '''
    # NEW: department selector
    department = forms.ChoiceField(
        label="Department",
        choices=[('', '— Select department —')] +
                [(d.code, d.code) for d in Department.objects.order_by('code')],
        required=True,
        help_text="Choose which dept this batch belongs to."
    )
    '''
    # placeholder; real choices set in __init__
    department = forms.ChoiceField(
        label="Department",
        choices=[('', '— Select department —')],
        required=True,
        help_text="Choose which dept this batch belongs to."
    )
    
    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        
        # If the user is NOT Factory Admin or Forklift Driver,
        # lock the department to their profile.dept
        user = getattr(request, 'user', None)
        if user and not user.groups.filter(name__in=['Factory Admin','Forklift Driver']).exists():
            user_dept = getattr(user.profile, 'dept', None)
#            if user_dept:
#                self.fields['department'].choices = [(user_dept, user_dept)]
#                self.fields['department'].initial   = user_dept
#                self.fields['department'].widget.attrs['readonly'] = True
        dept_obj = getattr(user.profile, 'department', None)
        if dept_obj:
            code = dept_obj.code
            name = dept_obj.name
            # lock down to “FM – Film” rather than just “FM”
            self.fields['department'].choices = [(code, f"{code} – {name}")]
            self.fields['department'].initial   = code
            self.fields['department'].widget.attrs['readonly'] = True
        
        # 1) Lazy‑load department options (only after migrations have run)
        try:
            qs = Department.objects.order_by('code')
            dept_choices = [('', '— Select department —')] + [
                (d.code, f"{d.code} – {d.name}") for d in qs
            ]
        except Exception:
            # DB not ready yet; leave only the placeholder
            dept_choices = [('', '— Select department —')]
        self.fields['department'].choices = dept_choices

        # 2) If not full‑access, lock them into their own dept
        user = getattr(self.request, 'user', None)
        if user and not user.groups.filter(
            name__in=['Factory Admin','Forklift Driver']
        ).exists():
            prof = getattr(user, 'profile', None)
            if prof and prof.department:
                code = prof.department.code
                label = f"{code} – {prof.department.name}"
                self.fields['department'].choices = [(code, label)]
                self.fields['department'].initial   = code
                self.fields['department'].widget.attrs['readonly'] = True        

    def clean(self):
        cleaned = super().clean()
        # either all manual fields OR an uploaded file must be present
        file_ok   = bool(cleaned.get('data_file'))
        manual_ok = all(cleaned.get(f) for f in [
            'material_number','description',
            'batch_number','weight_kg','posting_date'
        ])
        if not (file_ok or manual_ok):
            raise forms.ValidationError(
                "Please either fill all manual fields, or upload a SAP Excel/CSV."
            )
        return cleaned

class SignUpForm(forms.ModelForm):
    phone   = forms.CharField(max_length=20, label="Phone")
    pin     = forms.CharField(
        max_length=4,
        widget=forms.PasswordInput,
        label="PIN (4 digits)"
    )
    id_card = forms.ImageField(label="ID‑card photo")

    class Meta:
        model = User
        fields = ['username', 'password']
        widgets = {
            'password': forms.PasswordInput,
        }

    def clean_pin(self):
        pin = self.cleaned_data['pin']
        if not (pin.isdigit() and len(pin) == 4):
            raise ValidationError("PIN must be exactly 4 digits.")
        return pin

    def save(self, commit=True):
        # 1) create the User
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()

            # 2) fill in the Profile
            user.profile.phone          = self.cleaned_data['phone']
            user.profile.pin            = self.cleaned_data['pin']
            user.profile.id_card        = self.cleaned_data['id_card']
            user.profile.needs_approval = True
            user.profile.save()

            # 3) put them into View Only
            viewers = Group.objects.get(name="View Only")
            user.groups.add(viewers)

        return user
