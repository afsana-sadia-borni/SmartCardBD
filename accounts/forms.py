from allauth.account.adapter import get_adapter
from allauth.account.forms import LoginForm as AllauthLoginForm
from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
from django.urls import reverse
from django.utils.safestring import mark_safe

from core.forms import HoneypotMixin
from core.middleware import REFERRAL_SESSION_KEY

from .geo import is_valid_upazila
from .models import Address, CustomerProfile, Subscriber


class UpazilaMixin:
    """Check the chosen upazila belongs to the chosen district."""

    def clean(self):
        cleaned = super().clean()
        district, upazila = cleaned.get('district'), cleaned.get('upazila')
        if district and upazila and not is_valid_upazila(district, upazila):
            self.add_error('upazila', 'Please choose an upazila / thana in the selected district.')
        return cleaned


class AddressForm(UpazilaMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = ['full_name', 'phone', 'district', 'upazila', 'area', 'address_line', 'is_default']
        labels = {'is_default': 'Make this my default address', 'upazila': 'Upazila / Thana', 'area': 'Area'}
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}),
            'district': forms.Select(attrs={'class': 'form-select js-district'}),
            'upazila': forms.TextInput(attrs={'class': 'form-select js-upazila'}),
            'area': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Road 5, Block C'}),
            'address_line': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'House, road, village'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['upazila'].required = True


def style_auth_fields(form):
    """Bootstrap classes for allauth's forms (rendered by our own login/signup templates)."""
    for name, field in form.fields.items():
        if name == form_honeypot_name(form):
            continue
        css = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'
        field.widget.attrs['class'] = (field.widget.attrs.get('class', '') + ' ' + css).strip()


def form_honeypot_name(form):
    return getattr(form, 'honeypot_field', None)


class LoginForm(AllauthLoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['login'].label = 'Email or mobile number'
        self.fields['login'].widget.attrs.update({'placeholder': 'you@example.com or 01XXXXXXXXX',
                                                  'autocomplete': 'username'})
        self.fields['password'].help_text = ''  # the template has its own "Forgot password?" link
        if 'remember' in self.fields:
            self.fields['remember'].label = 'Keep me logged in'
        style_auth_fields(self)


class SignupForm(HoneypotMixin, AllauthSignupForm):
    full_name = forms.CharField(max_length=150, label='Full name',
                                widget=forms.TextInput(attrs={'placeholder': 'Your name', 'autocomplete': 'name'}))
    referral_code = forms.CharField(
        max_length=20, required=False, label='Referral code (optional)',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. SCB1A2B3C'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(['full_name', 'phone', 'email', 'password1', 'password2', 'referral_code'])
        self.fields['phone'].required = True
        self.fields['phone'].label = 'Mobile number'
        self.fields['email'].widget.attrs['placeholder'] = 'you@example.com'
        self.fields['password1'].help_text = 'At least 8 characters, not only numbers.'
        self.fields['password2'].label = 'Confirm password'
        self.fields['password2'].widget.attrs['placeholder'] = 'Repeat it'
        style_auth_fields(self)

    def _clean_phone(self):
        """Say plainly that a number is taken. allauth's default hides it behind a "we sent you a code"
        page, which only works with an SMS gateway; without one people get stuck waiting for a code."""
        phone = self.cleaned_data.get('phone')
        if phone and get_adapter().get_user_by_phone(phone):
            self.add_error('phone', mark_safe(
                f'This mobile number already has an account. <a href="{reverse("account_login")}">Log in</a> '
                'instead, or use a different number.'))

    def clean_referral_code(self):
        code = self.cleaned_data['referral_code'].strip().upper()
        if code and not CustomerProfile.objects.filter(referral_code=code).exists():
            raise forms.ValidationError('This referral code is not valid.')
        return code

    def save(self, request):
        user = super().save(request)
        first, _, last = self.cleaned_data['full_name'].strip().partition(' ')
        user.first_name, user.last_name = first[:150], last[:150]
        user.save(update_fields=['first_name', 'last_name'])
        code = self.cleaned_data.get('referral_code') or request.session.pop(REFERRAL_SESSION_KEY, '')
        referrer = CustomerProfile.objects.filter(referral_code=code.upper()).exclude(user=user).first() if code else None
        if referrer:
            CustomerProfile.objects.filter(user=user).update(referred_by=referrer.user)
        return user


class NewsletterForm(HoneypotMixin, forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ['email']
