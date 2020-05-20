from django.forms import ModelForm, forms


class MrMapModelForm(ModelForm):
    def __init__(self, action_url, *args, **kwargs):
        """
            @keyword action_url: the action_url is a mandatory keyword, which is used in our modal-form skeleton to
            dynamically configure the right action_url for the form
        """
        # first call parent's constructor
        super(MrMapModelForm, self).__init__(*args, **kwargs)
        self.action_url = action_url


class MrMapForm(forms.Form):
    def __init__(self, action_url, *args, **kwargs):
        """
            @keyword action_url: the action_url is a mandatory keyword, which is used in our modal-form skeleton to
            dynamically configure the right action_url for the form
        """
        # first call parent's constructor
        super(MrMapForm, self).__init__(*args, **kwargs)
        self.action_url = action_url
