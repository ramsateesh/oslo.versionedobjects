# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Nova base exception handling.

Includes decorator for re-raising Nova-type exceptions.

SHOULD include dedicated exception logging.

"""

import functools
import logging
import sys

from oslo_config import cfg
from oslo_utils import excutils
import webob.exc

from oslo_versionedobjects._i18n import _, _LE
from oslo_versionedobjects import safe_utils

LOG = logging.getLogger(__name__)

exc_log_opts = [
    cfg.BoolOpt('fatal_exception_format_errors',
                default=False,
                help='Make exception message format errors fatal'),
]

CONF = cfg.CONF
CONF.register_opts(exc_log_opts)


class ConvertedException(webob.exc.WSGIHTTPException):
    def __init__(self, code=0, title="", explanation=""):
        self.code = code
        self.title = title
        self.explanation = explanation
        super(ConvertedException, self).__init__()


def _cleanse_dict(original):
    """Strip all admin_password, new_pass, rescue_pass keys from a dict."""
    return dict([(k, v) for k, v in original.iteritems() if "_pass" not in k])


def wrap_exception(notifier=None, get_notifier=None):
    """This decorator wraps a method to catch any exceptions that may
    get thrown. It also optionally sends the exception to the notification
    system.
    """
    def inner(f):
        def wrapped(self, context, *args, **kw):
            # Don't store self or context in the payload, it now seems to
            # contain confidential information.
            try:
                return f(self, context, *args, **kw)
            except Exception as e:
                with excutils.save_and_reraise_exception():
                    if notifier or get_notifier:
                        payload = dict(exception=e)
                        call_dict = safe_utils.getcallargs(f, context,
                                                           *args, **kw)
                        cleansed = _cleanse_dict(call_dict)
                        payload.update({'args': cleansed})

                        # If f has multiple decorators, they must use
                        # functools.wraps to ensure the name is
                        # propagated.
                        event_type = f.__name__

                        (notifier or get_notifier()).error(context,
                                                           event_type,
                                                           payload)

        return functools.wraps(f)(wrapped)
    return inner


class NovaException(Exception):
    """Base Nova Exception

    To correctly use this class, inherit from it and define
    a 'msg_fmt' property. That msg_fmt will get printf'd
    with the keyword arguments provided to the constructor.

    """
    msg_fmt = _("An unknown exception occurred.")
    code = 500
    headers = {}
    safe = False

    def __init__(self, message=None, **kwargs):
        self.kwargs = kwargs

        if 'code' not in self.kwargs:
            try:
                self.kwargs['code'] = self.code
            except AttributeError:
                pass

        if not message:
            try:
                message = self.msg_fmt % kwargs

            except Exception:
                exc_info = sys.exc_info()
                # kwargs doesn't match a variable in the message
                # log the issue and the kwargs
                LOG.exception(_LE('Exception in string format operation'))
                for name, value in kwargs.iteritems():
                    LOG.error("%s: %s" % (name, value))    # noqa

                if CONF.fatal_exception_format_errors:
                    raise exc_info[0], exc_info[1], exc_info[2]
                else:
                    # at least get the core message out if something happened
                    message = self.msg_fmt

        super(NovaException, self).__init__(message)

    def format_message(self):
        # NOTE(mrodden): use the first argument to the python Exception object
        # which should be our full NovaException message, (see __init__)
        return self.args[0]


class ObjectActionError(NovaException):
    msg_fmt = _('Object action %(action)s failed because: %(reason)s')


class ObjectFieldInvalid(NovaException):
    msg_fmt = _('Field %(field)s of %(objname)s is not an instance of Field')


class OrphanedObjectError(NovaException):
    msg_fmt = _('Cannot call %(method)s on orphaned %(objtype)s object')


class IncompatibleObjectVersion(NovaException):
    msg_fmt = _('Version %(objver)s of %(objname)s is not supported')


class ReadOnlyFieldError(NovaException):
    msg_fmt = _('Cannot modify readonly field %(field)s')


class UnsupportedObjectError(NovaException):
    msg_fmt = _('Unsupported object type %(objtype)s')
