"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 27.04.20

"""
from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse

from MrMap.messages import METADATA_IS_ORIGINAL
from editor.forms import MetadataEditorForm

from service.helper.enums import ResourceOriginEnum, MetadataEnum
from service.models import Metadata
from service.tables import DatasetTable
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_public_organization
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD

EDITOR_METADATA_EDITOR_NAME = 'resource:edit'
EDITOR_ACCESS_EDITOR_NAME = 'resource:access-editor-wizard'

EDITOR_DATASET_INDEX_NAME = 'resource:datasets-index'
EDITOR_DATASET_WIZARD_NEW = 'editor:dataset-metadata-wizard-new'
EDITOR_DATASET_WIZARD_EDIT = 'resource:dataset-metadata-wizard-instance'
EDITOR_REMOVE_DATASET = 'resource:remove-dataset-metadata'


class EditorMetadataEditViewTestCase(TestCase):
    """ Test case for basic metadata editor view

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.groups.first(), how_much_services=1)

    def test_get_form_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        metadata = Metadata.objects.filter(
            metadata_type=MetadataEnum.SERVICE.value
        ).first()
        response = self.client.get(
            reverse(EDITOR_METADATA_EDITOR_NAME, args=(str(metadata.id),)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertIsInstance(response.context["form"], MetadataEditorForm)


class EditorAccessEditViewTestCase(TestCase):
    """ Test case for basic access editor view

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.groups.first(), how_much_services=10)

    def test_get_form_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        metadata = Metadata.objects.all().first()
        response = self.client.get(
            reverse(EDITOR_ACCESS_EDITOR_NAME, args=(str(metadata.id),)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="generic_views/base_extended/wizard.html")


class EditorDatasetWizardNewViewTestCase(TestCase):
    """ Test case for basic index view of WMS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.groups.first(), how_much_services=10)

    def test_get_wizard_new_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        response = self.client.get(
            reverse(EDITOR_DATASET_WIZARD_NEW,),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="generic_views/base_extended/wizard.html")


class EditorDatasetWizardInstanceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.organization = create_public_organization(user=self.user)
        self.wms_services = create_wms_service(group=self.user.groups.first(),
                                               how_much_services=10,
                                               contact=self.organization[0])

    def test_get_wizard_instance_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        datasets = self.user.get_datasets_as_qs().first()
        url = reverse(EDITOR_DATASET_WIZARD_EDIT, args=[datasets.id])
        response = self.client.get(
            url,
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="generic_views/base_extended/wizard.html")

    def test_step_and_save_wizard_instance_view(self):
        return
        # todo: refactor this testmonitoring
        datasets = self.user.get_datasets_as_qs()
        step_post_params = {"wizard_goto_step": "responsible party",
                            "dataset_wizard-current_step": "identification",
                            "identification-is_form_update": "False",
                            "identification-title": "Ahrhutstrasse",
                            "identification-abstract": "Bebauungsplan \"Ahrhutstraße\"",
                            "identification-language_code": "ger",
                            "identification-character_set_code": "utf8",
                            "identification-date_stamp": "2020-06-23",
                            "identification-created_by": self.user.groups.first().id}

        step2_post_params = {"wizard_goto_step": "classification",
                             "dataset_wizard-current_step": "responsible party",
                             "responsible party-is_form_update": "False",
                             "responsible party-organization": "",
                             }

        save_post_params = {"dataset_wizard-current_step": "classification",
                            "classification-is_form_update": "False",
                            "classification-keywords": [],
                            "wizard_save": "True"}
        url = reverse(EDITOR_DATASET_WIZARD_EDIT, args=[datasets[0].id])
        step_response = self.client.post(url,
                                         HTTP_REFERER=reverse('resource:datasets-index'),
                                         data=step_post_params,)
        self.assertEqual(step_response.status_code, 200, )
        self.assertTrue('name="dataset_wizard-current_step" value="responsible party"' in step_response.context['rendered_modal'], msg='The current step was not responsible party ')
        self.assertTemplateUsed(response=step_response, template_name="views/datasets_index.html")

        step2_response = self.client.post(reverse('resource:dataset-metadata-wizard-instance',
                                                  args=(datasets[0].id,)),
                                          HTTP_REFERER=reverse('resource:datasets-index'),
                                          data=step2_post_params,)

        self.assertEqual(step2_response.status_code, 200, )
        self.assertTrue('name="dataset_wizard-current_step" value="classification"' in step2_response.context['rendered_modal'], msg='The current step was not classification ')
        self.assertTemplateUsed(response=step2_response, template_name="views/datasets_index.html")

        save_response = self.client.post(reverse('resource:dataset-metadata-wizard-instance',
                                                 args=(datasets[0].id,))+"?current-view=resource:datasets-index",
                                         HTTP_REFERER=reverse('resource:datasets-index'),
                                         data=save_post_params,)

        # 303 is returned due to the FormWizard
        self.assertEqual(save_response.status_code, 303, )
        self.assertEqual('/resource/datasets/', save_response.url)


class EditorDatasetRemoveInstanceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(
            group=self.user.groups.first(),
            how_much_services=1,
            md_relation_origin=ResourceOriginEnum.EDITOR.value
        )

    def test_remove_instance_view(self):
        """ Test for checking whether the dataset is removed or not

        Returns:

        """
        datasets = self.user.get_datasets_as_qs()

        response = self.client.post(
            reverse('resource:remove-dataset-metadata', args=(datasets[0].id, )),
        )

        self.assertEqual(response.status_code, 302, )
        messages = [m.message for m in get_messages(response.wsgi_request)]
        # todo
        # self.assertIn("Dataset successfully deleted.", messages)


class EditorRestoreDatasetViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(group=self.user.groups.first(), how_much_services=10)

    def test_restore_non_custom_instance_view(self):
        """ Test for checking whether the dataset is restored or not

        Returns:

        """
        return
        # todo: currently this is not a unit test, cause ISOMetadata() resolves the metadata from remote...
        datasets = self.user.get_datasets_as_qs()

        response = self.client.post(
            reverse('resource:restore', args=(datasets[0].id,)),
            data={'is_confirmed': 'True'},
        )

        self.assertEqual(response.status_code, 303, )
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn(METADATA_IS_ORIGINAL, messages)
