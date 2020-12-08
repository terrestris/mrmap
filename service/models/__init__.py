# TODO split models.py further and import individual models individually
# https://docs.djangoproject.com/en/3.1/topics/db/models/#organizing-models-in-a-package
from .models import *
from service.mapcontext.models import MapContext, MapResource, WmsOffering
