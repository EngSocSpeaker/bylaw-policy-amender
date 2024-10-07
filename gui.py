import re
import sys
from typing import cast
from PySide6.QtCore import (
    QAbstractItemModel, QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
)
from PySide6.QtWidgets import (
    QApplication, QStyleOptionViewItem, QWidget, QVBoxLayout, QLabel,
    QTableView, QPushButton, QStyledItemDelegate, QComboBox, QStyleFactory,
    QLineEdit, QHeaderView, QTextEdit
)

from github import gh
from str_manip import SectionValidator, sectionToTuple, sectionsForLines, texToLines

class TreeFileDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QWidget:
        cb = QComboBox(parent)
        cb.addItems([item['path'] for item in gh.getTree('skule/bylaws') if item['path'].endswith('.tex')])
        self.setEditorData(cb, index)
        cb.currentIndexChanged.connect(lambda: self.commitData.emit(cb))
        return cb

    def setEditorData(self, cb: QComboBox, index: QModelIndex | QPersistentModelIndex) -> None:
        cb.setCurrentText(str(index.data(Qt.ItemDataRole.EditRole)))

    def setModelData(self, cb: QComboBox, model: QAbstractItemModel, index: QModelIndex | QPersistentModelIndex) -> None:
        model.setData(index, cb.currentText(), Qt.ItemDataRole.EditRole)

class FileSectionDelegate(QStyledItemDelegate):

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QWidget:
        line = QLineEdit(parent)
        self.setEditorData(line, index)
        lines, start2 = cast(AmendmentsModel, index.model()).getLines(index)
        line.setValidator(SectionValidator(set(sectionsForLines(lines).keys()), start2))
        return line

    def setEditorData(self, line: QLineEdit, index: QModelIndex | QPersistentModelIndex) -> None:
        line.setText(str(index.data(Qt.ItemDataRole.EditRole)))

    def setModelData(self, line: QLineEdit, model: QAbstractItemModel, index: QModelIndex | QPersistentModelIndex) -> None:
        model.setData(index, line.text(), Qt.ItemDataRole.EditRole)

class ProposedAmendmentDelegate(QStyledItemDelegate):

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QWidget:
        box = QTextEdit(parent)
        self.setEditorData(box, index)
        return box

    def setEditorData(self, box: QTextEdit, index: QModelIndex | QPersistentModelIndex) -> None:
        box.setText(str(index.data(Qt.ItemDataRole.EditRole)))

    def setModelData(self, box: QTextEdit, model: QAbstractItemModel, index: QModelIndex | QPersistentModelIndex) -> None:
        model.setData(index, box.toPlainText(), Qt.ItemDataRole.EditRole)

class AmendmentsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()

        self.amendments: list[list[str]] = []

    def getLines(self, index: QModelIndex | QPersistentModelIndex) -> tuple[list[str], int]:
        gh.getTree('skule/bylaws') # ensure it's fetched
        path = self.amendments[index.row()][0]
        tex = gh.getBlob(str(gh.repoPathUrls['skule/bylaws'][path]))
        start2 = 0 if 'Start2=0' in tex else 1
        return texToLines(tex), start2

    def headerData(self, section: int, orientation: Qt.Orientation, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole):
        if role not in {
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.AccessibleTextRole,
        }:
            return None
        if orientation == Qt.Orientation.Vertical:
            return None
        try:
            return ['File', 'Section', 'Current text', 'Proposed text'][section]
        except IndexError:
            return None

    def appendRow(self, path: str | None = None) -> None:
        self.insertRow(self.rowCount())
        if path is not None:
            self.amendments[-1][0] = path
            self.dataChanged.emit(self.index(self.rowCount() - 1, 0),
                                  self.index(self.rowCount() - 1, 0))

    def insertRows(self, row: int, count: int, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> bool:
        if row < 0 or row > self.rowCount():
            return False
        self.beginInsertRows(parent, row, row + count - 1)
        self.amendments[row:row] = [[''] * 4 for _ in range(count)]
        self.endInsertRows()
        return True

    def rowCount(self, parent=...) -> int:
        return len(self.amendments)

    def columnCount(self, parent=...) -> int:
        return 4

    def data(self, index: QModelIndex | QPersistentModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role not in {
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.AccessibleTextRole,
        }:
            return None
        try:
            return self.amendments[index.row()][index.column()]
        except IndexError:
            return None

    def setData(self, index: QModelIndex | QPersistentModelIndex, value, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> bool:
        if role not in {
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.AccessibleTextRole,
        }:
            return False
        if index.column() == 2:
            return False
        try:
            self.amendments[index.row()][index.column()] = value
        except IndexError:
            return False
        if index.column() == 0:
            self.amendments[index.row()][1:] = [''] * 3
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 3))
        elif index.column() == 1:
            if not value:
                self.amendments[index.row()][2:] = [''] * 2
            else:
                lines, start2 = self.getLines(index)
                line = lines[sectionsForLines(lines)[sectionToTuple(value, start2)]]
                line = re.sub(r'^[\s&]*', '', line)
                self.amendments[index.row()][2:] = [line, line]
            self.dataChanged.emit(self.index(index.row(), 1), self.index(index.row(), 3))
        else:
            self.dataChanged.emit(self.index(index.row(), 3), self.index(index.row(), 3))
        return True

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        flag = Qt.ItemFlag.ItemIsEnabled
        if index.column() != 2:
            flag |= Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable
        return flag

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

        button = QPushButton('Add')
        button.clicked.connect(self.addAmendment)

        self.amendmentsView = AmendmentsView()
        self.amendmentsView.setModel(self.amendmentsModel)
        self.amendmentsView.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.amendmentsView.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.amendmentsModel.dataChanged.connect(lambda: self.amendmentsView.resizeColumnToContents(1))
        self.amendmentsModel.dataChanged.connect(self.amendmentsView.resizeRowsToContents)

        self.addAmendment()

        layout = QVBoxLayout(self)

        layout.addWidget(header)
        layout.addWidget(button)
        layout.addWidget(self.amendmentsView)

        self.setLayout(layout)

    def addAmendment(self) -> None:
        if self.amendmentsModel.rowCount() > 0:
            path = str(self.amendmentsModel.index(self.amendmentsModel.rowCount() - 1, 0).data(Qt.ItemDataRole.EditRole))
        else:
            path = [item['path'] for item in gh.getTree('skule/bylaws') if item['path'].endswith('.tex')][0]
        self.amendmentsModel.appendRow(path)
        self.amendmentsView.openPersistentEditor(self.amendmentsModel.index(self.amendmentsModel.rowCount() - 1, 0))
        self.amendmentsView.resizeColumnToContents(0)
        self.amendmentsView.resizeColumnToContents(1)
        self.amendmentsView.resizeRowsToContents()

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
