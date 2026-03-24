from django import forms
from .models import User

class LoginForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'placeholder':'Username','autofocus':True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder':'Password'}))

class CreateUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=6)
    class Meta:
        model  = User
        fields = ['username','email','first_name','last_name','role']

class EditUserForm(forms.ModelForm):
    new_password = forms.CharField(widget=forms.PasswordInput, required=False,
                                   help_text="Leave blank to keep current password")
    class Meta:
        model  = User
        fields = ['first_name','last_name','email','is_active']
