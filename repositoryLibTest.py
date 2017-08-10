#!/usr/bin/python
#
# ----------------------------------------------------------------------------------------------------
# DESCRIPTION
# ----------------------------------------------------------------------------------------------------
## @file    repositoryLibTest.py [ FILE ] - Configuration module.
## @package repositoryLibTest    [ FILE ] - Configuration module.


#
# ----------------------------------------------------------------------------------------------------
# IMPORT
# ----------------------------------------------------------------------------------------------------
#

import brCore.fileSystemLib
import brGit.repositoryLib
import mock
import py.path
import pygit2
import pytest
import random


#
# ----------------------------------------------------------------------------------------------------
# CODE
# ----------------------------------------------------------------------------------------------------
#

REMOTE_NAME = 'origin'
REMOTE_URL = 'git://github.com/libgit2/pygit2.git'

# #
# # ----------------------------------------------------------------------------------------------------
# # FIXTURES
# # ----------------------------------------------------------------------------------------------------
# #

#
## @brief Fixture of a repository instance.
#
#  @param tmpdir [ str | None ] - Temporary path to repository.
#
#  @retval Repository - Repository object.
#
@pytest.fixture
def tmpRepo(tmpdir):
    repoDir = tmpdir.join('tmpRepo').ensure(dir=True)
    repo = brGit.repositoryLib.Repository.createRepository(repoDir.strpath)
    repo.createCommit('Initial commit.')
    return repo

#
# ----------------------------------------------------------------------------------------------------
# TESTS
# ----------------------------------------------------------------------------------------------------
#

