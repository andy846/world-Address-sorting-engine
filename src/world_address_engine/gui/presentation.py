"""Scoped native-workbench presentation; no data or application behavior."""
from PySide6.QtGui import QFont, QPalette
from PySide6.QtCore import Qt


def palette_tokens(dark: bool) -> dict[str, str]:
    if dark:
        return {
            'background': '#111b24', 'surface': '#192631', 'raised': '#20313f',
            'text': '#e8eff4', 'muted': '#a8bac7', 'border': '#3d5364',
            'primary': '#6edbd0', 'on_primary': '#0e2625', 'primary_hover': '#8be4db',
            'focus': '#6edbd0', 'warning': '#ffd08a', 'warning_surface': '#302b25',
            'success': '#82dfb5', 'success_surface': '#1c302a',
            'inferred': '#a6c8ff', 'inferred_surface': '#1f3048',
            'disabled': '#8397a7', 'disabled_surface': '#24323d',
            'danger': '#ffb4b0',
        }
    return {
        'background': '#edf2f5', 'surface': '#ffffff', 'raised': '#f5f8fa',
        'text': '#173244', 'muted': '#526674', 'border': '#bdcbd4',
        'primary': '#006c67', 'on_primary': '#ffffff', 'primary_hover': '#005852',
        'focus': '#006c67', 'warning': '#8a4900', 'warning_surface': '#fff4df',
        'success': '#146b4b', 'success_surface': '#e8f5ee',
        'inferred': '#2859a3', 'inferred_surface': '#eaf0fc',
        'disabled': '#647681', 'disabled_surface': '#dde5ea',
        'danger': '#b42318',
    }


def sync_workbench_fonts(window) -> None:
    """Qt stylesheets otherwise pin descendants to the application's old font."""
    from PySide6.QtWidgets import QWidget
    base = QFont(window.font())
    for widget in window.findChildren(QWidget):
        role = widget.property('workbenchRole')
        if role == 'metricValue':
            continue
        font = QFont(base)
        if role == 'title':
            font.setPointSizeF(max(12, base.pointSizeF() * 1.35))
            font.setBold(True)
        widget.setFont(font)
    window.results._update_metric_fonts()


