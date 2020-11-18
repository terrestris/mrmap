import csv
import io
import json
import uuid

import os
from collections import OrderedDict

import time
from datetime import datetime
from json import JSONDecodeError

from PIL import Image
from dateutil.parser import parse
from django.contrib.gis.geos import Polygon, GeometryCollection
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.contrib.gis.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from MrMap.cacher import DocumentCacher
from MrMap.messages import PARAMETER_ERROR, LOGGING_INVALID_OUTPUTFORMAT
from MrMap.settings import HTTP_OR_SSL, HOST_NAME, GENERIC_NAMESPACE_TEMPLATE, ROOT_URL, EXEC_TIME_PRINT
from MrMap import utils
from MrMap.validators import not_uuid, validate_spatial_resolution_types_enum_choices
from monitoring.models import MonitoringSetting, MonitoringRun
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, MetadataEnum, OGCOperationEnum, DocumentEnum, \
    ResourceOriginEnum, CategoryOriginEnum, MetadataRelationEnum, HttpMethodEnum, SpatialResolutionTypesEnum
from service.helper.crypto_handler import CryptoHandler
from service.settings import DEFAULT_SERVICE_BOUNDING_BOX, EXTERNAL_AUTHENTICATION_FILEPATH, \
    SERVICE_OPERATION_URI_TEMPLATE, SERVICE_LEGEND_URI_TEMPLATE, SERVICE_DATASET_URI_TEMPLATE, COUNT_DATA_PIXELS_ONLY, \
    LOGABLE_FEATURE_RESPONSE_FORMATS, DIMENSION_TYPE_CHOICES, DEFAULT_MD_LANGUAGE, ISO_19115_LANG_CHOICES, DEFAULT_SRS, \
    service_logger, DEFAULT_MULTIPOLYGON_EMPTY, DEFAULT_POLYGON_EMPTY, DEFAULT_BOUNDING_BOX
from structure.models import MrMapGroup, Organization, MrMapUser
from service.helper import xml_helper


class Resource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    public_id = models.CharField(unique=True, max_length=255, validators=[not_uuid], null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(MrMapGroup, on_delete=models.SET_NULL, null=True, blank=True)
    last_modified = models.DateTimeField(null=True)
    is_deleted = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    def save(self, update_last_modified=True, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if update_last_modified:
            # We always want to have automatically the last timestamp from the latest change!
            # ONLY if the function is especially called with a False flag in update_last_modified, we will not change the record's last change
            self.last_modified = timezone.now()
        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        abstract = True


class Keyword(models.Model):
    keyword = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.keyword

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=["keyword"])
        ]


