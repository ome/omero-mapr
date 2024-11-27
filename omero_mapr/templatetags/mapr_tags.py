#!/usr/bin/env python
# -*- coding: utf-8 -*-
# #!/usr/bin/env python
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
#

import logging
import json

from django import template
from django.utils.safestring import mark_safe
from ..mapr_settings import mapr_settings

register = template.Library()

logger = logging.getLogger(__name__)


@register.simple_tag
def mapr_menu_config():
    return mark_safe(json.dumps(mapr_settings.CONFIG))


@register.inclusion_tag("mapr/includes/right_panel_title.html",
                        takes_context=True)
def publication_title_from_kvp(context):
    """
    We try to load Key-Value pairs on an object in the 'manager' and show the
    'Publication Title' value
    """

    manager = context.get("manager", None)
    if not hasattr(manager, "_get_object"):
        return {}

    obj = context["manager"]._get_object()
    # We only try to show Publication Title for Projects/Screens
    if obj is None or obj.OMERO_CLASS not in ("Project", "Screen"):
        return {}

    title = ""
    for ann in obj.listAnnotations():
        if "MapAnnotationI" in str(ann.OMERO_TYPE):
            for kvp in ann.getValue():
                if kvp[0] == "Publication Title":
                    title = kvp[1]
                    break

    return {
        "title": title
    }
