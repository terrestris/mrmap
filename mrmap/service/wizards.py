from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from MrMap.messages import NO_PERMISSION
from MrMap.validators import check_uri_is_reachable
from MrMap.wizards import MrMapWizard
from django.utils.translation import gettext_lazy as _
from service.forms import RegisterNewResourceWizardPage1, RegisterNewResourceWizardPage2
from service.helper import service_helper
from service.settings import service_logger
from structure.permissionEnums import PermissionEnum

FIRST_STEP_ID = "URL"
SECOND_STEP_ID = "Overview"

NEW_RESOURCE_WIZARD_FORMS = [
    (FIRST_STEP_ID, RegisterNewResourceWizardPage1),
    (SECOND_STEP_ID, RegisterNewResourceWizardPage2),
]


@method_decorator(login_required, name='dispatch')
class NewResourceWizard(PermissionRequiredMixin, MrMapWizard):
    success_url = reverse_lazy('resource:pending-tasks')
    permission_required = PermissionEnum.CAN_REGISTER_RESOURCE.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def __init__(self, *args, **kwargs):
        super().__init__(
            action_url=reverse('resource:add', ),
            title=_(format_html('<b>Add New Resource</b>')),
            *args,
            **kwargs)

    def get_success_url(self):
        return reverse('resource:pending-tasks') + f'?task_id={self.task.id}'

    def get_form_kwargs(self, step=None):
        if step == SECOND_STEP_ID:
            return {'request': self.request}
        else:
            return super().get_form_kwargs(step=step)

    def get_form_initial(self, step):
        initial = self.initial_dict.get(step, {})

        if step == SECOND_STEP_ID:
            service_url_data = self.storage.get_step_data(FIRST_STEP_ID)
            uri = service_url_data.get('{}-get_request_uri'.format(FIRST_STEP_ID))
            url_dict = service_helper.split_service_uri(uri)
            is_reachable, needs_authentication, status_code = check_uri_is_reachable(uri)
            initial.update({
                'ogc_request': url_dict["request"],
                'ogc_service': url_dict["service"].value,
                'ogc_version': url_dict["version"],
                'uri': url_dict["base_uri"],
                'service_needs_authentication': needs_authentication,
            })
        return initial

    def render_goto_step(self, goto_step, **kwargs):
        # if the current step is the first and step two has initial data, we have to overwrite the initial stored data
        # This is necessary for the following case:
        # The user inserts an url at step 1. The wizard initialize step two with the url_dict above.
        # The user decides to goto the step 1 backward and insert a new url with different data.
        # For that case the wizard doesn't get's his data from the initial data.
        # He will get his data from the storage. For that we have to store the new found initial data for step 2!
        if self.steps.current == FIRST_STEP_ID and self.storage.get_step_data(SECOND_STEP_ID):
            # initial data found for step two
            service_url_data = self.storage.get_step_data(FIRST_STEP_ID)
            uri = service_url_data.get('{}-get_request_uri'.format(FIRST_STEP_ID))
            url_dict = service_helper.split_service_uri(uri)
            is_reachable, needs_authentication, status_code = check_uri_is_reachable(uri)
            self.storage.set_step_data(SECOND_STEP_ID, {
                    'ogc_request': url_dict["request"],
                    'ogc_service': url_dict["service"].value,
                    'ogc_version': url_dict["version"],
                    'uri': url_dict["base_uri"],
                    'service_needs_authentication': needs_authentication,
                })
        return super().render_goto_step(goto_step=goto_step)

    def done(self, form_list, **kwargs):
        """ Iterates over all forms and fills the Metadata/Dataset records accordingly

        Args:
            form_list (FormList): An iterable list of forms
            kwargs:
        Returns:

        """
        for form in form_list:
            if isinstance(form, RegisterNewResourceWizardPage2):
                try:
                    self.task = service_helper.create_new_service(form, self.request.user)
                    messages.success(self.request, 'Async task was created to create new resource.')
                except Exception as e:
                    service_logger.exception(e, stack_info=True, exc_info=True)
                    messages.error(self.request, 'Something went wrong. See service.log for details.')
                finally:
                    return super().done(form_list, **kwargs)
