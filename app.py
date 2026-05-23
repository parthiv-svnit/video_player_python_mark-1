import sys
import os
import vlc
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QSlider, QFileDialog, 
                             QLabel, QSpacerItem, QSizePolicy, QStackedWidget,
                             QScrollArea)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, QRect
from PyQt6.QtGui import QCursor

# MX Player Web-Style CSS (QSS) mapped exactly to Tailwind specifications
MODERN_STYLE = """
QMainWindow, QWidget#landingPage {
    background-color: #121212;
}
QWidget#playerPage, QWidget#videoFrame {
    background-color: #000000;
}
QWidget#topBar {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0, 0, 0, 150), stop:1 rgba(0, 0, 0, 0));
}
QWidget#bottomBar {
    background-color: qlineargradient(spread:pad, x1:0, y1:1, x2:0, y2:0, stop:0 rgba(0, 0, 0, 204), stop:1 rgba(0, 0, 0, 0));
}
QWidget#sidePanel {
    background-color: rgba(0, 0, 0, 204); /* black/80 */
}
QPushButton {
    background: transparent;
    border: none;
    color: #ffffff;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
}
QPushButton:hover {
    color: #3b82f6; /* blue-500 */
}
QPushButton:disabled {
    color: rgba(255, 255, 255, 128); /* opacity-50 */
}
QPushButton#primaryBtn {
    background-color: #2563eb; /* blue-600 */
    color: #ffffff;
    border-radius: 25px;
    padding: 16px 32px;
    font-size: 20px;
}
QPushButton#primaryBtn:hover {
    background-color: #1d4ed8; /* blue-700 */
}
QPushButton#unlockBtn {
    background-color: rgba(0, 0, 0, 178); /* black/70 */
    border-radius: 25px;
    font-size: 20px;
}
QPushButton#unlockBtn:hover {
    color: #ffffff;
    background-color: rgba(59, 130, 246, 204); /* blue accent */
}
QPushButton.trackBtn {
    background-color: rgba(55, 65, 81, 128); /* gray-700/50 */
    text-align: left;
    padding: 12px;
    border-radius: 4px;
    margin-bottom: 8px;
    font-size: 14px;
}
QPushButton.trackBtn:hover {
    background-color: rgba(75, 85, 101, 128);
}
QSlider::groove:horizontal {
    background: rgba(255, 255, 255, 76); /* white/30 */
    height: 4px;
    border-radius: 2px;
}
QSlider::groove:horizontal:hover {
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3b82f6;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 2px;
}
QLabel {
    color: #e0e0e0;
    font-family: 'Inter', sans-serif;
}
QLabel#notificationLabel {
    background-color: rgba(0, 0, 0, 178); /* black/70 */
    color: #ffffff;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 18px;
}
QLabel#progressTooltip {
    background-color: rgba(0, 0, 0, 178); /* black/70 */
    color: #ffffff;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
}
QScrollBar:vertical {
    border: none;
    background: rgba(255, 255, 255, 25);
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #3b82f6;
    border-radius: 3px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}
"""

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MX Player - Desktop Edition")
        self.setGeometry(100, 100, 1280, 720)
        self.setStyleSheet(MODERN_STYLE)
        
        # State Variables
        self.playlist = []
        self.current_index = 0
        self.is_locked = False
        self.is_slider_dragging = False
        self.tracks_populated = False
        self.show_remaining_time = False
        self.active_panel = None
        
        # VLC Engine setup
        self.instance = vlc.Instance("--no-xlib --drop-late-frames")
        self.media_player = self.instance.media_player_new()
        
        self.init_ui()
        self.setup_autohide()
        
        # UI Update Timer
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)

    def init_ui(self):
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stacked_widget = QStackedWidget(self)
        self.main_layout.addWidget(self.stacked_widget)
        
        # --- 1. Landing Page ---
        self.landing_page = QWidget()
        self.landing_page.setObjectName("landingPage")
        landing_layout = QVBoxLayout(self.landing_page)
        landing_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_label = QLabel("<span style='color:#3b82f6'>MX</span> Player")
        title_label.setStyleSheet("font-size: 48px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle_label = QLabel("Your Personal Video Player")
        subtitle_label.setStyleSheet("color: #9ca3af; font-size: 18px; margin-bottom: 30px;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.open_main_btn = QPushButton("📂 Open Video(s)")
        self.open_main_btn.setObjectName("primaryBtn")
        self.open_main_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_main_btn.clicked.connect(self.open_file)
        
        landing_layout.addWidget(title_label)
        landing_layout.addWidget(subtitle_label)
        landing_layout.addWidget(self.open_main_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # --- 2. Player Page (OVERLAYS) ---
        self.player_page = QWidget()
        self.player_page.setObjectName("playerPage")
        
        self.video_container = QWidget(self.player_page)
        
        # Base Video Layer
        self.video_frame = QWidget(self.video_container)
        self.video_frame.setObjectName("videoFrame")
        
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(int(self.video_frame.winId()))

        # Top Control Bar
        self.top_bar = QWidget(self.video_container)
        self.top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(16, 16, 16, 16)
        
        self.back_btn = QPushButton("←")
        self.back_btn.setStyleSheet("font-size: 24px; padding-right: 15px;")
        self.back_btn.clicked.connect(self.go_back)
        
        self.video_title = QLabel("")
        self.video_title.setStyleSheet("font-size: 18px; font-weight: 600;")
        
        self.audio_btn = QPushButton("🎵")
        self.audio_btn.setStyleSheet("font-size: 20px;")
        self.audio_btn.clicked.connect(lambda: self.toggle_side_panel("audio"))
        
        self.subtitle_btn = QPushButton("💬")
        self.subtitle_btn.setStyleSheet("font-size: 20px;")
        self.subtitle_btn.clicked.connect(lambda: self.toggle_side_panel("subtitle"))
        
        top_layout.addWidget(self.back_btn)
        top_layout.addWidget(self.video_title)
        top_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        top_layout.addWidget(self.audio_btn)
        top_layout.addSpacing(15)
        top_layout.addWidget(self.subtitle_btn)
        
        # Bottom Control Bar
        self.bottom_bar = QWidget(self.video_container)
        self.bottom_bar.setObjectName("bottomBar")
        bottom_layout = QVBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        
        # Progress Area
        progress_layout = QHBoxLayout()
        self.time_current = QLabel("00:00")
        self.time_current.setStyleSheet("font-family: monospace; font-size: 12px;")
        
        self.time_total = QLabel("00:00")
        self.time_total.setStyleSheet("font-family: monospace; font-size: 12px;")
        self.time_total.setCursor(Qt.CursorShape.PointingHandCursor)
        self.time_total.mousePressEvent = self.toggle_time_display # Click to show remaining
        
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.position_slider.sliderPressed.connect(self.slider_pressed)
        self.position_slider.sliderReleased.connect(self.slider_released)
        self.position_slider.installEventFilter(self) # For tooltip hover
        
        progress_layout.addWidget(self.time_current)
        progress_layout.addWidget(self.position_slider)
        progress_layout.addWidget(self.time_total)
        bottom_layout.addLayout(progress_layout)

        # Buttons Area
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 8, 0, 0)
        
        self.lock_btn = QPushButton("🔒")
        self.lock_btn.setStyleSheet("font-size: 20px;")
        self.lock_btn.clicked.connect(self.toggle_lock)
        
        self.seek_bwd_btn = QPushButton("↺")
        self.seek_bwd_btn.setStyleSheet("font-size: 20px;")
        self.seek_bwd_btn.clicked.connect(lambda: self.seek_relative(-10000))
        
        self.prev_btn = QPushButton("⏮")
        self.prev_btn.setStyleSheet("font-size: 24px;")
        self.prev_btn.clicked.connect(self.play_previous)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setStyleSheet("font-size: 36px;")
        self.play_btn.clicked.connect(self.play_pause)
        
        self.next_btn = QPushButton("⏭")
        self.next_btn.setStyleSheet("font-size: 24px;")
        self.next_btn.clicked.connect(self.play_next)
        
        self.seek_fwd_btn = QPushButton("↻")
        self.seek_fwd_btn.setStyleSheet("font-size: 20px;")
        self.seek_fwd_btn.clicked.connect(lambda: self.seek_relative(10000))
        
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setStyleSheet("font-size: 20px;")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        controls_layout.addWidget(self.lock_btn)
        controls_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        controls_layout.addWidget(self.seek_bwd_btn)
        controls_layout.addSpacing(15)
        controls_layout.addWidget(self.prev_btn)
        controls_layout.addSpacing(15)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addSpacing(15)
        controls_layout.addWidget(self.next_btn)
        controls_layout.addSpacing(15)
        controls_layout.addWidget(self.seek_fwd_btn)
        controls_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        controls_layout.addWidget(self.fullscreen_btn)

        bottom_layout.addLayout(controls_layout)

        # Slide-in Track Panel (Right Side)
        self.side_panel = QWidget(self.video_container)
        self.side_panel.setObjectName("sidePanel")
        self.side_panel.hide()
        
        side_layout = QVBoxLayout(self.side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        
        self.side_panel_title = QLabel("Tracks")
        self.side_panel_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 12px;")
        side_layout.addWidget(self.side_panel_title)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        side_layout.addWidget(self.scroll_area)

        # Overlays: Notifications & Tools
        self.notification_label = QLabel("", self.video_container)
        self.notification_label.setObjectName("notificationLabel")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.hide()
        self.notification_timer = QTimer(self)
        self.notification_timer.setSingleShot(True)
        self.notification_timer.timeout.connect(self.notification_label.hide)
        
        self.progress_tooltip = QLabel("00:00", self.video_container)
        self.progress_tooltip.setObjectName("progressTooltip")
        self.progress_tooltip.hide()
        
        self.unlock_btn = QPushButton("🔓", self.video_container)
        self.unlock_btn.setObjectName("unlockBtn")
        self.unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_btn.clicked.connect(self.toggle_lock)
        self.unlock_btn.hide()

        player_layout = QVBoxLayout(self.player_page)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.addWidget(self.video_container)
        
        self.stacked_widget.addWidget(self.landing_page)
        self.stacked_widget.addWidget(self.player_page)
        self.stacked_widget.setCurrentIndex(0)
        
        # Install event filter AFTER all UI elements are fully constructed
        self.video_container.installEventFilter(self)

    def eventFilter(self, source, event):
        # Handle Layout Resizing & Fullscreen logic dynamically
        if source == getattr(self, 'video_container', None) and event.type() == QEvent.Type.Resize:
            w = self.video_container.width()
            h = self.video_container.height()
            
            self.video_frame.setGeometry(0, 0, w, h)
            self.top_bar.setGeometry(0, 0, w, 80)
            
            # Fullscreen Layout Override (Floating Pill)
            if self.isFullScreen():
                b_w = min(800, int(w * 0.75))
                b_x = (w - b_w) // 2
                b_y = h - 110 - int(h * 0.05) # 5% from bottom
                self.bottom_bar.setGeometry(b_x, b_y, b_w, 110)
                self.bottom_bar.setStyleSheet("background-color: rgba(0, 0, 0, 153); border-radius: 12px;") # black/60
            else:
                self.bottom_bar.setGeometry(0, h - 110, w, 110)
                self.bottom_bar.setStyleSheet("") # Revert to QSS default
            
            # Side Panel position
            p_w = 320
            if self.active_panel:
                self.side_panel.setGeometry(w - p_w, 0, p_w, h)
            else:
                self.side_panel.setGeometry(w, 0, p_w, h)
            
            nl_w = self.notification_label.width()
            nl_h = self.notification_label.height()
            self.notification_label.setGeometry((w - nl_w) // 2, (h - nl_h) // 2, nl_w, nl_h)
            self.unlock_btn.setGeometry(w - 75, 24, 50, 50)
            
        # Hover Tooltip Logic for Progress Slider
        elif source == getattr(self, 'position_slider', None):
            if event.type() == QEvent.Type.MouseMove and self.media_player.get_length() > 0:
                x = event.pos().x()
                width = self.position_slider.width()
                if width > 0:
                    percent = max(0, min(1, x / width))
                    time_ms = percent * self.media_player.get_length()
                    self.progress_tooltip.setText(self.format_time(time_ms))
                    self.progress_tooltip.adjustSize()
                    
                    # Map position to parent container
                    global_pos = self.position_slider.mapTo(self.video_container, event.pos())
                    t_w = self.progress_tooltip.width()
                    self.progress_tooltip.move(global_pos.x() - (t_w // 2), global_pos.y() - 35)
                    self.progress_tooltip.show()
            elif event.type() == QEvent.Type.Leave:
                self.progress_tooltip.hide()
            
        return super().eventFilter(source, event)

    def toggle_time_display(self, event):
        self.show_remaining_time = not getattr(self, 'show_remaining_time', False)
        self.update_ui()

    def show_notification(self, text):
        self.notification_label.setText(text)
        self.notification_label.adjustSize()
        w = self.video_container.width()
        h = self.video_container.height()
        nl_w = self.notification_label.width()
        nl_h = self.notification_label.height()
        self.notification_label.move((w - nl_w) // 2, (h - nl_h) // 2)
        
        self.notification_label.show()
        self.notification_timer.start(1500)

    def slider_pressed(self):
        self.is_slider_dragging = True

    def slider_released(self):
        self.is_slider_dragging = False
        if self.media_player.get_state() != vlc.State.NothingSpecial:
            self.media_player.set_time(self.position_slider.value())

    def go_back(self):
        self.stop_video()
        self.stacked_widget.setCurrentIndex(0)
        self.playlist.clear()
        self.is_locked = False
        self.unlock_btn.hide()
        if self.active_panel:
            self.toggle_side_panel(self.active_panel)

    def toggle_lock(self):
        self.is_locked = not self.is_locked
        if self.is_locked:
            self.show_notification("Controls Locked")
            self.top_bar.hide()
            self.bottom_bar.hide()
            if self.active_panel: self.toggle_side_panel(self.active_panel)
            self.unlock_btn.show()
            self.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self.show_notification("Controls Unlocked")
            self.unlock_btn.hide()
            self.show_controls()

    def seek_relative(self, ms):
        if self.media_player.is_playing():
            new_time = max(0, self.media_player.get_time() + ms)
            self.media_player.set_time(new_time)

    def setup_autohide(self):
        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)
        self.player_page.setMouseTracking(True)
        self.video_container.setMouseTracking(True)
        
        self.mouse_timer = QTimer(self)
        self.mouse_timer.setInterval(2000) 
        self.mouse_timer.timeout.connect(self.hide_controls)

    def mouseMoveEvent(self, event):
        if self.stacked_widget.currentIndex() == 1:
            if not self.is_locked:
                self.show_controls()
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.mouse_timer.start()
        super().mouseMoveEvent(event)
        
    def mouseDoubleClickEvent(self, event):
        if self.stacked_widget.currentIndex() == 1 and not self.is_locked:
            self.toggle_fullscreen()
        super().mouseDoubleClickEvent(event)

    def show_controls(self):
        if not self.is_locked:
            # Re-hide top bar in fullscreen when active as per spec
            if not self.isFullScreen():
                self.top_bar.show()
            self.bottom_bar.show()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.mouse_timer.start()

    def hide_controls(self):
        if self.media_player.is_playing() and self.stacked_widget.currentIndex() == 1:
            pos = self.video_container.mapFromGlobal(QCursor.pos())
            if not self.top_bar.geometry().contains(pos) and \
               not self.bottom_bar.geometry().contains(pos) and \
               not self.side_panel.geometry().contains(pos):
                self.top_bar.hide()
                self.bottom_bar.hide()
                self.setCursor(Qt.CursorShape.BlankCursor)
                if self.is_locked: self.unlock_btn.hide() # Fades lock button per spec

    def keyPressEvent(self, event):
        # Open shortcut is universal
        mods = event.modifiers()
        if mods == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_O:
            self.open_file()
            return
            
        if self.stacked_widget.currentIndex() == 0 or self.is_locked:
            # Only let Unlock work if locked
            if self.is_locked and event.key() == Qt.Key.Key_L:
                self.toggle_lock()
            return super().keyPressEvent(event)
            
        key = event.key()
        
        # Spec mappings
        if key in (Qt.Key.Key_Space, Qt.Key.Key_K):
            self.play_pause()
        elif key == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen(): self.toggle_fullscreen()
            else: self.go_back()
        elif key == Qt.Key.Key_Right:
            self.seek_relative(10000 if mods == Qt.KeyboardModifier.ShiftModifier else 5000)
        elif key == Qt.Key.Key_Left:
            self.seek_relative(-10000 if mods == Qt.KeyboardModifier.ShiftModifier else -5000)
        elif key == Qt.Key.Key_Up:
            self.change_volume(5)
        elif key == Qt.Key.Key_Down:
            self.change_volume(-5)
        elif key == Qt.Key.Key_M:
            self.media_player.audio_toggle_mute()
            self.show_notification("Muted" if self.media_player.audio_get_mute() else "Unmuted")
        elif key == Qt.Key.Key_B:
            self.cycle_track('audio')
        elif key == Qt.Key.Key_V:
            self.cycle_track('subtitle')
        elif key == Qt.Key.Key_L:
            self.toggle_lock()
        else:
            super().keyPressEvent(event)

    def change_volume(self, delta):
        vol = max(0, min(100, self.media_player.audio_get_volume() + delta))
        self.media_player.audio_set_volume(vol)
        self.show_notification(f"Volume: {vol}%")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.top_bar.show()
        else:
            self.showFullScreen()
            self.top_bar.hide()
            
        # Re-trigger resize filter logic
        QApplication.postEvent(self.video_container, QEvent(QEvent.Type.Resize))

    def open_file(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Open Video File(s)", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.webm);;All Files (*)")
        if filenames:
            self.playlist = filenames
            self.current_index = 0
            self.play_current_index()

    def play_current_index(self):
        if not self.playlist: return
        
        filename = self.playlist[self.current_index]
        self.stacked_widget.setCurrentIndex(1)
        self.video_title.setText(os.path.basename(filename))
        
        self.tracks_populated = False
        self.position_slider.setValue(0)
        if self.active_panel: self.toggle_side_panel(self.active_panel) # Hide panel if open
        
        media = self.instance.media_new(filename)
        self.media_player.set_media(media)
        self.media_player.play()
        self.timer.start()
        self.play_btn.setText("⏸")
        self.mouse_timer.start()
        
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.playlist) - 1)

    def play_next(self):
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self.play_current_index()

    def play_previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.play_current_index()

    def play_pause(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_btn.setText("▶")
            self.show_controls()
            self.mouse_timer.stop() 
        else:
            self.media_player.play()
            self.play_btn.setText("⏸")
            self.mouse_timer.start()

    def stop_video(self):
        self.media_player.stop()
        self.play_btn.setText("▶")
        self.position_slider.setValue(0)
        self.time_current.setText("00:00")
        self.time_total.setText("00:00")
        self.show_controls()

    def update_ui(self):
        if self.media_player.get_state() in [vlc.State.Playing, vlc.State.Paused]:
            length = self.media_player.get_length()
            current_time = self.media_player.get_time()
            
            if length > 0 and not self.tracks_populated:
                self.tracks_populated = True
                self.position_slider.setMaximum(length)
            
            if length > 0 and current_time >= length - 500:
                if self.current_index < len(self.playlist) - 1: self.play_next()
            
            if length > 0:
                if not self.is_slider_dragging:
                    self.position_slider.setValue(current_time)
                
                self.time_current.setText(self.format_time(current_time))
                if self.show_remaining_time:
                    self.time_total.setText(f"-{self.format_time(length - current_time)}")
                else:
                    self.time_total.setText(self.format_time(length))

    def format_time(self, ms):
        if ms < 0: return "00:00"
        s = round(ms / 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def toggle_side_panel(self, p_type):
        w = self.video_container.width()
        h = self.video_container.height()
        p_w = 320
        
        if self.active_panel == p_type:
            # Close it
            self.active_panel = None
            end_rect = QRect(w, 0, p_w, h)
        else:
            # Open it
            self.active_panel = p_type
            self.side_panel_title.setText("Audio Tracks" if p_type == "audio" else "Subtitle Tracks")
            self.populate_tracks()
            self.side_panel.setGeometry(w, 0, p_w, h)
            self.side_panel.show()
            end_rect = QRect(w - p_w, 0, p_w, h)
            
        self.panel_anim = QPropertyAnimation(self.side_panel, b"geometry")
        self.panel_anim.setDuration(250)
        self.panel_anim.setEndValue(end_rect)
        self.panel_anim.start()

    def populate_tracks(self):
        if not self.active_panel: return
        
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
                
        if self.active_panel == "audio":
            tracks = self.media_player.audio_get_track_description()
            curr = self.media_player.audio_get_track()
            setter = self.media_player.audio_set_track
        else:
            # Subtitles have default Off button
            off_btn = QPushButton("Off")
            off_btn.setProperty("class", "trackBtn")
            if self.media_player.video_get_spu() == -1:
                off_btn.setStyleSheet("background-color: #2563eb;")
            off_btn.clicked.connect(lambda: self.switch_track("subtitle", -1, "Subtitles Off", self.media_player.video_set_spu))
            self.scroll_layout.addWidget(off_btn)
            
            tracks = self.media_player.video_get_spu_description()
            curr = self.media_player.video_get_spu()
            setter = self.media_player.video_set_spu
            
        if tracks:
            for t in tracks:
                t_id = t[0]
                if self.active_panel == "subtitle" and t_id == -1: continue 
                
                t_name = t[1].decode('utf-8') if isinstance(t[1], bytes) else str(t[1])
                btn = QPushButton(t_name)
                btn.setProperty("class", "trackBtn")
                if t_id == curr:
                    btn.setStyleSheet("background-color: #2563eb;") # Active highlight
                
                btn.clicked.connect(lambda checked, tid=t_id, tn=t_name: self.switch_track(self.active_panel, tid, tn, setter))
                self.scroll_layout.addWidget(btn)
                
        self.scroll_layout.addStretch()

    def switch_track(self, p_type, tid, tname, setter):
        setter(tid)
        self.show_notification(tname)
        self.populate_tracks()

    def cycle_track(self, track_type):
        if track_type == 'audio':
            tracks = self.media_player.audio_get_track_description()
            curr = self.media_player.audio_get_track()
            setter = self.media_player.audio_set_track
        else:
            tracks = self.media_player.video_get_spu_description()
            curr = self.media_player.video_get_spu()
            setter = self.media_player.video_set_spu
            
        if not tracks or len(tracks) <= 1: return
        
        idx = 0
        for i, t in enumerate(tracks):
            if t[0] == curr:
                idx = i
                break
        
        next_idx = (idx + 1) % len(tracks)
        next_id = tracks[next_idx][0]
        name = tracks[next_idx][1].decode('utf-8') if isinstance(tracks[next_idx][1], bytes) else str(tracks[next_idx][1])
        
        setter(next_id)
        self.show_notification(name)
        if self.active_panel == track_type: self.populate_tracks()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())