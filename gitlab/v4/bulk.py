
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
import git
import re


CONFIG_FILE = '.gitlab'
CFG_SECTION_GLOBAL = 'global'
CFG_BASE_GROUP = 'base_group'



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


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def group(self, group_path=None, **kwargs):
        """Returns the repo group identified by its group-path.
        """
        gl = self.gitlab

        grpath = group_path or self.workdir_group
        grname = grpath[grpath.rfind('/')+1:]
        groups = gl.groups.list(search=grname, all_available=True)
        for group in groups:
            if group.full_path == grpath:
                return group
        raise exc.GitlabGetError("Group '%s' does not exist." % grpath,
                                 response_code=404)

    @cli.register_custom_action('BulkManager', tuple(), ('project-path', ))
    def project(self, project_path=None, **kwargs):
        """Returns the repo project identified by its project-path.
        """
        gl = self.gitlab

        i = project_path.rfind('/')
        if i >=0:
            (grpath, prname) = (project_path[:i], project_path[i+1:])
        else:
            (grpath, prname) = ('', project_path)
        group = self.group(grpath)
        projects = group.projects.list(search=prname)
        for project in projects:
            if project.path_with_namespace == project_path:
                return project
        raise exc.GitlabGetError("Project '%s' does not exist." % project_path,
                                 response_code=404)

    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def subgroups(self, group_path=None, **kwargs):
        """Returns the list of repo groups directly under the group.
        """
        return self.group(group_path=group_path).subgroups.list()

    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def projects(self, group_path=None, **kwargs):
        """Returns the list of repo projects directly under the group.
        """
        return self.group(group_path=group_path).projects.list()


    @property
    def workdir_group(self):
        wdgroup = self.gitlab.workdir_group
        if not wdgroup:
            raise exc.GitlabError(
                    'The current directory must be within a gitlab work-dir.')
        return wdgroup

    @property
    def workdir_root(self):
        wdroot = self.gitlab.workdir_path
        if not wdroot:
            raise exc.GitlabError(
                    'The current directory must be within a gitlab work-dir.')
        return wdroot

    def get_wdpath(self, grpath):
        """Returns the workdir path for a group path.
        """
        wdgroup = self.workdir_group
        if wdgroup == grpath:
            return self.workdir_root
        l = len(wdgroup)
        if not grpath.startswith(wdgroup) or grpath[l] != '/':
            raise exc.GitlabError(
                    "'%s' is not stored in the current work-dir." % grpath)
        return os.path.join(self.workdir_root, grpath[l+1:])

    def get_grpath(self, wdpath):
        """Returns the group/project path for a workdir path.
        """
        path = wdpath.replace('\\', '/')
        wdroot = self.workdir_root.replace('\\', '/')
        if wdroot == path:
            return self.workdir_group
        if not path.startswith(wdroot):
            path = os.path.abspath(path)
            wdroot = os.path.abspath(wdroot)
            if wdroot == path:
                return self.workdir_group
        l = len(wdroot)
        if not path.startswith(wdroot) or path[l] != '/':
            raise exc.GitlabError(
                "'%s' is not a subdirectory of the current work-dir." % wdpath)
        return self.workdir_group + path[l:]


    def is_project(self, wdpath):
        """Returns True if the path points to (a root of) a git project.
        """
        return os.path.isdir(os.path.join(wdpath, '.git'))


