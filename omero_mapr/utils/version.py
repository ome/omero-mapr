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
# Author: Aleksandra Tarkowska <A(dot)Tarkowska(at)dundee(dot)ac(dot)uk>, 2008.
#
# Version: 1.0


def get_version(version=None):

    """
    Returns a PEP 386-compliant version number.
    See https://www.python.org/dev/peps/pep-0440/
    """

    return get_full_version(version)


def get_full_version(version=None):

    """
    Returns a tuple of the mapr version.
    """

    if version is None:
        from omero_mapr import VERSION as version  # noqa
    return version
