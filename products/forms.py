from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(i, f'{i} ★') for i in range(5, 0, -1)],
        coerce=int,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                             'placeholder': 'How did you like this product?'}),
        }
