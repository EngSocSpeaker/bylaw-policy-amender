import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QTableView, QPushButton, QStyleFactory, QHeaderView
)

from github import gh
from model import (
    TreeFileDelegate, FileSectionDelegate, ProposedAmendmentDelegate,
    AmendmentsModel
)

FILTER = 'JSON Files (*.json)'

class AmendmentsView(QTableView):
    def __init__(self) -> None:
        super().__init__()

        treeFileDelegate = TreeFileDelegate(self)
        fileSectionDelegate = FileSectionDelegate(self)
        proposedAmendmentDelegate = ProposedAmendmentDelegate(self)
        self.setItemDelegateForColumn(0, treeFileDelegate)
        self.setItemDelegateForColumn(1, fileSectionDelegate)
        self.setItemDelegateForColumn(3, proposedAmendmentDelegate)
        self.verticalHeader().hide()
        self.resizeColumnsToContents()

        self.horizontalHeader().sectionResized.connect(self.resizeRowsToContents)

class Amender(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setMinimumWidth(800)
        self.setWindowTitle('Bylaw/Policy Amendments')

        self.amendmentsModel = AmendmentsModel()

        header = QLabel('<h1>Bylaw/Policy Amendments</h1>')

        addButton = QPushButton('Add')
        addButton.clicked.connect(self.addAmendment)
        delButton = QPushButton('Remove')
        delButton.clicked.connect(self.delAmendment)
        sortButton = QPushButton('Sort')
        sortButton.clicked.connect(self.sortAmendments)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(addButton)
        buttonLayout.addWidget(delButton)
        buttonLayout.addWidget(sortButton)

        self.amendmentsView = AmendmentsView()
        self.amendmentsView.setModel(self.amendmentsModel)
        self.amendmentsView.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.amendmentsView.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.amendmentsModel.dataChanged.connect(lambda: self.amendmentsView.resizeColumnToContents(1))
        self.amendmentsModel.dataChanged.connect(self.amendmentsView.resizeRowsToContents)

        self.addAmendment()

        openButton = QPushButton('Open')
        openButton.clicked.connect(self.openAmendments)
        saveButton = QPushButton('Save')
        saveButton.clicked.connect(self.saveAmendments)

        fileLayout = QHBoxLayout()
        fileLayout.addWidget(openButton)
        fileLayout.addWidget(saveButton)

        layout = QVBoxLayout(self)

        layout.addWidget(header)
        layout.addLayout(buttonLayout)
        layout.addWidget(self.amendmentsView)
        layout.addLayout(fileLayout)

        self.setLayout(layout)

    def addAmendment(self) -> None:
        if self.amendmentsModel.rowCount() > 0:
            path = str(self.amendmentsModel.index(self.amendmentsModel.rowCount() - 1, 0).data(Qt.ItemDataRole.EditRole))
        else:
            path = [item['path'] for item in gh.getTree('skule/bylaws') if item['path'].endswith('.tex')][0]
        self.amendmentsModel.appendRow(path)
        self.amendmentsView.openPersistentEditor(self.amendmentsModel.index(self.amendmentsModel.rowCount() - 1, 0))
        self._resize()

    def delAmendment(self) -> None:
        rows = sorted({i.row() for i in self.amendmentsView.selectedIndexes()})
        if not rows:
            return
        firstRow = rows[0]
        for row in rows[::-1]:
            self.amendmentsModel.removeRow(row)
        if self.amendmentsModel.rowCount() == 0:
            self.addAmendment()
        self._resize()
        self.amendmentsView.selectRow(firstRow)

    def sortAmendments(self) -> None:
        self.amendmentsModel.naturalSort()
        self._resize()

    def _resize(self) -> None:
        self.amendmentsView.resizeColumnToContents(0)
        self.amendmentsView.resizeColumnToContents(1)
        self.amendmentsView.resizeRowsToContents()

    def openAmendments(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, filter=FILTER, selectedFilter=FILTER)
        self.amendmentsModel.open(path)
        for i in range(self.amendmentsModel.rowCount()):
            self.amendmentsView.openPersistentEditor(self.amendmentsModel.index(i, 0))
        self._resize()

    def saveAmendments(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, filter=FILTER, selectedFilter=FILTER)
        self.amendmentsModel.save(path)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    QApplication.setStyle(QStyleFactory.create('Fusion'))
    widget = Amender()
    widget.show()
    try:
        sys.exit(app.exec())
    finally:
        import pickle
        with open('github.pickle', 'wb') as f:
            pickle.dump(gh, f)
