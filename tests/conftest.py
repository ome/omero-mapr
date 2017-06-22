#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#
#
# Copyright (c) 2016,2017 University of Dundee.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Aleksandra Tarkowska <A(dot)Tarkowska(at)dundee(dot)ac(dot)uk>.
#
# Version: 1.0
#

import os
import json
import django
import pytest

from django.conf import settings
from omero_mapr.utils import config_list_to_dict

from omero_mapr.testlib import IMaprTest

# We manually designate which settings we will be using in an environment
# variable. This is similar to what occurs in the `manage.py`
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'omeroweb.settings')


# `pytest` automatically calls this function once when tests are run.
def pytest_configure():
    settings.DEBUG = False
    settings.MAPR_CONFIG = config_list_to_dict(json.dumps(
        [
            {
                "menu": "gene",
                "config": {
                    "default": ["Gene Symbol"],
                    "all": ["Gene Symbol", "Gene Identifier"],
                    "ns": ["openmicroscopy.org/mapr/gene"],
                    "label": "Gene",
                    "case_sensitive": True,
                }
            },
            {
                "menu": "phenotype",
                "config": {
                    "default": ["Phenotype"],
                    "all": ["Phenotype", "Phenotype Term Accession"],
                    "ns": ["openmicroscopy.org/mapr/phenotype"],
                    "label": "Phenotype",
                }
            },
            {
                "menu": "organism",
                "config": {
                    "default": ["Organism"],
                    "all": ["Organism"],
                    "ns": ["openmicroscopy.org/mapr/organism"],
                    "label": "Organism",
                }
            },
            {
                "menu": "others",
                "config": {
                    "default": ["Others"],
                    "all": ["Others"],
                    "ns": ["openmicroscopy.org/omero/bulk_annotations"],
                    "label": "Others",
                }
            }
        ]
    ))
    django.setup()


@pytest.fixture
def itest(request):
    """
    Returns a new L{weblibrary.IMaprTest} instance. With attached
    finalizer so that pytest will clean it up.
    """
    IMaprTest.setup_class()

    def finalizer():
        IMaprTest.teardown_class()
    request.addfinalizer(finalizer)
    return IMaprTest()


@pytest.fixture(scope="session")
def imaprtest(request):
    """
    Returns a new L{weblibrary.IMaprTest} instance and
    populate metadata. Attached finalizer so that pytest
    will clean it up.
    """
    IMaprTest.setup_class()

    def finalizer():
        IMaprTest.teardown_class()
    request.addfinalizer(finalizer)

    imt = IMaprTest()
    csv = os.path.join(
        os.path.dirname(__file__), 'integration',
        'bulk_to_map_annotation_context_ns.csv')
    cfg = os.path.join(
        os.path.dirname(__file__), 'integration',
        'bulk_to_map_annotation_context.yml')
    imt.populate_data(csv, cfg)
    return imt
