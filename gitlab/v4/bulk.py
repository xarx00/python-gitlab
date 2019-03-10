
from __future__ import print_function
from __future__ import absolute_import
import base64

from gitlab.base import *  # noqa
from gitlab import cli
from gitlab.exceptions import *  # noqa
from gitlab.mixins import *  # noqa
from gitlab import types
from gitlab import utils
import os
from six.moves import configparser
import pygit2


CONFIG_FILE = '.gitlab'
CFG_SECTION_GLOBAL = 'global'
CFG_BASE_GROUP = 'base_group'


def get_path_ancestors(path):
    """Returns list of the path and its ancestor paths in descending order.
    """
    ancestors = []
    while True:
        ancestors.append(path)
        spl = os.path.split(path)
        if not spl[1]:
            break
        path = spl[0]
    return ancestors

def read_first_config(paths):
    """Reads the first config file in the list of paths. Returns the read
    config, or None if no config file from the list exists.
    """
    config = None
    for path in paths:
        if os.path.isfile(path):
            config = configparser.ConfigParser()
            config.read(path)
            break
    return config



class GitlabCloneError(GitlabError):
    pass



class Bulk(RESTObject):
    _id_attr = None


class BulkManager(RESTManager):
    """Manager for work with the groups and projects hierarchy.

    This manager doesn't actually manage objects but provides helper functions
    for bulk operations over projects under a specified group.
    """
    _path = ''
    _obj_cls = Bulk

    _base_group = None

    @property
    def base_group(self):
        """Returns tuple of the group-path of the group corresponding to the gitlab
        project root.
        """
        if self._base_group is not None:
            return self._base_group
        gl = self.gitlab

        config_files = [f for d in get_path_ancestors(os.getcwd())
                        for f in (d+'/python-gitlab.cfg', d+'/'+CONFIG_FILE)]
        config = read_first_config(config_files)

        if base_group is None:
            base_group = gl._config.get(gl.gitlab_id, BASE_GROUP)

        self._base_group = base_group
        return base_group


    def is_project(self, path):
        """Returns True if the path points to (a root of) a git project.
        """
        return os.path.isdir(os.path.join(path, '.git'))


    def get_group_path(self, path):
        base_group = self.base_group

        pass


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def test(self, **kwargs):
        gl = self.gitlab

        group = gl.bulk.group(group_path=kwargs['group_path'])
        print(group.subgroups.list())
        subgrps = group.subgroups.list()[1].subgroups.list()
        print(subgrps)


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def group(self, **kwargs):
        gl = self.gitlab

        grpath = kwargs['group_path']
        grname = grpath[grpath.rfind('/')+1:]
        groups = gl.groups.list(search=grname, all_available=True)
        for group in groups:
            if group.group_path == grpath:
                return group
        raise exc.GitlabGetError(404)


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
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


    @cli.register_custom_action('BulkManager', ('base-path', 'workdir-name'))
    @exc.on_http_error(exc.GitlabGetError)
    def init(self, base_path, workdir_name, **kwargs):
        os.makedirs(workdir_name)

        gl = self.gitlab
        config = configparser.ConfigParser()
        config.add_section(CFG_SECTION_GLOBAL)
        config.set(CFG_SECTION_GLOBAL, 'default', 'origin')
        config.set(CFG_SECTION_GLOBAL, CFG_BASE_GROUP, base_path)
        if gl.timeout: config.set(CFG_SECTION_GLOBAL, 'timeout', gl.timeout)
        config.set(CFG_SECTION_GLOBAL, 'api_version', gl.api_version)
        config.add_section('origin')
        config.set('origin', 'url', gl.url)
        if gl.ssl_verify: config.set('origin', 'ssl_verify', gl.ssl_verify)
        if gl.private_token: config.set('origin', 'private_token', gl.private_token)
        if gl.oauth_token: config.set('origin', 'oauth_token', gl.oauth_token)
        if gl.http_username: config.set('origin', 'http_username', gl.http_username)
        if gl.http_password: config.set('origin', 'http_password', gl.http_password)

        f = open(os.path.join(workdir_name, CONFIG_FILE), 'w')
        config.write(f)


    @cli.register_custom_action('BulkManager', ('group-path', ))
    def clone(self, **kwargs):
        pass


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def fetch(self, **kwargs):
        pass


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def pull(self, **kwargs):
        pass


#    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def add_remote(self, **kwargs):
        pass
