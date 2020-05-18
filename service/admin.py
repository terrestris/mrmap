from django.contrib import admin

# Register your models here.
from django.contrib.admin import site

from service.admin_filter import MetadataTypeFilter
from service.models import *


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'title_EN', 'online_link', 'origin')


class CategoryOriginAdmin(admin.ModelAdmin):
    pass


class DimensionAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "extent")


class RequestOperationAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_name',)


class SecuredOperationAdmin(admin.ModelAdmin):
    list_display = ("id", 'secured_metadata', 'allowed_group', "operation")


class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'version')


class ModuleAdmin(admin.ModelAdmin):
    pass


class DatasetAdmin(admin.ModelAdmin):
    pass


class KeywordAdmin(admin.ModelAdmin):
    list_display = ('id', "keyword")


class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'related_metadata', 'is_active', 'created')


class MetadataOriginAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)


class MetadataTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'type',)


class MetadataAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'service', 'identifier', 'metadata_type', 'is_active', 'is_broken', 'contact', 'uuid')
    list_filter = ('metadata_type', 'is_active', 'is_broken')
    search_fields = ['title']


class MetadataRelationAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata_from', 'relation_type', 'metadata_to', 'origin')


class TermsOfUseAdmin(admin.ModelAdmin):
    pass


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'is_deleted',  'servicetype', 'metadata', 'parent_service', 'published_for')
    pass


class ReferenceSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'prefix', 'version')
    pass


class FeatureTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'parent_service')


class FeatureTypeElementAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type')


class LayerAdmin(admin.ModelAdmin):
    list_display = ('id', 'identifier', 'parent_service', 'parent_layer', 'last_modified')


class MimeTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation', 'mime_type')


class NamespaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'uri', 'version')


class ProxyLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'operation', 'user', 'response_wms_megapixel', 'response_wfs_num_features', 'timestamp')


class ExternalAuthenticationAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'auth_type')


class StyleAdmin(admin.ModelAdmin):
    list_display = ('id', 'layer',)


admin.site.register(Dimension, DimensionAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(RequestOperation, RequestOperationAdmin)
admin.site.register(SecuredOperation, SecuredOperationAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(CategoryOrigin, CategoryOriginAdmin)
admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
admin.site.register(MetadataOrigin, MetadataOriginAdmin)
admin.site.register(MetadataType, MetadataTypeAdmin)
admin.site.register(Metadata, MetadataAdmin)
admin.site.register(MetadataRelation, MetadataRelationAdmin)
admin.site.register(TermsOfUse, TermsOfUseAdmin)
admin.site.register(ReferenceSystem, ReferenceSystemAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(MimeType, MimeTypeAdmin)
admin.site.register(Layer, LayerAdmin)
admin.site.register(FeatureType, FeatureTypeAdmin)
admin.site.register(FeatureTypeElement, FeatureTypeElementAdmin)
admin.site.register(Namespace, NamespaceAdmin)
admin.site.register(ProxyLog, ProxyLogAdmin)
admin.site.register(ExternalAuthentication, ExternalAuthenticationAdmin)
admin.site.register(Style, StyleAdmin)
