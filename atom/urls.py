"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 02.09.2020

"""
from django.urls import path

from atom.views import index, get_service_feed, get_dataset_feed, get_service_feed_metadata, \
    get_dataset_feed_metadata, open_search, get_dataset

app_name = 'atom'
urlpatterns = [
    path('gui', index, name='atom-feed-index'),
    # atom feeds
    path('service-feed/<metadata_id>', get_service_feed, name='get-service-feed'),
    path('dataset-feed/<metadata_id>', get_dataset_feed, name='get-dataset-feed'),
    # iso 19139 metadata
    path('service-feed-metadata/<metadata_id>', get_service_feed_metadata, name='get-service-feed-metadata'),
    path('dataset-feed-metadata/<metadata_id>', get_dataset_feed_metadata, name='get-dataset-feed-metadata'),
    # opensearch
    path('search', open_search, name='opensearch'),
    # download
    path('download/<metadata_id>', get_dataset, name='get-dataset'),

]
