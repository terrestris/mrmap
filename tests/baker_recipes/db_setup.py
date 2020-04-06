from django.db.models import QuerySet
from model_bakery import baker
from model_bakery.recipe import related
from structure.models import MrMapGroup, MrMapUser, Organization
from service.helper.enums import MetadataEnum
from service.models import MetadataType
from structure.models import MrMapGroup


def create_testuser():
    return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser')


def create_superadminuser(groups: QuerySet = None):
    if groups is not None:
        return baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user',
                                 groups=groups)
    else:
        return baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user')


def create_wms_service(group: MrMapGroup, how_much_services: int = 1, how_much_sublayers: int = 1):
    service_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.SERVICE.value
    )[0]

    layer_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.LAYER.value
    )[0]

    root_service_metadatas = baker.make_recipe(
        'tests.baker_recipes.service_app.active_wms_service_metadata',
        created_by=group,
        _quantity=how_much_services,
        metadata_type=service_md_type,
    )

    for root_service_metadata in root_service_metadatas:
        root_service = baker.make_recipe(
            'tests.baker_recipes.service_app.active_root_wms_service',
            created_by=group,
            metadata=root_service_metadata
        )

        sublayer_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_layer_metadata',
            created_by=group,
            _quantity=how_much_sublayers,
            metadata_type=layer_md_type,
        )

        for sublayer_metadata in sublayer_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wms_sublayer',
                created_by=group,
                parent_service=root_service,
                metadata=sublayer_metadata,
            )

    return root_service_metadatas


def create_wfs_service(group: MrMapGroup, how_much_services: int = 1, how_much_featuretypes: int = 1):
    service_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.SERVICE.value
    )[0]

    feature_type_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.FEATURETYPE.value
    )[0]

    root_service_metadatas = baker.make_recipe(
        'tests.baker_recipes.service_app.active_wfs_service_metadata',
        created_by=group,
        _quantity=how_much_services,
        metadata_type=service_md_type,
    )

    for root_service_metadata in root_service_metadatas:
        root_service = baker.make_recipe(
            'tests.baker_recipes.service_app.active_root_wfs_service',
            created_by=group,
            metadata=root_service_metadata,
        )

        featuretype_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wfs_featuretype_metadata',
            created_by=group,
            _quantity=how_much_featuretypes,
            metadata_type=feature_type_md_type,
        )

        for featuretype_metadata in featuretype_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wfs_featuretype',
                created_by=group,
                parent_service=root_service,
                metadata=featuretype_metadata
            )

    return root_service_metadatas


def create_guest_groups(user: MrMapGroup = None, how_much_orgas: int = 1):
    if user is not None:
        return baker.make_recipe('tests.baker_recipes.structure_app.guest_group',
                                 created_by=user,
                                 _quantity=how_much_orgas)
    else:
        return baker.make_recipe('tests.baker_recipes.structure_app.guest_group',
                                 _quantity=how_much_orgas)


def create_non_autogenerated_orgas(user: MrMapUser, how_much_orgas: int = 1):
    return baker.make_recipe('tests.baker_recipes.structure_app.non_autogenerated_orga',
                             created_by=user,
                             _quantity=how_much_orgas)


def create_pending_request(group: MrMapGroup = None, orga: Organization = None, type_str: str = None, how_much_requests: int = 1):

    if group is not None and type_str is not None and orga is not None:
        return baker.make_recipe('tests.baker_recipes.structure_app.pending_request',
                                 group=group,
                                 type=type_str,
                                 organization=orga,
                                 _quantity=how_much_requests)
    else:
        return baker.make_recipe('tests.baker_recipes.structure_app.pending_request',
                                 _quantity=how_much_requests)


def create_pending_task(group: MrMapGroup, how_much_pending_tasks: int = 1):
    return baker.make_recipe('tests.baker_recipes.structure_app.pending_task',
                             created_by=group,
                             _quantity=how_much_pending_tasks)

