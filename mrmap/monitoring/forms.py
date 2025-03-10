from dal import autocomplete
from django.forms import ModelForm
from monitoring.models import MonitoringRun
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _


class MonitoringRunForm(ModelForm):
    class Meta:
        model = MonitoringRun
        fields = ('metadatas', )
        widgets = {
            'metadatas': autocomplete.ModelSelect2Multiple(url='resource:autocomplete_metadata_service')
        }
        labels = {
            'metadatas': _('Resources'),
        }
        help_texts = {
            'metadatas': _('Select one or multiple resources which become checked.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['metadatas'].queryset = Metadata.objects.filter(metadata_type=MetadataEnum.SERVICE.value)
