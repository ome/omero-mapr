#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#
#
# Copyright (c) 2016 University of Dundee.
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
import pytest

from django.core.urlresolvers import reverse

from omero.constants.namespaces import NSBULKANNOTATIONS
from omero.model import ScreenI
from omero.rtypes import rstring, unwrap
from omero.util.temp_files import create_path
from omero.util.populate_metadata import BulkToMapAnnotationContext
from omero.util.populate_metadata import ParsingContext

from omeroweb.testlib import IWebTest, _get_response_json


class IMaprTest(IWebTest):

    """
    Extends ITest
    """

    def create_csv(
        self,
        col_names="Well,Well Type,Concentration",
        row_data=("A1,Control,0", "A2,Treatment,10")
    ):

        csv_file_name = create_path("test", ".csv")
        csv_file = open(csv_file_name, 'w')
        try:
            csv_file.write(col_names)
            csv_file.write("\n")
            csv_file.write("\n".join(row_data))
        finally:
            csv_file.close()
        return str(csv_file_name)

    def set_name(self, obj, name):
        q = self.client.sf.getQueryService()
        up = self.client.sf.getUpdateService()
        obj = q.get(obj.__class__.__name__, obj.id.val)
        obj.setName(rstring(name))
        return up.saveAndReturnObject(obj)

    def create_screen(self, row_count, col_count):
        # TODO: remove 5.2 vs 5.3 compatibility
        try:
            plate = self.importPlates(plateRows=row_count,
                                      plateCols=col_count)[0]
        except AttributeError:
            plate = self.import_plates(plateRows=row_count,
                                       plateCols=col_count)[0]
        plate = self.set_name(plate, "Plate001")
        screen = ScreenI()
        screen.name = rstring("Screen001")
        screen.linkPlate(plate.proxy())
        return (self.client.sf.getUpdateService().saveAndReturnObject(screen),
                plate)

    def new_screen(self, name=None, description=None):
        """
        Creates a new screen object.
        :param name: The screen name. If None, a UUID string will be used
        :param description: The screen description
        """
        return self.new_object(ScreenI, name=name, description=description)

    def make_screen(self, name=None, description=None, client=None):
        """
        Creates a new screen instance and returns the persisted object.
        :param name: The screen name. If None, a UUID string will be used
        :param description: The screen description
        :param client: The client to use to create the object
        """
        if client is None:
            client = self.client
        screen = self.new_screen(name=name, description=description)
        return client.sf.getUpdateService().saveAndReturnObject(screen)

    def get_screen_annotations(self):
        query = """select s from Screen s
            left outer join fetch s.annotationLinks links
            left outer join fetch links.child
            where s.id=%s""" % self.screen.id.val
        qs = self.client.sf.getQueryService()
        screen = qs.findByQuery(query, None)
        anns = screen.linkedAnnotationList()
        return anns


class TestMapr(IMaprTest):

    def setup_method(self, method):
        row_count = 1
        col_count = 4
        self.screen, self.plate = self.create_screen(row_count, col_count)

        csv = os.path.join(os.path.dirname(__file__),
                           'bulk_to_map_annotation_context_ns.csv')

        ctx = ParsingContext(self.client, self.screen.proxy(), file=csv)
        ctx.parse()
        ctx.write_to_omero()

        cfg = os.path.join(
            os.path.dirname(__file__), 'bulk_to_map_annotation_context.yml')

        # Get file annotations
        anns = self.get_screen_annotations()
        # Only expect a single annotation which is a 'bulk annotation'
        assert len(anns) == 1
        table_file_ann = anns[0]
        assert unwrap(table_file_ann.getNs()) == NSBULKANNOTATIONS
        fileid = table_file_ann.file.id.val

        ctx = BulkToMapAnnotationContext(
            self.client, self.screen.proxy(), fileid=fileid, cfg=cfg)
        ctx.parse()
        ctx.write_to_omero()

    @pytest.mark.parametrize('ac', (
        {'menu': 'gene', 'value': 'CDC20', 'search_value': 'cdc'},
        {'menu': 'organism', 'value': 'Homo sapiens', 'search_value': 'homo'},
        {'menu': 'gene', 'value': "beta'Cop", 'search_value': "'"},
        {'menu': 'gene', 'value': "123 (abc\%def)", 'search_value': "%"},
    ))
    def test_autocomplete(self, ac):
        # test autocomplete
        request_url = reverse("mapannotations_autocomplete",
                              args=[ac['menu']])
        data = {
            'value': ac['search_value'],
            'query': 'true',
        }
        response = _get_response_json(self.django_client, request_url, data)

        assert response == [{'value': ac['value']}]
