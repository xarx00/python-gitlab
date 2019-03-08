
from __future__ import print_function
from __future__ import absolute_import
import base64

from gitlab.base import *  # noqa
from gitlab import cli
from gitlab.exceptions import *  # noqa
from gitlab.mixins import *  # noqa
from gitlab import types
from gitlab import utils


class Tree(RESTObject):
    _id_attr = None


class TreeManager(ListMixin, RESTManager):
    """Manager for work with the groups and projects hierarchy.

    This manager doesn't actually manage objects but provides helper functions
    for bulk operations over projects under a specified group.
    """
    _path = ''
    _obj_cls = Tree

    @cli.register_custom_action('TreeManager', ('full-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def group(self, **kwargs):
        gl = self.gitlab

        grpath = kwargs['full-path']
        grname = grpath[grpath.rfind('/')+1:]
        groups = gl.groups.list(search=grname, all-available=True)
        for group in groups:
            if group.full_path == grpath:
                return group
        raise exc.GitlabGetError(404)


        print(groups)
        groups = groups[1].subgroups.list()
        print(groups)
        grp = groups[5]
        print(grp)
        groups = grp.subgroups.list()
        print(groups)
        

    @cli.register_custom_action('TreeManager', ('full-path', ))
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