class ProxyLog(models.Model):
    from structure.models import MrMapUser
    metadata = models.ForeignKey('Metadata', on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(MrMapUser, on_delete=models.CASCADE, null=True, blank=True)
    operation = models.CharField(max_length=100, null=True, blank=True)
    uri = models.CharField(max_length=1000, null=True, blank=True)
    post_body = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    response_wfs_num_features = models.IntegerField(null=True, blank=True)
    response_wms_megapixel = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = [
            "-timestamp"
        ]

    def __str__(self):
        return str(self.id)

    @transaction.atomic
    def log_response(self, response, request_param: str, output_format: str):
        """ Evaluate the response.

        In case of a WFS response, the number of returned features will be counted.
        In case of a WMS response, the megapixel will be computed.

        Args:
            response: The response, could be xml or bytes
            request_param (str): The operation that has been performed
            output_format (str): The output format for the response
        Returns:
             nothing
        """
        start_time = time.time()
        if self.metadata.is_service_type(OGCServiceEnum.WFS):
            self._log_wfs_response(response, output_format)
        elif self.metadata.is_service_type(OGCServiceEnum.WMS):
            self._log_wms_response(response)
        else:
            # For future implementation
            pass
        self.operation = request_param
        self.save()
        service_logger.debug(EXEC_TIME_PRINT % ("logging response", time.time() - start_time))

    def _log_wfs_response_xml(self, xml: str):
        """ Evaluate the wfs response.

        For KML:
        KML specification can be found here:
        http://schemas.opengis.net/kml/

        Another informative page:
        https://developers.google.com/kml/documentation/kml_tut?hl=de#placemarks

        Args:
            xml (str): The response xml
        Returns:
             nothing
        """
        num_features = 0
        try:
            xml = xml_helper.parse_xml(xml)

            # Due to different versions of wfs, the member name changes. Since we do not know in which version the
            # GetFeature request was performed, we simply check on both possibilites and continue with the one that
            # delivers more features than 0. If no features are returned anyway, the value 0 will fit as well.
            identifiers = [
                "member",
                "featureMember",
            ]
            root = xml.getroot()

            num_features = -1
            for identifier in identifiers:
                feature_elems = xml_helper.try_get_element_from_xml(
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format(identifier),
                    root
                )
                num_features = len(feature_elems)
                if num_features > 0:
                    break

            if num_features == 0:
                # Special case:
                # There are services which do not follow the specification for WFS and wrap all their features in
                # <members> or <featureMembers> elements. So we have to check if there might be one of these identifiers
                # inside the response.
                identifiers = [
                    "members",
                    "featureMembers"
                ]
                for identifier in identifiers:
                    feature_elem = xml_helper.try_get_single_element_from_xml(
                        "//" + GENERIC_NAMESPACE_TEMPLATE.format(identifier),
                        root
                    )
                    if feature_elem is not None:
                        num_features = len(feature_elem.getchildren())
                        break
        except AttributeError:
            pass
        self.response_wfs_num_features = num_features

    def _log_wfs_response_csv(self, response: str):
        """ Evaluate the wfs response as csv.

        It's assumed, that the first line of a csv formatted wfs response contains the headlines
        of each column.
        All following lines are features.

        Args:
            response (str): The response csv
        Returns:
             nothing
        """
        response_maybe_csv = True

        # Make sure no non-csv has been returned as response
        # Check if we can create XML from it
        test_xml = xml_helper.parse_xml(response)
        if test_xml is not None:
            # This is not CSV! maybe an error message of the server
            response_maybe_csv = False

        try:
            test_json = json.loads(response)
            # If we can raise the ValueError, the response could be transformed into json -> no csv!
            raise ValueError
        except JSONDecodeError:
            # Could not create JSON -> might be regular csv
            pass
        except ValueError:
            # It is JSON, no csv
            response_maybe_csv = False

        # If csv is not supported by the responding server, we are not able to read csv values.
        # In this case, set the initial number of features to 0, since there are no features inside.
        num_features = 0
        if response_maybe_csv:
            # CSV responses might be wrongly encoded. So UTF-8 will fail and we need to try latin-1
            try:
                response = response.decode("utf-8")
            except UnicodeDecodeError:
                response = response.decode("latin-1")

            try:
                _input = io.StringIO(response)
                reader = csv.reader(_input, delimiter=",")

                # Set initial of num_features to -1 so we don't need to subtract the headline row afterwards
                num_features = -1
                for line in reader:
                    num_features += 1

            except Exception as e:
                pass

        self.response_wfs_num_features = num_features

    def _log_wfs_response_geojson(self, response: str):
        """ Evaluate the wfs response.

        Args:
            response (str): The response geojson
        Returns:
             nothing
        """
        # Initial is 0. It is possible, that the server does not support geojson. Then 0 features are delivered.
        num_features = 0
        try:
            response = json.loads(response)
            # If 'numberMatched' could not be found, we need to set an error value in here
            num_features = response.get("numberMatched", -1)
        except JSONDecodeError:
            pass

        self.response_wfs_num_features = num_features

    def _log_wfs_response_kml(self, response: str):
        """ Evaluate the wfs response.

        References:
            https://www.ogc.org/standards/kml
            https://developers.google.com/kml/documentation/kml_tut?hl=de#placemarks

        Args:
            response (str): The response kml
        Returns:
             nothing
        """
        num_features = 0
        try:
            xml = xml_helper.parse_xml(response)
            root = xml.getroot()

            # Count <Placemark> elements
            identifier = "Placemark"

            feature_elems = xml_helper.try_get_element_from_xml(
                "//" + GENERIC_NAMESPACE_TEMPLATE.format(identifier),
                root
            )
            num_features = len(feature_elems)
        except AttributeError as e:
            pass

        self.response_wfs_num_features = num_features

    def _log_wfs_response(self, response: str, output_format: str):
        """ Evaluate the wfs response.

        Args:
            xml (str): The response xml
            output_format (str): The output format of the response
        Returns:
             nothing
        """
        used_logable_format = None

        # Output_format might be None if no parameter was specified. We assume the default xml response in this case
        if output_format is not None:
            for _format in LOGABLE_FEATURE_RESPONSE_FORMATS:
                if _format in output_format.lower():
                    used_logable_format = _format
                    break

        if used_logable_format is None and output_format is None:
            # Default case - no outputformat parameter was given. We assume a xml representation
            self._log_wfs_response_xml(response)
        elif used_logable_format is None:
            raise ValueError(LOGGING_INVALID_OUTPUTFORMAT.format(",".join(LOGABLE_FEATURE_RESPONSE_FORMATS)))
        elif used_logable_format == "csv":
            self._log_wfs_response_csv(response)
        elif used_logable_format == "geojson":
            self._log_wfs_response_geojson(response)
        elif used_logable_format == "kml":
            self._log_wfs_response_kml(response)
        elif "gml" in used_logable_format:
            # Specifies the default gml xml response
            self._log_wfs_response_xml(response)
        else:
            # Should not happen!
            raise ValueError(PARAMETER_ERROR.format("outputformat"))

    def _log_wms_response(self, img):
        """ Evaluate the wms response.

        Args:
            img: The response image (probably masked)
        Returns:
             nothing
        """
        # Catch case where image might be bytes and transform it into a RGBA image
        if isinstance(img, bytes):
            img = Image.open(io.BytesIO(img))
            tmp = Image.new("RGBA", img.size, (255, 255, 255, 255))
            tmp.paste(img)
            img = tmp

        if COUNT_DATA_PIXELS_ONLY:
            pixels = self._count_data_pixels_only(img)
        else:
            h = img.height
            w = img.width
            pixels = h * w

        # Calculation of megapixels, round up to 2 digits
        # megapixels = width*height / 1,000,000
        self.response_wms_megapixel = round(pixels / 1000000, 4)

    def _count_data_pixels_only(self, img: Image):
        """ Counts all pixels, besides the pure-alpha-pixels

        Args:
            img (Image): The image
        Returns:
             pixels (int): Amount of non-alpha pixels
        """
        # Get alpha channel pixel values as list
        all_pixel_vals = list(img.getdata(3))

        # Count all alpha pixel (value == 0)
        num_alpha_pixels = all_pixel_vals.count(0)

        # Compute difference
        pixels = len(all_pixel_vals) - num_alpha_pixels

        return pixels


class RequestOperation(models.Model):
    operation_name = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.operation_name


class SecuredOperation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    operation = models.CharField(max_length=255, choices=OGCOperationEnum.as_choices(), null=True, blank=True)
    allowed_group = models.ForeignKey(MrMapGroup, related_name="allowed_operations", on_delete=models.CASCADE, null=True, blank=True)
    bounding_geometry = models.GeometryCollectionField(blank=True, null=True)
    secured_metadata = models.ForeignKey('Metadata', related_name="secured_operations", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return str(self.id)

    def delete(self, using=None, keep_parents=False):
        """ Overwrites builtin delete() method with model specific logic.

        If a SecuredOperation will be deleted, all related subelements of the secured_metadata have to be freed from
        existing SecuredOperation records as well.

        Args:
            using:
            keep_parents:
        Returns:

        """
        md = self.secured_metadata
        operation = self.operation
        group = self.allowed_group

        # continue with possibly existing children
        if md.is_metadata_type(MetadataEnum.FEATURETYPE):
            sec_ops = SecuredOperation.objects.filter(
                secured_metadata=md,
                operation=operation,
                allowed_group=group
            )
            sec_ops.delete()

        elif md.is_metadata_type(MetadataEnum.SERVICE) or md.is_metadata_type(MetadataEnum.LAYER):
            if md.is_service_type(OGCServiceEnum.WFS):
                # find all wfs featuretypes
                featuretypes = md.service.featuretypes.all()
                for featuretype in featuretypes:
                    sec_ops = SecuredOperation.objects.filter(
                        secured_metadata=featuretype.metadata,
                        operation=operation,
                        allowed_group=group,
                    )
                    sec_ops.delete()

            elif md.is_service_type(OGCServiceEnum.WMS):
                if md.service.is_root:
                    # find root layer
                    layer = Layer.objects.get(
                        parent_layer=None,
                        parent_service=md.service
                    )
                else:
                    # find layer which is described by this metadata
                    layer = Layer.objects.get(
                        metadata=md
                    )

                # remove root layer secured operation
                sec_op = SecuredOperation.objects.filter(
                    secured_metadata=layer.metadata,
                    operation=operation,
                    allowed_group=group
                )
                sec_op.delete()

                # remove secured operations of root layer children
                for child_layer in layer.child_layers.all():
                    sec_ops = SecuredOperation.objects.filter(
                        secured_metadata=child_layer.metadata,
                        operation=operation,
                        allowed_group=group,
                    )
                    sec_ops.delete()
                    child_layer.delete_children_secured_operations(child_layer, operation, group)

        # delete current object
        super().delete(using, keep_parents)


class MetadataRelation(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    metadata_to = models.ForeignKey('Metadata', on_delete=models.CASCADE)
    relation_type = models.CharField(max_length=255, null=True, blank=True, choices=MetadataRelationEnum.as_choices())
    internal = models.BooleanField(default=False)
    origin = models.CharField(max_length=255, choices=ResourceOriginEnum.as_choices(), null=True, blank=True)

    def __str__(self):
        return "{} {}".format(self.relation_type, self.metadata_to.title)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """ Overwrites default save function

        Saves the relation and stores information about relation in both related metadata records

        Args:
            force_insert: Default save parameter
            force_update: Default save parameter
            using: Default save parameter
            update_fields: Default save parameter
        Returns:

        """
        super().save(force_insert, force_update, using, update_fields)


class ExternalAuthentication(models.Model):
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=500)
    auth_type = models.CharField(max_length=100)
    metadata = models.OneToOneField('Metadata', on_delete=models.DO_NOTHING, null=True, blank=True, related_name="external_authentication")

    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete function

        Removes local stored file if it exists!

        Args;
            using:
            keep_parents:
        Returns:
        """
        # remove local stored key
        filepath = "{}/md_{}.key".format(EXTERNAL_AUTHENTICATION_FILEPATH, self.metadata.id)
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass
        super().delete(using, keep_parents)

    def encrypt(self, key: str):
        """ Encrypts the login credentials using a given key

        Args:
            key (str):
        Returns:

        """
        crypto_handler = CryptoHandler(msg=self.username, key=key)
        crypto_handler.encrypt()
        self.username = crypto_handler.crypt_message.decode("ascii")

        crypto_handler.message = self.password
        crypto_handler.encrypt()
        self.password = crypto_handler.crypt_message.decode("ascii")

    def decrypt(self, key):
        """ Decrypts the login credentials using a given key

        Args:
            key:
        Returns:

        """
        crypto_handler = CryptoHandler()
        crypto_handler.key = key

        crypto_handler.crypt_message = self.password.encode("ascii")
        crypto_handler.decrypt()
        self.password = crypto_handler.message.decode("ascii")

        crypto_handler.crypt_message = self.username.encode("ascii")
        crypto_handler.decrypt()
        self.username = crypto_handler.message.decode("ascii")


class Metadata(Resource):
    from MrMap.validators import validate_metadata_enum_choices
    identifier = models.CharField(max_length=1000, null=True)
    spatial_dataset_identifier_code = models.CharField(max_length=1000, null=True)
    spatial_dataset_identifier_namespace = models.CharField(max_length=1000, null=True)
    title = models.CharField(max_length=1000)
    abstract = models.TextField(null=True, blank=True)
    online_resource = models.CharField(max_length=1000, null=True, blank=True)  # where the service data can be found

    capabilities_original_uri = models.CharField(max_length=1000, blank=True, null=True)
    service_metadata_original_uri = models.CharField(max_length=1000, blank=True, null=True)
    additional_urls = models.ManyToManyField('GenericUrl', blank=True)

    contact = models.ForeignKey(Organization, on_delete=models.SET_NULL, blank=True, null=True)
    licence = models.ForeignKey('Licence', on_delete=models.SET_NULL, blank=True, null=True)
    access_constraints = models.TextField(null=True, blank=True)
    fees = models.TextField(null=True, blank=True)

    last_remote_change = models.DateTimeField(null=True, blank=True)  # the date time, when the metadata was changed where it comes from
    status = models.IntegerField(null=True, blank=True)
    use_proxy_uri = models.BooleanField(default=False)
    log_proxy_access = models.BooleanField(default=False)
    spatial_res_type = models.CharField(max_length=100,
                                        null=True,
                                        blank=True,
                                        choices=SpatialResolutionTypesEnum.as_choices(),
                                        validators=[validate_spatial_resolution_types_enum_choices])
    spatial_res_value = models.CharField(max_length=100, null=True, blank=True)
    is_broken = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)
    is_inspire_conform = models.BooleanField(default=False)
    has_inspire_downloads = models.BooleanField(default=False)
    bounding_geometry = models.MultiPolygonField(default=DEFAULT_MULTIPOLYGON_EMPTY)
    bounding_box = models.PolygonField(default=DEFAULT_POLYGON_EMPTY)
    # security
    is_secured = models.BooleanField(default=False)

    # capabilities
    authority_url = models.CharField(max_length=255, null=True, blank=True)
    metadata_url = models.CharField(max_length=255, null=True, blank=True)

    # other
    keywords = models.ManyToManyField(Keyword)
    formats = models.ManyToManyField('MimeType', blank=True)
    categories = models.ManyToManyField('Category', blank=True)
    reference_system = models.ManyToManyField('ReferenceSystem', blank=True)
    dimensions = models.ManyToManyField('Dimension', blank=True)
    metadata_type = models.CharField(max_length=500, null=True, blank=True, choices=MetadataEnum.as_choices(), validators=[validate_metadata_enum_choices])
    legal_dates = models.ManyToManyField('LegalDate', blank=True)
    legal_reports = models.ManyToManyField('LegalReport', blank=True)
    hits = models.IntegerField(default=0)

    # Related metadata creates Relations between metadata records by using the MetadataRelation table.
    # Each MetadataRelation record might hold further information about the relation, e.g. 'describedBy', ...
    related_metadata = models.ManyToManyField(MetadataRelation, blank=True)
    language_code = models.CharField(max_length=100, choices=ISO_19115_LANG_CHOICES, default=DEFAULT_MD_LANGUAGE)
    origin = None

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "id",
                    "public_id",
                    "identifier"
                ]
            )
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.keywords_list = []
        self.reference_system_list = []
        self.dimension_list = []
        self.formats_list = []
        self.categories_list = []

    def __str__(self):
        return "{} ({}) #{}".format(self.title, self.metadata_type, self.id)

    def get_current_operations_url(self):
        """ Returns the current operations url

        If use_proxy_uri flag is True, we return the Mr. Map operations url.
        Else we just return the original operations url

        """
        if self.use_proxy_uri:
            return f"{ROOT_URL}{reverse('resource:metadata-proxy-operation', args=(self.id, ))}?"
        else:
            return self.online_resource

    def get_formats(self, filter: dict = {}):
        """ Returns supported formats/MimeTypes.

        If the metadata record itself does not hold any format information, the parent metadata will be requested.

        Args:
            filter (dict): Prefilter
        Returns:
             QuerySet
        """
        if self.is_root() or self.formats.all().count() != 0:
            formats = self.formats.filter(**filter)
        else:
            try:
                formats = self.service.parent_service.metadata.formats.filter(**filter)
            except Exception:
                formats = MimeType.objects.none()
        return formats

    @property
    def capabilities_uri(self):
        """ Creates the capabilities uri for this metadata record

        Returns:
             capabilities_uri (str)
        """
        p_id = self.public_id or self.id
        return "{}{}{}".format(
            ROOT_URL,
            reverse("resource:metadata-proxy-operation", args=(str(p_id),)),
            "?request={}".format(OGCOperationEnum.GET_CAPABILITIES.value),
        ) if not self.is_dataset_metadata else None

    @property
    def service_metadata_uri(self):
        """ Creates the metadata uri for this metadata record

        Returns:
             metadata_uri (str)
        """
        p_id = self.public_id or self.id
        if not self.is_dataset_metadata:
            url_name = reverse("resource:get-service-metadata", args=(str(p_id),))
        else:
            url_name = reverse("resource:get-dataset-metadata", args=(str(p_id),))
        return "{}{}".format(ROOT_URL, url_name)

    @property
    def html_metadata_uri(self):
        """ Creates the html view uri for this metadata record

        Returns:
             metadata_uri (str)
        """
        p_id = self.public_id or self.id
        url_name = reverse("resource:get-metadata-html", args=(str(p_id),))
        return "{}{}".format(ROOT_URL, url_name)

    @property
    def is_service_metadata(self):
        """ Returns whether the metadata record describes this type of data

        Returns:
             True|False
        """
        return self.is_metadata_type(MetadataEnum.SERVICE)

    @property
    def is_layer_metadata(self):
        """ Returns whether the metadata record describes this type of data

        Returns:
             True|False
        """
        return self.is_metadata_type(MetadataEnum.LAYER)

    @property
    def is_featuretype_metadata(self):
        """ Returns whether the metadata record describes this type of data

        Returns:
             True|False
        """
        return self.is_metadata_type(MetadataEnum.FEATURETYPE)

    @property
    def is_dataset_metadata(self):
        """ Returns whether the metadata record describes this type of data

        Returns:
             True|False
        """
        return self.is_metadata_type(MetadataEnum.DATASET)

    @property
    def is_catalogue_metadata(self):
        """ Returns whether the metadata record describes this type of data

        Returns:
             True|False
        """
        return self.is_metadata_type(MetadataEnum.CATALOGUE)

    def is_metadata_type(self, enum: MetadataEnum):
        """ Returns whether the metadata is of this MetadataEnum

        Args:
            enum (MetadataEnum): The enum
        Returns:
             True if the metadata_type is equal, false otherwise
        """
        return self.metadata_type == enum.value

    def is_service_type(self, enum: OGCServiceEnum):
        """ Returns whether the described service element of this metadata is of the given OGCServiceEnum

        Args:
            enum (MetadataEnum): The enum
        Returns:
             True|False
        """
        return self.get_service_type() == enum.value

    def get_described_element(self):
        """ Simple getter to return the 'real' described element.

        Described elements are .service, .layer or .featuretype. Instead of doing these if-else checks
        over and over again, this function directly returns the appropriate element.

        Returns:

        """
        ret_val = None
        if self.is_service_metadata:
            ret_val = self.service
        elif self.is_layer_metadata:
            ret_val = Layer.objects.get(
                metadata=self
            )
        elif self.is_featuretype_metadata:
            ret_val = self.featuretype
        return ret_val

    def clear_upper_element_capabilities(self, clear_self_too=False):
        """ Removes current_capability_document from upper element Document records.

        This forces the documents to be regenerated on the next call

        Returns:

        """
        # Only important for Layer instances, since there is no hierarchy in WFS
        if self.metadata_type != MetadataEnum.LAYER.value:
            return

        # Find all upper layers/elements
        layer = Layer.objects.get(metadata=self)

        upper_elements = layer.get_upper_layers()
        upper_elements_metadatas = [elem.metadata for elem in upper_elements]

        if clear_self_too:
            upper_elements_metadatas.append(self)

        # Set document records value to None
        upper_elements_docs = Document.objects.filter(
            metadata__in=upper_elements_metadatas
        )
        for doc in upper_elements_docs:
            doc.content = None
            doc.save()

        for md in upper_elements_metadatas:
            md.clear_cached_documents()

    def clear_cached_documents(self):
        """ Sets the content of all possibly auto-generated documents to None

        Returns:

        """
        self._clear_current_capability_document()
        self._clear_service_metadata_document()

    def _clear_service_metadata_document(self):
        """ Sets the service_metadata_document content to None

        Returns:

        """
        # Clear cached documents
        cacher = DocumentCacher("SERVICE_METADATA", "0")
        cacher.remove(str(self.id))

    def _clear_current_capability_document(self):
        """ Sets the current_capability_document content to None

        Returns:

        """
        # Clear cached documents
        for version in OGCServiceVersionEnum:
            cacher = DocumentCacher(OGCOperationEnum.GET_CAPABILITIES.value, version.value)
            cacher.remove(str(self.id))

    def get_subelements_metadatas(self):
        """ Returns a list containing all subelement metadata records


        Returns:
             ret_list (list)
        """
        is_service = self.is_metadata_type(MetadataEnum.SERVICE)
        is_layer = self.is_metadata_type(MetadataEnum.LAYER)

        ret_list = []
        if is_service or is_layer:
            ret_list += [elem.metadata for elem in self.service.subelements]
        else:
            subelement_metadatas = Metadata.objects.filter(
                service__parent_service__metadata=self,
            )
            ret_list += list(subelement_metadatas)

        return ret_list

    def get_root_metadata(self):
        """ Returns the root metadata of the current metadata if there is one.

        Returns the same metadata otherwise


        Returns:
             ret_list (list)
        """
        if self.service.parent_service is not None:
            root_md = self.service.parent_service.metadata
        else:
            root_md = self

        return root_md

    def get_service_metadata_xml(self):
        """ Getter for the service metadata.

        If no service metadata is persisted in the database, we generate one.

        Returns:
            doc (str): The xml document
        """
        from service.helper.iso.iso_19115_metadata_builder import Iso19115MetadataBuilder
        doc = None
        cacher = DocumentCacher(title="SERVICE_METADATA", version="0")
        try:
            # Before we access the database (slow), we try to find a cached document from redis (memory -> faster)
            doc = cacher.get(self.id)
            if doc is not None:
                return doc

            # If we reach this point, we found no cached document. Check the db!
            # Try to fetch an existing Document record from the db
            cap_doc = Document.objects.get(
                metadata=self,
                document_type=DocumentEnum.METADATA.value,
            )
            doc = cap_doc.content

            # There is a capability_document in the db. Let's write it to cache, so it can be returned even faster
            cacher.set(self.id, doc)

        except ObjectDoesNotExist as e:
            # There is no service metadata document in the database, we need to create it
            builder = Iso19115MetadataBuilder(self.id, MetadataEnum.SERVICE)
            doc = builder.generate_service_metadata()

            # Write new creates service metadata to cache
            cacher.set(str(self.id), doc)

            # Write metadata to db as well
            cap_doc = Document.objects.get_or_create(
                metadata=self,
                document_type=DocumentEnum.METADATA.value,
                is_original=False,
            )[0]
            cap_doc.is_active = self.is_active
            cap_doc.content = doc.decode("UTF-8")
            cap_doc.save()

        return doc

    def get_current_capability_xml(self, version_param: str):
        """ Getter for the capability xml of the current status of this metadata object.

        If there is no capability document available (maybe the capabilities of a subelement of a service are requested),
        the capabilities xml will be generated and persisted to the database to increase the speed of another request.

        Args:
            version_param (str): The version parameter for which the capabilities shall be built
        Returns:
            current_capability_document (str): The xml document
        """
        from service.helper import service_helper
        cap_doc = None

        cacher = DocumentCacher(title=OGCOperationEnum.GET_CAPABILITIES.value, version=version_param)
        try:
            # Before we access the database (slow), we try to find a cached document from redis (memory -> faster)
            cap_xml = cacher.get(self.id)
            if cap_xml is not None:
                return cap_xml

            # If we reach this point, we found no cached document. Check the db!
            # Try to fetch an existing Document record from the db
            cap_doc = Document.objects.get(
                metadata=self,
                document_type=DocumentEnum.CAPABILITY.value,
                is_original=False,
            )

            cap_xml = cap_doc.content
            # There is content in the db. Let's write it to cache, so it can be returned even faster
            cacher.set(self.id, cap_xml)

        except ObjectDoesNotExist as e:
            # This means we have no Document record or the current_capability value is None.
            # This is possible for subelements of a service, which (usually) do not have an own capability document or
            # if a service has been updated.

            # We create a capability document on the fly for this metadata object and use the set_proxy functionality
            # of the Document class for automatically setting all proxied links according to the user's setting.
            cap_xml = self._create_capability_xml(version_param)

            # Write the new capability document to the cache!
            cacher.set(self.id, cap_xml)

            # If no Document record existed, we create it now!
            cap_doc = Document.objects.get_or_create(
                metadata=self,
                document_type=DocumentEnum.CAPABILITY.value,
                is_original=False,
            )[0]
            cap_doc.is_active = self.is_active
            cap_doc.content = cap_xml

            # Do not forget to proxy the links inside the document, if needed
            if self.use_proxy_uri:
                version_param_enum = service_helper.resolve_version_enum(version=version_param)
                cap_doc.set_proxy(use_proxy=True, force_version=version_param_enum, auto_save=False)

            cap_doc.save()

        return cap_doc.content

    def _create_capability_xml(self, force_version: str = None):
        """ Creates a capability xml from the current state of the service object

        Args:
            force_version (str): The OGC standard version that has to be used for xml generating
        Returns:
             xml (str): The xml document as string
        """
        from service.helper.ogc.capabilities_builder import CapabilityXMLBuilder

        capabilty_builder = CapabilityXMLBuilder(metadata=self, force_version=force_version)
        xml = capabilty_builder.generate_xml()
        return xml

    def get_external_authentication_object(self):
        """ Returns the external authentication object, if one exists

        If none exists, None will be returned

        Returns:
             ext_auth (ExternalAuthentication) | None
        """
        ext_auth = None
        try:
            ext_auth = self.external_authentication
        except ObjectDoesNotExist:
            pass
        return ext_auth

    def get_related_dataset_metadata(self):
        """ Returns a related dataset metadata record.

        If none exists, None is returned

        Returns:
             dataset_md (Metadata) | None
        """
        try:
            dataset_md = self.related_metadata.get(
                metadata_to__metadata_type=OGCServiceEnum.DATASET.value
            )
            dataset_md = dataset_md.metadata_to
            return dataset_md
        except ObjectDoesNotExist:
            return None

    def get_remote_original_capabilities_document(self, version: str):
        """ Fetches the original capabilities document from the remote server.

        Returns:
             doc (str): The xml document as string
        """
        if version is None or len(version) == 0:
            raise ValueError()

        doc = None
        if self.has_external_authentication:
            ext_auth = self.external_authentication
            crypto_handler = CryptoHandler()
            key = crypto_handler.get_key_from_file(self.id)
            ext_auth.decrypt(key)
        else:
            ext_auth = None

        uri = self.capabilities_original_uri
        uri = utils.set_uri_GET_param(uri, "version", version)
        conn = CommonConnector(url=uri, external_auth=ext_auth)
        conn.load()
        if conn.status_code == 200:
            doc = conn.content
        else:
            raise ConnectionError()
        return doc

    @property
    def has_external_authentication(self):
        """ Checks whether the metadata has a related ExternalAuthentication set

        Returns:
             True | False
        """
        try:
            tmp = self.external_authentication
            return True
        except ObjectDoesNotExist:
            return False

    @transaction.atomic
    def increase_hits(self):
        """ Increases the hit counter of the metadata

        Returns:
             Nothing
        """
        # increase itself
        self.hits += 1

        # Only if whole service was called, increase the children hits as well
        if self.is_metadata_type(MetadataEnum.SERVICE):

            # wms children
            if self.service.is_service_type(OGCServiceEnum.WMS):
                children = self.service.child_service.all()
                for child in children:
                    child.metadata.hits += 1
                    child.metadata.save()

            elif self.service.is_service_type(OGCServiceEnum.WFS):
                featuretypes = self.service.featuretypes.all()
                for f_t in featuretypes:
                    f_t.metadata.hits += 1
                    f_t.metadata.save()

        self.save()

    def generate_public_id(self, stump: str = None):
        """ Generates a public_id for a Metadata entry.

        If no stump was provided, the title attribute will be used as stump.

        Args:
            stump (str): The base string input, which will be incremented if already taken
        Returns:
             public_id (str): The generated public id
        """
        if stump is None:
            stump = "{} {}".format(self.title, self.metadata_type)

        slug_stump = slugify(stump)
        # To prevent too long public ids (keep them < 255 character)
        # we need to make sure the stump itself isn't longer than 200 characters! So we have enough space left for numbers in the end
        slug_stump = slug_stump[:225]
        exists = Metadata.objects.filter(
            public_id=slug_stump
        ).exists()
        public_id = slug_stump

        counter = 1
        while exists:
            public_id = "{}-{}".format(slug_stump, counter)
            counter += 1
            exists = Metadata.objects.filter(
                public_id=public_id
            ).exists()
        return public_id

    def save(self, add_monitoring: bool = True, *args, **kwargs):
        """ Overwriting the regular save function

        Calls the regular save function without any changes and adds the created/updated
        Metadata object to the MonitoringSetting.

        Passes all args and kwargs to the regular save function.

        Returns:
            nothing
        """
        super().save(*args, **kwargs)

        # Add created/updated object to the MonitoringSettings. Django does not add
        # the same instance twice, so we do not have to check for updating specifically.
        # NOTE: Since we do not have a clear handling for which setting to use, always use first (default) setting.
        if add_monitoring:
            monitoring_setting = MonitoringSetting.objects.first()
            if monitoring_setting is not None:
                monitoring_setting.metadatas.add(self)
                monitoring_setting.save()

    def delete(self, using=None, keep_parents=False, force=False):
        """ Overwriting of the regular delete function

        Checks if the current processed metadata is part of a MetadataRelation, which indicates, that it is still used
        somewhere else, maybe by another service. If there is only one MetadataRelation found for this metadata record,
        we can delete it safely..

        Args:
            using: The regular 'using' parameter
            keep_parents: The regular 'keep_parents' parameter
            force: Forces the deletion in any case
        Returns:
            nothing
        """
        # check for SecuredOperations
        if self.is_secured:
            sec_ops = self.secured_operations.all()
            sec_ops.delete()

        # remove externalAuthentication object if it exists
        try:
            self.external_authentication.delete()
        except ObjectDoesNotExist:
            pass

        # Remove GenricUrls if they are not used anywhere else!
        urls = self.additional_urls.all()
        for url in urls:
            other_dependencies = Metadata.objects.filter(
                additional_urls=url
            ).exclude(
                id=self.id
            ).exists()
            if not other_dependencies:
                url.delete()

        # check if there are MetadataRelations to(!) this metadata record
        # if so, we can not remove it until these relations aren't used anymore
        dependencies = MetadataRelation.objects.filter(
            metadata_to=self
        )
        if dependencies.count() > 1 and force is False:
            # if there are more than one dependency, we should not remove it
            # the one dependency we can expect at least is the relation to the current metadata record
            return
        else:
            # Remove all relations from(!) this metadata as well
            md_rels = self.related_metadata.all()
            md_rels.delete()
            # if we have one or less relations to this metadata record, we can remove it anyway
            super().delete(using, keep_parents)

    def get_service_type(self):
        """ Performs a check on which service type is described by the metadata record

        Returns:
             service_type (str): The service type as string ('wms' or 'wfs')
        """
        service_type = None
        if self.is_root():
            return self.service.service_type.name
        elif self.is_metadata_type(MetadataEnum.LAYER):
            service_type = OGCServiceEnum.WMS.value
        elif self.is_metadata_type(MetadataEnum.FEATURETYPE):
            service_type = OGCServiceEnum.WFS.value
        return service_type

    def get_service_version(self) -> OGCServiceEnum:
        """ Returns the service version

        Returns:
             The service version
        """
        # Non root elements have to be handled differently, since FeatureTypes are not Service instances and always use
        # their parent_service as Service information holder
        if not self.is_root():
            if self.is_service_type(OGCServiceEnum.WFS):
                service = FeatureType.objects.get(
                    metadata=self
                ).parent_service
            elif self.is_service_type(OGCServiceEnum.WMS):
                service = self.service.parent_service
            else:
                raise TypeError(PARAMETER_ERROR.format("SERVICE"))
        else:
            service = self.service
        service_version = service.service_type.version
        for v in OGCServiceVersionEnum:
            if v.value == service_version or v.name == service_version:
                return v
        return service_version

    def find_max_bounding_box(self):
        """ Returns the largest bounding box of all children

        Returns:

        """
        if self.metadata_type == MetadataEnum.SERVICE.value:
            if self.service.service_type.name == OGCServiceEnum.WMS.value:
                children = Layer.objects.filter(
                    parent_service__metadata=self
                )
            elif self.service.service_type.name == OGCServiceEnum.WFS.value:
                children = FeatureType.objects.filter(
                    parent_service__metadata=self
                )
        elif self.metadata_type == MetadataEnum.LAYER.value:
            children = Layer.objects.filter(
                parent_layer__metadata=self
            )
        else:
            return DEFAULT_SERVICE_BOUNDING_BOX

        try:
            children_bboxes = {child.bbox_lat_lon.area: child.bbox_lat_lon for child in children}
            max_box = children_bboxes.get(max(children_bboxes), None)
        except ValueError:
            # happens in max() on empty iterables
            max_box = None

        if max_box is None:
            max_box = DEFAULT_SERVICE_BOUNDING_BOX
        if max_box.area == 0:
            # if this element and it's children does not provide a bounding geometry, we simply take the one from the
            # whole service to avoid the map flipping somewhere else on the planet
            return self.service.parent_service.metadata.find_max_bounding_box()
        return max_box

    def is_root(self):
        """ Checks whether the metadata describes a root service or a layer/featuretype

        Returns:
             is_root (bool): True if there is no parent service to the described service, False otherwise
        """
        is_root = [
            self.is_metadata_type(MetadataEnum.SERVICE),
            self.is_metadata_type(MetadataEnum.CATALOGUE)
        ]
        return True in is_root

    def _restore_layer_md(self, service,):
        """ Private function for retrieving single layer metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
        Returns:
             nothing, it changes the Metadata object itself
        """
        # parse single layer
        identifier = self.service.layer.identifier
        layer = service.get_layer_by_identifier(identifier)
        self.title = layer.title
        self.abstract = layer.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in layer.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        original_iso_links = [x.uri for x in layer.iso_metadata]
        for related_iso in self.related_metadata.all():
            md_link = related_iso.metadata_to.metadata_url
            if md_link not in original_iso_links:
                related_iso.metadata_to.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.service.parent_service.metadata
        cap_doc = Document.objects.get(
            metadata=rel_md
        )
        cap_doc.restore_subelement(identifier)

    def _restore_feature_type_md(self, service, external_auth: ExternalAuthentication = None):
        """ Private function for retrieving single featuretype metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
        Returns:
             nothing, it changes the Metadata object itself
        """
        # parse single layer
        identifier = self.identifier
        f_t = service.get_feature_type_by_identifier(identifier, external_auth=external_auth)
        f_t_obj = f_t.get("feature_type", None)
        f_t_iso_links = f_t.get("dataset_md_list", [])
        self.title = f_t_obj.metadata.title
        self.abstract = f_t_obj.metadata.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in f_t_obj.metadata.keywords_list:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        for related_iso in self.related_metadata.all():
            md_link = related_iso.metadata_to.metadata_url
            if md_link not in f_t_iso_links:
                related_iso.metadata_to.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.featuretype.parent_service.metadata
        cap_doc = Document.objects.get(
            metadata=rel_md
        )
        cap_doc.restore_subelement(identifier)

    def _restore_wms(self, external_auth: ExternalAuthentication = None):
        """ Restore the metadata of a wms service

        Args;
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
        from service.helper.ogc.wms import OGCWebMapServiceFactory
        from service.helper import service_helper
        service_version = service_helper.resolve_version_enum(self.service.service_type.version)
        service = None
        service = OGCWebMapServiceFactory()
        service = service.get_ogc_wms(version=service_version, service_connect_url=self.capabilities_original_uri)
        service.get_capabilities()
        service.create_from_capabilities(metadata_only=True, external_auth=external_auth)

        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_layer_md(service)

        self.title = service.service_identification_title
        self.abstract = service.service_identification_abstract
        self.access_constraints = service.service_identification_accessconstraints
        keywords = service.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False

        try:
            cap_doc = Document.objects.get(
                metadata=self,
                document_type=DocumentEnum.CAPABILITY.value,
                is_original=False,
            )
            cap_doc.restore()
        except ObjectDoesNotExist:
            service_logger.error(
                "Restoring of metadata {} didn't find any capability document!".format(self.id)
            )

    def _restore_wfs(self, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Restore the metadata of a wfs service

        Args;
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper

        # Prepare 'service' for further handling
        # If no identifier is provided, we deal with a root metadata
        is_root = identifier is None
        if is_root:
            service = self.service
        else:
            service = self.featuretype.service
        service_version = service_helper.resolve_version_enum(service.service_type.version)
        service_tmp = OGCWebFeatureServiceFactory()
        service_tmp = service_tmp.get_ogc_wfs(version=service_version, service_connect_url=self.capabilities_original_uri)
        if service_tmp is None:
            return
        service_tmp.get_capabilities()
        service_tmp.create_from_capabilities(metadata_only=True)
        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_feature_type_md(service_tmp, external_auth=external_auth)

        self.title = service_tmp.service_identification_title
        self.abstract = service_tmp.service_identification_abstract
        self.access_constraints = service_tmp.service_identification_accessconstraints
        keywords = service_tmp.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False

        try:
            cap_doc = Document.objects.get(
                metadata=service.metadata
            )
            cap_doc.restore()
        except ObjectDoesNotExist:
            service_logger.error(
                "Restoring of metadata {} didn't find any capability document!".format(self.id)
            )

    def _restore_dataset_md(self, ):
        """ Private function for restoring dataset metadata

        Args:

        Returns:
             nothing, it changes the Metadata object itself
        """
        from service.helper.iso.iso_19115_metadata_parser import ISOMetadata
        original_metadata_document = ISOMetadata(uri=str(self.metadata_url), origin=ResourceOriginEnum.CAPABILITIES.value)
        self.abstract = original_metadata_document.abstract
        self.title = original_metadata_document.title

        self.contact = Organization.objects.get_or_create(
            organization_name=original_metadata_document.responsible_party,
            email=original_metadata_document.contact_email,
            person_name=original_metadata_document.contact_person,
            phone=original_metadata_document.contact_phone
        )[0]

        self.language_code = original_metadata_document.language

        if original_metadata_document.bounding_geometry:
            self.bounding_geometry = original_metadata_document.bounding_geometry
        else:
            self.bounding_geometry = Polygon([0.0, 0.0, 0.0, 0.0], srid=DEFAULT_SRS)

        self.bounding_box = original_metadata_document.bounding_box

        keyword_list = []
        for keyword in original_metadata_document.keywords:
            keyword_list.append(Keyword.objects.get_or_create(keyword=keyword)[0])
        self.keywords.set(keyword_list)

        category_list = []
        for cat in original_metadata_document.iso_categories:
            try:
                category_list.append(Category.objects.get(title_EN=cat))
            except ObjectDoesNotExist:
                pass
        self.categories.set(category_list)

        self.reference_system.clear()

        self.dataset.lineage_statement = original_metadata_document.lineage
        self.dataset.character_set_code = original_metadata_document.character_set_code

        try:
            doc = Document.objects.get(
                metadata=self,
                document_type=DocumentEnum.METADATA.value,
                is_original=False,)

            doc.content = Document.objects.get(
                metadata=self,
                document_type=DocumentEnum.METADATA.value,
                is_original=True,).content
            doc.save()
        except ObjectDoesNotExist:
            service_logger.error(
                "Restoring of metadata {} didn't find any capability document!".format(self.id)
            )

    def restore(self, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Load original metadata from capabilities and ISO metadata

        Args:
            identifier (str): The identifier of a featureType or Layer (in xml often named 'name')
            external_auth (ExternalAuthentication):
        Returns:
             nothing
        """
        # catch dataset
        if self.is_dataset_metadata:
            self._restore_dataset_md()

        # identify whether this is a wfs or wms (we need to handle them in different ways)
        if self.is_service_type(OGCServiceEnum.WFS):
            self._restore_wfs(identifier, external_auth=external_auth)
        elif self.is_service_type(OGCServiceEnum.WMS):
            self._restore_wms(external_auth=external_auth)

        # Subelements like layers or featuretypes might have own capabilities documents. Delete them on restore!
        self.clear_cached_documents()

    def get_related_metadata_uris(self):
        """ Generates a list of all related metadata online links and returns them

        Returns:
             links (list): A list containing all online links of related metadata
        """
        rel_mds = self.related_metadata.all()
        links = []
        for md in rel_mds:
            links.append(md.metadata_to.metadata_url)
        return links

    def _set_document_secured(self, is_secured: bool):
        """ Fetches the metadata documents and sets the secured uris for all operations

        Args:
            is_secured (bool): Whether the operations should be secured or not
        Returns:
            nothing
        """
        try:
            cap_doc = Document.objects.get(
                metadata=self,
                document_type=DocumentEnum.CAPABILITY.value,
                is_original=False,
            )
            cap_doc.set_proxy(is_secured)
        except ObjectDoesNotExist:
            pass

    def set_documents_active_status(self, is_active: bool):
        """ Sets the active status for related documents

        Args:
            is_active (bool): Whether the documents are active or not
        Returns:

        """
        docs = Document.objects.filter(
            metadata=self
        )
        for doc in docs:
            doc.is_active = is_active
            doc.save()

    def set_logging(self, logging: bool):
        """ Set the metadata logging flag to a new value

        Args:
            logging (bool): Whether the metadata shall be logged or not
        Returns:
        """
        # Only change if the proxy setting is activated or the logging shall be deactivated anyway
        if self.use_proxy_uri or not logging:
            self.log_proxy_access = logging

            # If the metadata shall be logged, all of it's subelements shall be logged as well!
            child_mds = Metadata.objects.filter(service__parent_service=self.service)
            for child_md in child_mds:
                child_md.log_proxy_access = logging
                child_md.save()

            self.save()

    def set_proxy(self, use_proxy: bool):
        """ Set the metadata proxy to a new value.

        Iterates over subelements.

        Args:
            use_proxy (bool): Whether to use a proxy or not
        Returns:
        """
        if not self.is_root():
            root_md = self.service.parent_service.metadata
        else:
            root_md = self

        # change capabilities document if there is one (subelements may not have any documents yet)
        try:
            self.get_current_capability_xml(self.service.service_type.version)
            root_md_doc = Document.objects.get_or_create(
                metadata=root_md,
                document_type=DocumentEnum.CAPABILITY.value,
                is_original=False
            )[0]

            if root_md_doc.content is None:
                # There is no content yet inside - we take it from the original one
                orig_doc = Document.objects.get(
                    metadata=root_md,
                    document_type=DocumentEnum.CAPABILITY.value,
                    is_original=True
                )
                root_md_doc.content = orig_doc.content
                root_md_doc.is_active = orig_doc.is_active

            root_md_doc.set_proxy(use_proxy)
        except ObjectDoesNotExist:
            pass

        # Clear cached documents
        self.clear_cached_documents()

        self.use_proxy_uri = use_proxy

        # If md uris shall be tunneled using the proxy, we need to make sure that all children are aware of this!
        subelements_mds = [element.metadata for element in self.service.subelements]
        for subelement_md in subelements_mds:
            subelement_md.use_proxy_uri = self.use_proxy_uri
            try:
                # If there exists already a capabilities document for a subelement, we need to change the links there as well
                subelement_md_doc = Document.objects.get(
                    metadata=subelement_md,
                    document_type=DocumentEnum.CAPABILITY.value,
                    is_original=False
                )
                if subelement_md_doc.content is not None:
                    subelement_md_doc.set_proxy(use_proxy)
            except ObjectDoesNotExist:
                pass
            subelement_md.save()
            subelement_md.clear_cached_documents()

        self.save()

    def set_secured(self, is_secured: bool):
        """ Set is_secured to a new value.

        Iterates over all children for the same purpose.
        Activates use_proxy automatically!

        Args:
            is_secured (bool): The new value for is_secured
        Returns:

        """
        self.is_secured = is_secured
        if not is_secured and self.use_proxy_uri:
            # secured access shall be disabled, but use_proxy is still enabled
            # we keep the use_proxy_uri on True!
            self.use_proxy_uri = True
        else:
            self.use_proxy_uri = is_secured
        self._set_document_secured(self.use_proxy_uri)

        children = []
        if self.is_metadata_type(MetadataEnum.SERVICE) or self.is_metadata_type(MetadataEnum.LAYER):
            if self.service.is_service_type(OGCServiceEnum.WMS):
                parent_service = self.service
                children = Metadata.objects.filter(
                    service__parent_service=parent_service
                )
                for child in children:
                    child._set_document_secured(self.use_proxy_uri)

            elif self.service.is_service_type(OGCServiceEnum.WFS):
                children = [ft.metadata for ft in self.service.featuretypes.all()]

            for child in children:
                child.is_secured = is_secured
                child.use_proxy_uri = self.use_proxy_uri
                child.save()

        elif self.is_metadata_type(MetadataEnum.FEATURETYPE):
            # a featuretype does not have children - we can skip this case!
            pass
        self.save()

    def inform_subscriptors(self):
        """ Iterates over all related subscriptions and triggers the inform_subscriptor() method

        Returns:

        """
        from users.models import Subscription
        subscriptions = Subscription.objects.filter(
            metadata=self
        )
        for sub in subscriptions:
            sub.inform_subscriptor()

    def get_health_state(self, monitoring_run: MonitoringRun = None, ):
        """ Returns the last health state of the metadata object by default.

        Returns: the health state or None if no Monitoring results where found

        """
        from monitoring.models import HealthState
        if monitoring_run:
            health_state = HealthState.objects.get(metadata=self, monitoring_run=monitoring_run, )
            return health_state
        else:
            health_state = HealthState.objects.filter(metadata=self, ).order_by('-monitoring_run__end').first()
            return health_state

    def get_health_states(self, last_x_items: int = 10):
        """ Returns the last 10 health states of the metadata object by default.

        Returns:

        """
        from monitoring.models import HealthState
        health_states = HealthState.objects.filter(metadata=self, ).order_by('-monitoring_run__end')[:last_x_items]
        return health_states


class Document(Resource):
    from MrMap.validators import validate_document_enum_choices
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=255, null=True, choices=DocumentEnum.as_choices(), validators=[validate_document_enum_choices])
    content = models.TextField(null=True, blank=True)
    is_original = models.BooleanField(default=False)

    def __str__(self):
        return self.metadata.title

    def get_dataset_metadata_as_dict(self):
        """ Parses the persisted dataset_metadata_document into a dict

        Parses only values which are important for the HTML representation rendering.
        Useful resource: https://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml

        Returns:
             ret_dict (dict): The dict
        """
        ret_dict = {}

        if self.content is None:
            return ret_dict

        xml = xml_helper.parse_xml(self.content)

        # Date
        date_elem = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("dateStamp"), xml)
        ret_dict["date"] = xml_helper.try_get_text_from_xml_element(date_elem, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Date"))
        del date_elem

        # Organization
        org_elem = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("organisationName"), xml)
        ret_dict["organization_name"] = xml_helper.try_get_text_from_xml_element(org_elem, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString"))
        del org_elem

        # Language
        ret_dict["language"] = xml_helper.try_get_text_from_xml_element(xml, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode"))

        # Topic category
        ret_dict["topic_category"] = xml_helper.try_get_text_from_xml_element(xml, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_TopicCategoryCode"))

        # Keywords
        keyword_elems = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("keyword"), xml)
        keywords = [xml_helper.try_get_text_from_xml_element(elem, ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")) for elem in keyword_elems]
        ret_dict["keywords"] = keywords
        del keyword_elems
        del keywords

        # Spatial reference systems
        srs_elems = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("RS_Identifier"),
            xml
        )
        reference_systems = [xml_helper.try_get_text_from_xml_element(
            elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("code") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        ) for elem in srs_elems]
        ret_dict["reference_systems"] = reference_systems
        del srs_elems
        del reference_systems

        # Extent coordinates
        extent_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("EX_GeographicBoundingBox"),
            xml
        )
        extent_coords = [xml_helper.try_get_text_from_xml_element(
            elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
        ) for elem in extent_elem.getchildren()]
        # Switch coords[1] and coords[2] to match the common order of minx,miny,maxx,maxy
        tmp = extent_coords[1]
        extent_coords[1] = extent_coords[2]
        extent_coords[2] = tmp
        ret_dict["extent_coords"] = extent_coords
        del extent_elem
        del extent_coords
        del tmp

        # Temporal extent
        temporal_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("EX_TemporalExtent"),
            xml
        )
        ret_dict["temporal_extent_begin"] =  xml_helper.try_get_text_from_xml_element(
            temporal_elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("beginPosition")
        )
        ret_dict["temporal_extent_end"] =  xml_helper.try_get_text_from_xml_element(
            temporal_elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("endPosition")
        )
        del temporal_elem

        # Date of creation|revision|publication
        date_additionals = OrderedDict({
            "creation": [],
            "revision": [],
            "publication": [],
        })
        md_elem = xml_helper.try_get_single_element_from_xml(
            ".//"  + GENERIC_NAMESPACE_TEMPLATE.format("MD_DataIdentification") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("citation"),
            xml
        )
        date_elems = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Date"),
            md_elem
        )
        for identifier, _list in date_additionals.items():
            for elem in date_elems:
                date_type_elem = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_DateTypeCode"),
                    elem
                )
                date_txt = xml_helper.try_get_text_from_xml_element(
                    elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Date"),
                )
                date_type_txt = xml_helper.try_get_text_from_xml_element(date_type_elem) or ""
                date_type_attr = xml_helper.try_get_attribute_from_xml_element(date_type_elem, "codeListValue") or ""
                if identifier in date_type_txt or identifier in date_type_attr:
                    # Found one!
                    _list.append(date_txt)
        ret_dict["dates_additional"] = date_additionals
        del elem
        del _list
        del md_elem
        del date_txt
        del date_elems
        del identifier
        del date_type_txt
        del date_type_attr
        del date_type_elem
        del date_additionals

        # Encoding
        ret_dict["encoding"] = xml_helper.try_get_attribute_from_xml_element(
            xml,
            "codeListValue",
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_CharacterSetCode")
        )

        return ret_dict

    def set_proxy(self, use_proxy: bool, force_version: OGCServiceVersionEnum=None, auto_save: bool=True):
        """ Sets different elements inside the document on a secured level

        Args:
            use_proxy (bool): Whether to use a proxy or not
            auto_save (bool): Whether to directly save the modified document or not
        Returns:
        """
        self.set_dataset_metadata_secured(use_proxy, force_version=force_version, auto_save=auto_save)
        self.set_legend_url_secured(use_proxy, force_version=force_version, auto_save=auto_save)
        self.set_operations_secured(use_proxy, force_version=force_version, auto_save=auto_save)

    def _set_wms_operations_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wms operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        request_objs = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request")
            , xml_obj
        )
        request_objs = request_objs.getchildren()
        service = self.metadata.service
        operation_urls = service.operation_urls.all()
        op_uri_dict = {
            OGCOperationEnum.GET_MAP.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_MAP.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_MAP.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.GET_FEATURE_INFO.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE_INFO.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE_INFO.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.DESCRIBE_LAYER.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.GET_LEGEND_GRAPHIC.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.GET_STYLES.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Post").first(),"url", None),
            },
        }

        for op in request_objs:

            # skip GetCapabilities - it is already set to another internal link
            if OGCOperationEnum.GET_CAPABILITIES.value in op.tag:
                continue

            uri_dict = op_uri_dict.get(op.tag, {})
            http_operations = ["Get", "Post"]

            for http_operation in http_operations:
                res_objs = xml_helper.try_get_element_from_xml(
                    ".//{}/".format(GENERIC_NAMESPACE_TEMPLATE.format(http_operation)) + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
                    , op
                )
                # Load url attribute from ServiceUrl object
                if not is_secured:
                    # overwrite uri
                    uri = uri_dict.get(http_operation, "")

                for res_obj in res_objs:
                    xml_helper.write_attribute(
                        res_obj,
                        attrib="{http://www.w3.org/1999/xlink}href",
                        txt=uri
                    )

    def _set_wfs_1_0_0_operations_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wfs 1.0.0 operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        operation_objs = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request")
            , xml_obj
        )
        try:
            service = self.metadata.service
        except ObjectDoesNotExist:
            service = FeatureType.objects.get(
                metadata=self.metadata
            ).parent_service
        operation_urls = service.operation_urls.all()
        op_uri_dict = {
            OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.GET_FEATURE.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.GET_PROPERTY_VALUE.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_PROPERTY_VALUE.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_PROPERTY_VALUE.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.LIST_STORED_QUERIES.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.LIST_STORED_QUERIES.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.LIST_STORED_QUERIES.value, method="Post").first(),"url", None),
            },
            OGCOperationEnum.DESCRIBE_STORED_QUERIES.value: {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_STORED_QUERIES.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_STORED_QUERIES.value, method="Post").first(),"url", None),
            },
        }

        for op in operation_objs:
            # skip GetCapabilities - it is already set to another internal link
            name = op.tag

            if OGCOperationEnum.GET_CAPABILITIES.value in name:
                continue
            if not is_secured:
                uri = op_uri_dict.get(name, {"Get": None, "Post": None})
            http_objs = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP"), op)
            for http_obj in http_objs:
                requ_objs = http_obj.getchildren()
                for requ_obj in requ_objs:
                    xml_helper.write_attribute(
                        requ_obj,
                        attrib="onlineResource",
                        txt=uri
                    )

    def _set_wfs_operations_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wfs operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        operation_objs = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation"), xml_obj)

        try:
            service = self.metadata.service
        except ObjectDoesNotExist:
            service = FeatureType.objects.get(
                metadata=self.metadata
            ).parent_service

        operation_urls = service.operation_urls.all()
        op_uri_dict = {
            "DescribeFeatureType": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value, method="Get").first(), "url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value, method="Post").first(), "url", None),
            },
            "GetFeature": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE.value, method="Get").first(), "url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE.value, method="Post").first(), "url", None),
            },
            "GetPropertyValue": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_PROPERTY_VALUE.value, method="Get").first(), "url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_PROPERTY_VALUE.value, method="Post").first(), "url", None),
            },
            "ListStoredQueries": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.LIST_STORED_QUERIES.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.LIST_STORED_QUERIES.value, method="Post").first(),"url", None),
            },
            "DescribeStoredQueries": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_STORED_QUERIES.value, method="Get").first(), "url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_STORED_QUERIES.value, method="Post").first(), "url", None),
            },
            "GetGmlObject": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_GML_OBJECT.value, method="Get").first(), "url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_GML_OBJECT.value, method="Post").first(), "url", None),
            },
        }

        fallback_uri = getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE.value, method="Get").first(), "url", None)

        for op in operation_objs:
            # skip GetCapabilities - it is already set to another internal link
            name = xml_helper.try_get_attribute_from_xml_element(op, "name")
            if name == OGCOperationEnum.GET_CAPABILITIES.value or name is None:
                continue

            http_operations = ["Get", "Post"]

            for http_operation in http_operations:

                if not is_secured:
                    uri = op_uri_dict.get(name, {}).get(http_operation, None) or fallback_uri

                http_objs = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") + "/" + GENERIC_NAMESPACE_TEMPLATE.format(http_operation), op)

                for http_obj in http_objs:
                    xml_helper.write_attribute(
                        http_obj,
                        attrib="{http://www.w3.org/1999/xlink}href",
                        txt=uri
                    )

    def _set_wms_1_0_0_operation_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wms 1.0.0 operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        request_objs = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request")
            , xml_obj
        )
        request_objs = request_objs.getchildren()
        service = self.metadata.service
        operation_urls = service.operation_urls.all()
        op_uri_dict = {
            "GetMap": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_MAP.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_MAP.value, method="Post").first(),"url", None),
            },
            "GetFeatureInfo": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE_INFO.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_FEATURE_INFO.value, method="Post").first(),"url", None),
            },
            "DescribeLayer": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.DESCRIBE_LAYER.value, method="Post").first(),"url", None),
            },
            "GetLegendGraphic": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value, method="Post").first(),"url", None),
            },
            "GetStyles": {
                "Get": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Get").first(),"url", None),
                "Post": getattr(operation_urls.filter(operation=OGCOperationEnum.GET_STYLES.value, method="Post").first(),"url", None),
            },
        }

        for op in request_objs:

            # skip GetCapabilities - it is already set to another internal link
            if OGCOperationEnum.GET_CAPABILITIES.value in op.tag:
                continue

            uri_dict = op_uri_dict.get(op.tag, "")
            http_operations = ["Get", "Post"]

            for http_operation in http_operations:
                res_objs = xml_helper.try_get_element_from_xml(".//{}".format(http_operation), op)

                if not is_secured:
                    # overwrite uri
                    uri = uri_dict.get(http_operation, "")

                for res_obj in res_objs:
                    xml_helper.write_attribute(
                        res_obj,
                        attrib="onlineResource",
                        txt=uri
                    )

    def set_capabilities_secured(self, auto_save: bool=True):
        """ Change external links to internal for service capability document call

        Args:
            auto_save (bool): Whether the document shall be directly saved or not
        Returns:

        """

        # change some external linkage to internal links for the current_capability_document
        uri = SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        xml = xml_helper.parse_xml(self.content)

        # wms and wfs have to be handled differently!
        # Furthermore each standard has a different handling of attributes and elements ...
        service_version = self.metadata.get_service_version().value

        if self.metadata.is_service_type(OGCServiceEnum.WMS):

            if service_version == "1.0.0":
                # additional things to change for WMS 1.0.0
                xml_helper.write_text_to_element(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    uri
                )
                http_methods = ["Get", "Post"]
                for method in http_methods:
                    xml_helper.write_attribute(
                        xml,
                        "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capabilities") +
                        "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCPType") +
                        "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                        "/" + GENERIC_NAMESPACE_TEMPLATE.format(method),
                        "onlineResource",
                        uri)

            else:
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href", uri)
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("GetCapabilities") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCPType") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri)
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("GetCapabilities") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCPType") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri)

        elif self.metadata.is_service_type(OGCServiceEnum.WFS):
            if service_version == "1.0.0":
                xml_helper.write_text_to_element(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                    "onlineResource",
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                    "onlineResource",
                    uri
                )
            else:
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInfo") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri
                )

        xml = xml_helper.xml_to_string(xml)
        self.content = xml

        if auto_save:
            self.save()

    def set_operations_secured(self, is_secured: bool, force_version: OGCServiceVersionEnum, auto_save: bool=True):
        """ Change external links to internal for service operations

        Args:
            is_secured (bool): Whether the service is secured or not
            force_version (OGCServiceVersionEnum): Which version processing shall be forced
            auto_save (bool): Whether to directly save at the end of the function or not
        Returns:

        """
        if self.content is None:
            # Nothing to do here
            return

        xml_obj = xml_helper.parse_xml(self.content)
        if is_secured:
            uri = SERVICE_OPERATION_URI_TEMPLATE.format(self.metadata.id)
        else:
            uri = ""
        _version = force_version or self.metadata.get_service_version()
        if self.metadata.is_service_type(OGCServiceEnum.WMS):
            if _version is OGCServiceVersionEnum.V_1_0_0:
                self._set_wms_1_0_0_operation_secured(xml_obj, uri, is_secured)
            else:
                self._set_wms_operations_secured(xml_obj, uri, is_secured)
        elif self.metadata.is_service_type(OGCServiceEnum.WFS):
            if _version is OGCServiceVersionEnum.V_1_0_0:
                self._set_wfs_1_0_0_operations_secured(xml_obj, uri, is_secured)
            else:
                self._set_wfs_operations_secured(xml_obj, uri, is_secured)

        self.content = xml_helper.xml_to_string(xml_obj)

        if auto_save:
            self.save()

    def set_dataset_metadata_secured(self, is_secured: bool, force_version: OGCServiceVersionEnum=None, auto_save: bool=True):
        """ Set or unsets the proxy for the dataset metadata uris

        Args:
            is_secured (bool): Whether the proxy shall be activated or deactivated
            force_version (OGCServiceVersionEnum): Which version processing shall be forced
            auto_save (bool): Whether to directly save at the end of the function or not
        Returns:
             nothing
        """
        cap_doc_curr = self.content
        if cap_doc_curr is None:
            # Nothing to do here!
            return

        xml_obj = xml_helper.parse_xml(cap_doc_curr)
        service_version = force_version or self.metadata.get_service_version()
        service_type = self.metadata.get_service_type()

        is_wfs = service_type == OGCServiceEnum.WFS.value
        is_wfs_1_0_0 = is_wfs and service_version == OGCServiceVersionEnum.V_1_0_0.value
        is_wfs_1_1_0 = is_wfs and service_version == OGCServiceVersionEnum.V_1_1_0.value

        # get <MetadataURL> xml elements
        if is_wfs:
            xml_metadata_elements = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataURL"), xml_obj)
        else:
            xml_metadata_elements = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataURL") + "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"), xml_obj)

        # iterate over elements and change the uris
        for xml_metadata in xml_metadata_elements:
            attr = "{http://www.w3.org/1999/xlink}href"

            # get metadata url
            if is_wfs_1_0_0 or is_wfs_1_1_0:
                metadata_uri = xml_helper.try_get_text_from_xml_element(xml_metadata)
            else:
                metadata_uri = xml_helper.get_href_attribute(xml_metadata)
            own_uri_prefix = "{}{}".format(HTTP_OR_SSL, HOST_NAME)

            if not metadata_uri.startswith(own_uri_prefix):
                # find metadata record which matches the metadata uri
                try:
                    dataset_md_record = Metadata.objects.get(
                        metadata_url=metadata_uri,
                    )
                    uri = SERVICE_DATASET_URI_TEMPLATE.format(dataset_md_record.id)
                except ObjectDoesNotExist:
                    # This is a bad situation... Only possible if the registered service has not been updated BUT the
                    # original remote service changed and maybe has a new - for us - unknown MetadataURL object.
                    # This is why we can't find it in our db. We simply have to set it to some placeholder, since the
                    # user has to update the service.
                    uri = "unknown"
            else:
                # this means we have our own proxy uri in here and want to restore the original one
                # metadata uri contains the proxy uri
                # so we need to extract the id from the uri!
                md_uri_list = metadata_uri.split("/")
                md_id = md_uri_list[len(md_uri_list) - 1]
                dataset_md_record = Metadata.objects.get(id=md_id)
                uri = dataset_md_record.metadata_url
            if is_wfs_1_0_0 or is_wfs_1_1_0:
                xml_helper.write_text_to_element(xml_metadata, txt=uri)
            else:
                xml_helper.set_attribute(xml_metadata, attr, uri)
        xml_obj_str = xml_helper.xml_to_string(xml_obj)
        self.content = xml_obj_str

        if auto_save:
            self.save()

    def set_legend_url_secured(self, is_secured: bool, force_version:OGCServiceVersionEnum=None, auto_save: bool=True):
        """ Set or unsets the proxy for the style legend uris

        Args:
            is_secured (bool): Whether the proxy shall be activated or deactivated
            force_version (OGCServiceVersionEnum): Which version processing shall be forced
            auto_save (bool): Whether to directly save at the end of the function or not
        Returns:
             nothing
        """
        cap_doc_curr = self.content
        if cap_doc_curr is None:
            # Nothing to do here!
            return

        xml_doc = xml_helper.parse_xml(cap_doc_curr)

        # get <LegendURL> elements
        xml_legend_elements = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("LegendURL") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
            xml_doc
        )
        attr = "{http://www.w3.org/1999/xlink}href"
        for xml_elem in xml_legend_elements:
            legend_uri = xml_helper.get_href_attribute(xml_elem)

            uri = None

            if is_secured and not legend_uri.startswith(ROOT_URL):
                parent_md = self.metadata

                if not self.metadata.is_root():
                    parent_md = self.metadata.service.parent_service.metadata

                style_id = Style.objects.get(
                    legend_uri=legend_uri,
                    layer__parent_service__metadata=parent_md,
                ).id
                uri = SERVICE_LEGEND_URI_TEMPLATE.format(self.metadata.id, style_id)

            elif not is_secured and legend_uri.startswith(ROOT_URL):
                # restore the original legend uri by using the layer identifier
                style_id = legend_uri.split("/")[-1]
                uri = Style.objects.get(id=style_id).legend_uri

            if uri is not None:
                xml_helper.set_attribute(xml_elem, attr, uri)

        xml_doc_str = xml_helper.xml_to_string(xml_doc)
        self.content = xml_doc_str

        if auto_save:
            self.save()

    def restore(self):
        """ We overwrite the current metadata xml with the original

        Returns:
             nothing
        """
        original_doc = Document.objects.get(
            is_original=True,
            metadata=self.metadata,
            document_type=DocumentEnum.CAPABILITY.value
        )
        self.content = original_doc.content
        self.set_capabilities_secured()
        self.set_proxy(use_proxy=self.metadata.use_proxy_uri)
        self.save()

    def restore_subelement(self, identifier: str):
        """ Restores only the layer which matches the provided identifier

        Args:
            identifier (str): The identifier which matches a single layer in the document
        Returns:
             nothing
        """
        original_doc = Document.objects.get(
            is_original=True,
            metadata=self.metadata,
            document_type=DocumentEnum.CAPABILITY.value
        )
        # only restored the layer and it's children
        cap_doc_curr_obj = xml_helper.parse_xml(self.content)
        cap_doc_orig_obj = xml_helper.parse_xml(original_doc.content)

        xml_layer_obj_curr = xml_helper.find_element_where_text(cap_doc_curr_obj, identifier)[0]
        xml_layer_obj_orig = xml_helper.find_element_where_text(cap_doc_orig_obj, identifier)[0]

        # find position where original element existed
        parent_orig = xml_helper.get_parent(xml_layer_obj_orig)
        orig_index = parent_orig.index(xml_layer_obj_orig)

        # insert original element at the original index and remove current element (which now is at index + 1)
        parent_curr = xml_helper.get_parent(xml_layer_obj_curr)
        parent_curr.insert(orig_index, xml_layer_obj_orig)
        parent_curr.remove(xml_layer_obj_curr)

        self.content = xml_helper.xml_to_string(cap_doc_curr_obj)
        self.save()


class Licence(Resource):
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255, unique=True)
    symbol_url = models.URLField(null=True)
    description = models.TextField()
    description_url = models.URLField(null=True)
    is_open_data = models.BooleanField(default=False)

    def __str__(self):
        return "{} ({})".format(self.identifier, self.name)

    @classmethod
    def as_choices(cls):
        """ Returns a list of (identifier, name) to be used as choices in a form

        Returns:
             tuple_list (list): As described above
        """
        return [(licence.identifier, licence.__str__()) for licence in Licence.objects.filter(is_active=True)]

    @classmethod
    def get_descriptions_help_text(cls):
        """ Returns a string containing all active Licence records for rendering as help_text in a form

        Returns:
             string (str): As described above
        """
        from django.db.utils import ProgrammingError

        try:
            descrs = [
                "<a href='{}' target='_blank'>{}</a>".format(
                    licence.description_url, licence.identifier
                ) for licence in Licence.objects.filter(
                    is_active=True
                )
            ]
            descr_str = "<br>".join(descrs)
            descr_str = _("Explanations: <br>") + descr_str
        except ProgrammingError:
            # This will happen on an initial installation. The Licence table won't be created yet, but this function
            # will be called on makemigrations.
            descr_str = ""
        return descr_str


class Category(Resource):
    type = models.CharField(max_length=255, choices=CategoryOriginEnum.as_choices())
    title_locale_1 = models.CharField(max_length=255, null=True)
    title_locale_2 = models.CharField(max_length=255, null=True)
    title_EN = models.CharField(max_length=255, null=True)
    description_locale_1 = models.TextField(null=True)
    description_locale_2 = models.TextField(null=True)
    description_EN = models.TextField(null=True)
    symbol = models.CharField(max_length=500, null=True)
    online_link = models.CharField(max_length=500, null=True)

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(
                fields=[
                    "title_EN"
                ]
            )
        ]

    def __str__(self):
        return self.title_EN + " (" + self.type + ")"


class ServiceType(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=100, choices=OGCServiceVersionEnum.as_choices())
    specification = models.URLField(blank=False, null=True)

    def __str__(self):
        return self.name


class GenericUrl(Resource):
    description = models.TextField(null=True, blank=True)
    method = models.CharField(max_length=255, choices=HttpMethodEnum.as_choices(), blank=True, null=True)
    url = models.URLField(blank=True, null=True)

    def __str__(self):
        return "{} ({})".format(self.url, self.method)


class ServiceUrl(GenericUrl):
    operation = models.CharField(max_length=255, choices=OGCOperationEnum.as_choices(), blank=True, null=True)


class Service(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="service")
    parent_service = models.ForeignKey('self', on_delete=models.CASCADE, related_name="child_service", null=True, default=None, blank=True)
    published_for = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, related_name="published_for", null=True, default=None, blank=True)
    service_type = models.ForeignKey(ServiceType, on_delete=models.DO_NOTHING, blank=True, null=True)
    operation_urls = models.ManyToManyField(ServiceUrl)
    is_root = models.BooleanField(default=False)
    availability = models.DecimalField(decimal_places=2, max_digits=4, default=0.0)
    is_available = models.BooleanField(default=False)
    is_update_candidate_for = models.OneToOneField('self', on_delete=models.SET_NULL, related_name="has_update_candidate", null=True, default=None, blank=True)
    created_by_user = models.ForeignKey(MrMapUser, on_delete=models.SET_NULL, null=True, blank=True)
    keep_custom_md = models.BooleanField(default=True)

    # used to store ows linked_service_metadata until parsing is finished
    # will not be part of the db
    linked_service_metadata = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.root_layer = None
        self.feature_type_list = []
        self.categories_list = []

    def __str__(self):
        return str(self.id)

    @property
    def subelements(self):
        """ Returns a list of Layer or Featuretype records.

        Returns:
             list (list): The list of subelements
        """
        ret_list = []
        if self.is_service_type(OGCServiceEnum.WMS):
            if self.metadata.is_metadata_type(MetadataEnum.SERVICE):
                qs = Layer.objects.filter(
                    parent_service=self
                ).prefetch_related(
                    "metadata"
                )
                ret_list = list(qs)
            else:
                self_layer_instance = Layer.objects.get(metadata=self.metadata)
                ret_list += list(self_layer_instance.child_layers.all())
                for layer in ret_list:
                    ret_list += list(layer.child_layers.all())
        elif self.is_service_type(OGCServiceEnum.WFS):
            ret_list += FeatureType.objects.filter(
                parent_service=self
            ).prefetch_related(
                "metadata"
            )

        return ret_list

    @property
    def is_wms(self):
        """ Returns whether the service is a WMS or not

        Returns:
             True if WMS else False
        """
        return self.is_service_type(enum=OGCServiceEnum.WMS)

    @property
    def is_wfs(self):
        """ Returns whether the service is a WMS or not

        Returns:
             True if WMS else False
        """
        return self.is_service_type(enum=OGCServiceEnum.WFS)

    @property
    def is_csw(self):
        """ Returns whether the service is a CSW or not

        Returns:
             True if CSW else False
        """
        return self.is_service_type(enum=OGCServiceEnum.CSW)

    def is_service_type(self, enum: OGCServiceEnum):
        """ Returns whether the service is of this ServiceEnum

        Args:
            enum (OGCServiceEnum): The enum
        Returns:
             True if the service_types are equal, false otherwise
        """
        return self.service_type.name == enum.value

    def secure_access(self, is_secured: bool, group: MrMapGroup, operation: RequestOperation, group_polygons: dict, sec_op: SecuredOperation, element=None):
        """ Secures a single element

        Args:
            is_secured (bool): Whether to secure the element or not
            group (MrMapGroup): The group which is allowed to perform an operation
            operation (RequestOperation): The operation which can be performed by the groups
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:

        """
        if element is None:
            element = self
        element.metadata.is_secured = is_secured
        if is_secured:

            if sec_op is None:
                sec_op = SecuredOperation()
                sec_op.operation = operation
                sec_op.allowed_group = group
            else:
                sec_op = SecuredOperation.objects.get(
                    secured_metadata=element.metadata,
                    operation=operation,
                    allowed_group=group
                )

            poly_list = []
            for group_polygon in group_polygons:
                poly_str = group_polygon.get("geometry", group_polygon).get("coordinates", [None])[0]
                tmp_poly = Polygon(poly_str)
                poly_list.append(tmp_poly)

            sec_op.bounding_geometry = GeometryCollection(poly_list)
            sec_op.save()
            element.metadata.secured_operations.add(sec_op)
        else:
            element.metadata.secured_operations.all().delete()
            element.metadata.secured_operations.clear()
        element.metadata.save()
        element.save()

    def _secure_sub_layers(self, is_secured: bool, group: MrMapGroup, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Secures all sub layers of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (MrMapGroup): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        if self.is_root:
            # get the first layer in this service
            start_element = Layer.objects.get(
                parent_service=self,
                parent_layer=None,
            )
        else:
            # simply get the layer which is described by the given metadata
            start_element = Layer.objects.get(
                metadata=self.metadata
            )
        start_element.secure_sub_layers_recursive(is_secured, group, operation, group_polygons, secured_operation)

    def _secure_feature_types(self, is_secured: bool, group: MrMapGroup, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Secures all sub layers of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (MrMapGroup): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        if self.is_root:
            elements = self.featuretypes.all()
            for element in elements:
                self.secure_access(is_secured, group, operation, group_polygons, secured_operation, element=element)

    def secure_sub_elements(self, is_secured: bool, group: MrMapGroup, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Secures all sub elements of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (MrMapGroup): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        if self.is_service_type(OGCServiceEnum.WMS):
            self._secure_sub_layers(is_secured, group, operation, group_polygons, secured_operation)
        elif self.is_service_type(OGCServiceEnum.WFS):
            self._secure_feature_types(is_secured, group, operation, group_polygons, secured_operation)

    @transaction.atomic
    def delete_child_data(self, child):
        """ Delete all layer data like related iso metadata

        Args:
            layer (Layer): The current layer object
        Returns:
            nothing
        """
        # remove related metadata
        iso_mds = child.metadata.related_metadata.all()
        for iso_md in iso_mds:
            md_2 = iso_md.metadata_to
            md_2.delete()
            iso_md.delete()
        if isinstance(child, FeatureType):
            # no other way to remove feature type metadata on service deleting
            child.metadata.delete()
        child.delete()

    @transaction.atomic
    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete method

        Recursively remove children

        Args;
            using:
            keep_parents:
        Returns:
        """
        # remove related metadata
        linked_mds = self.metadata.related_metadata.all()
        for linked_md in linked_mds:
            md_2 = linked_md.metadata_to
            md_2.delete()
            linked_md.delete()

        # remove subelements
        if self.is_service_type(OGCServiceEnum.WMS):
            layers = self.child_service.all()
            for layer in layers:
                self.delete_child_data(layer)
        elif self.is_service_type(OGCServiceEnum.WFS):
            feature_types = self.featuretypes.all()
            for f_t in feature_types:
                self.delete_child_data(f_t)

        # Remove ServiceURL entries if they are not used by other services
        operation_urls = self.operation_urls.all()
        for url in operation_urls:
            other_services_exists = Service.objects.filter(
                operation_urls=url
            ).exclude(
                id=self.id
            ).exists()
            if not other_services_exists:
                url.delete()

        self.metadata.delete()
        super().delete()

    def __get_children(self, current, layers: list):
        """ Recursive appending of all layers

        Args:
            current (Layer): The current layer instance
            layers (list): The list of all collected layers so far
        Returns:
             nothing
        """
        layers.append(current)
        for layer in current.children_list:
            layers.append(layer)
            if len(layer.children_list) > 0:
                self.__get_children(layer, layers)

    def get_all_layers(self):
        """ Returns all layers in a list that can be found in this service

        NOTE: THIS IS ONLY USED FOR CHILDREN_LIST, WHICH SHOULD ONLY BE USED FOR NON-PERSISTED OBJECTS!!!

        Returns:
             layers (list): The layers
        """

        layers = []
        self.__get_children(self.root_layer, layers)
        return layers

    def activate_service(self, is_active: bool):
        """ Toggles the activity status of a service and it's metadata

        Args:
            is_active (bool): Whether the service shall be activated or not
        Returns:
             nothing
        """
        self.is_active = is_active
        self.metadata.is_active = is_active

        linked_mds = self.metadata.related_metadata.all()
        for md_relation in linked_mds:
            md_relation.metadata_to.is_active = is_active
            md_relation.metadata_to.save(update_last_modified=False)

        self.metadata.save(update_last_modified=False)
        self.save(update_last_modified=False)

    def persist_original_capabilities_doc(self, xml: str):
        """ Persists the capabilities document

        Args:
            xml (str): The xml document as string
        Returns:
             nothing
        """
        # save original capabilities document
        Document.objects.create(
            content=xml,
            metadata=self.metadata,
            is_original=True,
            document_type=DocumentEnum.CAPABILITY.value
        )


class Layer(Service):
    class Meta:
        ordering = ["position"]
    identifier = models.CharField(max_length=500, null=True)
    preview_image = models.CharField(max_length=100, blank=True, null=True)
    preview_extent = models.CharField(max_length=100, blank=True, null=True)
    preview_legend = models.CharField(max_length=100)
    parent_layer = models.ForeignKey("self", on_delete=models.CASCADE, null=True, related_name="child_layers")
    position = models.IntegerField(default=0)
    is_queryable = models.BooleanField(default=False)
    is_opaque = models.BooleanField(default=False)
    is_cascaded = models.BooleanField(default=False)
    scale_min = models.FloatField(default=0)
    scale_max = models.FloatField(default=0)
    bbox_lat_lon = models.PolygonField(default=DEFAULT_BOUNDING_BOX)
    iso_metadata = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.children_list = []
        self.tmp_style = None  # holds the style before persisting

    def __str__(self):
        return str(self.identifier)

    def delete(self, using=None, keep_parents=False):
        """ Deletes layer and all of it's children

        Args:
            using:
            keep_parents:
        Returns:

        """
        children = self.get_children()
        for child in children:
            child.delete(using, keep_parents)
        super().delete(using, keep_parents)

    def get_inherited_reference_systems(self):
        ref_systems = []
        ref_systems += list(self.metadata.reference_system.all())

        parent_layer = self.parent_layer
        while parent_layer is not None:
            parent_srs = parent_layer.metadata.reference_system.all()
            for srs in parent_srs:
                if srs not in ref_systems:
                    ref_systems.append(srs)
            parent_layer = parent_layer.parent_layer

        return ref_systems

    def get_inherited_bounding_geometry(self):
        """ Returns the biggest bounding geometry of the service.

        Bounding box shall be inherited. We do not persist them directly into the layer objects, since we might
        lose the geometry, that is specified by the single layer object.
        This function walks all the way up to the root layer of the service and returns the biggest bounding geometry.
        Since upper layer geometries must cover the ones of their children, these big geometry includes the children ones.

        Returns:
             bounding_box (Polygon): A geometry object
        """
        bounding_box = self.metadata.bounding_box
        parent_layer = self.parent_layer
        while parent_layer is not None:
            parent_bounding_box = parent_layer.metadata.bounding_box
            if bounding_box.area > 0:
                if parent_bounding_box.covers(bounding_box):
                    bounding_box = parent_bounding_box
            else:
                bounding_box = parent_bounding_box
            parent_layer = parent_layer.parent_layer
        return bounding_box

    def get_style(self):
        """ Simple getter for the style of the current layer

        Returns:
             styles (QuerySet): A query set containing all styles
        """
        return self.style.all()

    def _get_all_children_recursive(self, layer_list: list):
        """ Returns a list of all children of the current layer

        Args:
            layer_list (list): The list of collected layers so far
        Returns:
            layer_list (list)
        """
        children = self.get_children()
        for child in children:
            layer_list.append(child)
            child._get_all_children_recursive(layer_list)
        return layer_list

    def get_children(self, all=False):
        """ Simple getter for the direct children of the current layer

        Returns:
             children (QuerySet): A query set containing all direct children layer of this layer
        """
        if all:
            return self._get_all_children_recursive([])
        else:
            return self.child_layers.all()

    def get_upper_layers(self):
        """ Returns a list of all layers from self to the root layer of the service

        Returns:

        """
        ret_list = []
        upper_element = Layer.objects.get(
            child_layers=self
        )
        while upper_element is not None:
            ret_list.append(upper_element)
            try:
                upper_element = Layer.objects.get(
                    child_layers=upper_element
                )
            except ObjectDoesNotExist:
                upper_element = None
        return ret_list

    def delete_children_secured_operations(self, layer, operation, group):
        """ Walk recursive through all layers of wms and remove their secured operations

        The 'layer' will not be affected!

        Args:
            layer: The layer, which children shall be changed.
            operation: The RequestOperation of the SecuredOperation
            group: The group
        Returns:

        """
        for child_layer in layer.child_layers.all():
            sec_ops = SecuredOperation.objects.filter(
                secured_metadata=child_layer.metadata,
                operation=operation,
                allowed_group=group,
            )
            sec_ops.delete()
            self.delete_children_secured_operations(child_layer, operation, group)

    def activate_layer_recursive(self, new_status):
        """ Walk recursive through all layers of a wms and set the activity status new

        Args:
            root_layer: The root layer, where the recursion begins
            new_status: The new status that will be persisted
        Returns:
             nothing
        """
        # check for all related metadata, we need to toggle their active status as well
        rel_md = self.metadata.related_metadata.all()
        for md in rel_md:
            dependencies = MetadataRelation.objects.filter(
                metadata_to=md.metadata_to,
            )
            if dependencies.count() > 1 and new_status is False:
                # we still have multiple dependencies on this relation (besides us), we can not deactivate the metadata
                pass
            else:
                # since we have no more dependencies on this metadata, we can set it inactive
                md.metadata_to.is_active = new_status
                md.metadata_to.set_documents_active_status(new_status)
                md.metadata_to.save()
                md.save()

        self.metadata.is_active = new_status
        self.metadata.save()
        self.metadata.set_documents_active_status(new_status)
        self.is_active = new_status
        self.save()

        for layer in self.child_layers.all():
            layer.activate_layer_recursive(new_status)

    def _get_bottom_layers_identifier_iterative(self):
        """ Runs a iterative search for all leaf layers.

        If a leaf layer is found, it will be added to layer_list

        Returns:
             leaves (list): List of id sorted leaf layer identifiers
        """
        layer_obj_children = self.child_layers.all()
        leaves = []
        non_leaves = []
        for child in layer_obj_children:
            children = child.child_layers.all()
            if children.count() == 0:
                leaves.append(child)
            else:
                non_leaves.append(child)

        while len(non_leaves) > 0:
            layer = non_leaves.pop()
            children = layer.child_layers.all()
            if children.count() == 0:
                leaves.append(layer)
            else:
                non_leaves += children

        leaves.sort(key=lambda elem: elem.id)
        leaves = [leaf.identifier for leaf in leaves]
        return leaves

    def get_leaf_layers_identifier(self):
        """ Returns a list of all leaf layer's identifiers.

        Leaf layers are the layers, which have no further children.

        Returns:
             leaf_layers (list): The leaf layers of a layer
        """
        leaf_layers = self._get_bottom_layers_identifier_iterative()
        return leaf_layers

    def secure_sub_layers_recursive(self, is_secured: bool, group: MrMapGroup, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Recursive implementation of securing all sub layers of a current layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (MrMapGroup): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        self.secure_access(is_secured, group, operation, group_polygons, secured_operation)

        for layer in self.child_layers.all():
            layer.secure_sub_layers_recursive(is_secured, group, operation, group_polygons, secured_operation)


class Module(Service):
    type = models.CharField(max_length=100)

    def __str__(self):
        return self.type


class ReferenceSystem(models.Model):
    code = models.CharField(max_length=100)
    prefix = models.CharField(max_length=255, default="EPSG:")
    version = models.CharField(max_length=50, default="9.6.1")

    class Meta:
        unique_together = ("code", "prefix")
        ordering = ["-code"]

    def __str__(self):
        return str(self.code)


class Dataset(Resource):
    """ Representation of Dataset objects.

    Datasets identify a real-life resource, like a shapefile. One dataset can be the source for multiple services.
    Therefore one dataset record can describe multiple services as well.

    """
    SRS_AUTHORITIES_CHOICES = [
        ("EPSG", "European Petroleum Survey Group (EPSG) Geodetic Parameter Registry"),
    ]

    CHARACTER_SET_CHOICES = [
        ("utf8", "utf8"),
        ("utf16", "utf16"),
    ]

    UPDATE_FREQUENCY_CHOICES = [
        ("annually", "annually"),
        ("asNeeded", "asNeeded"),
        ("biannually", "biannually"),
        ("irregular", "irregular"),
        ("notPlanned", "notPlanned"),
        ("unknown", "unknown"),
    ]

    LEGAL_RESTRICTION_CHOICES = [
        ("copyright", "copyright"),
        ("intellectualPropertyRights", "intellectualPropertyRights"),
        ("license", "license"),
        ("otherRestrictions", "otherRestrictions"),
        ("patent", "patent"),
        ("patentPending", "patentPending"),
        ("restricted", "restricted"),
        ("trademark", "trademark"),
    ]

    DISTRIBUTION_FUNCTION_CHOICES = [
        ("download", "download"),
        ("information", "information"),
        ("offlineAccess", "offlineAccess"),
        ("order", "order"),
        ("search", "search"),
    ]

    DATA_QUALITY_SCOPE_CHOICES = [
        ("attribute", "attribute"),
        ("attributeType", "attributeType"),
        ("collectionHardware", "collectionHardware"),
        ("collectionSession", "collectionSession"),
        ("dataset", "dataset"),
        ("dimensionGroup", "dimensionGroup"),
        ("feature", "feature"),
        ("featureType", "featureType"),
        ("fieldSession", "fieldSession"),
        ("model", "model"),
        ("nonGeographicDataset", "nonGeographicDataset"),
        ("propertyType", "propertyType"),
        ("series", "series"),
        ("software", "software"),
        ("service", "service"),
        ("tile", "tile"),
    ]

    LANGUAGE_CODE_LIST_URL_DEFAULT = "https://standards.iso.org/iso/19139/Schemas/resources/codelist/ML_gmxCodelists.xml"
    CODE_LIST_URL_DEFAULT = "https://www.isotc211.org/2005/resources/Codelist/gmxCodelists.xml"

    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, blank=True, null=True, related_name="dataset")
    language_code = models.CharField(max_length=100, blank=True, null=True)
    language_code_list_url = models.CharField(max_length=1000, blank=True, null=True, default=LANGUAGE_CODE_LIST_URL_DEFAULT)

    character_set_code = models.CharField(max_length=255, choices=CHARACTER_SET_CHOICES, default="utf8")
    character_set_code_list_url = models.CharField(max_length=1000, blank=True, null=True, default=CODE_LIST_URL_DEFAULT)

    hierarchy_level_code = models.CharField(max_length=100, blank=True, null=True)
    hierarchy_level_code_list_url = models.CharField(max_length=1000, blank=True, null=True, default=CODE_LIST_URL_DEFAULT)

    update_frequency_code = models.CharField(max_length=255, choices=UPDATE_FREQUENCY_CHOICES, null=True, blank=True)
    update_frequency_code_list_url = models.CharField(max_length=1000, blank=True, null=True, default=CODE_LIST_URL_DEFAULT)

    legal_restriction_code = models.CharField(max_length=255, choices=LEGAL_RESTRICTION_CHOICES, null=True, blank=True)
    legal_restriction_code_list_url = models.CharField(max_length=1000, blank=True, null=True, default=CODE_LIST_URL_DEFAULT)
    legal_restriction_other_constraints = models.TextField(null=True, blank=True)

    date_stamp = models.DateField(blank=True, null=True)
    metadata_standard_name = models.CharField(max_length=255, blank=True, null=True)
    metadata_standard_version = models.CharField(max_length=255, blank=True, null=True)
    md_identifier_code = models.CharField(max_length=500, null=True, blank=True)

    use_limitation = models.TextField(null=True, blank=True)

    distribution_function_code = models.CharField(max_length=255, choices=DISTRIBUTION_FUNCTION_CHOICES, default="dataset")
    distribution_function_code_list_url = models.CharField(max_length=1000, blank=True, null=True, default=CODE_LIST_URL_DEFAULT)

    lineage_statement = models.TextField(null=True, blank=True)

    def __str__(self):
        try:
            ret_val = self.metadata.title
        except (AttributeError, ObjectDoesNotExist):
            ret_val = "None"

        return ret_val


class LegalReport(models.Model):
    """ Representation of gmd:DQ_DomainConsistency objects.

    """
    title = models.TextField()
    date = models.ForeignKey('LegalDate', on_delete=models.SET_NULL, null=True)
    explanation = models.TextField()

    def __str__(self):
        return self.title


class LegalDate(models.Model):
    """ Representation of CI_DateType objects.

    Multiple records can create a history of actions related to a database element.

    """
    DATE_TYPE_CODE_CHOICES = [
        ("creation", "creation"),
        ("publication", "publication"),
        ("revision", "revision"),
    ]

    CODE_LIST_URL_DEFAULT = "https://standards.iso.org/iso/19139/resources/gmxCodelists.xml"

    date = models.DateField()
    date_type_code = models.CharField(max_length=255, choices=DATE_TYPE_CODE_CHOICES)
    date_type_code_list_url = models.CharField(max_length=1000, default=CODE_LIST_URL_DEFAULT)

    def __str__(self):
        return self.date_type_code


class MimeType(Resource):
    operation = models.CharField(max_length=255, null=True, choices=OGCOperationEnum.as_choices())
    mime_type = models.CharField(max_length=500)

    def __str__(self):
        return self.mime_type


class Dimension(models.Model):
    type = models.CharField(max_length=255, choices=DIMENSION_TYPE_CHOICES, null=True, blank=True)
    units = models.CharField(max_length=255, null=True, blank=True)
    extent = models.TextField(null=True, blank=True)
    custom_name = models.CharField(max_length=500, null=True, blank=True)

    time_extent_min = models.DateTimeField(null=True, blank=True)
    time_extent_max = models.DateTimeField(null=True, blank=True)

    elev_extent_min = models.FloatField(max_length=500, null=True, blank=True)
    elev_extent_max = models.FloatField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.type

    def _set_min_max_time_intervals(self, values: list):
        """ Sets the time_extent_min and time_extent_max values, parsed from many intervals

        Args:
            values (list): The list of values
        Returns:

        """
        # each of structure 'start/end/resolution'
        # Find min and max interval boundaries
        #intervals_min = datetime.now(timezone.utc)
        intervals_min = timezone.localtime()
        intervals_max = datetime(1800, 1, 1, tzinfo=timezone.utc)
        for interval in values:
            interval_components = interval.split("/")
            min = parse(timestr=interval_components[0])
            max = parse(timestr=interval_components[1])
            if min < intervals_min:
                intervals_min = min
            if max > intervals_max:
                intervals_max = max
        self.time_extent_min = intervals_min
        self.time_extent_max = intervals_max

    def _set_min_max_time_values(self, values: list):
        """ Sets the time_extent_min and time_extent_max values

        Args:
            values (list): The list of values
        Returns:

        """
        # each of structure 'start/end/resolution'
        # Find min and max interval boundaries
        #intervals_min = datetime.now(timezone.utc)
        intervals_min = timezone.localtime()
        intervals_max = datetime(1800, 1, 1, tzinfo=timezone.utc)
        for value in values:
            value = parse(timestr=value)
            if value < intervals_min:
                intervals_min = value
            if value > intervals_max:
                intervals_max = value
        self.time_extent_min = intervals_min
        self.time_extent_max = intervals_max

    def _set_min_max_elevation_interval(self, values: list):
        """ Sets the elev_extent_min and elev_extent_max values, parsed from many intervals

        Args:
            values (list): The list of values
        Returns:

        """
        # each of structure 'start/end/resolution'
        # Find min and max interval boundaries
        intervals_min = float("inf")
        intervals_max = -float("inf")
        for interval in values:
            interval_components = interval.split("/")
            val_min = float(interval_components[0])
            val_max = float(interval_components[1])
            intervals_min = min(val_min, intervals_min)
            intervals_max = max(val_max, intervals_max)
        self.elev_extent_min = intervals_min
        self.elev_extent_max = intervals_max

    def _set_min_max_elevation_values(self, values: list):
        """ Sets the elev_extent_min and elev_extent_max values

        Args:
            values (list): The list of values
        Returns:

        """
        float_values = [float(val) for val in values]
        self.elev_extent_max = max(float_values)
        self.elev_extent_min = min(float_values)

    def _evaluate_time_dimension(self, values: list):
        """ Evaluates the given time dimension extent.

        Instead of simply holding this giant string data, we try to find the range of it.

        Args:
            values (list): List holding all time values as values or intervals
        Returns:

        """
        # We assume the values to be dateTime strings
        if len(values) > 1:
            # Multiple intervals or multiple values
            if "/" in self.extent:
                # Multiple intervals
                self._set_min_max_time_intervals(values)
            else:
                # Multiple values
                self._set_min_max_time_values(values)
        else:
            # Single interval or single value
            if "/" in self.extent:
                # Single interval
                self._set_min_max_time_intervals(values)
            else:
                # Single value
                for value in values:
                    date = parse(timestr=value)
                    self.time_extent_min = date
                    self.time_extent_max = self.time_extent_min

    def _evaluate_elevation_dimension(self, values: list):
        """ Evaluates the given evaluation dimension extent.

        Instead of simply holding this giant string data, we try to find the range of it.

        Args:
            values (list): List holding all time values as values or intervals
        Returns:

        """
        # We assume the values to be numerical strings
        if len(values) > 1:
            # Multiple intervals or multiple values
            if "/" in self.extent:
                # Multiple intervals
                self._set_min_max_elevation_interval(values)
            else:
                # Multiple values
                self._set_min_max_elevation_values(values)
        else:
            # Single interval or single value
            if "/" in self.extent:
                # Single interval
                self._set_min_max_elevation_interval(values)
            else:
                # Single value
                for value in values:
                    self.elev_extent_min = float(value)
                    self.elev_extent_max = self.elev_extent_min

    def save(self, *args, **kwargs):
        """ Overwrites default saving

        Checks whether the given type is valid according to the valid choices of the field. If not, it's assumed
        to be a type 'other' and the given type will be moved to custom_name. The type will be set to the default
        for unknown types: 'other'.

        Args:
            args:
            kwargs:
        Returns:

        """
        # Check whether the given type is an allowed type from the choices
        if self.type != "time" and self.type != "elevation":
            # If we could not find it, the type is a custom name and needs to be moved to the custom_name field
            # The type is set to 'other'
            self.custom_name = self.type
            self.type = "other"

        # Find min and max values of extent
        try:
            # Multiple values are given if they are comma separated
            values = self.extent.split(",")
            if self.type == "time":
                self._evaluate_time_dimension(values)
            elif self.type == "elevation":
                self._evaluate_elevation_dimension(values)
            else:
                # In case of other - no way to understand automatically what the extent means
                pass
        except AttributeError:
            # Might happen if Dimension does not contain any Extent
            pass

        super().save(*args, **kwargs)


class Style(models.Model):
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE, related_name="style")
    name = models.CharField(max_length=255, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    legend_uri = models.CharField(max_length=500, null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.layer.identifier + ": " + self.name


class FeatureType(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="featuretype")
    parent_service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.CASCADE, related_name="featuretypes")
    is_searchable = models.BooleanField(default=False)
    default_srs = models.ForeignKey(ReferenceSystem, on_delete=models.DO_NOTHING, null=True, related_name="default_srs")
    inspire_download = models.BooleanField(default=False)
    elements = models.ManyToManyField('FeatureTypeElement')
    namespaces = models.ManyToManyField('Namespace')
    bbox_lat_lon = models.PolygonField(default=DEFAULT_BOUNDING_BOX)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.additional_srs_list = []
        self.keywords_list = []
        self.elements_list = []
        self.namespaces_list = []
        self.dataset_md_list = []

    def __str__(self):
        return self.metadata.identifier

    def secure_feature_type(self, is_secured: bool, groups: list, operation: RequestOperation, secured_operation: SecuredOperation):
        """ Secures the feature type or removes the secured constraints

        Args:
            is_secured (bool): Whether to secure the feature type or not
            groups (list): The list of groups which are allowed to perform an operation
            operation (RequestOperation): The operation which can be allowed
        Returns:

        """
        self.metadata.is_secured = is_secured
        if is_secured:
            sec_op = SecuredOperation()
            sec_op.operation = operation
            sec_op.save()
            for g in groups:
                sec_op.allowed_groups.add(g)
            self.metadata.secured_operations.add(sec_op)
        else:
            for sec_op in self.metadata.secured_operations.all():
                sec_op.delete()
            self.metadata.secured_operations.clear()
        self.metadata.save()
        self.save()

    def restore(self):
        """ Reset the metadata to it's original capabilities content

        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper
        if self.parent_service is None:
            return
        service_version = service_helper.resolve_version_enum(self.parent_service.service_type.version)
        service = None
        if self.parent_service.is_service_type(OGCServiceEnum.WFS):
            service = OGCWebFeatureServiceFactory()
            service = service.get_ogc_wfs(version=service_version, service_connect_url=self.parent_service.metadata.capabilities_original_uri)
        if service is None:
            return
        service.get_capabilities()
        service.get_single_feature_type_metadata(self.metadata.identifier)
        result = service.feature_type_list.get(self.metadata.identifier, {})
        original_ft = result.get("feature_type")
        keywords = result.get("keyword_list")

        # now restore the "metadata"
        self.title = original_ft.title
        self.abstract = original_ft.abstract
        self.metadata.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.metadata.keywords.add(keyword)
        self.is_custom = False


class FeatureTypeElement(Resource):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name


class Namespace(models.Model):
    name = models.CharField(max_length=50)
    version = models.CharField(max_length=50, blank=True, null=True)
    uri = models.CharField(max_length=500)

    def __str__(self):
        return self.name + " (" + self.uri + ")"