def apply_workbench_theme(window, *, dark=None) -> None:
    """Respect the platform palette at startup without restyling other windows."""
    from PySide6.QtGui import QColor

    if dark is None:
        dark = window.palette().color(QPalette.ColorRole.Window).lightness() < 128
    t = palette_tokens(dark)
    palette = QPalette(window.palette())
    for role, token in (
            ('Window', 'background'), ('WindowText', 'text'), ('Base', 'surface'),
            ('AlternateBase', 'raised'), ('Text', 'text'), ('Button', 'raised'),
            ('ButtonText', 'text'), ('Highlight', 'primary'), ('HighlightedText', 'on_primary'),
            ('PlaceholderText', 'muted'), ('Link', 'primary'), ('Light', 'border'),
            ('Midlight', 'raised'), ('Dark', 'background'), ('Mid', 'border'),
            ('Shadow', 'background'), ('ToolTipBase', 'surface'), ('ToolTipText', 'text')):
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(t[token]))
    for role in ('Text', 'WindowText', 'ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(t['disabled']))
    window.setPalette(palette)
    if hasattr(window, 'results'):
        window.results.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        window.results.tabs.widget(1).setObjectName('countryCasesPage')
    window.setProperty('workbenchTheme', 'dark' if dark else 'light')
    window.setStyleSheet(f'''
        QWidget#workbenchRoot {{ background: {t['background']}; color: {t['text']}; }}
        QWidget#workspacePanel, QWidget#countryResults,
        QWidget#workspaceViewport, QWidget#settingsViewport {{ background: {t['background']}; }}
        QWidget#countryCasesPage {{ background: {t['surface']}; }}
        QFrame[workbenchRole="card"], QFrame[workbenchRole="metricCard"] {{
            background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
        }}
        QFrame[workbenchRole="metricCard"][tone="success"] {{ background: {t['success_surface']}; }}
        QFrame[workbenchRole="metricCard"][tone="inferred"] {{ background: {t['inferred_surface']}; }}
        QFrame[workbenchRole="metricCard"][tone="warning"] {{ background: {t['warning_surface']}; }}
        QLabel {{ color: {t['text']}; background: transparent; border: none; }}
        QLabel[workbenchRole="muted"] {{ color: {t['muted']}; }}
        QLabel[workbenchRole="section"] {{ color: {t['muted']}; font-weight: 600; }}
        QLabel[workbenchRole="badge"] {{
            color: {t['success']}; background: {t['success_surface']};
            border: 1px solid {t['border']}; border-radius: 5px; padding: 4px 8px;
        }}
        QLabel[workbenchRole="metricValue"] {{ font-weight: 600; }}
        QPushButton {{
            background: {t['raised']}; color: {t['text']}; border: 1px solid {t['border']};
            border-radius: 6px; padding: 6px 10px; min-height: 20px;
        }}
        QPushButton:hover {{ border-color: {t['focus']}; }}
        QPushButton:checked {{ background: {t['raised']}; border-color: {t['focus']}; }}
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus,
        QTableWidget:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border: 2px solid {t['focus']};
        }}
        QPushButton[workbenchRole="primary"] {{
            background: {t['primary']}; color: {t['on_primary']}; border-color: {t['primary']}; font-weight: 600;
        }}
        QPushButton[workbenchRole="primary"]:hover {{ background: {t['primary_hover']}; }}
        QPushButton[workbenchRole="primary"]:focus {{ border: 2px solid {t['on_primary']}; }}
        QPushButton:disabled {{ background: {t['disabled_surface']}; color: {t['disabled']}; border-color: {t['border']}; }}
        QLineEdit, QComboBox, QListWidget, QPlainTextEdit, QTextEdit {{
            color: {t['text']}; background: {t['surface']}; border: 1px solid {t['border']};
            border-radius: 5px; padding: 5px;
        }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QListWidget::item {{ padding: 5px; border-radius: 3px; }}
        QListWidget::item:selected {{ background: {t['primary']}; color: {t['on_primary']}; }}
        QLineEdit#outputLocation {{ background: transparent; border: none; padding: 2px; }}
        QTableWidget {{
            color: {t['text']}; background: {t['surface']}; alternate-background-color: {t['raised']};
            border: 1px solid {t['border']}; border-radius: 5px; gridline-color: {t['border']};
            selection-background-color: {t['primary']}; selection-color: {t['on_primary']};
        }}
        QTableWidget::item {{ padding: 6px 8px; }}
        QHeaderView::section {{
            color: {t['muted']}; background: {t['raised']};
            padding: 8px; border: none; border-bottom: 1px solid {t['border']}; font-weight: 600;
        }}
        QHeaderView {{ background: {t['raised']}; color: {t['muted']}; }}
        QTableCornerButton::section {{ background: {t['raised']}; border: 1px solid {t['border']}; }}
        QTabWidget::pane {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; }}
        QTabBar::tab {{ color: {t['muted']}; background: transparent; padding: 9px 12px; border-bottom: 2px solid transparent; }}
        QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['primary']}; }}
        QTabBar::tab:focus {{ border: 2px solid {t['focus']}; }}
        QProgressBar {{
            color: {t['text']}; background: {t['raised']}; border: 1px solid {t['border']};
            border-radius: 4px; text-align: center; min-height: 16px;
        }}
        QProgressBar::chunk {{ background: {t['primary']}; border-radius: 3px; }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollBar:vertical {{ background: {t['background']}; width: 12px; }}
        QScrollBar:horizontal {{ background: {t['background']}; height: 12px; }}
        QScrollBar::handle:vertical {{ background: {t['border']}; min-height: 24px; margin: 2px; border-radius: 4px; }}
        QScrollBar::handle:horizontal {{ background: {t['border']}; min-width: 24px; margin: 2px; border-radius: 4px; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QSplitter::handle {{ background: {t['border']}; }}
        QSplitter::handle:horizontal {{ width: 4px; margin: 2px; }}
        QSplitter::handle:vertical {{ height: 4px; margin: 2px; }}
        QStatusBar {{ color: {t['muted']}; background: {t['background']}; }}
        QToolTip {{ color: {t['text']}; background: {t['surface']}; border: 1px solid {t['border']}; padding: 5px; }}
    ''')
    from PySide6.QtWidgets import QWidget
    for child in window.findChildren(QWidget):
        child.setPalette(palette)
    sync_workbench_fonts(window)
