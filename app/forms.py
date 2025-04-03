from django import forms
from .models import Review

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-3 py-2 border rounded-md',
                'placeholder': 'Share your thoughts about this company...'
            }),
            'rating': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-md'
            }),
        }