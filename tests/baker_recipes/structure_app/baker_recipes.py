import os
from django.contrib.auth.hashers import make_password
from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key, related
from structure.models import MrMapUser, Theme, Role, Permission, MrMapGroup, Organization, PendingRequest
from tests.test_data import get_password_data

salt = str(os.urandom(25).hex())
PASSWORD = get_password_data().get('valid')
EMAIL = "test@example.com"


light_theme = Recipe(
    Theme,
    name=seq("LIGHT")
)

superadmin_permission = Recipe(
    Permission,
    can_create_organization=True,
    can_edit_organization=True,
    can_delete_organization=True,
    can_create_group=True,
    can_delete_group=True,
    can_edit_group=True,
    can_add_user_to_group=True,
    can_remove_user_from_group=True,
    can_edit_group_role=True,
    can_activate_service=True,
    can_update_service=True,
    can_register_service=True,
    can_remove_service=True,
    can_edit_metadata_service=True,
    can_toggle_publish_requests=True,
    can_remove_publisher=True,
    can_request_to_become_publisher=True,
)

guest_permission = Recipe(
    Permission,
    can_create_organization=False,
    can_edit_organization=False,
    can_delete_organization=False,
    can_create_group=False,
    can_delete_group=False,
    can_edit_group=False,
    can_add_user_to_group=False,
    can_remove_user_from_group=False,
    can_edit_group_role=False,
    can_activate_service=False,
    can_update_service=False,
    can_register_service=False,
    can_remove_service=False,
    can_edit_metadata_service=False,
    can_toggle_publish_requests=False,
    can_remove_publisher=False,
    can_request_to_become_publisher=False,
)

superadmin_role = Recipe(
    Role,
    name="superadmin_role",
    permission=foreign_key(superadmin_permission)
)

guest_role = Recipe(
    Role,
    name="guest_role",
    permission=foreign_key(guest_permission)
)


god_user = Recipe(
    MrMapUser,
    username="God",
    email="god@heaven.va",
    salt=salt,
    password=make_password("354Dez25!"),
    is_active=True,
    theme=foreign_key(light_theme),
)

guest_group = Recipe(
    MrMapGroup,
    role=foreign_key(guest_role),
    created_by=foreign_key(god_user),
)

active_testuser = Recipe(
    MrMapUser,
    username="Testuser",
    email="test@example.com",
    salt=salt,
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    theme=foreign_key(light_theme),
    groups=related(guest_group)
)

inactive_testuser = active_testuser.extend(
    is_active=False,
)

superadmin_group = Recipe(
    MrMapGroup,
    name="_root_",
    role=foreign_key(superadmin_role),
    created_by=foreign_key(god_user),
)

superadmin_user = Recipe(
    MrMapUser,
    username="Testuser",
    email="test@example.com",
    salt=salt,
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    theme=foreign_key(light_theme),
    groups=related(superadmin_group)
)

non_autogenerated_orga = Recipe(
    Organization,
    is_auto_generated=False,
)

pending_request = Recipe(
    PendingRequest,
    group=foreign_key(superadmin_group),
    organization=foreign_key(non_autogenerated_orga),

)