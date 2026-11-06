"""공통 위젯: 카드, 배지, 막대, 검색·필터 표."""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QProgressBar, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QTableView, QVBoxLayout, QWidget)

from . import theme


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


class Badge(QLabel):
    """상태 배지: success / warn / error / neutral / info."""

    def __init__(self, text: str = "", kind: str = "neutral"):
        super().__init__(text)
        self.set(text, kind)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, text: str, kind: str):
        self.setText(text)
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)


class Card(QFrame):
    """흰 카드. clickable이면 눌렀을 때 clicked."""
    clicked = Signal()

    def __init__(self, title: str = "", code: str = "", clickable: bool = False):
        super().__init__()
        self.setObjectName("card")
        self.setProperty("clickable", clickable)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        if title or code:
            head = QHBoxLayout()
            head.addWidget(label(title, "cardTitle"))
            head.addStretch(1)
            if code:
                head.addWidget(label(code, "chip"))
            self.body.addLayout(head)

    def mouseReleaseEvent(self, event):
        if self.property("clickable") and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class RateBar(QProgressBar):
    def __init__(self, warn: bool = False):
        super().__init__()
        self.setRange(0, 1000)
        self.setTextVisible(False)
        if warn:
            self.setObjectName("barWarn")

    def set_rate(self, percent: float):
        self.setValue(int(round(max(0.0, min(100.0, percent)) * 10)))


class BigNumber(QWidget):
    """큰 숫자 + 단위."""

    def __init__(self, value: str = "—", unit: str = ""):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.value = label(value, "bigNumber")
        self.unit = label(unit, "bigUnit")
        row.addWidget(self.value, 0, Qt.AlignBottom)
        row.addWidget(self.unit, 0, Qt.AlignBottom)
        row.addStretch(1)

    def set(self, value: str, unit: str | None = None):
        self.value.setText(value)
        if unit is not None:
            self.unit.setText(unit)


class Kpi(Card):
    """작은 숫자 카드: 제목 + 큰 숫자."""

    def __init__(self, title: str):
        super().__init__()
        self.body.setSpacing(4)
        self.title = label(title, "muted")
        self.body.addWidget(self.title)
        self.number = BigNumber()
        self.body.addWidget(self.number)


class RowsModel(QAbstractTableModel):
    """행 목록 표. kinds[i] = 'error'/'warn'/None 이면 행 바탕색. check_col이 있으면 그 열이 체크박스."""
    checked_changed = Signal()

    def __init__(self, headers: list, parent=None):
        super().__init__(parent)
        self.headers = headers
        self.rows, self.kinds, self.checks = [], [], []
        self.check_col = None
        self.single_check = False   # True면 하나만 체크 (새로 체크하면 나머지는 풀림)
        self.mono_cols = set()
        self.editable_cols = set()
        self.result_col = None   # 결과(정상/오류) 열: 글자에 상태 색을 입힘
        self.cell_marks = {}     # {글자: 색} — 이 글자인 칸만 굵게 색칠 (예: 진단결과의 'N')

    def set_rows(self, rows: list, kinds: list | None = None, checks: list | None = None):
        self.beginResetModel()
        self.rows = [list(r) for r in rows]
        self.kinds = list(kinds) if kinds else [None] * len(rows)
        self.checks = list(checks) if checks is not None else []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if c == self.check_col:
            if role == Qt.CheckStateRole:
                return Qt.Checked if self.checks[r] else Qt.Unchecked
            if role == Qt.DisplayRole:
                return ""
        value = self.rows[r][c]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return "" if value is None else str(value)
        if role == Qt.ToolTipRole and value is not None and len(str(value)) > 20:
            return str(value)   # 칸이 좁아 잘려도 마우스를 올리면 전체가 보인다
        if role == Qt.BackgroundRole:
            kind = "selected" if (self.check_col is not None and self.checks and self.checks[r]) else self.kinds[r]
            return theme.ROW_TINT.get(kind)
        if role == Qt.FontRole and c in self.mono_cols:
            return QFont(theme.MONO, 10)
        if role == Qt.ForegroundRole and c == self.result_col:
            return QColor(theme.KINDS[self.kinds[r] or "success"][0])   # 오류 빨강, 경고 주황, 정상 초록
        if self.cell_marks and str(value) in self.cell_marks:
            if role == Qt.ForegroundRole:
                return QColor(self.cell_marks[str(value)])
            if role == Qt.FontRole:
                font = QFont()
                font.setBold(True)
                return font
        if role == Qt.TextAlignmentRole and c in getattr(self, "center_cols", ()):
            return int(Qt.AlignCenter)
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == self.check_col:
            f |= Qt.ItemIsUserCheckable
        if index.column() in self.editable_cols:
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.EditRole):
        r, c = index.row(), index.column()
        if c == self.check_col and role == Qt.CheckStateRole:
            self.checks[r] = Qt.CheckState(value) == Qt.Checked
            if self.single_check and self.checks[r]:
                self.checks = [i == r for i in range(len(self.checks))]
                self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))
            else:
                self.dataChanged.emit(self.index(r, 0), self.index(r, self.columnCount() - 1))
            self.checked_changed.emit()
            return True
        if role == Qt.EditRole and c in self.editable_cols:
            self.rows[r][c] = value
            self.dataChanged.emit(index, index)
            return True
        return False


