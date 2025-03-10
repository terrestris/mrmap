"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
from celery import shared_task
from celery.exceptions import Reject
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django_celery_results.models import TaskResult

from csw.models import HarvestResult
from csw.settings import csw_logger, CSW_GENERIC_ERROR_TEMPLATE
from csw.utils.harvester import Harvester
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import MrMapGroup


@shared_task(name="async_harvest")
def async_harvest(harvest_result_id: int):
    """ Performs the harvesting procedure in a background celery task

    Args:
        harvest_result_id (int):
    Returns:

    """
    try:
        harvest_result = HarvestResult.objects\
            .select_related('metadata',
                            'metadata__service__created_by__mrmapgroup')\
            .get(pk=harvest_result_id)
        try:
            harvester = Harvester(harvest_result,
                                  max_records_per_request=1000)
            harvester.harvest()

        except IntegrityError as e:
            csw_logger.error(
                CSW_GENERIC_ERROR_TEMPLATE.format(
                    harvest_result.metadata.title,
                    e
                )
            )
    except ObjectDoesNotExist:
        # todo: logging
        pass

