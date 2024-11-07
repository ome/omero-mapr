#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
# Author: Aleksandra Tarkowska <A(dot)Tarkowska(at)dundee(dot)ac(dot)uk>,
#
# Version: 1.0

import logging
import traceback
import requests
from io import BytesIO
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

from Ice import Exception as IceException
from omero import ApiUsageException, ServerError

from django.conf import settings
from .mapr_settings import mapr_settings

from django.urls import reverse
from django.http import HttpResponseServerError, HttpResponseBadRequest
from django.http import JsonResponse
from django.http import Http404

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from django.utils.html import strip_tags

from django_redis import get_redis_connection

from omero.gateway.utils import toBoolean

from .show import mapr_paths_to_object
from .show import MapShow as Show
from .tree import count_mapannotations, \
                  marshal_mapannotations, \
                  marshal_screens, \
                  marshal_projects, \
                  marshal_datasets, \
                  marshal_plates, \
                  marshal_images, \
                  load_mapannotation, \
                  marshal_autocomplete

from omeroweb.webclient.decorators import login_required, render_response
from omeroweb.webclient.views import get_long_or_default, get_bool_or_default

from omeroweb.webclient import tree as webclient_tree
from omeroweb.webclient.views import _load_template as _webclient_load_template

from omeroweb.webclient.views import api_paths_to_object \
    as webclient_api_paths_to_object

try:
    # renamed for Django 1.11
    from omeroweb.httprsp import HttpJPEGResponse
except ImportError:
    # old name for backwards compatibility
    from omeroweb.http import HttpJPEGResponse

import omeroweb

logger = logging.getLogger(__name__)


try:
    from PIL import Image  # see ticket:2597
except ImportError:
    try:
        import Image  # see ticket:2597
    except ImportError:
        logger.error(
            "You need to install the Python Imaging Library. Get it at"
            " http://www.pythonware.com/products/pil/")
        logger.error(traceback.format_exc())


# Views Helpers
def fake_experimenter(label):
    """
    Marshal faked experimenter when id is -1
    Load omero.client.ui.menu.dropdown.everyone.label as username
    """
    return {
        'id': -1,
        'omeName': label,
        'firstName': label,
        'lastName': ''
    }


def get_unicode_or_default(request, name, default):
    """
    Retrieves a parameter from the request. If the parameter is not present
    the default is returned

    This does not catch exceptions as it makes sense to throw exceptions if
    the arguments provided do not pass basic type validation
    """
    val = None
    val_raw = request.GET.get(name, default)
    if val_raw is not None:
        val = strip_tags(val_raw)
    return val


def _get_wildcard(mapr_settings, menu):
    wc = False
    try:
        wc = mapr_settings.CONFIG[menu]['wildcard']['enabled']
    except KeyError:
        pass
    return wc


def _get_wildcard_limit(mapr_settings, menu):
    wc = 0
    try:
        wc = mapr_settings.CONFIG[menu]['wildcard']['limit']
    except KeyError:
        pass
    return wc


def _get_ns(mapr_settings, menu):
    ns = []
    try:
        ns = mapr_settings.CONFIG[menu]['ns']
    except KeyError:
        pass
    return ns


def _get_keys(mapr_settings, menu):
    keys = None
    try:
        keys = mapr_settings.CONFIG[menu]['all']
    except KeyError:
        pass
    return keys


def _get_case_sensitive(mapr_settings, menu):
    cs = False
    try:
        cs = toBoolean(mapr_settings.CONFIG[menu]['case_sensitive'])
    except KeyError:
        pass
    return cs


def _get_page(request):
    page = get_long_or_default(request, 'page', 1)
    if page < 1:
        page = 1
    return page


