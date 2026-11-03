from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.fields import PhoneField
from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.urls import reverse

from .constants import BD_PHONE_REGEX, normalize_bd_phone
from .models import CustomerProfile, get_profile

bd_mobile_validator = RegexValidator(BD_PHONE_REGEX, 'Enter a Bangladeshi mobile number, e.g. 01712345678.')


class BDPhoneField(PhoneField):
    """Accepts '01712-345678' and '01712 345678': spaces and dashes are removed before validating."""

    def to_python(self, value):
        return super().to_python(value).replace(' ', '').replace('-', '')


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        """Staff land on the store panel after logging in; customers go to the shop.
        A ?next= link still wins (allauth checks it before calling this)."""
        if request.user.is_staff:
            return reverse('store:dashboard')
        return super().get_login_redirect_url(request)

    # ---- Log in / sign up with a Bangladeshi mobile number (allauth's phone support) ----

    def phone_form_field(self, **kwargs):
        kwargs.setdefault('label', 'Mobile number')
        kwargs['validators'] = [bd_mobile_validator]  # instead of the international +... format
        kwargs.setdefault('widget', forms.TextInput(attrs={
            'placeholder': '01XXXXXXXXX', 'autocomplete': 'tel', 'type': 'tel', 'inputmode': 'tel',
        }))
        return BDPhoneField(**kwargs)

    def clean_phone(self, phone):
        return normalize_bd_phone(phone)

    def set_phone(self, user, phone, verified):
        CustomerProfile.objects.filter(pk=get_profile(user).pk).update(phone=normalize_bd_phone(phone),
                                                                       phone_verified=verified)

    def get_phone(self, user):
        profile = CustomerProfile.objects.filter(user=user).values('phone', 'phone_verified').first()
        if profile and profile['phone']:
            return profile['phone'], profile['phone_verified']
        return None

    def set_phone_verified(self, user, phone):
        CustomerProfile.objects.filter(user=user, phone=normalize_bd_phone(phone)).update(phone_verified=True)

    def get_user_by_phone(self, phone):
        phone = normalize_bd_phone(phone)
        return get_user_model().objects.filter(profile__phone=phone).first() if phone else None

    def send_verification_code_sms(self, user, phone, code, **kwargs):
        # Needs an SMS gateway (e.g. SSL Wireless, BulkSMSBD). Phone verification is off until then.
        raise NotImplementedError('No SMS gateway configured.')
