"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
import uuid

from django.contrib.gis.db import models
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from service.models import Resource, Layer


class MapContext(Resource):
    title = models.CharField(max_length=1000, null=False, blank=False)
    abstract = models.TextField(null=False, blank=False)
    update_date = models.DateTimeField(auto_now_add=True)
    layer_tree = models.TextField(null=False, blank=False)
    # Additional possible parameters:
    # specReference
    # language
    # author
    # publisher
    # creator
    # rights
    # areaOfInterest
    # timeIntervalOfInterest
    # keyword
    # resource
    # contextMetadata
    # extension


class MapResource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    #title = models.CharField(max_length=1000, null=False, blank=False)
    abstract = models.TextField(null=False, blank=False)
    update_date = models.DateTimeField(auto_now_add=True)
    folder = TreeForeignKey('MapResourceFolder', on_delete=models.CASCADE)

    # Additional possible parameters:
    # author
    # publisher
    # rights
    # geospatialExtent
    # temporalExtent
    # contentDescription
    # preview
    # contentByRef
    # offering
    # active
    # keyword
    # minScaleDenominator
    # maxScaleDenominator
    # resourceMetadata
    # extension


class WmsOffering(models.Model):
    resource = models.ForeignKey(MapResource, on_delete=models.CASCADE)
    layer = models.ForeignKey(Layer, on_delete=models.DO_NOTHING)
    # code -> 'http://www.opengis.net/spec/owc-atom/1.0/req/wms' (FIXED)
    # operation ->
    # content
    # styleSet
    # extension


class MapResourceFolder(MPTTModel):
    name = models.CharField(max_length=1000, null=False, blank=False)
    context = models.ForeignKey(MapContext, on_delete=models.CASCADE)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')

    def __str__(self):
        return self.name

    @property
    def is_resource(self):
        return self.mapresource_set.exists()