#
## @brief [ CLASS ] - Tests for the Repository class.
class TestRepository:

    #
    ## @brief Tests for the Repository class initialization.
    #
    #  @retval None - This function does not return anything.
    def testInit(self):

        with pytest.raises(ValueError):

            brGit.repositoryLib.Repository(None)

    #
    ## @brief Test for the setRepository function.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - test repository.
    #
    #  @retval None - This function does not return anything.
    def testSetRepository(self, tmpRepo):

        with pytest.raises(ValueError):

            tmpRepo.setRepository('/tmp/nopath/norepo')

    #
    ## @brief Test branch related functions.
    #
    #  @param tmpdir  [ py.path.local ]                  - temp dir for test.
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - test repository.
    #
    #  @retval None - This function does not return anything.
    def testBranch(self, tmpdir, tmpRepo):

        testBranch = 'master'

        with mock.patch('pygit2.Repository.create_branch') as mockCreateBranch:

            br1 = tmpRepo.createBranch('branch1', testBranch)
            mockCreateBranch.assert_called_once()
            mockCreateBranch.reset_mock()
            br2 = tmpRepo.createBranch('branch2')
            mockCreateBranch.assert_called_once()


            pytest.raises(ValueError, "tmpRepo.createBranch('fakeBranch', sourceBranch='source')")

        with mock.patch('pygit2.Repository.listall_branches') as mockListBranch:

            tmpRepo.listBranches()
            mockListBranch.assert_called_once()

        with mock.patch('pygit2.Repository.checkout') as mockCheckout:

            tmpRepo.checkoutBranch('master')
            mockCheckout.assert_called_once()
            pytest.raises(AttributeError, "tmpRepo.checkoutBranch('fakeBranch')")


        pytest.raises(NameError, "tmpRepo.deleteBranch('fakeBranch')")

        pytest.raises(AttributeError, "tmpRepo.checkoutBranch('fakeBranch')")

        newRepo = brGit.repositoryLib.Repository.createRepository(tmpdir.join('newRepo').ensure(dir=True).strpath)
        assert newRepo.currentBranch() is None, 'new repository should not have a branch'

    #
    ## @brief Test stage and ustage a file.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repository.
    #
    #  @retval None - This function does not return anything.
    def testStaging(self, tmpRepo):
        filePath   = 'test.py'
        with open(brCore.fileSystemLib.Directory.join(tmpRepo.workDir(),filePath), 'w+') as f:
            f.write("number: "+ str(random.uniform(1, 5)))
            f.close()

        with mock.patch('pygit2.Index.add') as mockAdd:
            tmpRepo.add(filePath)
            mockAdd.assert_called_once()

        with mock.patch('pygit2.Index.remove') as mockRemove:
            tmpRepo.unstage(filePath)
            mockRemove.assert_called_once()

        with mock.patch('pygit2.Index.add_all') as mockAddAll:
            tmpRepo.addAll([filePath])
            mockAdd.assert_called_once()
    #
    ## @brief Test if it's a repository.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testIsRepo(self, tmpRepo):

        with mock.patch('pygit2.Repository') as mockTestRepo:
            tmpRepo.isRepository(tmpRepo.workDir())
            mockTestRepo.assert_called_once()

        assert tmpRepo.isRepository('fake/path') == False, 'fake path should not be a repository'

    #
    ## @brief Test repository path.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testFindGitRepo(self, tmpRepo):

        with mock.patch('pygit2.discover_repository') as mockFindRepo:
            tmpRepo.findGitRepo(tmpRepo.workDir())
            mockFindRepo.assert_called_once()

        pytest.raises(ValueError, 'tmpRepo.findGitRepo(None)')

    #
    ## @brief Test if status is correctly parsed.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testStatus(self, tmpRepo):

        _status = pygit2.GIT_STATUS_CONFLICTED | pygit2.GIT_STATUS_IGNORED | pygit2.GIT_STATUS_INDEX_DELETED | \
                  pygit2.GIT_STATUS_INDEX_MODIFIED | pygit2.GIT_STATUS_INDEX_NEW | pygit2.GIT_STATUS_WT_DELETED | \
                  pygit2.GIT_STATUS_WT_MODIFIED | pygit2.GIT_STATUS_WT_NEW

        _stList = tmpRepo.gitStatus(_status)

        repoPath = py.path.local(tmpRepo.path())
        repoPath.join('testfile').ensure(file=True)
        repoPath.join('.gitignore').ensure(file=True).write('*.ignore')
        repoPath.join('test.ignore').ensure(file=True)

        with mock.patch.object(tmpRepo, 'status', wraps=tmpRepo.status) as mockStatus:
            tmpRepo.displayStatus()
            mockStatus.assert_called_once()

        assert len(_stList) == 8, 'status should be parsed correctly'

        _status = pygit2.GIT_STATUS_CURRENT
        _stList = tmpRepo.gitStatus(_status)
        assert _stList[0] == "Current", 'status should be parsed correctly'

    #
    ## @brief Test if commit log is empty.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testCommitLog(self, tmpRepo):

        with mock.patch('pygit2.Repository.walk') as mockCommitLog:
            log = tmpRepo.commitLog()
            mockCommitLog.assert_called()

    #
    ## @brief Test commit.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testCommit(self, tmpRepo):

        pytest.raises(ValueError, 'tmpRepo.createCommit(None)')
        with mock.patch('pygit2.Repository.create_commit') as mockCommit:
            tmpRepo.createCommit('test commit')
            mockCommit.assert_called_once()

    #
    ## @brief Test Remote.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testRemote(self, tmpRepo):

        tmpRepo.createRemote(REMOTE_NAME, REMOTE_URL)

        with mock.patch('pygit2.Remote.fetch') as mockFetch:
            tmpRepo.fetch()
            mockFetch.assert_called()
            mockFetch.reset_mock()
            tmpRepo.fetch(REMOTE_NAME)
            mockFetch.assert_called()

        tmpRepo.pull()

    #
    ## @brief Test merge.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testMerge(self, tmpRepo):

        headID = tmpRepo.head().target
        pytest.raises(ValueError, 'tmpRepo.merge(headID)')

    #
    ## @brief Test delete a repository.
    #
    #  @param tmpRepo [ brGit.repositoryLib.Repository ] - Repsoitory.
    #
    #  @retval None - This function does not return anything.
    def testDeleteRepo(self, tmpRepo):

        pytest.raises(NameError, "tmpRepo.deleteRepository('fake/path')")

    #
    ## @brief Test for the getSSHConfig function.
    #
    #  @param tmpdir [ py.path.local ] - temporary directory for the test.
    #
    #  @retval None - This function does not return anything.
    def testGetSSHConfig(self, tmpdir):

        hostname = 'myhostname.com'
        url      = 'git@myhostname.com:user/repo.git'
        getSSHConfig = brGit.repositoryLib.Repository.AuthCallback.getSSHConfig

        with mock.patch('os.path.expanduser', side_effect=lambda x: x.replace('~', tmpdir.strpath)):

            config = getSSHConfig(url)
            assert isinstance(config, dict), 'missing config should still give dict'

            configFile  = tmpdir.join('.ssh').join('config').ensure(file=True)
            config      = getSSHConfig(url)
            assert isinstance(config, dict), 'empty config should still give dict'

            configFile.write('\n'.join([
                'host ' + hostname,
                '\tIdentityFile ~/.ssh/id_rsa'
            ]))

            config = getSSHConfig(url)
            assert isinstance(config, dict),   'valid config should give dict'
            assert config.get('identityfile'), 'should give lowercase attributes'

            config2 = getSSHConfig('ssh://' + url)
            assert config == config2, 'should give same dict with and without url scheme'

            with pytest.raises(ValueError, message='invalid url should raise'):

                getSSHConfig('/invalid/url.value@')
