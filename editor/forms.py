"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, CheckboxInput
from django.utils.translation import gettext_lazy as _

from service.models import Metadata, FeatureType


class MetadataEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "inherit_proxy_uris",
            # "metadata_url",
            # "keywords",
            # "categories",
            # "reference_system",
        ]
        labels = {
            "inherit_proxy_uris": _("Use metadata proxy"),
        }
        widgets = {
            "inherit_proxy_uris": CheckboxInput(attrs={"class": "checkbox-input"}),
        }


class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]