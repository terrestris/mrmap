"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
from dal import autocomplete
from django import forms
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from MrMap.forms import MrMapWizardForm
from MrMap.widgets import BootstrapDatePickerInput
from editor.forms import MetadataModelChoiceField, ReferenceSystemModelMultipleChoiceField
from service.helper.enums import MetadataEnum
from service.models import Metadata, ReferenceSystem
from service.settings import ISO_19115_LANG_CHOICES
from users.helper import user_helper


class MapContextForm(forms.Form):
    title = forms.CharField(label=_('Title'))
    abstract = forms.CharField(label=_('Abstract'))
    # layer = MetadataModelChoiceField(
    #     queryset=Metadata.objects.none(),
    #     widget=autocomplete.ModelSelect2(
    #         url='editor:layer-autocomplete',
    #     ),
    #     required=False, )
    # TODO
    language_code = forms.ChoiceField(label=_('Language'), choices=ISO_19115_LANG_CHOICES)
    date_stamp = forms.DateTimeField(label=_('Metadata creation date'),
                                     widget=BootstrapDatePickerInput())
    layer_tree = forms.CharField(widget=forms.HiddenInput)


class MapContextResourceForm(forms.Form):
    name = forms.CharField(label=_('Name'))
    layer = MetadataModelChoiceField(
        queryset=Metadata.objects.none(),
        widget=autocomplete.ModelSelect2(
            url='editor:layer-autocomplete',
        ),
        required=False, )


class MapContextLayersForm(MrMapWizardForm):
    layer = MetadataModelChoiceField(
        queryset=Metadata.objects.none(),
        widget=autocomplete.ModelSelect2(
            url='editor:layer-autocomplete',
        ),
        required=False, )

    def __init__(self, *args, **kwargs):
        super(MapContextLayersForm, self).__init__(has_autocomplete_fields=True,
                                                   *args,
                                                   **kwargs)
        self.fields['layer'].queryset = user_helper.get_user(self.request).get_metadatas_as_qs(
            type=MetadataEnum.LAYER)
