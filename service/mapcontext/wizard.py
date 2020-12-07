"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from MrMap.wizards import MrMapWizard
from .forms import MapContextIdentificationForm, MapContextLayersForm
from ..models import MapContext, MapResource

NEW_MAPCONTEXT_WIZARD_FORMS = [
    (_("identification"), MapContextIdentificationForm),
    (_("layers"), MapContextLayersForm)
]


class NewMapContextWizard(MrMapWizard):
    def __init__(self, current_view, *args, **kwargs):
        super(MrMapWizard, self).__init__(
            action_url=reverse('resource:add-mapcontext', ) + f"?current-view={current_view}",
            current_view=current_view,
            *args,
            **kwargs)

    def done(self, form_list, form_dict, **kwargs):
        identification_values = form_dict.get(_("identification")).cleaned_data
        layers_values = form_dict.get(_("layers")).cleaned_data

        context = MapContext(title=identification_values["title"], abstract=identification_values["abstract"])
        context.save()
        layer_md = layers_values["layer"]
        resource = MapResource(title=layer_md.title, abstract=layer_md.title, context=context)
        resource.save()

        return HttpResponseRedirect(reverse(self.current_view, ), status=303)