@login_required()
@render_response()
def index(request, menu, conn=None, url=None, **kwargs):
    """
    This override omeroweb.webclient.load_template
    to support custom template base_mapr.html
    """

    try:
        value = get_unicode_or_default(request, 'value', None)
        query = get_bool_or_default(request, 'query', False)
        if _get_case_sensitive(mapr_settings, menu):
            case_sensitive = get_bool_or_default(
                request, 'case_sensitive', False)
        else:
            case_sensitive = False
    except ValueError:
        logger.error(traceback.format_exc())
        return HttpResponseBadRequest('Invalid parameter value')
    kwargs['show'] = Show(conn=conn, request=request, menu=menu, value=value)
    kwargs['load_template_url'] = reverse(viewname="maprindex_%s" % menu)
    kwargs['template'] = "mapr/base_mapr.html"
    context = _webclient_load_template(request, menu,
                                       conn=conn, url=url, **kwargs)
    context['active_user'] = context.get('active_user', {'id': -1})
    context['mapr_conf'] = {
        'menu': menu,
        'menu_all': mapr_settings.CONFIG[menu]['all'],
        'menu_default': mapr_settings.CONFIG[menu]['default'],
        'case_sensitive': _get_case_sensitive(mapr_settings, menu)}
    context['map_ctx'] = \
        {'label': menu, 'value': value or "", 'query': query or "",
         'case_sensitive': case_sensitive or ""}
    context['template'] = "mapr/base_mapr.html"

    return context


def api_mapr_config(request):
    """Return mapr_settings.CONFIG as JSON."""
    return JsonResponse(mapr_settings.CONFIG)


@login_required()
def api_paths_to_object(request, menu=None, conn=None, **kwargs):
    """
    This override omeroweb.webclient.api_paths_to_object
    to support custom path to map.value
    """

    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        mapann_value = get_unicode_or_default(request, 'map.value', None)
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    if menu in mapr_settings.CONFIG and mapann_value:
        paths = []
        try:
            experimenter_id = get_long_or_default(request, 'experimenter',
                                                  None)
            project_id = get_long_or_default(request, 'project', None)
            dataset_id = get_long_or_default(request, 'dataset', None)
            image_id = get_long_or_default(request, 'image', None)
            screen_id = get_long_or_default(request, 'screen', None)
            plate_id = get_long_or_default(request, 'plate', None)
            group_id = get_long_or_default(request, 'group', None)
        except ValueError:
            return HttpResponseBadRequest('Invalid parameter value')

        paths = mapr_paths_to_object(
            conn=conn, mapann_value=mapann_value,
            mapann_ns=mapann_ns, mapann_names=mapann_names,
            screen_id=screen_id, plate_id=plate_id,
            project_id=project_id, dataset_id=dataset_id,
            image_id=image_id,
            experimenter_id=experimenter_id, group_id=group_id)

        return JsonResponse({'paths': paths})
    return webclient_api_paths_to_object(request, conn=conn, **kwargs)


omeroweb.webclient.views.api_paths_to_object = api_paths_to_object


