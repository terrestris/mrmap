"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from MapSkinner.messages import EMAIL_IS_UNKNOWN
from MapSkinner.settings import MIN_PASSWORD_LENGTH
from MapSkinner.validators import PASSWORD_VALIDATORS, USERNAME_VALIDATORS
from structure.models import MrMapUser, Theme


class PasswordResetForm(forms.Form):
    email = forms.EmailField(max_length=255, required=True, label=_("E-Mail"), label_suffix="")

    def clean(self):
        cleaned_data = super(PasswordResetForm, self).clean()
        email = cleaned_data.get("email")
        try:
            MrMapUser.objects.get(email=email)
        except ObjectDoesNotExist:
            self.add_error("email", forms.ValidationError(EMAIL_IS_UNKNOWN))

        return cleaned_data


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(
        max_length=255,
        label=_("Old password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
    )
    new_password = forms.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=255,
        label=_("New password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
        validators=PASSWORD_VALIDATORS
    )
    new_password_again = forms.CharField(
        max_length=255,
        label=_("Confirm new Password"),
        label_suffix=" ",
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned_data = super(PasswordChangeForm, self).clean()
        password = cleaned_data.get("new_password")
        password_again = cleaned_data.get("new_password_again")

        if password != password_again:
            self.add_error("new_password_again", forms.ValidationError(_("Password and confirmed password does not match")))

        return cleaned_data


class UserForm(forms.ModelForm):
    theme = forms.ModelChoiceField(queryset=Theme.objects.all(), to_field_name='name', empty_label=None, required=False)

    class Meta:
        model = MrMapUser
        fields = [
            "first_name",
            "last_name",
            "email",
            "confirmed_newsletter",
            "confirmed_survey",
            "theme",
        ]
