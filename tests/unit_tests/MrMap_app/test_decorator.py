"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.04.20

"""
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.test import TestCase, Client, RequestFactory

from MrMap.decorator import log_proxy, check_permission, check_ownership, resolve_metadata_public_id
from service.models import Metadata, ProxyLog, Service
from structure.models import MrMapGroup, Organization, Permission
from structure.permissionEnums import PermissionEnum
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_testuser, \
    create_non_autogenerated_orgas
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD

TEST_URI = "http://test.com?request=GetTest"
TEST_URI_LOG_STRING = "/?request=GetTest"
MSG_PERMISSION_CHECK_FALSE_POSITIVE = "Testuser without permissions passed @check_permission"
MSG_PERMISSION_CHECK_TRUE_NEGATIVE = "Testuser with permissions did not pass @check_permission"


class DecoratorTestCase(TestCase):
    def setUp(self):
        self.default_user = create_testuser()
        self.user = create_superadminuser()
        self.user.organization = create_non_autogenerated_orgas(user=self.user, how_much_orgas=1)[0]
        self.user.save()

        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.request_factory = RequestFactory()

        self.wms_services = create_wms_service(
            group=self.user.get_groups().first(),
            how_much_services=1
        )

        # Setup for log proxy test
        self.metadata = Metadata.objects.all().first()
        self.metadata.use_proxy_uri = True
        self.metadata.log_proxy_access = True
        self.metadata.save()
        self.metadata.refresh_from_db()

    def test_check_permission(self):
        """ Tests whether the permission properly checks for user permissions

        Returns:

        """
        # Mock decorator usage
        @check_permission(PermissionEnum.CAN_CREATE_ORGANIZATION)
        def test_function(request, *args, **kwargs):
            return HttpResponse()

        # Testuser permission check without any permissions must fail
        # Mock the request
        request = self.request_factory.get(
            TEST_URI,
        )
        request.user = self.default_user

        # add support for message middleware
        session_middleware = SessionMiddleware()
        session_middleware.process_request(request)
        request.session.save()
        request.META["HTTP_REFERER"] = "/"
        # adding messages
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = test_function(request)

        # Expect a redirect
        self.assertEqual(response.status_code, 302, msg=MSG_PERMISSION_CHECK_FALSE_POSITIVE)

        # Give Testuser group permission
        user_groups = self.default_user.get_groups()
        first_group = user_groups.first()
        create_org_perm = Permission.objects.get_or_create(name=PermissionEnum.CAN_CREATE_ORGANIZATION.value)[0]
        first_group.role.permissions.add(create_org_perm)

        # Testuser permission check with permission must run
        # Mock the request
        response = test_function(request)

        # Expect a 200
        self.assertEqual(response.status_code, 200, msg=MSG_PERMISSION_CHECK_TRUE_NEGATIVE)

    def test_check_ownership_of_resource(self):
        """ Tests whether the ownership properly checks for resource

        Returns:

        """

        # Mock the usage of the decorator
        @check_ownership(
            klass=Service,
            id_name='service_id'
        )
        def test_function(request, service_id, *args, **kwargs):
            return HttpResponse()

        requested_service = self.wms_services[0].service

        # Testuser permission check without any permissions must fail
        # Mock the request
        request = self.request_factory.get(
            "http://test.com/{}".format(requested_service.id),
        )
        request.user = self.default_user

        # add support for message middleware
        session_middleware = SessionMiddleware()
        session_middleware.process_request(request)
        request.session.save()
        request.META["HTTP_REFERER"] = "/"
        # adding messages
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = test_function(request, service_id=requested_service.id)
        self.assertEqual(response.status_code, 303, msg="")

        request.user = self.user

        response = test_function(request, service_id=requested_service.id)
        self.assertEqual(response.status_code, 200, msg="")

    def test_check_ownership_of_mr_map_group(self):
        """ Tests whether the ownership properly checks for mr map group

        Returns:

        """

        # Mock the usage of the decorator
        @check_ownership(
            klass=MrMapGroup,
            id_name='group_id'
        )
        def test_function(request, group_id, *args, **kwargs):
            return HttpResponse()

        requested_group = self.user.get_groups()[0]

        # Testuser permission check without any permissions must fail
        # Mock the request
        request = self.request_factory.get(
            "http://test.com/{}".format(requested_group.id),
        )
        request.user = self.default_user

        # add support for message middleware
        session_middleware = SessionMiddleware()
        session_middleware.process_request(request)
        request.session.save()
        request.META["HTTP_REFERER"] = "/"
        # adding messages
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = test_function(request, group_id=requested_group.id)
        self.assertEqual(response.status_code, 303, msg="")

        request.user = self.user

        response = test_function(request, group_id=requested_group.id)
        self.assertEqual(response.status_code, 200, msg="")

    def test_check_ownership_of_organization(self):
        """ Tests whether the ownership properly checks for organization

        Returns:

        """

        # Mock the usage of the decorator
        @check_ownership(
            klass=Organization,
            id_name='org_id'
        )
        def test_function(request, org_id, *args, **kwargs):
            return HttpResponse()

        requested_organization = self.user.organization

        # Testuser permission check without any permissions must fail
        # Mock the request
        request = self.request_factory.get(
            "http://test.com/{}".format(requested_organization.id),
        )
        request.user = self.default_user

        # add support for message middleware
        session_middleware = SessionMiddleware()
        session_middleware.process_request(request)
        request.session.save()
        request.META["HTTP_REFERER"] = "/"
        # adding messages
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = test_function(request, org_id=requested_organization.id)
        self.assertEqual(response.status_code, 303, msg="")

        request.user = self.user

        response = test_function(request, org_id=requested_organization.id)
        self.assertEqual(response.status_code, 200, msg="")

    def test_log_proxy(self):
        """ Tests whether the responses of a service is properly logged

        Returns:

        """
        # Mock the usage of the decorator
        @log_proxy
        def test_function(request, *args, **kwargs):
            return HttpResponse()

        # Check that there is no ProxyLog record yet
        try:
            ProxyLog.objects.get(
                metadata=self.metadata
            )
            self.fail("@log_proxy did already exist before creation")
        except ObjectDoesNotExist:
            self.assertTrue(True)

        # Mock the request and logging
        request = self.request_factory.get(
            TEST_URI,
        )
        request.user = self.user
        test_function(request, metadata_id=self.metadata.id)

        # Check again for proxy log
        try:
            proxy_log = ProxyLog.objects.get(
                metadata=self.metadata
            )
        except ObjectDoesNotExist:
            self.fail(msg="@log_proxy did not create ProxyLog record")

        # Check that everything we provided is in its place
        self.assertIsInstance(proxy_log, ProxyLog, msg="proxy_log record is not a ProxyLog instance")
        self.assertEqual(proxy_log.user, self.user, msg="Another user has been related to the ProxyLog record")
        self.assertEqual(proxy_log.uri, TEST_URI_LOG_STRING, msg="The uri has not been stored correctly into the ProxyLog record")

    def test_resolve_metadata_public_id(self):
        """ Tests whether the public_id of a metadata can be resolved into the regular one.

        Returns:

        """
        # Mock the usage of the decorator
        @resolve_metadata_public_id
        def test_function(request, *args, **kwargs):
            return HttpResponse(content=kwargs.get("metadata_id", None))

        requested_md = self.metadata
        request = self.request_factory.get(
            "http://test.com/{}".format(requested_md.id),
        )
        request.user = self.default_user

        # Add a public_id
        self.metadata.public_id = "TEST_PUBLIC_ID"
        self.metadata.save()

        response = test_function(request, metadata_id=str(self.metadata.id))
        self.assertEqual(response.content.decode("UTF-8"), str(self.metadata.id))
        response = test_function(request, metadata_id=self.metadata.public_id)
        self.assertEqual(response.content.decode("UTF-8"), str(self.metadata.id))
