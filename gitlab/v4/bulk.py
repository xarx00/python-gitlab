
from __future__ import print_function
from __future__ import absolute_import
from builtins import str
import base64
import os
import sys
import re

from gitlab.base import *  # noqa
from gitlab import cli
from gitlab.exceptions import *  # noqa
from six.moves import configparser

if sys.version_info < (3,):
    #workaround for the issue in GitPython with non-ascii filenames
    reload(sys) # makes sys.setdefaultencoding() visible
    sys.setdefaultencoding(sys.getfilesystemencoding())
import git


CONFIG_FILE = '.gitlab'
CFG_SECTION_GLOBAL = 'global'
CFG_BASE_GROUP = 'base_group'



def print_progress(msg=None, num=0, maxnum=None):
    CSI = '\033['
    if not sys.stdout.isatty():
        return
    if msg:
        print(CSI+'G', end='') #start of line
        print(msg, end='')
        if num:
            pct = '\t%3.f%%' % (num/maxnum*100) if maxnum else num
            print(': %s' % pct, end='')
        print(CSI+'J', end='') #clear rest of line
        sys.stdout.flush()
    else:
        print(CSI+'G', end='') #start of line
        print(CSI+'J', end='') #clear rest of line
        print(CSI+'G', end='') #start of line
        sys.stdout.flush()



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
        raise GitlabGetError("Group '%s' does not exist." % grpath,
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
        raise GitlabGetError("Project '%s' does not exist." % project_path,
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
            raise GitlabError(
                    'The current directory must be within a gitlab work-dir.')
        return wdgroup

    @property
    def workdir_root(self):
        wdroot = self.gitlab.workdir_path
        if not wdroot:
            raise GitlabError(
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
            raise GitlabError(
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
            raise GitlabError(
                "'%s' is not a subdirectory of the current work-dir." % wdpath)
        return self.workdir_group + path[l:]

    def get_url(self, grpath):
        """Returns the url into repo derived from the group path.
        """
        return '%s/%s' % (self.gitlab.url, grpath)


    def is_project(self, wdpath):
        """Returns True if the path points to (a root of) a git project.
        """
        return os.path.isdir(os.path.join(wdpath, '.git'))


#    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def wdprojects(self, group_path=None, **kwargs):
        """Returns the list of workdir path of all projects in the
        workdir under project-path.
        """
        print_progress("Collecting local projects")
        try:
            grpath = group_path or self.workdir_group
            wdpath = self.get_wdpath(grpath)
            if not os.path.isdir(wdpath):
                raise GitlabError(
                    "Group-path '%s' does not correspond to a local group nor project." % grpath)
            elif self.is_project(wdpath):
                projects = [wdpath]
            else:
                projects = []
                for dirname, dirs, files in os.walk(wdpath):
                    for i in reversed(range(len(dirs))):
                        path = os.path.join(dirname, dirs[i])
                        if self.is_project(path):
                            projects.append(path)
                            del dirs[i]
        finally:
            print_progress()
        return projects


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def local_projects(self, group_path=None, **kwargs):
        """Returns the list of project path of all projects in the
        workdir under group-path.
        """
        return [self.get_grpath(wdpath)
               for wdpath in self.wdprojects(group_path=group_path)]

    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def remote_projects(self, group_path=None, **kwargs):
        """Returns the list of project paths of all remote projects
        under group-path.
        """
        print_progress("Collecting remote projects")
        try:
            grpath = group_path or self.workdir_group
            l = len(grpath)
            projects =  [p.path_with_namespace
                         for p in self.gitlab.projects.list(all=True, simple=True)
                         if p.path_with_namespace == grpath or
                            p.path_with_namespace.startswith(grpath) and
                            p.path_with_namespace[l] == '/']
        finally:
            print_progress()
        return projects

    def _get_projects(self, group_path=None):
        """Returns the list of all local projects under group-path.
        Each project is represented as a tripple:
        (workdir-path, project-path, corresponding git Repo object)
        """
        return [
              (wdpath, self.get_grpath(wdpath), git.Repo(wdpath))
              for wdpath in self.wdprojects(group_path=group_path)]


    @cli.register_custom_action('BulkManager', ('group-path', 'workdir-name'))
    def init(self, group_path, workdir_name, **kwargs):
        """Initializes the given directory as a root of a working copy
        for the specified GitLab repo group, its subgroups and projects,
        The repo url is specified in the current section of 
        the python-gitlab.cfg,
        """
        if self.gitlab.workdir_path:
            raise GitlabError(
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


    def get_submodule_remote_branch(self, sm, repo):
        if sm.branch is None:
            return None
        elif sm.branch.name == '.':
            return repo.active_branch.name if not repo.head.is_detached else None
        else:
            return sm.branch.name


    @cli.register_custom_action('BulkManager', tuple(),
                                ('group-path', 'no-remote', 'branch'))
    def errors(self, group_path=None, no_remote=False, branch=None,
               _projects=None, **kwargs):
        projects = _projects or self._get_projects(group_path=group_path)
        errors = {prpath:[] for (wdpath, prpath, repo) in projects}

        pat_grpath = re.compile(r'(.*?//[^/]+)/(.*)\.git$')

        remote_name = self.gitlab.remote_name
        for (wdpath, prpath, repo) in projects:
            print_progress("Collecting error data: " + prpath)

            if repo.head.is_detached:
                errors[prpath].append("Current HEAD is detached.")
            elif branch is not None and repo.active_branch.name != branch:
                errors[prpath].append("Current branch is '%s', not '%s'." %
                                      (repo.active_branch.name, branch))

            for sm in repo.submodules:
                if sm.exists():
                    smrepo = sm.module()
                    if smrepo.head.is_detached:
                        errors[prpath].append("Submodule '%s' has detached HEAD." % sm.name)
                    else:
                        sm_branch = self.get_submodule_remote_branch(sm, repo)
                        if sm_branch is not None and sm_branch != smrepo.active_branch.name:
                            errors[prpath].append(
             "Submodule '%s' is not at the branch configured in the superproject." % sm.name)

            remote = None
            try:
                remote = repo.remote('origin')
            except ValueError:
                errors[prpath].append("Remote alias 'origin' is not set.")
            try:
                if remote_name != 'origin': #do not check 'origin' again
                    remote = repo.remote(remote_name)
            except ValueError:
                errors[prpath].append("Remote alias '%s' is not set." %
                                      remote_name)

            #remote now should correspond to the remote_name
            if remote is not None:
                m = pat_grpath.match(remote.url)
                if m:
                    if m.group(1) != self.gitlab.url:
                        errors[prpath].append(
                 "Remote '%s' server url '%s' does not correspond to the current GitLab server url '%s'." % (remote.name, m.group(1), self.gitlab.url))
                    else:
                        grpath = m.group(2)
                        if grpath != prpath:
                            errors[prpath].append(
                 "Local repo/workdir location does not correspond to its '%s' remote repo location '%s'." % (remote_name, grpath))
                else:
                        errors[prpath].append(
                                  "Cannot parse project url '%s'." % url)
            repo.git.clear_cache()

        print_progress()
        return {prpath:errs for prpath, errs in errors.items() if errs}


    @cli.register_custom_action('BulkManager', tuple(),
                                ('group-path', 'no-remote', 'branch'))
    def status(self, group_path=None, no_remote=False, branch=None,
               **kwargs):
        projects = self._get_projects(group_path=group_path)

        errors = self.errors(group_path=group_path, no_remote=no_remote,
                             branch=branch, _projects=projects).keys()
        modified = []
        untracked = []
        for (wdpath, prpath, repo) in projects:
            print_progress("Processing local status: " + prpath)
            if repo.is_dirty():
                modified.append(prpath)
            if repo.untracked_files:
                untracked.append(prpath)

        #Non-pushed repos
        non_pushed = []
        for (wdpath, prpath, repo) in projects:
            print_progress("Processing push status: " + prpath)
            needs_push = False
            response = repo.git.branch(v=True)
            if not repo.head.is_detached:
	            pat_start = r'^(?:\*|\s*' + repo.active_branch.name + r'\s)'
            else:
	            pat_start = r'^\*'
            pat = re.compile(pat_start + r'[^\[]*\[ahead', re.M)
            if pat.search(response):
                needs_push = True
            else:
                for sm in repo.submodules:
                    if sm.exists():
                        smrepo = sm.module()
                        response = smrepo.git.branch(v=True)
                        sm_branch = self.get_submodule_remote_branch(sm, repo)
                        if sm_branch is not None:
                            pat = re.compile(r'^\*?\s*' + sm_branch + r'[^\[]*\[ahead', re.M)
                            if pat.search(response):
                                needs_push = True
                                break
            if needs_push:
                non_pushed.append(prpath)
            repo.git.clear_cache()

        if no_remote:
            local_only = remote_only = outdated = None
        else:
            print_progress("Processing remote data")
            local = [prpath for (wdpath, prpath, repo) in projects]
            remote = self.remote_projects(group_path=group_path)
            #TODO local_only: compare repo remote location, not prpath
            local_only = [prpath for prpath in local if prpath not in remote]
            remote_only = [prpath for prpath in remote if prpath not in local]

            outdated = []
            remote_name = self.gitlab.remote_name
            for (wdpath, prpath, repo) in projects:
                print_progress("Processing remote status: " + prpath)
                if prpath in remote:
                    response = repo.git.remote('show', remote_name)
                    if response.find('out of date') != -1:
                        outdated.append(prpath)

        print_progress()
        status = {}
        if errors: status["errors"] = errors
        if modified: status["modified"] = modified
        if untracked: status["untracked_files"] = untracked
        if non_pushed: status["need_push"] = non_pushed
        if outdated: status["outdated"] = outdated
        if local_only: status["local-only"] = local_only
        if remote_only: status["remote-only"] = remote_only
        return status


    @cli.register_custom_action('BulkManager', ('group-path', ))
    def clone(self, group_path=None, **kwargs):
        projects = [(self.get_wdpath(prpath), prpath)
                    for prpath in self.remote_projects(group_path=group_path)]
        errors = {prpath:[] for (wdpath, prpath) in projects}

        for (wdpath, prpath) in projects:
            try:
                if os.path.exists(os.path.join(wdpath, '.git')):
                    errors[prpath].append('Project already exists.')
                else:
                    print_progress("Processing project:" + prpath)
                    url = self.get_url(prpath) + '.git'
                    git.Repo.clone_from(url, wdpath)
            except git.GitCommandError as e:
                m = re.search(r"\bstderr: '?(.*?)(?:\n|'?$)", str(e))
                errmsg = m.group(1) if m else str(e)
                errors[prpath].append('%s: %s' % 
                                      (e.__class__.__name__, errmsg))
            except Exception as e:
                errors[prpath].append('%s: %s' % 
                                      (e.__class__.__name__, e.message))	
        print_progress()

        return {prpath:errs for prpath, errs in errors.items() if errs}


    def _get_remote(self, repo, errors=None):
        remote_name = self.gitlab.remote_name
        try:
            return repo.remote(remote_name)
        except ValueError:
            if errors is not None:
                errors.append("Remote alias '%s' is not set." % remote_name)
                return None
            else:
                raise


    def _perform_op_on_remotes(self, group_path, op):
        projects = self._get_projects(group_path=group_path)
        results = {}
        errors = {prpath:[] for (wdpath, prpath, repo) in projects}
        
        remote_name = self.gitlab.remote_name
        for (wdpath, prpath, repo) in projects:
            print_progress(prpath)
            remote = self._get_remote(repo, errors[prpath])
            try:
                result = op(self, remote, wdpath, prpath, repo, errors[prpath])
                if result:
                    results[prpath] = result
            except Exception as e:
                errors[prpath].append('%s: %s' % (e.__class__.__name__, str(e)))
        print_progress()

        resp = errors.copy()
        for prpath, result in results.items():
            resp[prpath] = result + resp[prpath]
        return {prpath:result for prpath, result in resp.items() if result}


    def _yn(self, value):
        return 'no-' if str(value).lower() == 'false' else ''

    def _b(self, value):
        value = str(value).lower()
        return True if value == 'true' else False if value == 'false' else value


    def _resolve_fi_flags(self, flags):
        fl = []
        info = git.remote.FetchInfo
        if flags&info.ERROR: fl.append('ERROR')
        if flags&info.REJECTED: fl.append('REJECTED')
        if flags&info.NEW_HEAD: fl.append('NEW_HEAD')
        if flags&info.FAST_FORWARD: fl.append('FAST_FORWARD')
        if flags&info.FORCED_UPDATE: fl.append('FORCED_UPDATE')
        if flags&info.HEAD_UPTODATE: fl.append('HEAD_UPTODATE')
        if flags&info.NEW_TAG: fl.append('NEW_TAG')
        if flags&info.TAG_UPDATE: fl.append('TAG_UPDATE')
        return fl

    def _resolve_progress(self, op_code):
       rp = git.RemoteProgress
       op = op_code & rp.OP_MASK
       if op == rp.CHECKING_OUT:
           msg = 'Checking out'
       elif op == rp.COMPRESSING:
           msg = 'Compressing'
       elif op == rp.COUNTING:
           msg = 'Counting'
       elif op == rp.FINDING_SOURCES:
           msg = 'Finding sources'
       elif op == rp.RECEIVING:
           msg = 'Receiving'
       elif op == rp.RESOLVING:
           msg = 'Resolving'
       elif op == rp.WRITING:
           msg = 'Writing'
       else:
           msg = None
       return msg


    @cli.register_custom_action('BulkManager', tuple(), (
              'group-path', 'branch', 'recurse-submodules', 'dry-run',
              #options related to fetching
              'depth', 'deepen', 'shallow-since', 'unshallow',
              'update-shallow', 'prune'))
    def fetch(self, group_path=None, branch='master', recurse_submodules=None,
              dry_run=False,
              #options related to fetchig
              depth=False, deepen=False, shallow_since=False, unshallow=False,
              update_shallow=False, prune=False):
        pull_args = {}
        if recurse_submodules is not None:
            pull_args[self._yn(recurse_submodules)+'recurse-submodules'] = True
        pull_args['dry-run'] = self._b(dry_run)
        #options related to fetching
        pull_args['depth'] = depth
        pull_args['deepen'] = deepen
        pull_args['shallow-since'] = shallow_since
        pull_args['unshallow'] = self._b(unshallow)
        pull_args['update-shallow'] = self._b(update_shallow)
        pull_args['prune'] = self._b(prune)

        def fetch_op(self, remote, wdpath, prpath, repo, errors):
            #refspec=branch would not return fetch status
            refspec = '%s:remotes/%s/%s' % (branch, remote.name, branch)
            def progress(op_code, cur_count, max_count=None, message=''):
               print_progress(
                       '%s: %s' % (prpath, self._resolve_progress(op_code)),
                       cur_count, max_count)
            info = remote.fetch(refspec=refspec, progress=progress, **pull_args)[0]
            flags = self._resolve_fi_flags(info.flags)
            if info.flags not in (0, info.HEAD_UPTODATE):
                return flags
        return self._perform_op_on_remotes(group_path, fetch_op)



    @cli.register_custom_action('BulkManager', tuple(), (
             'group-path', 'branch', 'recurse-submodules',
             #options related to merging
             'commit', 'ff', 'ff-only', 'squash', 'rebase', 'strategy',
             'allow-unrelated-histories', 'sign-off', 'autostash',
             #options related to fetching
             'depth', 'deepen', 'shallow-since', 'unshallow',
             'update-shallow'))
    def pull(self, group_path=None, branch='master', recurse_submodules=None,
             #options related to merging
             commit=None, ff=None, ff_only=False, squash=None, rebase=False,
             strategy=False, allow_unrelated_histories=False, sign_off=None,
             autostash=None,
             #options related to fetchig
             depth=False, deepen=False, shallow_since=False, unshallow=False,
             update_shallow=False):
        pull_args = {}
        if recurse_submodules is not None:
            pull_args[self._yn(recurse_submodules)+'recurse-submodules'] = True
        #options related to merging
        if commit is not None:
            pull_args[self._yn(commit)+'commit'] = True
        if ff is not None:
            pull_args[self._yn(ff)+'ff'] = True
        if squash is not None:
            pull_args[self._yn(squash)+'squash'] = True
        if sign_off is not None:
            pull_args[self._yn(sign_off)+'sign-off'] = True
        if autostash is not None:
            pull_args[self._yn(autostash)+'autostash'] = True
        pull_args['ff-only'] = self._b(ff_only)
        pull_args['rebase'] = rebase
        pull_args['strategy'] = strategy
        pull_args['allow-unrelated-histories'] = self._b(allow_unrelated_histories)
        #options related to fetching
        pull_args['depth'] = depth
        pull_args['deepen'] = deepen
        pull_args['shallow-since'] = shallow_since
        pull_args['unshallow'] = self._b(unshallow)
        pull_args['update-shallow'] = self._b(update_shallow)

        def pull_op(self, remote, wdpath, prpath, repo, errors):
            if repo.head.is_detached or repo.active_branch.name != branch:
                errors.append("Current branch is not '%s'" % branch)
                return
            #refspec=branch would not return fetch status
            refspec = '%s:remotes/%s/%s' % (branch, remote.name, branch)
            def progress(op_code, cur_count, max_count=None, message=''):
               print_progress(
                       '%s: %s' % (prpath, self._resolve_progress(op_code)),
                       cur_count, max_count)
            info = remote.pull(refspec=refspec, progress=progress, **pull_args)[0]
            flags = self._resolve_fi_flags(info.flags)
            if info.flags not in (0, info.HEAD_UPTODATE):
                return flags
        return self._perform_op_on_remotes(group_path, pull_op)


    @cli.register_custom_action('BulkManager', tuple(), ('group-path', 'branch'))
    def log(self, group_path=None, branch='master', **kwargs):
        #TODO
        projects = self._get_projects(group_path=group_path)
        errors = {prpath:[] for (wdpath, prpath, repo) in projects}
        
        remote_name = self.gitlab.remote_name
        for (wdpath, prpath, repo) in projects:
            try:
                remote = repo.remote(remote_name)
                remote.log()
            except ValueError:
                errors[prpath].append("Remote alias '%s' is not set." %
                                      remote_name)
            except Exception as e:
                errors[prpath].append('%s: %s' % (e.__class__.__name__, str(e)))

        return {prpath:errs for prpath, errs in errors.items() if errs}


#    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def add_remote(self, **kwargs):
        pass




"""
    @cli.register_custom_action('BulkManager', tuple(), ('group-path', ))
    def test(self, group_path=None, **kwargs):
        gl = self.gitlab

        grpath = group_path or self.workdir_group
        group = gl.bulk.group(group_path=grpath)
        print(group.subgroups.list())
        subgrps = group.subgroups.list()[1].subgroups.list()
        print(subgrps)
"""
