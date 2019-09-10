"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""
from rest_framework import serializers

from service.models import Service, Layer, Metadata, ServiceType, Keyword
from structure.models import Contact, Organization


class ServiceTypeSerializer(serializers.ModelSerializer):
    """ Serializer for ServiceType model

    """
    class Meta:
        model = ServiceType
        fields = [
            "name",
            "version"
        ]

class OrganizationSerializer(serializers.ModelSerializer):
    """ Serializer for Organization model

    """
    class Meta:
        model = Organization
        fields = [
            "id",
            "organization_name",
            "is_auto_generated",
            "person_name",
            "email",
            "phone",
            "facsimile",
            "city",
            "city",
            "country",
        ]


class MetadataSerializer(serializers.ModelSerializer):
    """ Serializer for Metadata model

    """
    contact = OrganizationSerializer()
    class Meta:
        model = Metadata
        fields = [
            "id",
            "identifier",
            "title",
            "abstract",
            #"keywords",
            "online_resource",
            "original_uri",
            "contact",
        ]

class ServiceSerializer(serializers.ModelSerializer):
    """ Serializer for Service model

    """
    metadata = MetadataSerializer()
    servicetype = ServiceTypeSerializer()
    class Meta:
        model = Service
        fields = [
            "id",
            "uuid",
            "metadata",
            "published_for",
            "servicetype",
        ]


class LayerSerializer(serializers.ModelSerializer):
    """ Serializer for Layer model

    """
    metadata = MetadataSerializer()
    #parent_service = ServiceSerializer()
    servicetype = ServiceTypeSerializer()
    class Meta:
        model = Layer
        fields = [
            "id",
            "uuid",
            "identifier",
            "metadata",
            "is_available",
            "is_active",
            #"bbox_lat_lon",
            "parent_service",
            "child_layer",
            "servicetype",
        ]