@login_required()
def api_experimenter_list(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        # page = _get_page(request)
        # limit = get_long_or_default(request, 'limit', settings.PAGE)
        group_id = get_long_or_default(request, 'group', -1)
        experimenter_id = get_long_or_default(request, 'experimenter', -1)
        mapann_value = get_unicode_or_default(request, 'value', None) \
            or get_unicode_or_default(request, 'id', None)
        query = get_bool_or_default(request, 'query', False)
        if _get_case_sensitive(mapr_settings, menu):
            case_sensitive = get_bool_or_default(
                request, 'case_sensitive', False)
        else:
            case_sensitive = False
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    experimenter = {}
    try:
        if experimenter_id > -1:
            # Get the experimenter
            experimenter = webclient_tree.marshal_experimenter(
                conn=conn, experimenter_id=experimenter_id)
        else:
            # fake experimenter -1
            experimenter = fake_experimenter(
                mapr_settings.CONFIG[menu]['label'])

        if _get_wildcard(mapr_settings, menu) or mapann_value:
            experimenter['extra'] = {'case_sensitive': case_sensitive}
            if query:
                experimenter['extra']['query'] = query

            # count children
            experimenter['childCount'] = count_mapannotations(
                conn=conn,
                mapann_value=mapann_value,
                query=query,
                case_sensitive=case_sensitive,
                mapann_ns=mapann_ns,
                mapann_names=mapann_names,
                group_id=group_id,
                experimenter_id=experimenter_id)

            if experimenter['childCount'] > 0 and mapann_value:
                experimenter['extra']['value'] = mapann_value

    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse({'experimenter': experimenter})


@login_required()
def api_mapannotation_list(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        page = page = _get_page(request)
        limit = get_long_or_default(request, 'limit', settings.PAGE)
        group_id = get_long_or_default(request, 'group', -1)
        experimenter_id = get_long_or_default(request, 'experimenter_id', -1)
        mapann_value = get_unicode_or_default(request, 'id', None) \
            or get_unicode_or_default(request, 'value', None)
        query = get_bool_or_default(request, 'query', False)
        if _get_case_sensitive(mapr_settings, menu):
            case_sensitive = get_bool_or_default(
                request, 'case_sensitive', False)
        else:
            case_sensitive = False
        orphaned = get_bool_or_default(request, 'orphaned', False)
    except ValueError:
        logger.error(traceback.format_exc())
        return HttpResponseBadRequest('Invalid parameter value')

    mapannotations = []
    screens = []
    projects = []
    try:
        if _get_wildcard(mapr_settings, menu) or mapann_value:
            # Get attributes from map annotation
            if orphaned:
                # offset = _get_wildcard_limit(mapr_settings, menu)
                mapannotations = marshal_mapannotations(
                    conn=conn,
                    mapann_value=mapann_value,
                    query=query,
                    case_sensitive=case_sensitive,
                    mapann_ns=mapann_ns,
                    mapann_names=mapann_names,
                    group_id=group_id,
                    experimenter_id=experimenter_id,
                    page=page,
                    limit=limit)
            else:
                screens = marshal_screens(
                    conn=conn,
                    mapann_value=mapann_value,
                    query=query,
                    mapann_ns=mapann_ns,
                    mapann_names=mapann_names,
                    group_id=group_id,
                    experimenter_id=experimenter_id,
                    page=page,
                    limit=limit)
                projects = marshal_projects(
                    conn=conn,
                    mapann_value=mapann_value,
                    query=query,
                    mapann_ns=mapann_ns,
                    mapann_names=mapann_names,
                    group_id=group_id,
                    experimenter_id=experimenter_id,
                    page=page,
                    limit=limit)

    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse({'maps': mapannotations,
                         'screens': screens, 'projects': projects})


@login_required()
def api_datasets_list(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        page = _get_page(request)
        limit = get_long_or_default(request, 'limit', settings.PAGE)
        group_id = get_long_or_default(request, 'group', -1)
        experimenter_id = get_long_or_default(request,
                                              'experimenter_id', -1)
        project_id = get_long_or_default(request, 'id', None)
        mapann_value = get_unicode_or_default(request, 'value', None)
        query = get_bool_or_default(request, 'query', False)
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    datasets = []
    try:
        if _get_wildcard(mapr_settings, menu) or mapann_value:
            # Get the images
            datasets = marshal_datasets(
                conn=conn,
                project_id=project_id,
                mapann_value=mapann_value,
                query=query,
                mapann_ns=mapann_ns,
                mapann_names=mapann_names,
                group_id=group_id,
                experimenter_id=experimenter_id,
                page=page,
                limit=limit)
    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse({'datasets': datasets})


@login_required()
def api_plate_list(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        page = _get_page(request)
        limit = get_long_or_default(request, 'limit', settings.PAGE)
        group_id = get_long_or_default(request, 'group', -1)
        experimenter_id = get_long_or_default(request,
                                              'experimenter_id', -1)
        screen_id = get_long_or_default(request, 'id', None)
        mapann_value = get_unicode_or_default(request, 'value', None)
        query = get_bool_or_default(request, 'query', False)
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    plates = []
    try:
        if _get_wildcard(mapr_settings, menu) or mapann_value:
            # Get the images
            plates = marshal_plates(
                conn=conn,
                screen_id=screen_id,
                mapann_value=mapann_value,
                query=query,
                mapann_ns=mapann_ns,
                mapann_names=mapann_names,
                group_id=group_id,
                experimenter_id=experimenter_id,
                page=page,
                limit=limit)
    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse({'plates': plates})


@login_required()
def api_image_list(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        page = _get_page(request)
        limit = get_long_or_default(request, 'limit', settings.PAGE)
        group_id = get_long_or_default(request, 'group', -1)
        load_pixels = get_bool_or_default(request, 'sizeXYZ', False)
        thumb_version = get_bool_or_default(request, 'thumbVersion', False)
        date = get_bool_or_default(request, 'date', False)
        experimenter_id = get_long_or_default(request,
                                              'experimenter_id', -1)
        parent = get_unicode_or_default(request, 'node', None)
        parent_id = get_long_or_default(request, 'id', None)
        mapann_value = get_unicode_or_default(request, 'value', None)
        query = get_bool_or_default(request, 'query', False)
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    images = []
    try:
        if _get_wildcard(mapr_settings, menu) or mapann_value:
            # Get the images
            images = marshal_images(
                conn=conn,
                parent=parent,
                parent_id=parent_id,
                mapann_ns=mapann_ns,
                mapann_names=mapann_names,
                mapann_value=mapann_value,
                query=query,
                load_pixels=load_pixels,
                group_id=group_id,
                experimenter_id=experimenter_id,
                page=page,
                date=date,
                thumb_version=thumb_version,
                limit=limit)
    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse({'images': images})


@login_required()
@render_response()
def load_metadata_details(request, c_type, conn=None, share_id=None,
                          **kwargs):
    """
    This page is the right-hand panel 'general metadata', first tab only.
    Shown for Projects, Datasets, Images, Screens, Plates, Wells, Tags etc.
    The data and annotations are loaded by the manager. Display of appropriate
    data is handled by the template.
    """

    c_id = None
    try:
        c_id = get_unicode_or_default(request, 'value', None)
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    template = "mapr/metadata_general.html"

    context = dict()
    context['template'] = template
    context['menu'] = c_type
    context['manager'] = {'obj_type': 'map', 'obj_id': c_id}
    context['maprindex'] = reverse(viewname=('maprindex'))
    context['maprindex_path'] = reverse(viewname=('maprindex_%s' % c_type))
    return context


@login_required()
def api_annotations(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)

        mapann_value = get_unicode_or_default(request, 'map', None)
        mapann_names = _get_keys(mapr_settings, menu)
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    anns = []
    exps = []
    try:
        anns, exps = load_mapannotation(
            conn=conn,
            mapann_ns=mapann_ns,
            mapann_names=mapann_names,
            mapann_value=mapann_value)
    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse({'annotations': anns, 'experimenters': exps})


@login_required()
def mapannotations_autocomplete(request, menu, conn=None, **kwargs):

    # Get parameters
    try:
        mapann_ns = _get_ns(mapr_settings, menu)
        mapann_names = _get_keys(mapr_settings, menu)

        page = _get_page(request)
        limit = get_long_or_default(request, 'limit', settings.PAGE)
        group_id = get_long_or_default(request, 'group', -1)
        experimenter_id = get_long_or_default(request, 'experimenter_id', -1)
        mapann_value = get_unicode_or_default(request, 'value', None)
        query = get_bool_or_default(request, 'query', True)
        if _get_case_sensitive(mapr_settings, menu):
            case_sensitive = get_bool_or_default(
                request, 'case_sensitive', False)
        else:
            case_sensitive = False
    except ValueError:
        return HttpResponseBadRequest('Invalid parameter value')

    autocomplete = []
    try:
        if mapann_value:
            autocomplete = marshal_autocomplete(
                conn=conn,
                mapann_value=mapann_value,
                query=query,
                case_sensitive=case_sensitive,
                mapann_ns=mapann_ns,
                mapann_names=mapann_names,
                group_id=group_id,
                experimenter_id=experimenter_id,
                page=page,
                limit=limit)
    except ApiUsageException as e:
        return HttpResponseBadRequest(e.serverStackTrace)
    except ServerError as e:
        return HttpResponseServerError(e.serverStackTrace)
    except IceException as e:
        return HttpResponseServerError(e.message)

    return JsonResponse(list(autocomplete), safe=False)


@login_required()
def mapannotations_favicon(request, conn=None, **kwargs):

    icon = None
    favdomain = "{0.scheme}://{0.netloc}/".format(
        urlparse(request.GET.get('u', None)))
    if favdomain is not None:
        validate = URLValidator()
        try:
            validate(favdomain)
        except ValidationError:
            return HttpResponseBadRequest('Invalid url')

        _cache_key = "favicon.%s" % favdomain

        cache = get_redis_connection("default")
        icon = cache.hget('favdomain', _cache_key)
        if icon is None:
            try:
                r = requests.get(
                    "%s%s" % (mapr_settings.FAVICON_WEBSERVICE, favdomain),
                    stream=True)
                if r.status_code == 200:
                    icon = r.content
                    cache.hset('favdomain', _cache_key, icon)
            finally:
                r.connection.close()
        if icon is not None:
            return HttpJPEGResponse(icon)

    with Image.open(mapr_settings.DEFAULT_FAVICON) as img:
        img.thumbnail((16, 16))
        f = BytesIO()
        img.save(f, "PNG")
        f.seek(0)
        return HttpJPEGResponse(f.read())
    raise Http404
