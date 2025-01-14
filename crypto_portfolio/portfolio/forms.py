from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class RegistrationForm(UserCreationForm):
    api_key = forms.CharField(max_length=100)
    secret_key = forms.CharField(max_length=100)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2', 'api_key', 'secret_key')


