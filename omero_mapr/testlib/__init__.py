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

from omero.model import ScreenI
from omero.rtypes import rstring, unwrap
from omero.constants.namespaces import NSBULKANNOTATIONS
from omero.util.populate_metadata import BulkToMapAnnotationContext
from omero.util.populate_metadata import ParsingContext

from omeroweb.testlib import IWebTest


class IMaprTest(IWebTest):

    """
    Extends IWebTest (ITest)
    """

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
            plate = self.import_plates(plate_rows=row_count,
                                       plate_cols=col_count)[0]
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

    def populate_data(self, csv, cfg):
        row_count = 1
        col_count = 6
        self.screen, self.plate = self.create_screen(row_count, col_count)

        ctx = ParsingContext(self.client, self.screen.proxy(), file=csv)
        ctx.parse()
        ctx.write_to_omero()

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
