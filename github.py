import sys
import time
from typing import Any, TypedDict
import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel,
    QMessageBox
)

CLIENT_ID: str = 'Iv23lixE9BO6XLUTLthN'
CODE_URL: str = 'https://github.com/login/device/code'
TOKEN_URL: str = 'https://github.com/login/oauth/access_token'

class AuthDialog(QDialog):

    def __init__(self, url: str, code: str) -> None:
        super().__init__()

        description = QLabel(f'Please go to <a href="{url}">{url}</a> and enter the following code:')
        description.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        description.setOpenExternalLinks(True)

        codeView = QLineEdit(code)
        codeView.setReadOnly(True)
        codeView.setFont(QFont(['monospace'], 36))

        copy = QPushButton('Copy')
        copy.clicked.connect(lambda: self.doCopy(code))

        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.addWidget(codeView, 1)
        layout.addWidget(copy, 0)
        row.setLayout(layout)

        ok = QPushButton('Done')
        ok.clicked.connect(self.accept)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)

        buttons = QWidget(self)
        layout = QHBoxLayout(buttons)
        layout.addWidget(ok)
        layout.addWidget(cancel)
        buttons.setLayout(layout)

        layout = QVBoxLayout(self)

        layout.addWidget(description)
        layout.addWidget(row)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def doCopy(self, code: str) -> None:
        QGuiApplication.clipboard().setText(code)

class TreeItem(TypedDict):
    path: str
    url: str

class TreeSha(TypedDict):
    sha: str

class CommitTree(TypedDict):
    tree: TreeSha

class Commit(TypedDict):
    sha: str
    commit: CommitTree

class GitHub:

    token: str | None = None
    repoTrees: dict[str, list[TreeItem]]
    repoPathUrls: dict[str, dict[str, str]]
    urlContents: dict[str, str]
    branchCommits: dict[str, dict[str, Commit]]

    def __init__(self) -> None:
        self.repoTrees = {}
        self.repoPathUrls = {}
        self.urlContents = {}
        self.branchCommits = {}

    def getToken(self) -> str:
        if self.token is not None:
            return self.token
        r = requests.post(CODE_URL, data={'client_id': CLIENT_ID}, headers={'Accept': 'application/json'})
        r.raise_for_status()
        data = r.json()
        device_code = data['device_code']
        dialog = AuthDialog(data['verification_uri'], data['user_code'])
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted: # user cancelled
            sys.exit(1)
        data = {'error': 'authorization_pending'}
        while data.get('error') == 'authorization_pending':
            r = requests.post(TOKEN_URL, data=dict(
                client_id=CLIENT_ID,
                device_code=device_code,
                grant_type='urn:ietf:params:oauth:grant-type:device_code'
            ), headers={'Accept': 'application/json'})
            r.raise_for_status()
            data = r.json()
        if 'error' in data:
            QMessageBox.critical(dialog, 'GitHub Authentication Failed',
                                 f'GitHub error: {data["error"]!r}')
            sys.exit(data['error'])
        self.token = data['access_token']
        with open('github.pickle', 'wb') as f:
            pickle.dump(self, f)
        return data['access_token']

    def _getGitHub(self, repo: str, path: str, json: bool = True) -> Any:
        r = requests.get(f'https://api.github.com/repos/{repo}{path}', headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': 'Bearer ' + self.getToken(),
            'User-Agent': 'engsoc-bylaw-policy-amender <speaker@skule.ca>',
            'X-GitHub-APi-Version': '2022-11-28',
        })
        r.raise_for_status()
        if json:
            return r.json()
        else:
            return r.text

    def _postGitHub(self, repo: str, path: str, payload) -> Any:
        time.sleep(1)
        r = requests.get(f'https://api.github.com/repos/{repo}{path}', headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': 'Bearer ' + self.getToken(),
            'User-Agent': 'engsoc-bylaw-policy-amender <speaker@skule.ca>',
            'X-GitHub-APi-Version': '2022-11-28',
        }, json=payload)
        r.raise_for_status()
        return r.json()

    def getTree(self, repo: str) -> list[TreeItem]:
        if repo not in self.repoTrees:
            data = self._getGitHub(repo, '/git/trees/master?recursive=1')
            self.repoTrees[repo] = data['tree']
            self.repoPathUrls[repo] = {item['path']: item['url'] for item in self.repoTrees[repo]}
        return self.repoTrees[repo]

    def getBlob(self, url: str) -> str:
        if url not in self.urlContents:
            r = requests.get(url, headers={
                'Accept': 'application/vnd.github.raw+json',
                'Authorization': 'Bearer ' + self.getToken(),
                'User-Agent': 'engsoc-bylaw-policy-amender <speaker@skule.ca>',
                'X-GitHub-Api-Version': '2022-11-28',
            })
            r.raise_for_status()
            self.urlContents[url] = r.text
        return self.urlContents[url]

    def getBranchCommit(self, repo: str, branch: str) -> Commit:
        if branch not in self.branchCommits.setdefault(repo, {}):
            data = self._getGitHub(repo, '/branches/' + branch)
            self.branchCommits[repo][branch] = data['commit']
        return self.branchCommits[repo][branch]

    def createTree(self, repo: str, base: str, contents: dict[str, str]) -> str:
        data: TreeSha = self._postGitHub(repo, '/git/trees', dict(
            base_tree=base,
            tree=[dict(
                path=path,
                mode='100644',
                type='blob',
                content=content
            ) for path, content in contents.items()]
        ))
        return data['sha']

    def createCommit(self, repo: str, message: str, tree: str, parents: list[str]) -> str:
        data: Commit = self._postGitHub(repo, '/git/commits', dict(
            message=message,
            tree=tree,
            parents=parents
        ))
        return data['sha']

    def createBranch(self, repo: str, branch: str, commit: str) -> None:
        self._postGitHub(repo, '/git/refs', dict(
            ref='refs/heads/' + branch,
            sha=commit
        ))

    def makeBranch(self, repo: str, branch: str, message: str, parent: Commit, contents: dict[str, str]) -> None:
        tree = self.createTree(repo, parent['commit']['tree']['sha'], contents)
        commit = self.createCommit(repo, message, tree, [parent['sha']])
        self.createBranch(repo, branch, commit)

gh: GitHub

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    print(GitHub().getToken())
else:
    import pickle
    try:
        with open('github.pickle', 'rb') as f:
            gh = pickle.load(f)
    except FileNotFoundError:
        gh = GitHub()