class _Filter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.only_flagged = False
        self.row_filter = None   # 화면이 정하는 추가 조건: row_filter(원본 행 번호) -> bool
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def lessThan(self, left, right):
        """숫자는 숫자로, 나머지는 글자로 비교 (9 < 89)."""
        a = self.sourceModel().rows[left.row()][left.column()]
        b = self.sourceModel().rows[right.row()][right.column()]
        try:
            return float(a) < float(b)
        except (TypeError, ValueError):
            return str("" if a is None else a) < str("" if b is None else b)

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        if self.only_flagged and not model.kinds[row]:
            return False
        if self.row_filter and not self.row_filter(row):
            return False
        if not self.text:
            return True
        needle = self.text.upper()
        return any(needle in str(v).upper() for v in model.rows[row] if v is not None)


class _PaddedDelegate(QStyledItemDelegate):
    """칸 글자를 머리글과 같이 좌우 10px 띄운다 (QSS ::item padding은 표에 먹지 않음)."""
    PAD = 10

    def paint(self, painter, option, index):
        # 바탕(행 색·선택 색)은 칸 전체에 먼저 칠하고, 내용만 안쪽으로 그린다
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.brush(QPalette.Highlight))
        else:
            background = index.data(Qt.BackgroundRole)
            if background is not None:
                painter.fillRect(option.rect, background)
        inner = QStyleOptionViewItem(option)
        inner.rect = option.rect.adjusted(self.PAD, 0, -self.PAD, 0)
        super().paint(painter, inner, index)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setWidth(size.width() + 2 * self.PAD)
        return size


class TableBox(Card):
    """검색창 + '문제만 보기' + 표가 들어간 카드."""

    def __init__(self, headers: list, flag_label: str | None = "오류만 보기"):
        super().__init__()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(14, 12, 14, 12)
        bar.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("검색")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("표 검색")
        bar.addWidget(self.search, 1)
        self.count = label("", "muted")
        bar.addWidget(self.count)
        self.flag = None
        if flag_label:
            self.flag = QCheckBox(flag_label)
            bar.addWidget(self.flag)
        self.body.addLayout(bar)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {theme.BORDER};")
        self.body.addWidget(line)

        self.model = RowsModel(headers, self)
        self.proxy = _Filter()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(_PaddedDelegate(self.view))
        self.view.setSortingEnabled(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(36)
        self.view.setShowGrid(False)
        self.view.setWordWrap(False)
        self.wrap_cols = {}   # {열: 폭} — 이 열은 줄바꿈해서 전체를 보여 주고 행 높이를 글에 맞춘다
        self._sizing = False   # set_rows가 열 폭을 정하는 동안은 행 높이를 다시 재지 않는다
        self.view.horizontalHeader().sectionResized.connect(self._fit_rows)
        header = self.view.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setResizeContentsPrecision(80)   # 열 폭은 앞쪽 80행만 보고 정한다 (행이 많아도 빠르게)
        header.setSortIndicator(-1, Qt.AscendingOrder)   # 처음에는 원래 순서
        self.view.setMinimumHeight(260)
        self.body.addWidget(self.view, 1)
        self.placeholder = label("표시할 행이 없습니다.", "muted")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setMinimumHeight(120)
        self.body.addWidget(self.placeholder, 1)
        self.placeholder.setVisible(False)

        self.search.textChanged.connect(self._refilter)
        if self.flag:
            self.flag.toggled.connect(self._refilter)

    def refilter(self):
        """검색창·체크 밖의 조건(row_filter)이 바뀌었을 때."""
        self._refilter()

    def _refilter(self, *_):
        self.proxy.text = self.search.text().strip()
        self.proxy.only_flagged = bool(self.flag and self.flag.isChecked())
        self.proxy.invalidateFilter()
        self._update_count()
        self._fit_rows()   # 줄바꿈 열이 있으면 보이는 행 높이를 글에 맞춘다 (한 번만)

    def _update_count(self):
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count.setText(f"{shown:,} / {total:,}행" if shown != total else f"{total:,}행")

    def set_rows(self, rows: list, kinds: list | None = None, checks: list | None = None, empty: str = ""):
        self._sizing = True
        self.model.set_rows(rows, kinds, checks)
        self.view.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.proxy.sort(-1)
        self.view.resizeColumnsToContents()
        for c in range(self.model.columnCount()):
            self.view.setColumnWidth(c, min(max(self.view.columnWidth(c) + 24, 64), 320))
        for c, width in self.wrap_cols.items():
            self.view.setColumnWidth(c, width)
        self._sizing = False
        has_rows = bool(rows)
        self.view.setVisible(has_rows)
        self.placeholder.setVisible(not has_rows)
        self.placeholder.setText(empty or "표시할 행이 없습니다.")
        self._refilter()

    def wrap(self, columns: dict):
        """columns = {열: 폭}. 그 열은 줄바꿈해서 내용을 다 보여 준다 (다른 열은 한 줄 그대로)."""
        self.wrap_cols = dict(columns)
        self.view.setWordWrap(bool(columns))


    def _fit_rows(self, *_):
        if self.wrap_cols and not self._sizing:
            for r in range(self.proxy.rowCount()):   # 줄바꿈 열 글이 길거나 여러 줄인 행만 다시 잰다
                source = self.proxy.mapToSource(self.proxy.index(r, 0)).row()
                if any(_long(self.model.rows[source][c], w) for c, w in self.wrap_cols.items()):
                    self.view.resizeRowToContents(r)


def _long(value, width: int) -> bool:
    text = str(value or "")
    return "\n" in text or len(text) * 13 > width - 24   # 한글 한 글자 ≈ 13px


class EmptyState(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(f"color: {theme.MUTED}; border: 1px dashed #D0D5DD; border-radius: 12px; padding: 28px;"
                           f" background: {theme.SURFACE};")


def hbox(*widgets, spacing: int = 16, stretch_last: bool = False) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(spacing)
    for w in widgets:
        row.addWidget(w, 1)
    if stretch_last:
        row.addStretch(1)
    return row
