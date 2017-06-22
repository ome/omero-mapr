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

import pytest
import json

from django.core.urlresolvers import reverse, NoReverseMatch

from omeroweb.testlib import IWebTest, _get_response, _get_response_json
from omero_mapr.utils import config_list_to_dict


@pytest.fixture
def empty_settings(settings):
    settings.MAPR_CONFIG = {}


class TestMaprConfig(IWebTest):

    def test_settings(self, settings):
        assert len(settings.MAPR_CONFIG.keys()) > 0
        for menu in settings.MAPR_CONFIG.keys():
            request_url = reverse("maprindex_%s" % menu)
            _get_response(self.django_client, request_url, {}, status_code=200)

    @pytest.mark.xfail(raises=StopIteration)
    def test_empty_settings(self, empty_settings):
        # test empty config
        reverse("maprindex")

    @pytest.mark.parametrize('menu', ['foo', '', 'mygenes'])
    def test_bad_settings(self, settings, menu):
        assert menu not in settings.MAPR_CONFIG.keys()
        with pytest.raises(NoReverseMatch) as excinfo:
            request_url = reverse("maprindex_%s" % menu)
            _get_response(self.django_client, request_url, {}, status_code=200)
        regx = r"Reverse for 'maprindex_%s'.*" % menu
        assert excinfo.match(regx)


@pytest.fixture
def wildcard_settings(settings):
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
                    "wildcard": {
                        "enabled": False
                    }
                }
            },
            {
                "menu": "organism",
                "config": {
                    "default": ["Organism"],
                    "all": ["Organism"],
                    "ns": ["openmicroscopy.org/mapr/organism"],
                    "label": "Organism",
                    "wildcard": {
                        "enabled": True
                    }
                }
            },
        ]
    ))


class TestMaprViewsConfig(IWebTest):

    # Test wildcard_settings
    @pytest.mark.parametrize('params', [
        {'menu': 'organism', 'childCount': 4},
        {'menu': 'gene', 'childCount': None},
        {'menu': 'phenotype', 'childCount': None},
    ])
    def test_api_experimenter_list_wildcard(self, imaprtest,
                                            wildcard_settings, params):
        request_url = reverse("mapannotations_api_experimenters",
                              args=[params['menu']])
        response = _get_response_json(
            imaprtest.django_client, request_url, {})
        if params['childCount'] is not None:
            assert response['experimenter']['childCount'] == \
                params['childCount']
        else:
            with pytest.raises(KeyError) as excinfo:
                response['experimenter']['childCount']
            assert excinfo.match("'childCount'")

    @pytest.mark.parametrize('params', [
        {'menu': 'organism', 'count': 4},
        {'menu': 'gene', 'count': None},
        {'menu': 'phenotype', 'count': None},
    ])
    def test_api_mapannotations_wildcard(self, imaprtest,
                                         wildcard_settings, params):
        request_url = reverse("mapannotations_api_mapannotations",
                              args=[params['menu']])
        response = _get_response_json(
            imaprtest.django_client, request_url, {})
        if params['count'] is not None:
            assert len(response['screens']) == params['count']
            assert len(response['maps']) == 0
            assert len(response['projects']) == 0
            for r in response['screens']:
                assert r['name'].startswith("Screen001")
                assert r['childCount'] == 1
        else:
            assert response == {u'screens': [], u'maps': [], u'projects': []}
