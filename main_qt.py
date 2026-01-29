import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


SERVICE_OPTIONS = ["ChatGPT", "Gemini", "TikTok", "CapCut", "Facebook", "Edu"]
CHANNEL_TYPE_OPTIONS = ["YouTube", "TikTok", "Reel"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Quản lý Kênh YouTube - PySide6")
        self.resize(1200, 800)
        self.setFont(QFont("Segoe UI", 10))
        self.setWindowIcon(self._build_app_icon())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("Danh sách Email"))
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Tìm kiếm Email...")
        self.search_button = QPushButton("Tìm")
        search_row.addWidget(self.search_input, stretch=1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        self.email_list = QListWidget()
        self.email_list.addItems(["demo1@gmail.com", "demo2@gmail.com"])
        layout.addWidget(self.email_list, stretch=1)

        filter_group = QGroupBox("Bộ lọc tìm kiếm")
        filter_layout = QVBoxLayout(filter_group)
        status_row = QHBoxLayout()
        self.filter_verified = QCheckBox("Đã xác minh")
        self.filter_not_verified = QCheckBox("Chưa xác minh")
        self.filter_in_use_channel = QCheckBox("Đang dùng kênh")
        status_row.addWidget(self.filter_verified)
        status_row.addWidget(self.filter_not_verified)
        status_row.addWidget(self.filter_in_use_channel)
        status_row.addStretch(1)
        filter_layout.addLayout(status_row)

        services_row = QHBoxLayout()
        self.filter_service_boxes = []
        for service in SERVICE_OPTIONS:
            cb = QCheckBox(service)
            self.filter_service_boxes.append(cb)
            services_row.addWidget(cb)
        services_row.addStretch(1)
        filter_layout.addLayout(services_row)
        layout.addWidget(filter_group)

        import_export_row = QHBoxLayout()
        self.import_button = QPushButton("📥 Nhập Excel")
        self.export_button = QPushButton("📤 Xuất Excel")
        import_export_row.addWidget(self.import_button)
        import_export_row.addWidget(self.export_button)
        layout.addLayout(import_export_row)

        add_btn = QPushButton("➕ Thêm Email")
        delete_btn = QPushButton("🗑 Xóa Email")
        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        tabs = QTabWidget()
        tabs.addTab(self._build_email_tab(), "Chi tiết Email")
        tabs.addTab(self._build_channel_tab(), "Quản lý Kênh")
        layout.addWidget(tabs)

        return panel

    def _build_email_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info_row = QHBoxLayout()

        primary_group = QGroupBox("Email chính")
        primary_layout = QFormLayout(primary_group)
        self.email_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.show_password = QCheckBox("Hiện mật khẩu")
        self.show_password.toggled.connect(self._toggle_password_visibility)
        self.primary_2fa_input = QLineEdit()
        self.verified_by_input = QLineEdit()
        self.login_location_input = QLineEdit()
        self.is_verified_checkbox = QCheckBox("Đã xác minh")
        self.verification_failed_checkbox = QCheckBox("Xác minh bị lỗi / từ chối")

        primary_layout.addRow("Email:", self.email_input)
        password_row = QHBoxLayout()
        password_row.addWidget(self.password_input)
        password_row.addWidget(self.show_password)
        primary_layout.addRow("Mật khẩu:", password_row)
        primary_layout.addRow("Khóa 2FA:", self.primary_2fa_input)
        primary_layout.addRow("Người xác minh:", self.verified_by_input)
        primary_layout.addRow("Đăng nhập ở:", self.login_location_input)
        primary_layout.addRow("Trạng thái:", self.is_verified_checkbox)
        primary_layout.addRow("", self.verification_failed_checkbox)

        recovery_group = QGroupBox("Email khôi phục")
        recovery_layout = QFormLayout(recovery_group)
        self.recovery_email_input = QLineEdit()
        self.recovery_password_input = QLineEdit()
        self.recovery_password_input.setEchoMode(QLineEdit.Password)
        self.recovery_phone_input = QLineEdit()
        self.recovery_2fa_input = QLineEdit()

        recovery_layout.addRow("Email khôi phục:", self.recovery_email_input)
        recovery_layout.addRow("Mật khẩu khôi phục:", self.recovery_password_input)
        recovery_layout.addRow("SĐT khôi phục:", self.recovery_phone_input)
        recovery_layout.addRow("2FA khôi phục:", self.recovery_2fa_input)

        info_row.addWidget(primary_group)
        info_row.addWidget(recovery_group)
        layout.addLayout(info_row)

        otp_row = QHBoxLayout()
        otp_row.addWidget(self._build_otp_panel("OTP chính"))
        otp_row.addWidget(self._build_otp_panel("OTP Email khôi phục"))
        layout.addLayout(otp_row)

        qr_group = QGroupBox("Mã QR 2FA")
        qr_layout = QHBoxLayout(qr_group)
        qr_layout.addWidget(QPushButton("🖼️ Tải ảnh"))
        qr_layout.addWidget(QPushButton("🔍 Quét ảnh"))
        qr_layout.addWidget(QPushButton("❌ Xóa ảnh"))
        qr_layout.addStretch(1)
        layout.addWidget(qr_group)

        note_group = QGroupBox("Ghi chú Email")
        note_layout = QVBoxLayout(note_group)
        self.note_input = QTextEdit()
        note_layout.addWidget(self.note_input)
        layout.addWidget(note_group)

        services_group = QGroupBox("Dịch vụ đã dùng")
        services_layout = QHBoxLayout(services_group)
        for service in SERVICE_OPTIONS:
            services_layout.addWidget(QCheckBox(service))
        services_layout.addStretch(1)
        layout.addWidget(services_group)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(QPushButton("💾 Lưu Email"))
        layout.addLayout(save_row)

        return tab

    def _build_otp_panel(self, title: str) -> QWidget:
        group = QGroupBox(title)
        layout = QHBoxLayout(group)

        timer = QLabel("30")
        timer.setAlignment(Qt.AlignCenter)
        timer.setFixedSize(72, 72)
        timer.setStyleSheet(
            "QLabel {background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px; font: 16pt 'Segoe UI';}"
        )

        code_box = QLabel("------")
        code_box.setAlignment(Qt.AlignCenter)
        code_box.setMinimumWidth(160)
        code_box.setStyleSheet(
            "QLabel {background: #111827; color: #f9fafb; border-radius: 8px; padding: 8px; font: 28pt 'Consolas';}"
        )

        copy_btn = QPushButton("📋 Sao chép OTP")

        layout.addWidget(timer)
        layout.addWidget(code_box, stretch=1)
        layout.addWidget(copy_btn)
        return group

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _build_app_icon(self) -> QIcon:
        icon_size = 128
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)

            cloud_color = QColor("#dbeafe")
            envelope_color = QColor("#f97316")
            outline = QColor("#111827")

            painter.setPen(QPen(outline, 4))
            painter.setBrush(QBrush(cloud_color))
            painter.drawEllipse(20, 18, 88, 54)

            painter.setBrush(QBrush(envelope_color))
            painter.drawRoundedRect(24, 58, 80, 48, 8, 8)
            painter.setPen(QPen(outline, 3))
            painter.drawLine(24, 64, 64, 90)
            painter.drawLine(104, 64, 64, 90)
        finally:
            painter.end()
        return QIcon(pixmap)

    def _build_channel_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form_group = QGroupBox("Thông tin Kênh")
        form_layout = QFormLayout(form_group)
        self.channel_url_input = QLineEdit()
        self.channel_name_input = QLineEdit()
        self.channel_type_combo = QComboBox()
        self.channel_type_combo.addItems(CHANNEL_TYPE_OPTIONS)
        self.channel_note_input = QLineEdit()
        self.channel_in_use = QCheckBox("Đang sử dụng")

        form_layout.addRow("URL Kênh:", self.channel_url_input)
        form_layout.addRow("Tên Kênh:", self.channel_name_input)
        form_layout.addRow("Loại kênh:", self.channel_type_combo)
        form_layout.addRow("Ghi chú:", self.channel_note_input)
        form_layout.addRow("", self.channel_in_use)
        layout.addWidget(form_group)

        btn_row = QHBoxLayout()
        btn_row.addWidget(QPushButton("🌐 Lấy tên"))
        btn_row.addWidget(QPushButton("💾 Lưu Kênh"))
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        channels_group = QGroupBox("Danh sách Kênh")
        channels_layout = QVBoxLayout(channels_group)
        self.channel_list = QListWidget()
        self.channel_list.addItems(
            ["YouTube | Kênh Demo", "TikTok | Kênh Demo 2", "Reel | Kênh Demo 3"]
        )
        channels_layout.addWidget(self.channel_list)
        layout.addWidget(channels_group, stretch=1)

        return tab


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
