from django import forms
from django.conf import settings
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from accounts.constants import DISTRICT_CHOICES
from accounts.forms import UpazilaMixin
from accounts.models import get_profile, phone_validator

from . import payments
from .models import DeliveryZone, Order, ReturnRequest


class CheckoutForm(UpazilaMixin, forms.Form):
    full_name = forms.CharField(max_length=100, label=_l('Full name'), widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label=_l('Email'), widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(
        max_length=15, validators=[phone_validator], label=_l('Phone'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}),
    )
    district = forms.ChoiceField(
        choices=[('', _l('Select district'))] + DISTRICT_CHOICES, label=_l('District'),
        widget=forms.Select(attrs={'class': 'form-select js-district', 'id': 'id_district'}),
    )
    upazila = forms.CharField(
        max_length=60, label=_l('Upazila / Thana'), widget=forms.TextInput(attrs={'class': 'form-select js-upazila'}),
    )
    area = forms.CharField(
        max_length=100, label=_l('Area'), widget=forms.TextInput(attrs={'class': 'form-control',
                                                                        'placeholder': _l('e.g. Road 5, Block C')}),
    )
    address_line = forms.CharField(
        max_length=255, label=_l('Address'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _l('House, road, village')}),
    )
    note = forms.CharField(
        required=False, label=_l('Order note (optional)'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': _l('e.g. Please call before delivery')}),
    )
    gift_wrap = forms.BooleanField(required=False, label=_l('Gift wrap this order'))
    use_points = forms.BooleanField(required=False, label=_l('Use my reward points'))
    payment_method = forms.ChoiceField(
        choices=[(Order.PaymentMethod.COD, _l('Cash on Delivery'))] + Order.PaymentChannel.choices
        + [(Order.PaymentMethod.SSLCOMMERZ, _l('Other online methods'))],
        initial=Order.PaymentMethod.COD, widget=forms.RadioSelect, label=_l('Payment'),
    )
    save_address = forms.BooleanField(required=False, initial=True, label=_l('Save this address to my account'))

    SHIPPING_FIELDS = ['full_name', 'email', 'phone', 'district', 'upazila', 'area', 'address_line', 'note']

    def payment(self):
        """The chosen option as (payment_method, payment_channel), e.g. ('sslcommerz', 'bkash')."""
        choice = self.cleaned_data['payment_method']
        if choice in Order.PaymentChannel.values:
            return Order.PaymentMethod.SSLCOMMERZ, choice
        return choice, ''

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gift_wrap'].help_text = _('Wrapped with a card, +৳{price}').format(price=settings.GIFT_WRAP_PRICE)
        self.points = 0
        if user and user.is_authenticated:
            self.points = get_profile(user).points
        if self.points < settings.POINTS_REDEEM_BLOCK:
            del self.fields['use_points']
        if not (user and user.is_authenticated):
            del self.fields['save_address']
        if not payments.is_configured():
            self.fields['payment_method'].choices = [(Order.PaymentMethod.COD, _('Cash on Delivery'))]

    def shipping_data(self):
        return {name: self.cleaned_data[name] for name in self.SHIPPING_FIELDS}


class TrackOrderForm(forms.Form):
    order_number = forms.CharField(max_length=20, label=_l('Order number'), widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': _l('e.g. SCB261101-A1B2C3')}))
    phone = forms.CharField(max_length=15, validators=[phone_validator], label=_l('Phone'), widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}))


class ReturnRequestForm(forms.ModelForm):
    MAX_PHOTO_MB = 5

    class Meta:
        model = ReturnRequest
        fields = ['reason', 'details', 'photo']
        labels = {'reason': _l('Reason'), 'details': _l('Details'), 'photo': _l('Photo')}
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'details': forms.Textarea(attrs={'class': 'form-control', 'rows': 4,
                                             'placeholder': _l('Tell us what went wrong')}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > self.MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(_('Photo must be smaller than {mb} MB.').format(mb=self.MAX_PHOTO_MB))
        return photo


class DeliveryZoneForm(forms.ModelForm):
    districts = forms.MultipleChoiceField(
        choices=DISTRICT_CHOICES, required=False, widget=forms.CheckboxSelectMultiple,
        help_text='Leave empty for the default zone.',
    )

    class Meta:
        model = DeliveryZone
        fields = '__all__'
