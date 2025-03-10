from django.forms import ModelForm
from dal import autocomplete
from django.utils.translation import gettext_lazy as _
from csw.models import HarvestResult
from service.helper.enums import MetadataEnum
from service.models import Metadata


class HarvestRunForm(ModelForm):
    class Meta:
        model = HarvestResult
        fields = ('metadata', )
        widgets = {
            'metadata': autocomplete.ModelSelect2(url='resource:autocomplete_metadata_catalouge')
        }
        labels = {
            'metadata': _('Resource'),
        }
        help_texts = {
            'metadata': _('Select one which will be harvested.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['metadata'].queryset = Metadata.objects.filter(metadata_type=MetadataEnum.CATALOGUE.value)
