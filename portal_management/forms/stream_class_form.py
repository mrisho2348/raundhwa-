# portal_management/forms/stream_class_form.py

from django import forms
from django.core.exceptions import ValidationError
from core.models import StreamClass, ClassLevel
from .widgets import Select2Widget


class StreamClassForm(forms.ModelForm):
    """Form for creating/editing stream classes."""
    
    # Stream letter choices (A-Z)
    STREAM_LETTER_CHOICES = [(chr(i), chr(i)) for i in range(65, 91)]  # A to Z
    
    # Override stream_letter as a ChoiceField
    stream_letter = forms.ChoiceField(
        choices=[('', 'Select letter...')] + STREAM_LETTER_CHOICES,
        widget=Select2Widget(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select stream letter...',
            'data-allow-clear': 'true',
        }),
        required=True,
        help_text="Select the stream letter (A, B, C, etc.)"
    )
    
    class Meta:
        model = StreamClass
        fields = ['class_level', 'stream_letter', 'name', 'capacity']
        widgets = {
            'class_level': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select class level...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '1',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Form 1A',
            }),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '200',
                'placeholder': 'Maximum number of students',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['class_level'].required = True
        self.fields['stream_letter'].required = True
        self.fields['capacity'].required = False
        self.fields['name'].required = False
        
        # Set help texts
        self.fields['class_level'].help_text = "Select the class level for this stream"
        self.fields['stream_letter'].help_text = "Choose the stream letter (A, B, C, etc.)"
        self.fields['name'].help_text = "Leave blank to auto-generate from class level and letter"
        self.fields['capacity'].help_text = "Maximum number of students allowed in this stream"
        
        # Add CSS classes to all fields
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs') and 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'
    
    def clean_stream_letter(self):
        """Validate stream letter."""
        stream_letter = self.cleaned_data.get('stream_letter')
        
        if stream_letter:
            # Ensure it's a single uppercase letter
            stream_letter = stream_letter.upper().strip()
            if len(stream_letter) != 1 or not stream_letter.isalpha():
                raise forms.ValidationError("Stream letter must be a single letter (A-Z).")
        
        return stream_letter
    
    def clean_capacity(self):
        """Validate capacity."""
        capacity = self.cleaned_data.get('capacity')
        
        if capacity is not None:
            if capacity < 1:
                raise forms.ValidationError("Capacity must be at least 1.")
            if capacity > 200:
                raise forms.ValidationError("Capacity cannot exceed 200.")
        
        return capacity
    
    def clean(self):
        """Validate unique constraint across class_level and stream_letter."""
        cleaned_data = super().clean()
        
        class_level = cleaned_data.get('class_level')
        stream_letter = cleaned_data.get('stream_letter')
        
        if class_level and stream_letter:
            # Check for existing stream with same class_level and stream_letter
            existing = StreamClass.objects.filter(
                class_level=class_level,
                stream_letter=stream_letter
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(
                    f"A stream with letter '{stream_letter}' already exists for "
                    f"{class_level.name}. Please choose a different letter."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the stream class and auto-generate name if not provided."""
        stream = super().save(commit=False)
        
        # Auto-generate name if not provided
        if not stream.name and stream.class_level and stream.stream_letter:
            stream.name = f"{stream.class_level.name}{stream.stream_letter}"
        
        if commit:
            stream.save()
        
        return stream