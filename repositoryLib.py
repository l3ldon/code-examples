#!/usr/bin/python
#
# ----------------------------------------------------------------------------------------------------
# DESCRIPTION
# ----------------------------------------------------------------------------------------------------
## @file    repositoryLib.py [ FILE ] - A module that communicates with Git.
## @package repositoryLib    [ FILE ] - A module that communicates with Git.


#
# ----------------------------------------------------------------------------------------------------
# IMPORT
# ----------------------------------------------------------------------------------------------------
#

import cryptography.hazmat.backends
import cryptography.hazmat.primitives.serialization
import os
import paramiko.config
import pygit2
import re
import shutil
import urlparse

import brAuth.keystoreLib
import brCore.fileSystemLib
import brDeveloper.developerLib
import brPython.reloadLib

brPython.reloadLib.reload(brCore)
brPython.reloadLib.reload(brAuth)
brPython.reloadLib.reload(brDeveloper)

#
# ----------------------------------------------------------------------------------------------------
# CODE
# ----------------------------------------------------------------------------------------------------
#
## @brief [ CLASS ] - Class with functionality to operate on git repositories.
#  @code
#
#  # Create a repository instance
#  repo = brGit.repositoryLib.Repository('path/to/repo/')
#
#  # Clone a remote repository
#  repo = brGit.repository.Repository.clone('remoteURL', '/local/path/to/repo/')
#
#  # Fetch from a remote repository
#  repo.fetch('origin')
#
#  # Checkout a local branch
#  repo.checkoutBranch('PT-250')
#
#  # Checkout a remote branch
#  repo.checkoutBranch('PT-250', remote='origin')
#
#  # List file status in a repository
#  repo.listStatus()
#
#  # Stage a file
#  repo.add('filePath')
#
#  # Create a commit
#  repo.createCommit('commit message')
#
#  # Merge a commit into branch
#  repo.merge('a359b2879f30fc5571dfa9714491e52f1d37af49')
#  _# need to provide a unique ID for a commit_
# @endcode
#
class Repository(object):

    #
    # ------------------------------------------------------------------------------------------------
    # PUBLIC STATIC MEMBERS
    # ------------------------------------------------------------------------------------------------
    #
    ## [ str ] - Master reference.
    MASTER_REF   = 'refs/heads/master'

    #
    # ------------------------------------------------------------------------------------------------
    # CLASSES
    # ------------------------------------------------------------------------------------------------
    #
    ## @brief [ CLASS ] - Class with functionality to override remote callbacks.
    class AuthCallback(pygit2.remote.RemoteCallbacks):

        #
        ## @brief Credentials callback.
        #
        #  @param url               [ str ] - URL of remote repository.
        #  @param username_from_url [ str ] - User name from URL.
        #  @param allowed_types     [ list ] - List of allowed types.
        #
        #  @retval Keypair - A keypair of checking credentials.
        def credentials(self, url, username_from_url, allowed_types):

            config  = self.getSSHConfig(url)

            privKey = config.get('identityfile', ['~/.ssh/id_rsa'])[0]
            privKey = os.path.expanduser(privKey)

            if not os.path.isfile(privKey):

                raise ValueError('cannot find configured private key: ' + privKey)

            return self.generateKeypair(username_from_url, privKey)

        #
        ## @brief Check host certificate.
        #
        #  @param certificate [ None ] - The certificate.
        #  @param valid       [ bool ] - Whether the TLS/SSH library thinks the certificate is valid.
        #  @param host        [ str ]  - The hostname we want to connect to.
        #
        #  @retval bool - True to connect, False to abort.
        def certificate_check(self, certificate, valid, host):

            return True

        #
        ## @brief Push update reference callback.
        #
        #  @param refname [ str ] - Reference name (on the remote).
        #  @param message [ str ] - Rejection message from the remote.
        #
        #  @exception RuntimeError - If it fails to push to remote.
        #
        #  @retval None - None.
        def push_update_reference(self, refname, message):

            raise RuntimeError("Failed to push {0} to remote: {1}".format(refname, message))

        #
        ## @brief Get SSH config file.
        #
        #  @param url [ str ] - URL of remote.
        #
        #  @retval dict - SSH config for the given host.
        @staticmethod
        def getSSHConfig(url):

            configFile = os.path.expanduser("~/.ssh/config")

            if not os.path.isfile(configFile):

                return {}

            ssh_config = paramiko.config.SSHConfig()
            with open(configFile, 'r') as f:
                ssh_config.parse(f)

            if not re.search(r'^\w+://', url):
                url = 'ssh://' + url

            hostName = urlparse.urlparse(url).hostname
            if not hostName:
                raise ValueError("The given URL is invalid.")

            user_config = ssh_config.lookup(hostName)

            return user_config

        #
        ## @brief Generate a keypair.
        #
        #  @param username   [ str ] - User name on Host.
        #  @param privKey    [ str ] - Path to PrivKey.
        #
        #  @retval Keypair - Keypair.
        @staticmethod
        def generateKeypair(username, privKey):

            passPhrase = None
            with open(privKey, 'r') as keyFile:

                keyContents = keyFile.read()

            if 'ENCRYPTED' in keyContents: # pragma: no coverage

                maxTries = 5
                for tryNum in range (maxTries):

                    passPhrase = brAuth.keystoreLib.Keystore.getPassword(
                        'brGit.repositoryLib.AuthCallback',
                        privKey,
                        ask=True,
                        prompt='enter passphrase for private key:\n{}'.format(privKey))

                    if passPhrase is None:

                        raise RuntimeError('Failed to get password for ssh private key: {}'.format(privKey))

                    # make sure the password works before we commit to it
                    try:

                        cryptography.hazmat.primitives.serialization.load_pem_private_key(
                            keyContents,
                            password=bytes(passPhrase),
                            backend=cryptography.hazmat.backends.default_backend())
                        break

                    # a value error is usually a bad decrypt (bad passphrase)
                    # make sure we unset the password and try again up to max
                    except ValueError as e:

                        brAuth.keystoreLib.Keystore.deletePassword('brGit.repositoryLib.AuthCallback', privKey)

                        if tryNum == maxTries-1:

                            raise ValueError('Failed to decrypt private key, likely an invalid password: {}'.format(e.message))


            pubKey = privKey + '.pub'
            return pygit2.credentials.Keypair(username, pubKey, privKey, passPhrase)


    ##
    ## @brief   [ ENUM CLASS ] - Branch flag options.
    ##
    class BranchFlag(brCore.enumAbs.Enum):

        ## [ int ] - Local branches.
        kLocal  = pygit2.GIT_BRANCH_LOCAL

        ## [ int ] - Remote branches.
        kRemote = pygit2.GIT_BRANCH_REMOTE

    ##
    ## @brief   [ ENUM CLASS ] - Git statuses.
    ## @details The `GIT_STATUS_INDEX` set of flags represents the status of file in the index relative to the HEAD, and
    ##          the `GIT_STATUS_WT` set of flags represent the status of the file in the working directory relative to the index.
    ##          Some statuses from pygit2 cannot be imported:
    ##          'GIT_STATUS_INDEX_TYPECHANGE','GIT_STATUS_INDEX_RENAMED', 'GIT_STATUS_INDEX_UNREADABLE',
    ##          'GIT_STATUS_WT_TYPECHANGE', 'GIT_STATUS_WT_RENAMED', 'GIT_STATUS_WT_UNREADABLE'
    class Status(brCore.enumAbs.Enum):

        ## [ int ] - GIT_STATUS_CONFLICTED.
        kConflicted          = "Conflicted"

        ## [ int ] - GIT_STATUS_CURRENT.
        kCurrent             = "Current"

        ## [ int ] - GIT_STATUS_IGNORED.
        kIgnored             = "Ignored"

        ## [ int ] - GIT_STATUS_INDEX_DELETED.
        kIndexDeleted        = "Index deleted"

        ## [ int ] - GIT_STATUS_INDEX_MODIFIED.
        kIndexModified       = "Index modified"

        ## [ int ] - GIT_STATUS_INDEX_NEW.
        kIndexNew            = "New Index"

        ## [ int ] - GIT_STATUS_WT_DELETED.
        kWorkingTreeDeleted  = "Working tree deleted"

        ## [ int ] - GIT_STATUS_WT_MODIFIED.
        kWorkingTreeModified = "Working tree modified"

        ## [ int ] - GIT_STATUS_WT_NEW.
        kWorkingTreeNew      = "New working tree"


    ##
    ## @brief   [ ENUM CLASS ] - Sorting types.
    ## @details The following types of sorting could be used to control traversing direction.
    ##
    class SortingType(brCore.enumAbs.Enum):

        ## [ int ] - Sort the repository contents in no particular ordering.
        kSortNone        = pygit2.GIT_SORT_NONE

        ## [ int ] - Iterate through the repository contents in reverse order.
        kSortReverse     = pygit2.GIT_SORT_REVERSE

        ## [ int ] - Sort the repository contents by commit time.
        kSortTime        = pygit2.GIT_SORT_TIME

        ## [ int ] - Sort the repository contents in topological order (parents before children).
        kSortTopological = pygit2.GIT_SORT_TOPOLOGICAL


    #
    # ------------------------------------------------------------------------------------------------
    # BUILT-IN METHODS
    # ------------------------------------------------------------------------------------------------
    # @brief     Constructor.
    #
    # @param     repoPath [ str | None | in ]   Path to the repository
    #
    # @exception ValueError - If repoPath is not provided and no repository is found in the current working directory.
    #
    # @retval    None - None
    #
    def __init__(self, repoPath):

        ## [ Repository ] - Repository.
        self._repository    = None

        if not repoPath:

            raise ValueError("Repository path cannot be empty.")

        self.setRepository(repoPath)

    #
    # ------------------------------------------------------------------------------------------------
    # PROPERTIES
    # ------------------------------------------------------------------------------------------------
    #

    ##
    ## @brief     Get a branch by name
    ##
    ## @param     branchName [ str | None | in ]   The branch name
    ##
    ## @exception N/A
    ##
    ## @retval    Branch - A pygit2.Branch object.
    ##
    def branch(self, branchName):

        return self._repository.lookup_branch(branchName)

    ##
    ## @brief     List all the branches in the repository
    ##
    ## @exception N/A
    ##
    ## @retval    List - List of branches.
    ##
    def listBranches(self):

        return self._repository.listall_branches(Repository.BranchFlag.kLocal | Repository.BranchFlag.kRemote)

    ##
    ## @brief     Log of commits.
    ##
    ## @exception N/A
    ##
    ## @retval    Dict - Commit log.
    ##
    def commitLog(self):

        log = {}
        for commit in self._repository.walk(self.head().target,
                                             Repository.SortingType.kSortTopological |
                                             Repository.SortingType.kSortReverse):
            log[commit.committer] = commit.message

        return log

    ##
    ## @brief     Current branch.
    ##
    ## @exception N/A
    ##
    ## @retval    str - The shorthand "human-readable" name of the branch.
    ##
    def currentBranch(self):

        if not self.head():
            return None
        else:
            return self.head().shorthand

    #
    ## @brief     Current head reference of the repository.
    #
    #  @exception N/A
    #
    #  @retval    None      - if there is no current head reference.
    #  @retval    Reference - HEAD.
    def head(self):

        try:
            return self._repository.head
        except pygit2.GitError:
            return None

    ##
    ## @brief     The normalized path to the git repository.
    ##
    ## @exception N/A
    ##
    ## @retval    str - Path to the repository.
    ##
    def path(self):

        return os.path.dirname(
            self._repository.path.rstrip(os.sep))

    #
    ## @brief Remote.
    #
    #  @param name [ str ] - remote name.
    #
    #  @exception KeyError - If remote is not found.
    #
    #  @retval Remote - remote of repo.
    def remote(self, name):

        return self._repository.remotes[name]

    #
    ## @brief URL for a remote.
    #
    #  @param remoteName [ str ] - Remote name.
    #
    #  @retval str - Remote URL.
    def remoteURL(self, remoteName):

        return self.remote(remoteName).url

    ##
    ## @brief     File statuses in the git repository.
    ##
    ## @exception N/A
    ##
    ## @retval    Dict - Files in the repo and status.
    ##
    def status(self):

        return self._repository.status()

    ##
    ## @brief     The normalized path to the git repository.
    ##
    ## @exception N/A
    ##
    ## @retval    str - Path to the repository.
    ##
    def workDir(self):

        return self._repository.workdir

    #
    # ------------------------------------------------------------------------------------------------
    # PUBLIC METHODS
    # ------------------------------------------------------------------------------------------------
    #

    #
    ## @brief Stage a file.
    #
    #  @param filePath [ str ] - File path.
    #
    #  @retval None - This function does not return anything.
    def add(self, filePath):

        _index = self._repository.index
        _index.add(filePath)
        _index.write()

    #
    ## @brief Stage matching files in the working directory.
    #
    #  @details If pathspecs are specified, only files matching those pathspecs will be added.
    #
    #  @param pathSpecs [ list ] - List of path.
    #
    #  @retval None - This function does not return anything.
    def addAll(self, pathSpecs=[]):

        _index = self._repository.index
        _index.add_all(pathSpecs)
        _index.write()

    #
    ## @brief Unstage a file.
    #
    #  @param filePath [ str ] - File path.
    #
    #  @retval None - This function does not return anything.
    def unstage(self, filePath):

        _index = self._repository.index
        _index.remove(filePath)
        _index.write()

    #
    ## @brief Switch to a branch.
    #
    #  @param name   [ str ]          - branch name.
    #  @param remote [ str | origin ] - remote name.
    #
    #  @exception AttributeError - If the branch doesn't exist.
    #
    #  @retval None - This function does not return anything.
    def checkoutBranch(self, name, remote='origin'):

        if name not in self.listBranches():
            source = self._repository.lookup_branch('{}/{}'.format(remote, name), Repository.BranchFlag.kRemote)
            if source:
                self._repository.create_branch(name, source.get_object())
            else:
                raise AttributeError('Cannot find branch: {}'.format(name))

        self._repository.checkout('refs/heads/' + name)

    ##
    ## @brief     Create a new branch name which points to a commit.
    ##
    ## @param     name         [ str | None | in ]   The branch name
    ## @param     sourceBranch [ str | None | in ]   Source branch
    ##
    ## @exception ValueError - If no source branch is found.
    ##
    ## @retval    Branch - New branch.
    ##
    def createBranch(self, name, sourceBranch=None):

        if not sourceBranch:
            commit = self.head().get_object()
        else:
            source = self._repository.lookup_branch(sourceBranch)
            if source:
                commit = source.get_object()
            else:
                commit = None

        if not commit:
            raise ValueError("Source branch not found:{} \n If branch_type is GIT_BRANCH_REMOTE, \
                you must include the remote name in the branch name (eg 'origin/master').".format(sourceBranch))

        return self._repository.create_branch(name, commit)

    #
    ## @brief Delete a branch.
    #
    #  @param refname [ str ] - branch name.
    #
    #  @exception NameError - If given branch doesn't exist.
    #
    #  @retval None - This function does not return anything.
    def deleteBranch(self, refname):

        try:
            self.branch(refname).delete()
        except:
            raise NameError("Branch doesn't exitst: {}".format(refname))

    ##
    ## @brief     Create a commit to the repository.
    ##
    ## @param     commitMessage [ str | None | in ]   Commit message.
    ##
    ## @exception ValueError - If no commit message attached.
    ## @exception pygit2.GitError  - If the commit fails.
    ##
    ## @retval    str - ID of new commit.
    ##
    def createCommit(self, commitMessage):

        if not commitMessage:
            raise ValueError("Commit message should not be empty.")

        if self._repository.head_is_unborn:
            parent = []
        else:
            parent = [ self.head().target ]

        currentDev = brDeveloper.developerLib.Developer()
        author     = self._repository.default_signature
        committer  = pygit2.Signature(currentDev.name(), currentDev.email())
        tree       = self._repository.index.write_tree()

        try:
            oID    = self._repository.create_commit('HEAD', author, committer, commitMessage, tree, parent)
        except pygit2.GitError as gitErr:
            raise pygit2.GitError(gitErr.message)

        return oID


    #
    ## @brief Fetch against remote repo with a given remote name, otherwise fetch all remotes.
    #
    #  @param remoteName [ str | None ] - Remote name.
    #
    #  @retval None - This function does not return anything.
    def fetch(self, remoteName=None):

        if not remoteName:
            for _remote in self._repository.remotes:
                callbacks = Repository.AuthCallback()
                _remote.fetch(refspecs = _remote.fetch_refspecs, callbacks=callbacks)
        else:
            _remote = self._repository.remotes[remoteName]
            _remote.fetch(refspecs = _remote.fetch_refspecs, callbacks = Repository.AuthCallback())

    ##
    ## @brief     Display readable statuses of files in the repository.
    ##
    ## @exception N/A
    ##
    ## @retval    None - None.
    ##
    def displayStatus(self):

        print "# On branch {}".format(self.currentBranch())

        _status = self.status()

        for filePath, flags in _status.items():

            statusList = Repository.gitStatus(flags)
            if Repository.Status.kIgnored in statusList:
                continue
            print "{0}: {1}".format(filePath, " | ".join(statusList))

    #
    ## @brief Merge the given oid into HEAD.
    #
    #  @param commitID [ str ] - unique ID of a commit.
    #
    #  @exception ValueError - If trying to merge to current branch.
    #
    #  @retval None - This function does not return anything.
    def merge(self, commitID):

        headID = self.head().target
        if headID == commitID:
            raise ValueError("Cannot merge a branch to itself.")

        self._repository.merge(commitID)

    #
    ## @brief Pull from a remote.
    #
    #  @param remoteName  [ str  | origin ] - remote name.
    #  @param mergeCommit [ bool | None   ] - whether create a commit when merging.
    #
    #  @exception RuntimeError - If a conflict occurred.
    #  @exception ValueError   - If merge analysis is unborn.
    #  @exception ValueError   - If an unknown merge analysis
    #
    #  @retval None - This function does not return anything.
    def pull(self, remoteName='origin', mergeCommit=None):

        self.fetch(remoteName)

        remoteId = self._repository.lookup_reference('refs/remotes/{0}/{1}'.format(remoteName, self.currentBranch())).target

        mergeFlags, userPref = self._repository.merge_analysis(remoteId)

        if mergeFlags & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:

            pass

        elif mergeFlags & pygit2.GIT_MERGE_ANALYSIS_FASTFORWARD:

            self._repository.checkout_tree(self._repository.get(remoteId))

            masterRef = self._repository.lookup_reference(Repository.MASTER_REF)

            masterRef.set_target(remoteId)

            self.head().set_target(remoteId)

        elif mergeFlags & pygit2.GIT_MERGE_ANALYSIS_NORMAL:

            self.merge(remoteId)

            if self._repository.index.conflicts:

                raise RuntimeError("Conflicts occurred.")

            if mergeCommit:

                self.createCommit('Pull from remote of {}'.format(self.currentBranch()))

            self._repository.state_cleanup()

        elif mergeFlags & pygit2.GIT_MERGE_ANALYSIS_UNBORN:

            raise ValueError('The HEAD of the current repository is "unborn" and does not point to \
                              a valid commit.  No merge can be performed')
        else:
            raise ValueError('Unknown merge analysis result')


    #
    ## @brief Push.
    #
    #  @param remoteName [ str | origin ] - remote name.
    #
    #  @retval None - This function does not return anything.
    def push(self, remoteName='origin'):

        self._repository.remotes.set_push_url(remoteName, self.remoteURL(remoteName))

        self._repository.remotes[remoteName].push(specs = ['refs/heads/'+ self.currentBranch()],
                                                   callbacks = Repository.AuthCallback())

    #
    ## @brief Set a repository.
    #
    #  @param repoPath [ str ] - Path to a repository.
    #
    #  @exception KeyError - If repository doesn't exist.
    #
    #  @retval None - None.
    def setRepository(self, repoPath):

        try:
            self._repository = pygit2.Repository(repoPath)
        except KeyError as kErr:
            raise ValueError('Repository path doesn\'t exist: ' + kErr.message)


    #
    ## @brief create a new remote.
    #
    #  @param name [ str ] - name of remote.
    #  @param url  [ str ] - url of remote.
    #
    #  @retval None - This function does not return anything.
    def createRemote(self, name, url):

        self._repository.remotes.create(name, url)

    #
    # ------------------------------------------------------------------------------------------------
    # STATIC METHODS & PATH RELATED
    # ------------------------------------------------------------------------------------------------
    #
    ## @brief Clone a repository.
    #
    #  @param repoURL [ str ] - URL to remote repository.
    #  @param path    [ str ] - Local path of repository.
    #
    #  @exception RuntimeError  - If repository is not copied to local correctly.
    #
    #  @retval Repository - New repository instance of cloned repo.
    @staticmethod
    def clone(repoURL, path):

        try:
            newRepo = pygit2.clone_repository(repoURL, path, callbacks = Repository.AuthCallback())
        except pygit2.GitError as gitErr:
            raise RuntimeError(gitErr.message)

        return Repository(newRepo.path)

    #
    ## @brief Create a repository.
    #
    #  @param path [ str ] - Path to a repository.
    #  @param description [ str | None ] - repo description.
    #
    #  @retval [ Repository ] - New Repository object.
    @staticmethod
    def createRepository(path, description=None):

        pygit2.init_repository(path, description=description)

        return Repository(path)

    #
    ## @brief Delete a repository.
    #
    #  @param path [ str ] - path to the repository.
    #
    #  @exception NameError - If git repo doesn't exist.
    #
    #  @retval None - This function does not return anything.
    @staticmethod
    def deleteRepository(path):

        _join  = brCore.fileSystemLib.Directory.join

        gitDir = _join(path, '.git')

        if not os.path.exists(gitDir):

            raise NameError("{} doesn't exist".format(gitDir))

        shutil.rmtree(gitDir)

    #
    ## @brief Check if a path is a repository.
    #
    #  @param path [ str ] - path.
    #
    #  @retval bool - True if it's a repository.
    @staticmethod
    def isRepository(path):

        _join  = brCore.fileSystemLib.Directory.join

        gitDir = _join(path, '.git')

        try:
            _repo = pygit2.Repository(path)
        except:
            return False

        return True

    #
    ## @brief Find a Git repository.
    #
    #  @param path [ str ]    - Path to where to find the repository.
    #
    #  @exception ValueError  - If path is not provided.
    #
    #  @retval Repository - Repository if found, otherwise None.
    @staticmethod
    def findGitRepo(path):

        if not path:
            raise ValueError("Path is not provided.")

        return pygit2.discover_repository(path)

    ##
    ## @brief    Convert a Git status to a readable string.
    ##
    ## @param    status [ int | None | in ]     The status
    ##
    ## @retval   List - List of git status enum.
    ##
    @staticmethod
    def gitStatus(status):

        result = []

        if status == pygit2.GIT_STATUS_CURRENT:
            result.append(Repository.Status.kCurrent)

        if status & pygit2.GIT_STATUS_CONFLICTED:
            result.append(Repository.Status.kConflicted)

        if status & pygit2.GIT_STATUS_IGNORED:
            result.append(Repository.Status.kIgnored)

        if status & pygit2.GIT_STATUS_INDEX_DELETED:
            result.append(Repository.Status.kIndexDeleted)

        if status & pygit2.GIT_STATUS_INDEX_MODIFIED:
            result.append(Repository.Status.kIndexModified)

        if status & pygit2.GIT_STATUS_INDEX_NEW:
            result.append(Repository.Status.kIndexNew)

        if status & pygit2.GIT_STATUS_WT_DELETED:
            result.append(Repository.Status.kWorkingTreeDeleted)

        if status & pygit2.GIT_STATUS_WT_MODIFIED:
            result.append(Repository.Status.kWorkingTreeModified)

        if status & pygit2.GIT_STATUS_WT_NEW:
            result.append(Repository.Status.kWorkingTreeNew)

        return result
