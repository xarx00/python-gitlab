
from __future__ import print_function
from __future__ import absolute_import
import base64

from gitlab.base import *  # noqa
from gitlab import cli
from gitlab.exceptions import *  # noqa
from gitlab.mixins import *  # noqa
from gitlab import types
from gitlab import utils


class Bulk(RESTObject):
    _id_attr = None


class BulkManager(RESTManager):
    """Manager for work with the groups and projects hierarchy.

    This manager doesn't actually manage objects but provides helper functions
    for bulk operations over projects under a specified group.
    """
    _path = ''
    _obj_cls = Bulk

    @cli.register_custom_action('BulkManager', tuple(), ('full-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def test(self, **kwargs):
        gl = self.gitlab

        group = gl.bulk.group(full_path=kwargs['full_path'])
        print(group.subgroups.list())


    @cli.register_custom_action('BulkManager', ('full-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def group(self, **kwargs):
        gl = self.gitlab

        grpath = kwargs['full_path']
        grname = grpath[grpath.rfind('/')+1:]
        groups = gl.groups.list(search=grname, all_available=True)
        for group in groups:
            if group.full_path == grpath:
                return group
        raise exc.GitlabGetError(404)
        

    @cli.register_custom_action('BulkManager', ('full-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def status(self, **kwargs):
        """Get the status of all the geo nodes.

        Args:
            **kwargs: Extra options to send to the server (e.g. sudo)

        Raises:
            GitlabAuthenticationError: If authentication is not correct
            GitlabGetError: If the server failed to perform the request

        Returns:
            list: The status of all the geo nodes
        """
#        return self.gitlab.http_list('/geo_nodes/status', **kwargs)
        return self.gitlab.groups.list()