#    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def wdprojects(self, group_path=None, **kwargs):
        """Returns the list of workdir path of all projects in the
        workdir under project-path.
        """
        grpath = group_path or self.workdir_group
        wdpath = self.get_wdpath(grpath)
        if self.is_project(wdpath):
            projects = [wdpath]
        else:
            projects = []
            for dirname, dirs, files in os.walk(wdpath):
                for i in reversed(range(len(dirs))):
                    path = os.path.join(dirname, dirs[i])
                    if self.is_project(path):
                        projects.append(path)
                        del dirs[i]
        return projects


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def local_projects(self, group_path=None, **kwargs):
        """Returns the list of project path of all projects in the
        workdir under project-path.
        """
        projects = self.wdprojects(group_path=group_path)
        return [self.get_grpath(path) for path in projects]

    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def remote_projects(self, group_path=None, **kwargs):
        """Returns the list of project path of all remote projects
        under group-path.
        """
        grpath = group_path or self.workdir_group
        l = len(grpath)
        return [p.path_with_namespace
                for p in self.gitlab.projects.list(all=True, simple=True)
                if p.path_with_namespace == grpath or
                   p.path_with_namespace.startswith(grpath) and
                   p.path_with_namespace[l] == '/']

    def _get_projects(self, group_path=None):
        return [
              (wdpath, self.get_grpath(wdpath), git.Repo(wdpath))
              for wdpath in self.wdprojects(group_path=group_path)]


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def errors(self, group_path=None, _projects=None, **kwargs):
        projects = _projects or self._get_projects(group_path=group_path)
        errors = {prpath:[] for (wdpath, prpath, repo) in projects}

        pat_grpath = re.compile(r'.*?//[^/]+/(.*)\.git$')

        def check_remote(remote, wdpath, prpath):
            url = remote.url
            m = pat_grpath.match(url)
            if m:
                grpath = m.group(1)
                if grpath != prpath:
                    errors[prpath].append(
             "Project workdir location does not correspond to its '%s' repository location '%s'." % (remote_name, grpath))
            else:
                    errors[prpath].append(
                              "Cannot parse project url '%s'." % url)

        remote_name = self.gitlab.remote_name
        for (wdpath, prpath, repo) in projects:
            try:
                remote = repo.remote('origin')
                check_remote(remote, wdpath, prpath)
            except ValueError:
                errors[prpath].append("Remote alias 'origin' is not set.")
            try:
                if remote_name != 'origin':
                    remote = repo.remote(remote_name)
                    check_remote(remote, wdpath, prpath)
            except ValueError:
                errors[prpath].append("Remote alias '%s' is not set." %
                                      remote_name)
            #TODO: more tests
        return {prpath:errs for prpath, errs in errors.items() if errs}


    @cli.register_custom_action('BulkManager', tuple(),
                                ('group-path', 'no-remote'))
    def status(self, group_path=None, no_remote=False, **kwargs):
        projects = self._get_projects(group_path=group_path)

        errors = self.errors(group_path=group_path, _projects=projects).keys()
        modified = [prpath for (wdpath, prpath, repo) in projects
                    if repo.is_dirty()]
        if no_remote:
            local_only = remote_only = None
        else:
            local = [prpath for (wdpath, prpath, repo) in projects]
            remote = self.remote_projects(group_path=group_path)
            local_only = [prpath for prpath in local if prpath not in remote]
            remote_only = [prpath for prpath in remote if prpath not in local]

        status = {}
        if errors: status["errors"] = errors
        if modified: status["modified"] = modified
        if local_only: status["local-only"] = local_only
        if remote_only: status["remote-only"] = remote_only
        return status


    @cli.register_custom_action('BulkManager', ('group-path', 'workdir-name'))
    def init(self, group_path, workdir_name, **kwargs):
        if self.gitlab.workdir_path:
            raise exc.GitlabError(
                    'Cannot create a work-dir within another work-dir.')
        os.makedirs(workdir_name)

        gl = self.gitlab
        config = configparser.ConfigParser()

        config.add_section(CFG_SECTION_GLOBAL)
        config.set(CFG_SECTION_GLOBAL, 'default', 'origin')
        config.set(CFG_SECTION_GLOBAL, CFG_BASE_GROUP, group_path)
        if gl.timeout: config.set(CFG_SECTION_GLOBAL, 'timeout', gl.timeout)
        config.set(CFG_SECTION_GLOBAL, 'api_version', gl.api_version)

        config.add_section('origin')
        config.set('origin', 'url', gl.url)
        if gl.ssl_verify: config.set('origin', 'ssl_verify', gl.ssl_verify)
        if gl.private_token:
            config.set('origin', 'private_token', gl.private_token)
        if gl.oauth_token:
            config.set('origin', 'oauth_token', gl.oauth_token)
        if gl.http_username:
            config.set('origin', 'http_username', gl.http_username)
        if gl.http_password:
            config.set('origin', 'http_password', gl.http_password)

        f = open(os.path.join(workdir_name, CONFIG_FILE), 'w')
        config.write(f)


    @cli.register_custom_action('BulkManager', ('group-path', ))
    def clone(self, **kwargs):
        pass


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def fetch(self, group_path=None, **kwargs):
        projects = self._get_projects(group_path=group_path)
        errors = {prpath:[] for (wdpath, prpath, repo) in projects}
        
        remote_name = self.gitlab.remote_name
        for (wdpath, prpath, repo) in projects:
            try:
                remote = repo.remote(remote_name)
                remote.fetch()
            except ValueError:
                errors[prpath].append("Remote alias '%s' is not set." %
                                      remote_name)
            except Exception as e:
                errors[prpath].append('%s: %s' % (e.__class__.__name__, str(e)))

        return {prpath:errs for prpath, errs in errors.items() if errs}


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def pull(self, group_path=None, **kwargs):
        pass


#    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def add_remote(self, **kwargs):
        pass





    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    @exc.on_http_error(exc.GitlabGetError)
    def test(self, group_path=None, **kwargs):
        gl = self.gitlab

        grpath = group_path or self.workdir_group
        group = gl.bulk.group(group_path=grpath)
        print(group.subgroups.list())
        subgrps = group.subgroups.list()[1].subgroups.list()
        print(subgrps)
