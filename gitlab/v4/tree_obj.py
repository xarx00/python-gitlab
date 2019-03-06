
from __future__ import print_function
from __future__ import absolute_import
import base64

from gitlab.base import *  # noqa
from gitlab import cli
from gitlab.exceptions import *  # noqa
from gitlab.mixins import *  # noqa
from gitlab import types
from gitlab import utils


class Tree(SaveMixin, ObjectDeleteMixin, RESTObject):
    @cli.register_custom_action('GeoNode')
    @exc.on_http_error(exc.GitlabRepairError)
    def repair(self, **kwargs):
        """Repair the OAuth authentication of the geo node.

        Args:
            **kwargs: Extra options to send to the server (e.g. sudo)

        Raises:
            GitlabAuthenticationError: If authentication is not correct
            GitlabRepairError: If the server failed to perform the request
        """
        path = '/geo_nodes/%s/repair' % self.get_id()
        server_data = self.manager.gitlab.http_post(path, **kwargs)
        self._update_attrs(server_data)

    @cli.register_custom_action('GeoNode')
    @exc.on_http_error(exc.GitlabGetError)
    def status(self, **kwargs):
        """Get the status of the geo node.

        Args:
            **kwargs: Extra options to send to the server (e.g. sudo)

        Raises:
            GitlabAuthenticationError: If authentication is not correct
            GitlabGetError: If the server failed to perform the request

        Returns:
            dict: The status of the geo node
        """
        path = '/geo_nodes/%s/status' % self.get_id()
        return self.manager.gitlab.http_get(path, **kwargs)


class TreeManager(RetrieveMixin, UpdateMixin, DeleteMixin, RESTManager):
    _path = '/geo_nodes'
    _obj_cls = Tree
    _update_attrs = (tuple(), ('enabled', 'url', 'files_max_capacity',
                               'repos_max_capacity'))

    @cli.register_custom_action('TreeManager')
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
        return self.gitlab.http_list('/geo_nodes/status', **kwargs)

    @cli.register_custom_action('TreeManager')
    @exc.on_http_error(exc.GitlabGetError)
    def current_failures(self, **kwargs):
        """Get the list of failures on the current geo node.

        Args:
            **kwargs: Extra options to send to the server (e.g. sudo)

        Raises:
            GitlabAuthenticationError: If authentication is not correct
            GitlabGetError: If the server failed to perform the request

        Returns:
            list: The list of failures
        """
        return self.gitlab.http_list('/geo_nodes/current/failures', **kwargs)
