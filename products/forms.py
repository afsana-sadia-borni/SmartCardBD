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


class QuestionForm(forms.Form):
    question = forms.CharField(
        min_length=10, max_length=500,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'e.g. Does this come with a warranty?'}),
        error_messages={'min_length': 'Please write a little more (at least 10 characters).'},
    )
