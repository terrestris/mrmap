import os
import random

from celery import states
from django.contrib.auth.hashers import make_password
from django_celery_results.models import TaskResult
from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key, related
from structure.models import Organization, PublishRequest, GroupInvitationRequest
from structure.models import MrMapUser, MrMapGroup
from structure.settings import SUPERUSER_GROUP_NAME, PUBLIC_GROUP_NAME
from tests.test_data import get_password_data


salt = str(os.urandom(25).hex())
PASSWORD = get_password_data().get('valid')
EMAIL = "test@example.com"


god_user = Recipe(
    MrMapUser,
    username="God",
    email="god@heaven.va",
    salt=salt,
    password=make_password("354Dez25!"),
    is_active=True,
)

superadmin_orga = Recipe(
    Organization,
    organization_name=seq("SuperOrganization"),
    is_auto_generated=False
)

superadmin_group = Recipe(
    MrMapGroup,
    name=SUPERUSER_GROUP_NAME,
    created_by=foreign_key(god_user),
    organization=foreign_key(superadmin_orga)
)

public_group = Recipe(
    MrMapGroup,
    name=PUBLIC_GROUP_NAME,
    description="Public",
    is_public_group=True,
    created_by=foreign_key(god_user),
)

superadmin_user = Recipe(
    MrMapUser,
    username="Superuser",
    email="test@example.com",
    salt=salt,
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    groups=related(superadmin_group),
    organization=foreign_key(superadmin_orga),
    is_superuser=True
)

non_autogenerated_orga = Recipe(
    Organization,
    organization_name=seq("RealOrg"),
    is_auto_generated=False,
)

guest_group = Recipe(
    MrMapGroup,
    name=seq("GuestGroup", increment_by=int(random.random() * 100)),
    description=seq("Description"),
    #created_by=foreign_key(god_user),
)

active_testuser = Recipe(
    MrMapUser,
    username="Testuser",
    email="test@example.com",
    salt=salt,
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    groups=related(guest_group)
)

inactive_testuser = active_testuser.extend(
    is_active=False,
)

publish_request = Recipe(
    PublishRequest,
    group=foreign_key(superadmin_group),
    organization=foreign_key(non_autogenerated_orga),
)

group_invitation_request = Recipe(
    GroupInvitationRequest,
    to_group=foreign_key(superadmin_group),
    invited_user=foreign_key(active_testuser),
    message="Test",
)

pending_task = Recipe(
    TaskResult,
    status=states.STARTED,
    task_id=1
)
